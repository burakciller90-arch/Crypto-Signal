# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: Shared deterministic primitives
State: PRIMITIVES_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Accepted foundations
- Phase 0 Environment & Constitution accepted.
- Phase 1 Data Truth accepted with Bybit + Binance REST/WS, persistence, recovery and reconciliation.
- Shared deterministic swing primitives accepted before methodology engines.

## Primitive contract
- Strict fractal HIGH/LOW pivots require closed, gapless, single-semantics candle series.
- A pivot is not considered available at its source candle.
- Market confirmation occurs only after configured right-side candles close.
- Local observation time is tracked separately from market confirmation time.
- Equal-price plateaus do not silently become pivots.
- Same-bar HIGH+LOW outside-bar ambiguity is represented explicitly.
- Alternating compression never merges different symbol/timeframe semantics.
- Consecutive same-kind pivots retain the more extreme point deterministically.

## Acceptance evidence
- Unit/quality gate: 51 tests PASS; Ruff PASS; mypy PASS.
- Live Bybit sample: 200 closed 15m candles -> 52 pivots -> 41 alternating swings.
- Live Binance sample: 200 closed 15m candles -> 50 pivots -> 39 alternating swings.
- Repeated detection on identical input produced identical pivot tuples.
- All pivots satisfy market confirmation <= local observation time.

## Canonical next frontier
PA / SMC / ICT V1 engine.
It must consume deterministic primitives but remain independently testable and return structured evidence,
not a single bullish/bearish label.
Do not begin Harmonic/Elliott conclusions inside the PA engine.
