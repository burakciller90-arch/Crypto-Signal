# M3 Order Flow 2.0 — Slice 2A: PIT Price/CVD Divergence

Status: DEVELOPMENT ONLY. Parent issue #868; governing locked roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`. REAL_CAPITAL=0.

## Reuse, not replacement

Reuse accepted M3 Slice 1 `TemporalFlowEvidenceFreeze` as the **window-local** trade tape and CVD source; do not edit its existing immutable semantics. Pair its eligible public trades with real `Candle` observations on an exact exchange / market type / symbol / timeframe. Preserve input evidence and frozen identity. Absorption is a separate M3 Slice 2B.

## Minimum point-in-time evidence

- One exact `as_of_ms` and source context. The trade freeze must be measured/GOOD at this as-of.
- Only **closed** candles with `close_time_ms`, `source_timestamp_ms` and `ingested_at_ms` all at or before the cutoff.
- Only public-trade records already frozen in M3 Slice 1, excluding block/RPI from flow calculations.
- Two actually confirmed price pivots of the same type with a completed neighboring candle on each side; no future or provisional pivot.
- Enough real, timely trades to compute **CVD at each pivot's own close time**. Bucket gaps are not filled; no backfilled trade or interpolated CVD at an absent timestamp.
- No mixed venue, symbol, timeframe or source chronology, no duplicated candle identity, no stale price/flow reference.

## Bounded candidate semantics

- Bullish candidate: a later **lower price low** but higher window-local CVD at the matched later pivot close.
- Bearish candidate: a later **higher price high** but lower window-local CVD at that matched close.
- Both comparisons use versioned minimum price displacement and minimum CVD-notional separation, with minimum intervening trade count and time span.
- `NONE` and `UNRESOLVED` are valid. A candidate is **neither** a trading order nor a calibrated probability. Contradictory price/CVD behavior must not be silently hidden.
- Preserve earlier/later pivot timestamps, OHLC price, CVD at exact matched endpoints, delta, trade count, freshness, uncertainty and deterministic frozen source identities.

## Acceptance

- Constructed bullish, bearish and no-divergence examples.
- Future, late-ingested or unclosed candles and trades cannot change a historical freeze.
- Input ordering independence; duplicated/mixed-context data and evidence-identity tampering fail closed.
- Sparse/stale/missing price and trade evidence produces explicit unresolved status, not a fabricated divergence.
- Synthetic test windows must be tied to actual known trade observations; no invented missing intervals.
- Focused + full hosted pytest/Ruff/mypy/JS/freshness PASS before main merge.
- No live collector, canonical paper policy, probability, Cursor worker or real-money authority.
