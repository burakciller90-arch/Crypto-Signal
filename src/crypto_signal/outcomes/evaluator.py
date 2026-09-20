from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from itertools import pairwise

from crypto_signal.confluence.models import InvalidationTrigger
from crypto_signal.data.models import Candle
from crypto_signal.data.timeframes import bucket_open_ms, is_aligned_open, spec
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
    SignalDecision,
    SignalDirection,
    SignalState,
)


def _validate_candles(
    decision: SignalDecision,
    candles: Sequence[Candle],
) -> tuple[Candle, ...]:
    ordered = tuple(sorted(candles, key=lambda candle: candle.open_time_ms))
    seen: set[int] = set()
    duration_ms = spec(decision.timeframe).duration_ms

    for candle in ordered:
        if (
            candle.exchange != decision.exchange
            or candle.market_type != decision.market_type
            or candle.symbol != decision.symbol
            or candle.timeframe != decision.timeframe
        ):
            raise ValueError("outcome candles do not match signal market context")
        if candle.open_time_ms in seen:
            raise ValueError("outcome candle open times must be unique")
        seen.add(candle.open_time_ms)
        if not is_aligned_open(candle.open_time_ms, decision.timeframe):
            raise ValueError("outcome candle is off canonical timeframe grid")
        if candle.close_time_ms != candle.open_time_ms + duration_ms - 1:
            raise ValueError("outcome candle bounds do not match timeframe")
        if candle.is_closed and candle.ingested_at_ms < candle.close_time_ms:
            raise ValueError("closed outcome candle cannot be ingested before close")

    return ordered


def _first_full_post_decision_open(
    decision: SignalDecision,
) -> tuple[int, bool]:
    timeframe_spec = spec(decision.timeframe)
    bucket = bucket_open_ms(decision.as_of_ms, decision.timeframe)
    if bucket < decision.as_of_ms:
        return bucket + timeframe_spec.duration_ms, True
    return bucket, False


def _expected_opens(
    decision: SignalDecision,
    *,
    evaluated_as_of_ms: int,
    max_holding_bars: int,
) -> tuple[tuple[int, ...], bool, bool]:
    timeframe_spec = spec(decision.timeframe)
    first_open, skipped_partial = _first_full_post_decision_open(decision)
    horizon_last_open = (
        first_open + (max_holding_bars - 1) * timeframe_spec.duration_ms
    )
    horizon_end_ms = (
        horizon_last_open + timeframe_spec.duration_ms - 1
    )
    effective_end_ms = min(evaluated_as_of_ms, horizon_end_ms)

    expected: list[int] = []
    open_time_ms = first_open
    while (
        open_time_ms + timeframe_spec.duration_ms - 1
        <= effective_end_ms
    ):
        expected.append(open_time_ms)
        open_time_ms += timeframe_spec.duration_ms

    return (
        tuple(expected),
        skipped_partial,
        evaluated_as_of_ms >= horizon_end_ms,
    )


def _invalidation_hit(
    decision: SignalDecision,
    candle: Candle,
) -> bool:
    geometry = decision.geometry
    if geometry is None:
        return False
    price = geometry.invalidation_price
    trigger = geometry.invalidation_trigger

    if trigger is InvalidationTrigger.TOUCH_OR_CROSS:
        if decision.direction is SignalDirection.BULLISH:
            return candle.low <= price
        if decision.direction is SignalDirection.BEARISH:
            return candle.high >= price
        return False

    if trigger is InvalidationTrigger.CLOSE_AT_OR_BEYOND:
        if decision.direction is SignalDirection.BULLISH:
            return candle.close <= price
        if decision.direction is SignalDirection.BEARISH:
            return candle.close >= price
        return False

    raise ValueError(f"unsupported outcome invalidation trigger: {trigger}")


def _target_hits(
    decision: SignalDecision,
    candle: Candle,
) -> tuple[int, ...]:
    geometry = decision.geometry
    if geometry is None:
        return ()
    hits: list[int] = []
    for index, target in enumerate(geometry.targets, start=1):
        if decision.direction is SignalDirection.BULLISH:
            hit = candle.high >= target.target_price
        elif decision.direction is SignalDirection.BEARISH:
            hit = candle.low <= target.target_price
        else:
            hit = False
        if hit:
            hits.append(index)
    return tuple(hits)


def _entry_hit(
    decision: SignalDecision,
    candle: Candle,
) -> bool:
    geometry = decision.geometry
    if geometry is None:
        return False
    return (
        candle.low
        <= geometry.entry_reference_price
        <= candle.high
    )


def _success_state(target_index: int) -> OutcomeState:
    mapping = {
        1: OutcomeState.SUCCESS_TP1,
        2: OutcomeState.SUCCESS_TP2,
        3: OutcomeState.SUCCESS_TP3,
    }
    try:
        return mapping[target_index]
    except KeyError as exc:
        raise ValueError("unsupported target index") from exc


def _validate_target_structure(decision: SignalDecision) -> bool:
    geometry = decision.geometry
    if geometry is None:
        return False
    targets = geometry.targets
    if not 1 <= len(targets) <= 3:
        return False
    prices = tuple(target.target_price for target in targets)
    if decision.direction is SignalDirection.BULLISH:
        return all(left < right for left, right in pairwise(prices))
    if decision.direction is SignalDirection.BEARISH:
        return all(left > right for left, right in pairwise(prices))
    return False


def outcome_identity_payload(
    evaluation: OutcomeEvaluation,
) -> dict[str, object]:
    return {
        "signal_freeze_identity": evaluation.signal_freeze_identity,
        "evidence_class": evaluation.evidence_class.value,
        "evaluated_as_of_ms": evaluation.evaluated_as_of_ms,
        "resolution_status": evaluation.resolution_status.value,
        "outcome_state": (
            None
            if evaluation.outcome_state is None
            else evaluation.outcome_state.value
        ),
        "signal_initial_state": evaluation.signal_initial_state.value,
        "coverage_status": evaluation.coverage_status.value,
        "max_holding_bars": evaluation.max_holding_bars,
        "expected_bar_count": evaluation.expected_bar_count,
        "observed_bar_count": evaluation.observed_bar_count,
        "missing_open_times_ms": list(evaluation.missing_open_times_ms),
        "skipped_partial_decision_bucket": (
            evaluation.skipped_partial_decision_bucket
        ),
        "entry_observed": evaluation.entry_observed,
        "entry_candle_identity": (
            None
            if evaluation.entry_candle_identity is None
            else list(evaluation.entry_candle_identity)
        ),
        "highest_target_index": evaluation.highest_target_index,
        "outcome_candle_identity": (
            None
            if evaluation.outcome_candle_identity is None
            else list(evaluation.outcome_candle_identity)
        ),
        "ambiguity_reason": (
            None
            if evaluation.ambiguity_reason is None
            else evaluation.ambiguity_reason.value
        ),
        "not_evaluable_reason": (
            None
            if evaluation.not_evaluable_reason is None
            else evaluation.not_evaluable_reason.value
        ),
    }


def compute_outcome_identity(evaluation: OutcomeEvaluation) -> str:
    payload = outcome_identity_payload(evaluation)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def verify_outcome_identity(evaluation: OutcomeEvaluation) -> None:
    if evaluation.outcome_identity != compute_outcome_identity(evaluation):
        raise ValueError("outcome evaluation identity mismatch")


def _with_identity(evaluation: OutcomeEvaluation) -> OutcomeEvaluation:
    return replace(
        evaluation,
        outcome_identity=compute_outcome_identity(evaluation),
    )


def _build(
    *,
    decision: SignalDecision,
    evidence_class: EvidenceClass,
    evaluated_as_of_ms: int,
    resolution_status: OutcomeResolutionStatus,
    outcome_state: OutcomeState | None,
    coverage_status: OutcomeCoverageStatus,
    max_holding_bars: int,
    expected_bar_count: int,
    observed_bar_count: int,
    missing_open_times_ms: tuple[int, ...],
    skipped_partial_decision_bucket: bool,
    entry_candle_identity: tuple[str, str, str, str, int] | None,
    highest_target_index: int,
    outcome_candle_identity: tuple[str, str, str, str, int] | None,
    ambiguity_reason: OutcomeAmbiguityReason | None = None,
    not_evaluable_reason: OutcomeNotEvaluableReason | None = None,
) -> OutcomeEvaluation:
    draft = OutcomeEvaluation(
        outcome_identity="0" * 64,
        signal_freeze_identity=decision.freeze_identity,
        evidence_class=evidence_class,
        evaluated_as_of_ms=evaluated_as_of_ms,
        resolution_status=resolution_status,
        outcome_state=outcome_state,
        signal_initial_state=decision.state,
        coverage_status=coverage_status,
        max_holding_bars=max_holding_bars,
        expected_bar_count=expected_bar_count,
        observed_bar_count=observed_bar_count,
        missing_open_times_ms=missing_open_times_ms,
        skipped_partial_decision_bucket=skipped_partial_decision_bucket,
        entry_observed=entry_candle_identity is not None,
        entry_candle_identity=entry_candle_identity,
        highest_target_index=highest_target_index,
        outcome_candle_identity=outcome_candle_identity,
        ambiguity_reason=ambiguity_reason,
        not_evaluable_reason=not_evaluable_reason,
    )
    return _with_identity(draft)


def evaluate_outcome(
    decision: SignalDecision,
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
    evidence_class: EvidenceClass,
    max_holding_bars: int,
) -> OutcomeEvaluation:
    if as_of_ms < decision.as_of_ms:
        raise ValueError("outcome as-of cannot precede signal decision")
    if max_holding_bars <= 0:
        raise ValueError("max_holding_bars must be positive")

    ordered = _validate_candles(decision, candles)
    expected, skipped_partial, horizon_complete = _expected_opens(
        decision,
        evaluated_as_of_ms=as_of_ms,
        max_holding_bars=max_holding_bars,
    )
    expected_set = set(expected)

    observed_by_open: dict[int, Candle] = {}
    for candle in ordered:
        if candle.open_time_ms not in expected_set:
            continue
        if not candle.is_closed:
            continue
        if candle.close_time_ms > as_of_ms:
            continue
        if candle.ingested_at_ms > as_of_ms:
            continue
        observed_by_open[candle.open_time_ms] = candle

    missing = tuple(
        open_time
        for open_time in expected
        if open_time not in observed_by_open
    )
    if not expected:
        coverage = OutcomeCoverageStatus.NO_NEW_EVIDENCE
    elif missing:
        coverage = OutcomeCoverageStatus.INCOMPLETE_GAPS
    else:
        coverage = OutcomeCoverageStatus.COMPLETE

    def emit(
        *,
        resolution_status: OutcomeResolutionStatus,
        outcome_state: OutcomeState | None,
        entry_candle_identity: tuple[str, str, str, str, int] | None,
        highest_target_index: int,
        outcome_candle_identity: tuple[str, str, str, str, int] | None,
        ambiguity_reason: OutcomeAmbiguityReason | None = None,
        not_evaluable_reason: OutcomeNotEvaluableReason | None = None,
    ) -> OutcomeEvaluation:
        return _build(
            decision=decision,
            evidence_class=evidence_class,
            evaluated_as_of_ms=as_of_ms,
            resolution_status=resolution_status,
            outcome_state=outcome_state,
            coverage_status=coverage,
            max_holding_bars=max_holding_bars,
            expected_bar_count=len(expected),
            observed_bar_count=len(observed_by_open),
            missing_open_times_ms=missing,
            skipped_partial_decision_bucket=skipped_partial,
            entry_candle_identity=entry_candle_identity,
            highest_target_index=highest_target_index,
            outcome_candle_identity=outcome_candle_identity,
            ambiguity_reason=ambiguity_reason,
            not_evaluable_reason=not_evaluable_reason,
        )

    if decision.state is not SignalState.ACTIVE:
        return emit(
            resolution_status=OutcomeResolutionStatus.NOT_EVALUABLE,
            outcome_state=OutcomeState.NOT_EVALUABLE,
            entry_candle_identity=None,
            highest_target_index=0,
            outcome_candle_identity=None,
            not_evaluable_reason=OutcomeNotEvaluableReason.SIGNAL_NOT_ACTIVE,
        )
    if decision.geometry is None:
        return emit(
            resolution_status=OutcomeResolutionStatus.NOT_EVALUABLE,
            outcome_state=OutcomeState.NOT_EVALUABLE,
            entry_candle_identity=None,
            highest_target_index=0,
            outcome_candle_identity=None,
            not_evaluable_reason=OutcomeNotEvaluableReason.MISSING_GEOMETRY,
        )
    if not _validate_target_structure(decision):
        return emit(
            resolution_status=OutcomeResolutionStatus.NOT_EVALUABLE,
            outcome_state=OutcomeState.NOT_EVALUABLE,
            entry_candle_identity=None,
            highest_target_index=0,
            outcome_candle_identity=None,
            not_evaluable_reason=(
                OutcomeNotEvaluableReason.UNSUPPORTED_TARGET_STRUCTURE
            ),
        )

    contiguous: list[Candle] = []
    for open_time in expected:
        observed_candle = observed_by_open.get(open_time)
        if observed_candle is None:
            break
        contiguous.append(observed_candle)

    entry_identity: tuple[str, str, str, str, int] | None = None
    highest_target_index = 0
    highest_target_candle: tuple[str, str, str, str, int] | None = None
    target_count = len(decision.geometry.targets)

    for candle in contiguous:
        invalidation = _invalidation_hit(decision, candle)
        target_hits = _target_hits(decision, candle)

        if entry_identity is None:
            entry = _entry_hit(decision, candle)
            if not entry:
                if invalidation:
                    return emit(
                        resolution_status=OutcomeResolutionStatus.RESOLVED,
                        outcome_state=OutcomeState.INVALIDATED,
                        entry_candle_identity=None,
                        highest_target_index=0,
                        outcome_candle_identity=candle.identity,
                    )
                continue

            entry_identity = candle.identity
            if invalidation:
                return emit(
                    resolution_status=OutcomeResolutionStatus.RESOLVED,
                    outcome_state=OutcomeState.AMBIGUOUS,
                    entry_candle_identity=entry_identity,
                    highest_target_index=0,
                    outcome_candle_identity=candle.identity,
                    ambiguity_reason=(
                        OutcomeAmbiguityReason.ENTRY_AND_INVALIDATION_SAME_CANDLE
                    ),
                )
            if target_hits:
                return emit(
                    resolution_status=OutcomeResolutionStatus.RESOLVED,
                    outcome_state=OutcomeState.AMBIGUOUS,
                    entry_candle_identity=entry_identity,
                    highest_target_index=0,
                    outcome_candle_identity=candle.identity,
                    ambiguity_reason=(
                        OutcomeAmbiguityReason.ENTRY_AND_TARGET_SAME_CANDLE
                    ),
                )
            continue

        new_highest = (
            max(target_hits)
            if target_hits
            else highest_target_index
        )
        if invalidation and new_highest > highest_target_index:
            return emit(
                resolution_status=OutcomeResolutionStatus.RESOLVED,
                outcome_state=OutcomeState.AMBIGUOUS,
                entry_candle_identity=entry_identity,
                highest_target_index=highest_target_index,
                outcome_candle_identity=candle.identity,
                ambiguity_reason=(
                    OutcomeAmbiguityReason.INVALIDATION_AND_NEW_TARGET_SAME_CANDLE
                ),
            )

        if invalidation:
            if highest_target_index > 0:
                return emit(
                    resolution_status=OutcomeResolutionStatus.RESOLVED,
                    outcome_state=_success_state(highest_target_index),
                    entry_candle_identity=entry_identity,
                    highest_target_index=highest_target_index,
                    outcome_candle_identity=highest_target_candle,
                )
            return emit(
                resolution_status=OutcomeResolutionStatus.RESOLVED,
                outcome_state=OutcomeState.FAIL_SL,
                entry_candle_identity=entry_identity,
                highest_target_index=0,
                outcome_candle_identity=candle.identity,
            )

        if new_highest > highest_target_index:
            highest_target_index = new_highest
            highest_target_candle = candle.identity
            if highest_target_index == target_count:
                return emit(
                    resolution_status=OutcomeResolutionStatus.RESOLVED,
                    outcome_state=_success_state(highest_target_index),
                    entry_candle_identity=entry_identity,
                    highest_target_index=highest_target_index,
                    outcome_candle_identity=highest_target_candle,
                )

    if highest_target_index > 0:
        return emit(
            resolution_status=OutcomeResolutionStatus.RESOLVED,
            outcome_state=_success_state(highest_target_index),
            entry_candle_identity=entry_identity,
            highest_target_index=highest_target_index,
            outcome_candle_identity=highest_target_candle,
        )

    if missing:
        return emit(
            resolution_status=OutcomeResolutionStatus.NOT_EVALUABLE,
            outcome_state=OutcomeState.NOT_EVALUABLE,
            entry_candle_identity=entry_identity,
            highest_target_index=0,
            outcome_candle_identity=None,
            not_evaluable_reason=OutcomeNotEvaluableReason.DATA_GAPS,
        )

    if horizon_complete:
        return emit(
            resolution_status=OutcomeResolutionStatus.RESOLVED,
            outcome_state=OutcomeState.TIMEOUT,
            entry_candle_identity=entry_identity,
            highest_target_index=0,
            outcome_candle_identity=(
                contiguous[-1].identity if contiguous else None
            ),
        )

    return emit(
        resolution_status=OutcomeResolutionStatus.PENDING,
        outcome_state=None,
        entry_candle_identity=entry_identity,
        highest_target_index=0,
        outcome_candle_identity=None,
    )
