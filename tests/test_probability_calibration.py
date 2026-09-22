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
from crypto_signal.evaluation.calibration import (
    CalibrationStatus,
    ProbabilitySemantic,
    build_score_bucket_calibrations,
    calibrated_probability_for_decision,
)
from crypto_signal.evaluation.models import EvaluatedSignal
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


def _evaluated(
    seed: str,
    *,
    success: bool,
    score: Decimal,
    as_of_ms: int,
    evidence_class: EvidenceClass = EvidenceClass.LIVE_UNTOUCHED_FORWARD,
    max_holding_bars: int = 8,
) -> EvaluatedSignal:
    geometry = SignalGeometry(
        source_evidence_id=f"evidence-{seed}",
        source_methodology=MethodologyKind.PRICE_ACTION,
        entry_zone=PriceZone(Decimal(100), Decimal(102)),
        entry_reference_price=Decimal(101),
        entry_reference_model=EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION,
        invalidation_price=Decimal(95),
        invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
        targets=(
            RiskRewardTarget(
                label="target_1",
                target_price=Decimal(108),
                reference_rr=Decimal("1.4"),
            ),
        ),
    )
    decision = SignalDecision(
        freeze_identity=_digest(seed),
        signal_version="signal-v1/1",
        state=SignalState.ACTIVE,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="1h",
        as_of_ms=as_of_ms,
        direction=SignalDirection.BULLISH,
        setup_type="breakout",
        geometry=geometry,
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
        evaluated_as_of_ms=as_of_ms + 9_000,
        resolution_status=OutcomeResolutionStatus.RESOLVED,
        outcome_state=state,
        signal_initial_state=SignalState.ACTIVE,
        coverage_status=OutcomeCoverageStatus.COMPLETE,
        max_holding_bars=max_holding_bars,
        expected_bar_count=max_holding_bars,
        observed_bar_count=max_holding_bars,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=False,
        entry_observed=True,
        entry_candle_identity=("bybit", "spot", "BTCUSDT", "1h", as_of_ms + 1_000),
        highest_target_index=1 if success else 0,
        outcome_candle_identity=("bybit", "spot", "BTCUSDT", "1h", as_of_ms + 8_000),
        ambiguity_reason=None,
        not_evaluable_reason=None,
    )
    outcome = replace(
        draft,
        outcome_identity=compute_outcome_identity(draft),
    )
    return EvaluatedSignal(decision=decision, outcome=outcome)


def _patterned_items(
    *,
    reverse_holdout: bool = False,
) -> tuple[EvaluatedSignal, ...]:
    items: list[EvaluatedSignal] = []
    total = 120
    train_cut = 84
    for index in range(total):
        high = index % 2 == 0
        score = Decimal(85) if high else Decimal(20)
        phase_index = index // 2
        if index < train_cut:
            success = phase_index % 5 != 0 if high else phase_index % 5 == 0
        elif reverse_holdout:
            success = phase_index % 5 == 0 if high else phase_index % 5 != 0
        else:
            success = phase_index % 5 != 0 if high else phase_index % 5 == 0
        items.append(
            _evaluated(
                f"signal-{index}",
                success=success,
                score=score,
                as_of_ms=10_000 + index * 10_000,
            )
        )
    return tuple(items)


def test_calibration_accepts_chronological_untouched_forward_model() -> None:
    reports = build_score_bucket_calibrations(_patterned_items())

    assert len(reports) == 1
    report = reports[0]
    assert report.status is CalibrationStatus.ACCEPTED
    assert report.semantic is ProbabilitySemantic.CALIBRATED_TARGET_SUCCESS_BEFORE_FAIL_SL
    assert report.train_n == 84
    assert report.holdout_n == 36
    assert report.brier_score is not None
    assert report.baseline_brier_score is not None
    assert report.brier_skill_score is not None
    assert report.expected_calibration_error is not None
    assert report.brier_score < report.baseline_brier_score
    assert report.brier_skill_score > 0
    assert report.expected_calibration_error <= Decimal("0.12")
    assert report.trained_through_as_of_ms is not None
    assert report.holdout_predictions
    assert (
        report.trained_through_as_of_ms
        < min(item.decision_as_of_ms for item in report.holdout_predictions)
    )
    assert len(report.bins) == 2


def test_calibration_is_order_independent_but_time_split_is_not() -> None:
    items = _patterned_items()
    forward = build_score_bucket_calibrations(items)[0]
    reversed_input = build_score_bucket_calibrations(tuple(reversed(items)))[0]

    assert forward == reversed_input


def test_calibration_rejects_model_that_fails_untouched_holdout() -> None:
    (report,) = build_score_bucket_calibrations(_patterned_items(reverse_holdout=True))

    assert report.status is CalibrationStatus.FAILED_BRIER_SKILL
    assert report.brier_skill_score is not None
    assert report.brier_skill_score < 0


def test_calibration_does_not_promote_small_or_retrospective_samples() -> None:
    small = tuple(
        _evaluated(
            f"small-{index}",
            success=index % 2 == 0,
            score=Decimal(85),
            as_of_ms=1_000 + index * 10_000,
        )
        for index in range(40)
    )
    retrospective = tuple(
        _evaluated(
            f"retro-{index}",
            success=index % 2 == 0,
            score=Decimal(85),
            as_of_ms=1_000 + index * 10_000,
            evidence_class=EvidenceClass.RETROSPECTIVE,
        )
        for index in range(120)
    )

    (small_report,) = build_score_bucket_calibrations(small)
    retro_reports = build_score_bucket_calibrations(retrospective)

    assert small_report.status is CalibrationStatus.INSUFFICIENT_SAMPLE
    assert small_report.brier_score is None
    assert retro_reports == ()


def test_probability_lookup_requires_accepted_matching_scope() -> None:
    items = _patterned_items()
    (report,) = build_score_bucket_calibrations(items)
    decision = items[-1].decision

    probability = calibrated_probability_for_decision(
        decision,
        max_holding_bars=8,
        reports=(report,),
    )
    wrong_horizon = calibrated_probability_for_decision(
        decision,
        max_holding_bars=12,
        reports=(report,),
    )

    assert probability is not None
    assert probability.semantic is ProbabilitySemantic.CALIBRATED_TARGET_SUCCESS_BEFORE_FAIL_SL
    assert Decimal(0) < probability.probability < Decimal(1)
    assert probability.train_n == 84
    assert probability.holdout_n == 36
    assert probability.brier_skill_score > 0
    assert wrong_horizon is None
