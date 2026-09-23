# GALACTECH Production UI Cutover — Candidate

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product path.
Predecessor: accepted accessibility/performance polish PR #931.
REAL_CAPITAL=0.

## Candidate routing

This isolated candidate changes only the customer HTML entry point:

- `GET /` -> accepted GALACTECH v1.1 surface;
- `GET /galactech` -> same GALACTECH surface as an explicit alias;
- `GET /legacy` -> previous accepted legacy UI for rollback/audit access;
- `/galactech-static/*` and `/static/*` remain separate;
- all existing read-only APIs remain unchanged.

No redirect or state mutation is required.

## Rollback invariant

The legacy surface is intentionally retained at `/legacy`. A cutover rollback can restore
the previous root route without rewriting ledger, paper, market or archive state.

The cutover does not:
- migrate a database;
- change paper accounting;
- mutate immutable evidence;
- enable credentials/orders;
- change REAL_CAPITAL.

## Truth invariant

The promoted root remains the exact accepted GALACTECH surface:

- no fake LIVE;
- no fake latency/freshness;
- no fake probability;
- missing product adapters remain NOT EXPOSED / NOT MEASURED;
- REAL_CAPITAL=0;
- authority remains READ ONLY.

## Acceptance layers

Candidate acceptance requires:

1. focused root/alias/legacy route tests;
2. every accepted GALACTECH product-slice regression;
3. legacy UI regression on `/legacy`;
4. full repository pytest/Ruff/mypy/JS/freshness gate.

This is still hosted candidate evidence. The locked roadmap separately requires
UID504/runtime acceptance and deployed-source hash parity before v1.1.0 release.

## Human-impact boundary

Preparing and testing this branch is isolated development. Merging/deploying the production
entry-point cutover is treated as the production UI transition and is not performed merely
because the candidate passes hosted tests.

Status: CANDIDATE ONLY until production cutover authority is explicitly satisfied.
