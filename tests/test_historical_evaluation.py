from __future__ import annotations

import hashlib
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.evaluation.aggregate import (
    aggregate_segments,
    confluence_score_bucket,
    realized_shadow_r,
)
from crypto_signal.evaluation.models import (
    ConfluenceScoreBucket,
    EvaluatedSignal,
    HistoricalFrequencySemantic,
    PromotionSemantic,
)
from crypto_signal.outcomes.evaluator import compute_outcome_identity
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeAmbiguityReason,
    OutcomeCoverageStatus,
    OutcomeEvaluation,
    OutcomeNotEvaluableReason,
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


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def decision(
    seed: str,
    *,
    score: Decimal = Decimal("66.67"),
    setup_type: str = "gartley",
    direction: SignalDirection = SignalDirection.BULLISH,
    source_methodology: MethodologyKind = MethodologyKind.HARMONIC,
    target_rr: tuple[Decimal, ...] = (
        Decimal(1),
        Decimal(2),
        Decimal(3),
    ),
    as_of_ms: int = 1_000,
) -> SignalDecision:
    if direction is SignalDirection.BULLISH:
        target_prices = (Decimal(110), Decimal(120), Decimal(130))
        invalidation = Decimal(90)
    else:
        target_prices = (Decimal(92), Decimal(82), Decimal(72))
        invalidation = Decimal(112)

    targets = tuple(
        RiskRewardTarget(
            label=f"target_{index + 1}",
            target_price=price,
            reference_rr=rr,
        )
        for index, (price, rr) in enumerate(
            zip(target_prices, target_rr, strict=True)
        )
    )
    geometry = SignalGeometry(
        source_evidence_id=f"evidence-{seed}",
        source_methodology=source_methodology,
        entry_zone=PriceZone(Decimal(100), Decimal(102)),
        entry_reference_price=Decimal(101),
        entry_reference_model=(
            EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
        ),
        invalidation_price=invalidation,
        invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
        targets=targets,
    )
    return SignalDecision(
        freeze_identity=digest(seed),
        signal_version="signal-v1/1",
        state=SignalState.ACTIVE,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=as_of_ms,
        direction=direction,
        setup_type=setup_type,
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
                methodology=source_methodology,
                version=f"{source_methodology.value}/test",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=(),
        evidence_summary=(),
    )


def outcome(
    signal: SignalDecision,
    *,
    evidence_class: EvidenceClass = EvidenceClass.RETROSPECTIVE,
    evaluated_as_of_ms: int = 2_000,
    state: OutcomeState | None = OutcomeState.SUCCESS_TP1,
    resolution: OutcomeResolutionStatus = OutcomeResolutionStatus.RESOLVED,
) -> OutcomeEvaluation:
    if resolution is OutcomeResolutionStatus.PENDING:
        state = None
        not_evaluable_reason = None
        ambiguity_reason = None
        coverage = OutcomeCoverageStatus.NO_NEW_EVIDENCE
        observed = 0
    elif resolution is OutcomeResolutionStatus.NOT_EVALUABLE:
        state = OutcomeState.NOT_EVALUABLE
        not_evaluable_reason = OutcomeNotEvaluableReason.DATA_GAPS
        ambiguity_reason = None
        coverage = OutcomeCoverageStatus.INCOMPLETE_GAPS
        observed = 0
    else:
        not_evaluable_reason = None
        ambiguity_reason = (
            OutcomeAmbiguityReason.ENTRY_AND_TARGET_SAME_CANDLE
            if state is OutcomeState.AMBIGUOUS
            else None
        )
        coverage = OutcomeCoverageStatus.COMPLETE
        observed = 1

    if state in {
        OutcomeState.SUCCESS_TP1,
        OutcomeState.SUCCESS_TP2,
        OutcomeState.SUCCESS_TP3,
        OutcomeState.FAIL_SL,
        OutcomeState.AMBIGUOUS,
        OutcomeState.TIMEOUT,
        OutcomeState.CANCELLED,
    }:
        entry_observed = True
        entry_identity = ("bybit", "spot", "BTCUSDT", "15m", 1_800)
    else:
        entry_observed = False
        entry_identity = None

    target_index = (
        0
        if state is None
        else {
            OutcomeState.SUCCESS_TP1: 1,
            OutcomeState.SUCCESS_TP2: 2,
            OutcomeState.SUCCESS_TP3: 3,
        }.get(state, 0)
    )

    draft = OutcomeEvaluation(
        outcome_identity="0" * 64,
        signal_freeze_identity=signal.freeze_identity,
        evidence_class=evidence_class,
        evaluated_as_of_ms=evaluated_as_of_ms,
        resolution_status=resolution,
        outcome_state=state,
        signal_initial_state=signal.state,
        coverage_status=coverage,
        max_holding_bars=4,
        expected_bar_count=1 if resolution is not OutcomeResolutionStatus.PENDING else 0,
        observed_bar_count=observed,
        missing_open_times_ms=(
            (1_800,)
            if resolution is OutcomeResolutionStatus.NOT_EVALUABLE
            else ()
        ),
        skipped_partial_decision_bucket=True,
        entry_observed=entry_observed,
        entry_candle_identity=entry_identity,
        highest_target_index=target_index,
        outcome_candle_identity=(
            None
            if state is None or state is OutcomeState.NOT_EVALUABLE
            else ("bybit", "spot", "BTCUSDT", "15m", 2_700)
        ),
        ambiguity_reason=ambiguity_reason,
        not_evaluable_reason=not_evaluable_reason,
    )
    return replace(
        draft,
        outcome_identity=compute_outcome_identity(draft),
    )


def evaluated(
    seed: str,
    *,
    state: OutcomeState | None = OutcomeState.SUCCESS_TP1,
    resolution: OutcomeResolutionStatus = OutcomeResolutionStatus.RESOLVED,
    evidence_class: EvidenceClass = EvidenceClass.RETROSPECTIVE,
    evaluated_as_of_ms: int = 2_000,
    score: Decimal = Decimal("66.67"),
    as_of_ms: int = 1_000,
    regime_label: str | None = None,
) -> EvaluatedSignal:
    signal = decision(seed, score=score, as_of_ms=as_of_ms)
    return EvaluatedSignal(
        decision=signal,
        outcome=outcome(
            signal,
            state=state,
            resolution=resolution,
            evidence_class=evidence_class,
            evaluated_as_of_ms=evaluated_as_of_ms,
        ),
        regime_label=regime_label,
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (Decimal(0), ConfluenceScoreBucket.SCORE_0),
        (Decimal("0.01"), ConfluenceScoreBucket.SCORE_GT_0_LE_33_33),
        (Decimal("33.33"), ConfluenceScoreBucket.SCORE_GT_0_LE_33_33),
        (
            Decimal("33.34"),
            ConfluenceScoreBucket.SCORE_GT_33_33_LE_66_67,
        ),
        (
            Decimal("66.67"),
            ConfluenceScoreBucket.SCORE_GT_33_33_LE_66_67,
        ),
        (
            Decimal("66.68"),
            ConfluenceScoreBucket.SCORE_GT_66_67_LE_100,
        ),
        (Decimal(100), ConfluenceScoreBucket.SCORE_GT_66_67_LE_100),
    ],
)
def test_confluence_score_bucket_boundaries(
    score: Decimal,
    expected: ConfluenceScoreBucket,
) -> None:
    assert confluence_score_bucket(score) is expected


def test_shadow_r_uses_frozen_target_rr_and_fail_sl_is_minus_one() -> None:
    tp2 = evaluated("tp2", state=OutcomeState.SUCCESS_TP2)
    fail = evaluated("fail", state=OutcomeState.FAIL_SL)
    ambiguous = evaluated("amb", state=OutcomeState.AMBIGUOUS)

    assert realized_shadow_r(tp2) == Decimal(2)
    assert realized_shadow_r(fail) == Decimal(-1)
    assert realized_shadow_r(ambiguous) is None


def test_evidence_classes_never_merge_into_one_segment() -> None:
    retrospective = evaluated(
        "retro",
        evidence_class=EvidenceClass.RETROSPECTIVE,
    )
    live = evaluated(
        "live",
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
    )

    result = aggregate_segments((live, retrospective))

    assert len(result) == 2
    assert {
        item.key.evidence_class
        for item in result
    } == {
        EvidenceClass.RETROSPECTIVE,
        EvidenceClass.LIVE_UNTOUCHED_FORWARD,
    }
    assert all(item.total_n == 1 for item in result)


def test_segment_counts_do_not_reclassify_non_decisive_outcomes() -> None:
    items = (
        evaluated("tp1", state=OutcomeState.SUCCESS_TP1),
        evaluated("tp2", state=OutcomeState.SUCCESS_TP2),
        evaluated("fail", state=OutcomeState.FAIL_SL),
        evaluated("amb", state=OutcomeState.AMBIGUOUS),
        evaluated("timeout", state=OutcomeState.TIMEOUT),
        evaluated("cancel", state=OutcomeState.CANCELLED),
        evaluated("invalid", state=OutcomeState.INVALIDATED),
        evaluated(
            "pending",
            state=None,
            resolution=OutcomeResolutionStatus.PENDING,
        ),
        evaluated(
            "not-eval",
            state=OutcomeState.NOT_EVALUABLE,
            resolution=OutcomeResolutionStatus.NOT_EVALUABLE,
        ),
    )

    (metrics,) = aggregate_segments(items)

    assert metrics.total_n == 9
    assert metrics.pending_n == 1
    assert metrics.resolved_n == 7
    assert metrics.not_evaluable_n == 1
    assert metrics.success_n == 2
    assert metrics.fail_sl_n == 1
    assert metrics.ambiguous_n == 1
    assert metrics.timeout_n == 1
    assert metrics.cancelled_n == 1
    assert metrics.invalidated_n == 1
    assert metrics.decisive_n == 3
    assert metrics.r_evaluable_n == 3
    assert metrics.historical_success_fraction == Decimal(2) / Decimal(3)
    assert (
        metrics.historical_frequency_semantic
        is HistoricalFrequencySemantic.DESCRIPTIVE_FREQUENCY_NOT_PROBABILITY
    )


def test_r_statistics_are_chronological_and_max_drawdown_is_peak_to_trough() -> None:
    items = (
        evaluated(
            "fourth",
            state=OutcomeState.FAIL_SL,
            evaluated_as_of_ms=5_000,
            as_of_ms=1_400,
        ),
        evaluated(
            "second",
            state=OutcomeState.FAIL_SL,
            evaluated_as_of_ms=3_000,
            as_of_ms=1_200,
        ),
        evaluated(
            "first",
            state=OutcomeState.SUCCESS_TP1,
            evaluated_as_of_ms=2_000,
            as_of_ms=1_100,
        ),
        evaluated(
            "third",
            state=OutcomeState.SUCCESS_TP2,
            evaluated_as_of_ms=4_000,
            as_of_ms=1_300,
        ),
    )

    (metrics,) = aggregate_segments(items)

    assert [item.value_r for item in metrics.r_observations] == [
        Decimal(1),
        Decimal(-1),
        Decimal(2),
        Decimal(-1),
    ]
    assert metrics.average_r == Decimal("0.25")
    assert metrics.median_r == Decimal(0)
    assert metrics.cumulative_r == Decimal(1)
    assert metrics.max_drawdown_r == Decimal(1)
    assert metrics.min_r == Decimal(-1)
    assert metrics.max_r == Decimal(2)


def test_promotion_threshold_is_visibility_policy_not_significance() -> None:
    items = (
        evaluated("one", state=OutcomeState.SUCCESS_TP1),
        evaluated("two", state=OutcomeState.FAIL_SL),
        evaluated("three", state=OutcomeState.SUCCESS_TP2),
    )

    (default_metrics,) = aggregate_segments(items)
    (lower_threshold,) = aggregate_segments(
        items,
        minimum_decisive_sample_size_for_promotion=3,
    )

    assert default_metrics.promotion_eligible is False
    assert default_metrics.minimum_decisive_sample_size_for_promotion == 30
    assert lower_threshold.promotion_eligible is True
    assert (
        lower_threshold.promotion_semantic
        is PromotionSemantic.PRODUCT_VISIBILITY_POLICY_NOT_STATISTICAL_SIGNIFICANCE
    )


def test_duplicate_signal_snapshot_is_rejected() -> None:
    item = evaluated("duplicate")

    with pytest.raises(ValueError, match="duplicate signal freeze identity"):
        aggregate_segments((item, item))


def test_regime_label_is_nullable_but_segmented_when_present() -> None:
    none = evaluated("none-regime")
    trend = evaluated("trend-regime", regime_label="trend")

    result = aggregate_segments((none, trend))

    assert len(result) == 2
    assert {item.key.regime_label for item in result} == {None, "trend"}
