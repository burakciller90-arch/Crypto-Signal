# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: 1 — Data Truth
State: SLICE2_PERSISTENCE_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Accepted Phase 1 evidence
- Provider-neutral immutable Candle contract exists.
- Bybit V5 Spot REST normalization is live-verified.
- SQLite canonical candle store runs in WAL mode.
- Decimal values are persisted as text, not float.
- Duplicate equivalent delivery is idempotent.
- Newer open candles may update; stale open updates are ignored.
- Open candles may finalize; finalized candles cannot reopen.
- Conflicting finalized truth raises an explicit error.
- Gap detection and freshness assessment are explicit.
- Unit/quality gate: 23 tests passed; Ruff PASS; mypy PASS.
- Live persistence probe: 10 inserts, then 10 unchanged, row count 10, no gaps, fresh state.

## Repository integrity correction
The root runtime ignore rules are anchored as `/data/`, `/runtime/`, `/secrets/`.
This prevents source package paths such as `src/crypto_signal/data/` from being ignored.

## Canonical next slice
Phase 1 Slice 3 — Bybit WebSocket live candle ingestion + reconnect/backoff + closed-candle persistence.
Do not begin methodology engines or V2+ scope.
