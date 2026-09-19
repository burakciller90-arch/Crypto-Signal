from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.primitives.models import ConfirmedPivot


class HarmonicPatternKind(StrEnum):
    GARTLEY = "gartley"
    BAT = "bat"
    BUTTERFLY = "butterfly"
    CRAB = "crab"
    DEEP_CRAB = "deep_crab"


class HarmonicDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ConstraintKind(StrEnum):
    TARGET = "target"
    RANGE = "range"
    MINIMUM = "minimum"


@dataclass(frozen=True, slots=True)
class RatioConstraint:
    name: str
    kind: ConstraintKind
    minimum: Decimal
    maximum: Decimal
    target: Decimal | None = None
    relative_tolerance: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ratio constraint name must be non-empty")
        if self.minimum <= 0 or self.maximum < self.minimum:
            raise ValueError("ratio constraint bounds are invalid")
        if self.kind is ConstraintKind.TARGET:
            if self.target is None or self.relative_tolerance is None:
                raise ValueError("target constraint requires target and tolerance")
            if not self.minimum <= self.target <= self.maximum:
                raise ValueError("target must lie inside constraint bounds")
            if self.relative_tolerance < 0:
                raise ValueError("target tolerance must be non-negative")
        elif self.target is not None or self.relative_tolerance is not None:
            raise ValueError("non-target constraint cannot carry target tolerance")


@dataclass(frozen=True, slots=True)
class PatternSpec:
    kind: HarmonicPatternKind
    b_xa: RatioConstraint
    c_ab: RatioConstraint
    d_bc: RatioConstraint
    d_xa: RatioConstraint
    cd_ab: RatioConstraint
    cd_ab_projection_anchors: tuple[Decimal, ...]
    invalidation_xa_ratio: Decimal
    def __post_init__(self) -> None:
        if self.invalidation_xa_ratio <= 0:
            raise ValueError("invalidation ratio must be positive")
        if not self.cd_ab_projection_anchors:
            raise ValueError("CD/AB projection anchors must be non-empty")
        if any(anchor <= 0 for anchor in self.cd_ab_projection_anchors):
            raise ValueError("CD/AB projection anchors must be positive")


@dataclass(frozen=True, slots=True)
class XABCDCandidate:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    direction: HarmonicDirection
    x: ConfirmedPivot
    a: ConfirmedPivot
    b: ConfirmedPivot
    c: ConfirmedPivot
    d: ConfirmedPivot
    market_available_at_ms: int
    observed_at_ms: int

    def __post_init__(self) -> None:
        indices = [
            self.x.candle_index,
            self.a.candle_index,
            self.b.candle_index,
            self.c.candle_index,
            self.d.candle_index,
        ]
        if indices != sorted(indices) or len(set(indices)) != 5:
            raise ValueError("XABCD pivots must be strictly chronological")
        if self.market_available_at_ms != self.d.market_confirmed_at_ms:
            raise ValueError("candidate market availability must equal D confirmation")
        if self.observed_at_ms != self.d.observed_at_ms:
            raise ValueError("candidate observation must equal D observation")
    @property
    def pivots(self) -> tuple[ConfirmedPivot, ...]:
        return (self.x, self.a, self.b, self.c, self.d)

    @property
    def identity(self) -> tuple[str, str, str, str, int, int, int, int, int]:
        return (
            self.exchange.value,
            self.market_type.value,
            self.symbol,
            self.timeframe,
            self.x.open_time_ms,
            self.a.open_time_ms,
            self.b.open_time_ms,
            self.c.open_time_ms,
            self.d.open_time_ms,
        )


@dataclass(frozen=True, slots=True)
class HarmonicRatios:
    b_xa: Decimal
    c_ab: Decimal
    d_bc: Decimal
    d_xa: Decimal
    cd_ab: Decimal


@dataclass(frozen=True, slots=True)
class RatioEvidence:
    name: str
    actual: Decimal
    valid: bool
    residual: Decimal
    minimum: Decimal
    maximum: Decimal
    target: Decimal | None
@dataclass(frozen=True, slots=True)
class PRZProjection:
    source: str
    ratio: Decimal
    price: Decimal
    actual_d_distance_bps: Decimal
    physical: bool


@dataclass(frozen=True, slots=True)
class HarmonicMatch:
    pattern: HarmonicPatternKind
    candidate: XABCDCandidate
    ratios: HarmonicRatios
    ratio_evidence: tuple[RatioEvidence, ...]
    geometry_valid: bool
    valid: bool
    mean_ratio_residual: Decimal
    max_ratio_residual: Decimal
    prz_low: Decimal
    prz_high: Decimal
    prz_width_bps: Decimal
    projections: tuple[PRZProjection, ...]
    fib_clustering_width_bps: Decimal
    ab_cd_time_symmetry_error: Decimal
    invalidation_price: Decimal
    target_1_price: Decimal
    target_2_price: Decimal


@dataclass(frozen=True, slots=True)
class HarmonicAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    left_bars: int
    right_bars: int
    candidates: tuple[XABCDCandidate, ...]
    matches: tuple[HarmonicMatch, ...]
    valid_matches: tuple[HarmonicMatch, ...]
    degenerate_candidate_count: int
    ambiguous_swing_source_indices: tuple[int, ...]
