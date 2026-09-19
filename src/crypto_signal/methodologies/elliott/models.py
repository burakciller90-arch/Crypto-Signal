from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.primitives.models import ConfirmedPivot


class ElliottDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ElliottRuleStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class ElliottRuleEvidence:
    name: str
    status: ElliottRuleStatus
    description: str


@dataclass(frozen=True, slots=True)
class ElliottProjection:
    name: str
    price: Decimal
    actual_distance_bps: Decimal | None = None
@dataclass(frozen=True, slots=True)
class ImpulseCandidate:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    direction: ElliottDirection
    points: tuple[ConfirmedPivot, ...]
    current_wave: int
    complete: bool
    rules: tuple[ElliottRuleEvidence, ...]
    valid_so_far: bool
    rule_support_fraction: Decimal
    competing_valid_count: int
    structural_invalidation_price: Decimal
    projections: tuple[ElliottProjection, ...]
    truncated_fifth: bool | None
    market_available_at_ms: int
    observed_at_ms: int

    def __post_init__(self) -> None:
        if not 1 <= self.current_wave <= 5:
            raise ValueError("current_wave must be between 1 and 5")
        if len(self.points) != self.current_wave + 1:
            raise ValueError("impulse point count must equal current_wave + 1")
        if self.complete != (self.current_wave == 5):
            raise ValueError("complete flag must match Wave 5 completion")
        if not Decimal(0) <= self.rule_support_fraction <= Decimal(1):
            raise ValueError("rule support must lie between zero and one")
        if self.structural_invalidation_price <= 0:
            raise ValueError("structural invalidation price must be positive")
        if self.competing_valid_count < 0:
            raise ValueError("competing count cannot be negative")
    @property
    def start(self) -> ConfirmedPivot:
        return self.points[0]

    @property
    def end(self) -> ConfirmedPivot:
        return self.points[-1]


@dataclass(frozen=True, slots=True)
class ABCCandidate:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    direction: ElliottDirection
    start: ConfirmedPivot
    a: ConfirmedPivot
    b: ConfirmedPivot
    c: ConfirmedPivot
    zigzag_rules: tuple[ElliottRuleEvidence, ...]
    zigzag_compatible: bool
    rule_support_fraction: Decimal
    c_equality_projection: ElliottProjection
    market_available_at_ms: int
    observed_at_ms: int


@dataclass(frozen=True, slots=True)
class ElliottAmbiguity:
    end_candle_index: int
    valid_impulse_count: int
    candidate_count: int


@dataclass(frozen=True, slots=True)
class ElliottAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    impulse_candidates: tuple[ImpulseCandidate, ...]
    abc_candidates: tuple[ABCCandidate, ...]
    ambiguity: tuple[ElliottAmbiguity, ...]
    ambiguous_swing_source_indices: tuple[int, ...]
