# ADR 0020 — Signal Lifecycle and PIT-Safe Invalidation

Status: Accepted for Signal Slice 2 implementation
Date: 2026-09-20

## Immutable decision
SignalDecision is never rewritten.

Lifecycle evaluation may emit an append-only SignalStateTransition referencing
the original freeze_identity.

V1 lifecycle only adds the transition:
- WATCH -> INVALIDATED
- ACTIVE -> INVALIDATED

NO_SIGNAL and NEUTRAL have no invalidation transition.
A WATCH without complete geometry cannot invalidate.

## Post-decision evidence boundary
Only fully post-decision candles may be used for lifecycle invalidation.

If the decision as-of falls inside an already-open candle, that candle is
skipped entirely because its final high/low contains price action from before
the decision.

The first eligible candle is the first canonical timeframe candle whose
open_time is greater than or equal to the decision as-of.

If decision as-of is exactly on a canonical candle open, that candle is eligible.

This intentionally sacrifices some earliest intrabar information to avoid
pre-decision contamination.

## Point-in-time observation
A candle may participate only when:
- it is closed
- its close time is <= lifecycle evaluation as-of
- its local ingested_at is <= lifecycle evaluation as-of
- its open time is in the fully post-decision canonical grid

Future or not-yet-observed candles are invisible.

## Coverage and gaps
Expected canonical candle opens are computed from the first fully post-decision
open through the evaluation as-of.

LifecycleEvaluationStatus:
- NO_NEW_EVIDENCE: no full post-decision candle has completed yet
- COMPLETE: every expected candle is observed
- INCOMPLETE_GAPS: one or more expected candle opens are missing/unobserved

Missing opens are always returned explicitly.

A missing candle never gets synthetically filled.

If no invalidation breach is observed while gaps exist, the original state
remains unchanged but coverage is INCOMPLETE_GAPS. This is not proof that the
setup remained valid.

If an invalidation breach is observed after an earlier gap, state becomes
INVALIDATED because invalidation is proven by the observed candle, but
first_trigger_candle_certain=false because an earlier missing candle may have
invalidated first.

## Trigger semantics

### TOUCH_OR_CROSS
Bullish signal:
- candle.low <= invalidation price

Bearish signal:
- candle.high >= invalidation price

### CLOSE_AT_OR_BEYOND
Bullish signal:
- candle.close <= invalidation price

Bearish signal:
- candle.close >= invalidation price

The trigger semantic is copied from the source MethodologyEvidence and is not
reinterpreted by lifecycle code.

## Transition evidence
An invalidation transition stores:
- deterministic transition identity
- signal freeze identity
- from state
- INVALIDATED to state
- trigger reason
- trigger candle identity
- candle close as market confirmation time
- local ingestion time
- lifecycle evaluation as-of
- whether the first observed trigger candle is known to be the first possible
  trigger candle under complete coverage

For TOUCH_OR_CROSS, no exact intrabar trigger timestamp is fabricated.

## Non-goals
This slice does not evaluate:
- target success
- stop-vs-target same-candle ordering
- timeout
- realized R
- outcome states

Those belong to Outcome / Historical Evaluation after immutable live freeze.

REAL_CAPITAL remains 0.
