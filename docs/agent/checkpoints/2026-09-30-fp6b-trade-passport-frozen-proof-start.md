# Crypto Signal — FP6-B Live Checkpoint

Status: **ACTIVE / TEST ACCEPTANCE PENDING**
Date: 2026-09-30
Repository: `burakciller90-arch/Crypto-Signal`
Canonical roadmap: `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
Active pointer: `ACTIVE_ROADMAP.md`
Task-start main: `38d757071a50566379715f3074b4b74b668a6aa6`
Active branch: `fp6b/trade-passport-frozen-proof`
Draft PR: `#1737`
Current branch head before this checkpoint update: `ecb949dcce578de60d2a7848b6f310afa0b130d5`
Safety: `REAL_CAPITAL=0`

## Current program state

- FP0 / RDP11 remains mechanically **ACTIVE / NOT PASS** on the isolated R2 soak. Do not mutate the frozen Product/Development soak target, observer contract, or historical/frozen evidence.
- FP1–FP5 accepted work is reuse authority; do not rebuild it.
- FP6-A merged as PR #1705 / main `38d757071a50566379715f3074b4b74b668a6aa6` after exact-head FP6-A + WC6 + RDP11 Pre-Soak + F10 acceptance.
- FP6 is the current parallel product frontier while FP0 remains time/evidence gated.

## Duplicate audit

Live GitHub recheck found:
- current `main` still `38d757071a50566379715f3074b4b74b668a6aa6` before FP6-B coding;
- no FP6-B branch or PR pre-existed;
- existing FP6 branches are FP6-A/runner/acceptance remnants only.

Classification:
- **REUSE** R22/R21 immutable transaction/accounting lineage and FP6-A lifecycle reconstruction;
- **REUSE** FP1-E immutable Trade Passport read model;
- **REUSE** S10 `IntelligenceStreamVisualProofReadModel` for frozen historical chart/annotation proof;
- **REUSE** RDP10 `IntelligenceStreamExactEvidenceReadModel` for exact persisted family/source proof;
- **EXTEND** read-only Trade Passport proof projection;
- **BUILD: NO** new canonical ledger/store/schema/writer/evidence engine.

## First mechanically open FP6 requirement

Master-roadmap FP6 PASS requires **every lifecycle event to open the exact proof that existed at that time**.

FP6-A correctly reconstructs OPEN / SCALE_IN / PARTIAL_TAKE_PROFIT / REDUCE / CLOSE and reopens each exact Trade Passport, but the current customer Trade Passport view exposes only a decision-proof summary. It does not yet directly bind each event to accepted frozen Market Story / exact family proof.

## Implemented so far

Commit `8b5ab765a74c0daafd664e4b3a78ee312b51b1d7`:
- added `src/crypto_signal/product/trade_passport_frozen_proof.py`;
- reads exact `forecast_identity + proof_identity + signal_freeze_identity` from existing Trade Passport audit lineage;
- resolves exactly one persisted Stream narrative through read-only SQL over existing immutable Stream tables;
- re-verifies the narrative with `IntelligenceStreamReadModel`;
- reuses S10 `IntelligenceStreamVisualProofReadModel` for frozen candles/annotations;
- reuses RDP10 `IntelligenceStreamExactEvidenceReadModel` for exact family/source proof;
- rejects ambiguous/mismatched lineage;
- requires `current_data_substitution=false`;
- no canonical writer/store/schema/backfill added.

Commit `ecb949dcce578de60d2a7848b6f310afa0b130d5`:
- added `tests/test_fp6b_trade_passport_frozen_proof.py`;
- covers exact-lineage proof opening, source DB byte immutability, explicit missing-lineage behavior, signal-lineage mismatch fail-closed behavior, and invalid identity rejection before lookup.

Draft PR `#1737` opened only as an acceptance vehicle. It must not merge before all required mechanical gates pass on one final candidate SHA.

## Acceptance currently running

PR-head workflows observed after opening #1737:
- RDP11 Pre-Soak Fulltest UID504 — run `36706151196` — queued at last check;
- Crypto Stream Final F10 Closeout Prep UID504 — run `36706150990` — in progress at last check;
- Crypto Stream Final F7 Local Rewrite Prep UID504 — run `36706151080` — in progress at last check;
- Crypto Stream Final F9 Real UI Acceptance — run `36706151189` — in progress at last check.

A dedicated FP6-B focused acceptance still needs to be established/run; generic workflow SUCCESS alone is not FP6-B PASS.

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

- `CURRENT_FRONTIER.md` (~382 KB) and `HANDOFF_LOG.md` (~305 KB) on `main` are stale relative to FP6-A. Do not overwrite them from truncated reads. Reconcile them losslessly before final handoff/merge or add an authoritative bootstrap pointer to this live checkpoint.
- UID504 runner startup was repaired for the immediate FP6-A blocker, but daily sleep/shutdown/network-loss resilience has not all been mechanically exercised as durable operational acceptance.
- FP0/RDP11 remains independently open until its real accumulated evidence audit passes; elapsed time alone is not PASS.
- After FP6-B, audit all remaining FP6 master clauses before advancing to FP7; likely checks include funding/latency/partial-fill/queue visibility plus whole-phase immutable-archive acceptance.

## Exact next action

Read PR #1737 workflow results/logs. Fix any code/test issue first. Then add/confirm a dedicated FP6-B exact-head gate that runs the new focused test plus relevant FP6-A/read-model regressions, Ruff, strict mypy/py_compile, and non-mutation assertions. Before any merge, recheck latest `main`, reconcile parallel changes if any, and rerun FP6-B + WC6 + RDP11 Pre-Soak + F10 on the single final candidate SHA.
