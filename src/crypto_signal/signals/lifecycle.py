from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from crypto_signal.confluence.models import InvalidationTrigger
from crypto_signal.data.models import Candle
from crypto_signal.data.timeframes import bucket_open_ms, is_aligned_open, spec
from crypto_signal.signals.models import (
    LifecycleEvaluationStatus,
    LifecycleTransitionReason,
    SignalDecision,
    SignalDirection,
    SignalLifecycleEvaluation,
    SignalState,
    SignalStateTransition,
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
            raise ValueError("lifecycle candles do not match signal market context")
        if candle.open_time_ms in seen:
            raise ValueError("lifecycle candle open times must be unique")
        seen.add(candle.open_time_ms)
        if not is_aligned_open(candle.open_time_ms, decision.timeframe):
            raise ValueError("lifecycle candle is off canonical timeframe grid")
        if candle.close_time_ms != candle.open_time_ms + duration_ms - 1:
            raise ValueError("lifecycle candle bounds do not match timeframe")
        if candle.is_closed and candle.ingested_at_ms < candle.close_time_ms:
            raise ValueError("closed lifecycle candle cannot be ingested before close")

    return ordered


def _first_full_post_decision_open(
    decision: SignalDecision,
) -> tuple[int, bool]:
    timeframe_spec = spec(decision.timeframe)
    bucket = bucket_open_ms(decision.as_of_ms, decision.timeframe)
    if bucket < decision.as_of_ms:
        return bucket + timeframe_spec.duration_ms, True
    return bucket, False


def _expected_open_times(
    decision: SignalDecision,
    evaluated_as_of_ms: int,
) -> tuple[tuple[int, ...], bool]:
    timeframe_spec = spec(decision.timeframe)
    first_open, skipped_partial = _first_full_post_decision_open(decision)

    expected: list[int] = []
    open_time = first_open
    while open_time + timeframe_spec.duration_ms - 1 <= evaluated_as_of_ms:
        expected.append(open_time)
        open_time += timeframe_spec.duration_ms
    return tuple(expected), skipped_partial


def _is_invalidation_breach(
    decision: SignalDecision,
    candle: Candle,
) -> tuple[bool, LifecycleTransitionReason | None]:
    geometry = decision.geometry
    if geometry is None:
        return False, None

    price = geometry.invalidation_price
    trigger = geometry.invalidation_trigger

    if trigger is InvalidationTrigger.TOUCH_OR_CROSS:
        if decision.direction is SignalDirection.BULLISH:
            breached = candle.low <= price
        elif decision.direction is SignalDirection.BEARISH:
            breached = candle.high >= price
        else:
            return False, None
        return (
            breached,
            (
                LifecycleTransitionReason.INVALIDATION_TOUCH_OR_CROSS
                if breached
                else None
            ),
        )

    if trigger is InvalidationTrigger.CLOSE_AT_OR_BEYOND:
        if decision.direction is SignalDirection.BULLISH:
            breached = candle.close <= price
        elif decision.direction is SignalDirection.BEARISH:
            breached = candle.close >= price
        else:
            return False, None
        return (
            breached,
            (
                LifecycleTransitionReason.INVALIDATION_CLOSE_AT_OR_BEYOND
                if breached
                else None
            ),
        )

    raise ValueError(f"unsupported invalidation trigger: {trigger}")


def _transition_identity(
    decision: SignalDecision,
    candle: Candle,
    reason: LifecycleTransitionReason,
    evaluated_as_of_ms: int,
    first_trigger_candle_certain: bool,
) -> str:
    payload = {
        "signal_freeze_identity": decision.freeze_identity,
        "from_state": decision.state.value,
        "to_state": SignalState.INVALIDATED.value,
        "reason": reason.value,
        "trigger_candle_identity": list(candle.identity),
        "market_confirmed_at_ms": candle.close_time_ms,
        "observed_at_ms": candle.ingested_at_ms,
        "evaluated_as_of_ms": evaluated_as_of_ms,
        "first_trigger_candle_certain": first_trigger_candle_certain,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate_signal_lifecycle(
    decision: SignalDecision,
    candles: Sequence[Candle],
    *,
    as_of_ms: int,
) -> SignalLifecycleEvaluation:
    if as_of_ms < decision.as_of_ms:
        raise ValueError("lifecycle as-of cannot precede signal decision")

    ordered = _validate_candles(decision, candles)
    expected, skipped_partial = _expected_open_times(decision, as_of_ms)
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
        status = LifecycleEvaluationStatus.NO_NEW_EVIDENCE
    elif missing:
        status = LifecycleEvaluationStatus.INCOMPLETE_GAPS
    else:
        status = LifecycleEvaluationStatus.COMPLETE

    transition: SignalStateTransition | None = None
    if (
        decision.state in {SignalState.WATCH, SignalState.ACTIVE}
        and decision.geometry is not None
    ):
        for open_time in expected:
            observed_candle = observed_by_open.get(open_time)
            if observed_candle is None:
                continue
            breached, reason = _is_invalidation_breach(
                decision,
                observed_candle,
            )
            if not breached or reason is None:
                continue

            first_certain = not any(
                missing_open < observed_candle.open_time_ms
                for missing_open in missing
            )
            transition = SignalStateTransition(
                transition_identity=_transition_identity(
                    decision,
                    observed_candle,
                    reason,
                    as_of_ms,
                    first_certain,
                ),
                signal_freeze_identity=decision.freeze_identity,
                from_state=decision.state,
                to_state=SignalState.INVALIDATED,
                reason=reason,
                trigger_candle_identity=observed_candle.identity,
                market_confirmed_at_ms=observed_candle.close_time_ms,
                observed_at_ms=observed_candle.ingested_at_ms,
                evaluated_as_of_ms=as_of_ms,
                first_trigger_candle_certain=first_certain,
            )
            break

    return SignalLifecycleEvaluation(
        signal_freeze_identity=decision.freeze_identity,
        evaluated_as_of_ms=as_of_ms,
        current_state=(
            SignalState.INVALIDATED
            if transition is not None
            else decision.state
        ),
        status=status,
        missing_open_times_ms=missing,
        skipped_partial_decision_bucket=skipped_partial,
        transition=transition,
    )
