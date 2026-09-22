from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_EVEN
from enum import StrEnum

from crypto_signal.evaluation.aggregate import confluence_score_bucket
from crypto_signal.evaluation.models import ConfluenceScoreBucket, EvaluatedSignal
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeResolutionStatus,
    OutcomeState,
)

_SUCCESS_STATES = {
    OutcomeState.SUCCESS_TP1,
    OutcomeState.SUCCESS_TP2,
    OutcomeState.SUCCESS_TP3,
}
_DECISIVE_STATES = _SUCCESS_STATES | {OutcomeState.FAIL_SL}
_Q = Decimal("0.000001")


class ProbabilityEvent(StrEnum):
    TP1_BEFORE_STOP_WITHIN_FROZEN_HORIZON = (
        "tp1_before_stop_within_frozen_horizon"
    )


class ProbabilityCalibrationStatus(StrEnum):
    CALIBRATED = "calibrated"
    NOT_CALIBRATED = "not_calibrated"


class ProbabilityCalibrationReason(StrEnum):
    ACCEPTED = "accepted"
    INSUFFICIENT_TRAINING_SAMPLE = "insufficient_training_sample"
    INSUFFICIENT_VALIDATION_SAMPLE = "insufficient_validation_sample"
    MISSING_BUCKET_SUPPORT = "missing_bucket_support"
    BRIER_GATE_FAILED = "brier_gate_failed"
    CALIBRATION_ERROR_GATE_FAILED = "calibration_error_gate_failed"


@dataclass(frozen=True, slots=True)
class CalibrationPolicy:
    policy_version: str = "probability-calibration-v1/1"
    event: ProbabilityEvent = (
        ProbabilityEvent.TP1_BEFORE_STOP_WITHIN_FROZEN_HORIZON
    )
    training_evidence_classes: tuple[EvidenceClass, ...] = (
        EvidenceClass.WALK_FORWARD,
    )
    validation_evidence_classes: tuple[EvidenceClass, ...] = (
        EvidenceClass.LIVE_UNTOUCHED_FORWARD,
    )
    minimum_training_n: int = 30
    minimum_validation_n: int = 20
    minimum_bucket_training_n: int = 5
    maximum_brier_score: Decimal = Decimal("0.25")
    maximum_expected_calibration_error: Decimal = Decimal("0.15")
    require_no_worse_than_base_rate_brier: bool = True

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("calibration policy version must be non-empty")
        if not self.training_evidence_classes:
            raise ValueError("training evidence classes cannot be empty")
        if not self.validation_evidence_classes:
            raise ValueError("validation evidence classes cannot be empty")
        if set(self.training_evidence_classes) & set(
            self.validation_evidence_classes
        ):
            raise ValueError(
                "training and validation evidence classes must be disjoint"
            )
        if self.minimum_training_n <= 0 or self.minimum_validation_n <= 0:
            raise ValueError("calibration sample thresholds must be positive")
        if self.minimum_bucket_training_n <= 0:
            raise ValueError("bucket training threshold must be positive")
        for value in (
            self.maximum_brier_score,
            self.maximum_expected_calibration_error,
        ):
            if not Decimal(0) <= value <= Decimal(1):
                raise ValueError("calibration metric gates must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class BucketProbability:
    bucket: ConfluenceScoreBucket
    training_n: int
    success_n: int
    probability: Decimal

    def __post_init__(self) -> None:
        if self.training_n <= 0:
            raise ValueError("bucket training_n must be positive")
        if not 0 <= self.success_n <= self.training_n:
            raise ValueError("bucket success_n must be within training sample")
        if not Decimal(0) <= self.probability <= Decimal(1):
            raise ValueError("bucket probability must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationMetrics:
    validation_n: int
    validation_success_n: int
    validation_base_rate: Decimal | None
    brier_score: Decimal | None
    base_rate_brier_score: Decimal | None
    expected_calibration_error: Decimal | None

    def __post_init__(self) -> None:
        if self.validation_n < 0:
            raise ValueError("validation_n cannot be negative")
        if not 0 <= self.validation_success_n <= self.validation_n:
            raise ValueError("validation success count is inconsistent")
        values = (
            self.validation_base_rate,
            self.brier_score,
            self.base_rate_brier_score,
            self.expected_calibration_error,
        )
        if self.validation_n == 0:
            if any(value is not None for value in values):
                raise ValueError("empty validation sample cannot carry metrics")
        else:
            if any(value is None for value in values):
                raise ValueError("non-empty validation sample requires metrics")
            if any(
                value is not None
                and not Decimal(0) <= value <= Decimal(1)
                for value in values
            ):
                raise ValueError("probability metrics must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class CalibratedProbabilityModel:
    model_identity: str
    model_version: str
    event: ProbabilityEvent
    training_cutoff_ms: int
    trained_through_outcome_ms: int | None
    validated_through_outcome_ms: int | None
    status: ProbabilityCalibrationStatus
    reason: ProbabilityCalibrationReason
    training_n: int
    bucket_probabilities: tuple[BucketProbability, ...]
    metrics: ProbabilityCalibrationMetrics
    policy: CalibrationPolicy

    def __post_init__(self) -> None:
        if len(self.model_identity) != 64:
            raise ValueError("calibration model identity must be SHA256")
        int(self.model_identity, 16)
        if not self.model_version.strip():
            raise ValueError("calibration model version must be non-empty")
        if self.training_cutoff_ms < 0:
            raise ValueError("training cutoff must be non-negative")
        if self.training_n < 0:
            raise ValueError("training_n cannot be negative")
        if self.status is ProbabilityCalibrationStatus.CALIBRATED:
            if self.reason is not ProbabilityCalibrationReason.ACCEPTED:
                raise ValueError("calibrated model requires accepted reason")
        elif self.reason is ProbabilityCalibrationReason.ACCEPTED:
            raise ValueError("not-calibrated model cannot be accepted")
        buckets = [item.bucket for item in self.bucket_probabilities]
        if len(set(buckets)) != len(buckets):
            raise ValueError("bucket probabilities must be unique")


@dataclass(frozen=True, slots=True)
class ProbabilityEstimate:
    model_identity: str
    event: ProbabilityEvent
    confluence_score_bucket: ConfluenceScoreBucket
    probability: Decimal | None
    status: ProbabilityCalibrationStatus
    reason: ProbabilityCalibrationReason
    training_n: int
    validation_n: int

    def __post_init__(self) -> None:
        if len(self.model_identity) != 64:
            raise ValueError("estimate model identity must be SHA256")
        int(self.model_identity, 16)
        if self.probability is not None and not (
            Decimal(0) <= self.probability <= Decimal(1)
        ):
            raise ValueError("probability estimate must be in [0, 1]")
        if self.status is ProbabilityCalibrationStatus.CALIBRATED:
            if self.probability is None:
                raise ValueError("calibrated estimate requires probability")
        elif self.probability is not None:
            raise ValueError("not-calibrated estimate cannot expose probability")


def _decisive_label(item: EvaluatedSignal) -> int | None:
    outcome = item.outcome
    if outcome.resolution_status is not OutcomeResolutionStatus.RESOLVED:
        return None
    state = outcome.outcome_state
    if state not in _DECISIVE_STATES:
        return None
    return 1 if state in _SUCCESS_STATES else 0


def _bucket(item: EvaluatedSignal) -> ConfluenceScoreBucket:
    return confluence_score_bucket(item.decision.agreement.confluence_score)


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("mean requires observations")
    return sum(values, Decimal(0)) / Decimal(len(values))


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_EVEN)


def _identity_payload(model: CalibratedProbabilityModel) -> dict[str, object]:
    return {
        "model_version": model.model_version,
        "event": model.event.value,
        "training_cutoff_ms": model.training_cutoff_ms,
        "trained_through_outcome_ms": model.trained_through_outcome_ms,
        "validated_through_outcome_ms": model.validated_through_outcome_ms,
        "status": model.status.value,
        "reason": model.reason.value,
        "training_n": model.training_n,
        "bucket_probabilities": [
            {
                "bucket": item.bucket.value,
                "training_n": item.training_n,
                "success_n": item.success_n,
                "probability": str(item.probability),
            }
            for item in model.bucket_probabilities
        ],
        "metrics": {
            "validation_n": model.metrics.validation_n,
            "validation_success_n": model.metrics.validation_success_n,
            "validation_base_rate": (
                None
                if model.metrics.validation_base_rate is None
                else str(model.metrics.validation_base_rate)
            ),
            "brier_score": (
                None
                if model.metrics.brier_score is None
                else str(model.metrics.brier_score)
            ),
            "base_rate_brier_score": (
                None
                if model.metrics.base_rate_brier_score is None
                else str(model.metrics.base_rate_brier_score)
            ),
            "expected_calibration_error": (
                None
                if model.metrics.expected_calibration_error is None
                else str(model.metrics.expected_calibration_error)
            ),
        },
        "policy": {
            "policy_version": model.policy.policy_version,
            "training_evidence_classes": [
                value.value for value in model.policy.training_evidence_classes
            ],
            "validation_evidence_classes": [
                value.value for value in model.policy.validation_evidence_classes
            ],
            "minimum_training_n": model.policy.minimum_training_n,
            "minimum_validation_n": model.policy.minimum_validation_n,
            "minimum_bucket_training_n": (
                model.policy.minimum_bucket_training_n
            ),
            "maximum_brier_score": str(model.policy.maximum_brier_score),
            "maximum_expected_calibration_error": str(
                model.policy.maximum_expected_calibration_error
            ),
            "require_no_worse_than_base_rate_brier": (
                model.policy.require_no_worse_than_base_rate_brier
            ),
        },
    }


def _with_identity(
    model: CalibratedProbabilityModel,
) -> CalibratedProbabilityModel:
    payload = _identity_payload(model)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    identity = hashlib.sha256(canonical.encode()).hexdigest()
    return replace(model, model_identity=identity)


def build_probability_calibration(
    evaluated_signals: tuple[EvaluatedSignal, ...],
    *,
    training_cutoff_ms: int,
    policy: CalibrationPolicy = CalibrationPolicy(),
) -> CalibratedProbabilityModel:
    if training_cutoff_ms < 0:
        raise ValueError("training cutoff must be non-negative")

    decisive = tuple(
        item
        for item in evaluated_signals
        if _decisive_label(item) is not None
    )
    training = tuple(
        item
        for item in decisive
        if item.outcome.evidence_class in policy.training_evidence_classes
        and item.decision.as_of_ms <= training_cutoff_ms
        and item.outcome.evaluated_as_of_ms <= training_cutoff_ms
    )
    validation = tuple(
        item
        for item in decisive
        if item.outcome.evidence_class in policy.validation_evidence_classes
        and item.decision.as_of_ms > training_cutoff_ms
    )

    trained_through = (
        None
        if not training
        else max(item.outcome.evaluated_as_of_ms for item in training)
    )
    validated_through = (
        None
        if not validation
        else max(item.outcome.evaluated_as_of_ms for item in validation)
    )

    counts: dict[ConfluenceScoreBucket, tuple[int, int]] = {}
    for item in training:
        bucket = _bucket(item)
        n, success = counts.get(bucket, (0, 0))
        label = _decisive_label(item)
        assert label is not None
        counts[bucket] = (n + 1, success + label)

    bucket_probabilities = tuple(
        BucketProbability(
            bucket=bucket,
            training_n=n,
            success_n=success,
            # Deterministic Beta(1,1) smoothing avoids 0/1 certainty.
            probability=_q(
                Decimal(success + 1) / Decimal(n + 2)
            ),
        )
        for bucket, (n, success) in sorted(
            counts.items(),
            key=lambda pair: pair[0].value,
        )
    )
    probability_by_bucket = {
        item.bucket: item.probability
        for item in bucket_probabilities
    }

    empty_metrics = ProbabilityCalibrationMetrics(
        validation_n=0,
        validation_success_n=0,
        validation_base_rate=None,
        brier_score=None,
        base_rate_brier_score=None,
        expected_calibration_error=None,
    )

    def emit(
        *,
        status: ProbabilityCalibrationStatus,
        reason: ProbabilityCalibrationReason,
        metrics: ProbabilityCalibrationMetrics,
    ) -> CalibratedProbabilityModel:
        draft = CalibratedProbabilityModel(
            model_identity="0" * 64,
            model_version=policy.policy_version,
            event=policy.event,
            training_cutoff_ms=training_cutoff_ms,
            trained_through_outcome_ms=trained_through,
            validated_through_outcome_ms=validated_through,
            status=status,
            reason=reason,
            training_n=len(training),
            bucket_probabilities=bucket_probabilities,
            metrics=metrics,
            policy=policy,
        )
        return _with_identity(draft)

    if len(training) < policy.minimum_training_n:
        return emit(
            status=ProbabilityCalibrationStatus.NOT_CALIBRATED,
            reason=(
                ProbabilityCalibrationReason.INSUFFICIENT_TRAINING_SAMPLE
            ),
            metrics=empty_metrics,
        )

    if len(validation) < policy.minimum_validation_n:
        return emit(
            status=ProbabilityCalibrationStatus.NOT_CALIBRATED,
            reason=(
                ProbabilityCalibrationReason.INSUFFICIENT_VALIDATION_SAMPLE
            ),
            metrics=empty_metrics,
        )

    validation_buckets = {_bucket(item) for item in validation}
    unsupported = {
        bucket
        for bucket in validation_buckets
        if counts.get(bucket, (0, 0))[0]
        < policy.minimum_bucket_training_n
    }
    if unsupported:
        return emit(
            status=ProbabilityCalibrationStatus.NOT_CALIBRATED,
            reason=ProbabilityCalibrationReason.MISSING_BUCKET_SUPPORT,
            metrics=empty_metrics,
        )

    labels: list[Decimal] = []
    predictions: list[Decimal] = []
    bucket_validation: dict[
        ConfluenceScoreBucket, list[tuple[Decimal, Decimal]]
    ] = {}
    for item in validation:
        label_int = _decisive_label(item)
        assert label_int is not None
        label = Decimal(label_int)
        prediction = probability_by_bucket[_bucket(item)]
        labels.append(label)
        predictions.append(prediction)
        bucket_validation.setdefault(_bucket(item), []).append(
            (prediction, label)
        )

    base_rate = _q(_mean(labels))
    brier = _q(
        _mean(
            [
                (prediction - label) ** 2
                for prediction, label in zip(
                    predictions, labels, strict=True
                )
            ]
        )
    )
    base_rate_brier = _q(
        _mean([(base_rate - label) ** 2 for label in labels])
    )

    ece = Decimal(0)
    for observations in bucket_validation.values():
        predicted = _mean([item[0] for item in observations])
        observed = _mean([item[1] for item in observations])
        weight = Decimal(len(observations)) / Decimal(len(validation))
        ece += weight * abs(predicted - observed)
    ece = _q(ece)

    metrics = ProbabilityCalibrationMetrics(
        validation_n=len(validation),
        validation_success_n=sum(int(value) for value in labels),
        validation_base_rate=base_rate,
        brier_score=brier,
        base_rate_brier_score=base_rate_brier,
        expected_calibration_error=ece,
    )

    if brier > policy.maximum_brier_score or (
        policy.require_no_worse_than_base_rate_brier
        and brier > base_rate_brier
    ):
        return emit(
            status=ProbabilityCalibrationStatus.NOT_CALIBRATED,
            reason=ProbabilityCalibrationReason.BRIER_GATE_FAILED,
            metrics=metrics,
        )
    if ece > policy.maximum_expected_calibration_error:
        return emit(
            status=ProbabilityCalibrationStatus.NOT_CALIBRATED,
            reason=(
                ProbabilityCalibrationReason.CALIBRATION_ERROR_GATE_FAILED
            ),
            metrics=metrics,
        )

    return emit(
        status=ProbabilityCalibrationStatus.CALIBRATED,
        reason=ProbabilityCalibrationReason.ACCEPTED,
        metrics=metrics,
    )


def estimate_probability(
    model: CalibratedProbabilityModel,
    *,
    confluence_score: Decimal,
) -> ProbabilityEstimate:
    bucket = confluence_score_bucket(confluence_score)
    probability_by_bucket = {
        item.bucket: item
        for item in model.bucket_probabilities
    }
    match = probability_by_bucket.get(bucket)

    if (
        model.status is ProbabilityCalibrationStatus.CALIBRATED
        and match is not None
        and match.training_n >= model.policy.minimum_bucket_training_n
    ):
        return ProbabilityEstimate(
            model_identity=model.model_identity,
            event=model.event,
            confluence_score_bucket=bucket,
            probability=match.probability,
            status=ProbabilityCalibrationStatus.CALIBRATED,
            reason=ProbabilityCalibrationReason.ACCEPTED,
            training_n=match.training_n,
            validation_n=model.metrics.validation_n,
        )

    reason = (
        model.reason
        if model.status is ProbabilityCalibrationStatus.NOT_CALIBRATED
        else ProbabilityCalibrationReason.MISSING_BUCKET_SUPPORT
    )
    return ProbabilityEstimate(
        model_identity=model.model_identity,
        event=model.event,
        confluence_score_bucket=bucket,
        probability=None,
        status=ProbabilityCalibrationStatus.NOT_CALIBRATED,
        reason=reason,
        training_n=0 if match is None else match.training_n,
        validation_n=model.metrics.validation_n,
    )
