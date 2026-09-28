from __future__ import annotations

from collections.abc import AsyncIterable, Callable
from dataclasses import dataclass

from crypto_signal.data.adapters.bybit_liquidation_ws import (
    BybitLiquidationWireBatch,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collection import (
    MarketTapeLiquidationCollectionResult,
    persist_liquidation_batch,
)
from crypto_signal.data.models import Exchange
from crypto_signal.data.raw_market_tape import (
    RawMarketTapeStore,
    RawMarketTapeWriteDisposition,
)


@dataclass(frozen=True, slots=True)
class LiquidationWireCollectionResult:
    observed_messages: int
    raw_inserted: int
    raw_unchanged: int
    liquidation_inserted: int
    liquidation_unchanged: int
    coverage_inserted: int
    coverage_unchanged: int

    @property
    def normalized_inserted_total(self) -> int:
        return self.liquidation_inserted + self.coverage_inserted


async def persist_bybit_liquidation_wire_stream(
    *,
    store: MarketTapeStore,
    raw_store: RawMarketTapeStore,
    batches: AsyncIterable[BybitLiquidationWireBatch],
    max_messages: int | None = None,
    collection_progress_callback: (
        Callable[
            [
                BybitLiquidationWireBatch,
                LiquidationWireCollectionResult,
            ],
            None,
        ]
        | None
    ) = None,
) -> LiquidationWireCollectionResult:
    if max_messages is not None and max_messages <= 0:
        raise ValueError(
            "liquidation collector max_messages must be positive when provided"
        )

    observed_messages = 0
    raw_inserted = 0
    raw_unchanged = 0
    liquidation_inserted = 0
    liquidation_unchanged = 0
    coverage_inserted = 0
    coverage_unchanged = 0

    async for batch in batches:
        raw_disposition, _ = raw_store.append(
            exchange=Exchange.BYBIT,
            channel="allLiquidation",
            symbol=batch.symbol,
            event_kind="liquidation_batch",
            source_timestamp_ms=batch.source_timestamp_ms,
            event_at_ms=batch.event_at_ms,
            ingested_at_ms=batch.ingested_at_ms,
            sequence=0,
            update_id=0,
            payload=batch.raw_payload,
        )
        if raw_disposition is RawMarketTapeWriteDisposition.INSERTED:
            raw_inserted += 1
        else:
            raw_unchanged += 1

        normalized: MarketTapeLiquidationCollectionResult = (
            persist_liquidation_batch(
                store=store,
                events=batch.events,
                coverage=batch.coverage,
            )
        )
        liquidation_inserted += normalized.liquidation_inserted
        liquidation_unchanged += normalized.liquidation_unchanged
        if normalized.coverage_disposition.value == "inserted":
            coverage_inserted += 1
        else:
            coverage_unchanged += 1

        observed_messages += 1
        progress = LiquidationWireCollectionResult(
            observed_messages=observed_messages,
            raw_inserted=raw_inserted,
            raw_unchanged=raw_unchanged,
            liquidation_inserted=liquidation_inserted,
            liquidation_unchanged=liquidation_unchanged,
            coverage_inserted=coverage_inserted,
            coverage_unchanged=coverage_unchanged,
        )
        if collection_progress_callback is not None:
            collection_progress_callback(batch, progress)
        if max_messages is not None and observed_messages >= max_messages:
            break

    return LiquidationWireCollectionResult(
        observed_messages=observed_messages,
        raw_inserted=raw_inserted,
        raw_unchanged=raw_unchanged,
        liquidation_inserted=liquidation_inserted,
        liquidation_unchanged=liquidation_unchanged,
        coverage_inserted=coverage_inserted,
        coverage_unchanged=coverage_unchanged,
    )
