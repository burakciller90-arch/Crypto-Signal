from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Exchange, MarketType


class MethodologyKind(StrEnum):
    PRICE_ACTION = "price_action"
    HARMONIC = "harmonic"
    ELLIOTT = "elliott"


class EvidenceDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNRESOLVED = "unresolved"


class EvidenceValidity(StrEnum):
    CONTEXT = "context"
    VALID_SO_FAR = "valid_so_far"
    VALID = "valid"


class InvalidationTrigger(StrEnum):
    TOUCH_OR_CROSS = "touch_or_cross"
    CLOSE_AT_OR_BEYOND = "close_at_or_beyond"


@dataclass(frozen=True, slots=True)
class PriceZone:
    low: Decimal
    high: Decimal

    def __post_init__(self) -> None:
        if self.low <= 0 or self.high <= 0:
            raise ValueError("price zone values must be positive")
        if self.high < self.low:
            raise ValueError("price zone high must be >= low")


@dataclass(frozen=True, slots=True)
class NamedPrice:
    label: str
    price: Decimal

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("named price label must be non-empty")
        if self.price <= 0:
            raise ValueError("named price must be positive")


@dataclass(frozen=True, slots=True)
class EvidenceMetric:
    name: str
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("evidence metric name must be non-empty")
        if not self.unit.strip():
            raise ValueError("evidence metric unit must be non-empty")


@dataclass(frozen=True, slots=True)
class MethodologyEvidence:
    methodology: MethodologyKind
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    evidence_id: str
    setup_type: str
    direction: EvidenceDirection
    validity: EvidenceValidity
    market_available_at_ms: int
    observed_at_ms: int
    entry_zone: PriceZone | None
    invalidation_price: Decimal | None
    invalidation_trigger: InvalidationTrigger | None
    targets: tuple[NamedPrice, ...]
    key_levels: tuple[NamedPrice, ...]
    metrics: tuple[EvidenceMetric, ...]
    ambiguity_flags: tuple[str, ...]
    contradiction_flags: tuple[str, ...]
    evidence_summary: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("evidence symbol must be non-empty")
        if not self.timeframe.strip():
            raise ValueError("evidence timeframe must be non-empty")
        if not self.methodology_version.strip():
            raise ValueError("methodology version must be non-empty")
        if not self.evidence_id.strip():
            raise ValueError("evidence id must be non-empty")
        if not self.setup_type.strip():
            raise ValueError("setup type must be non-empty")
        if self.as_of_ms < 0:
            raise ValueError("as_of_ms must be non-negative")
        if self.market_available_at_ms < 0 or self.observed_at_ms < 0:
            raise ValueError("evidence availability timestamps must be non-negative")
        if self.observed_at_ms < self.market_available_at_ms:
            raise ValueError("evidence cannot be observed before market availability")
        if self.as_of_ms < self.observed_at_ms:
            raise ValueError("evidence cannot be observed after as_of")
        if self.invalidation_price is not None and self.invalidation_price <= 0:
            raise ValueError("invalidation price must be positive")
        if (self.invalidation_price is None) != (self.invalidation_trigger is None):
            raise ValueError(
                "invalidation price and trigger must either both exist or both be absent"
            )
        if len({target.label for target in self.targets}) != len(self.targets):
            raise ValueError("target labels must be unique")
        if len({level.label for level in self.key_levels}) != len(self.key_levels):
            raise ValueError("key-level labels must be unique")
        if len({metric.name for metric in self.metrics}) != len(self.metrics):
            raise ValueError("metric names must be unique")
        if len(set(self.ambiguity_flags)) != len(self.ambiguity_flags):
            raise ValueError("ambiguity flags must be unique")
        if len(set(self.contradiction_flags)) != len(self.contradiction_flags):
            raise ValueError("contradiction flags must be unique")


class PairRelation(StrEnum):
    AGREE = "agree"
    CONTRADICT = "contradict"
    INTERNAL_AMBIGUITY = "internal_ambiguity"
    INSUFFICIENT = "insufficient"


class ScoreSemantic(StrEnum):
    AGREEMENT_INDEX_NOT_PROBABILITY = "agreement_index_not_probability"


@dataclass(frozen=True, slots=True)
class MethodologySelection:
    methodology: MethodologyKind
    source_count: int
    selected: tuple[MethodologyEvidence, ...]
    latest_market_available_at_ms: int | None
    resolved_direction: EvidenceDirection
    has_internal_direction_conflict: bool

    def __post_init__(self) -> None:
        if self.source_count < 0:
            raise ValueError("source_count must be non-negative")
        if self.source_count < len(self.selected):
            raise ValueError("selected count cannot exceed source count")
        if any(item.methodology is not self.methodology for item in self.selected):
            raise ValueError("selection cannot mix methodologies")
        if self.selected:
            latest = max(item.market_available_at_ms for item in self.selected)
            if self.latest_market_available_at_ms != latest:
                raise ValueError("selection latest timestamp does not match selected evidence")
            if any(
                item.market_available_at_ms != latest
                for item in self.selected
            ):
                raise ValueError("all selected evidence must share latest market timestamp")
        elif self.latest_market_available_at_ms is not None:
            raise ValueError("empty selection cannot have latest market timestamp")

        directional = {
            item.direction
            for item in self.selected
            if item.direction
            in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}
        }
        expected_conflict = len(directional) > 1
        if self.has_internal_direction_conflict != expected_conflict:
            raise ValueError("internal-direction conflict flag is inconsistent")
        expected_direction = (
            next(iter(directional))
            if len(directional) == 1
            else EvidenceDirection.UNRESOLVED
        )
        if self.resolved_direction is not expected_direction:
            raise ValueError("resolved direction is inconsistent with selected evidence")


@dataclass(frozen=True, slots=True)
class MethodologyPairRelation:
    left: MethodologyKind
    right: MethodologyKind
    relation: PairRelation
    left_direction: EvidenceDirection
    right_direction: EvidenceDirection

    def __post_init__(self) -> None:
        if self.left is self.right:
            raise ValueError("pair relation requires distinct methodologies")


@dataclass(frozen=True, slots=True)
class ConfluenceScore:
    value: Decimal
    support_method_count: int
    opposing_method_count: int
    resolved_method_count: int
    total_methodology_slots: int
    semantic: ScoreSemantic = ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.value <= Decimal(100):
            raise ValueError("confluence score must be between 0 and 100")
        if self.total_methodology_slots <= 0:
            raise ValueError("total methodology slots must be positive")
        counts = (
            self.support_method_count,
            self.opposing_method_count,
            self.resolved_method_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("confluence score counts must be non-negative")
        if self.resolved_method_count > self.total_methodology_slots:
            raise ValueError("resolved methodology count exceeds total slots")
        if (
            self.support_method_count + self.opposing_method_count
            != self.resolved_method_count
        ):
            raise ValueError("support/opposition counts must equal resolved count")


@dataclass(frozen=True, slots=True)
class ConfluenceAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    selections: tuple[MethodologySelection, ...]
    pairwise_relations: tuple[MethodologyPairRelation, ...]
    dominant_direction: EvidenceDirection
    score: ConfluenceScore
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = set(MethodologyKind)
        actual = {selection.methodology for selection in self.selections}
        if actual != expected or len(self.selections) != len(expected):
            raise ValueError("confluence result must contain exactly one selection per methodology")
        if len(set(self.flags)) != len(self.flags):
            raise ValueError("confluence flags must be unique")
