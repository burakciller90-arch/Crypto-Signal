# M6 Confluence Matrix 2.0 — Slice 2: Chronological Forward Threshold Research

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Evaluate the locked M6 threshold hypotheses **70 / 75 / 80 / 85** on one frozen,
chronological untouched-forward window without retrospectively selecting a winner.

This slice is descriptive research only. It does not activate signals, calibrate probability,
promote a threshold, mutate paper capital, or create execution authority.

## Frozen-before-forward contract

Before the forward window opens, `ConfluenceThresholdResearchConfig` freezes:

- exact accepted M6 matrix policy identity;
- exact threshold set 70 / 75 / 80 / 85;
- creation timestamp;
- forward window start/end;
- explicit outcome definition;
- no-winner/no-promotion/no-calibration/no-production invariants.

The config creation time must strictly predate the forward window.

## Forward partition contract

Evaluation requires the existing Alpha Factory
`PartitionRole.UNTOUCHED_FORWARD` contract.

The partition must exactly match:

- frozen window start/end;
- row count;
- every M6 matrix snapshot identity used in the comparison.

This reuses the accepted research partition semantics instead of creating a parallel
backtest framework.

## Outcome attachment

Each forward observation links one immutable M6 matrix snapshot to one later outcome and
freezes:

- candidate direction;
- decision as-of timestamp;
- outcome availability timestamp;
- support score;
- opposition score;
- matrix resolution;
- coverage / quality / freshness;
- material-conflict count;
- gross outcome in R;
- explicit research cost in R;
- net outcome in R;
- exact outcome evidence identity.

The outcome must become available **after** the decision and no later than the frozen
forward-window end.

## Threshold comparison

For each locked threshold:

- only `MEASURED` matrix snapshots are eligible to activate;
- support must be greater than or equal to the threshold;
- CONFLICT / ABSTAIN / PARTIAL / NOT_EVALUABLE snapshots remain blocked even if their
  arithmetic support is high;
- results retain eligible count, activation count, blocked count, positive/negative/flat
  net outcome counts, gross R, explicit cost R, net R, mean net R and descriptive
  positive-net fraction.

The positive-net fraction is an empirical descriptive fraction over activated forward
observations. It is **not** calibrated probability.

## No winner selection

The manifest always preserves:

- `automatic_winner_selection = false`;
- `threshold_winner = null`;
- `automatic_promotion = false`;
- `calibrated_probability_claim = false`;
- `production_authority = false`;
- `REAL_CAPITAL = 0`.

The system may show all four threshold results side by side. It may not automatically call
one “best,” promote one to canonical ACTIVE policy, or rewrite the frozen experiment after
outcomes arrive.

## Maturity semantics

- Before the frozen window closes: `NOT_YET_EVALUABLE`.
- Closed window with no matching observations: `NO_EVIDENCE`.
- Closed window with complete matching observations/outcomes: `EVALUATED`.

Missing evidence is never converted into a result.

## Scientific boundaries

- Confluence threshold is not probability.
- Historical/forward positive fraction is not calibrated probability.
- One forward window is not proof of optimality.
- No threshold winner is inferred from net R, mean R or activation rate.
- Explicit costs remain visible.
- Conflict veto remains active before threshold arithmetic.
- No production, sizing, leverage or order authority.
- REAL_CAPITAL=0.

## Acceptance checklist

1. Config freezes before the forward window.
2. Thresholds are exactly 70 / 75 / 80 / 85.
3. Existing `UNTOUCHED_FORWARD` partition semantics are reused.
4. Decision evidence predates outcome availability.
5. Outcomes must mature inside the frozen window.
6. 72 / 77 / 82 / 90 synthetic forward support produces activation counts 4 / 3 / 2 / 1.
7. High-support conflict evidence remains blocked.
8. Input permutation does not alter results.
9. NOT_YET_EVALUABLE and NO_EVIDENCE remain explicit.
10. Exact partition membership is enforced.
11. No automatic winner, promotion, calibration or production authority.
12. Focused pytest/Ruff/mypy plus full repository Python/JavaScript/freshness regression.
13. Temporary hosted workflow removed after PASS.

Once accepted, the locked Phase 8 M6 exit is satisfied at the infrastructure/contract
level: the five-family matrix exists and the mandated threshold hypotheses can be compared
under chronological untouched-forward evidence without automatic selection.

The next locked intelligence frontier is Phase 9 — **R19 calibrated probability**. A
percentage remains forbidden until its separate calibration evidence contract is satisfied.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
