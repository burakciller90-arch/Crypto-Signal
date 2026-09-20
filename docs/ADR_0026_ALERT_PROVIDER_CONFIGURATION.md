# ADR 0026 — Alert Provider Configuration and Secret Boundary

Status: Accepted
Date: 2026-09-20
REAL_CAPITAL: 0

## Purpose
External notification providers are delivery infrastructure only.

They never become signal authority and cannot change immutable evidence.

## Disabled by default
No external provider is enabled by default.

The stable Alert Clock materializes eligible events into the production outbox
without consuming them.

## Secrets
Provider secrets must never be stored in:
- Git
- project markdown
- alert event JSON
- delivery-attempt JSON/rows
- dashboard API responses
- logs
- wake/lease checkpoints

Accepted secret sources for a future adapter:
- environment injected at runtime
- macOS Keychain or equivalent credential store

## Destination identity
A sink_id must be a stable non-secret alias, for example:
provider:primary

It must not embed:
- access token
- webhook secret
- password
- API key

A provider-specific destination identifier should be treated as configuration,
not immutable signal truth.

## Idempotency
Every provider call receives:
idempotency_key = AlertEvent.event_identity

Before production acceptance, an adapter must demonstrate one of:
1. native provider-side idempotency keyed by the event identity; or
2. an adapter-owned durable deduplication layer that closes the
   send-success/local-crash window.

A provider with neither mechanism cannot be marked production-safe.

## Failure mapping
Provider errors must map explicitly to:
- RETRYABLE_FAILURE
- PERMANENT_FAILURE

Unexpected programming errors are not silently converted into retries.

Secrets and raw provider payloads must not be copied into error_message.

## Rendering
A notification may render:
- market identity
- signal state
- direction
- setup
- confluence agreement index
- probability status
- immutable alert identity
- selected uncertainty flags

It must not render confluence score as win probability.

## No execution
Provider adapters cannot place orders or mutate exchange state.

REAL_CAPITAL remains 0.
