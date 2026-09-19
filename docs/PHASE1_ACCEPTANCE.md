# PHASE 1 — DATA TRUTH ACCEPTANCE

Status: ACCEPTED
Date: 2026-09-19

- [x] Provider-neutral Candle contract exists and rejects impossible OHLC/time data.
- [x] 15m is the canonical base candle interval.
- [x] Bybit REST backfill normalizes real public market data.
- [x] Live Bybit WebSocket ingestion works with reconnect handling.
- [x] Binance REST/WebSocket reaches semantic parity behind the same Candle contract.
- [x] Persistence preserves candle identity, provenance and closed/open state.
- [x] Duplicate equivalent delivery is idempotent.
- [x] Missing intervals and stale feeds are detectable and explicit.
- [x] Restart/recovery backfill reports expected/missing opens and never synthesizes data.
- [x] 1h, 4h, 1D and 1W are deterministically aggregated from closed 15m candles.
- [x] Daily/Weekly/Monthly/Yearly Opens are deterministic and PIT-safe.
- [x] Native-source reconciliation detects semantic/material mismatches.
- [x] Bybit derived higher-timeframe candles reconcile exactly with native Bybit candles.
- [x] Cross-provider reconciliation verifies shared UTC grid without forcing equal prices.
- [x] Restart/recovery closes a deliberate gap for both providers and is idempotent on rerun.
- [x] Unit tests and static-quality gates pass.
- [x] Bounded concurrent Bybit+Binance live ingestion passes.
- [x] No V2+ market microstructure or execution scope was introduced.

## Key mechanical evidence
- 45 tests pass before integrated acceptance rerun.
- Full-week Bybit reconciliation: 672 x 15m -> 168 x 1h, 42 x 4h, 7 x 1D, 1 x 1W.
- Binance/Bybit recent 15m grid: 20/20 overlap in Slice 5 live gate.
- Restart recovery: intentional 1-candle gap -> 0 for both Bybit and Binance.
- Second recovery: 30/30 unchanged for both providers.
- Dual-feed live smoke: five Bybit + five Binance updates in one canonical store.

`REAL_CAPITAL = 0`
