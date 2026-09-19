from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType


class PivotKind(StrEnum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ConfirmedPivot:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    kind: PivotKind
    candle_index: int
    open_time_ms: int
    price: Decimal
    left_bars: int
    right_bars: int
    market_confirmed_at_ms: int
    observed_at_ms: int
    source_candle_identity: tuple[str, str, str, str, int]
    confirmation_candle_identity: tuple[str, str, str, str, int]
    same_bar_ambiguity: bool = False

    def __post_init__(self) -> None:
        if self.candle_index < 0:
            raise ValueError("candle_index must be non-negative")
        if self.left_bars < 1 or self.right_bars < 1:
            raise ValueError("pivot confirmation windows must be positive")
        if self.price <= 0:
            raise ValueError("pivot price must be positive")
        if self.market_confirmed_at_ms < self.open_time_ms:
            raise ValueError("pivot cannot confirm before its source candle")
        if self.observed_at_ms < self.market_confirmed_at_ms:
            raise ValueError("pivot cannot be observed before market confirmation")


@dataclass(frozen=True, slots=True)
class AlternatingSwingResult:
    swings: tuple[ConfirmedPivot, ...]
    ambiguous_source_indices: tuple[int, ...]
