# R25 Slice 4 — Exact Decision Composition Replay

Status: development candidate. REAL_CAPITAL=0.

This slice proves that already-accepted evidence can travel through one deterministic lineage:

accepted Geometry proof + accepted M2–M5 adapters + exact Event Risk + optional exact-scope R19
-> Unified Decision Runtime
-> R20 forecast
-> R20.5 Decision Proof
-> immutable decision ledger
-> read-only Product API / GALACTECH evidence surface.

## No evidence fabrication

The composition layer does **not** create market evidence.

It requires an upstream accepted Geometry family and exactly two geometry proof domains:
- FROZEN_CHART
- CONSUMED_CANDLES

If their exact source identities do not cover the Geometry family source identities, the existing Unified Decision Runtime rejects the decision.

The M2–M5 bundle is the accepted Slice 3 output. Missing families remain NO_EVIDENCE / INSUFFICIENT.

Event Risk is carried as a neutral context proof with exact circuit-breaker, event-risk, news and market-quality identities. Event state can block/caution/abstain elsewhere in the runtime; the proof itself is not mislabeled as bullish or bearish.

R19 probability is absent by default. A probability slice becomes AVAILABLE only when an exact CalibratedProbabilityEvidence and matching CalibrationScope are supplied and were already available by the signal PIT cutoff.

## Replay acceptance

The focused acceptance verifies:
- exact chart/candle IDs remain in the Decision Proof;
- exact M3 microstructure and temporal-flow freeze IDs remain in the proof;
- missing M4/M5 data remains insufficient rather than synthesized;
- Event Risk constituent identities remain visible;
- forecast + proof + feed are atomically persisted;
- read-only Product API returns the exact persisted proof identity and evidence IDs;
- scope-without-calibration cannot create probability;
- geometry source/proof mismatch fails closed.

This slice is still development/replay infrastructure. It does not activate a 7/24 writer, mutate canonical Epoch 2 NAV, enable exchange credentials/orders, deploy production UI, resume wake/lease, or use real money.

## Next frontier

After hosted focused + whole-repository acceptance:
1. bind richer already-accepted evidence freezes (Liquidation Heatmap, Absorption/Divergence, Derivatives Crowding, wallet cohorts / transfer clusters) without inventing directional semantics;
2. add an idempotent shadow/paper decision writer around this exact composition path;
3. run bounded replay/crash-restart tests;
4. only after that consider a separately-authorized UID504 production activation.