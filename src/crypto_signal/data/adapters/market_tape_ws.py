from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import cast

from crypto_signal.data.market_tape_stream import (
    MarketTapeChannel,
    RawMarketEvent,
    build_raw_market_event,
)
from crypto_signal.data.microstructure import (
    AggressorSide,
    PublicTradeObservation,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType

BINANCE_AGG_TRADE_ADAPTER_VERSION = "binance-spot-aggtrade-ws/1"
BINANCE_DEPTH_ADAPTER_VERSION = "binance-spot-depth-ws/1"
BYBIT_PUBLIC_TRADE_ADAPTER_VERSION = "bybit-v5-spot-public-trade-ws/1"
BYBIT_ORDERBOOK_ADAPTER_VERSION = "bybit-v5-spot-orderbook-ws/1"


def parse_binance_agg_trade_message(
    message: str | bytes,
    *,
    symbol: str,
    ingested_at_ms: int | None = None,
) -> tuple[RawMarketEvent, PublicTradeObservation]:
    payload = _json_message(message)
    if payload.get("e") != "aggTrade":
        raise ValueError("unexpected Binance aggTrade event")
    if payload.get("s") != symbol:
        raise ValueError("unexpected Binance aggTrade symbol")
    _require_upper_symbol(symbol)

    source_timestamp_ms = int(cast(int | str, payload["E"]))
    event_at_ms = int(cast(int | str, payload["T"]))
    first_sequence = int(cast(int | str, payload["f"]))
    last_sequence = int(cast(int | str, payload["l"]))
    agg_trade_id = int(cast(int | str, payload["a"]))
    seen_at_ms = _seen_at_ms(ingested_at_ms)
    buyer_is_maker = bool(payload["m"])

    raw = build_raw_market_event(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        channel=MarketTapeChannel.PUBLIC_TRADE,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=seen_at_ms,
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        payload=payload,
        adapter_version=BINANCE_AGG_TRADE_ADAPTER_VERSION,
    )
    trade = build_public_trade_observation(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        exec_id=str(agg_trade_id),
        sequence=agg_trade_id,
        aggressor_side=(
            AggressorSide.SELL if buyer_is_maker else AggressorSide.BUY
        ),
        price=Decimal(str(payload["p"])),
        size=Decimal(str(payload["q"])),
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=seen_at_ms,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.WEBSOCKET,
        adapter_version=BINANCE_AGG_TRADE_ADAPTER_VERSION,
    )
    return raw, trade


def parse_binance_depth_message(
    message: str | bytes,
    *,
    symbol: str,
    ingested_at_ms: int | None = None,
) -> RawMarketEvent:
    payload = _json_message(message)
    if payload.get("e") != "depthUpdate":
        raise ValueError("unexpected Binance depth event")
    if payload.get("s") != symbol:
        raise ValueError("unexpected Binance depth symbol")
    _require_upper_symbol(symbol)
    _validate_depth_rows(payload.get("b"), "Binance bid delta")
    _validate_depth_rows(payload.get("a"), "Binance ask delta")

    source_timestamp_ms = int(cast(int | str, payload["E"]))
    first_sequence = int(cast(int | str, payload["U"]))
    last_sequence = int(cast(int | str, payload["u"]))
    return build_raw_market_event(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        channel=MarketTapeChannel.ORDERBOOK_DELTA,
        event_at_ms=source_timestamp_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=_seen_at_ms(ingested_at_ms),
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        payload=payload,
        adapter_version=BINANCE_DEPTH_ADAPTER_VERSION,
    )


def parse_bybit_public_trade_message(
    message: str | bytes,
    *,
    symbol: str,
    ingested_at_ms: int | None = None,
) -> tuple[RawMarketEvent, tuple[PublicTradeObservation, ...]]:
    payload = _json_message(message)
    expected_topic = f"publicTrade.{symbol}"
    if payload.get("topic") != expected_topic:
        raise ValueError("unexpected Bybit public-trade topic")
    if payload.get("type") != "snapshot":
        raise ValueError("unexpected Bybit public-trade message type")
    _require_upper_symbol(symbol)

    source_timestamp_ms = int(cast(int | str, payload["ts"]))
    rows = cast(list[dict[str, object]], payload["data"])
    if not rows:
        raise ValueError("Bybit public-trade payload must contain at least one trade")

    seen_at_ms = _seen_at_ms(ingested_at_ms)
    trades: list[PublicTradeObservation] = []
    seen_ids: set[str] = set()
    event_times: list[int] = []
    for row in rows:
        if row.get("s") != symbol:
            raise ValueError("Bybit public-trade symbol mismatch")
        exec_id = str(row["i"])
        if not exec_id or exec_id in seen_ids:
            raise ValueError("Bybit public-trade exec id must be unique and non-empty")
        seen_ids.add(exec_id)
        side = str(row["S"]).lower()
        if side not in {"buy", "sell"}:
            raise ValueError("Bybit public-trade side must be Buy or Sell")
        event_at_ms = int(cast(int | str, row["T"]))
        event_times.append(event_at_ms)
        trades.append(
            build_public_trade_observation(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol=symbol,
                exec_id=exec_id,
                sequence=int(cast(int | str, row["seq"])),
                aggressor_side=AggressorSide(side),
                price=Decimal(str(row["p"])),
                size=Decimal(str(row["v"])),
                event_at_ms=event_at_ms,
                source_timestamp_ms=source_timestamp_ms,
                ingested_at_ms=seen_at_ms,
                is_block_trade=bool(row.get("BT", False)),
                is_rpi_trade=bool(row.get("RPI", False)),
                source=DataSource.WEBSOCKET,
                adapter_version=BYBIT_PUBLIC_TRADE_ADAPTER_VERSION,
            )
        )

    trades.sort(key=lambda item: (item.event_at_ms, item.sequence, item.exec_id))
    raw = build_raw_market_event(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        channel=MarketTapeChannel.PUBLIC_TRADE,
        event_at_ms=max(event_times),
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=seen_at_ms,
        first_sequence=None,
        last_sequence=None,
        payload=payload,
        adapter_version=BYBIT_PUBLIC_TRADE_ADAPTER_VERSION,
    )
    return raw, tuple(trades)


def parse_bybit_orderbook_message(
    message: str | bytes,
    *,
    symbol: str,
    depth: int,
    ingested_at_ms: int | None = None,
) -> RawMarketEvent:
    payload = _json_message(message)
    expected_topic = f"orderbook.{depth}.{symbol}"
    if payload.get("topic") != expected_topic:
        raise ValueError("unexpected Bybit orderbook topic")
    if payload.get("type") not in {"snapshot", "delta"}:
        raise ValueError("unexpected Bybit orderbook message type")
    if depth <= 0:
        raise ValueError("Bybit orderbook depth must be positive")
    _require_upper_symbol(symbol)

    data = cast(dict[str, object], payload["data"])
    if data.get("s") != symbol:
        raise ValueError("Bybit orderbook symbol mismatch")
    _validate_depth_rows(data.get("b"), "Bybit bid delta")
    _validate_depth_rows(data.get("a"), "Bybit ask delta")

    source_timestamp_ms = int(cast(int | str, payload["ts"]))
    event_at_raw = payload.get("cts", data.get("cts", source_timestamp_ms))
    event_at_ms = int(cast(int | str, event_at_raw))
    update_id = int(cast(int | str, data["u"]))
    return build_raw_market_event(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        channel=MarketTapeChannel.ORDERBOOK_DELTA,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=_seen_at_ms(ingested_at_ms),
        first_sequence=update_id,
        last_sequence=update_id,
        payload=payload,
        adapter_version=BYBIT_ORDERBOOK_ADAPTER_VERSION,
    )


def _json_message(message: str | bytes) -> dict[str, object]:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    parsed = json.loads(message)
    if not isinstance(parsed, dict):
        raise ValueError("market WebSocket message must be a JSON object")
    return cast(dict[str, object], parsed)


def _seen_at_ms(value: int | None) -> int:
    return value if value is not None else time.time_ns() // 1_000_000


def _require_upper_symbol(symbol: str) -> None:
    if not symbol or symbol != symbol.upper():
        raise ValueError("market WebSocket symbol must be non-empty uppercase")


def _validate_depth_rows(value: object, label: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    for row in value:
        if not isinstance(row, list) or len(row) < 2:
            raise ValueError(f"{label} row is incomplete")
        price = Decimal(str(row[0]))
        size = Decimal(str(row[1]))
        if price.is_nan() or price.is_infinite() or price <= 0:
            raise ValueError(f"{label} price must be finite and positive")
        if size.is_nan() or size.is_infinite() or size < 0:
            raise ValueError(f"{label} size must be finite and non-negative")
