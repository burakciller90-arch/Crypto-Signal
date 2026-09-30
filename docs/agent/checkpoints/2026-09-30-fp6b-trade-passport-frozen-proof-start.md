# Crypto Signal — FP6-B Live Checkpoint

Status: **ACTIVE / IMPLEMENTATION NOT YET STARTED**
Date: 2026-09-30
Repository: `burakciller90-arch/Crypto-Signal`
Canonical roadmap: `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
Active pointer: `ACTIVE_ROADMAP.md`
Task-start main: `38d757071a50566379715f3074b4b74b668a6aa6`
Active branch: `fp6b/trade-passport-frozen-proof`
Safety: `REAL_CAPITAL=0`

## Current program state

- FP0 / RDP11 remains mechanically **ACTIVE / NOT PASS** on the isolated R2 soak. Do not mutate the frozen Product/Development soak target, observer contract, or historical/frozen evidence.
- FP1–FP5 accepted work is reuse authority; do not rebuild it.
- FP6-A merged as PR #1705 / main `38d757071a50566379715f3074b4b74b668a6aa6` after exact-head FP6-A + WC6 + RDP11 Pre-Soak + F10 acceptance.
- FP6 is the current parallel product frontier while FP0 remains time/evidence gated.

## Duplicate audit before implementation

Live GitHub recheck on task start found:
- current `main` still `38d757071a50566379715f3074b4b74b668a6aa6`;
- no FP6-B branch exists;
- no open/merged PR already implements the same Trade Passport frozen-proof event binding;
- existing FP6 branches are FP6-A/runner/acceptance remnants only.

Classification:
- **REUSE** R22/R21 immutable transaction/accounting lineage and FP6-A lifecycle reconstruction;
- **REUSE** FP1-E immutable Trade Passport read model;
- **REUSE** S10 `IntelligenceStreamVisualProofReadModel` for frozen historical chart/annotation proof;
- **REUSE** RDP10 `IntelligenceStreamExactEvidenceReadModel` for exact persisted family/source proof;
- **EXTEND** read-only Trade Passport proof projection so every lifecycle event can open the exact persisted proof that existed at that time;
- **BUILD: NO** new canonical ledger/store/schema/writer/evidence engine.

## First mechanically open FP6 requirement

Master-roadmap FP6 PASS requires **every lifecycle event to open the exact proof that existed at that time**.

FP6-A correctly reconstructs OPEN / SCALE_IN / PARTIAL_TAKE_PROFIT / REDUCE / CLOSE and reopens each exact Trade Passport, but the current customer Trade Passport view exposes only a decision-proof summary. It does not yet provide a direct event-level customer projection into the accepted frozen Market Story / exact family proof stack.

The existing Trade Passport audit already preserves the exact immutable `forecast_identity`, `proof_identity`, and `signal_freeze_identity`. The implementation must resolve from those identities and fail closed; it must never substitute current market data or recompute historical evidence.

## Bounded FP6-B goal

Create the smallest read-only bridge from each FP6 lifecycle event to accepted historical proof owners:
1. deterministically resolve the persisted Stream narrative bound to the event's exact forecast/proof lineage;
2. verify the resolved narrative is bound to the same forecast/proof/signal-freeze lineage as the Trade Passport;
3. reuse S10 frozen visual proof for issuance-time chart/annotations;
4. reuse RDP10 exact evidence for exact persisted family/source proof where available;
5. expose explicit unavailable/fail-closed state when exact historical proof cannot be resolved;
6. prove source databases are not mutated and `current_data_substitution=false`.

## Explicit non-goals / forbidden work

- no second Trade Passport ledger;
- no second evidence database;
- no historical backfill;
- no current-data substitution;
- no Product/Development deployment;
- no RDP11 observer/soak mutation;
- no real-money/exchange authority;
- no changes to Durdurulmaz or Quantum Capital.

## Other active project risks retained for handoff

These are not ignored merely because FP6-B is bounded:
- `CURRENT_FRONTIER.md` and `HANDOFF_LOG.md` on `main` are stale relative to FP6-A; they must be reconciled without truncating their large historical contents before final handoff/merge.
- UID504 runner startup was repaired for the immediate FP6-A blocker, but daily sleep/shutdown/network-loss resilience has not all been mechanically exercised as durable operational acceptance.
- FP0/RDP11 remains independently open until its real 72h accumulated evidence audit passes; elapsed time alone is not PASS.
- After FP6-B, audit all remaining FP6 master clauses before advancing to FP7; likely checks include execution semantics such as funding/latency/partial-fill/queue visibility and whole-phase immutable-archive acceptance.

## Exact next action

Inspect current Stream persistence lineage and add a read-only exact-lineage resolver that maps a Trade Passport event's `forecast_identity + proof_identity + signal_freeze_identity` to exactly one persisted decision narrative, then compose the existing S10/RDP10 proof readers over that narrative. Add deterministic tests before acceptance workflow work.
