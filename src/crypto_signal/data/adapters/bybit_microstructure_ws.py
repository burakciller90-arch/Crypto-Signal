from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from decimal import Decimal
from typing import Literal, cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from crypto_signal.data.microstructure import (
    AggressorSide,
    PublicTradeObservation,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType


def parse_bybit_public_trade_message(
    message: str | bytes,
    *,
    symbol: str,
    ingested_at_ms: int | None = None,
) -> tuple[PublicTradeObservation, ...]:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    payload = cast(dict[str, object], json.loads(message))

    topic = payload.get("topic")
    if topic is None:
        return ()

    expected_topic = f"publicTrade.{symbol}"
    if topic != expected_topic:
        raise ValueError(f"unexpected Bybit public-trade topic: {topic!r}")
    if payload.get("type") not in {None, "snapshot"}:
        raise ValueError("Bybit public-trade message type must be snapshot")

    source_timestamp_ms = int(cast(int | str, payload["ts"]))
    raw_rows = cast(list[dict[str, object]], payload["data"])
    seen_at_ms = (
        ingested_at_ms
        if ingested_at_ms is not None
        else time.time_ns() // 1_000_000
    )

    trades: list[PublicTradeObservation] = []
    seen_exec_ids: set[str] = set()
    for row in raw_rows:
        if row.get("s") != symbol:
            raise ValueError("Bybit public-trade symbol mismatch")

        exec_id = str(row["i"])
        if not exec_id:
            raise ValueError("Bybit public-trade id must be non-empty")
        if exec_id in seen_exec_ids:
            raise ValueError("Bybit public-trade message contains duplicate trade id")
        seen_exec_ids.add(exec_id)

        side_raw = str(row["S"]).lower()
        if side_raw not in {"buy", "sell"}:
            raise ValueError("Bybit public-trade taker side must be Buy or Sell")

        trades.append(
            build_public_trade_observation(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol=symbol,
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
                adapter_version=BybitSpotPublicTradeStream.ADAPTER_VERSION,
            )
        )

    trades.sort(
        key=lambda item: (
            item.event_at_ms,
            item.sequence,
            item.exec_id,
        )
    )
    return tuple(trades)


class BybitSpotPublicTradeStream:
    WS_URL = "wss://stream.bybit.com/v5/public/spot"
    ADAPTER_VERSION = "bybit-v5-spot-public-trade-ws/1"

    def __init__(
        self,
        *,
        url: str | None = None,
        proxy: str | Literal[True] | None = True,
    ) -> None:
        self.url = url or self.WS_URL
        self.proxy = proxy

    async def stream_trades(
        self,
        *,
        symbol: str,
    ) -> AsyncGenerator[PublicTradeObservation, None]:
        if not symbol or symbol != symbol.upper():
            raise ValueError("Bybit public-trade symbol must be non-empty uppercase")

        topic = f"publicTrade.{symbol}"
        subscription = json.dumps({"op": "subscribe", "args": [topic]})

        async for websocket in connect(
            self.url,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
            proxy=self.proxy,
        ):
            heartbeat = asyncio.create_task(self._heartbeat(websocket))
            try:
                await websocket.send(subscription)
                async for message in websocket:
                    for trade in parse_bybit_public_trade_message(
                        message,
                        symbol=symbol,
                    ):
                        yield trade
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
