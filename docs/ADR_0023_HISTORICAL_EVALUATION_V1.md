# ADR 0023 — Historical Evaluation V1

Status: Accepted for implementation
Date: 2026-09-20
REAL_CAPITAL: 0

## Purpose
Historical Evaluation summarizes already-frozen SignalDecision + OutcomeEvaluation pairs.

It does not rerun methodology logic and does not infer a missing outcome.

The caller supplies exactly one OutcomeEvaluation snapshot per SignalDecision.

## Evidence-class firewall
EvidenceClass is a mandatory segment dimension:
- RETROSPECTIVE
- WALK_FORWARD
- LIVE_UNTOUCHED_FORWARD

The V1 aggregator returns separate segments.
It never emits one combined metric that silently mixes evidence classes.

## Evaluated-signal contract
An EvaluatedSignal requires:
- outcome.signal_freeze_identity == decision.freeze_identity
- deterministic outcome identity verification
- one snapshot per signal in one aggregation call

Duplicate signal freeze identities are rejected rather than silently choosing
one snapshot.

## Segment dimensions
V1 segment key:
- evidence class
- geometry source methodology, nullable when no geometry exists
- setup type
- exchange
- market type
- symbol
- timeframe
- signal direction
- confluence score bucket
- regime label, nullable
- entry reference model, nullable
- target count
- target labels

Regime remains nullable because no V1 regime engine is accepted yet.

## Confluence score buckets
V1 uses descriptive numeric buckets:
- SCORE_0
- SCORE_GT_0_LE_33_33
- SCORE_GT_33_33_LE_66_67
- SCORE_GT_66_67_LE_100

Bucket names are not quality labels.

## Counts
Each segment exposes:
- total_n
- pending_n
- resolved_n
- not_evaluable_n
- success_n
- fail_sl_n
- ambiguous_n
- timeout_n
- cancelled_n
- invalidated_n
- decisive_n = success_n + fail_sl_n
- r_evaluable_n

Historical success fraction:
success_n / decisive_n

It is emitted only when decisive_n > 0.

The denominator is explicit.
Timeout, ambiguity, invalidated-before-entry, cancelled and not-evaluable cases
are not silently reclassified as wins or losses.

Historical success fraction is descriptive frequency, not probability.

## Realized shadow R
V1 emits realized shadow R only where deterministic under the frozen model:
- SUCCESS_TPn -> the frozen corresponding target reference_rr
- FAIL_SL -> -1R

Undefined R:
- AMBIGUOUS
- TIMEOUT
- CANCELLED
- INVALIDATED
- NOT_EVALUABLE
- PENDING

No exit price is invented for timeout or cancellation.

## R statistics
For R-evaluable outcomes only:
- exact chronological R observations
- average R
- median R
- cumulative R
- max drawdown in R units
- minimum R
- maximum R

Chronological order:
outcome evaluated_as_of_ms, then decision as_of_ms, then signal freeze identity.

Max drawdown starts from 0R equity and uses peak-to-trough loss on cumulative R.

## Sample-size visibility
Default product policy:
minimum_decisive_sample_size_for_promotion = 30

promotion_eligible is true only when decisive_n >= that configured threshold.

This is a product visibility policy.
It is not a statistical-significance claim and does not calibrate probability.

The threshold is explicit input and may be changed by product policy.

## Probability boundary
The following remain distinct:
- historical success fraction
- confluence score
- calibrated probability status
- realized shadow R

Historical frequency does not become calibrated probability.

REAL_CAPITAL remains 0.
