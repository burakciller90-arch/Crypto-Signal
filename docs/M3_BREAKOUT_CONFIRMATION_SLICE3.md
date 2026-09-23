# M3 Slice 3 — Breakout Confirmation / Failure + Sweep/Absorption Interaction

Status: development slice after accepted M3 Slice 2  
REAL_CAPITAL: 0  
Parent roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Purpose

A price crossing a level is not automatically a confirmed breakout.

This slice combines already-frozen evidence instead of recomputing it:

- accepted temporal public-trade flow;
- accepted liquidity-sweep evidence;
- accepted absorption evidence;
- closed point-in-time candles.

## Confirmation candidate

For an upside confirmation candidate:

- an ask-side sweep candidate exists;
- latest closed candle accepts above the sweep level by a configured minimum distance;
- window-local taker imbalance confirms the same direction;
- the sweep has not recovered/reclaimed the level;
- no nearby ask-absorption candidate contradicts continuation.

Downside confirmation is symmetric.

## Failure candidate

For an upside breakout-failure candidate:

- the ask-side sweep recovered/reclaimed;
- latest closed candle is back inside the bounded re-entry zone;
- nearby ask absorption is present.

Downside failure is symmetric with bid absorption.

## Scientific boundary

- a touched or crossed level alone is insufficient;
- confluence of sweep/flow/candle/absorption is still evidence, not probability;
- no future-return claim;
- no actor, institution, stop-hunt or iceberg attribution;
- all upstream freezes must share exact market and `as_of_ms`;
- absorption must use the exact same temporal flow freeze;
- only closed PIT candles are consumed;
- late/future candles cannot rewrite a historical freeze;
- REAL_CAPITAL=0.

## Acceptance

- deterministic input ordering;
- upside and downside confirmation positives;
- sweep without flow/close acceptance negative;
- recovery + matching absorption failure positive;
- recovery without absorption negative;
- mixed context/as-of mismatch fail closed;
- late/future candle exclusion;
- identity tamper rejection;
- hosted focused + full pytest/Ruff/mypy/JS/freshness PASS;
- no production activation or paper mutation.
