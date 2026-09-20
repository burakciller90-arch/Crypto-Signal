# Immutable Live Ledger Acceptance

Date: 2026-09-20
Status: ACTIVE
REAL_CAPITAL: 0

## Accepted core
The immutable ledger now freezes:
- SignalDecision
- ConfluenceAnalysisResult
- selected neutral MethodologyEvidence
- raw Price Action analysis
- raw Harmonic analysis
- raw Elliott analysis
- complete closed/observed candle snapshots consumed by the decision

Each freeze has:
- signal_freeze_identity
- broader decision bundle_identity
- source_cutoff_open_time_ms
- real decision as-of
- real database frozen_at_ms

SQLite uses WAL and SQL triggers reject UPDATE and DELETE.

## Mechanical acceptance
Focused immutable-ledger tests:
- 9 PASS

Live-clock tests:
- 3 PASS

Pre-activation full repository:
- 170 tests PASS
- Ruff PASS
- mypy PASS
- launchd plist lint PASS

Live acceptance probe:
- first run inserted Bybit + Binance freezes
- second run on the same source cutoff returned ALREADY_FROZEN for both
- acceptance DB remained exactly 2 freezes + 2 lifecycle evaluations

## Production forward evidence clock
Production database:
runtime/ledger/live_signal_ledger.sqlite3

LaunchAgent:
com.cryptosignal.liveevidenceclock

Schedule:
- RunAtLoad
- StartInterval = 120 seconds
- one-shot runner with non-blocking file lock
- one freeze maximum per provider/source closed-candle cutoff

Pilot scope:
- BTCUSDT
- 15m
- Bybit Spot
- Binance Spot
- 500-candle live decision window

## First untouched-forward freezes

### Bybit
- source cutoff open time: 1789862400000
- state: WATCH
- direction: bearish
- confluence score: 33.33
- signal freeze identity:
  b15be217623c72c592188315e20f7731f68f3b0fafd76dbb83ce7b70ecefe304
- bundle identity:
  4a977fbdfac5e1f2202eccfb9b74980dab38fab143655a0a93a13cbe96bda1fc
- frozen_at_ms: 1789864158775
- frozen UTC: 2026-09-20T00:29:18.775Z
- frozen Europe/Istanbul: 2026-09-20T03:29:18.775+03:00

### Binance
- source cutoff open time: 1789862400000
- state: WATCH
- direction: bearish
- confluence score: 33.33
- signal freeze identity:
  51e80cf6c98f4a8e0aeb7d8421040f1d16f601cc470544c6f65c97c6c5dd4022
- bundle identity:
  58914695eac84d2bc50e05681f2f8207d7e6bdc2ce0939764544b672901fc9b1
- frozen_at_ms: 1789864159955
- frozen UTC: 2026-09-20T00:29:19.955Z
- frozen Europe/Istanbul: 2026-09-20T03:29:19.955+03:00

These are the first records eligible for untouched-forward evidence classification.

## Live idempotence recheck
A manual launchctl kickstart was performed after the first freezes.

Result:
- Bybit: ALREADY_FROZEN
- Binance: ALREADY_FROZEN
- production freeze count remained 2
- production lifecycle count remained 2

No existing row was updated or replaced.

## Scientific boundary
The fact that the live decisions were WATCH is preserved exactly.
The system did not promote them to ACTIVE merely to start the evidence clock.

Historical REST data inside the decision bundle is prior market history observed
at the real freeze time. It is not relabeled as historically untouched-forward evidence.

The untouched-forward classification applies to the frozen decision itself and
its later append-only lifecycle/outcome evidence.

## Canonical next frontier
Outcome + Historical Evaluation V1:
- outcome state contract
- target/stop ordering semantics
- same-candle ambiguity
- timeout / not-evaluable semantics
- append-only outcome ledger
- segmented retrospective versus untouched-forward performance
- no mixing evidence classes

REAL_CAPITAL remains 0.
