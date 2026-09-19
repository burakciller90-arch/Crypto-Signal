# ADR 0006 — Restart Recovery and Integrated Data-Truth Acceptance

Status: Accepted for Phase 1 Slice 6
Date: 2026-09-19

## Restart recovery
Historical recovery uses provider-neutral paginated REST backfill behind the MarketDataAdapter contract.

For a requested timeframe-aligned open-time range:
- every expected candle open is known deterministically,
- adapters are queried in bounded pages,
- returned candles are validated for symbol, timeframe, grid and requested range,
- historical recovery requires closed candles,
- missing opens are reported explicitly,
- missing data is never synthesized.

## Idempotence
Recovered candles pass through the canonical CandleStore policy.
A repeated equivalent backfill is therefore unchanged rather than duplicated or rewritten.

## Live restart evidence
For both Bybit and Binance BTCUSDT 15m:
- a stored 30-candle historical range was created with one intentional internal gap,
- recovery reduced the gap from 1 to 0,
- the first recovery inserted exactly one missing candle,
- a second recovery returned 30 unchanged candles.

## Bounded dual-feed soak
Bybit and Binance public kline WebSockets were ingested concurrently into one SQLite store.
Five updates from each provider were accepted.
Provider identity remained isolated by the canonical candle key.

## Boundary
This acceptance proves V1 Data Truth mechanics, not indefinite production uptime.
Long-running operational soak and launchd supervision remain later production-hardening work.

REAL_CAPITAL remains 0.
