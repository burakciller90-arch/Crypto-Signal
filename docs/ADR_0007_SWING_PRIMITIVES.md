# ADR 0007 — Shared Deterministic Swing Primitives

Status: Accepted for pre-methodology implementation
Date: 2026-09-19

## Purpose
PA/SMC/ICT, Harmonic and Elliott need a common deterministic geometric substrate,
but they must not share methodology conclusions.

## Primitive
A confirmed pivot records:
- HIGH or LOW kind,
- source candle identity/index/time,
- pivot price,
- left/right confirmation windows,
- market confirmation time,
- local observation time.

## Point-in-time rule
A pivot at candle i does not exist for the system at candle i.
It becomes market-confirmed only after the configured right-side closed candles exist.
Its observed time is the latest ingest time in the full confirmation window.

## Detection rule
Initial shared detection uses strict fractal extrema:
- HIGH: candidate high is strictly greater than all highs in left/right windows.
- LOW: candidate low is strictly lower than all lows in left/right windows.
- equal-price plateaus do not silently become pivots.

## Input truth
Primitive detection requires:
- one exchange/market/symbol/timeframe,
- chronological closed candles,
- canonical timeframe spacing without gaps.

Open candles, mixed semantics, duplicates, out-of-order data and hidden gaps are rejected.

## Alternating swing view
A separate deterministic compression converts confirmed pivots to alternating HIGH/LOW swings.
Consecutive same-kind pivots retain the more extreme price.
This is geometry only; it is not a Harmonic, Elliott or PA decision.

REAL_CAPITAL remains 0.
