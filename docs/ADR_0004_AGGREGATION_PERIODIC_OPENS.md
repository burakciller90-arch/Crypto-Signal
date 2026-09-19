# ADR 0004 — Deterministic Aggregation and Periodic Opens

Status: Accepted for Phase 1 Slice 4
Date: 2026-09-19

## Canonical base
Closed 15m candles are the canonical V1 base series.

## Derived timeframes
1h, 4h, 1D and 1W candles are derived deterministically from closed 15m candles.
A derived candle is emitted only when every expected 15m source candle exists.
Incomplete buckets are reported explicitly and never silently filled.

## Calendar alignment
- 1h, 4h and 1D use UTC epoch-aligned buckets.
- 1W starts Monday 00:00 UTC.
- Weekly alignment was mechanically verified against Bybit native weekly candles.

## Precision and provenance
Derived OHLC, volume, quote volume and trade count are deterministic reductions.
Derived source type is `aggregated`.
Source timestamp and ingest timestamp are the maximum of their source candles.

## Periodic opens
Daily, Weekly, Monthly and Yearly Opens are resolved from the exact 15m boundary candle.
The system tracks:
- market availability time, and
- local observation/ingest time.

Point-in-time queries default to requiring that the boundary candle had actually been observed by the requested as-of time.

## Reconciliation evidence
A complete 672-candle 15m week was aggregated and reconciled exactly against Bybit native:
- 168 x 1h
- 42 x 4h
- 7 x 1D
- 1 x 1W

REAL_CAPITAL remains 0.
