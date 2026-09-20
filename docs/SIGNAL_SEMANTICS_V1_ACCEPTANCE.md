# Signal Semantics V1 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted creation semantics
SignalDecision creation supports:
- NO_SIGNAL
- NEUTRAL
- WATCH
- ACTIVE

ACTIVE requires:
- resolved bullish or bearish Confluence direction
- at least two independent supporting methodologies
- zero opposing methodology votes
- exactly one complete geometry source

No arbitrary score threshold creates ACTIVE.

Signal geometry is atomic and comes from one source evidence item.
Entry, invalidation and targets are never spliced across methodologies.

## Scientific separation
Every SignalDecision explicitly stores:
- Confluence agreement score
- score semantic = agreement_index_not_probability
- calibrated probability status = NOT_CALIBRATED
- historical analogue status = NOT_EVALUATED

No numeric probability is fabricated.

Entry-zone midpoint is used only as a descriptive R/R reference and is
explicitly not an execution assumption.

## Freeze-ready identity
SignalDecision uses a deterministic SHA256 freeze identity derived from its
canonical decision-time fields.

Input ordering does not alter freeze identity.
Lifecycle events never rewrite the decision identity.

## Accepted lifecycle semantics
SignalDecision remains immutable.

Lifecycle evaluation can append:
- WATCH -> INVALIDATED
- ACTIVE -> INVALIDATED

Invalidation is derived only from observed fully post-decision closed candles.

The candle already open at decision time is skipped to prevent pre-decision
OHLC contamination.

Coverage states:
- NO_NEW_EVIDENCE
- COMPLETE
- INCOMPLETE_GAPS

Missing canonical candle opens are explicit and are never synthetically filled.

If an observed later candle proves invalidation after an earlier gap,
INVALIDATED is allowed because the breach is proven, but
first_trigger_candle_certain=false.

## Trigger semantics
Supported V1 invalidation triggers:
- TOUCH_OR_CROSS
- CLOSE_AT_OR_BEYOND

The trigger is frozen from source evidence and lifecycle evaluation does not
reinterpret it.

## Mechanical evidence
Focused lifecycle gate:
- 10 tests PASS
- Ruff PASS
- mypy PASS

Full repository gate:
- 158 tests PASS
- Ruff PASS
- mypy PASS

Coverage includes:
- partial decision candle exclusion
- bullish / bearish touch invalidation
- close-trigger wick non-invalidation
- deterministic transition identity
- gap without breach -> incomplete coverage
- gap before breach -> invalidated with uncertain first-trigger timing
- unobserved future ingestion -> explicit missing candle
- WATCH without geometry cannot invalidate
- market-context mismatch rejection

## Live-safe evidence
Bybit BTCUSDT:
- 499 closed 15m candles
- current SignalDecision: WATCH bearish
- confluence score: 33.33
- lifecycle at decision as-of: NO_NEW_EVIDENCE
- partial decision bucket skipped: true

Binance BTCUSDT:
- 499 closed 15m candles
- current SignalDecision: WATCH bearish
- confluence score: 33.33
- lifecycle at decision as-of: NO_NEW_EVIDENCE
- partial decision bucket skipped: true

The live-safe smoke intentionally does not backdate REST ingestion timestamps.
Historical backfill is not presented as untouched-forward lifecycle evidence.

## Canonical next frontier
Immutable Live Ledger activation.

The ledger must freeze:
- SignalDecision
- decision-time confluence
- selected methodology evidence
- decision-time candle/evidence provenance sufficient for audit
- immutable freeze identity and version

Later lifecycle/outcome records append only.
Original signal rows are never rewritten or deleted.

REAL_CAPITAL remains 0.
