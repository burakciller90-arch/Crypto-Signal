# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: 1 — Data Truth
State: PHASE1_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Phase 1 accepted
- Bybit and Binance Spot REST/WebSocket adapters normalize into one provider-neutral Candle contract.
- Exchange source time and local ingest time remain distinct.
- Decimal precision, closed/open state, quote volume, trade count and adapter version are preserved.
- SQLite WAL persistence is idempotent and protects finalized candle truth.
- Gap/freshness checks and explicit range completeness are implemented.
- Restart recovery backfill is paginated, grid-validated and never synthesizes missing data.
- Closed 15m is the canonical base series.
- 1h/4h/1D/1W are deterministically aggregated from complete 15m buckets.
- Daily/Weekly/Monthly/Yearly Opens are PIT-safe.
- Native Bybit higher-timeframe reconciliation passes exactly.
- Bybit/Binance cross-provider 15m grid reconciliation passes without forcing equal prices.
- Reconnect paths are tested and public WS live ingestion is verified for both providers.
- Dual-provider ingestion into one canonical store is verified.
- Integrated acceptance: 45 tests PASS; Ruff PASS; mypy PASS; all live probes PASS.

## Integrated acceptance evidence
- Full-week Bybit base: 672 x 15m.
- Derived/native exact reconciliation: 168 x 1h, 42 x 4h, 7 x 1D, 1 x 1W.
- Recent Bybit/Binance 15m grid overlap: 20/20.
- Restart recovery: deliberate 1-candle gap -> 0 on both providers.
- Second recovery: 30/30 unchanged on both providers.
- Dual-feed live smoke: five updates from each provider accepted concurrently.

## Canonical next frontier
Shared deterministic primitives — swing/peak/trough geometry used by PA, Harmonic and Elliott.
Primitive sharing must not merge methodology decision logic.
Do not begin V2+ scope. REAL_CAPITAL remains 0.
