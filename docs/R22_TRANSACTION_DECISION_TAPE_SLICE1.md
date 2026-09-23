# R22 Transaction & Decision Tape — Phase 17 acceptance candidate

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Phase 17.
Baseline: accepted R20 forecast / R20.5 Decision Proof / R21 Epoch 2 / R11 sizing.
REAL_CAPITAL=0. No exchange, broker, credential, leverage or real-money authority is added.

## Canonical trace contract

Every R22 paper-capital mutation is required to bind the exact immutable chain:

`forecast -> Decision Proof -> sizing assessment -> sizing result -> paper decision
-> simulated fill -> cash/position mutation -> R21 vault snapshot
-> R21 consolidated snapshot -> financial outcome -> immutable R22 bundle`.

The caller cannot substitute free-form SHA strings for the accepted sizing/decision/fill
objects. Trade intent construction validates the actual immutable objects and identities.

For every trade, R22 records and verifies:

- forecast identity and signal-freeze identity;
- exact R20.5 Decision Proof and source-evidence identities;
- vault and accepted sizing policy;
- sizing-assessment identity, chosen sizing-result identity and allocator-candidate identity;
- exact paper decision identity, action, symbol, quantity and reference price;
- exact simulated-fill identity, fill price, venue reference and execution-policy version;
- fee, spread and slippage without double-counting execution impact;
- exact position/cash mutation identity;
- cash and position before/after;
- R21 before/after vault snapshot identities;
- R21 before/after consolidated snapshot identities;
- realized and unrealized PnL deltas;
- explicit financial outcome (`OPEN`, `PARTIAL_REDUCTION`, `CLOSED_WIN`,
  `CLOSED_LOSS`, `CLOSED_BREAKEVEN`);
- explicit outcome evidence for a closed sale;
- exact mark/evidence identities;
- immutable SHA256 identities for intent, fill and accounting bundle.

`HOLD_CASH` is a first-class immutable decision. It cannot fabricate a forecast,
sizing result, paper trade or fill.

## Accounting interpretation

The simulated fill price already contains the adverse spread/slippage effect.
Only the separately specified fee is subtracted again from cash. Therefore R22
forbids charging spread/slippage twice.

The R21 mark evidence explains mark-to-market exposure and unrealized PnL. R22
does not invent a hidden mark and does not attribute unrelated mark movement to
the transaction.

A closed sale must advance R21 closed-trade accounting and provide an explicit
outcome-evidence identity. R22 derives the financial outcome from the immutable
action/PnL record and validates it during construction.

## Atomic Epoch 2 commit

R22 audit tables live in the same local Epoch 2 SQLite database as R21 accounting.
A canonical trade bundle is committed inside one `BEGIN IMMEDIATE` transaction:

1. immutable R22 intent;
2. three same-timestamp R21 vault snapshots;
3. R21 consolidated snapshot;
4. immutable R22 fill;
5. immutable R22 accounting bundle.

A forced failure during the R22 fill insert is tested to roll back **all** R21 and
R22 writes together. There is therefore no cross-database partial-commit window in
this design.

The legacy Epoch 1 ledger is read-only provenance and is never mutated.

## Replay / audit contract

Read-only audit verifies:

- payload SHA against every embedded immutable identity;
- SQL row headers against payload activation/vault/event time;
- intent and fill predecessor chains per vault;
- one fill per trade intent and one bundle per fill;
- no fill for `HOLD_CASH`;
- exact activation lineage;
- exact before/after consolidated lineage;
- exact three-vault before/after sets;
- exact target-vault fill binding;
- semantic Decimal equality for non-target vaults so representation-only
  differences such as `0` vs `0E+2` do not create false mutations;
- no hidden financial mutation in another vault;
- REAL_CAPITAL=0 and production-authority=false boundaries.

The full replay audit fails closed when persisted evidence is missing.

## Deliberate authority boundaries

R22 does **not**:

- submit real or simulated exchange orders;
- create exchange/network/credential authority;
- enable leverage, borrowing or martingale;
- activate a production scheduler or unattended capital mutation;
- promote Shadow Lab research automatically;
- rewrite Epoch 1;
- deploy to the SSD merely because hosted tests pass.

This Phase 17 implementation is paper accounting/audit infrastructure only.

## Hosted acceptance evidence

At exact branch head `83db1c1c36bb48d6d8073dcddda9214fdea227e4`,
GitHub Actions run `35865395011` passed:

- focused R22 transaction + atomic-accounting tests;
- Ruff on R22 source/tests;
- strict mypy on R22 source;
- whole-repository pytest;
- whole-repository Ruff;
- whole-repository strict mypy;
- product JavaScript syntax checks;
- product freshness contract.

The run emitted `R22_SLICE1_HOSTED_FULL_PASS=YES`.

A final documentation commit and its exact-head rerun are still required before merge.
Wake/lease remains user-paused and duplicate/stale R22 branches are not replayed.

## Phase 17 exit interpretation

The locked roadmap requires that any canonical paper NAV movement be explainable from
the tape. The accepted R22 contract above provides the immutable provenance required
for that explanation while preserving REAL_CAPITAL=0.

Status: **PHASE 17 MERGE CANDIDATE — exact-head hosted gate required after this document update.**
