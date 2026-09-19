# ADR 0018 — Confluence Selection, Agreement and Score Semantics

Status: Accepted for Confluence Slice 2 implementation
Date: 2026-09-20

## Scope
This slice adds:
- current-evidence selection
- methodology-level directional resolution
- pairwise agreement / contradiction matrix
- deterministic V1 confluence score

It does not create Signal state or probability.

## Current evidence selection
Evidence is grouped by methodology.

For each methodology:
1. find the greatest market_available_at_ms
2. select every evidence item at exactly that market timestamp
3. preserve all alternatives at that timestamp

No arbitrary age window is introduced in this slice.
No older artifact competes with a newer artifact from the same methodology.

This is a current-artifact selection policy, not a claim that the selected artifact
remains economically active forever. Signal freshness/lifecycle is a later contract.
## Methodology direction
For one methodology selection:
- only bullish selected items -> BULLISH
- only bearish selected items -> BEARISH
- only neutral/unresolved items -> UNRESOLVED
- both bullish and bearish selected items -> UNRESOLVED with internal-conflict flag

Multiple alternatives pointing in the same direction remain directional agreement
inside that methodology; their count does not create extra voting weight.

Each methodology gets at most one directional vote.

## Pairwise relation
For each methodology pair:
- AGREE: both have resolved direction and directions match
- CONTRADICT: both have resolved direction and directions oppose
- INTERNAL_AMBIGUITY: at least one side contains opposing selected directions
- INSUFFICIENT: at least one side has no resolved directional evidence

No pairwise relation is a probability.
## Dominant direction
Count one vote per resolved methodology.

- bullish votes > bearish votes -> BULLISH
- bearish votes > bullish votes -> BEARISH
- tie or zero resolved votes -> UNRESOLVED

A methodology with internal directional conflict casts no vote.

## V1 deterministic confluence score
Let:
- support = number of methodologies voting for dominant direction
- opposition = number voting against dominant direction
- total methodology slots = 3

When dominant direction is unresolved, score = 0.

Otherwise:
score = (support - opposition) / 3 * 100

The stored value is rounded to two decimal places using decimal ROUND_HALF_UP.

Examples:
- 3 support / 0 oppose -> 100.00
- 2 support / 0 oppose -> 66.67
- 2 support / 1 oppose -> 33.33
- 1 support / 0 oppose -> 33.33
- 1 bullish / 1 bearish / 1 unresolved -> 0.00

This intentionally rewards independent methodology agreement and penalizes direct
directional contradiction without inventing statistical meaning.
## Scientific boundary
The confluence score is:
- not calibrated probability
- not historical win rate
- not confidence
- not expected return
- not setup quality
- not permission to trade

Harmonic residuals, Elliott rule-support fraction and PA geometry are not
normalized into the V1 score.

Their descriptive metrics remain visible separately.

## Point-in-time and semantic consistency
Every evidence item in one confluence analysis must match:
- exchange
- market type
- symbol
- timeframe
- as_of_ms

Cross-timeframe and cross-symbol confluence require a future explicit aggregation policy.

REAL_CAPITAL remains 0.
