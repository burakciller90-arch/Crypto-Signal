# M3 Order Flow 2.0 — Slice 2: PIT Price–Flow Mismatch Candidates

Status: isolated development only. Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`.
Predecessor: accepted Stage 8 `order_flow_microstructure.py` and M3 Temporal Flow Slice 1.

## Evidence and temporal contract

Combine two **independent** frozen evidence sources:
1. one accepted M3 `TemporalFlowEvidenceFreeze` covering a suitable window of book-eligible public trades; and
2. closed `Candle` observations from the same exact exchange, market type, asset and timeframe.

All consumed price and trade evidence must predate the analysis `as_of_ms` by open/close/event/source/ingest cutoffs. Source context and flow-freeze identity must match. Duplicate candles and cross-source mixing fail closed. Required two anchor candles must lie inside one same temporal-flow freeze window and have adequate eligible public trades in their intervals. Sparse, stale or gapped evidence remains `UNRESOLVED`.

## Limited calculation

Choose the earliest and latest closed anchor candles in the accepted price window. Measure close-to-close price displacement in basis points against book-eligible aggressive-flow delta **between the anchor closes**, using the same window-local CVD series. If price rises by a versioned minimum displacement while intervening CVD falls by a versioned notional threshold, emit `BEARISH_PRICE_FLOW_MISMATCH_CANDIDATE`. Reverse signs emit `BULLISH_PRICE_FLOW_MISMATCH_CANDIDATE`. Otherwise `NO_MISMATCH`. Include explicit consumed-trade IDs and immutable candle payload identities.

Two anchor candles are **not** proof of classical swing-pivot CVD divergence, absorption, distribution, manipulation, institution or predictive probability. Record that public trade feed coverage may remain unproven. An actual multi-swing divergence model is a separate forward-validated extension, not silently asserted here.

## Acceptance

- exact-window deterministic ordering and immutable price/flow freeze hashes;
- independent closed-price versus same-window trade-flow evidence;
- both directional mismatch candidates and no-mismatch;
- threshold-versioned no-activity/abstain semantics;
- future/late/uncertain coverage fail closed;
- duplicate/mixed context rejected;
- no confluence promotion or Paper Fund mutation;
- focused+full hosted pytest/Ruff/mypy/JS/freshness PASS.
REAL_CAPITAL=0.
