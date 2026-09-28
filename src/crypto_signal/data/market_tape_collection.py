from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Protocol

from crypto_signal.data.adapters.bybit_derivatives import (
    BybitLinearDerivativesSourceSnapshot,
)
from crypto_signal.data.adapters.bybit_microstructure import (
    BybitSpotMicrostructureSourceSnapshot,
)
from crypto_signal.data.derivatives import DerivativesObservation
from crypto_signal.data.liquidations import (
    LiquidationFeedCoverage,
    LiquidationObservation,
)
from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.market_tape_rest_source_contract import (
    BybitRestMarketTapeCapabilities,
    BybitRestMarketTapeWriteResult,
    persist_bybit_rest_market_tape_snapshot,
)
from crypto_signal.data.microstructure import (
    OrderBookSnapshot,
    PublicTradeObservation,
)
from crypto_signal.data.source_contract import SourceContractStore


class MicrostructureSnapshotAdapter(Protocol):
    async def fetch_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ) -> tuple[OrderBookSnapshot, tuple[PublicTradeObservation, ...]]: ...


class MicrostructureSourceSnapshotAdapter(Protocol):
    async def fetch_source_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ) -> BybitSpotMicrostructureSourceSnapshot: ...


class DerivativesSourceSnapshotAdapter(Protocol):
    async def fetch_source_snapshot(
        self,
        *,
        symbol: str,
        oi_interval: str = "15min",
        oi_limit: int = 8,
        end_ms: int | None = None,
    ) -> BybitLinearDerivativesSourceSnapshot: ...


class DerivativesSnapshotAdapter(Protocol):
    async def fetch_observations(
        self,
        *,
        symbol: str,
        oi_interval: str = "15min",
        oi_limit: int = 8,
        end_ms: int | None = None,
    ) -> tuple[DerivativesObservation, ...]: ...


@dataclass(frozen=True, slots=True)
class MarketTapeCollectionResult:
    symbol: str
    orderbook_disposition: MarketTapeWriteDisposition
    trade_inserted: int
    trade_unchanged: int
    derivatives_inserted: int
    derivatives_unchanged: int

    @property
    def inserted_total(self) -> int:
        return (
            (1 if self.orderbook_disposition is MarketTapeWriteDisposition.INSERTED else 0)
            + self.trade_inserted
            + self.derivatives_inserted
        )


async def collect_bybit_market_tape_snapshot(
    *,
    store: MarketTapeStore,
    microstructure_adapter: MicrostructureSnapshotAdapter,
    derivatives_adapter: DerivativesSnapshotAdapter,
    symbol: str,
    book_depth: int = 25,
    trade_limit: int = 60,
    oi_interval: str = "15min",
    oi_limit: int = 16,
) -> MarketTapeCollectionResult:
    if not symbol or symbol != symbol.upper():
        raise ValueError("market tape symbol must be non-empty uppercase")

    book, trades = await microstructure_adapter.fetch_snapshot(
        symbol=symbol,
        book_depth=book_depth,
        trade_limit=trade_limit,
    )
    derivatives = await derivatives_adapter.fetch_observations(
        symbol=symbol,
        oi_interval=oi_interval,
        oi_limit=oi_limit,
    )

    book_result = store.append_orderbook(book)
    trade_results = tuple(store.append_trade(item) for item in trades)
    derivative_results = tuple(
        store.append_derivatives(item) for item in derivatives
    )

    return MarketTapeCollectionResult(
        symbol=symbol,
        orderbook_disposition=book_result,
        trade_inserted=sum(
            item is MarketTapeWriteDisposition.INSERTED
            for item in trade_results
        ),
        trade_unchanged=sum(
            item is MarketTapeWriteDisposition.UNCHANGED
            for item in trade_results
        ),
        derivatives_inserted=sum(
            item is MarketTapeWriteDisposition.INSERTED
            for item in derivative_results
        ),
        derivatives_unchanged=sum(
            item is MarketTapeWriteDisposition.UNCHANGED
            for item in derivative_results
        ),
    )


async def collect_bybit_market_tape_snapshot_with_source_contract(
    *,
    store: MarketTapeStore,
    source_store: SourceContractStore,
    source_capabilities: BybitRestMarketTapeCapabilities,
    microstructure_adapter: MicrostructureSourceSnapshotAdapter,
    derivatives_adapter: DerivativesSourceSnapshotAdapter,
    symbol: str,
    book_depth: int = 25,
    trade_limit: int = 60,
    oi_interval: str = "15min",
    oi_limit: int = 16,
) -> BybitRestMarketTapeWriteResult:
    if not symbol or symbol != symbol.upper():
        raise ValueError("market tape symbol must be non-empty uppercase")

    microstructure = await microstructure_adapter.fetch_source_snapshot(
        symbol=symbol,
        book_depth=book_depth,
        trade_limit=trade_limit,
    )
    derivatives = await derivatives_adapter.fetch_source_snapshot(
        symbol=symbol,
        oi_interval=oi_interval,
        oi_limit=oi_limit,
    )
    return persist_bybit_rest_market_tape_snapshot(
        market_store=store,
        source_store=source_store,
        capabilities=source_capabilities,
        microstructure=microstructure,
        derivatives=derivatives,
        symbol=symbol,
    )


@dataclass(frozen=True, slots=True)
class MarketTapeLiquidationCollectionResult:
    observed_events: int
    liquidation_inserted: int
    liquidation_unchanged: int
    coverage_disposition: MarketTapeWriteDisposition

    @property
    def inserted_total(self) -> int:
        return (
            self.liquidation_inserted
            + (
                1
                if self.coverage_disposition
                is MarketTapeWriteDisposition.INSERTED
                else 0
            )
        )


def persist_liquidation_batch(
    *,
    store: MarketTapeStore,
    events: tuple[LiquidationObservation, ...],
    coverage: LiquidationFeedCoverage,
) -> MarketTapeLiquidationCollectionResult:
    ordered = tuple(
        sorted(
            events,
            key=lambda item: (
                item.event_at_ms,
                item.source_timestamp_ms,
                item.source_row_index,
                item.liquidation_identity,
            ),
        )
    )
    for event in ordered:
        if (
            event.exchange is not coverage.exchange
            or event.instrument_type is not coverage.instrument_type
            or event.symbol != coverage.symbol
        ):
            raise ValueError("liquidation batch context mismatch")
        if not (
            coverage.coverage_start_ms
            <= event.event_at_ms
            <= coverage.coverage_end_ms
        ):
            raise ValueError("liquidation event falls outside coverage window")
        if max(
            event.event_at_ms,
            event.source_timestamp_ms,
            event.ingested_at_ms,
        ) > coverage.observed_at_ms:
            raise ValueError(
                "liquidation event is not observable by coverage timestamp"
            )

    dispositions = tuple(
        store.append_liquidation(event)
        for event in ordered
    )
    coverage_disposition = store.append_liquidation_coverage(coverage)
    return MarketTapeLiquidationCollectionResult(
        observed_events=len(ordered),
        liquidation_inserted=sum(
            item is MarketTapeWriteDisposition.INSERTED
            for item in dispositions
        ),
        liquidation_unchanged=sum(
            item is MarketTapeWriteDisposition.UNCHANGED
            for item in dispositions
        ),
        coverage_disposition=coverage_disposition,
    )


@dataclass(frozen=True, slots=True)
class MarketTapeStreamCollectionResult:
    observed_events: int
    orderbooks_inserted: int
    orderbooks_unchanged: int
    trades_inserted: int
    trades_unchanged: int

    @property
    def inserted_total(self) -> int:
        return self.orderbooks_inserted + self.trades_inserted


async def persist_market_tape_stream(
    *,
    store: MarketTapeStore,
    events: AsyncIterable[OrderBookSnapshot | PublicTradeObservation],
    max_events: int | None = None,
) -> MarketTapeStreamCollectionResult:
    if max_events is not None and max_events <= 0:
        raise ValueError("market tape max_events must be positive when provided")

    observed_events = 0
    orderbooks_inserted = 0
    orderbooks_unchanged = 0
    trades_inserted = 0
    trades_unchanged = 0

    async for event in events:
        if isinstance(event, OrderBookSnapshot):
            disposition = store.append_orderbook(event)
            if disposition is MarketTapeWriteDisposition.INSERTED:
                orderbooks_inserted += 1
            else:
                orderbooks_unchanged += 1
        elif isinstance(event, PublicTradeObservation):
            disposition = store.append_trade(event)
            if disposition is MarketTapeWriteDisposition.INSERTED:
                trades_inserted += 1
            else:
                trades_unchanged += 1
        else:
            raise TypeError("unsupported Market Tape stream event")

        observed_events += 1
        if max_events is not None and observed_events >= max_events:
            break

    return MarketTapeStreamCollectionResult(
        observed_events=observed_events,
        orderbooks_inserted=orderbooks_inserted,
        orderbooks_unchanged=orderbooks_unchanged,
        trades_inserted=trades_inserted,
        trades_unchanged=trades_unchanged,
    )
