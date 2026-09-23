# M6 Confluence Matrix 2.0 — Slice 1: Five-family Core

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Replace the old narrow methodology-only confluence view with the locked v1.1 five-family
research matrix while preserving all existing evidence engines and the historical
three-methodology agreement index.

This slice is a **research measurement layer**. It does not produce calibrated probability,
does not auto-activate a signal, and has no paper/live execution authority.

## Locked priors

Exactly:

- Geometry / PA / Elliott / Harmonic: **20%**
- Liquidity: **25%**
- Order Flow / Absorption: **25%**
- Derivatives: **15%**
- On-chain / Smart Money: **15%**

Weights sum to exactly 100%.

Event Risk remains **outside** this 100-point matrix as veto/context.

## Matrix input contract

Each family supplies one explicit `ConfluenceFamilyEvidence` object for the exact
asset/timeframe/regime/as-of context.

An observed family freezes:

- family;
- direction;
- directional strength [0,1];
- evidence quality [0,1];
- freshness [0,1];
- market-available and observed timestamps;
- source engine IDs;
- exact source evidence identities;
- material independent-conflict identities;
- uncertainty flags.

Missing or not-evaluable family evidence is represented explicitly using the existing
`MetaEvidenceState` semantics. It is never silently treated as neutral evidence.

## Output truth

The matrix keeps separate:

- support score, 0..100;
- opposition score, 0..100;
- evidence coverage, 0..100;
- weighted evidence quality, 0..1;
- weighted freshness, 0..1;
- material independent conflicts;
- family-level contributions.

The score semantic is:

`weighted_support_opposition_points_not_probability`

and the probability status is always:

`not_calibrated`

until R19 independently earns probability calibration.

Therefore a valid statement such as:

`Confluence support: 82/100 — Probability: NOT CALIBRATED`

is an explicit design invariant.

## Conflict and missing-data semantics

Core Slice 1 resolution states:

- `MEASURED` — all five families are present and no material conflict/abstain state exists;
- `PARTIAL` — at least one family is explicit NO_EVIDENCE;
- `NOT_EVALUABLE` — at least one family is explicit NOT_EVALUABLE;
- `CONFLICT` — material independent conflict evidence exists;
- `ABSTAIN` — at least one family explicitly abstains.

A high arithmetic support score cannot erase material conflict or abstention.

## Threshold research boundary

The locked hypotheses are preserved in policy metadata:

- 70
- 75
- 80
- 85

Slice 1 **does not choose a winning threshold** and **does not emit ACTIVE**.

Chronological forward comparison of these hypotheses belongs to the next M6 Shadow Lab
slice. No retrospective threshold selection is allowed.

## Reuse boundary

- Existing `crypto_signal.confluence` methodology evidence remains accepted and unchanged.
- Existing `meta_intelligence` direction/state semantics are reused.
- M6 does not replace or rewrite historical confluence records.
- Future adapters may map accepted family engines into this matrix, but adapters must
  preserve original evidence identities and PIT timestamps.

## Scientific boundaries

- Confluence is not probability.
- Weighted priors are research priors, not proof of optimality.
- Quality/freshness are not hidden inside the arithmetic support score.
- Opposition remains visible rather than being subtracted away into one opaque number.
- Material contradictions remain first-class veto evidence.
- Event Risk is context/veto outside the 100-point score.
- No probability, sizing, leverage, promotion, deployment or order authority.
- REAL_CAPITAL=0.

## Acceptance checklist

1. Exact 20/25/25/15/15 prior contract.
2. Exact 70/75/80/85 threshold hypotheses preserved as research hypotheses only.
3. `82/100` can coexist with `NOT CALIBRATED`.
4. Support and opposition remain separately observable.
5. Coverage, evidence quality and freshness remain separately observable.
6. Material conflict vetoes high arithmetic support.
7. Family abstention is not overridden by arithmetic score.
8. Missing/not-evaluable families remain explicit.
9. Context mismatch, duplicate family assignment, invalid measures and identity tampering fail closed.
10. Event Risk remains outside the score.
11. Focused pytest/Ruff/mypy plus full repository Python/JavaScript/freshness regression.
12. Temporary hosted workflow removed after PASS.

Next M6 frontier after Slice 1: chronological forward threshold research for 70/75/80/85
without winner auto-selection or production promotion.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
