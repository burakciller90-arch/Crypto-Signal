# POST-V1 HIGHER-TIMEFRAME RUNNER INTEGRATION — ACCEPTANCE

Status: ACCEPTED
Date: 2026-09-20
REAL_CAPITAL=0

## Scope
The live evidence runner can now execute both accepted coverage strategies:
- DIRECT_CANONICAL_15M
- AGGREGATE_CANONICAL_15M

The higher-timeframe path:
1. obtains the latest closed canonical 15m cutoff,
2. prepares the exact required 15m history through CandleStore/backfill,
3. fails closed on missing base candles or incomplete aggregate buckets,
4. aggregates only canonical closed 15m truth,
5. enters the same immutable freeze_live_candles() pipeline.

## Runtime isolation
The production current_pilot() coverage plan was not changed.
No 1h/4h/1D/1W production context is activated by this acceptance.
A dedicated canonical 15m cache path is available for higher-timeframe preparation.

## Acceptance evidence
- higher-timeframe runner/preparation/freeze focused tests: 14 PASS
- aggregate path first freeze: PASS
- repeated aggregate path source-cutoff idempotence: PASS
- incomplete base history fails closed with zero freeze rows: PASS
- full repository pytest: 273 PASS
- Ruff: PASS
- mypy: PASS across 121 source files
- uv lock: PASS
- runner py_compile: PASS
- git diff check: PASS

## Next frontier
Stage 1 Slice 2: prove BTCUSDT 1h and 4h against real Bybit and Binance data on isolated
acceptance ledger/cache paths before any stable production coverage activation.
