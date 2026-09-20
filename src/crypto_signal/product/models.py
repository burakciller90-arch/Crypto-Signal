from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.alerts.models import AlertSourceKind, DeliveryAttemptStatus
from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.models import SegmentMetrics
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
class EvidenceKeyLevelView:
    label: str
    price: Decimal


@dataclass(frozen=True, slots=True)
class EvidenceMetricView:
    name: str
    value: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class SelectedEvidenceView:
    evidence_id: str
    methodology: str
    setup_type: str
    direction: str
    validity: str
    market_available_at_ms: int
    observed_at_ms: int
    evidence_summary: tuple[str, ...]
    ambiguity_flags: tuple[str, ...]
    contradiction_flags: tuple[str, ...]
    key_levels: tuple[EvidenceKeyLevelView, ...]
    metrics: tuple[EvidenceMetricView, ...]
    invalidation_price: Decimal | None
    invalidation_trigger: str | None


@dataclass(frozen=True, slots=True)
class MethodologySelectionView:
    methodology: str
    source_count: int
    selected_count: int
    latest_market_available_at_ms: int | None
    resolved_direction: str
    has_internal_direction_conflict: bool
    selected: tuple[SelectedEvidenceView, ...]


@dataclass(frozen=True, slots=True)
class AgreementRelationView:
    left: str
    right: str
    relation: str
    left_direction: str
    right_direction: str


@dataclass(frozen=True, slots=True)
class GeometryTargetView:
    label: str
    target_price: Decimal
    reference_rr: Decimal


@dataclass(frozen=True, slots=True)
class SignalGeometryView:
    source_evidence_id: str
    source_methodology: str
    entry_zone_low: Decimal
    entry_zone_high: Decimal
    entry_reference_price: Decimal
    entry_reference_model: str
    invalidation_price: Decimal
    invalidation_trigger: str
    targets: tuple[GeometryTargetView, ...]


@dataclass(frozen=True, slots=True)
class NavigationContext:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    freeze_count: int
    latest_frozen_at_ms: int


@dataclass(frozen=True, slots=True)
class NavigationView:
    status: ProductDataStatus
    contexts: tuple[NavigationContext, ...]


@dataclass(frozen=True, slots=True)
class PerformanceSegmentGroup:
    evidence_class: EvidenceClass
    max_holding_bars: int
    stored_snapshot_count: int
    selected_latest_signal_count: int
    segments: tuple[SegmentMetrics, ...]

    def __post_init__(self) -> None:
        if self.max_holding_bars <= 0:
            raise ValueError("performance holding horizon must be positive")
        if self.stored_snapshot_count < 0 or self.selected_latest_signal_count < 0:
            raise ValueError("performance snapshot counts must be non-negative")
        if self.selected_latest_signal_count > self.stored_snapshot_count:
            raise ValueError("selected signal count cannot exceed stored snapshots")


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
    methodologies: tuple[MethodologySelectionView, ...] = ()
    pairwise_relations: tuple[AgreementRelationView, ...] = ()
    geometry: SignalGeometryView | None = None
    evidence_summary: tuple[str, ...] = ()
    candle_count: int = 0
    first_candle_open_time_ms: int | None = None
    last_candle_open_time_ms: int | None = None


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
    groups: tuple[PerformanceSegmentGroup, ...] = ()


@dataclass(frozen=True, slots=True)
class AlertSinkDeliveryView:
    sink_id: str
    attempts: int
    latest_status: DeliveryAttemptStatus
    latest_attempted_at_ms: int
    terminal: bool
    delivered: bool
    latest_receipt: str | None

    def __post_init__(self) -> None:
        if not self.sink_id.strip():
            raise ValueError("alert delivery sink id must be non-empty")
        if self.attempts <= 0:
            raise ValueError("alert delivery attempts must be positive")
        if self.latest_attempted_at_ms < 0:
            raise ValueError("alert delivery timestamp must be non-negative")
        if self.delivered and not self.terminal:
            raise ValueError("delivered alert sink state must be terminal")
        if self.delivered and self.latest_status is not DeliveryAttemptStatus.DELIVERED:
            raise ValueError("delivered alert sink state must have DELIVERED status")


@dataclass(frozen=True, slots=True)
class AlertEventView:
    event_identity: str
    source_kind: AlertSourceKind
    signal_freeze_identity: str
    lifecycle_evaluation_identity: str | None
    transition_identity: str | None
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    signal_state: SignalState
    direction: SignalDirection
    setup_type: str
    decision_as_of_ms: int
    source_evaluated_as_of_ms: int
    confluence_score: Decimal
    confluence_score_semantic: ScoreSemantic
    probability_status: ProbabilityStatus
    uncertainty_flags: tuple[str, ...]
    notification_title: str
    notification_body: str
    appended_at_ms: int
    delivery_states: tuple[AlertSinkDeliveryView, ...]

    def __post_init__(self) -> None:
        if len(self.event_identity) != 64:
            raise ValueError("alert event identity must be SHA256")
        if len(self.signal_freeze_identity) != 64:
            raise ValueError("alert source signal identity must be SHA256")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("alert event market identity must be non-empty")
        if not self.notification_title.strip() or not self.notification_body.strip():
            raise ValueError("alert notification preview must be non-empty")
        if self.appended_at_ms < self.source_evaluated_as_of_ms:
            raise ValueError("alert append time cannot precede source evidence")


@dataclass(frozen=True, slots=True)
class AlertCenterView:
    status: ProductDataStatus
    total_count: int
    events: tuple[AlertEventView, ...]

    def __post_init__(self) -> None:
        if self.total_count < 0:
            raise ValueError("alert center total count must be non-negative")
        if self.total_count < len(self.events):
            raise ValueError("alert center page cannot exceed total count")
