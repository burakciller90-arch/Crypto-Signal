from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.microstructure import PublicTradeObservation


class PublicTradeStreamAdapter(Protocol):
    def stream_trades(
        self,
        *,
        symbol: str,
    ) -> AsyncIterator[PublicTradeObservation]: ...


@dataclass(frozen=True, slots=True)
class MarketTapeTradeStreamResult:
    symbol: str
    seen: int
    inserted: int
    unchanged: int

    @property
    def writes(self) -> int:
        return self.inserted


async def capture_public_trade_stream(
    *,
    store: MarketTapeStore,
    adapter: PublicTradeStreamAdapter,
    symbol: str,
    max_trades: int | None = None,
) -> MarketTapeTradeStreamResult:
    if not symbol or symbol != symbol.upper():
        raise ValueError("market tape symbol must be non-empty uppercase")
    if max_trades is not None and max_trades <= 0:
        raise ValueError("max_trades must be positive when provided")

    seen = 0
    inserted = 0
    unchanged = 0

    async for trade in adapter.stream_trades(symbol=symbol):
        if trade.symbol != symbol:
            raise ValueError("public-trade stream yielded unexpected symbol")

        disposition = store.append_trade(trade)
        seen += 1
        if disposition is MarketTapeWriteDisposition.INSERTED:
            inserted += 1
        else:
            unchanged += 1

        if max_trades is not None and seen >= max_trades:
            break

    return MarketTapeTradeStreamResult(
        symbol=symbol,
        seen=seen,
        inserted=inserted,
        unchanged=unchanged,
    )
