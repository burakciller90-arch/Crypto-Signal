# WC2 Untouched-Forward Evidence Policy v1

Status: PREREGISTRATION CONTRACT  
Evidence class: `LIVE_UNTOUCHED_FORWARD` only  
Authority: World-Class Completion WC2  
REAL_CAPITAL=0

## Purpose

This policy defines **when the accumulated untouched-forward paper cohort is large
and diverse enough to begin WC3 performance/calibration review**.

It does **not** define a profitable system, an accuracy target, a probability
authorization, a model winner, or automatic production promotion.

The policy must be frozen before its collection window begins. A later policy
change starts a new cohort boundary; it cannot be applied retroactively to earlier
observations.

## Locked v1 review-sufficiency thresholds

- Minimum total decisive untouched-forward observations: **300**.
- Required asset scope: **BTCUSDT, ETHUSDT, SOLUSDT**.
- Minimum decisive observations per required asset: **75**.
- Minimum qualifying regime buckets: **3**.
- Minimum decisive observations in each qualifying regime: **50**.
- Minimum calendar duration: **120 days**.
- Every immutable forecast in the cohort must retain a paper decision/intent.
- Every paper trade decision must retain a simulated execution record.
- Every simulated paper trade must retain explicit execution-cost evidence.
- Losses, abstains, invalidations and unresolved observations must remain retained.

These thresholds are evidence-sufficiency gates. They are deliberately separate
from the historical evaluation module's smaller product-visibility threshold and
from R19 scope-specific calibration support thresholds.

## Why these numbers are frozen before results

The total-N threshold is intended to prevent a small lucky run from becoming a
headline result. The per-asset and regime requirements prevent a large aggregate
sample from hiding concentration in one asset or one market state. The calendar
duration requirement reduces the risk of treating one short volatility episode as
general evidence.

No WC2 gate depends on observed win rate, expectancy, Brier score, Sharpe,
Sortino, profit factor, or any selected performance threshold. Those belong to WC3
and may only be computed from the accepted evidence that actually exists.

## Review semantics

Passing WC2 means only:

`REVIEW_ELIGIBLE = enough preregistered evidence exists to run WC3 analysis`.

It does not mean:

- edge supported;
- calibrated;
- profitable;
- production ready;
- promotion approved;
- real-money authorized.

Automatic promotion remains forbidden. REAL_CAPITAL remains 0.
