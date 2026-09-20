# ADR 0024 — Dashboard V1 Read Model and Web Surface

Status: Accepted for Slice 1 implementation
Date: 2026-09-20
REAL_CAPITAL: 0

## Product boundary
The Dashboard is a PRODUCT/COMMAND CENTER lane over accepted immutable evidence.

It does not:
- create methodology truth
- mutate the live ledger
- send exchange orders
- reinterpret confluence score as probability
- infer missing evidence class

## V1 web surface
The smallest maintainable V1 surface is:
- Python ASGI API
- FastAPI application layer
- Uvicorn local server
- static HTML/CSS/JavaScript assets
- no Node build chain for the initial product shell

Framework dependencies are introduced only after the framework-independent
read model is accepted.

## Read-only storage rule
Dashboard readers open SQLite in read-only mode and enable query_only.

The product lane never initializes or migrates the production ledger.

Missing database or optional tables are represented as explicit data-status
states rather than being created by the reader.

## Initial surfaces
Slice 1 defines read models for:
- Command Center
- Market Radar
- Asset Cockpit
- Signal Detail
- Signal Archive
- Performance availability summary

Visual implementation follows after these contracts are accepted.

## Signal card truth
A frozen signal card exposes:
- immutable bundle and signal identities
- market identity and source cutoff
- decision and freeze timestamps
- state / direction / setup
- confluence score
- confluence score semantic
- probability status
- uncertainty flags

The UI must label confluence as an agreement index, not probability.

## Evidence-class boundary
Current signal_freezes do not carry a separate explicit evidence-class column.

The Dashboard must not infer signal evidence class from timestamps or file path.

Outcome evidence class may be displayed only from explicit outcome_evaluations
records.

If outcome_evaluations schema is not deployed in the read database, the
Performance read model reports SCHEMA_UNAVAILABLE.

## Market Radar
Market Radar groups immutable freezes by:
exchange + market type + symbol + timeframe

and exposes the newest freeze per group.

It does not create a BUY/SELL recommendation.

## Asset Cockpit
Asset Cockpit is a focused projection over one symbol/timeframe:
- latest freeze per provider
- recent immutable signal history
- current state/direction/confluence labels

No cross-provider price synthesis occurs in the product reader.

## Signal Detail / Archive
Signal Detail reads one immutable bundle by signal freeze identity.

Signal Archive lists immutable freezes in reverse freeze-time order.
Losses or non-active states are never hidden by storage policy.

## Performance surface
Slice 1 exposes only:
- whether outcome schema exists
- outcome snapshot count
- explicit evidence-class counts

Historical Evaluation metric reconstruction from serialized snapshots is a
later Dashboard slice.

No empty performance dataset is converted into zero win rate.

## No mock-data masquerade
Test fixtures are allowed only in tests.

The runtime Dashboard must identify missing/empty real data explicitly and must
never render fixture values as live observations.

REAL_CAPITAL remains 0.
