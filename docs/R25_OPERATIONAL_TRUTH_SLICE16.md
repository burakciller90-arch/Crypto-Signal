# R25 Slice 16 — Operational Runtime Truth

Status: development candidate. REAL_CAPITAL=0.

This slice reconciles the major R25 runtime evidence sources in one read-only
Product endpoint and one GALACTECH System Truth panel.

It intentionally does **not** produce a score, ranking, confidence percentage or
generic “production ready” badge.

## Endpoint

`GET /api/r25/operational-truth`

Each source is reported independently:

1. Decision Evidence — R20 forecast / R20.5 Decision Proof ledger status.
2. Shadow Intent Journal — isolated reviewed R22 preview journal verification.
3. Shadow Cycle Manifest — persisted Forecast → Capital Science → Position
   Sizing → Review → Preview → Journal lineage.
4. Runtime Replay Observation — persisted proof that one exact runtime cycle
   was followed by an idempotent restart/replay.
5. Canonical Epoch 2 — read-only canonical R21 accounting activation and latest
   consolidated snapshot.
6. GALACTECH Product — current read-only product exposure at `/galactech`.

For the five evidence stores, a missing/unconfigured source remains
`unavailable` with a concrete reason. Corrupt/incompatible configured evidence
fails closed.

`all_required_runtime_evidence_present=true` means only that all five required
runtime evidence sources are independently readable at request time. It does
not authorize production deployment, canonical mutation, real capital or
exchange execution.

## Read-only acceptance

The complete-runtime acceptance builds all five evidence stores, calls the
endpoint, verifies every component separately, and asserts the database bytes
are unchanged by Product GET.

A missing-runtime acceptance verifies the endpoint creates no evidence files.

## GALACTECH

System Truth gains an `R25 / OPERATIONAL TRUTH` panel with one row per source.

The panel uses:
- READY / EXPOSED when exact runtime evidence exists;
- UNAVAILABLE + exact reason when it does not;
- ALL REQUIRED RUNTIME EVIDENCE PRESENT only when every required evidence
  source is readable;
- PARTIAL RUNTIME EVIDENCE otherwise.

The wording explicitly says partial runtime evidence is not production
readiness.

## Authority

No writer is activated. No canonical Epoch 2 mutation, simulated fill, order,
network/credential authority, leverage, borrowing, production deployment or
real capital is introduced. REAL_CAPITAL=0.

## Next frontier

After exact-head and whole-repository acceptance, R25 development can move to a
closeout/release-candidate reconciliation: update CURRENT_STATUS/Chronicle,
supersede the stale pre-R25 production-cutover candidate, and build a new
latest-main GALACTECH cutover candidate with hosted integrated acceptance.
Physical UID504 production cutover/deploy remains a separate explicit
human-authority boundary.