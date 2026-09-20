# Alerts V1 Slice 2 Acceptance — Alert Clock

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted clock boundary
Alert Clock reads immutable signal/lifecycle evidence and materializes eligible
AlertEvents into the separate alert outbox.

The source signal ledger is opened with:
- SQLite mode=ro
- PRAGMA query_only=ON

Alert Clock never initializes, migrates or mutates the signal ledger.

## Shared persisted-evidence parser
Persisted SignalDecision, OutcomeEvaluation and SignalLifecycleEvaluation
reconstruction now lives in:

crypto_signal.ledger.deserialization

Dashboard compatibility exports reuse the same implementation.

This prevents Product and Alerts lanes from silently interpreting immutable
stored evidence differently.

## Materialization policy
Default V1 policy remains:
- initial ACTIVE eligible
- initial WATCH suppressed
- lifecycle INVALIDATED transition eligible

Each clock run:
1. reads all immutable signal freezes
2. strictly reconstructs SignalDecision
3. plans initial alerts
4. reads all lifecycle evaluations
5. verifies lifecycle canonical identity and row coherence
6. plans transition alerts
7. appends eligible events idempotently to the separate outbox

Malformed/mismatched source evidence fails closed.

## Runtime default
ops/run_alert_clock.py defaults to materialize-only.

It does not perform external notification delivery.

Optional:
--dispatch-local-noop

is acceptance/test-only and performs no external network delivery.

## Idempotency
Repeated clock runs over unchanged evidence:
- reproduce identical AlertEvent identities
- insert no duplicate events
- return UNCHANGED for already materialized events

## Mechanical acceptance
Alert Clock + Dashboard shared-parser focused gate:
- 38 tests PASS
- Ruff PASS
- mypy PASS

Full repository gate:
- 241 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- git diff check PASS

Clock-specific coverage:
- ACTIVE initial materialization
- WATCH initial suppression
- INVALIDATED lifecycle materialization
- repeat-run idempotence
- read-only source ledger hash preservation in isolated test
- tampered lifecycle identity fail-closed
- signal identity mismatch fail-closed
- missing required source table fail-closed

## Production-ledger smoke
Acceptance outbox:
runtime/alerts/acceptance_slice2.sqlite3

Three real-ledger runs were performed:
1. materialize-only
2. repeated materialize-only
3. materialize + LocalNoopSink

Observed immutable source:
- signal freezes: 30
- lifecycle evaluations: 30
- signal states: WATCH=30

Observed alert result on every run:
- eligible events: 0
- inserted events: 0
- outbox events: 0
- delivery attempts: 0

This is the expected default-policy behavior.
WATCH evidence is not notification spam.

No alert was marked delivered because no eligible event existed.

## Canonical next frontier
Alerts V1 Slice 3 — persistent materialize-only runtime:
- create isolated ALERTS/STABLE worktree pinned to accepted Alert Clock commit
- create alerts-local virtual environment from accepted lockfile
- install com.cryptosignal.alertclock LaunchAgent
- RunAtLoad + periodic one-shot materialization
- source ledger remains read-only
- production alert outbox remains separate
- no external dispatch
- runtime health/log/idempotency smoke
- keep LIVE/STABLE and PRODUCT/STABLE independent

After stable Alert Clock acceptance, implement/configure a real user-facing
notification adapter with explicit destination configuration and accepted
provider-side idempotency semantics.

REAL_CAPITAL remains 0.
