# FP6-A SQLite SHM Oracle Diagnosis — 2026-09-30

Status: ACTIVE BLOCKER DIAGNOSED / REPAIR NOT YET APPLIED

## Exact Git/GitHub state at checkpoint

- Repository: `burakciller90-arch/Crypto-Signal`
- PR: `#1705` — `FP6-A: reconstruct immutable Trade Passport lifecycle`
- Branch: `fp6a/trade-passport-lifecycle-audit`
- Pre-checkpoint branch head: `59e52b1263df346cdafea045a664526c8c5f23f3`
- Canonical `main` at recheck: `c1263bc073f78caea12b088e95447c3cae91bf50`
- PR base SHA at recheck: `c1263bc073f78caea12b088e95447c3cae91bf50`
- PR remained OPEN and mergeable at the pre-repair recheck.

## Exact failing acceptance evidence

- Workflow run: `36678699513`
- Job: `109769220219`
- Job name: `FP6-A exact-head Trade Passport lifecycle acceptance`
- Checked-out source SHA: `59e52b1263df346cdafea045a664526c8c5f23f3`
- Failing step: `Focused FP6-A lifecycle tests`
- Failing test:
  `tests/test_fp6a_trade_passport_lifecycle.py::test_fp6a_single_open_bundle_projects_one_open_episode_read_only`
- Assertion location: `tests/test_fp6a_trade_passport_lifecycle.py:202`
- Assertion:
  `assert _sqlite_sidecar_bytes(epoch2_path) == before_sidecars`
- Exact observed difference: the main SQLite database bytes remained unchanged and the `-wal` sidecar was identical; the `-shm` sidecar bytes differed.
- All lifecycle projection assertions preceding this mutation oracle passed: availability, OPEN state, Core vault, BTCUSDT, one event, exact audit bundle lineage, and open-event classification.

## Root-cause diagnosis

This failure is an acceptance-oracle defect, not evidence of a canonical paper-ledger write by FP6-A.

The test currently treats both SQLite WAL sidecars as immutable data payloads. That is too strong for `-shm`: SQLite's WAL shared-memory file contains coordination / reader metadata and may change as a consequence of opening and using a read-only connection even when the database file and WAL payload are not mutated. Therefore byte-for-byte `-shm` equality is not a valid source-immutability oracle.

The valid immutable-source evidence for this fixture is:

1. canonical Epoch 2 database file bytes unchanged;
2. WAL payload bytes unchanged (including existence/non-existence state);
3. no new canonical ledger/database/schema/writer introduced by FP6-A;
4. lifecycle values are reconstructed from existing immutable R22/R21 truth only;
5. exact lifecycle/audit assertions still pass.

The repair must not weaken product semantics, write to the Epoch 2 database, alter RDP11, backfill history, or deploy Product/Development.

## Systems affected

- FP6-A focused acceptance test oracle only.
- No evidence currently implicates `FinalProductReadModel.trade_lifecycle()` in a canonical database/WAL write.
- RDP11 R2 soak/runtime/observer is out of scope and must remain untouched.
- Durdurulmaz and Quantum Capital are out of scope.
- `REAL_CAPITAL=0` remains binding.

## Next action

1. Change the FP6-A read-only test helper/assertions so source immutability compares canonical DB bytes plus WAL payload/existence, while explicitly excluding volatile SQLite `-shm` coordination bytes from the immutability oracle.
2. Keep lifecycle semantic/audit assertions unchanged.
3. Commit the minimal test-oracle repair on this branch.
4. Re-run the exact-head dedicated FP6-A acceptance.
5. Require the PR body's full acceptance set on the same final head: dedicated FP6-A + WC6 + RDP11 Pre-Soak + F10 mechanical SUCCESS.
6. Before merge, re-read live `main`, PR head and acceptance SHAs; never infer PASS from commit/workflow status alone.
7. After exact-head PASS, update `docs/agent/CURRENT_FRONTIER.md` and `docs/agent/HANDOFF_LOG.md` with final SHA/run/job evidence and next frontier.

## Safety / continuity lock

- Active RDP11 replacement epoch: `rdp11-3d9f33db-20260930-r2`.
- Frozen runtime target remains `3d9f33db3f1189571d40566125fbeabd00c04930`.
- R2 anchor remains run `36637452090`, attempt 2 / job `109642444475`.
- Earliest 72h eligibility remains `2026-10-03T01:10:09.650000+03:00`; elapsed time alone cannot produce PASS.
- No runtime mutation, backfill, deployment, historical rewrite, Durdurulmaz change or Quantum Capital change is authorized by this checkpoint.
