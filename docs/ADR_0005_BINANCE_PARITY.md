# ADR 0005 — Binance Parity and Cross-Provider Reconciliation

Status: Accepted for Phase 1 Slice 5
Date: 2026-09-19

## Decision
Binance Spot is the second V1 market-data adapter behind the same provider-neutral Candle contract.

## REST semantics
- Klines come from Binance Spot REST.
- Binance server time is fetched separately so exchange time remains distinct from local ingest time.
- Decimal values remain Decimal.
- Native close time, quote volume, trade count and closed/open state are preserved.

## WebSocket semantics
- Raw kline streams are normalized into the same Candle contract.
- Event time `E` is preserved as source time.
- Kline `x` is the closed/finalized flag.
- Protocol ping/pong remains enabled.
- The reconnect iterator reconnects after transient connection failure.

## Cross-provider reconciliation
Different exchanges are not expected to have identical OHLCV.
Parity therefore means:
- same requested symbol semantics,
- same UTC timeframe grid,
- same candle-bound rules,
- same open/closed semantics,
- compatible provenance fields.

Price differences are measured in basis points and reported; they are not forced to equality.

## Live evidence
For the latest 20 BTCUSDT 15m candles:
- grid overlap: 20/20
- Bybit-only opens: none
- Binance-only opens: none
- median absolute close spread: ~0.56 bps
- maximum absolute close spread: ~1.88 bps

Binance 1W alignment was also verified as Monday 00:00 UTC.
REAL_CAPITAL remains 0.
