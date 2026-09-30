# FP6-A WC6 Trigger Blocker — 2026-09-30

Status: ACTIVE ACCEPTANCE BLOCKER DIAGNOSED / CI-TRIGGER REPAIR NOT YET APPLIED

## Exact state at checkpoint

- Repository: `burakciller90-arch/Crypto-Signal`
- PR: `#1705` — `FP6-A: reconstruct immutable Trade Passport lifecycle`
- Branch: `fp6a/trade-passport-lifecycle-audit`
- Pre-checkpoint PR head: `707219a89c4c050f256cc1f2f2f2fc24fca48b7c`
- Canonical `main`: `c1263bc073f78caea12b088e95447c3cae91bf50`
- PR remains OPEN / mergeable at this checkpoint.

## Required exact-head acceptance contract

PR #1705 requires all four gates on the same final head before merge:

1. FP6-A dedicated acceptance
2. WC6 Paper Recovery Reconciliation
3. RDP11 Pre-Soak Fulltest
4. F10 mechanical closeout

For pre-checkpoint head `707219a89c4c050f256cc1f2f2f2fc24fca48b7c`, pull-request-triggered runs observed were:

- FP6-A: run `36690628658` — queued at last observation
- RDP11 Pre-Soak: run `36690628642` — queued at last observation
- F10: run `36690628675` — queued at last observation
- WC6: no pull-request-triggered run existed for this head

Skipped F7/F9 runs are not substitutes for the required gates.

## Root cause

The exact WC6 workflow present in the head tree is:

`.github/workflows/wc6-paper-recovery-reconciliation-uid504.yml`

Its job is `WC6 exact-head paper execution-lab acceptance` and it supports `workflow_dispatch`, but its `pull_request.paths` filter only covers:

- `src/crypto_signal/paper/**`
- `tests/test_paper_*.py`
- `tests/test_wc6_execution_lab.py`
- the WC6 workflow file itself

PR #1705 currently changes only FP6-A workflow/docs/checkpoints, `src/crypto_signal/product/final_product_read_model.py`, and `tests/test_fp6a_trade_passport_lifecycle.py`; none matches the existing WC6 pull-request path filter. Therefore WC6 does not auto-trigger on FP6-A synchronize events even though PR #1705 explicitly requires WC6 exact-head SUCCESS.

The available GitHub connector exposes workflow read/re-run operations but no `workflow_dispatch` creation action. Re-running an older WC6 run would remain bound to its original SHA and is not valid evidence for the current final head.

## Classification

This is a CI acceptance-routing defect, not a product/runtime defect.

- No product code change is justified by this blocker.
- No canonical paper ledger/database/schema/write path is implicated.
- No runtime mutation/backfill/deployment is justified.
- RDP11 R2 runtime/observer/sidecar remains out of scope.

## Repair boundary / nextAction

1. Extend WC6 `pull_request.paths` narrowly so FP6-A lifecycle/read-model changes that explicitly require WC6 can trigger the WC6 exact-head gate. The intended minimal additions are the FP6-A lifecycle source/test paths, not a broad catch-all.
2. Keep WC6 test commands, runner, exact-source assertion and non-mutating Development checks unchanged.
3. Commit the trigger-only repair on PR #1705.
4. Treat the resulting commit as a new candidate head; all four required gates must be re-evaluated on that exact SHA.
5. Before any merge, re-read live `main`, PR head, each required run/job and checked-out SHA. Aggregate workflow status alone is insufficient.
6. Any new failure must be checkpointed before repair.

## Safety / continuity lock

- `REAL_CAPITAL=0` remains binding.
- Active RDP11 replacement epoch: `rdp11-3d9f33db-20260930-r2`.
- Frozen runtime target: `3d9f33db3f1189571d40566125fbeabd00c04930`.
- R2 anchor: run `36637452090`, attempt 2 / job `109642444475`.
- Earliest 72h eligibility: `2026-10-03T01:10:09.650000+03:00`; elapsed time alone cannot produce PASS.
- Frozen/historical evidence is immutable.
- No runtime mutation, backfill, deployment, historical rewrite, Durdurulmaz change or Quantum Capital change is authorized by this checkpoint.
