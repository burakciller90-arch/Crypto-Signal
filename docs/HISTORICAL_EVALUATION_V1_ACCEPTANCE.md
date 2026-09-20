# Historical Evaluation V1 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted input contract
Historical Evaluation consumes already-frozen:
- SignalDecision
- exactly one OutcomeEvaluation snapshot for that signal

EvaluatedSignal verifies:
- outcome parent identity equals SignalDecision.freeze_identity
- deterministic outcome identity is valid
- optional regime label is explicit and nullable

One aggregation call rejects duplicate signal freeze identities rather than
silently choosing between multiple outcome snapshots.

## Evidence-class firewall
Evidence class is a mandatory segment key:
- RETROSPECTIVE
- WALK_FORWARD
- LIVE_UNTOUCHED_FORWARD

The aggregator does not emit a silently merged cross-class metric.

## Accepted segment dimensions
Each segment is keyed by:
- evidence class
- geometry source methodology, nullable
- setup type
- exchange
- market type
- symbol
- timeframe
- signal direction
- descriptive confluence-score bucket
- optional regime label
- optional entry reference model
- target count
- target labels

Confluence buckets:
- SCORE_0
- SCORE_GT_0_LE_33_33
- SCORE_GT_33_33_LE_66_67
- SCORE_GT_66_67_LE_100

Bucket labels are descriptive numeric partitions, not quality ratings.

## Accepted counts
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
- decisive_n
- r_evaluable_n

decisive_n = success_n + fail_sl_n.

Historical success fraction is emitted only when decisive_n > 0:
success_n / decisive_n.

AMBIGUOUS, TIMEOUT, CANCELLED, INVALIDATED, PENDING and NOT_EVALUABLE are not
silently recoded as wins or losses.

Historical success fraction is explicitly tagged:
descriptive_frequency_not_probability.

## Accepted shadow-R semantics
Defined R only:
- SUCCESS_TP1 -> frozen target 1 reference_rr
- SUCCESS_TP2 -> frozen target 2 reference_rr
- SUCCESS_TP3 -> frozen target 3 reference_rr
- FAIL_SL -> -1R

Undefined R:
- AMBIGUOUS
- TIMEOUT
- CANCELLED
- INVALIDATED
- NOT_EVALUABLE
- PENDING

No timeout/cancellation exit price is invented.

Success R must be supported by the frozen target structure.
A success state referring to a non-existent frozen target is rejected.

## Accepted R statistics
For R-evaluable outcomes only:
- chronological R observations
- average R
- median R
- cumulative R
- max drawdown in R units
- minimum R
- maximum R

Chronological ordering:
1. outcome evaluated_as_of_ms
2. decision as_of_ms
3. signal freeze identity

Max drawdown starts at 0R equity and measures the greatest peak-to-trough
decline in cumulative shadow R.

## Sample-size visibility
Default product visibility threshold:
minimum_decisive_sample_size_for_promotion = 30.

promotion_eligible is a product display policy only.

It is explicitly tagged:
product_visibility_policy_not_statistical_significance.

It does not imply:
- statistical significance
- calibrated probability
- expected profitability
- confidence

## Mechanical acceptance
Historical Evaluation focused gate:
- 14 tests PASS
- Ruff PASS
- mypy PASS

Full repository gate:
- 203 tests PASS
- Ruff PASS
- mypy PASS
- git diff check PASS

Test coverage includes:
- exact score-bucket boundaries
- frozen target R mapping
- FAIL_SL = -1R
- undefined R for ambiguous outcomes
- evidence classes never merging into one segment
- explicit non-decisive counts
- historical success fraction denominator
- chronological R ordering
- average / median / cumulative R
- peak-to-trough max drawdown
- sample-size promotion policy
- duplicate signal snapshot rejection
- nullable regime segmentation

## Current untouched-forward evidence state
At acceptance read-only production inspection:
- immutable signal freezes: 24
- WATCH: 24
- ACTIVE: 0
- bearish WATCH: 20
- bullish WATCH: 4

Therefore there is currently no LIVE_UNTOUCHED_FORWARD ACTIVE outcome sample
from which a live success fraction or shadow-R performance statistic can be
honestly reported.

Historical Evaluation V1 is ready to summarize such evidence when ACTIVE
signals and their later append-only outcomes exist.

No live win rate or live probability is fabricated.

## Canonical next frontier
Dashboard V1 / Product Command Center.

Initial bounded slice:
- application shell and information architecture
- Command Center
- Market Radar
- Asset Cockpit
- Signal Detail
- Signal Archive
- Performance surface
- explicit evidence-class and probability/confluence labels
- no mock data presented as real

The first Dashboard slice should establish product contracts and a real-data
read model before visual polish expands.

REAL_CAPITAL remains 0.
