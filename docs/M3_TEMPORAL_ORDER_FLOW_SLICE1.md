# M3 Order Flow 2.0 — Slice 1: PIT Temporal Trade Tape

Status: isolated development slice; no production authority. Governing roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`.

## Reuse boundary
Reuse accepted Stage 8 `order_flow_microstructure.py` (book imbalance and single-window taker-flow). Do not recreate it or modify the accepted M2 sweep/heatmap stack. Slice 1 adds chronological public-trade evidence only.

## Inputs and cutoff
Normalized `PublicTradeObservation` from one exact exchange, market type and symbol. Eligible observations must have event, source and ingestion timestamps all <= `as_of_ms`; future and late-ingested observations are excluded. Each snapshot preserves exact trade identities and a deterministic freeze hash. Duplicate identities and mixed market contexts fail closed. Block/RPI trades are retained as excluded source evidence but cannot contribute to book-eligible aggressive-flow metrics.

## Metrics
Versioned fixed-window configuration, non-empty chronological UTC buckets, taker buy/sell notional, bucket delta, cumulative **window-local** CVD (not exchange-global CVD), count-based trade velocity, imbalance, large trade candidate counts under an explicit research threshold, first/last eligible trade price context and freshness. Buckets never fill missing gaps with fabricated trades; sparse/stale data is `UNRESOLVED`.

## Claims deliberately not made
Trade delta/CVD is not calibrated probability, a buy/sell signal, institutional attribution, proven absorption, or price/CVD divergence against independent candles. Absorption, price/flow divergence and sweep interaction are separate later M3 slices requiring additional PIT price/book evidence. No automatic confluence weight promotion; REAL_CAPITAL=0.

## Acceptance
- deterministic input-order-independent evidence and freeze identities;
- positive/negative delta and cumulative window-local CVD;
- last bucket and time window truth;
- block/RPI exclusion without deleting raw evidence;
- future/late exclusion;
- stale/sparse/gapped and invalid context fail-closed;
- no canonical Paper Fund mutation;
- focused + full hosted test/Ruff/mypy/JS/freshness PASS before main integration.
