# Alerts V1 Slice 1 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted policy boundary
Alert policy is separate from signal truth.

Default V1 product policy:
- initial ACTIVE -> alert eligible
- initial WATCH -> not alert eligible
- lifecycle transition to INVALIDATED -> alert eligible

A different explicit versioned policy may choose WATCH later without rewriting
the immutable signal.

## Immutable alert identity
Alert event identity is deterministic over:
- alert schema version
- policy version
- source kind
- signal freeze identity
- lifecycle evaluation identity when applicable
- transition identity when applicable
- eligible signal state

Equivalent source + policy produces the same event identity.

The rendered message text does not define alert identity.

## Source binding
INITIAL_SIGNAL events bind to SignalDecision.freeze_identity.

LIFECYCLE_TRANSITION events additionally bind to:
- deterministic lifecycle evaluation identity
- immutable transition identity

Lifecycle evaluations without a transition do not create transition alerts.

## Alert truth carried forward
AlertEvent preserves:
- exchange / market / symbol / timeframe
- signal state
- direction
- setup type
- decision/source timestamps
- confluence score
- agreement-index semantic
- probability status
- uncertainty flags

No alert converts confluence score into probability.

## Append-only outbox
Alerts use a separate SQLite database.

Immutable tables:
- alert_events
- alert_delivery_attempts

SQL UPDATE and DELETE are rejected by triggers.

Equivalent event append is idempotent.

## Delivery semantics
Attempt result vocabulary:
- DELIVERED
- RETRYABLE_FAILURE
- PERMANENT_FAILURE

Delivery state is derived from append-only attempts.

For one sink:
- RETRYABLE_FAILURE remains dispatchable
- DELIVERED is terminal
- PERMANENT_FAILURE is terminal

Different sinks have independent delivery state.

## Provider idempotency contract
Every sink receives:

idempotency_key = alert_event_identity

Retries reuse the exact same idempotency key.

A real provider adapter cannot be accepted until it provides equivalent durable
deduplication semantics.

## Local no-op sink
LocalNoopSink:
- performs no external network delivery
- accepts the event identity as idempotency key
- returns a deterministic local receipt
- is used only to validate dispatch/outbox semantics

## Mechanical acceptance
Focused Alerts V1 gate:
- 14 tests PASS
- Ruff PASS
- mypy PASS

Full repository gate:
- 234 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock check PASS
- git diff check PASS

Coverage includes:
- ACTIVE eligible / WATCH not eligible under default policy
- explicit custom WATCH policy
- deterministic identity
- policy version identity separation
- lifecycle INVALIDATED alert binding
- no-transition suppression
- source-parent mismatch rejection
- event append idempotence
- tampered event identity rejection
- retryable failure then success
- terminal delivery protection
- permanent failure terminal per sink
- sink-independent state
- local no-op exactly-once outbox behavior
- retry reuses the same event idempotency key
- SQL immutability

## Canonical next frontier
Alerts V1 Slice 2 — Alert Clock:
- read immutable signal/lifecycle evidence without modifying the signal ledger
- strictly reconstruct source objects
- materialize eligible AlertEvents into separate alert outbox
- default policy should currently yield no initial alert for WATCH-only evidence
- dispatch through LocalNoopSink for runtime acceptance
- repeated clock runs must be idempotent
- add runtime status/counts
- no external notification provider yet
- no execution semantics
- REAL_CAPITAL=0

After Alert Clock acceptance, add a real user-facing notification adapter only
with explicit destination configuration and accepted idempotency behavior.

REAL_CAPITAL remains 0.
