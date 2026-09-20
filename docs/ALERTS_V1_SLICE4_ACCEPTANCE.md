# Alerts V1 Slice 4 Acceptance — Mission Control Alert Center

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted product surface
Mission Control now includes a read-only Alert Center over the separate
production alert outbox.

It does not modify:
- alert events
- delivery attempts
- signal ledger
- lifecycle evidence
- outcome evidence

## Alert Center states
The product surface preserves explicit data states:
- NO_LEDGER
- SCHEMA_UNAVAILABLE
- EMPTY
- READY

EMPTY means no eligible immutable AlertEvent exists.

It does not mean:
- 0% alert success
- no market activity
- no WATCH signals

Under the default policy, WATCH is intentionally not an alert.

## Event projection
Each visible alert preserves:
- alert event identity
- source kind
- signal freeze identity
- lifecycle/transition identities when applicable
- exchange / market / symbol / timeframe
- signal state
- direction
- setup type
- decision/source timestamps
- confluence score and agreement-index semantic
- probability status
- uncertainty flags

## Delivery projection
Alert Center shows delivery state per sink.

For every sink with attempts:
- attempt count
- latest attempt status
- latest attempt timestamp
- terminal flag
- delivered flag
- latest receipt when present

An event with no sink attempts is shown as:
pending / no delivery attempt

The UI does not synthesize a global delivery state across independent sinks.

## Product API
Product version:
dashboard-v1-alert-center/1

New endpoint:
- GET /api/alerts

Health now additionally reports:
- alert_outbox_present

The API remains read-only.

## UI
Mission Control now renders:
- Alert Center event count
- explicit empty state
- source signal state/direction
- agreement index with not-probability label
- sink delivery pills
- click-through to immutable Signal Detail

No synthetic alert rows are rendered.

## Mechanical acceptance
Alert Center + web focused gate:
- 21 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS

Full repository gate:
- 245 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- alert LaunchAgent plist lint PASS
- git diff check PASS after EOF cleanup

Only two upstream TestClient deprecation warnings remain non-failing.

## Real production-outbox smoke
Temporary development server:
- 127.0.0.1:48701

Health:
- product_version=dashboard-v1-alert-center/1
- ledger_present=true
- alert_outbox_present=true
- read_only=true
- REAL_CAPITAL=0

Alert Center:
- status=EMPTY
- total_count=0
- events=0

HTML contains the Alert Center surface.

The temporary development server was stopped after smoke.

## Canonical next frontier
Explicitly deploy this accepted Alert Center commit to PRODUCT/STABLE, then
continue Alerts V1 user-facing notification presentation.

A real external provider remains disabled until destination configuration and
provider idempotency are explicitly accepted.

REAL_CAPITAL remains 0.
