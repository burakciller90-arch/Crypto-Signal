# V1 CORE CONTRACTS

These are semantic contracts before implementation; field-level schemas will version them.

## Candle
Exchange, market type, symbol, timeframe, open/high/low/close/volume,
open time, close time, source identity, ingestion timestamp, completeness and provenance.

## MethodologyResult
Methodology, symbol, timeframe, direction, setup type, quality/confidence,
entry zone, invalidation, targets, key levels, detected structure, evidence,
timestamp, source identity and methodology version.

## Signal
Symbol, exchange, market type, timeframe, timestamp, direction, setup,
entry zone, invalidation, targets, expected R/R, agreement, confluence score,
historical analogous stats, calibrated-probability status, uncertainty,
evidence summary, signal version and freeze identity.

## Signal states
NO_SIGNAL, NEUTRAL, WATCH, ACTIVE, INVALIDATED.

## Outcome
SUCCESS_TP1, SUCCESS_TP2, SUCCESS_TP3, FAIL_SL, AMBIGUOUS, TIMEOUT,
CANCELLED, INVALIDATED, NOT_EVALUABLE.

## Hard rule
Confluence score and historical success rate are not calibrated win probability.
