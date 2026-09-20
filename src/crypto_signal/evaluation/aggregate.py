from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from statistics import median

from crypto_signal.evaluation.models import (
    ConfluenceScoreBucket,
    EvaluatedSignal,
    HistoricalFrequencySemantic,
    PromotionSemantic,
    SegmentKey,
    SegmentMetrics,
    ShadowRObservation,
)
from crypto_signal.outcomes.models import OutcomeResolutionStatus, OutcomeState
from crypto_signal.signals.models import SignalState

DEFAULT_MINIMUM_DECISIVE_SAMPLE_SIZE_FOR_PROMOTION = 30


_SUCCESS_STATES = {
    OutcomeState.SUCCESS_TP1,
    OutcomeState.SUCCESS_TP2,
    OutcomeState.SUCCESS_TP3,
}
_TARGET_INDEX = {
    OutcomeState.SUCCESS_TP1: 1,
    OutcomeState.SUCCESS_TP2: 2,
    OutcomeState.SUCCESS_TP3: 3,
}


def confluence_score_bucket(score: Decimal) -> ConfluenceScoreBucket:
    if score < 0 or score > 100:
        raise ValueError("confluence score must be between 0 and 100")
    if score == 0:
        return ConfluenceScoreBucket.SCORE_0
    if score <= Decimal("33.33"):
        return ConfluenceScoreBucket.SCORE_GT_0_LE_33_33
    if score <= Decimal("66.67"):
        return ConfluenceScoreBucket.SCORE_GT_33_33_LE_66_67
    return ConfluenceScoreBucket.SCORE_GT_66_67_LE_100


def realized_shadow_r(item: EvaluatedSignal) -> Decimal | None:
    outcome_state = item.outcome.outcome_state
    if outcome_state is None:
        return None

    if outcome_state is OutcomeState.FAIL_SL:
        if item.decision.state is not SignalState.ACTIVE:
            raise ValueError("FAIL_SL requires an initially ACTIVE signal")
        if item.decision.geometry is None:
            raise ValueError("FAIL_SL requires frozen signal geometry")
        return Decimal(-1)

    target_index = _TARGET_INDEX.get(outcome_state)
    if target_index is None:
        return None

    if item.decision.state is not SignalState.ACTIVE:
        raise ValueError("target success requires an initially ACTIVE signal")
    geometry = item.decision.geometry
    if geometry is None:
        raise ValueError("target success requires frozen signal geometry")
    if target_index > len(geometry.targets):
        raise ValueError(
            "outcome target index exceeds frozen signal target structure"
        )
    return geometry.targets[target_index - 1].reference_rr


def segment_key(item: EvaluatedSignal) -> SegmentKey:
    decision = item.decision
    geometry = decision.geometry
    return SegmentKey(
        evidence_class=item.outcome.evidence_class,
        source_methodology=(
            None if geometry is None else geometry.source_methodology
        ),
        setup_type=decision.setup_type,
        exchange=decision.exchange,
        market_type=decision.market_type,
        symbol=decision.symbol,
        timeframe=decision.timeframe,
        signal_direction=decision.direction,
        confluence_score_bucket=confluence_score_bucket(
            decision.agreement.confluence_score
        ),
        regime_label=item.regime_label,
        entry_reference_model=(
            None if geometry is None else geometry.entry_reference_model
        ),
        target_count=(0 if geometry is None else len(geometry.targets)),
        target_labels=(
            ()
            if geometry is None
            else tuple(target.label for target in geometry.targets)
        ),
    )


def _r_observation(item: EvaluatedSignal) -> ShadowRObservation | None:
    value = realized_shadow_r(item)
    if value is None:
        return None
    state = item.outcome.outcome_state
    if state is None:
        raise AssertionError("R-evaluable outcome lost outcome state")
    return ShadowRObservation(
        signal_freeze_identity=item.decision.freeze_identity,
        outcome_state=state,
        outcome_evaluated_as_of_ms=item.outcome.evaluated_as_of_ms,
        decision_as_of_ms=item.decision.as_of_ms,
        value_r=value,
    )


def _max_drawdown(values: Sequence[Decimal]) -> Decimal:
    equity = Decimal(0)
    peak = Decimal(0)
    max_drawdown = Decimal(0)
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = peak - equity
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def _metrics_for_segment(
    key: SegmentKey,
    items: Sequence[EvaluatedSignal],
    *,
    minimum_decisive_sample_size_for_promotion: int,
) -> SegmentMetrics:
    total_n = len(items)
    pending_n = sum(
        item.outcome.resolution_status is OutcomeResolutionStatus.PENDING
        for item in items
    )
    resolved_n = sum(
        item.outcome.resolution_status is OutcomeResolutionStatus.RESOLVED
        for item in items
    )
    not_evaluable_n = sum(
        item.outcome.resolution_status
        is OutcomeResolutionStatus.NOT_EVALUABLE
        for item in items
    )
    states = [item.outcome.outcome_state for item in items]
    success_n = sum(state in _SUCCESS_STATES for state in states)
    fail_sl_n = states.count(OutcomeState.FAIL_SL)
    ambiguous_n = states.count(OutcomeState.AMBIGUOUS)
    timeout_n = states.count(OutcomeState.TIMEOUT)
    cancelled_n = states.count(OutcomeState.CANCELLED)
    invalidated_n = states.count(OutcomeState.INVALIDATED)
    decisive_n = success_n + fail_sl_n
    historical_success_fraction = (
        None
        if decisive_n == 0
        else Decimal(success_n) / Decimal(decisive_n)
    )

    observations = tuple(
        sorted(
            (
                observation
                for item in items
                if (observation := _r_observation(item)) is not None
            ),
            key=lambda observation: (
                observation.outcome_evaluated_as_of_ms,
                observation.decision_as_of_ms,
                observation.signal_freeze_identity,
            ),
        )
    )
    values = tuple(observation.value_r for observation in observations)
    if values:
        cumulative_r = sum(values, start=Decimal(0))
        average_r = cumulative_r / Decimal(len(values))
        median_r = median(values)
        max_drawdown_r = _max_drawdown(values)
        min_r = min(values)
        max_r = max(values)
    else:
        cumulative_r = None
        average_r = None
        median_r = None
        max_drawdown_r = None
        min_r = None
        max_r = None

    return SegmentMetrics(
        key=key,
        total_n=total_n,
        pending_n=pending_n,
        resolved_n=resolved_n,
        not_evaluable_n=not_evaluable_n,
        success_n=success_n,
        fail_sl_n=fail_sl_n,
        ambiguous_n=ambiguous_n,
        timeout_n=timeout_n,
        cancelled_n=cancelled_n,
        invalidated_n=invalidated_n,
        decisive_n=decisive_n,
        r_evaluable_n=len(observations),
        historical_success_fraction=historical_success_fraction,
        historical_frequency_semantic=(
            HistoricalFrequencySemantic.DESCRIPTIVE_FREQUENCY_NOT_PROBABILITY
        ),
        r_observations=observations,
        average_r=average_r,
        median_r=median_r,
        cumulative_r=cumulative_r,
        max_drawdown_r=max_drawdown_r,
        min_r=min_r,
        max_r=max_r,
        minimum_decisive_sample_size_for_promotion=(
            minimum_decisive_sample_size_for_promotion
        ),
        promotion_eligible=(
            decisive_n >= minimum_decisive_sample_size_for_promotion
        ),
        promotion_semantic=(
            PromotionSemantic.PRODUCT_VISIBILITY_POLICY_NOT_STATISTICAL_SIGNIFICANCE
        ),
    )


def aggregate_segments(
    evaluated_signals: Iterable[EvaluatedSignal],
    *,
    minimum_decisive_sample_size_for_promotion: int = (
        DEFAULT_MINIMUM_DECISIVE_SAMPLE_SIZE_FOR_PROMOTION
    ),
) -> tuple[SegmentMetrics, ...]:
    if minimum_decisive_sample_size_for_promotion <= 0:
        raise ValueError("promotion sample threshold must be positive")

    items = tuple(evaluated_signals)
    seen_signals: set[str] = set()
    grouped: dict[SegmentKey, list[EvaluatedSignal]] = defaultdict(list)
    for item in items:
        identity = item.decision.freeze_identity
        if identity in seen_signals:
            raise ValueError(
                "aggregation received duplicate signal freeze identity"
            )
        seen_signals.add(identity)
        grouped[segment_key(item)].append(item)

    metrics = tuple(
        _metrics_for_segment(
            key,
            tuple(grouped[key]),
            minimum_decisive_sample_size_for_promotion=(
                minimum_decisive_sample_size_for_promotion
            ),
        )
        for key in sorted(
            grouped,
            key=lambda value: (
                value.evidence_class.value,
                "" if value.source_methodology is None else value.source_methodology.value,
                value.setup_type,
                value.exchange.value,
                value.market_type.value,
                value.symbol,
                value.timeframe,
                value.signal_direction.value,
                value.confluence_score_bucket.value,
                "" if value.regime_label is None else value.regime_label,
                "" if value.entry_reference_model is None else value.entry_reference_model.value,
                value.target_count,
                value.target_labels,
            ),
        )
    )
    return metrics
