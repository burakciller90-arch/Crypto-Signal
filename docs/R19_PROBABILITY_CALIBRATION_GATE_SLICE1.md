# R19 Calibrated Probability — Slice 1: Untouched-forward Evidence Gate

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

R19 does **not** turn confluence, hit rate or backtest accuracy into a percentage.

This slice defines the minimum evidence contract that must be satisfied before a frozen
model/calibrator output is allowed to carry `CALIBRATED` probability status.

Without an accepted R19 report, the product remains:

`Probability: NOT CALIBRATED`.

## Exact probability event

A probability is scoped to one immutable binary event definition plus:

- asset;
- timeframe;
- regime;
- horizon;
- model version;
- calibrator version;
- walk-forward fit identity.

The probability semantic is:

`frozen_binary_outcome_probability`.

The system never interprets this as generic “chance price goes up.”

## Pre-holdout freeze

Before the untouched holdout decision window begins, the config freezes:

- policy version;
- exact scope identity;
- model version;
- calibrator version;
- accepted walk-forward fit identity;
- training cutoff;
- training sample count;
- training positive/negative class counts;
- minimum training sample/class support;
- untouched decision-window start/end;
- evaluation cutoff covering the full outcome horizon;
- reliability-bin edges;
- minimum untouched sample/class/bin support;
- minimum Brier skill;
- maximum expected calibration error.

The config must predate the holdout window and training must stop before it.

## Frozen prediction identity

Each numeric probability is first frozen into `FrozenProbabilityPrediction`.

Its immutable identity binds:

- scope;
- model version;
- calibrator version;
- walk-forward fit identity;
- source forecast identity;
- issuance timestamp;
- numeric probability;
- probability semantic.

Outcome data is **not** part of that prediction identity.

This matters because holdout membership is based on the pre-outcome prediction identities,
not on outcome-derived rows.

## Untouched-forward outcome attachment

Later, one `UntouchedProbabilityObservation` attaches:

- the exact frozen prediction identity;
- exact source outcome identity;
- outcome availability timestamp;
- observed binary class.

Only `EvidenceClass.LIVE_UNTOUCHED_FORWARD` is admissible.

The observation re-hashes the prediction fields and fails closed if anyone attempts to
change the numeric prediction after seeing the outcome.

## Partition contract

R19 reuses Alpha Factory `PartitionRole.UNTOUCHED_FORWARD`.

Partition evidence membership is the set of **frozen prediction identities**.

It is therefore impossible for an outcome identity itself to define inclusion in the
holdout evidence set.

All observations must match the frozen scope/model/calibrator/walk-forward identity,
decision window, horizon and evaluation cutoff.

## Diagnostics

For the untouched-forward holdout, R19 records:

- training sample and class counts;
- holdout sample and class counts;
- Brier score;
- training-base-rate Brier baseline;
- Brier skill score;
- reliability bins;
- expected calibration error (ECE);
- maximum calibration gap;
- exact observation identities;
- exact calibration evidence identity.

Acceptance fails closed for:

- insufficient untouched sample support;
- insufficient untouched class support;
- insufficient reliability-bin support;
- insufficient Brier skill;
- excessive expected calibration error;
- missing evidence;
- immature holdout window.

Training sample/class support must also satisfy its explicit minimum before a calibration
config is admissible.

## Authorization boundary

An accepted R19 report does not allow a caller to type an arbitrary new percentage.

A future percentage must already exist as a new immutable
`FrozenProbabilityPrediction` from the **same** accepted:

- scope;
- model version;
- calibrator version;
- walk-forward fit identity.

Authorization copies the exact frozen numeric value and links it to the accepted calibration
evidence identity. Manual numeric substitution fails identity verification.

Authorization is allowed only after the calibration report's evaluation cutoff.

## What ACCEPTED does not mean

R19 ACCEPTED means only that this exact frozen model/calibrator/scope passed the configured
untouched-forward calibration evidence gate.

It does **not** mean:

- guaranteed accuracy;
- guaranteed profit;
- optimal model;
- optimal threshold;
- automatic signal promotion;
- automatic position sizing;
- paper-capital write authority;
- real-money authority.

A new model/calibrator/version/scope requires its own evidence.

## Relationship to historical PR #723

Historical draft PR #723 contained an earlier score-bucket probability experiment on an
obsolete v1.1 base. Its useful scientific ideas (chronology, untouched-forward evidence,
Brier diagnostics and fail-closed percentage exposure) are preserved conceptually here.

PR #723 is **not** current merge authority: it targets an older base and uses legacy
confluence/signal assumptions. R19 Slice 1 is the mainline-compatible successor.

## Acceptance checklist

1. Exact event definition + asset/timeframe/regime/horizon are frozen.
2. Model and calibrator versions are frozen.
3. Walk-forward fit identity is mandatory.
4. Training cutoff predates untouched holdout.
5. Explicit training sample/class minimums are enforced.
6. Numeric predictions freeze before outcomes.
7. Holdout partition membership uses prediction identities, not outcome identities.
8. LIVE_UNTOUCHED_FORWARD is the only admissible evidence class.
9. Outcomes cannot exceed frozen horizon/evaluation cutoff.
10. Training and holdout sample/class counts remain visible.
11. Brier, baseline Brier, Brier skill, reliability and ECE remain visible.
12. Insufficient/weak evidence remains NOT_CALIBRATED.
13. Accepted evidence alone may authorize only the exact numeric value of a later frozen prediction.
14. No automatic promotion, sizing, paper write, deployment or real-money authority.
15. REAL_CAPITAL=0.
16. Existing Alpha Factory research gate PASS.
17. Focused R19 + full repository pytest/Ruff/mypy/JS/freshness PASS.
18. Temporary hosted workflow removed after PASS.

If Slice 1 passes, the locked Phase 9 R19 infrastructure requirement is satisfied. Actual
user-visible probability remains conditional on real accepted evidence; where that evidence
does not exist, the correct output remains NOT CALIBRATED.

The next locked roadmap frontier is Phase 10 — Smart Capital Allocator, while Kelly remains
disabled unless R19 calibration evidence exists for the exact probability used.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
