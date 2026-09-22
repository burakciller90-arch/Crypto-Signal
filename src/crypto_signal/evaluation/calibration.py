from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from crypto_signal.evaluation.aggregate import confluence_score_bucket
from crypto_signal.evaluation.models import (
    ConfluenceScoreBucket,
    EvaluatedSignal,
)
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import (
    SignalDecision,
    SignalDirection,
    SignalState,
)

_SUCCESS_STATES = {
    OutcomeState.SUCCESS_TP1,
    OutcomeState.SUCCESS_TP2,
    OutcomeState.SUCCESS_TP3,
}


class CalibrationStatus(StrEnum):
    ACCEPTED = "accepted"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    INSUFFICIENT_CLASS_SUPPORT = "insufficient_class_support"
    INSUFFICIENT_BUCKET_SUPPORT = "insufficient_bucket_support"
    FAILED_BRIER_SKILL = "failed_brier_skill"
    FAILED_CALIBRATION_ERROR = "failed_calibration_error"


class ProbabilitySemantic(StrEnum):
    CALIBRATED_TARGET_SUCCESS_BEFORE_FAIL_SL = (
        "calibrated_target_success_before_fail_sl"
    )


@dataclass(frozen=True, slots=True)
class CalibrationScope:
    symbol: str
    timeframe: str
    direction: SignalDirection
    setup_type: str
    max_holding_bars: int

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("calibration scope symbol must be non-empty")
        if not self.timeframe.strip():
            raise ValueError("calibration scope timeframe must be non-empty")
        if not self.setup_type.strip():
            raise ValueError("calibration scope setup type must be non-empty")
        if self.direction is SignalDirection.NONE:
            raise ValueError("calibration scope direction must be directional")
        if self.max_holding_bars <= 0:
            raise ValueError("calibration scope max holding bars must be positive")


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    score_bucket: ConfluenceScoreBucket
    train_n: int
    train_success_n: int
    probability: Decimal

    def __post_init__(self) -> None:
        if self.train_n <= 0:
            raise ValueError("calibration bin train_n must be positive")
        if not 0 <= self.train_success_n <= self.train_n:
            raise ValueError("calibration bin success count is invalid")
        if not Decimal(0) <= self.probability <= Decimal(1):
            raise ValueError("calibration bin probability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class HoldoutPrediction:
    signal_freeze_identity: str
    score_bucket: ConfluenceScoreBucket
    probability: Decimal
    observed_success: bool
    decision_as_of_ms: int
    outcome_evaluated_as_of_ms: int

    def __post_init__(self) -> None:
        if len(self.signal_freeze_identity) != 64:
            raise ValueError("holdout prediction signal identity must be SHA256")
        if not Decimal(0) <= self.probability <= Decimal(1):
            raise ValueError("holdout prediction probability must be between 0 and 1")
        if self.decision_as_of_ms < 0 or self.outcome_evaluated_as_of_ms < 0:
            raise ValueError("holdout prediction timestamps must be non-negative")
        if self.outcome_evaluated_as_of_ms < self.decision_as_of_ms:
            raise ValueError("outcome cannot precede decision")


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    model_version: str
    scope: CalibrationScope
    status: CalibrationStatus
    semantic: ProbabilitySemantic
    train_n: int
    holdout_n: int
    train_success_n: int
    holdout_success_n: int
    minimum_train_n: int
    minimum_holdout_n: int
    minimum_class_n: int
    minimum_bucket_train_n: int
    max_expected_calibration_error: Decimal
    minimum_brier_skill: Decimal
    train_base_rate: Decimal | None
    brier_score: Decimal | None
    baseline_brier_score: Decimal | None
    brier_skill_score: Decimal | None
    expected_calibration_error: Decimal | None
    trained_through_as_of_ms: int | None
    evaluated_through_as_of_ms: int | None
    bins: tuple[CalibrationBin, ...]
    holdout_predictions: tuple[HoldoutPrediction, ...]

    def __post_init__(self) -> None:
        if not self.model_version.strip():
            raise ValueError("calibration model version must be non-empty")
        counts = (
            self.train_n,
            self.holdout_n,
            self.train_success_n,
            self.holdout_success_n,
            self.minimum_train_n,
            self.minimum_holdout_n,
            self.minimum_class_n,
            self.minimum_bucket_train_n,
        )
        if any(value < 0 for value in counts):
            raise ValueError("calibration counts must be non-negative")
        if self.minimum_train_n <= 0 or self.minimum_holdout_n <= 0:
            raise ValueError("minimum sample thresholds must be positive")
        if self.minimum_class_n <= 0 or self.minimum_bucket_train_n <= 0:
            raise ValueError("minimum support thresholds must be positive")
        if self.train_success_n > self.train_n:
            raise ValueError("train success count exceeds train sample")
        if self.holdout_success_n > self.holdout_n:
            raise ValueError("holdout success count exceeds holdout sample")
        if not Decimal(0) <= self.max_expected_calibration_error <= Decimal(1):
            raise ValueError("max calibration error must be between 0 and 1")
        if self.minimum_brier_skill > Decimal(1):
            raise ValueError("minimum brier skill cannot exceed 1")
        for value in (
            self.train_base_rate,
            self.brier_score,
            self.baseline_brier_score,
            self.expected_calibration_error,
        ):
            if value is not None and not Decimal(0) <= value <= Decimal(1):
                raise ValueError("calibration metric must be between 0 and 1")
        if self.train_n == 0 and self.trained_through_as_of_ms is not None:
            raise ValueError("empty train set cannot have trained-through timestamp")
        if self.holdout_n == 0 and self.evaluated_through_as_of_ms is not None:
            raise ValueError("empty holdout cannot have evaluated-through timestamp")
        if len(self.holdout_predictions) not in {0, self.holdout_n}:
            raise ValueError("holdout predictions must cover all holdout rows or none")
        if self.status is CalibrationStatus.ACCEPTED:
            required = (
                self.train_base_rate,
                self.brier_score,
                self.baseline_brier_score,
                self.brier_skill_score,
                self.expected_calibration_error,
            )
            if any(value is None for value in required):
                raise ValueError("accepted calibration requires all diagnostics")
            if not self.bins:
                raise ValueError("accepted calibration requires fitted bins")
            if len(self.holdout_predictions) != self.holdout_n:
                raise ValueError("accepted calibration requires holdout predictions")


@dataclass(frozen=True, slots=True)
class CalibratedProbability:
    model_version: str
    semantic: ProbabilitySemantic
    scope: CalibrationScope
    score_bucket: ConfluenceScoreBucket
    probability: Decimal
    train_n: int
    holdout_n: int
    brier_score: Decimal
    brier_skill_score: Decimal
    expected_calibration_error: Decimal
    trained_through_as_of_ms: int
    evaluated_through_as_of_ms: int

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.probability <= Decimal(1):
            raise ValueError("calibrated probability must be between 0 and 1")


def _is_decisive_live_forward(item: EvaluatedSignal) -> bool:
    return (
        item.decision.state is SignalState.ACTIVE
        and item.outcome.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
        and item.outcome.resolution_status is OutcomeResolutionStatus.RESOLVED
        and (
            item.outcome.outcome_state in _SUCCESS_STATES
            or item.outcome.outcome_state is OutcomeState.FAIL_SL
        )
    )


def _scope_for(item: EvaluatedSignal) -> CalibrationScope:
    return CalibrationScope(
        symbol=item.decision.symbol,
        timeframe=item.decision.timeframe,
        direction=item.decision.direction,
        setup_type=item.decision.setup_type,
        max_holding_bars=item.outcome.max_holding_bars,
    )


def _observed_success(item: EvaluatedSignal) -> bool:
    state = item.outcome.outcome_state
    if state in _SUCCESS_STATES:
        return True
    if state is OutcomeState.FAIL_SL:
        return False
    raise ValueError("calibration item is not decisive")


def _laplace_probability(success_n: int, total_n: int) -> Decimal:
    if total_n <= 0:
        raise ValueError("Laplace probability requires positive total_n")
    return (Decimal(success_n) + Decimal(1)) / (Decimal(total_n) + Decimal(2))


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values, Decimal(0)) / Decimal(len(values))


def _empty_report(
    *,
    model_version: str,
    scope: CalibrationScope,
    status: CalibrationStatus,
    minimum_train_n: int,
    minimum_holdout_n: int,
    minimum_class_n: int,
    minimum_bucket_train_n: int,
    max_expected_calibration_error: Decimal,
    minimum_brier_skill: Decimal,
    train_n: int = 0,
    holdout_n: int = 0,
    train_success_n: int = 0,
    holdout_success_n: int = 0,
    trained_through_as_of_ms: int | None = None,
    evaluated_through_as_of_ms: int | None = None,
) -> CalibrationReport:
    return CalibrationReport(
        model_version=model_version,
        scope=scope,
        status=status,
        semantic=ProbabilitySemantic.CALIBRATED_TARGET_SUCCESS_BEFORE_FAIL_SL,
        train_n=train_n,
        holdout_n=holdout_n,
        train_success_n=train_success_n,
        holdout_success_n=holdout_success_n,
        minimum_train_n=minimum_train_n,
        minimum_holdout_n=minimum_holdout_n,
        minimum_class_n=minimum_class_n,
        minimum_bucket_train_n=minimum_bucket_train_n,
        max_expected_calibration_error=max_expected_calibration_error,
        minimum_brier_skill=minimum_brier_skill,
        train_base_rate=None,
        brier_score=None,
        baseline_brier_score=None,
        brier_skill_score=None,
        expected_calibration_error=None,
        trained_through_as_of_ms=trained_through_as_of_ms,
        evaluated_through_as_of_ms=evaluated_through_as_of_ms,
        bins=(),
        holdout_predictions=(),
    )


def _fit_scope(
    items: tuple[EvaluatedSignal, ...],
    *,
    model_version: str,
    train_fraction: Decimal,
    minimum_train_n: int,
    minimum_holdout_n: int,
    minimum_class_n: int,
    minimum_bucket_train_n: int,
    max_expected_calibration_error: Decimal,
    minimum_brier_skill: Decimal,
) -> CalibrationReport:
    if not items:
        raise ValueError("calibration scope requires at least one item")
    scope = _scope_for(items[0])
    if any(_scope_for(item) != scope for item in items):
        raise ValueError("calibration scope cannot mix incompatible items")

    ordered = tuple(
        sorted(
            items,
            key=lambda item: (
                item.decision.as_of_ms,
                item.decision.freeze_identity,
            ),
        )
    )
    identities = tuple(item.decision.freeze_identity for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate signal freeze identity in calibration scope")

    total_n = len(ordered)
    if total_n < minimum_train_n + minimum_holdout_n:
        return _empty_report(
            model_version=model_version,
            scope=scope,
            status=CalibrationStatus.INSUFFICIENT_SAMPLE,
            minimum_train_n=minimum_train_n,
            minimum_holdout_n=minimum_holdout_n,
            minimum_class_n=minimum_class_n,
            minimum_bucket_train_n=minimum_bucket_train_n,
            max_expected_calibration_error=max_expected_calibration_error,
            minimum_brier_skill=minimum_brier_skill,
        )

    desired_train_n = int(
        (Decimal(total_n) * train_fraction).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    train_n = min(
        max(desired_train_n, minimum_train_n),
        total_n - minimum_holdout_n,
    )
    train = ordered[:train_n]
    holdout = ordered[train_n:]

    train_success_n = sum(_observed_success(item) for item in train)
    holdout_success_n = sum(_observed_success(item) for item in holdout)
    train_fail_n = len(train) - train_success_n
    holdout_fail_n = len(holdout) - holdout_success_n

    trained_through_as_of_ms = max(item.decision.as_of_ms for item in train)
    evaluated_through_as_of_ms = max(
        item.outcome.evaluated_as_of_ms for item in holdout
    )

    if min(
        train_success_n,
        train_fail_n,
        holdout_success_n,
        holdout_fail_n,
    ) < minimum_class_n:
        return _empty_report(
            model_version=model_version,
            scope=scope,
            status=CalibrationStatus.INSUFFICIENT_CLASS_SUPPORT,
            minimum_train_n=minimum_train_n,
            minimum_holdout_n=minimum_holdout_n,
            minimum_class_n=minimum_class_n,
            minimum_bucket_train_n=minimum_bucket_train_n,
            max_expected_calibration_error=max_expected_calibration_error,
            minimum_brier_skill=minimum_brier_skill,
            train_n=len(train),
            holdout_n=len(holdout),
            train_success_n=train_success_n,
            holdout_success_n=holdout_success_n,
            trained_through_as_of_ms=trained_through_as_of_ms,
            evaluated_through_as_of_ms=evaluated_through_as_of_ms,
        )

    train_by_bucket: dict[ConfluenceScoreBucket, list[EvaluatedSignal]] = (
        defaultdict(list)
    )
    for item in train:
        bucket = confluence_score_bucket(item.decision.agreement.confluence_score)
        train_by_bucket[bucket].append(item)

    holdout_buckets = {
        confluence_score_bucket(item.decision.agreement.confluence_score)
        for item in holdout
    }
    if any(
        len(train_by_bucket[bucket]) < minimum_bucket_train_n
        for bucket in holdout_buckets
    ):
        return _empty_report(
            model_version=model_version,
            scope=scope,
            status=CalibrationStatus.INSUFFICIENT_BUCKET_SUPPORT,
            minimum_train_n=minimum_train_n,
            minimum_holdout_n=minimum_holdout_n,
            minimum_class_n=minimum_class_n,
            minimum_bucket_train_n=minimum_bucket_train_n,
            max_expected_calibration_error=max_expected_calibration_error,
            minimum_brier_skill=minimum_brier_skill,
            train_n=len(train),
            holdout_n=len(holdout),
            train_success_n=train_success_n,
            holdout_success_n=holdout_success_n,
            trained_through_as_of_ms=trained_through_as_of_ms,
            evaluated_through_as_of_ms=evaluated_through_as_of_ms,
        )

    bins: list[CalibrationBin] = []
    probability_by_bucket: dict[ConfluenceScoreBucket, Decimal] = {}
    for bucket in sorted(train_by_bucket, key=lambda item: item.value):
        bucket_items = train_by_bucket[bucket]
        success_n = sum(_observed_success(item) for item in bucket_items)
        probability = _laplace_probability(success_n, len(bucket_items))
        bins.append(
            CalibrationBin(
                score_bucket=bucket,
                train_n=len(bucket_items),
                train_success_n=success_n,
                probability=probability,
            )
        )
        probability_by_bucket[bucket] = probability

    predictions: list[HoldoutPrediction] = []
    squared_errors: list[Decimal] = []
    for item in holdout:
        bucket = confluence_score_bucket(item.decision.agreement.confluence_score)
        probability = probability_by_bucket[bucket]
        observed_success = _observed_success(item)
        observed = Decimal(1) if observed_success else Decimal(0)
        squared_errors.append((probability - observed) ** 2)
        predictions.append(
            HoldoutPrediction(
                signal_freeze_identity=item.decision.freeze_identity,
                score_bucket=bucket,
                probability=probability,
                observed_success=observed_success,
                decision_as_of_ms=item.decision.as_of_ms,
                outcome_evaluated_as_of_ms=item.outcome.evaluated_as_of_ms,
            )
        )

    train_base_rate = Decimal(train_success_n) / Decimal(len(train))
    baseline_errors = tuple(
        (
            train_base_rate
            - (Decimal(1) if _observed_success(item) else Decimal(0))
        )
        ** 2
        for item in holdout
    )
    brier_score = _mean(tuple(squared_errors))
    baseline_brier_score = _mean(baseline_errors)
    brier_skill_score = (
        Decimal(1) - (brier_score / baseline_brier_score)
        if baseline_brier_score > 0
        else Decimal(0)
    )

    holdout_by_bucket: dict[ConfluenceScoreBucket, list[HoldoutPrediction]] = (
        defaultdict(list)
    )
    for prediction in predictions:
        holdout_by_bucket[prediction.score_bucket].append(prediction)

    ece = Decimal(0)
    for bucket_predictions in holdout_by_bucket.values():
        predicted = bucket_predictions[0].probability
        empirical = Decimal(
            sum(item.observed_success for item in bucket_predictions)
        ) / Decimal(len(bucket_predictions))
        weight = Decimal(len(bucket_predictions)) / Decimal(len(predictions))
        ece += weight * abs(predicted - empirical)

    if brier_skill_score < minimum_brier_skill:
        status = CalibrationStatus.FAILED_BRIER_SKILL
    elif ece > max_expected_calibration_error:
        status = CalibrationStatus.FAILED_CALIBRATION_ERROR
    else:
        status = CalibrationStatus.ACCEPTED

    return CalibrationReport(
        model_version=model_version,
        scope=scope,
        status=status,
        semantic=ProbabilitySemantic.CALIBRATED_TARGET_SUCCESS_BEFORE_FAIL_SL,
        train_n=len(train),
        holdout_n=len(holdout),
        train_success_n=train_success_n,
        holdout_success_n=holdout_success_n,
        minimum_train_n=minimum_train_n,
        minimum_holdout_n=minimum_holdout_n,
        minimum_class_n=minimum_class_n,
        minimum_bucket_train_n=minimum_bucket_train_n,
        max_expected_calibration_error=max_expected_calibration_error,
        minimum_brier_skill=minimum_brier_skill,
        train_base_rate=train_base_rate,
        brier_score=brier_score,
        baseline_brier_score=baseline_brier_score,
        brier_skill_score=brier_skill_score,
        expected_calibration_error=ece,
        trained_through_as_of_ms=trained_through_as_of_ms,
        evaluated_through_as_of_ms=evaluated_through_as_of_ms,
        bins=tuple(bins),
        holdout_predictions=tuple(predictions),
    )


def build_score_bucket_calibrations(
    items: tuple[EvaluatedSignal, ...],
    *,
    model_version: str = "score-bucket-laplace-v1",
    train_fraction: Decimal = Decimal("0.70"),
    minimum_train_n: int = 60,
    minimum_holdout_n: int = 30,
    minimum_class_n: int = 5,
    minimum_bucket_train_n: int = 10,
    max_expected_calibration_error: Decimal = Decimal("0.12"),
    minimum_brier_skill: Decimal = Decimal(0),
) -> tuple[CalibrationReport, ...]:
    if not model_version.strip():
        raise ValueError("calibration model version must be non-empty")
    if not Decimal(0) < train_fraction < Decimal(1):
        raise ValueError("train_fraction must be between 0 and 1")
    if minimum_train_n <= 0 or minimum_holdout_n <= 0:
        raise ValueError("minimum sample thresholds must be positive")
    if minimum_class_n <= 0 or minimum_bucket_train_n <= 0:
        raise ValueError("minimum support thresholds must be positive")
    if not Decimal(0) <= max_expected_calibration_error <= Decimal(1):
        raise ValueError("max calibration error must be between 0 and 1")
    if minimum_brier_skill > Decimal(1):
        raise ValueError("minimum brier skill cannot exceed 1")

    groups: dict[CalibrationScope, list[EvaluatedSignal]] = defaultdict(list)
    for item in items:
        if _is_decisive_live_forward(item):
            groups[_scope_for(item)].append(item)

    return tuple(
        _fit_scope(
            tuple(groups[scope]),
            model_version=model_version,
            train_fraction=train_fraction,
            minimum_train_n=minimum_train_n,
            minimum_holdout_n=minimum_holdout_n,
            minimum_class_n=minimum_class_n,
            minimum_bucket_train_n=minimum_bucket_train_n,
            max_expected_calibration_error=max_expected_calibration_error,
            minimum_brier_skill=minimum_brier_skill,
        )
        for scope in sorted(
            groups,
            key=lambda value: (
                value.symbol,
                value.timeframe,
                value.direction.value,
                value.setup_type,
                value.max_holding_bars,
            ),
        )
    )


def calibrated_probability_for_decision(
    decision: SignalDecision,
    *,
    max_holding_bars: int,
    reports: tuple[CalibrationReport, ...],
) -> CalibratedProbability | None:
    if decision.state is not SignalState.ACTIVE:
        return None
    scope = CalibrationScope(
        symbol=decision.symbol,
        timeframe=decision.timeframe,
        direction=decision.direction,
        setup_type=decision.setup_type,
        max_holding_bars=max_holding_bars,
    )
    report = next(
        (
            item
            for item in reports
            if item.scope == scope and item.status is CalibrationStatus.ACCEPTED
        ),
        None,
    )
    if report is None:
        return None

    bucket = confluence_score_bucket(decision.agreement.confluence_score)
    calibration_bin = next(
        (item for item in report.bins if item.score_bucket is bucket),
        None,
    )
    if calibration_bin is None:
        return None

    assert report.brier_score is not None
    assert report.brier_skill_score is not None
    assert report.expected_calibration_error is not None
    assert report.trained_through_as_of_ms is not None
    assert report.evaluated_through_as_of_ms is not None

    return CalibratedProbability(
        model_version=report.model_version,
        semantic=report.semantic,
        scope=report.scope,
        score_bucket=bucket,
        probability=calibration_bin.probability,
        train_n=report.train_n,
        holdout_n=report.holdout_n,
        brier_score=report.brier_score,
        brier_skill_score=report.brier_skill_score,
        expected_calibration_error=report.expected_calibration_error,
        trained_through_as_of_ms=report.trained_through_as_of_ms,
        evaluated_through_as_of_ms=report.evaluated_through_as_of_ms,
    )
