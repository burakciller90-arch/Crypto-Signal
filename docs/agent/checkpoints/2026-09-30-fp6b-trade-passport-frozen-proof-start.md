# Crypto Signal — FP6-B Live Checkpoint

Status: **ACTIVE / TEST ACCEPTANCE PENDING**
Date: 2026-09-30
Repository: `burakciller90-arch/Crypto-Signal`
Canonical roadmap: `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
Active pointer: `ACTIVE_ROADMAP.md`
Task-start main: `38d757071a50566379715f3074b4b74b668a6aa6`
Active branch: `fp6b/trade-passport-frozen-proof`
Draft PR: `#1737`
Current branch head before this checkpoint update: `32281aa4613f1ca2d0be685368df98073b15b782`
Safety: `REAL_CAPITAL=0`

## Current program state

- FP0 / RDP11 remains mechanically **ACTIVE / NOT PASS** on the isolated R2 soak. Do not mutate the frozen Product/Development soak target, observer contract, or historical/frozen evidence.
- FP1–FP5 accepted work is reuse authority; do not rebuild it.
- FP6-A merged as PR #1705 / main `38d757071a50566379715f3074b4b74b668a6aa6` after exact-head FP6-A + WC6 + RDP11 Pre-Soak + F10 acceptance.
- FP6 is the current parallel product frontier while FP0 remains time/evidence gated.

## Duplicate audit

Live GitHub recheck found:
- current `main` is still `38d757071a50566379715f3074b4b74b668a6aa6` at this continuation checkpoint;
- draft PR #1737 is still open, mergeable, and based on that exact main SHA;
- no parallel `main` drift was present at this checkpoint.

Classification:
- **REUSE** R22/R21 immutable transaction/accounting lineage and FP6-A lifecycle reconstruction;
- **REUSE** FP1-E immutable Trade Passport read model;
- **REUSE** S10 `IntelligenceStreamVisualProofReadModel` for frozen historical chart/annotation proof;
- **REUSE** RDP10 `IntelligenceStreamExactEvidenceReadModel` for exact persisted family/source proof;
- **EXTEND** read-only Trade Passport proof projection;
- **BUILD: NO** new canonical ledger/store/schema/writer/evidence engine.

## Canonical FP6 master clauses being enforced

From `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`:
- passport identity must expose asset/action/vault/policy/open-close time/size/result;
- “What did the system see?” must expose frozen Market Story, exact five-family states, source/provider/time, Event Risk and exact trigger/invalidation/targets;
- execution must expose signal/reference price, simulated fill, fill status, fee/spread/slippage plus funding/latency/partial-fill/queue status where applicable;
- lifecycle is append-only and includes OPEN / SCALE_IN / STOP_UPDATE / PARTIAL_TAKE_PROFIT / REDUCE / CLOSE / CORRECTION-SUPERSEDED when required;
- PASS requires reconstruction solely from accepted immutable records, every lifecycle event opening the exact proof that existed then, losses being equally inspectable, and later model versions being unable to alter historical content.

## Implemented so far

Commit `8b5ab765a74c0daafd664e4b3a78ee312b51b1d7`:
- added `src/crypto_signal/product/trade_passport_frozen_proof.py`;
- reads `forecast_identity + proof_identity + signal_freeze_identity` from existing Trade Passport audit lineage;
- reuses S10 frozen visual proof and RDP10 exact family/source proof;
- requires `current_data_substitution=false`;
- no canonical writer/store/schema/backfill added.

Commit `ecb949dcce578de60d2a7848b6f310afa0b130d5`:
- added `tests/test_fp6b_trade_passport_frozen_proof.py`;
- covers exact-lineage proof opening, source DB byte immutability, explicit missing-lineage behavior, signal-lineage mismatch fail-closed behavior, and invalid identity rejection before lookup.

Draft PR `#1737` is an acceptance vehicle only. It must not merge before all required mechanical gates pass on one final candidate SHA.

## Continuation audit — active problem found

The current resolver still selects Stream candidates using only `forecast_identity + proof_identity` and then requires exactly one narrative. That is too coarse for the FP6 historical guarantee because one accepted decision truth can legitimately have more than one persisted Stream narrative/story revision.

The safe selection key is:
1. exact Trade Passport `forecast_identity`;
2. exact Trade Passport `proof_identity`;
3. exact Trade Passport `signal_freeze_identity` resolved through S10 proof lineage;
4. for a lifecycle event, the narrative must have existed by that event (`event_at_ms <= passport.filled_at_ms` / lifecycle event time);
5. among exact-lineage candidates already existing at that time, select the latest persisted narrative deterministically; same-timestamp competing exact candidates remain fail-closed.

This prevents a later Stream rewrite/story from being substituted into an earlier trade event while also avoiding false ambiguity merely because accepted history contains multiple narrative revisions.

## Acceptance status / known limitation

Generic F10 green is **not** FP6-B PASS. It does not execute the new focused test and PR-event runs may checkout a GitHub merge ref. FP6-B requires a dedicated exact-head workflow modeled on the accepted FP6-A gate.

Required dedicated gate:
- exact PR head checkout and explicit SHA assertion;
- frozen RDP11 Product/Development target assertion (`3d9f33db3f1189571d40566125fbeabd00c04930`);
- focused FP6-B proof tests;
- FP6-A lifecycle regression;
- S10 visual-proof regression;
- RDP10 exact-evidence regression;
- Final Product read-model regression;
- R22/FP3 regressions where relevant;
- Ruff + mypy;
- whole-repository regression;
- post-run Product/Development non-mutation proof.

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

- `CURRENT_FRONTIER.md` and `HANDOFF_LOG.md` are large and must never be overwritten from truncated connector reads. Reconcile losslessly before final handoff/merge; this live checkpoint remains the authoritative in-flight FP6-B continuation record until that reconciliation.
- UID504 runner startup was repaired for the immediate FP6-A blocker, but daily sleep/shutdown/network-loss resilience has not all been mechanically exercised as durable operational acceptance.
- FP0/RDP11 remains independently open until its real accumulated evidence audit passes; elapsed time alone is not PASS.
- FP6-B closes only the first still-open FP6 master clause. Before FP7, separately audit remaining execution visibility (funding/latency/partial-fill/queue/fill-not-proven) and immutable archive/later-model immutability clauses.

## Exact next action

1. Change FP6-B resolver to exact triple + event-time selection.
2. Add tests proving later narratives cannot rewrite earlier lifecycle-event proof and proving every lifecycle event opens proof through its own immutable passport lineage.
3. Add dedicated exact-head FP6-B UID504 acceptance workflow.
4. Run/inspect dedicated FP6-B workflow and fix failures.
5. Recheck latest `main`, then require FP6-B + WC6 + RDP11 Pre-Soak + F10 on one final candidate SHA before any merge.
