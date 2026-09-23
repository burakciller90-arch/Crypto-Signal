from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass
from research.alpha_factory.foundation import PartitionRole, ResearchPartition

R19_CALIBRATION_ENGINE_VERSION = "r19-probability-calibration-gate-v1-slice1/1"
R19_CALIBRATION_SCHEMA_VERSION = "r19-probability-calibration-v1/1"
R19_PROBABILITY_SEMANTIC = "frozen_binary_outcome_probability"
REAL_CAPITAL = 0


class CalibrationGateStatus(StrEnum):
    ACCEPTED = "accepted"
    NOT_YET_EVALUABLE = "not_yet_evaluable"
    NO_EVIDENCE = "no_evidence"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    INSUFFICIENT_CLASS_SUPPORT = "insufficient_class_support"
    INSUFFICIENT_BIN_SUPPORT = "insufficient_bin_support"
    FAILED_BRIER_SKILL = "failed_brier_skill"
    FAILED_CALIBRATION_ERROR = "failed_calibration_error"


class R19ProbabilityStatus(StrEnum):
    NOT_CALIBRATED = "not_calibrated"
    CALIBRATED = "calibrated"


@dataclass(frozen=True, slots=True)
class CalibrationScope:
    scope_identity: str
    asset: str
    timeframe: str
    regime: str
    outcome_event_definition: str
    horizon_ms: int

    def __post_init__(self) -> None:
        _require_sha256(self.scope_identity, "R19 scope identity")
        for text_value, label in (
            (self.asset, "R19 scope asset"),
            (self.timeframe, "R19 scope timeframe"),
            (self.regime, "R19 scope regime"),
            (self.outcome_event_definition, "R19 outcome event definition"),
        ):
            _require_text(text_value, label)
        if self.asset != self.asset.upper():
            raise ValueError("R19 scope asset must be uppercase")
        if self.horizon_ms <= 0:
            raise ValueError("R19 scope horizon must be positive")
        if self.scope_identity != canonical_sha256(_scope_payload(self)):
            raise ValueError("R19 scope identity mismatch")


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    scope: CalibrationScope
    model_version: str
    calibrator_version: str
    walk_forward_fit_identity: str
    created_at_ms: int
    training_cutoff_ms: int
    training_sample_count: int
    training_positive_count: int
    decision_window_start_ms: int
    decision_window_end_ms: int
    evaluation_cutoff_ms: int
    probability_bin_edges: tuple[Decimal, ...]
    minimum_holdout_n: int
    minimum_holdout_class_n: int
    minimum_reliability_bin_n: int
    minimum_brier_skill: Decimal
    maximum_expected_calibration_error: Decimal
    probability_semantic: str = R19_PROBABILITY_SEMANTIC
    automatic_promotion: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "R19 config identity")
        _require_sha256(
            self.walk_forward_fit_identity,
            "R19 walk-forward fit identity",
        )
        if self.schema_version != R19_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported R19 calibration schema")
        if self.engine_version != R19_CALIBRATION_ENGINE_VERSION:
            raise ValueError("unsupported R19 calibration engine")
        for text_value, label in (
            (self.policy_version, "R19 calibration policy version"),
            (self.model_version, "R19 model version"),
            (self.calibrator_version, "R19 calibrator version"),
        ):
            _require_text(text_value, label)
        if min(
            self.created_at_ms,
            self.training_cutoff_ms,
            self.decision_window_start_ms,
            self.decision_window_end_ms,
            self.evaluation_cutoff_ms,
        ) < 0:
            raise ValueError("R19 calibration timestamps must be non-negative")
        if self.created_at_ms >= self.decision_window_start_ms:
            raise ValueError("R19 calibration config must predate holdout decision window")
        if self.training_cutoff_ms >= self.decision_window_start_ms:
            raise ValueError("R19 training cutoff must predate untouched holdout")
        if self.decision_window_end_ms <= self.decision_window_start_ms:
            raise ValueError("R19 holdout decision window requires start before end")
        if (
            self.evaluation_cutoff_ms
            < self.decision_window_end_ms + self.scope.horizon_ms
        ):
            raise ValueError(
                "R19 evaluation cutoff must cover full horizon after holdout window"
            )
        if self.training_sample_count <= 0:
            raise ValueError("R19 training sample count must be positive")
        if not 0 < self.training_positive_count < self.training_sample_count:
            raise ValueError("R19 training set requires both outcome classes")
        if min(
            self.minimum_holdout_n,
            self.minimum_holdout_class_n,
            self.minimum_reliability_bin_n,
        ) <= 0:
            raise ValueError("R19 holdout support thresholds must be positive")
        if not self.probability_bin_edges:
            raise ValueError("R19 probability bins cannot be empty")
        if len(self.probability_bin_edges) < 3:
            raise ValueError("R19 probability bins require at least two intervals")
        if (
            self.probability_bin_edges[0] != Decimal(0)
            or self.probability_bin_edges[-1] != Decimal(1)
        ):
            raise ValueError("R19 probability bins must span exactly [0,1]")
        if tuple(sorted(set(self.probability_bin_edges))) != self.probability_bin_edges:
            raise ValueError("R19 probability bin edges must be unique and sorted")
        for edge in self.probability_bin_edges:
            _require_unit_interval(edge, "R19 probability bin edge")
        if self.minimum_brier_skill > Decimal(1):
            raise ValueError("R19 minimum Brier skill cannot exceed 1")
        _require_unit_interval(
            self.maximum_expected_calibration_error,
            "R19 maximum expected calibration error",
        )
        if self.probability_semantic != R19_PROBABILITY_SEMANTIC:
            raise ValueError("R19 probability semantic mismatch")
        if self.automatic_promotion or self.production_authority:
            raise ValueError("R19 calibration gate has no promotion/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("R19 calibration config identity mismatch")

    @property
    def training_base_rate(self) -> Decimal:
        return Decimal(self.training_positive_count) / Decimal(
            self.training_sample_count
        )


@dataclass(frozen=True, slots=True)
class FrozenProbabilityPrediction:
    prediction_identity: str
    schema_version: str
    engine_version: str
    scope_identity: str
    model_version: str
    calibrator_version: str
    walk_forward_fit_identity: str
    source_forecast_identity: str
    issued_at_ms: int
    predicted_probability_0_1: Decimal
    probability_semantic: str = R19_PROBABILITY_SEMANTIC
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.prediction_identity, "R19 prediction identity"),
            (self.scope_identity, "R19 prediction scope identity"),
            (self.walk_forward_fit_identity, "R19 prediction walk-forward identity"),
            (self.source_forecast_identity, "R19 prediction source forecast identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != R19_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported R19 prediction schema")
        if self.engine_version != R19_CALIBRATION_ENGINE_VERSION:
            raise ValueError("unsupported R19 prediction engine")
        _require_text(self.model_version, "R19 prediction model version")
        _require_text(self.calibrator_version, "R19 prediction calibrator version")
        if self.issued_at_ms < 0:
            raise ValueError("R19 prediction issuance must be non-negative")
        _require_unit_interval(
            self.predicted_probability_0_1,
            "R19 frozen predicted probability",
        )
        if self.probability_semantic != R19_PROBABILITY_SEMANTIC:
            raise ValueError("R19 prediction probability semantic mismatch")
        if self.production_authority:
            raise ValueError("R19 prediction has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.prediction_identity != canonical_sha256(_prediction_payload(self)):
            raise ValueError("R19 frozen prediction identity mismatch")


@dataclass(frozen=True, slots=True)
class UntouchedProbabilityObservation:
    observation_identity: str
    schema_version: str
    engine_version: str
    scope_identity: str
    model_version: str
    calibrator_version: str
    walk_forward_fit_identity: str
    source_prediction_identity: str
    source_forecast_identity: str
    source_outcome_identity: str
    evidence_class: EvidenceClass
    issued_at_ms: int
    outcome_available_at_ms: int
    predicted_probability_0_1: Decimal
    observed_positive: bool

    def __post_init__(self) -> None:
        for identity, label in (
            (self.observation_identity, "R19 observation identity"),
            (self.scope_identity, "R19 observation scope identity"),
            (self.walk_forward_fit_identity, "R19 observation walk-forward identity"),
            (self.source_prediction_identity, "R19 source prediction identity"),
            (self.source_forecast_identity, "R19 source forecast identity"),
            (self.source_outcome_identity, "R19 source outcome identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != R19_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported R19 observation schema")
        if self.engine_version != R19_CALIBRATION_ENGINE_VERSION:
            raise ValueError("unsupported R19 observation engine")
        _require_text(self.model_version, "R19 observation model version")
        _require_text(self.calibrator_version, "R19 observation calibrator version")
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("R19 calibration accepts LIVE_UNTOUCHED_FORWARD only")
        if min(self.issued_at_ms, self.outcome_available_at_ms) < 0:
            raise ValueError("R19 observation timestamps must be non-negative")
        if self.outcome_available_at_ms <= self.issued_at_ms:
            raise ValueError("R19 outcome must become available after forecast issuance")
        _require_unit_interval(
            self.predicted_probability_0_1,
            "R19 predicted probability",
        )
        expected_prediction = {
            "calibrator_version": self.calibrator_version,
            "engine_version": self.engine_version,
            "issued_at_ms": self.issued_at_ms,
            "model_version": self.model_version,
            "predicted_probability_0_1": self.predicted_probability_0_1,
            "probability_semantic": R19_PROBABILITY_SEMANTIC,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
            "schema_version": self.schema_version,
            "scope_identity": self.scope_identity,
            "source_forecast_identity": self.source_forecast_identity,
            "walk_forward_fit_identity": self.walk_forward_fit_identity,
        }
        if self.source_prediction_identity != canonical_sha256(expected_prediction):
            raise ValueError("R19 observation source prediction identity mismatch")
        if self.observation_identity != canonical_sha256(_observation_payload(self)):
            raise ValueError("R19 probability observation identity mismatch")


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower_bound: Decimal
    upper_bound: Decimal
    upper_inclusive: bool
    sample_count: int
    positive_count: int
    mean_predicted_probability: Decimal
    observed_positive_fraction: Decimal
    absolute_calibration_gap: Decimal

    def __post_init__(self) -> None:
        _require_unit_interval(self.lower_bound, "R19 reliability lower bound")
        _require_unit_interval(self.upper_bound, "R19 reliability upper bound")
        if self.upper_bound <= self.lower_bound:
            raise ValueError("R19 reliability bin bounds are invalid")
        if self.sample_count <= 0:
            raise ValueError("R19 reliability bin requires samples")
        if not 0 <= self.positive_count <= self.sample_count:
            raise ValueError("R19 reliability bin positive count is invalid")
        for probability_value in (
            self.mean_predicted_probability,
            self.observed_positive_fraction,
            self.absolute_calibration_gap,
        ):
            _require_unit_interval(
                probability_value,
                "R19 reliability metric",
            )


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationReport:
    evidence_identity: str
    schema_version: str
    engine_version: str
    config_identity: str
    partition_identity: str
    scope_identity: str
    model_version: str
    calibrator_version: str
    walk_forward_fit_identity: str
    status: CalibrationGateStatus
    probability_status: R19ProbabilityStatus
    holdout_sample_count: int
    holdout_positive_count: int
    holdout_negative_count: int
    brier_score: Decimal | None
    baseline_brier_score: Decimal | None
    brier_skill_score: Decimal | None
    expected_calibration_error: Decimal | None
    maximum_calibration_error: Decimal | None
    reliability_bins: tuple[ReliabilityBin, ...]
    observation_identities: tuple[str, ...]
    training_cutoff_ms: int
    evaluation_cutoff_ms: int
    probability_semantic: str = R19_PROBABILITY_SEMANTIC
    automatic_promotion: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.evidence_identity, "R19 report evidence identity"),
            (self.config_identity, "R19 report config identity"),
            (self.partition_identity, "R19 report partition identity"),
            (self.scope_identity, "R19 report scope identity"),
            (self.walk_forward_fit_identity, "R19 report walk-forward identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != R19_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported R19 report schema")
        if self.engine_version != R19_CALIBRATION_ENGINE_VERSION:
            raise ValueError("unsupported R19 report engine")
        _require_text(self.model_version, "R19 report model version")
        _require_text(self.calibrator_version, "R19 report calibrator version")
        if min(
            self.holdout_sample_count,
            self.holdout_positive_count,
            self.holdout_negative_count,
            self.training_cutoff_ms,
            self.evaluation_cutoff_ms,
        ) < 0:
            raise ValueError("R19 report counts/timestamps must be non-negative")
        if (
            self.holdout_positive_count + self.holdout_negative_count
            != self.holdout_sample_count
        ):
            raise ValueError("R19 holdout class counts do not equal sample count")
        _require_identity_tuple(
            self.observation_identities,
            "R19 report observation identity",
        )
        if len(self.observation_identities) != self.holdout_sample_count:
            raise ValueError("R19 report observation count mismatch")
        metric_values = (
            self.brier_score,
            self.baseline_brier_score,
            self.expected_calibration_error,
            self.maximum_calibration_error,
        )
        for metric_value in metric_values:
            if metric_value is not None:
                _require_unit_interval(metric_value, "R19 calibration metric")
        if self.brier_skill_score is not None and self.brier_skill_score > Decimal(1):
            raise ValueError("R19 Brier skill cannot exceed 1")
        if self.holdout_sample_count == 0:
            if any(metric_value is not None for metric_value in metric_values):
                raise ValueError("empty R19 report cannot expose calibration metrics")
            if self.brier_skill_score is not None or self.reliability_bins:
                raise ValueError("empty R19 report cannot expose diagnostics")
        else:
            required_metrics = (
                self.brier_score,
                self.baseline_brier_score,
                self.expected_calibration_error,
                self.maximum_calibration_error,
            )
            if any(metric_value is None for metric_value in required_metrics):
                raise ValueError("non-empty R19 report requires calibration metrics")
            if not self.reliability_bins:
                raise ValueError("non-empty R19 report requires reliability bins")
        if self.status is CalibrationGateStatus.ACCEPTED:
            if self.probability_status is not R19ProbabilityStatus.CALIBRATED:
                raise ValueError("accepted R19 report must authorize calibrated status")
            if self.brier_skill_score is None:
                raise ValueError("accepted R19 report requires Brier skill")
        elif self.probability_status is not R19ProbabilityStatus.NOT_CALIBRATED:
            raise ValueError("unaccepted R19 report must remain NOT_CALIBRATED")
        if self.probability_semantic != R19_PROBABILITY_SEMANTIC:
            raise ValueError("R19 report probability semantic mismatch")
        if self.automatic_promotion or self.production_authority:
            raise ValueError("R19 report has no promotion/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.evidence_identity != canonical_sha256(_report_payload(self)):
            raise ValueError("R19 calibration evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class CalibratedProbabilityEvidence:
    authorization_identity: str
    schema_version: str
    engine_version: str
    calibration_evidence_identity: str
    scope_identity: str
    model_version: str
    calibrator_version: str
    walk_forward_fit_identity: str
    source_prediction_identity: str
    source_forecast_identity: str
    issued_at_ms: int
    probability_0_1: Decimal
    probability_status: R19ProbabilityStatus
    probability_semantic: str
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.authorization_identity, "R19 probability authorization identity"),
            (self.calibration_evidence_identity, "R19 calibration evidence identity"),
            (self.scope_identity, "R19 probability scope identity"),
            (self.walk_forward_fit_identity, "R19 probability walk-forward identity"),
            (self.source_prediction_identity, "R19 probability source prediction identity"),
            (self.source_forecast_identity, "R19 probability source forecast identity"),
        ):
            _require_sha256(identity, label)
        if self.schema_version != R19_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported R19 probability authorization schema")
        if self.engine_version != R19_CALIBRATION_ENGINE_VERSION:
            raise ValueError("unsupported R19 probability authorization engine")
        _require_text(self.model_version, "R19 probability model version")
        _require_text(self.calibrator_version, "R19 probability calibrator version")
        if self.issued_at_ms < 0:
            raise ValueError("R19 probability issuance must be non-negative")
        _require_unit_interval(self.probability_0_1, "R19 authorized probability")
        expected_prediction = {
            "calibrator_version": self.calibrator_version,
            "engine_version": self.engine_version,
            "issued_at_ms": self.issued_at_ms,
            "model_version": self.model_version,
            "predicted_probability_0_1": self.probability_0_1,
            "probability_semantic": R19_PROBABILITY_SEMANTIC,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
            "schema_version": self.schema_version,
            "scope_identity": self.scope_identity,
            "source_forecast_identity": self.source_forecast_identity,
            "walk_forward_fit_identity": self.walk_forward_fit_identity,
        }
        if self.source_prediction_identity != canonical_sha256(expected_prediction):
            raise ValueError("R19 authorization source prediction identity mismatch")
        if self.probability_status is not R19ProbabilityStatus.CALIBRATED:
            raise ValueError("R19 authorization must be CALIBRATED")
        if self.probability_semantic != R19_PROBABILITY_SEMANTIC:
            raise ValueError("R19 authorization semantic mismatch")
        if self.production_authority:
            raise ValueError("R19 probability has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.authorization_identity != canonical_sha256(
            _authorization_payload(self)
        ):
            raise ValueError("R19 probability authorization identity mismatch")


def build_calibration_scope(
    *,
    asset: str,
    timeframe: str,
    regime: str,
    outcome_event_definition: str,
    horizon_ms: int,
) -> CalibrationScope:
    payload = {
        "asset": asset,
        "horizon_ms": horizon_ms,
        "outcome_event_definition": outcome_event_definition,
        "regime": regime,
        "timeframe": timeframe,
    }
    return CalibrationScope(
        scope_identity=canonical_sha256(payload),
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        outcome_event_definition=outcome_event_definition,
        horizon_ms=horizon_ms,
    )


def build_probability_calibration_config(
    *,
    policy_version: str,
    scope: CalibrationScope,
    model_version: str,
    calibrator_version: str,
    walk_forward_fit_identity: str,
    created_at_ms: int,
    training_cutoff_ms: int,
    training_sample_count: int,
    training_positive_count: int,
    decision_window_start_ms: int,
    decision_window_end_ms: int,
    evaluation_cutoff_ms: int,
    probability_bin_edges: tuple[Decimal, ...],
    minimum_holdout_n: int,
    minimum_holdout_class_n: int,
    minimum_reliability_bin_n: int,
    minimum_brier_skill: Decimal,
    maximum_expected_calibration_error: Decimal,
) -> ProbabilityCalibrationConfig:
    payload = {
        "automatic_promotion": False,
        "calibrator_version": calibrator_version,
        "created_at_ms": created_at_ms,
        "decision_window_end_ms": decision_window_end_ms,
        "decision_window_start_ms": decision_window_start_ms,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "evaluation_cutoff_ms": evaluation_cutoff_ms,
        "maximum_expected_calibration_error": maximum_expected_calibration_error,
        "minimum_brier_skill": minimum_brier_skill,
        "minimum_holdout_class_n": minimum_holdout_class_n,
        "minimum_holdout_n": minimum_holdout_n,
        "minimum_reliability_bin_n": minimum_reliability_bin_n,
        "model_version": model_version,
        "policy_version": policy_version,
        "probability_bin_edges": probability_bin_edges,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": scope.scope_identity,
        "training_cutoff_ms": training_cutoff_ms,
        "training_positive_count": training_positive_count,
        "training_sample_count": training_sample_count,
        "walk_forward_fit_identity": walk_forward_fit_identity,
    }
    return ProbabilityCalibrationConfig(
        config_identity=canonical_sha256(payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        policy_version=policy_version,
        scope=scope,
        model_version=model_version,
        calibrator_version=calibrator_version,
        walk_forward_fit_identity=walk_forward_fit_identity,
        created_at_ms=created_at_ms,
        training_cutoff_ms=training_cutoff_ms,
        training_sample_count=training_sample_count,
        training_positive_count=training_positive_count,
        decision_window_start_ms=decision_window_start_ms,
        decision_window_end_ms=decision_window_end_ms,
        evaluation_cutoff_ms=evaluation_cutoff_ms,
        probability_bin_edges=probability_bin_edges,
        minimum_holdout_n=minimum_holdout_n,
        minimum_holdout_class_n=minimum_holdout_class_n,
        minimum_reliability_bin_n=minimum_reliability_bin_n,
        minimum_brier_skill=minimum_brier_skill,
        maximum_expected_calibration_error=maximum_expected_calibration_error,
    )


def build_frozen_probability_prediction(
    config: ProbabilityCalibrationConfig,
    *,
    source_forecast_identity: str,
    issued_at_ms: int,
    predicted_probability_0_1: Decimal,
) -> FrozenProbabilityPrediction:
    if issued_at_ms < config.decision_window_start_ms:
        raise ValueError("R19 prediction cannot predate frozen holdout start")
    _require_sha256(source_forecast_identity, "R19 prediction source forecast")
    payload = {
        "calibrator_version": config.calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "issued_at_ms": issued_at_ms,
        "model_version": config.model_version,
        "predicted_probability_0_1": predicted_probability_0_1,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": config.scope.scope_identity,
        "source_forecast_identity": source_forecast_identity,
        "walk_forward_fit_identity": config.walk_forward_fit_identity,
    }
    return FrozenProbabilityPrediction(
        prediction_identity=canonical_sha256(payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        scope_identity=config.scope.scope_identity,
        model_version=config.model_version,
        calibrator_version=config.calibrator_version,
        walk_forward_fit_identity=config.walk_forward_fit_identity,
        source_forecast_identity=source_forecast_identity,
        issued_at_ms=issued_at_ms,
        predicted_probability_0_1=predicted_probability_0_1,
    )


def build_untouched_probability_observation(
    prediction: FrozenProbabilityPrediction,
    *,
    source_outcome_identity: str,
    outcome_available_at_ms: int,
    observed_positive: bool,
) -> UntouchedProbabilityObservation:
    _require_sha256(source_outcome_identity, "R19 observation source outcome")
    payload = {
        "calibrator_version": prediction.calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "evidence_class": EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        "issued_at_ms": prediction.issued_at_ms,
        "model_version": prediction.model_version,
        "observed_positive": observed_positive,
        "outcome_available_at_ms": outcome_available_at_ms,
        "predicted_probability_0_1": prediction.predicted_probability_0_1,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": prediction.scope_identity,
        "source_forecast_identity": prediction.source_forecast_identity,
        "source_outcome_identity": source_outcome_identity,
        "source_prediction_identity": prediction.prediction_identity,
        "walk_forward_fit_identity": prediction.walk_forward_fit_identity,
    }
    return UntouchedProbabilityObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        scope_identity=prediction.scope_identity,
        model_version=prediction.model_version,
        calibrator_version=prediction.calibrator_version,
        walk_forward_fit_identity=prediction.walk_forward_fit_identity,
        source_prediction_identity=prediction.prediction_identity,
        source_forecast_identity=prediction.source_forecast_identity,
        source_outcome_identity=source_outcome_identity,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        issued_at_ms=prediction.issued_at_ms,
        outcome_available_at_ms=outcome_available_at_ms,
        predicted_probability_0_1=prediction.predicted_probability_0_1,
        observed_positive=observed_positive,
    )


def evaluate_probability_calibration(
    config: ProbabilityCalibrationConfig,
    partition: ResearchPartition,
    observations: Sequence[UntouchedProbabilityObservation] = (),
    *,
    as_of_ms: int,
) -> ProbabilityCalibrationReport:
    if partition.role is not PartitionRole.UNTOUCHED_FORWARD:
        raise ValueError("R19 calibration requires UNTOUCHED_FORWARD partition")
    if (
        partition.start_ms != config.decision_window_start_ms
        or partition.end_ms != config.decision_window_end_ms
    ):
        raise ValueError("R19 holdout partition does not match frozen decision window")
    if as_of_ms < 0:
        raise ValueError("R19 calibration as_of_ms must be non-negative")
    if as_of_ms < config.evaluation_cutoff_ms:
        return _empty_report(
            config=config,
            partition=partition,
            status=CalibrationGateStatus.NOT_YET_EVALUABLE,
        )

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.issued_at_ms,
                item.source_forecast_identity,
                item.observation_identity,
            ),
        )
    )
    if not ordered:
        return _empty_report(
            config=config,
            partition=partition,
            status=CalibrationGateStatus.NO_EVIDENCE,
        )

    _validate_holdout(config, partition, ordered)
    positive_count = sum(item.observed_positive for item in ordered)
    negative_count = len(ordered) - positive_count

    reliability_bins = _build_reliability_bins(
        ordered,
        config.probability_bin_edges,
    )
    squared_errors = tuple(
        (
            item.predicted_probability_0_1
            - (Decimal(1) if item.observed_positive else Decimal(0))
        )
        ** 2
        for item in ordered
    )
    brier_score = _mean(squared_errors)
    training_base_rate = config.training_base_rate
    baseline_brier_score = _mean(
        tuple(
            (
                training_base_rate
                - (Decimal(1) if item.observed_positive else Decimal(0))
            )
            ** 2
            for item in ordered
        )
    )
    brier_skill_score = (
        Decimal(1) - (brier_score / baseline_brier_score)
        if baseline_brier_score > 0
        else None
    )
    expected_calibration_error = sum(
        (
            Decimal(item.sample_count)
            / Decimal(len(ordered))
            * item.absolute_calibration_gap
            for item in reliability_bins
        ),
        start=Decimal(0),
    )
    maximum_calibration_error = max(
        item.absolute_calibration_gap for item in reliability_bins
    )

    if len(ordered) < config.minimum_holdout_n:
        status = CalibrationGateStatus.INSUFFICIENT_SAMPLE
    elif min(positive_count, negative_count) < config.minimum_holdout_class_n:
        status = CalibrationGateStatus.INSUFFICIENT_CLASS_SUPPORT
    elif any(
        item.sample_count < config.minimum_reliability_bin_n
        for item in reliability_bins
    ):
        status = CalibrationGateStatus.INSUFFICIENT_BIN_SUPPORT
    elif (
        brier_skill_score is None
        or brier_skill_score < config.minimum_brier_skill
    ):
        status = CalibrationGateStatus.FAILED_BRIER_SKILL
    elif (
        expected_calibration_error
        > config.maximum_expected_calibration_error
    ):
        status = CalibrationGateStatus.FAILED_CALIBRATION_ERROR
    else:
        status = CalibrationGateStatus.ACCEPTED

    probability_status = (
        R19ProbabilityStatus.CALIBRATED
        if status is CalibrationGateStatus.ACCEPTED
        else R19ProbabilityStatus.NOT_CALIBRATED
    )
    return _report(
        config=config,
        partition=partition,
        status=status,
        probability_status=probability_status,
        observations=ordered,
        positive_count=positive_count,
        negative_count=negative_count,
        brier_score=brier_score,
        baseline_brier_score=baseline_brier_score,
        brier_skill_score=brier_skill_score,
        expected_calibration_error=expected_calibration_error,
        maximum_calibration_error=maximum_calibration_error,
        reliability_bins=reliability_bins,
    )


def authorize_calibrated_probability(
    report: ProbabilityCalibrationReport,
    prediction: FrozenProbabilityPrediction,
) -> CalibratedProbabilityEvidence | None:
    if report.status is not CalibrationGateStatus.ACCEPTED:
        return None
    if report.probability_status is not R19ProbabilityStatus.CALIBRATED:
        return None
    if prediction.scope_identity != report.scope_identity:
        return None
    if prediction.model_version != report.model_version:
        return None
    if prediction.calibrator_version != report.calibrator_version:
        return None
    if prediction.walk_forward_fit_identity != report.walk_forward_fit_identity:
        return None
    if prediction.issued_at_ms <= report.evaluation_cutoff_ms:
        return None
    payload = {
        "calibration_evidence_identity": report.evidence_identity,
        "calibrator_version": prediction.calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "issued_at_ms": prediction.issued_at_ms,
        "model_version": prediction.model_version,
        "probability_0_1": prediction.predicted_probability_0_1,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "probability_status": R19ProbabilityStatus.CALIBRATED,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": prediction.scope_identity,
        "source_forecast_identity": prediction.source_forecast_identity,
        "source_prediction_identity": prediction.prediction_identity,
        "walk_forward_fit_identity": prediction.walk_forward_fit_identity,
    }
    return CalibratedProbabilityEvidence(
        authorization_identity=canonical_sha256(payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        calibration_evidence_identity=report.evidence_identity,
        scope_identity=prediction.scope_identity,
        model_version=prediction.model_version,
        calibrator_version=prediction.calibrator_version,
        walk_forward_fit_identity=prediction.walk_forward_fit_identity,
        source_prediction_identity=prediction.prediction_identity,
        source_forecast_identity=prediction.source_forecast_identity,
        issued_at_ms=prediction.issued_at_ms,
        probability_0_1=prediction.predicted_probability_0_1,
        probability_status=R19ProbabilityStatus.CALIBRATED,
        probability_semantic=R19_PROBABILITY_SEMANTIC,
    )


def _validate_holdout(
    config: ProbabilityCalibrationConfig,
    partition: ResearchPartition,
    observations: tuple[UntouchedProbabilityObservation, ...],
) -> None:
    if len(observations) != partition.row_count:
        raise ValueError("R19 holdout observation count must match partition")
    observation_ids = tuple(sorted(item.observation_identity for item in observations))
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("R19 holdout observations must be unique")
    prediction_ids = tuple(
        sorted(item.source_prediction_identity for item in observations)
    )
    if prediction_ids != partition.evidence_identities:
        raise ValueError("R19 holdout predictions do not match partition evidence")
    if len(set(prediction_ids)) != len(prediction_ids):
        raise ValueError("R19 holdout source predictions must be unique")

    forecast_ids = tuple(item.source_forecast_identity for item in observations)
    if len(set(forecast_ids)) != len(forecast_ids):
        raise ValueError("R19 holdout source forecasts must be unique")

    for item in observations:
        if item.scope_identity != config.scope.scope_identity:
            raise ValueError("R19 holdout scope mismatch")
        if item.model_version != config.model_version:
            raise ValueError("R19 holdout model version mismatch")
        if item.calibrator_version != config.calibrator_version:
            raise ValueError("R19 holdout calibrator version mismatch")
        if item.walk_forward_fit_identity != config.walk_forward_fit_identity:
            raise ValueError("R19 holdout walk-forward fit mismatch")
        if not (
            config.decision_window_start_ms
            <= item.issued_at_ms
            < config.decision_window_end_ms
        ):
            raise ValueError("R19 forecast issued outside frozen holdout window")
        if item.outcome_available_at_ms > item.issued_at_ms + config.scope.horizon_ms:
            raise ValueError("R19 outcome exceeds frozen horizon")
        if item.outcome_available_at_ms > config.evaluation_cutoff_ms:
            raise ValueError("R19 outcome unavailable by evaluation cutoff")


def _build_reliability_bins(
    observations: tuple[UntouchedProbabilityObservation, ...],
    edges: tuple[Decimal, ...],
) -> tuple[ReliabilityBin, ...]:
    bins: list[ReliabilityBin] = []
    for index, (lower, upper) in enumerate(pairwise(edges)):
        upper_inclusive = index == len(edges) - 2
        items = tuple(
            item
            for item in observations
            if (
                lower <= item.predicted_probability_0_1 <= upper
                if upper_inclusive
                else lower <= item.predicted_probability_0_1 < upper
            )
        )
        if not items:
            continue
        count = len(items)
        positive_count = sum(item.observed_positive for item in items)
        mean_predicted = _mean(
            tuple(item.predicted_probability_0_1 for item in items)
        )
        observed_fraction = Decimal(positive_count) / Decimal(count)
        bins.append(
            ReliabilityBin(
                lower_bound=lower,
                upper_bound=upper,
                upper_inclusive=upper_inclusive,
                sample_count=count,
                positive_count=positive_count,
                mean_predicted_probability=mean_predicted,
                observed_positive_fraction=observed_fraction,
                absolute_calibration_gap=abs(mean_predicted - observed_fraction),
            )
        )
    return tuple(bins)


def _empty_report(
    *,
    config: ProbabilityCalibrationConfig,
    partition: ResearchPartition,
    status: CalibrationGateStatus,
) -> ProbabilityCalibrationReport:
    return _report(
        config=config,
        partition=partition,
        status=status,
        probability_status=R19ProbabilityStatus.NOT_CALIBRATED,
        observations=(),
        positive_count=0,
        negative_count=0,
        brier_score=None,
        baseline_brier_score=None,
        brier_skill_score=None,
        expected_calibration_error=None,
        maximum_calibration_error=None,
        reliability_bins=(),
    )


def _report(
    *,
    config: ProbabilityCalibrationConfig,
    partition: ResearchPartition,
    status: CalibrationGateStatus,
    probability_status: R19ProbabilityStatus,
    observations: tuple[UntouchedProbabilityObservation, ...],
    positive_count: int,
    negative_count: int,
    brier_score: Decimal | None,
    baseline_brier_score: Decimal | None,
    brier_skill_score: Decimal | None,
    expected_calibration_error: Decimal | None,
    maximum_calibration_error: Decimal | None,
    reliability_bins: tuple[ReliabilityBin, ...],
) -> ProbabilityCalibrationReport:
    observation_ids = tuple(sorted(item.observation_identity for item in observations))
    payload = {
        "automatic_promotion": False,
        "baseline_brier_score": baseline_brier_score,
        "brier_score": brier_score,
        "brier_skill_score": brier_skill_score,
        "calibrator_version": config.calibrator_version,
        "config_identity": config.config_identity,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "evaluation_cutoff_ms": config.evaluation_cutoff_ms,
        "expected_calibration_error": expected_calibration_error,
        "holdout_negative_count": negative_count,
        "holdout_positive_count": positive_count,
        "holdout_sample_count": len(observations),
        "maximum_calibration_error": maximum_calibration_error,
        "model_version": config.model_version,
        "observation_identities": observation_ids,
        "partition_identity": partition.partition_identity,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "probability_status": probability_status,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reliability_bins": reliability_bins,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": config.scope.scope_identity,
        "status": status,
        "training_cutoff_ms": config.training_cutoff_ms,
        "walk_forward_fit_identity": config.walk_forward_fit_identity,
    }
    return ProbabilityCalibrationReport(
        evidence_identity=canonical_sha256(payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        config_identity=config.config_identity,
        partition_identity=partition.partition_identity,
        scope_identity=config.scope.scope_identity,
        model_version=config.model_version,
        calibrator_version=config.calibrator_version,
        walk_forward_fit_identity=config.walk_forward_fit_identity,
        status=status,
        probability_status=probability_status,
        holdout_sample_count=len(observations),
        holdout_positive_count=positive_count,
        holdout_negative_count=negative_count,
        brier_score=brier_score,
        baseline_brier_score=baseline_brier_score,
        brier_skill_score=brier_skill_score,
        expected_calibration_error=expected_calibration_error,
        maximum_calibration_error=maximum_calibration_error,
        reliability_bins=reliability_bins,
        observation_identities=observation_ids,
        training_cutoff_ms=config.training_cutoff_ms,
        evaluation_cutoff_ms=config.evaluation_cutoff_ms,
    )


def _scope_payload(scope: CalibrationScope) -> dict[str, object]:
    return {
        "asset": scope.asset,
        "horizon_ms": scope.horizon_ms,
        "outcome_event_definition": scope.outcome_event_definition,
        "regime": scope.regime,
        "timeframe": scope.timeframe,
    }


def _config_payload(config: ProbabilityCalibrationConfig) -> dict[str, object]:
    return {
        "automatic_promotion": config.automatic_promotion,
        "calibrator_version": config.calibrator_version,
        "created_at_ms": config.created_at_ms,
        "decision_window_end_ms": config.decision_window_end_ms,
        "decision_window_start_ms": config.decision_window_start_ms,
        "engine_version": config.engine_version,
        "evaluation_cutoff_ms": config.evaluation_cutoff_ms,
        "maximum_expected_calibration_error": (
            config.maximum_expected_calibration_error
        ),
        "minimum_brier_skill": config.minimum_brier_skill,
        "minimum_holdout_class_n": config.minimum_holdout_class_n,
        "minimum_holdout_n": config.minimum_holdout_n,
        "minimum_reliability_bin_n": config.minimum_reliability_bin_n,
        "model_version": config.model_version,
        "policy_version": config.policy_version,
        "probability_bin_edges": config.probability_bin_edges,
        "probability_semantic": config.probability_semantic,
        "production_authority": config.production_authority,
        "real_capital": config.real_capital,
        "schema_version": config.schema_version,
        "scope_identity": config.scope.scope_identity,
        "training_cutoff_ms": config.training_cutoff_ms,
        "training_positive_count": config.training_positive_count,
        "training_sample_count": config.training_sample_count,
        "walk_forward_fit_identity": config.walk_forward_fit_identity,
    }


def _prediction_payload(
    prediction: FrozenProbabilityPrediction,
) -> dict[str, object]:
    return {
        "calibrator_version": prediction.calibrator_version,
        "engine_version": prediction.engine_version,
        "issued_at_ms": prediction.issued_at_ms,
        "model_version": prediction.model_version,
        "predicted_probability_0_1": prediction.predicted_probability_0_1,
        "probability_semantic": prediction.probability_semantic,
        "production_authority": prediction.production_authority,
        "real_capital": prediction.real_capital,
        "schema_version": prediction.schema_version,
        "scope_identity": prediction.scope_identity,
        "source_forecast_identity": prediction.source_forecast_identity,
        "walk_forward_fit_identity": prediction.walk_forward_fit_identity,
    }


def _observation_payload(
    observation: UntouchedProbabilityObservation,
) -> dict[str, object]:
    return {
        "calibrator_version": observation.calibrator_version,
        "engine_version": observation.engine_version,
        "evidence_class": observation.evidence_class,
        "issued_at_ms": observation.issued_at_ms,
        "model_version": observation.model_version,
        "observed_positive": observation.observed_positive,
        "outcome_available_at_ms": observation.outcome_available_at_ms,
        "predicted_probability_0_1": observation.predicted_probability_0_1,
        "schema_version": observation.schema_version,
        "scope_identity": observation.scope_identity,
        "source_forecast_identity": observation.source_forecast_identity,
        "source_prediction_identity": observation.source_prediction_identity,
        "source_outcome_identity": observation.source_outcome_identity,
        "walk_forward_fit_identity": observation.walk_forward_fit_identity,
    }


def _report_payload(report: ProbabilityCalibrationReport) -> dict[str, object]:
    return {
        "automatic_promotion": report.automatic_promotion,
        "baseline_brier_score": report.baseline_brier_score,
        "brier_score": report.brier_score,
        "brier_skill_score": report.brier_skill_score,
        "calibrator_version": report.calibrator_version,
        "config_identity": report.config_identity,
        "engine_version": report.engine_version,
        "evaluation_cutoff_ms": report.evaluation_cutoff_ms,
        "expected_calibration_error": report.expected_calibration_error,
        "holdout_negative_count": report.holdout_negative_count,
        "holdout_positive_count": report.holdout_positive_count,
        "holdout_sample_count": report.holdout_sample_count,
        "maximum_calibration_error": report.maximum_calibration_error,
        "model_version": report.model_version,
        "observation_identities": report.observation_identities,
        "partition_identity": report.partition_identity,
        "probability_semantic": report.probability_semantic,
        "probability_status": report.probability_status,
        "production_authority": report.production_authority,
        "real_capital": report.real_capital,
        "reliability_bins": report.reliability_bins,
        "schema_version": report.schema_version,
        "scope_identity": report.scope_identity,
        "status": report.status,
        "training_cutoff_ms": report.training_cutoff_ms,
        "walk_forward_fit_identity": report.walk_forward_fit_identity,
    }


def _authorization_payload(
    evidence: CalibratedProbabilityEvidence,
) -> dict[str, object]:
    return {
        "calibration_evidence_identity": evidence.calibration_evidence_identity,
        "calibrator_version": evidence.calibrator_version,
        "engine_version": evidence.engine_version,
        "issued_at_ms": evidence.issued_at_ms,
        "model_version": evidence.model_version,
        "probability_0_1": evidence.probability_0_1,
        "probability_semantic": evidence.probability_semantic,
        "probability_status": evidence.probability_status,
        "production_authority": evidence.production_authority,
        "real_capital": evidence.real_capital,
        "schema_version": evidence.schema_version,
        "scope_identity": evidence.scope_identity,
        "source_forecast_identity": evidence.source_forecast_identity,
        "source_prediction_identity": evidence.source_prediction_identity,
        "walk_forward_fit_identity": evidence.walk_forward_fit_identity,
    }


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("R19 mean requires at least one value")
    return sum(values, start=Decimal(0)) / Decimal(len(values))


def _require_unit_interval(value: Decimal, label: str) -> None:
    if (
        value.is_nan()
        or value.is_infinite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{label} must be inside [0,1]")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
