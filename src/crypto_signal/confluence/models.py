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
