from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.calibration import ProbabilitySemantic
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import SignalDirection, SignalState


class ForecastTriggerKind(StrEnum):
    GEOMETRY_ENTRY_ZONE = "geometry_entry_zone"


class DecisionProofAuthority(StrEnum):
    RESEARCH = "research"
    SHADOW = "shadow"
    CANONICAL_PAPER = "canonical_paper"


@dataclass(frozen=True, slots=True)
class ConditionalForecast:
    forecast_identity: str
    forecast_version: str
    signal_freeze_identity: str
    bundle_identity: str
    issued_at_ms: int
    signal_as_of_ms: int
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    signal_state: SignalState
    direction: SignalDirection
    setup_type: str
    trigger_kind: ForecastTriggerKind
    trigger_zone: PriceZone
    target_label: str
    target_price: Decimal
    invalidation_price: Decimal
    invalidation_trigger: InvalidationTrigger
    horizon_bars: int
    confluence_score: Decimal
    confluence_semantic: ScoreSemantic
    calibrated_probability: Decimal | None
    probability_semantic: ProbabilitySemantic | None
    probability_model_version: str | None
    probability_train_n: int | None
    probability_holdout_n: int | None
    probability_brier_score: Decimal | None
    probability_brier_skill_score: Decimal | None
    probability_expected_calibration_error: Decimal | None
    probability_trained_through_as_of_ms: int | None
    probability_evaluated_through_as_of_ms: int | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.forecast_identity, "forecast identity")
        _require_sha256(self.signal_freeze_identity, "signal freeze identity")
        _require_sha256(self.bundle_identity, "bundle identity")
        if not self.forecast_version.strip():
            raise ValueError("forecast version must be non-empty")
        if self.issued_at_ms < self.signal_as_of_ms:
            raise ValueError("forecast cannot be issued before signal as-of")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("forecast market identity must be non-empty")
        if self.signal_state not in {SignalState.WATCH, SignalState.ACTIVE}:
            raise ValueError("forecast requires WATCH or ACTIVE signal")
        if self.direction is SignalDirection.NONE:
            raise ValueError("forecast requires directional signal")
        if not self.setup_type.strip() or not self.target_label.strip():
            raise ValueError("forecast setup/target label must be non-empty")
        if self.target_price <= 0 or self.invalidation_price <= 0:
            raise ValueError("forecast target/invalidation must be positive")
        if self.horizon_bars <= 0:
            raise ValueError("forecast horizon must be positive")
        if not Decimal(0) <= self.confluence_score <= Decimal(100):
            raise ValueError("forecast confluence score must be between 0 and 100")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("forecast uncertainty flags must be unique")

        probability_fields = (
            self.probability_semantic,
            self.probability_model_version,
            self.probability_train_n,
            self.probability_holdout_n,
            self.probability_brier_score,
            self.probability_brier_skill_score,
            self.probability_expected_calibration_error,
            self.probability_trained_through_as_of_ms,
            self.probability_evaluated_through_as_of_ms,
        )
        if self.calibrated_probability is None:
            if any(value is not None for value in probability_fields):
                raise ValueError("uncalibrated forecast cannot carry probability metadata")
        else:
            if self.signal_state is not SignalState.ACTIVE:
                raise ValueError("calibrated probability requires ACTIVE signal")
            if not Decimal(0) <= self.calibrated_probability <= Decimal(1):
                raise ValueError("forecast probability must be between 0 and 1")
            if any(value is None for value in probability_fields):
                raise ValueError("calibrated forecast requires complete probability metadata")
            if self.probability_train_n is not None and self.probability_train_n <= 0:
                raise ValueError("probability train sample must be positive")
            if self.probability_holdout_n is not None and self.probability_holdout_n <= 0:
                raise ValueError("probability holdout sample must be positive")


@dataclass(frozen=True, slots=True)
class DecisionProof:
    proof_identity: str
    proof_version: str
    forecast_identity: str
    signal_freeze_identity: str
    bundle_identity: str
    created_at_ms: int
    authority: DecisionProofAuthority
    supporting_evidence_ids: tuple[str, ...]
    opposing_evidence_ids: tuple[str, ...]
    ambiguous_evidence_ids: tuple[str, ...]
    contradiction_flags: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]
    simple_explanation_tr: str
    technical_explanation: str
    snapshot_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.proof_identity, "proof identity"),
            (self.forecast_identity, "forecast identity"),
            (self.signal_freeze_identity, "signal freeze identity"),
            (self.bundle_identity, "bundle identity"),
        ):
            _require_sha256(value, label)
        if not self.proof_version.strip():
            raise ValueError("proof version must be non-empty")
        if self.created_at_ms < 0:
            raise ValueError("proof timestamp must be non-negative")
        for values, label in (
            (self.supporting_evidence_ids, "supporting evidence ids"),
            (self.opposing_evidence_ids, "opposing evidence ids"),
            (self.ambiguous_evidence_ids, "ambiguous evidence ids"),
            (self.contradiction_flags, "contradiction flags"),
            (self.uncertainty_flags, "uncertainty flags"),
            (self.snapshot_refs, "snapshot refs"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        evidence_sets = (
            set(self.supporting_evidence_ids),
            set(self.opposing_evidence_ids),
            set(self.ambiguous_evidence_ids),
        )
        if evidence_sets[0] & evidence_sets[1]:
            raise ValueError("supporting/opposing evidence cannot overlap")
        if evidence_sets[0] & evidence_sets[2]:
            raise ValueError("supporting/ambiguous evidence cannot overlap")
        if evidence_sets[1] & evidence_sets[2]:
            raise ValueError("opposing/ambiguous evidence cannot overlap")
        if not self.simple_explanation_tr.strip():
            raise ValueError("simple explanation must be non-empty")
        if not self.technical_explanation.strip():
            raise ValueError("technical explanation must be non-empty")


@dataclass(frozen=True, slots=True)
class ForecastResolution:
    resolution_identity: str
    resolution_version: str
    forecast_identity: str
    signal_freeze_identity: str
    outcome_identity: str
    evidence_class: EvidenceClass
    evaluated_as_of_ms: int
    resolution_status: OutcomeResolutionStatus
    outcome_state: OutcomeState | None
    horizon_bars: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.resolution_identity, "resolution identity"),
            (self.forecast_identity, "forecast identity"),
            (self.signal_freeze_identity, "signal freeze identity"),
            (self.outcome_identity, "outcome identity"),
        ):
            _require_sha256(value, label)
        if not self.resolution_version.strip():
            raise ValueError("resolution version must be non-empty")
        if self.evaluated_as_of_ms < 0:
            raise ValueError("forecast resolution timestamp must be non-negative")
        if self.horizon_bars <= 0:
            raise ValueError("forecast resolution horizon must be positive")
        if self.resolution_status is OutcomeResolutionStatus.PENDING:
            if self.outcome_state is not None:
                raise ValueError("pending forecast resolution cannot carry outcome state")
        elif self.outcome_state is None:
            raise ValueError("closed forecast resolution requires outcome state")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
