from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from crypto_signal.data.models import Candle


@dataclass(frozen=True, slots=True)
class CandleSourceSnapshot:
    provider: str
    source: str
    channel: str
    symbol: str
    timeframe: str
    raw_payload: dict[str, object]
    candles: tuple[Candle, ...]
    source_timestamp_ms: int
    observed_at_ms: int

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.provider,
                self.source,
                self.channel,
                self.symbol,
                self.timeframe,
            )
        ):
            raise ValueError(
                "candle source snapshot context must be non-empty"
            )
        if self.symbol != self.symbol.upper():
            raise ValueError("candle source snapshot symbol must be uppercase")
        if min(self.source_timestamp_ms, self.observed_at_ms) < 0:
            raise ValueError(
                "candle source snapshot timestamps cannot be negative"
            )
        for candle in self.candles:
            if candle.symbol != self.symbol:
                raise ValueError("candle source snapshot symbol mismatch")
            if candle.timeframe != self.timeframe:
                raise ValueError("candle source snapshot timeframe mismatch")




class MarketDataAdapter(Protocol):
    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> Sequence[Candle]: ...


class SourceAwareMarketDataAdapter(MarketDataAdapter, Protocol):
    async def fetch_source_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> CandleSourceSnapshot: ...
