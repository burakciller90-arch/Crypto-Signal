# Dashboard V1 Integrated Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Product outcome
Dashboard V1 is accepted as a persistent, read-only Mission Control over
immutable Crypto Signal evidence.

Mandatory V1 surfaces are present:
- Command Center
- Market Radar
- Asset Cockpit
- Signal Detail
- Signal Archive
- Performance

## Truth boundary
Dashboard V1 never creates methodology truth.

It reads accepted immutable evidence and preserves:
- signal state
- direction
- setup type
- source cutoff
- confluence score
- confluence semantic
- probability status
- uncertainty
- evidence-class separation
- immutable signal identity

Confluence score is always presented as an agreement index, not probability.

Historical success fraction is always descriptive frequency, not calibrated
probability.

Empty outcome evidence is displayed as EMPTY, never as a 0% win rate.

## Read-only architecture
The product reader uses:
- SQLite mode=ro
- PRAGMA query_only=ON

It does not:
- initialize production schema
- migrate production schema
- update/delete immutable evidence
- place exchange orders
- expose POST execution controls

REAL_CAPITAL remains 0.

## Accepted product/runtime architecture
Development worktree:
- /Users/crypto-signal-agent/Crypto-Signal

PRODUCT/STABLE:
- /Users/crypto-signal-agent/Crypto-Signal-Product
- pinned accepted commit: 2c2fc99e58d543bbf77060bb134c49b332720280

Persistent local runtime:
- LaunchAgent: com.cryptosignal.dashboard
- 127.0.0.1:48700 only
- RunAtLoad=true
- KeepAlive=true
- product-local .venv

LIVE/STABLE evidence collection remains isolated in:
- /Users/crypto-signal-agent/Crypto-Signal-Live

## Dashboard Slice 1
Accepted:
- framework-independent read models
- strict immutable signal cards
- explicit NO_LEDGER / SCHEMA_UNAVAILABLE / EMPTY / READY states
- Command Center / Radar / Asset / Archive / Detail / Performance availability
- no runtime mock data

## Dashboard Slice 2
Accepted:
- FastAPI + Uvicorn local read-only API
- static Mission Control shell
- no Node frontend build chain
- GET-only product endpoints
- local real-ledger smoke

## Dashboard Slice 3
Accepted:
- isolated PRODUCT/STABLE worktree
- independent product .venv
- persistent LaunchAgent
- localhost-only bind
- KeepAlive restart acceptance

## Dashboard Slice 4
Accepted:
- rich frozen methodology evidence in Signal Detail
- pairwise methodology agreement
- frozen geometry visibility when it exists
- candle coverage
- strict SignalDecision / OutcomeEvaluation reconstruction
- Historical Evaluation metric projection through accepted aggregate_segments()
- evidence-class tabs
- holding-horizon separation
- symbol / timeframe / provider navigation
- responsive visual polish

## Mechanical evidence
Latest full development gate:
- 220 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- git diff check PASS

Slice 4 stable deployment smoke:
- PRODUCT/STABLE commit: 2c2fc99e58d543bbf77060bb134c49b332720280
- product_version: dashboard-v1-slice4/1
- listener: 127.0.0.1:48700
- health: HTTP 200
- read_only=true
- REAL_CAPITAL=0
- navigation: READY / 2 contexts
- immutable freezes observed: 30
- Performance: EMPTY / 0 outcome snapshots
- rich detail: PA/Harmonic/Elliott selection projection present
- pairwise relations: present
- frozen candle coverage: present

No live performance claim is fabricated while explicit outcome evidence is empty.

## Access
Local Mission Control:

http://127.0.0.1:48700

## Canonical next frontier
Alerts V1.

Initial bounded work:
- immutable alert-event contract
- deterministic deduplication identity
- signal-state transition eligibility
- alert policy separate from signal truth
- append-only alert outbox
- delivery status without rewriting signal/outcome evidence
- local/no-op sink for testing
- provider adapter boundary for future notification channels
- no execution/order semantics
- REAL_CAPITAL=0

Dashboard development may continue later as product polish, but Dashboard V1 is
no longer on the critical path.

REAL_CAPITAL remains 0.
