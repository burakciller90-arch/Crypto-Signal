from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from crypto_signal.data.adapters.bybit_liquidations import (
    BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION,
    parse_bybit_all_liquidation_payload,
)
from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.liquidations import (
    LiquidationFeedCoverage,
    LiquidationObservation,
    build_liquidation_feed_coverage,
)
from crypto_signal.data.models import DataSource, Exchange

BYBIT_LINEAR_PUBLIC_WS_URL = "wss://stream.bybit.com/v5/public/linear"
BYBIT_LIQUIDATION_STREAM_VERSION = "bybit-v5-all-liquidation-ws/1"


class LiquidationTransportEventKind(StrEnum):
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    ACTIVITY = "activity"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class LiquidationTransportEvent:
    kind: LiquidationTransportEventKind
    observed_at_ms: int

    def __post_init__(self) -> None:
        if self.observed_at_ms < 0:
            raise ValueError(
                "liquidation transport observation cannot be negative"
            )


@dataclass(frozen=True, slots=True)
class BybitLiquidationWireBatch:
    symbol: str
    source_timestamp_ms: int
    event_at_ms: int
    ingested_at_ms: int
    raw_payload: dict[str, object]
    events: tuple[LiquidationObservation, ...]
    coverage: LiquidationFeedCoverage

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Bybit liquidation wire symbol must be uppercase")
        if min(
            self.source_timestamp_ms,
            self.event_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("Bybit liquidation wire timestamps cannot be negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("Bybit liquidation wire event cannot postdate source")
        if not self.events:
            raise ValueError(
                "Bybit liquidation wire batch requires provider liquidation rows"
            )
        if (
            self.coverage.exchange is not Exchange.BYBIT
            or self.coverage.instrument_type
            is not DerivativesInstrumentType.LINEAR_PERPETUAL
            or self.coverage.symbol != self.symbol
        ):
            raise ValueError("Bybit liquidation wire coverage context mismatch")
        if self.coverage.coverage_end_ms != self.source_timestamp_ms:
            raise ValueError("Bybit liquidation wire coverage end mismatch")
        if self.coverage.observed_at_ms != self.ingested_at_ms:
            raise ValueError("Bybit liquidation wire coverage observation mismatch")
        if self.coverage.coverage_start_ms != min(
            item.event_at_ms for item in self.events
        ):
            raise ValueError("Bybit liquidation wire coverage start mismatch")
        for event in self.events:
            if (
                event.exchange is not Exchange.BYBIT
                or event.instrument_type
                is not DerivativesInstrumentType.LINEAR_PERPETUAL
                or event.symbol != self.symbol
            ):
                raise ValueError("Bybit liquidation wire event context mismatch")
            if max(
                event.event_at_ms,
                event.source_timestamp_ms,
                event.ingested_at_ms,
            ) > self.coverage.observed_at_ms:
                raise ValueError(
                    "Bybit liquidation wire event exceeds coverage observation"
                )


def build_bybit_liquidation_wire_batch(
    payload: dict[str, object],
    *,
    expected_symbol: str,
    ingested_at_ms: int | None = None,
) -> BybitLiquidationWireBatch:
    seen_at_ms = (
        time.time_ns() // 1_000_000
        if ingested_at_ms is None
        else ingested_at_ms
    )
    events = parse_bybit_all_liquidation_payload(
        payload,
        expected_symbol=expected_symbol,
        ingested_at_ms=seen_at_ms,
    )
    if not events:
        raise ValueError(
            "Bybit all-liquidation provider message must contain rows; "
            "silence is not converted into zero-event coverage"
        )
    source_timestamp_ms = int(cast(int | str, payload["ts"]))
    coverage_start_ms = min(item.event_at_ms for item in events)
    coverage = build_liquidation_feed_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol=expected_symbol,
        coverage_start_ms=coverage_start_ms,
        coverage_end_ms=source_timestamp_ms,
        observed_at_ms=seen_at_ms,
        source=DataSource.WEBSOCKET,
        adapter_version=BYBIT_ALL_LIQUIDATION_ADAPTER_VERSION,
    )
    return BybitLiquidationWireBatch(
        symbol=expected_symbol,
        source_timestamp_ms=source_timestamp_ms,
        event_at_ms=max(item.event_at_ms for item in events),
        ingested_at_ms=seen_at_ms,
        raw_payload=payload,
        events=events,
        coverage=coverage,
    )


def bybit_liquidation_subscription(symbols: tuple[str, ...]) -> str:
    normalized = _normalize_symbols(symbols)
    return json.dumps(
        {
            "op": "subscribe",
            "args": [
                f"allLiquidation.{symbol}"
                for symbol in normalized
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


class BybitLinearLiquidationStream:
    WS_URL = BYBIT_LINEAR_PUBLIC_WS_URL
    ADAPTER_VERSION = BYBIT_LIQUIDATION_STREAM_VERSION

    def __init__(
        self,
        *,
        url: str | None = None,
        proxy: str | Literal[True] | None = True,
    ) -> None:
        self.url = url or self.WS_URL
        self.proxy = proxy

    async def stream_wire_batches(
        self,
        *,
        symbols: tuple[str, ...],
        transport_event_callback: (
            Callable[[LiquidationTransportEvent], None] | None
        ) = None,
    ) -> AsyncGenerator[BybitLiquidationWireBatch, None]:
        normalized_symbols = _normalize_symbols(symbols)
        subscription = bybit_liquidation_subscription(normalized_symbols)

        async for websocket in connect(
            self.url,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
            proxy=self.proxy,
        ):
            heartbeat = asyncio.create_task(self._heartbeat(websocket))
            subscription_confirmed = False
            disconnected_reported = False
            try:
                connected_at_ms = time.time_ns() // 1_000_000
                _emit_transport_event(
                    transport_event_callback,
                    LiquidationTransportEventKind.CONNECTED,
                    connected_at_ms,
                )
                await websocket.send(subscription)
                async for raw_message in websocket:
                    observed_at_ms = time.time_ns() // 1_000_000
                    _emit_transport_event(
                        transport_event_callback,
                        LiquidationTransportEventKind.ACTIVITY,
                        observed_at_ms,
                    )
                    payload = _json_object(raw_message)
                    topic = payload.get("topic")
                    if topic is None:
                        if str(payload.get("op", "")) == "subscribe":
                            if payload.get("success") is not True:
                                raise ValueError(
                                    "Bybit liquidation subscription rejected"
                                )
                            if not subscription_confirmed:
                                subscription_confirmed = True
                                _emit_transport_event(
                                    transport_event_callback,
                                    LiquidationTransportEventKind.SUBSCRIBED,
                                    observed_at_ms,
                                )
                        continue
                    topic_text = str(topic)
                    if not topic_text.startswith("allLiquidation."):
                        raise ValueError(
                            "unexpected topic on Bybit liquidation stream"
                        )
                    if not subscription_confirmed:
                        subscription_confirmed = True
                        _emit_transport_event(
                            transport_event_callback,
                            LiquidationTransportEventKind.SUBSCRIBED,
                            observed_at_ms,
                        )
                    symbol = _topic_symbol(
                        topic_text,
                        allowed=normalized_symbols,
                    )
                    yield build_bybit_liquidation_wire_batch(
                        payload,
                        expected_symbol=symbol,
                        ingested_at_ms=observed_at_ms,
                    )
            except ConnectionClosed:
                _emit_transport_event(
                    transport_event_callback,
                    LiquidationTransportEventKind.DISCONNECTED,
                    time.time_ns() // 1_000_000,
                )
                disconnected_reported = True
                continue
            finally:
                if not disconnected_reported:
                    _emit_transport_event(
                        transport_event_callback,
                        LiquidationTransportEventKind.DISCONNECTED,
                        time.time_ns() // 1_000_000,
                    )
                heartbeat.cancel()
                with suppress(asyncio.CancelledError, ConnectionClosed):
                    await heartbeat

    @staticmethod
    async def _heartbeat(websocket: ClientConnection) -> None:
        while True:
            await asyncio.sleep(20)
            await websocket.send(json.dumps({"op": "ping"}))


def _emit_transport_event(
    callback: Callable[[LiquidationTransportEvent], None] | None,
    kind: LiquidationTransportEventKind,
    observed_at_ms: int,
) -> None:
    if callback is None:
        return
    callback(
        LiquidationTransportEvent(
            kind=kind,
            observed_at_ms=observed_at_ms,
        )
    )


def _normalize_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(value).upper() for value in symbols))
    if not normalized or any(not value for value in normalized):
        raise ValueError("Bybit liquidation stream symbols must be non-empty")
    if any(not value.endswith("USDT") for value in normalized):
        raise ValueError(
            "development liquidation collector supports USDT linear symbols only"
        )
    return normalized


def _topic_symbol(
    topic: str,
    *,
    allowed: tuple[str, ...],
) -> str:
    prefix = "allLiquidation."
    if not topic.startswith(prefix):
        raise ValueError("unexpected Bybit liquidation topic")
    symbol = topic[len(prefix):]
    if symbol not in allowed:
        raise ValueError("Bybit liquidation topic symbol was not subscribed")
    return symbol


def _json_object(raw_message: str | bytes) -> dict[str, object]:
    payload = json.loads(raw_message)
    if not isinstance(payload, dict):
        raise TypeError("Bybit liquidation websocket payload must be an object")
    return cast(dict[str, object], payload)
