# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: 1 — Data Truth
State: SLICE1_REST_CONTRACT_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Phase 0
Accepted. Isolation, pinned runtimes, architecture/contracts and quality baseline are established.

## Phase 1 accepted evidence
- Provider-neutral immutable Candle contract exists.
- Decimal OHLCV rules and impossible-data validation exist.
- Exchange event timestamp and local ingest timestamp are distinct.
- V1 timeframe mapping is explicit.
- Bybit V5 Spot selected as first adapter; Binance remains planned second adapter.
- Bybit REST kline normalization sorts chronologically and preserves closed/open state.
- Unit/quality gate: 13 tests passed; Ruff PASS; mypy PASS.
- Live BTCUSDT 15m REST probe returned five gapless candles.
- Live probe observed four closed candles and one current open candle as expected.

## Canonical next slice
Phase 1 Slice 2 — SQLite persistence/provenance + idempotent writes + gap/freshness detection.
Do not begin methodology engines or V2+ scope.
