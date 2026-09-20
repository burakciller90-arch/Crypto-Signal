from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.signals.models import ProbabilityStatus, SignalDirection, SignalState


class ProductDataStatus(StrEnum):
    READY = "ready"
    NO_LEDGER = "no_ledger"
    EMPTY = "empty"
    SCHEMA_UNAVAILABLE = "schema_unavailable"


class SignalEvidenceClassStatus(StrEnum):
    NOT_EXPLICIT_AT_FREEZE_LEVEL = "not_explicit_at_freeze_level"


@dataclass(frozen=True, slots=True)
class FrozenSignalCard:
    bundle_identity: str
    signal_freeze_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    frozen_at_ms: int
    source_cutoff_open_time_ms: int
    state: SignalState
    direction: SignalDirection
    setup_type: str
    confluence_score: Decimal
    confluence_score_semantic: ScoreSemantic
    probability_status: ProbabilityStatus
    uncertainty_flags: tuple[str, ...]
    evidence_class_status: SignalEvidenceClassStatus

    def __post_init__(self) -> None:
        if len(self.bundle_identity) != 64 or len(self.signal_freeze_identity) != 64:
            raise ValueError("frozen signal identities must be SHA256")
        if not self.symbol.strip() or not self.timeframe.strip() or not self.setup_type.strip():
            raise ValueError("frozen signal identity fields must be non-empty")
        if self.as_of_ms < 0 or self.frozen_at_ms < 0 or self.source_cutoff_open_time_ms < 0:
            raise ValueError("frozen signal timestamps must be non-negative")
        if self.frozen_at_ms < self.as_of_ms:
            raise ValueError("frozen_at cannot precede signal as-of")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("uncertainty flags must be unique")


@dataclass(frozen=True, slots=True)
class CommandCenterView:
    status: ProductDataStatus
    freeze_count: int
    latest_frozen_at_ms: int | None
    state_counts: tuple[tuple[SignalState, int], ...]
    direction_counts: tuple[tuple[SignalDirection, int], ...]
    recent_signals: tuple[FrozenSignalCard, ...]


@dataclass(frozen=True, slots=True)
class MarketRadarItem:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    latest: FrozenSignalCard


@dataclass(frozen=True, slots=True)
class MarketRadarView:
    status: ProductDataStatus
    items: tuple[MarketRadarItem, ...]


@dataclass(frozen=True, slots=True)
class AssetCockpitView:
    status: ProductDataStatus
    symbol: str
    timeframe: str
    latest_by_provider: tuple[FrozenSignalCard, ...]
    recent_signals: tuple[FrozenSignalCard, ...]


@dataclass(frozen=True, slots=True)
class SignalArchiveView:
    status: ProductDataStatus
    total_count: int
    offset: int
    limit: int
    signals: tuple[FrozenSignalCard, ...]


@dataclass(frozen=True, slots=True)
class SignalDetailView:
    status: ProductDataStatus
    signal: FrozenSignalCard | None
    bundle_json: str | None


@dataclass(frozen=True, slots=True)
class EvidenceClassCount:
    evidence_class: EvidenceClass
    count: int

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("evidence class count must be non-negative")


@dataclass(frozen=True, slots=True)
class PerformanceAvailabilityView:
    status: ProductDataStatus
    outcome_snapshot_count: int
    evidence_class_counts: tuple[EvidenceClassCount, ...]
