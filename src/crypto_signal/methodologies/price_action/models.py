from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.periodic_opens import PeriodicOpen
from crypto_signal.primitives.models import ConfirmedPivot


class StructureDirection(StrEnum):
    UNKNOWN = "unknown"
    BULLISH = "bullish"
    BEARISH = "bearish"


class StructureBreakKind(StrEnum):
    BOS = "bos"
    CHOCH_MSB = "choch_msb"


class SwingRelation(StrEnum):
    UNCLASSIFIED = "unclassified"
    HIGHER_HIGH = "higher_high"
    LOWER_HIGH = "lower_high"
    EQUAL_HIGH = "equal_high"
    HIGHER_LOW = "higher_low"
    LOWER_LOW = "lower_low"
    EQUAL_LOW = "equal_low"


@dataclass(frozen=True, slots=True)
class LabeledSwing:
    pivot: ConfirmedPivot
    relation: SwingRelation


@dataclass(frozen=True, slots=True)
class StructureBreak:
    kind: StructureBreakKind
    direction: StructureDirection
    broken_pivot: ConfirmedPivot
    break_candle_identity: tuple[str, str, str, str, int]
    break_close: Decimal
    level_price: Decimal
    distance_bps: Decimal
    market_confirmed_at_ms: int
    observed_at_ms: int


@dataclass(frozen=True, slots=True)
class PriceActionStructureResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    confirmed_pivots: tuple[ConfirmedPivot, ...]
    labeled_swings: tuple[LabeledSwing, ...]
    structure_breaks: tuple[StructureBreak, ...]
    current_direction: StructureDirection
    periodic_opens: tuple[PeriodicOpen, ...]
    ambiguous_swing_source_indices: tuple[int, ...]
