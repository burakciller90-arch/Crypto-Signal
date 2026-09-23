# R21.5 Shadow Lab 2.0 — Slice 1: Research Governance & Comparison

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Shadow Lab 2.0 is the research comparison layer above the accepted Alpha Factory. It does
not add a parallel backtester. It freezes challenger identity, forward-validation evidence,
robustness/cost-stress evidence, descriptive metrics and promotion-gate state in one
research-only manifest.

Supported locked research families:

- confluence thresholds;
- alternative priors/weights;
- scalping/microstructure policies;
- fractional-Kelly sizing;
- arbitrage/market-neutral policies;
- entry/exit alternatives;
- horizon alternatives;
- event windows;
- liquidity definitions;
- wallet filters.

## Authority boundary

Every Shadow Lab artifact is:

`shadow_research_only_no_canonical_write`

and enforces:

- no self-promotion;
- no automatic winner;
- no champion write;
- no canonical paper-capital mutation;
- no production/order authority;
- REAL_CAPITAL=0.

## Reuse boundary

Shadow Lab reuses accepted Alpha Factory:

- immutable experiment identity;
- non-overlapping train/validation/OOS/untouched-forward partitions;
- leakage audit;
- reproducibility;
- cost stress;
- walk-forward evidence;
- untouched-forward evidence;
- robustness/ablation;
- promotion-gate evidence identity;
- promotion-gate assessment.

A Shadow variant does not accept caller-invented forward/robustness/cost identities.
Those identities are derived directly from the exact `PromotionGateEvidence` object, and
the supplied `PromotionGateAssessment` must bind that same evidence identity.

A variant whose Alpha Factory promotion gate is BLOCKED stays BLOCKED. A variant whose
gate is ready becomes only `READY_FOR_EXPLICIT_REVIEW`. A supervisor-accepted gate is
represented as `SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION_REVIEW`; even then no champion
write, canonical-capital mutation, deployment or production authority is granted.

## Comparison truth

A comparison freezes:

- current champion policy identity;
- exact shadow variant identities;
- represented research families;
- review-ready variants;
- blocked variants;
- creation time.

`winner_identity` is always null.

Metrics are descriptive values with exact evidence identities. They can show net-R,
drawdown, cost or other properly-defined research measures, but the comparison itself does
not rank or select a winner automatically.

## Promotion semantics

Shadow success never promotes itself.

Any later champion/challenger transition must remain:

- explicit;
- versioned;
- separately authorized;
- supported by accepted untouched-forward evidence;
- supported by robustness and cost-stress evidence;
- outside this Shadow Lab comparison artifact.

## Acceptance checklist

1. All locked Shadow Lab research families are representable.
2. Every variant binds an accepted Alpha Factory experiment identity.
3. Untouched-forward, robustness and cost-stress identities are derived from the exact bound promotion-evidence dossier.
4. Promotion assessment must bind the same promotion-evidence identity.
5. Missing promotion evidence remains BLOCKED.
6. Ready evidence becomes only READY_FOR_EXPLICIT_REVIEW.
7. Supervisor acceptance remains manual-review evidence and grants no canonical write authority.
8. Comparison cannot select a winner.
9. No self-promotion/champion write/canonical capital mutation.
10. Descriptive metrics retain exact evidence identities.
11. Duplicate/tampered identities fail closed.
12. REAL_CAPITAL=0.
13. Alpha Factory research-only gate remains green.
14. Focused Shadow Lab + full repository regression pass.
15. Temporary hosted workflow is removed after PASS.

After acceptance, Phase 16 infrastructure exit is satisfied. The next locked frontier is
Phase 17 — R22 Transaction & Decision Tape.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
