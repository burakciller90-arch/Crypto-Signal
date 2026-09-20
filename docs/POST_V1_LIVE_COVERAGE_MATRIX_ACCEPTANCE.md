# Post-V1 Live Coverage Matrix Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Purpose
Replace hard-coded live evidence scope with an explicit versioned coverage
contract without silently expanding production.

## Accepted current pilot
The stable production pilot remains exactly:
- BTCUSDT
- 15m
- Spot
- Bybit
- Binance
- freeze_limit=500
- minimum_closed_candles=100

No production scope was widened by this slice.

## Coverage contract
LiveCoverageContext makes these dimensions explicit:
- exchange
- market type
- symbol
- target timeframe
- source strategy
- freeze history limit
- minimum closed history
- enabled flag

LiveCoveragePlan:
- has an explicit version
- rejects duplicate market identities
- exposes enabled contexts
- exposes per-run base-15m budget

## Data Truth guard
Accepted rule:
- 15m -> DIRECT_CANONICAL_15M
- 1h / 4h / 1D / 1W -> AGGREGATE_CANONICAL_15M only

A higher timeframe configured with direct/native exchange candles is rejected.

This preserves the accepted Data Truth rule:
canonical higher timeframe truth is deterministically aggregated from canonical
closed 15m candles; native higher timeframe data is reconciliation-only.

## Expansion remains disabled
post_v1_timeframe_candidates() describes:
- 2 enabled 15m contexts
- 8 disabled higher-timeframe candidates

Higher-timeframe candidates cannot be activated through the current runner
because the runner fails closed unless the source strategy is
DIRECT_CANONICAL_15M.

Therefore this slice cannot accidentally expand production before canonical
aggregation acquisition is implemented and accepted.

## Load budget
Base 15m requirements for a 500-target-candle analysis window per provider:
- 15m: 500
- 1h: 2,000
- 4h: 8,000
- 1D: 48,000
- 1W: 336,000

Minimum 100 weekly target candles alone require:
- 67,200 base 15m candles per provider

This makes clear why higher-timeframe activation must not be implemented as one
naive REST request per run.

## Runner refactor
ops/run_live_evidence_clock.py now reads LiveCoveragePlan.current_pilot()
instead of hard-coding provider/symbol/timeframe parameters.

Adapter mapping is typed through MarketDataAdapter.

The runner logs:
- provider
- symbol
- timeframe
- status

Behavior for the accepted production pilot is unchanged.

## Mechanical acceptance
Coverage + live-freeze focused gate:
- 10 tests PASS
- Ruff PASS
- mypy PASS

Full repository:
- 262 tests PASS
- Ruff PASS
- mypy PASS
- uv lock PASS
- git diff check PASS

## Production deployment
NOT DEPLOYED by this slice.

LIVE/STABLE remains pinned to its accepted source and current BTCUSDT 15m
production evidence clock.

## Canonical next frontier
Canonical higher-timeframe live evidence preparation:
1. create a deterministic target-timeframe builder from canonical closed 15m
2. make incomplete target buckets explicit
3. preserve PIT observation timestamps through aggregation
4. define paginated/base-history acquisition rather than oversized one-shot REST
5. prove target-window equivalence against accepted aggregation contracts
6. only then allow a disabled higher-timeframe coverage context to become eligible
7. do not activate production coverage until load/runtime acceptance passes

REAL_CAPITAL remains 0.
