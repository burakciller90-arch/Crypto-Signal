# CURRENT STATUS

Updated: 2026-09-20
Project: Crypto Signal
Phase: PA / SMC / ICT V1
State: PA_SLICE4B_DISPLACEMENT_INTERACTIONS_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504`
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Accepted PA layers
- Slice 1 — PIT-safe market structure
- Slice 2 — FVG lifecycle + BPR
- Slice 3 — EQH/EQL liquidity pools + sweep/SFP
- Slice 4A — complete prior-period and explicit-session high/low levels
- Slice 4B — deterministic displacement + explicit-level reclaim/rejection

## Slice 4B contract
- Displacement thresholds are explicit config, not hidden heuristics.
- Current candle is never part of its own rolling baseline.
- Default V1 baseline: 20 bars; body x2.0; range x1.5; body/range >= 0.60.
- Reclaim/rejection only evaluates explicit ReferenceLevel objects.
- Reference levels carry market availability and local observation times.
- Incomplete prior-period/session ranges produce no numeric reference level.
- Periodic open levels preserve their own PIT availability.
- Opposing same-candle rejection geometry at an exactly-on-level state is explicit ambiguity.

## Acceptance evidence
- 94 tests PASS.
- Ruff PASS.
- mypy PASS.
- Live Bybit: 4,794 closed 15m candles; 86 displacement events; 11 reference levels; 194 interactions.
- Bybit displacement directions: 44 bearish / 42 bullish.
- Live Binance: 4,794 closed 15m candles; 87 displacement events; 11 reference levels; 189 interactions.
- Binance displacement directions: 44 bearish / 43 bullish.
- Deterministic repeat equality PASS for displacement and interactions.
- All live interaction events occur only after market/local level availability.

## Canonical next frontier
PA integrated result and PA V1 acceptance gate.
The integrated PA object must combine evidence without converting it into fake probability or a trade order.
Only after PA acceptance may Harmonic V1 begin.
REAL_CAPITAL remains 0.
