# Alerts V1 Slice 5 Acceptance — Canonical Notification Presentation

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Purpose
All future notification providers must consume one canonical notification
presentation derived from immutable AlertEvent truth.

Providers do not independently reinterpret signal semantics.

## NotificationMessage
A canonical NotificationMessage carries:
- alert event identity
- identical idempotency key
- deterministic title
- deterministic body

The idempotency key must equal the immutable alert event identity.

## Rendering semantics
ACTIVE and INVALIDATED events render explicitly.

The message includes:
- exchange / market / symbol / timeframe
- signal state
- direction
- setup type
- agreement index
- explicit '(not probability)' wording
- probability status
- source kind
- source as-of timestamp in UTC
- uncertainty flags
- immutable alert ID

No calibrated probability is invented.

## Provider contract
AlertSink now receives NotificationMessage rather than raw AlertEvent.

This means every provider sees the same accepted semantic presentation.

Dispatcher behavior:
1. read pending immutable AlertEvent
2. render canonical NotificationMessage
3. call provider sink with the canonical message
4. pass event identity as idempotency key
5. append delivery attempt result

## Configuration
AlertSinkConfiguration contains only non-secret configuration:
- sink_id
- provider name
- destination alias
- credential reference kind
- credential reference name
- enabled flag

Credential reference kinds:
- environment
- keychain

The model rejects common embedded-secret markers such as:
- token=
- password=
- secret=
- api_key=

The credential value itself is not part of the model.

## Read-only preview
ops/preview_alerts.py provides a dry-run preview.

It:
- opens the alert outbox read-only
- renders canonical notification messages
- creates no delivery attempts
- consumes no events
- modifies no outbox state

Mission Control Alert Center also projects the same canonical title/body.

Therefore product preview and future provider delivery share one renderer.

## Mechanical acceptance
Slice 5 focused gate:
- 34 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS

Full repository gate:
- 255 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- git diff check PASS

## Production-outbox preview smoke
Before preview:
- alert events=0
- delivery attempts=0

preview:
- ALERT_PREVIEW_COUNT=0

After preview:
- alert events=0
- delivery attempts=0

No production state was consumed or rewritten.

## Canonical next frontier
Deploy this exact accepted commit to:
- PRODUCT/STABLE
- ALERTS/STABLE

Then perform Alerts V1 integrated acceptance:
- stable materializer remains materialize-only
- stable product shows canonical notification preview
- production outbox remains safe and empty while evidence is WATCH-only
- external providers remain disabled by default
- REAL_CAPITAL remains 0

After Alerts V1 integrated acceptance, advance to V1 Integrated Acceptance.
