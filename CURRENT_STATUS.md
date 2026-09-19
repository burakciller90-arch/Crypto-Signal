# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: 1 — Data Truth
State: SLICE3_LIVE_WS_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Accepted Phase 1 evidence
- Provider-neutral Candle contract and Bybit REST adapter are live-verified.
- SQLite WAL canonical persistence and gap/freshness checks are live-verified.
- Bybit V5 Spot WebSocket kline parser validates topic, interval and time bounds.
- Bybit application heartbeat is sent every 20 seconds.
- Transient reconnect uses the websockets asyncio reconnect iterator and re-subscribes.
- Local forced-disconnect test proved two subscriptions across reconnect.
- Generic CandleIngestor persists stream events through canonical finalization rules.
- Open-to-closed persistence transition is unit-tested.
- Live Bybit BTCUSDT 15m smoke received two WebSocket updates for the same candle:
  first INSERTED, second UPDATED, canonical row count remained 1.
- Unit/quality gate: 27 tests passed; Ruff PASS; mypy PASS.

## Canonical next slice
Phase 1 Slice 4 — deterministic 15m -> 1h/4h/1D/1W aggregation + PIT-safe periodic opens.
Do not begin methodology engines or V2+ scope.
