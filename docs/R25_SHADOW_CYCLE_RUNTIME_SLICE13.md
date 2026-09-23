# R25 Slice 13 — Restart-Safe Persisted Shadow Cycle

Status: development candidate. REAL_CAPITAL=0.

This slice composes the accepted shadow replay rail and immutable Shadow Cycle
Manifest into one recoverable persistence operation.

## Problem closed

The shadow intent journal and shadow cycle manifest are deliberately separate
append-only stores. Therefore a process can theoretically stop after the journal
append succeeds but before the manifest append occurs.

This slice makes that partial state restart-safe.

On replay with the same immutable inputs:
- the R22 preview identity is reproduced;
- the existing shadow journal record is returned IDEMPOTENT;
- the exact same cycle identity is reproduced;
- the missing Shadow Cycle Manifest is inserted;
- no duplicate decision, preview or journal record is created.

If both stores already contain the exact cycle, both appends are idempotent.

## Failure behavior

- unavailable Kelly review fails before either store is created;
- HOLD_CASH cycles persist with null review/method rather than fabricated trade
  lineage;
- a malformed/non-shadow manifest database fails closed;
- after such a manifest failure, the already accepted journal evidence remains
  immutable and can be reconciled into a clean manifest store on restart.

## Integrity

The persisted-cycle identity binds:
- deterministic cycle identity;
- journal record identity;
- manifest identity;
- preview identity;
- engine version;
- authority boundaries.

The manifest independently binds forecast, Decision Proof, Capital Science,
Position Sizing, optional explicit review, preview and journal identities.

## Authority

This remains shadow/research infrastructure only.

It introduces no:
- canonical Epoch 2 mutation;
- fill/cash/position writer;
- exchange/network/credential access;
- automatic sizing-method selection;
- leverage/borrowing;
- production activation.

REAL_CAPITAL=0.

## Next frontier

After exact-head and whole-repository acceptance, Product API/GALACTECH can read
the cycle manifest and truthfully expose stage-by-stage persisted lineage:
Decision Proof -> Capital Science -> Position Sizing -> Review -> R22 Preview ->
Journal -> Cycle Manifest.

A separate persisted runtime replay observation is still required before the UI
may claim that a particular deployed runtime restart/replay was observed.