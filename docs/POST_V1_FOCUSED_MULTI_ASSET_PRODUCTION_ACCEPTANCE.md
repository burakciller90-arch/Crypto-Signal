# POST-V1 FOCUSED MULTI-ASSET PRODUCTION — ACCEPTANCE

Status: ACCEPTED
Date: 2026-09-20
Production code head: 7020413188d633b2b5a9661356c2fe319f256a34
REAL_CAPITAL=0

## Scope
The deliberately small Birthday Edition market universe is now:
- BTCUSDT
- ETHUSDT
- SOLUSDT

For each symbol, Bybit Spot and Binance Spot run:
- 15m direct canonical truth
- 1h aggregated from canonical closed 15m
- 4h aggregated from canonical closed 15m

No 1D/1W production activation and no additional assets are included in this slice.

## Isolated real-data acceptance
Before production activation, ETHUSDT + SOLUSDT were tested on separate acceptance ledger/cache paths:
- 12 provider/symbol/timeframe contexts
- first pass: 12/12 immutable freezes
- second pass: 12/12 ALREADY_FROZEN
- 12 lifecycle rows
- 1,920 canonical 15m cached candles for each provider/symbol pair
Evidence:
runtime/ledger/stage2_symbols_live_acceptance_20260920T081651Z.txt

Observed states were not forced:
- ETH contexts were WATCH in the acceptance sample
- SOL 15m/1h were WATCH
- SOL 4h was NEUTRAL on both providers

## Code gate
- focused coverage/runtime gate: 21 PASS
- full repository pytest: 273 PASS
- Ruff PASS
- mypy PASS across 121 source files
- uv lock PASS
- git diff check PASS

## Stable production deployment
LIVE/STABLE advanced to:
7020413188d633b2b5a9661356c2fe319f256a34

Production smoke completed without errors:
- 60 total immutable freezes
- 60 lifecycle evaluations
- 18 distinct live provider/symbol/timeframe contexts
- Dashboard Market Radar immediately exposed all 18 contexts

The automatic launchd evidence clock was kickstarted after deployment:
- run count: 36
- final state: not running (normal between one-shot intervals)
- last exit code: 0
- all 18 owned cutoffs returned ALREADY_FROZEN
- stderr empty

## Product meaning
The platform is no longer a single BTC/15m pilot.
It now monitors a focused high-liquidity universe across three useful timeframes while preserving
provider separation, immutable evidence, no forced signal creation and no fabricated probability.

## Next frontier
Birthday Edition product work now moves to the Turkish-first premium Mission Control,
then visual chart intelligence and decision-quality explanations.
