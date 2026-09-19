# ADR 0013 — Integrated Price Action Evidence Result

Status: Accepted for PA V1 integration
Date: 2026-09-20

## Purpose
The PA / SMC / ICT V1 engine exposes one integrated, deterministic evidence result.

It combines:
- PIT-safe market structure
- FVG lifecycle and BPR
- EQH/EQL liquidity pools and sweep/SFP events
- Previous Day/Week/Month and explicit-session high/low evidence
- Daily/Weekly/Monthly/Yearly Opens when PIT-available
- displacement evidence
- reclaim/rejection interactions against explicit available levels

## Non-goals
The integrated PA result does NOT:
- create a calibrated probability
- convert evidence counts into a win rate
- create a confluence score
- call Harmonic or Elliott logic
- place or recommend an exchange order
- force a bullish/bearish setup when evidence is mixed

## Shared as-of
Every nested component is evaluated with one explicit top-level `as_of_ms`.
If the caller omits it, the top-level engine resolves it once from the latest local ingest time
and passes that same value to every nested PA component.

This prevents subtle component-to-component time drift.

## Reference-level bridge
Level interactions are evaluated only against numeric levels that are actually available:
- COMPLETE previous-period/session high-low evidence
- PIT-available periodic opens

Incomplete ranges never create numeric ReferenceLevel objects.

## Evidence summary
The integrated result may expose deterministic counts and the current structure regime for convenience.
These are descriptive metadata only, not a methodology quality score or probability.

REAL_CAPITAL remains 0.
