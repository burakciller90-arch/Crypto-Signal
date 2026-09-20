# Dashboard V1 Slice 4 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Accepted scope
Slice 4 enriches the accepted read-only Mission Control without changing
signal truth, outcome truth or execution boundaries.

Accepted additions:
- richer Signal Detail from the immutable frozen decision bundle
- strict persisted SignalDecision / OutcomeEvaluation reconstruction
- Historical Evaluation projection through the already-accepted aggregator
- explicit evidence-class presentation
- holding-horizon separation
- symbol / timeframe / provider navigation
- methodology selection and agreement presentation
- responsive product styling

## Rich Signal Detail
The detail projection now exposes frozen:
- methodology source and selected counts
- resolved methodology direction
- internal direction-conflict flag
- selected evidence summaries
- ambiguity and contradiction flags
- key levels and deterministic metrics
- pairwise methodology relations
- frozen geometry when one exists
- candle coverage
- decision evidence summary and uncertainty flags

If complete frozen geometry does not exist, the UI says so.
It does not invent entry, invalidation or target levels.

## Performance projection
Dashboard Performance does not reimplement evaluation mathematics.

Persisted signal and outcome JSON are strictly reconstructed into accepted
SignalDecision and OutcomeEvaluation objects, then passed to
aggregate_segments() from Historical Evaluation V1.

For each:
- evidence class
- max_holding_bars

the newest evaluated_as_of snapshot per signal is selected.

Different evidence classes are never merged.
Different holding horizons are never merged.

Displayed metrics inherit accepted semantics:
- decisive N
- historical success fraction
- R-evaluable N
- average shadow R
- cumulative shadow R
- max drawdown R
- promotion visibility policy

Historical success fraction remains descriptive frequency, not probability.

## Navigation
/api/navigation exposes real immutable ledger contexts grouped by:
- exchange
- market type
- symbol
- timeframe

Asset Cockpit can select:
- symbol
- timeframe
- provider

No cross-provider synthetic signal is created.

## API
Product version:
dashboard-v1-slice4/1

New endpoint:
- GET /api/navigation

Existing endpoints remain read-only.

## Mechanical acceptance
Slice 4 data/read-model gate:
- 11 tests PASS
- Ruff PASS
- mypy PASS

Slice 4 combined focused gate:
- 17 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS

Full repository gate:
- 220 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock check PASS
- git diff check PASS

Only two upstream TestClient deprecation warnings remain non-failing.

## Real production-ledger smoke
Temporary development runtime:
- 127.0.0.1:48701
- product_version=dashboard-v1-slice4/1
- read_only=true
- REAL_CAPITAL=0

Observed real immutable state during smoke:
- freeze count: 30
- latest signal state: WATCH
- navigation contexts: 2
- outcome snapshots: 0
- Performance: EMPTY

Latest rich detail example:
- Price Action source count: 1 / selected: 1 / bullish
- Harmonic source count: 0 / selected: 0 / unresolved
- Elliott source count: 195 / selected: 2 / bullish
- pairwise relations: 3
- complete signal geometry: absent
- frozen candle count: 499

These are evidence observations, not performance claims.

The temporary 48701 server was stopped after smoke.

## Deployment rule
The currently running PRODUCT/STABLE remains on the previous accepted commit
until this Slice 4 commit is created.

After commit, PRODUCT/STABLE may be explicitly advanced to that exact accepted
commit and restarted. Mutable development source must not be imported by the
stable runtime.

## Next frontier
After explicit PRODUCT/STABLE deployment and stable smoke, close Dashboard V1
integrated acceptance and advance to Alerts V1.

REAL_CAPITAL remains 0.
