from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Protocol

from crypto_signal.data.derivatives import DerivativesObservation
from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.microstructure import (
    OrderBookSnapshot,
    PublicTradeObservation,
)


class MicrostructureSnapshotAdapter(Protocol):
    async def fetch_snapshot(
        self,
        *,
        symbol: str,
        book_depth: int = 25,
        trade_limit: int = 60,
    ) -> tuple[OrderBookSnapshot, tuple[PublicTradeObservation, ...]]: ...


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
