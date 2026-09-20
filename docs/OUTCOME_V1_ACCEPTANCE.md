# Outcome V1 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted outcome vocabulary
- SUCCESS_TP1
- SUCCESS_TP2
- SUCCESS_TP3
- FAIL_SL
- AMBIGUOUS
- TIMEOUT
- CANCELLED
- INVALIDATED
- NOT_EVALUABLE

Snapshot resolution is separate:
- PENDING
- RESOLVED
- NOT_EVALUABLE

PENDING is not an outcome state.

## Accepted evidence classes
Every OutcomeEvaluation carries exactly one explicit evidence class:
- RETROSPECTIVE
- WALK_FORWARD
- LIVE_UNTOUCHED_FORWARD

The evaluator does not infer evidence class from timestamps.

## Entry and ordering semantics
V1 shadow entry model:
ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION.

Only fully post-decision closed/observed candles are used.

The decision-time partial candle is excluded.

The following are AMBIGUOUS without lower-timeframe/tick evidence:
- entry + invalidation in one candle
- entry + target in one candle
- invalidation + a new target in one candle after entry

No intrabar ordering is guessed.

## Accepted outcome behavior
- invalidation before entry -> INVALIDATED
- separate entry then stop before any target -> FAIL_SL
- TP1 then later stop -> proven SUCCESS_TP1 remains
- highest configured target hit -> corresponding SUCCESS_TPn
- complete horizon with no stronger result -> TIMEOUT
- gap before unresolved ordering -> NOT_EVALUABLE / DATA_GAPS
- explicit close invalidation does not treat wick-only breach as stop
- bullish/bearish behavior is symmetric

## Evidence coverage
Expected canonical post-decision opens are explicit.

Outcome evaluation uses only the contiguous observed prefix before the first gap
for event ordering.

Missing candles are never synthesized.

## Immutable ledger integration
The ledger now has append-only outcome_evaluations.

Each outcome snapshot is bound to:
- parent signal freeze identity
- evidence class
- evaluated as-of
- max holding bars
- deterministic outcome identity

Equivalent insertion is UNCHANGED.

Different content at the same:
signal + evidence class + as-of + holding horizon
is an immutable conflict.

SQL UPDATE and DELETE are rejected by triggers.

## Mechanical evidence
Outcome evaluator tests:
- 15 PASS

Combined outcome + immutable-ledger focused gate:
- 28 PASS

Full repository gate:
- 189 PASS
- Ruff PASS
- mypy PASS
- live-evidence launchd plist lint PASS

Coverage includes:
- pending state without post-decision evidence
- inactive signal NOT_EVALUABLE
- entry/stop same-candle ambiguity
- entry/target same-candle ambiguity
- stop/new-target same-candle ambiguity
- SL
- TP1 retained after later stop
- TP3
- timeout
- gap non-evaluability
- close-vs-wick invalidation
- bearish symmetry
- evidence-class-specific outcome identity
- parent freeze enforcement
- outcome identity tamper rejection
- SQL immutability

## LIVE/STABLE isolation
Production evidence clock no longer imports the mutable development working tree.

Production runner is bound to:
- /Users/crypto-signal-agent/Crypto-Signal-Live
- accepted commit e53c5b29ffc9301fb36c89aa85ddc3677c4e64a1

The main development worktree may advance independently.

A later accepted live deployment must explicitly move the stable worktree to a
new reviewed commit.

## Canonical next frontier
Historical Evaluation V1:
- evidence-class-preserving aggregation
- segmentation by methodology/setup/symbol/timeframe/direction/confluence bucket
- N, success/failure/ambiguous/not-evaluable counts
- average/median realized shadow R where definable
- cumulative shadow R and drawdown
- sample-size visibility
- no calibrated probability claim
- retrospective and untouched-forward results never silently merged

REAL_CAPITAL remains 0.
