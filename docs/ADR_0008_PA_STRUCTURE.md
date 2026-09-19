# ADR 0008 — PA/SMC/ICT Market-Structure Rules

Status: Accepted for PA Slice 1 implementation
Date: 2026-09-19

## Scope of this slice
This slice implements only deterministic structure evidence:
- confirmed swings,
- HH/LH/HL/LL-style swing relations,
- close-based BOS,
- CHoCH/MSB when break direction flips the established break regime,
- current structure direction,
- available PIT-safe Daily/Weekly/Monthly/Yearly Opens.

FVG, BPR, mitigation, EQH/EQL, sweeps/SFP and displacement/reclaim are separate later slices.

## Break rule
A confirmed swing level becomes structurally breakable only after its right-side confirmation.
A candle creates a structural break only when its close is strictly beyond the latest available
unbroken swing level in that direction.

Wick-only penetration is not BOS/CHoCH in this slice.

## Classification
- First observed structural break establishes the regime and is BOS.
- A later break in the same direction is BOS.
- A later break opposite the established regime is CHoCH/MSB and flips the regime.

## Point-in-time rule
Break market time is the breaking candle close time.
Break observation time is the breaking candle ingest time.
No pivot may be used before its own market confirmation.

## Independence
This PA structure layer consumes shared deterministic swings.
It does not call Harmonic or Elliott logic and does not emit trade orders.

REAL_CAPITAL remains 0.
