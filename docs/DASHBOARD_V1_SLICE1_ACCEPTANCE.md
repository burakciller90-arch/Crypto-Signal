# Dashboard V1 Slice 1 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted architecture
Dashboard V1 begins with a framework-independent, read-only product read model.

Selected product direction:
- Python ASGI API
- FastAPI application layer
- Uvicorn local server
- static HTML/CSS/JavaScript assets
- no Node frontend build chain for the initial shell

Framework dependencies are intentionally deferred until Slice 2.

## Read-only storage boundary
DashboardReader:
- opens SQLite with mode=ro
- enables PRAGMA query_only=ON
- never initializes production schema
- never migrates production schema
- never writes fixture/mock data into runtime
- returns explicit status when ledger/schema/data is unavailable

## Accepted product surfaces
Read models now exist for:
- Command Center
- Market Radar
- Asset Cockpit
- Signal Archive
- Signal Detail
- Performance availability

## Accepted signal truth
Frozen signal cards expose:
- immutable bundle identity
- immutable signal freeze identity
- exchange / market / symbol / timeframe
- decision and freeze timestamps
- source cutoff
- signal state / direction / setup
- confluence score
- confluence score semantic
- probability status
- uncertainty flags

Signal-level evidence class is explicitly marked:
NOT_EXPLICIT_AT_FREEZE_LEVEL.

The UI does not infer evidence class from timestamps or database path.

## Performance boundary
Performance availability reads only explicit outcome_evaluations records.

States:
- NO_LEDGER
- SCHEMA_UNAVAILABLE
- EMPTY
- READY

An empty outcome table is not converted into zero win rate.

## Mechanical acceptance
Focused Dashboard read-model gate:
- 8 tests PASS
- Ruff PASS
- mypy PASS

Full repository gate:
- 211 tests PASS
- Ruff PASS
- mypy PASS
- git diff check PASS

Test coverage includes:
- missing ledger NO_LEDGER
- strict immutable signal parsing
- state/direction counts
- latest-per-provider Market Radar
- Asset Cockpit provider projection
- reverse-time immutable Signal Archive
- exact Signal Detail bundle return
- performance schema absence without mutation
- explicit outcome evidence-class counts
- malformed bundle fail-closed

## Production read-only smoke
Production ledger read via DashboardReader:
- Command Center: READY
- immutable freezes read: 24
- states: WATCH=24
- directions: bearish=20, bullish=4
- Market Radar contexts: 2
- Archive total: 24
- Performance outcome snapshots: 0
- Performance status: EMPTY

Recent live cards preserve:
- probability_status=not_calibrated
- confluence_score_semantic=agreement_index_not_probability

No mock data was used in runtime smoke.

## Canonical next frontier
Dashboard V1 Slice 2:
- install bounded FastAPI/Uvicorn dependencies
- expose read-only JSON endpoints over accepted product read models
- add local health/status endpoint
- build static Mission Control shell
- render Command Center / Radar / Archive first
- clearly label confluence versus probability
- Performance empty state must remain explicit
- no order/execution controls
- local smoke on reserved project port
- focused tests + full repo gate

LIVE/STABLE evidence clock remains isolated.
REAL_CAPITAL remains 0.
