from __future__ import annotations

from collections.abc import AsyncIterable, Callable
from dataclasses import dataclass

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitMicrostructureWireEvent,
)
from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.models import Exchange
from crypto_signal.data.raw_market_tape import (
    RawMarketEvent,
    RawMarketTapeStore,
    RawMarketTapeWriteDisposition,
)


@dataclass(frozen=True, slots=True)
class MarketTapeWireCollectionResult:
    observed_messages: int
    raw_inserted: int
    raw_unchanged: int
    orderbooks_inserted: int
    orderbooks_unchanged: int
    orderbooks_skipped_by_cadence: int
    trades_inserted: int
    trades_unchanged: int

    @property
    def normalized_inserted_total(self) -> int:
        return self.orderbooks_inserted + self.trades_inserted


async def persist_bybit_wire_stream(
    *,
    store: MarketTapeStore,
    raw_store: RawMarketTapeStore,
    events: AsyncIterable[BybitMicrostructureWireEvent],
    orderbook_snapshot_interval_ms: int = 1_000,
    max_messages: int | None = None,
    progress_callback: (
        Callable[[BybitMicrostructureWireEvent, int], None] | None
    ) = None,
    persisted_event_callback: (
        Callable[[RawMarketEvent, int], None] | None
    ) = None,
    persisted_wire_callback: (
        Callable[[BybitMicrostructureWireEvent, RawMarketEvent, bool], None]
        | None
    ) = None,
    collection_progress_callback: (
        Callable[[MarketTapeWireCollectionResult], None] | None
    ) = None,
) -> MarketTapeWireCollectionResult:
    if orderbook_snapshot_interval_ms <= 0:
        raise ValueError("orderbook snapshot interval must be positive")
    if max_messages is not None and max_messages <= 0:
        raise ValueError("market tape max_messages must be positive when provided")

    observed_messages = 0
    raw_inserted = 0
    raw_unchanged = 0
    orderbooks_inserted = 0
    orderbooks_unchanged = 0
    orderbooks_skipped_by_cadence = 0
    trades_inserted = 0
    trades_unchanged = 0
    last_orderbook_bucket: dict[str, int] = {}

    def result_snapshot() -> MarketTapeWireCollectionResult:
        return MarketTapeWireCollectionResult(
            observed_messages=observed_messages,
            raw_inserted=raw_inserted,
            raw_unchanged=raw_unchanged,
            orderbooks_inserted=orderbooks_inserted,
            orderbooks_unchanged=orderbooks_unchanged,
            orderbooks_skipped_by_cadence=orderbooks_skipped_by_cadence,
            trades_inserted=trades_inserted,
            trades_unchanged=trades_unchanged,
        )

    async for event in events:
        raw_disposition, raw_event = raw_store.append(
            exchange=Exchange.BYBIT,
            channel=event.channel,
            symbol=event.symbol,
            event_kind=event.event_kind,
            source_timestamp_ms=event.source_timestamp_ms,
            event_at_ms=event.event_at_ms,
            ingested_at_ms=event.ingested_at_ms,
            sequence=event.sequence,
            update_id=event.update_id,
            payload=event.raw_payload,
        )
        if raw_disposition is RawMarketTapeWriteDisposition.INSERTED:
            raw_inserted += 1
        else:
            raw_unchanged += 1

        orderbook_normalized_persisted = False
        if event.orderbook is not None:
            bucket = event.event_at_ms // orderbook_snapshot_interval_ms
            previous_bucket = last_orderbook_bucket.get(event.symbol)
            persist_snapshot = (
                event.event_kind == "snapshot"
                or previous_bucket is None
                or bucket > previous_bucket
            )
            if persist_snapshot:
                disposition = store.append_orderbook(event.orderbook)
                orderbook_normalized_persisted = True
                if disposition is MarketTapeWriteDisposition.INSERTED:
                    orderbooks_inserted += 1
                else:
                    orderbooks_unchanged += 1
                last_orderbook_bucket[event.symbol] = max(
                    bucket,
                    previous_bucket if previous_bucket is not None else bucket,
                )
            else:
                orderbooks_skipped_by_cadence += 1

        for trade in event.trades:
            disposition = store.append_trade(trade)
            if disposition is MarketTapeWriteDisposition.INSERTED:
                trades_inserted += 1
            else:
                trades_unchanged += 1

        observed_messages += 1
        if progress_callback is not None:
            progress_callback(event, observed_messages)
        if persisted_event_callback is not None:
            persisted_event_callback(raw_event, observed_messages)
        if persisted_wire_callback is not None:
            persisted_wire_callback(
                event,
                raw_event,
                orderbook_normalized_persisted,
            )
        if collection_progress_callback is not None:
            collection_progress_callback(result_snapshot())
        if max_messages is not None and observed_messages >= max_messages:
            break

    return result_snapshot()
