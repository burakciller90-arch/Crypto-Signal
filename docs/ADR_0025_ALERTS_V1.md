# ADR 0025 — Alerts V1 Immutable Event and Delivery Contract

Status: Accepted for implementation
Date: 2026-09-20
REAL_CAPITAL: 0

## Purpose
Alerts V1 turns already-accepted immutable signal/lifecycle evidence into
notification events.

Alerts do not create signal truth and do not alter:
- SignalDecision
- lifecycle evaluation
- outcome evaluation
- Historical Evaluation
- exchange/data state

## Policy is separate from truth
Alert eligibility is controlled by an explicit versioned AlertPolicy.

V1 default product policy:
- initial ACTIVE SignalDecision -> eligible
- initial WATCH -> not eligible by default
- lifecycle transition to INVALIDATED -> eligible

This is notification policy, not market truth.

A future user/product configuration may choose a different explicit policy
without rewriting frozen signals.

## Source kinds
V1 AlertEvent source kinds:
- INITIAL_SIGNAL
- LIFECYCLE_TRANSITION

INITIAL_SIGNAL is bound to one SignalDecision.freeze_identity.

LIFECYCLE_TRANSITION is bound to:
- SignalDecision.freeze_identity
- deterministic lifecycle_evaluation_identity
- transition_identity

A lifecycle evaluation with no transition does not create a transition alert.

## Deterministic identity
Alert event identity is SHA256 over canonical:
- alert schema version
- policy version
- source kind
- signal freeze identity
- lifecycle evaluation identity when applicable
- transition identity when applicable
- eligible state

Equivalent source + policy creates the same alert identity.

The human message text is not the source of identity.

## Event payload
AlertEvent carries only frozen descriptive truth needed by a notification:
- market identity
- signal state
- direction
- setup type
- decision as-of
- source evaluation as-of when applicable
- confluence score
- confluence semantic
- probability status
- uncertainty flags
- immutable source identities

Confluence remains an agreement index, not probability.

## Append-only alert outbox
Alerts use a separate SQLite outbox.

Tables:
- alert_events
- alert_delivery_attempts

Both reject UPDATE and DELETE with SQLite triggers.

Equivalent event append is idempotent.

A different payload with the same alert identity is conflict.

## Delivery attempts
Delivery state never rewrites AlertEvent.

Every sink call creates an append-only delivery attempt result:
- DELIVERED
- RETRYABLE_FAILURE
- PERMANENT_FAILURE

A delivered or permanently failed event is terminal for that sink.

Retryable failure may be attempted again.

## Provider idempotency
Every sink receives:
idempotency_key = alert_event_identity

A production provider adapter must either:
- support an equivalent provider-side idempotency primitive, or
- implement its own durable deduplication contract

before it can be accepted for user-facing delivery.

This protects the crash window where a provider accepted a notification but
the local process died before persisting the success receipt.

## V1 test sink
Slice 1 includes a LocalNoopSink.

It performs no external network delivery.

It returns a deterministic local receipt so dispatcher/outbox semantics can be
accepted without pretending a notification channel is live.

## No execution
Alerts contain no:
- order placement
- broker command
- exchange trade
- capital allocation

REAL_CAPITAL remains 0.
