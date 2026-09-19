# ADR 0012 — Displacement and Level Interaction Evidence

Status: Accepted for PA Slice 4B implementation
Date: 2026-09-20

## Displacement
Displacement is treated as explicit deterministic evidence, not a visual adjective.

V1 config:
- lookback bars: 20
- body multiple versus median prior body: 2.0
- range multiple versus median prior range: 1.5
- minimum body/range fraction: 0.60

All thresholds are fields on DisplacementConfig and are stored in the result.
The current candle is never included in its own baseline.

A candle is bullish displacement when:
- close > open
- body >= configured multiple of median body over the prior lookback
- total range >= configured multiple of median range over the prior lookback
- body/range >= configured minimum

Bearish is symmetric with close < open.

Market confirmation time is candle close; observation time is candle ingest time.

## Explicit reference levels
Reclaim/rejection is evaluated only against a ReferenceLevel that carries:
- label
- numeric price
- market availability time
- local observation time
- source identity/description

A level cannot generate interactions before both market and local availability.

## Interaction rules
Bullish reclaim:
- previous close < level
- current candle trades level
- current close > level

Bearish reclaim:
- previous close > level
- current candle trades level
- current close < level

Bullish rejection:
- previous close >= level
- current low < level
- current close >= level

Bearish rejection:
- previous close <= level
- current high > level
- current close <= level

If a candle simultaneously satisfies opposing rejection geometry at an exactly-on-level state,
the event is AMBIGUOUS_TWO_SIDED rather than guessed.

## Prior-period/session level conversion
Only COMPLETE high/low range evidence may become ReferenceLevel objects.
Incomplete ranges produce no numeric reference level.

## Scope
These are descriptive evidence objects, not trade signals.
No Harmonic/Elliott logic is used.

REAL_CAPITAL remains 0.
