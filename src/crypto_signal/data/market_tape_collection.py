from __future__ import annotations

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
