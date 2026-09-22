from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    OrderBookSnapshot,
    PublicTradeObservation,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType

MicrostructureStreamEvent = OrderBookSnapshot | PublicTradeObservation


@dataclass(frozen=True, slots=True)
class BybitMicrostructureWireEvent:
    symbol: str
    channel: str
    event_kind: str
    source_timestamp_ms: int
    event_at_ms: int
    ingested_at_ms: int
    sequence: int
    update_id: int
    raw_payload: dict[str, object]
    orderbook: OrderBookSnapshot | None = None
    trades: tuple[PublicTradeObservation, ...] = ()

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not self.channel.strip():
            raise ValueError("Bybit wire-event channel must be non-empty")
        if not self.event_kind.strip():
            raise ValueError("Bybit wire-event kind must be non-empty")
        if min(
            self.source_timestamp_ms,
            self.event_at_ms,
            self.ingested_at_ms,
            self.sequence,
            self.update_id,
        ) < 0:
            raise ValueError("Bybit wire-event numeric fields must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("Bybit wire event cannot postdate source timestamp")
        if self.orderbook is None and not self.trades:
            raise ValueError("Bybit wire event must contain normalized evidence")
        if self.orderbook is not None and self.trades:
            raise ValueError("Bybit wire event cannot mix book and trades")


@dataclass(slots=True)
class BybitSpotOrderBookState:
    symbol: str
    depth: int
    adapter_version: str
    _bids: dict[Decimal, Decimal] = field(default_factory=dict)
    _asks: dict[Decimal, Decimal] = field(default_factory=dict)
    _initialized: bool = False
    _last_sequence: int = -1
    _last_update_id: int = -1

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if self.depth not in {1, 50, 200, 1000}:
            raise ValueError("Bybit spot orderbook depth must be one of 1,50,200,1000")
        if not self.adapter_version.strip():
            raise ValueError("adapter_version must be non-empty")

    def apply_payload(
        self,
        payload: dict[str, object],
        *,
        ingested_at_ms: int | None = None,
    ) -> OrderBookSnapshot:
        expected_topic = f"orderbook.{self.depth}.{self.symbol}"
        if payload.get("topic") != expected_topic:
            raise ValueError("unexpected Bybit orderbook topic")

        message_type = str(payload.get("type", ""))
        if message_type not in {"snapshot", "delta"}:
            raise ValueError("Bybit orderbook message type must be snapshot or delta")

        source_timestamp_ms = int(cast(int | str, payload["ts"]))
        event_at_ms = int(cast(int | str, payload["cts"]))
        data = cast(dict[str, object], payload["data"])
        if data.get("s") != self.symbol:
            raise ValueError("Bybit orderbook symbol mismatch")

        update_id = int(cast(int | str, data["u"]))
        sequence = int(cast(int | str, data["seq"]))
        if update_id < 0 or sequence < 0:
            raise ValueError("Bybit orderbook update/sequence must be non-negative")

        reset = message_type == "snapshot" or update_id == 1
        if reset:
            self._bids.clear()
            self._asks.clear()
            self._apply_levels(self._bids, cast(list[list[str]], data.get("b", [])))
            self._apply_levels(self._asks, cast(list[list[str]], data.get("a", [])))
            self._initialized = True
        else:
            if not self._initialized:
                raise ValueError("Bybit orderbook delta arrived before snapshot")
            if sequence < self._last_sequence:
                raise ValueError("Bybit orderbook sequence regressed")
            if update_id < self._last_update_id:
                raise ValueError("Bybit orderbook update id regressed")
            self._apply_levels(self._bids, cast(list[list[str]], data.get("b", [])))
            self._apply_levels(self._asks, cast(list[list[str]], data.get("a", [])))

        if not self._bids or not self._asks:
            raise ValueError("Bybit orderbook state must retain both sides")

        self._last_sequence = sequence
        self._last_update_id = update_id
        seen_at_ms = (
            ingested_at_ms
            if ingested_at_ms is not None
            else time.time_ns() // 1_000_000
        )
        bids = tuple(
            OrderBookLevel(price=price, size=size)
            for price, size in sorted(
                self._bids.items(),
                key=lambda item: item[0],
                reverse=True,
            )[: self.depth]
        )
        asks = tuple(
            OrderBookLevel(price=price, size=size)
            for price, size in sorted(
                self._asks.items(),
                key=lambda item: item[0],
            )[: self.depth]
        )

        return build_orderbook_snapshot(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=self.symbol,
            event_at_ms=event_at_ms,
            source_timestamp_ms=source_timestamp_ms,
            response_time_ms=source_timestamp_ms,
            ingested_at_ms=seen_at_ms,
            update_id=update_id,
            sequence=sequence,
            bids=bids,
            asks=asks,
            source=DataSource.WEBSOCKET,
            adapter_version=self.adapter_version,
        )

    @staticmethod
    def _apply_levels(
        book: dict[Decimal, Decimal],
        rows: list[list[str]],
    ) -> None:
        for row in rows:
            if len(row) < 2:
                raise ValueError("Bybit orderbook delta level is incomplete")
            price = Decimal(str(row[0]))
            size = Decimal(str(row[1]))
            if price.is_nan() or price.is_infinite() or price <= Decimal(0):
                raise ValueError("Bybit orderbook price must be finite and positive")
            if size.is_nan() or size.is_infinite() or size < Decimal(0):
                raise ValueError("Bybit orderbook size must be finite and non-negative")
            if size == Decimal(0):
                book.pop(price, None)
            else:
                book[price] = size


def parse_bybit_public_trade_payload(
    payload: dict[str, object],
    *,
    expected_symbol: str,
    adapter_version: str,
    ingested_at_ms: int | None = None,
) -> tuple[PublicTradeObservation, ...]:
    _require_symbol(expected_symbol)
    if not adapter_version.strip():
        raise ValueError("adapter_version must be non-empty")
    if payload.get("topic") != f"publicTrade.{expected_symbol}":
        raise ValueError("unexpected Bybit public-trade topic")
    if payload.get("type") != "snapshot":
        raise ValueError("Bybit public-trade message type must be snapshot")

    source_timestamp_ms = int(cast(int | str, payload["ts"]))
    rows = cast(list[dict[str, object]], payload["data"])
    seen_at_ms = (
        ingested_at_ms
        if ingested_at_ms is not None
        else time.time_ns() // 1_000_000
    )
    observations: list[PublicTradeObservation] = []
    seen_exec_ids: set[str] = set()
    for row in rows:
        if row.get("s") != expected_symbol:
            raise ValueError("Bybit public-trade symbol mismatch")
        exec_id = str(row["i"])
        if not exec_id:
            raise ValueError("Bybit public-trade id must be non-empty")
        if exec_id in seen_exec_ids:
            raise ValueError("Bybit public-trade payload contains duplicate trade id")
        seen_exec_ids.add(exec_id)

        side_raw = str(row["S"]).lower()
        if side_raw not in {"buy", "sell"}:
            raise ValueError("Bybit public-trade side must be Buy or Sell")
        observations.append(
            build_public_trade_observation(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol=expected_symbol,
                exec_id=exec_id,
                sequence=int(cast(int | str, row["seq"])),
                aggressor_side=AggressorSide(side_raw),
                price=Decimal(str(row["p"])),
                size=Decimal(str(row["v"])),
                event_at_ms=int(cast(int | str, row["T"])),
                source_timestamp_ms=source_timestamp_ms,
                ingested_at_ms=seen_at_ms,
                is_block_trade=bool(row.get("BT", False)),
                is_rpi_trade=bool(row.get("RPI", False)),
                source=DataSource.WEBSOCKET,
                adapter_version=adapter_version,
            )
        )
    return tuple(observations)


class BybitSpotMicrostructureStream:
    WS_URL = "wss://stream.bybit.com/v5/public/spot"
    ADAPTER_VERSION = "bybit-v5-spot-microstructure-ws/1"

    def __init__(
        self,
        *,
        url: str | None = None,
        proxy: str | Literal[True] | None = True,
    ) -> None:
        self.url = url or self.WS_URL
        self.proxy = proxy

    async def stream_events(
        self,
        *,
        symbols: tuple[str, ...],
        depth: int = 50,
    ) -> AsyncGenerator[MicrostructureStreamEvent, None]:
        async for wire_event in self.stream_wire_events(
            symbols=symbols,
            depth=depth,
        ):
            if wire_event.orderbook is not None:
                yield wire_event.orderbook
            for trade in wire_event.trades:
                yield trade

    async def stream_wire_events(
        self,
        *,
        symbols: tuple[str, ...],
        depth: int = 50,
    ) -> AsyncGenerator[BybitMicrostructureWireEvent, None]:
        normalized_symbols = _normalize_symbols(symbols)
        if depth not in {1, 50, 200, 1000}:
            raise ValueError("Bybit spot orderbook depth must be one of 1,50,200,1000")

        topics: list[str] = []
        for symbol in normalized_symbols:
            topics.append(f"orderbook.{depth}.{symbol}")
            topics.append(f"publicTrade.{symbol}")
        subscription = json.dumps({"op": "subscribe", "args": topics})

        async for websocket in connect(
            self.url,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
            proxy=self.proxy,
        ):
            states = {
                symbol: BybitSpotOrderBookState(
                    symbol=symbol,
                    depth=depth,
                    adapter_version=self.ADAPTER_VERSION,
                )
                for symbol in normalized_symbols
            }
            heartbeat = asyncio.create_task(self._heartbeat(websocket))
            try:
                await websocket.send(subscription)
                async for raw_message in websocket:
                    payload = _json_object(raw_message)
                    topic = payload.get("topic")
                    if topic is None:
                        continue
                    topic_text = str(topic)
                    ingested_at_ms = time.time_ns() // 1_000_000

                    if topic_text.startswith("orderbook."):
                        symbol = _topic_symbol(
                            topic_text,
                            prefix=f"orderbook.{depth}.",
                            allowed=normalized_symbols,
                        )
                        data = cast(dict[str, object], payload["data"])
                        message_type = str(payload.get("type", ""))
                        snapshot = states[symbol].apply_payload(
                            payload,
                            ingested_at_ms=ingested_at_ms,
                        )
                        yield BybitMicrostructureWireEvent(
                            symbol=symbol,
                            channel=f"orderbook.{depth}",
                            event_kind=message_type,
                            source_timestamp_ms=int(
                                cast(int | str, payload["ts"])
                            ),
                            event_at_ms=int(cast(int | str, payload["cts"])),
                            ingested_at_ms=ingested_at_ms,
                            sequence=int(cast(int | str, data["seq"])),
                            update_id=int(cast(int | str, data["u"])),
                            raw_payload=payload,
                            orderbook=snapshot,
                        )
                        continue

                    if topic_text.startswith("publicTrade."):
                        symbol = _topic_symbol(
                            topic_text,
                            prefix="publicTrade.",
                            allowed=normalized_symbols,
                        )
                        trades = parse_bybit_public_trade_payload(
                            payload,
                            expected_symbol=symbol,
                            adapter_version=self.ADAPTER_VERSION,
                            ingested_at_ms=ingested_at_ms,
                        )
                        if not trades:
                            raise ValueError(
                                "Bybit public-trade payload must contain trades"
                            )
                        yield BybitMicrostructureWireEvent(
                            symbol=symbol,
                            channel="publicTrade",
                            event_kind="trade_batch",
                            source_timestamp_ms=int(
                                cast(int | str, payload["ts"])
                            ),
                            event_at_ms=max(
                                trade.event_at_ms for trade in trades
                            ),
                            ingested_at_ms=ingested_at_ms,
                            sequence=max(trade.sequence for trade in trades),
                            update_id=0,
                            raw_payload=payload,
                            trades=trades,
                        )
                        continue

                    raise ValueError(
                        f"unexpected Bybit microstructure topic: {topic_text!r}"
                    )
            except ConnectionClosed:
                continue
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError, ConnectionClosed):
                    await heartbeat

    @staticmethod
    async def _heartbeat(websocket: ClientConnection) -> None:
        while True:
            await asyncio.sleep(20)
            await websocket.send(json.dumps({"op": "ping"}))


def _normalize_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    if not symbols:
        raise ValueError("Bybit microstructure stream requires at least one symbol")
    if len(set(symbols)) != len(symbols):
        raise ValueError("Bybit microstructure stream symbols must be unique")
    for symbol in symbols:
        _require_symbol(symbol)
    return symbols


def _require_symbol(symbol: str) -> None:
    if not symbol or symbol != symbol.upper():
        raise ValueError("Bybit microstructure symbol must be non-empty uppercase")


def _topic_symbol(
    topic: str,
    *,
    prefix: str,
    allowed: tuple[str, ...],
) -> str:
    if not topic.startswith(prefix):
        raise ValueError("Bybit topic prefix mismatch")
    symbol = topic[len(prefix) :]
    if symbol not in allowed:
        raise ValueError("Bybit topic symbol was not subscribed")
    return symbol


def _json_object(message: str | bytes) -> dict[str, object]:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    payload = json.loads(message)
    if not isinstance(payload, dict):
        raise TypeError("Bybit WebSocket payload must be an object")
    return cast(dict[str, object], payload)
