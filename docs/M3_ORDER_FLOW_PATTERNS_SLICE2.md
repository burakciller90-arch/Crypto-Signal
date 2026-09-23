# M3 Slice 2 — Price/CVD Divergence + Bounded Absorption

Status: development slice after accepted M3 Temporal Order Flow Slice 1  
REAL_CAPITAL: 0  
Parent issue: #868  
Parent roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Scope

This slice adds two separate immutable evidence freezes. They are candidates, not
predictions or trade commands.

### A. Price/CVD divergence

Inputs:
- closed candles from one exact exchange / market / symbol / timeframe;
- accepted `TemporalFlowEvidenceFreeze` from the same exact market and PIT cutoff.

The engine compares chronological local swing pairs. A bullish candidate requires a
lower price low while **window-local** CVD is higher. A bearish candidate requires a
higher price high while window-local CVD is lower.

Each comparison endpoint must have real public-trade coverage inside that candle and a
bounded gap between the last eligible trade and candle close. Missing buckets are never
interpolated. Exchange-global CVD is never claimed.

### B. Absorption

Inputs:
- accepted temporal public-trade flow freeze;
- accepted Liquidity Structure freeze;
- exact same market and `as_of_ms`.

Bid absorption requires sell aggression around a visible bid level together with actual
book replenishment and bounded downside price response. Ask absorption is the symmetric
buy-aggression case.

A large wall alone, a large print alone, or flat price alone is insufficient.

## Scientific boundary

- future or late-ingested candles/trades/book observations cannot rewrite historical
  freezes;
- mixed venue / market / symbol / timeframe inputs fail closed;
- duplicate candle identities fail closed;
- unresolved upstream flow or liquidity evidence yields UNRESOLVED rather than a forced
  candidate;
- divergence is not a directional forecast;
- absorption is not proof of iceberg execution, actor identity or manipulation;
- no arbitrary probability/confidence score is emitted;
- REAL_CAPITAL=0.

## Acceptance

- deterministic under input reordering;
- bullish and bearish divergence positives;
- weak/misaligned/no-coverage divergence negatives;
- bid and ask absorption positives;
- wall-only, print-only and excessive-price-response negatives;
- future/late candle exclusion;
- freeze/evidence tamper rejection;
- focused + full hosted pytest/Ruff/mypy/JS/freshness PASS;
- no production cutover or paper mutation.
