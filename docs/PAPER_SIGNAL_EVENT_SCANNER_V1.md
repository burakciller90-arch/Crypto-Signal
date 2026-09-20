# PAPER SIGNAL EVENT SCANNER V1

Status: candidate Stage 6C read-only production event frontier. It does not activate PAPER/STABLE trading.

Version: `paper_signal_event_scanner.v1`.

## Inputs and authority

The scanner opens:
- immutable production signal ledger with SQLite `mode=ro` + `query_only`;
- paper ledger activation/processed-event tables with SQLite `mode=ro` + `query_only`.

It has no write path, network access, execution simulation, venue refresh, order API or runtime activation authority.

## Eligibility window

Only signal freezes satisfying all of these are considered:
- market type = spot;
- timeframe = 4h;
- exchange = Binance or Bybit;
- symbol is one of BTCUSDT, ETHUSDT, SOLUSDT;
- signal as-of >= persistent activation cutoff;
- freeze timestamp >= persistent activation timestamp.

The scanner also requires the supplied activation identity to equal the immutable singleton persisted in the paper DB.

## Exact provider pairing

Events are grouped by exact `(symbol, signal_as_of_ms)`.

A candidate is emitted only when the group contains exactly one Binance freeze and exactly one Bybit freeze. One-sided groups remain incomplete and emit nothing. Duplicate freezes for the same provider/context fail closed.

The scanner deserializes `signal_decision` from the immutable bundle JSON and rechecks freeze identity, provider, market, symbol, timeframe, as-of, indexed state and indexed direction against the signal_freezes columns.

Candidate provider order is fixed:
1. Binance
2. Bybit

The processed-event identity is the same activation + source-pair + symbol + 4h + as-of identity used by the persistent paper event receipt layer. If that identity already exists in `paper_processed_events`, the event is skipped.

## Deterministic ordering

Unprocessed candidates are ordered by:
1. signal as-of;
2. symbol;
3. event identity.

This slice only produces candidate events. It does not evaluate autonomy or create HOLD/BUY/EXIT decisions.

REAL_CAPITAL remains 0.
