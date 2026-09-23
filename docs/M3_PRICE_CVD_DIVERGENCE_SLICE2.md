# M3 Slice 2 — PIT price/CVD divergence

Development-only; REAL_CAPITAL=0. Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`.

Reuse accepted M3 Slice 1 window-local public-trade Delta/CVD and independent M2 normalized order-book snapshots. Compare the *same exchange, instrument, symbol and overlapping point-in-time window*. Snapshot event/source/response/ingest and trade event/source/ingest timestamps must all be at or before the freeze cutoff. Reject stale, sparse, discontinuous, duplicate and mixed-context input. Never synthesize missing price or flow.

A bullish candidate requires measured downward independent book-mid movement and materially opposing positive window-local CVD; bearish candidate requires upward book-mid movement and materially opposing negative window-local CVD. Both require explicit versioned thresholds, source-coverage and freshness evidence. The no-divergence and UNRESOLVED states are first-class. Candidate is neither proven reversal, calibrated probability, causal absorption, actor attribution, nor paper-trade authority.

Keep source identities, independent mid-price observations, accepted temporal-flow evidence identity, exact freeze cutoff, uncertainty and deterministic content identity. Future or late-ingested evidence cannot rewrite a historical freeze. Full hosted regression is mandatory before acceptance. A separate M3 Slice 3 later combines independent book replenishment with aggressive flow for bounded absorption candidates.
