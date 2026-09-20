# POST-V1 BTC MULTI-TIMEFRAME PRODUCTION — ACCEPTANCE

Status: ACCEPTED
Date: 2026-09-20
Production code head: b9b8ba1662cbdb387c380318d14bba0d40f151a7
REAL_CAPITAL=0

## Scope
BTCUSDT Spot production coverage now runs on Bybit and Binance for:
- 15m direct canonical truth
- 1h aggregated only from canonical closed 15m truth
- 4h aggregated only from canonical closed 15m truth

Higher-timeframe target history is deliberately bounded at 120 candles with minimum 100.
1D and 1W remain disabled.

## Pre-production live acceptance
An isolated real-data ledger/cache proved Bybit + Binance 1h/4h before deployment:
- first pass: four contexts FROZEN
- second pass: the same four contexts ALREADY_FROZEN
- 4 immutable freezes / 4 lifecycle rows
- per-provider canonical 15m cache: 1,920 candles
- no production evidence was polluted by the acceptance run
Evidence file:
runtime/ledger/stage1_slice2_ht_live_acceptance_20260920T081255Z.txt

## Code gate
- focused activation gate: 21 PASS
- full repository pytest: 273 PASS
- Ruff PASS
- mypy PASS across 121 source files
- uv lock PASS
- git diff check PASS

## Stable production deployment
LIVE/STABLE advanced cleanly to b9b8ba1662cbdb387c380318d14bba0d40f151a7.
A production smoke inserted 15m/1h/4h evidence for both providers.
Production ledger immediately after smoke:
- 48 signal freezes
- 48 lifecycle evaluations
- Bybit 1h WATCH and 4h WATCH present
- Binance 1h WATCH and 4h WATCH present

The launchd evidence clock was then kickstarted:
- runs=34
- last exit code=0
- 15m/1h/4h all returned ALREADY_FROZEN at the owned cutoffs
- stderr remained empty

## Product visibility
The existing read-only dashboard required no data migration.
GET /api/market-radar returned 6 live contexts:
Bybit/Binance x BTCUSDT x 15m/1h/4h.
GET /api/health remained read_only=true and REAL_CAPITAL=0.

## Scientific notes
Observed 1h/4h WATCH scores remain agreement indices, not probabilities.
No success rate is inferred.
Non-15m PA period/session level evidence remains intentionally unmanufactured until
canonical 15m reference provenance is explicitly represented.
