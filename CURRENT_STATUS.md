# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: 1 — Data Truth
State: SLICE5_BINANCE_PARITY_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Accepted Phase 1 evidence
- Bybit and Binance Spot REST/WebSocket adapters share one provider-neutral Candle contract.
- Exchange source time remains distinct from local ingest time.
- SQLite canonical persistence/finalization rules are shared across providers.
- Gap/freshness checks, deterministic aggregation and PIT-safe periodic opens are established.
- Binance 1W starts Monday 00:00 UTC, matching the canonical weekly grid.
- Cross-provider reconciliation compares semantic grid and measures price spread rather than forcing equality.
- Unit/quality gate: 43 tests passed; Ruff PASS; mypy PASS.
- Live BTCUSDT 15m cross-provider grid overlap: 20/20; no provider-only timestamps.
- Live median absolute close spread: ~0.56 bps; maximum: ~1.88 bps.
- Live Binance WS smoke: first update INSERTED, second UPDATED, canonical row count 1.

## Canonical next slice
Phase 1 Slice 6 — restart/recovery backfill, explicit range completeness,
bounded dual-feed soak and integrated Phase 1 acceptance.
Do not begin methodology engines until Phase 1 acceptance passes.
