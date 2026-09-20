# ADR 0022 — Outcome V1 Semantics

Status: Accepted for implementation
Date: 2026-09-20
REAL_CAPITAL: 0

## Outcome states
V1 supports:
- SUCCESS_TP1
- SUCCESS_TP2
- SUCCESS_TP3
- FAIL_SL
- AMBIGUOUS
- TIMEOUT
- CANCELLED
- INVALIDATED
- NOT_EVALUABLE

## Snapshot resolution status
Outcome state and snapshot resolution are separate.

Every OutcomeEvaluation has one resolution status:
- PENDING: no outcome state is yet provable
- RESOLVED: one documented outcome state is already proven at this as-of
- NOT_EVALUABLE: evaluation cannot be trusted under the V1 contract

PENDING is not an outcome state and does not alter the contracted outcome vocabulary.

## Evidence classes
Every outcome evaluation carries exactly one evidence class:
- RETROSPECTIVE
- WALK_FORWARD
- LIVE_UNTOUCHED_FORWARD

Evidence class is explicit input.
It is never inferred merely from timestamps.

Performance aggregation must segment these classes.
It may not silently merge them into one success rate.

## Eligibility
Automated candle outcome evaluation requires:
- initial SignalDecision state ACTIVE
- complete SignalGeometry
- directional signal
- 1 through 3 ordered targets
- supported entry reference model

NO_SIGNAL, NEUTRAL and WATCH are NOT_EVALUABLE for outcome success/failure.

CANCELLED is an explicit external lifecycle decision and is not inferred from OHLC.

## Shadow entry model
V1 outcome evaluation uses:
ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION

The signal entry-zone midpoint is a shadow evaluation reference only.
It is not an execution fill claim.

Entry becomes observed on the first fully post-decision closed/observed candle
whose range contains the midpoint reference price.

The candle already open at signal-decision time is excluded.

## Before entry
If a fully observed candle invalidates the signal before any entry touch:
outcome = INVALIDATED.

If one candle contains both the entry reference and invalidation:
outcome = AMBIGUOUS because intrabar ordering is unknown.

Targets reached before entry do not count as success.

If one candle contains both entry and any target:
outcome = AMBIGUOUS because the target may have occurred before entry.

## After entry
For each later fully observed candle:
- evaluate invalidation trigger exactly as frozen
- evaluate target touches

If a candle contains both invalidation and a not-yet-achieved target:
outcome = AMBIGUOUS.

If only targets are reached, record the highest target reached.

If invalidation occurs after one or more targets were already reached and no new
target shares the invalidation candle, the highest previously proven target remains
the success state.

If invalidation occurs before any target:
outcome = FAIL_SL.

## Target ordering
Bullish targets must be strictly increasing in the declared tuple.
Bearish targets must be strictly decreasing.

A candle reaching a higher target without invalidation also proves all lower
ordered targets were traversed after a prior established entry.

V1 supports at most three targets because the outcome vocabulary is TP1/TP2/TP3.

## Same-candle ambiguity
Without lower-timeframe or tick evidence, V1 never guesses event order.

AMBIGUOUS examples:
- entry + stop in same candle
- entry + target in same candle
- stop + next target in same candle after entry

A future resolver may replace ambiguity only by appending higher-resolution evidence.
It must never rewrite the original ambiguous snapshot.

## Gaps and point-in-time
Expected fully post-decision candle opens are explicit.

If any required candle is missing/unobserved before the evaluated horizon and
no already-provable outcome can be established safely, outcome = NOT_EVALUABLE
with explicit missing-open evidence.

Missing data is never synthesized.

## Timeout
max_holding_bars is an explicit evaluation policy input.

TIMEOUT requires complete coverage through the configured bar horizon and no
stronger proven outcome.

A signal that never entered before the complete timeout horizon is TIMEOUT.

An entered signal with no target or stop before the complete timeout horizon is TIMEOUT.

If TP1 or TP2 was proven before timeout, the proven success state is retained.

## Snapshot model
OutcomeEvaluation is a point-in-time snapshot.

A later snapshot may progress:
- TIMEOUT is final for that configured horizon
- SUCCESS_TP1 may later become SUCCESS_TP2/TP3 before horizon
- SUCCESS_TP2 may later become SUCCESS_TP3
- terminal ambiguity/failure/invalidation remain evidence at their evaluation time

Ledger storage is append-only; no earlier outcome snapshot is rewritten.

## Probability boundary
Outcome states are observations.
They are not calibrated probabilities and do not retroactively change the
decision-time confluence score.

REAL_CAPITAL remains 0.
