from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    MethodologyPairRelation,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType


class SignalState(StrEnum):
    NO_SIGNAL = "no_signal"
    NEUTRAL = "neutral"
    WATCH = "watch"
    ACTIVE = "active"
    INVALIDATED = "invalidated"


class SignalDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class ProbabilityStatus(StrEnum):
    NOT_CALIBRATED = "not_calibrated"


class HistoricalStatsStatus(StrEnum):
    NOT_EVALUATED = "not_evaluated"


class EntryReferenceModel(StrEnum):
    ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION = (
        "zone_midpoint_reference_not_execution"
    )


@dataclass(frozen=True, slots=True)
class RiskRewardTarget:
    label: str
    target_price: Decimal
    reference_rr: Decimal

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("risk/reward target label must be non-empty")
        if self.target_price <= 0:
            raise ValueError("risk/reward target price must be positive")
        if self.reference_rr <= 0:
            raise ValueError("reference R/R must be positive")


@dataclass(frozen=True, slots=True)
class SignalGeometry:
    source_evidence_id: str
    source_methodology: MethodologyKind
    entry_zone: PriceZone
    entry_reference_price: Decimal
    entry_reference_model: EntryReferenceModel
    invalidation_price: Decimal
    invalidation_trigger: InvalidationTrigger
    targets: tuple[RiskRewardTarget, ...]

    def __post_init__(self) -> None:
        if not self.source_evidence_id.strip():
            raise ValueError("geometry source evidence id must be non-empty")
        if not (
            self.entry_zone.low
            <= self.entry_reference_price
            <= self.entry_zone.high
        ):
            raise ValueError("entry reference must lie inside entry zone")
        if self.invalidation_price <= 0:
            raise ValueError("geometry invalidation price must be positive")
        if not self.targets:
            raise ValueError("signal geometry requires at least one target")
        if len({target.label for target in self.targets}) != len(self.targets):
            raise ValueError("signal target labels must be unique")


@dataclass(frozen=True, slots=True)
class MethodologyVersionRef:
    methodology: MethodologyKind
    version: str

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("methodology version must be non-empty")


@dataclass(frozen=True, slots=True)
class SignalAgreementSummary:
    confluence_score: Decimal
    score_semantic: ScoreSemantic
    support_method_count: int
    opposing_method_count: int
    resolved_method_count: int
    total_methodology_slots: int
    pairwise_relations: tuple[MethodologyPairRelation, ...]

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.confluence_score <= Decimal(100):
            raise ValueError("signal confluence score must be between 0 and 100")
        if self.total_methodology_slots <= 0:
            raise ValueError("signal methodology slot count must be positive")
        if (
            self.support_method_count < 0
            or self.opposing_method_count < 0
            or self.resolved_method_count < 0
        ):
            raise ValueError("signal agreement counts must be non-negative")
        if (
            self.support_method_count + self.opposing_method_count
            != self.resolved_method_count
        ):
            raise ValueError("signal agreement counts are inconsistent")


@dataclass(frozen=True, slots=True)
class SignalDecision:
    freeze_identity: str
    signal_version: str
    state: SignalState
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    direction: SignalDirection
    setup_type: str
    geometry: SignalGeometry | None
    agreement: SignalAgreementSummary
    selected_evidence_ids: tuple[str, ...]
    methodology_versions: tuple[MethodologyVersionRef, ...]
    probability_status: ProbabilityStatus
    historical_stats_status: HistoricalStatsStatus
    uncertainty_flags: tuple[str, ...]
    evidence_summary: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.freeze_identity) != 64:
            raise ValueError("freeze identity must be a SHA256 hex digest")
        try:
            int(self.freeze_identity, 16)
        except ValueError as exc:
            raise ValueError("freeze identity must be hexadecimal") from exc
        if not self.signal_version.strip():
            raise ValueError("signal version must be non-empty")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("signal market identity must be non-empty")
        if self.as_of_ms < 0:
            raise ValueError("signal as_of_ms must be non-negative")
        if not self.setup_type.strip():
            raise ValueError("signal setup_type must be non-empty")
        if self.state is SignalState.INVALIDATED:
            raise ValueError(
                "initial SignalDecision cannot be created as INVALIDATED"
            )
        if self.state in {SignalState.NO_SIGNAL, SignalState.NEUTRAL}:
            if self.direction is not SignalDirection.NONE:
                raise ValueError(
                    "NO_SIGNAL/NEUTRAL decisions must have NONE direction"
                )
            if self.geometry is not None:
                raise ValueError(
                    "NO_SIGNAL/NEUTRAL decisions cannot choose geometry"
                )
        else:
            if self.direction is SignalDirection.NONE:
                raise ValueError("WATCH/ACTIVE decisions require direction")
        if self.state is SignalState.ACTIVE and self.geometry is None:
            raise ValueError("ACTIVE signal requires geometry")
        if len(set(self.selected_evidence_ids)) != len(
            self.selected_evidence_ids
        ):
            raise ValueError("selected evidence ids must be unique")
        methods = [item.methodology for item in self.methodology_versions]
        if len(set(methods)) != len(methods):
            raise ValueError("methodology versions must be unique by methodology")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("signal uncertainty flags must be unique")
