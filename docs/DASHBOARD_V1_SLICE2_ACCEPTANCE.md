# Dashboard V1 Slice 2 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted web stack
Dashboard V1 now has a bounded local web surface:
- FastAPI 0.141.1
- Uvicorn 0.53.0
- static HTML/CSS/JavaScript
- no Node frontend build chain

The web layer is thin and consumes the accepted DashboardReader only.

## Read-only API
Accepted GET endpoints:
- /api/health
- /api/command-center
- /api/market-radar
- /api/assets/{symbol}/{timeframe}
- /api/signals
- /api/signals/{signal_freeze_identity}
- /api/performance

No POST order/command endpoint exists.

Health reports:
- product version
- REAL_CAPITAL=0
- ledger presence
- read_only=true

## Static Mission Control shell
The initial shell renders only real API data:
- immutable freeze count
- latest freeze
- state mix
- direction mix
- Market Radar
- Asset Cockpit
- recent frozen signals
- Signal Archive
- Signal Detail modal
- Performance evidence availability

The shell explicitly displays:
- REAL_CAPITAL = 0
- Confluence != probability
- agreement index labels
- probability_status
- evidence-class status

Initial markup contains no fake market numbers.

## Performance empty state
When outcome_evaluations exists but contains zero snapshots:
- API returns status=EMPTY
- UI says the evidence set is empty
- UI does not display a 0% win rate

## Mechanical acceptance
Dashboard read-model + web focused gate:
- 14 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS

Full repository gate:
- 217 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock check PASS
- git diff check PASS

The current TestClient path emits two upstream dependency deprecation warnings.
They are non-failing and do not affect runtime semantics.

## Production-ledger local smoke
Temporary local server:
- host: 127.0.0.1
- port: 48700

Smoke evidence:
- /api/health -> status=ok, ledger_present=true, read_only=true, REAL_CAPITAL=0
- /api/command-center -> READY, 24 immutable freezes
- latest real cards preserved probability_status=not_calibrated
- latest real cards preserved confluence semantic=agreement_index_not_probability
- /api/performance -> EMPTY, outcome_snapshot_count=0
- / -> Mission Control shell with REAL_CAPITAL=0 and Confluence != probability markers

The smoke server was stopped after acceptance and port 48700 returned FREE.

## Canonical next frontier
Dashboard V1 Slice 3 — stable product runtime:
- create isolated PRODUCT/STABLE worktree pinned to accepted Dashboard commit
- run dashboard from the stable worktree, not mutable development source
- install com.cryptosignal.dashboard LaunchAgent
- bind only to 127.0.0.1:48700
- retain read-only production-ledger access
- add runtime health/log checks
- perform browser/local HTTP smoke
- keep LIVE/STABLE evidence clock independent
- no execution controls

After stable product runtime acceptance, continue visual/functional expansion:
- richer Signal Detail evidence
- Historical Evaluation metric projection
- multi-timeframe/symbol navigation
- polished UX iteration

REAL_CAPITAL remains 0.
