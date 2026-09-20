# Alerts V1 Integrated Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Scope accepted
Alerts V1 is accepted end-to-end as a notification evidence and delivery
platform boundary.

Accepted chain:

immutable SignalDecision / lifecycle evidence
-> explicit versioned AlertPolicy
-> deterministic AlertEvent
-> append-only AlertOutbox
-> stable materialize-only Alert Clock
-> canonical NotificationMessage
-> idempotent AlertSink boundary
-> append-only delivery attempts
-> read-only Mission Control Alert Center

## Notification policy
Default V1 policy:
- initial ACTIVE is eligible
- initial WATCH is suppressed
- lifecycle INVALIDATED transition is eligible

Policy is versioned product behavior, not signal truth.

## Immutable event identity
Alert identity binds:
- schema version
- policy version
- source kind
- signal freeze identity
- lifecycle evaluation identity when applicable
- transition identity when applicable
- eligible state

Equivalent immutable source + policy reproduces the same identity.

## Outbox and delivery truth
Alert events and delivery attempts are append-only.

SQL UPDATE/DELETE is rejected.

Per-sink delivery states:
- DELIVERED terminal
- PERMANENT_FAILURE terminal
- RETRYABLE_FAILURE retryable

Different sinks remain independent.

## Idempotency
Every provider call uses:

idempotency_key = AlertEvent.event_identity

Retries reuse the same identity.

Production external adapters require provider-side or durable adapter-side
deduplication before acceptance.

## Canonical presentation
Every provider receives the same deterministic NotificationMessage.

The message explicitly preserves:
- ACTIVE / INVALIDATED state
- market identity
- direction
- setup
- agreement index
- '(not probability)' wording
- probability status
- source kind
- UTC source as-of
- uncertainty
- immutable alert ID

Provider adapters cannot invent an alternative signal interpretation.

## Secret boundary
External providers are disabled by default.

Secrets are never committed to:
- Git
- markdown
- alert events
- delivery rows
- product API
- logs
- wake/lease checkpoints

Provider configuration stores only secret references such as environment or
Keychain references.

## Alert Clock
ALERTS/STABLE:
- /Users/crypto-signal-agent/Crypto-Signal-Alerts
- exact accepted commit:
  1d8c8757fb825c8934229b454db49bf800f2b5cf
- own .venv
- LaunchAgent com.cryptosignal.alertclock
- RunAtLoad=true
- StartInterval=120 seconds
- one-shot materialize-only execution
- no external provider
- source signal ledger read-only
- separate production alert outbox

Stable runtime observed:
- launchd runs=11
- last exit code=0
- latest source observed by Alert Clock: 34 signals / 34 lifecycle
- eligible=0
- outbox events=0
- attempts=0

A not-running launchd state between StartInterval one-shots is expected.

## Mission Control
PRODUCT/STABLE:
- /Users/crypto-signal-agent/Crypto-Signal-Product
- exact accepted commit:
  1d8c8757fb825c8934229b454db49bf800f2b5cf
- dashboard product_version=dashboard-v1-alert-center/1
- localhost 127.0.0.1:48700 only
- read_only=true
- alert_outbox_present=true

Alert Center stable state at acceptance:
- EMPTY
- total_count=0
- events=0

This is correct because all current prospective evidence is WATCH and WATCH is
not eligible under the default policy.

## Preview
ops/preview_alerts.py is read-only.

Stable preview observed:
- ALERT_PREVIEW_COUNT=0
- production outbox remains 0 events / 0 attempts

Mission Control uses the same canonical notification renderer.

## Mechanical evidence
Alerts V1 Slice 1 focused:
- 14 tests PASS

Alert Clock/shared persisted parser focused:
- 38 tests PASS

Alert Center focused:
- 21 tests PASS

Canonical notification Slice 5 focused:
- 34 tests PASS

Latest full repository gate:
- 255 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- git diff check PASS

## Isolation
Alerts V1 remains isolated from:
- mutable development source
- LIVE/STABLE evidence runtime
- PRODUCT/STABLE runtime
- Durdurulmaz
- Quantum Capital

No alert feature places orders or mutates exchange state.

REAL_CAPITAL remains 0.

## Acceptance conclusion
Alerts V1 is accepted.

External notification delivery is an optional configured adapter step, not a
blocker for the V1 core, because:
- event truth is materialized durably
- pending events are not consumed
- provider semantic/idempotency contracts are accepted
- external provider selection requires explicit destination configuration

## Canonical next frontier
V1 Integrated Acceptance.

The integrated gate must verify the complete critical path:

Data Truth
-> deterministic primitives
-> PA / Harmonic / Elliott
-> Confluence / Signal semantics
-> immutable live freeze
-> lifecycle / outcome
-> Historical Evaluation
-> Dashboard
-> Alerts
-> stable runtime isolation and recovery

REAL_CAPITAL remains 0.
