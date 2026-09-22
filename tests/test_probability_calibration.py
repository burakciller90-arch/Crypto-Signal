from __future__ import annotations

import hashlib
from dataclasses import replace
from decimal import Decimal

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.models import EvaluatedSignal
from crypto_signal.evaluation.probability_calibration import (
    CalibrationPolicy,
    ProbabilityCalibrationReason,
    ProbabilityCalibrationStatus,
    build_probability_calibration,
    estimate_probability,
)
from crypto_signal.outcomes.evaluator import compute_outcome_identity
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeCoverageStatus,
    OutcomeEvaluation,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _item(
    seed: str,
    *,
    as_of_ms: int,
    evaluated_as_of_ms: int,
    evidence_class: EvidenceClass,
    success: bool,
    score: Decimal = Decimal("66.67"),
) -> EvaluatedSignal:
    decision = SignalDecision(
        freeze_identity=_digest(seed),
        signal_version="signal-v1/1",
        state=SignalState.ACTIVE,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=as_of_ms,
        direction=SignalDirection.BULLISH,
        setup_type="calibration_fixture",
        geometry=SignalGeometry(
            source_evidence_id=f"evidence-{seed}",
            source_methodology=MethodologyKind.PRICE_ACTION,
            entry_zone=PriceZone(Decimal(100), Decimal(102)),
            entry_reference_price=Decimal(101),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=Decimal(95),
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(
                RiskRewardTarget(
                    label="tp1",
                    target_price=Decimal(110),
                    reference_rr=Decimal(1),
                ),
            ),
        ),
        agreement=SignalAgreementSummary(
            confluence_score=score,
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"evidence-{seed}",),
        methodology_versions=(
            MethodologyVersionRef(
                methodology=MethodologyKind.PRICE_ACTION,
                version="price-action/test",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=(),
        evidence_summary=(),
    )
    state = OutcomeState.SUCCESS_TP1 if success else OutcomeState.FAIL_SL
    draft = OutcomeEvaluation(
        outcome_identity="0" * 64,
        signal_freeze_identity=decision.freeze_identity,
        evidence_class=evidence_class,
        evaluated_as_of_ms=evaluated_as_of_ms,
        resolution_status=OutcomeResolutionStatus.RESOLVED,
        outcome_state=state,
        signal_initial_state=SignalState.ACTIVE,
        coverage_status=OutcomeCoverageStatus.COMPLETE,
        max_holding_bars=4,
        expected_bar_count=1,
        observed_bar_count=1,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=True,
        entry_observed=True,
        entry_candle_identity=("bybit", "spot", "BTCUSDT", "15m", as_of_ms),
        highest_target_index=1 if success else 0,
        outcome_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            evaluated_as_of_ms,
        ),
        ambiguity_reason=None,
        not_evaluable_reason=None,
    )
    outcome = replace(
        draft,
        outcome_identity=compute_outcome_identity(draft),
    )
    return EvaluatedSignal(decision=decision, outcome=outcome)


def _accepted_fixture() -> tuple[EvaluatedSignal, ...]:
    training = tuple(
        _item(
            f"train-success-{index}",
            as_of_ms=1_000 + index,
            evaluated_as_of_ms=2_000 + index,
            evidence_class=EvidenceClass.WALK_FORWARD,
            success=True,
        )
        for index in range(21)
    ) + tuple(
        _item(
            f"train-fail-{index}",
            as_of_ms=1_100 + index,
            evaluated_as_of_ms=2_100 + index,
            evidence_class=EvidenceClass.WALK_FORWARD,
            success=False,
        )
        for index in range(9)
    )
    validation = tuple(
        _item(
            f"validation-success-{index}",
            as_of_ms=20_000 + index,
            evaluated_as_of_ms=21_000 + index,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            success=True,
        )
        for index in range(22)
    ) + tuple(
        _item(
            f"validation-fail-{index}",
            as_of_ms=20_100 + index,
            evaluated_as_of_ms=21_100 + index,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            success=False,
        )
        for index in range(10)
    )
    return training + validation


def test_probability_calibration_fails_closed_on_small_training_sample() -> None:
    model = build_probability_calibration(
        (
            _item(
                "small",
                as_of_ms=1_000,
                evaluated_as_of_ms=2_000,
                evidence_class=EvidenceClass.WALK_FORWARD,
                success=True,
            ),
        ),
        training_cutoff_ms=10_000,
    )

    assert model.status is ProbabilityCalibrationStatus.NOT_CALIBRATED
    assert (
        model.reason
        is ProbabilityCalibrationReason.INSUFFICIENT_TRAINING_SAMPLE
    )
    estimate = estimate_probability(
        model,
        confluence_score=Decimal("66.67"),
    )
    assert estimate.probability is None


def test_training_rejects_outcome_that_was_not_available_by_cutoff() -> None:
    items = tuple(
        _item(
            f"future-outcome-{index}",
            as_of_ms=1_000 + index,
            evaluated_as_of_ms=20_000 + index,
            evidence_class=EvidenceClass.WALK_FORWARD,
            success=True,
        )
        for index in range(30)
    )
    model = build_probability_calibration(
        items,
        training_cutoff_ms=10_000,
    )

    assert model.training_n == 0
    assert (
        model.reason
        is ProbabilityCalibrationReason.INSUFFICIENT_TRAINING_SAMPLE
    )


def test_probability_calibration_accepts_true_untouched_validation() -> None:
    model = build_probability_calibration(
        _accepted_fixture(),
        training_cutoff_ms=10_000,
    )

    assert model.status is ProbabilityCalibrationStatus.CALIBRATED
    assert model.reason is ProbabilityCalibrationReason.ACCEPTED
    assert model.training_n == 30
    assert model.metrics.validation_n == 32
    assert model.metrics.brier_score == model.metrics.base_rate_brier_score
    assert model.metrics.expected_calibration_error == Decimal("0.000000")

    estimate = estimate_probability(
        model,
        confluence_score=Decimal("66.67"),
    )
    assert estimate.status is ProbabilityCalibrationStatus.CALIBRATED
    assert estimate.probability == Decimal("0.687500")


def test_probability_calibration_fails_brier_gate_when_forward_flips() -> None:
    training = tuple(
        _item(
            f"high-train-{index}",
            as_of_ms=1_000 + index,
            evaluated_as_of_ms=2_000 + index,
            evidence_class=EvidenceClass.WALK_FORWARD,
            success=index < 27,
        )
        for index in range(30)
    )
    validation = tuple(
        _item(
            f"low-forward-{index}",
            as_of_ms=20_000 + index,
            evaluated_as_of_ms=21_000 + index,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            success=index < 3,
        )
        for index in range(20)
    )
    model = build_probability_calibration(
        training + validation,
        training_cutoff_ms=10_000,
    )

    assert model.status is ProbabilityCalibrationStatus.NOT_CALIBRATED
    assert model.reason is ProbabilityCalibrationReason.BRIER_GATE_FAILED
    assert model.metrics.brier_score is not None
    assert model.metrics.base_rate_brier_score is not None
    assert model.metrics.brier_score > model.metrics.base_rate_brier_score


def test_probability_model_identity_is_permutation_invariant() -> None:
    items = _accepted_fixture()
    first = build_probability_calibration(
        items,
        training_cutoff_ms=10_000,
    )
    second = build_probability_calibration(
        tuple(reversed(items)),
        training_cutoff_ms=10_000,
    )

    assert first == second


def test_training_and_validation_evidence_classes_must_be_disjoint() -> None:
    try:
        CalibrationPolicy(
            training_evidence_classes=(EvidenceClass.WALK_FORWARD,),
            validation_evidence_classes=(EvidenceClass.WALK_FORWARD,),
        )
    except ValueError as exc:
        assert "disjoint" in str(exc)
    else:
        raise AssertionError("overlapping evidence classes must fail closed")
