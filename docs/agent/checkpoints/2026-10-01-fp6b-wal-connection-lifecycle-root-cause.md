# FP6-B WAL connection lifecycle root cause checkpoint — 2026-10-01

## Problem

The clean isolated acceptance environment exposed a real FP6-B read-only mismatch. The first bounded hypothesis (`mode=ro&immutable=1` on frozen readers) stopped physical mutation, but exact-SHA whole-repository regression then failed with `sqlite3.OperationalError: no such table: signal_freezes`.

## Evidence

- Candidate `4d6146b0d2fba5d584071f29377e647de67c53bc` reached WC6 focused acceptance and paper-subsystem regression successfully.
- Whole-repository regression failed in FP6-B / visual-proof / exact-evidence tests because `read_freeze_by_signal()` opened the SQLite main file with `immutable=1`, while committed schema/data were still visible only through WAL.
- `ImmutableSignalLedger.initialize()` and write paths use `with self._connect() as connection:`. Python's `sqlite3.Connection` context manager commits/rolls back but does not close the connection. Connection finalization is therefore left to GC, so WAL checkpoint/close timing is nondeterministic.
- This explains both observed modes: ordinary `mode=ro` sees WAL truth but can coincide with delayed close/checkpoint and change main-file bytes; `immutable=1` guarantees non-mutation but intentionally ignores WAL, so it cannot see a schema/data set stranded there by leaked connections.

## Root cause

The root cause is nondeterministic SQLite connection lifetime in `ImmutableSignalLedger`, not shared-venv contamination and not an FP6-B assertion defect.

## Bounded fix

Preserve transaction semantics and WAL mode, but deterministically close every `_connect()` context in `src/crypto_signal/ledger/store.py` after its existing commit/rollback scope. Use `contextlib.closing` together with the existing `sqlite3.Connection` context manager so exit order remains commit/rollback first, close second. Keep the two frozen reader URIs at `mode=ro&immutable=1`.

Do not weaken tests. Do not change immutable identities, frozen/history content, writer payloads, REAL_CAPITAL, Development, Product, Durdurulmaz, or Quantum Capital.

## Acceptance required

On one exact final candidate SHA:

1. FP6-B focused acceptance must pass, including byte-for-byte non-mutation.
2. WC6 focused + paper regression + whole-repository regression must pass.
3. RDP11 Pre-Soak must pass its actual runtime/startup and full acceptance, independently of RDP11's later 72-hour eligibility gate.
4. F10 Final Closeout must pass.
5. Development remains clean and `REAL_CAPITAL=0`.
6. Only after FP6-B is green, continue to the separate immutable lineage proof: `ExecutionReceiptV2 → R22 immutable tape → Trade Passport`; FP6 remains open until that chain is mechanically proven.

## LIVE continuation checkpoint — sequence 1

- Live `main` re-verified at `38d757071a50566379715f3074b4b74b668a6aa6`.
- PR #1737 remains open/draft on `fp6b/trade-passport-frozen-proof`.
- Product-fix head observed before this checkpoint: `112998033279d555f70bf801a1b2af45d463f78a` (`fix: close immutable ledger sqlite connections deterministically`).
- Diff from prior candidate `4d6146b0d2fba5d584071f29377e647de67c53bc` contains the intended `src/crypto_signal/ledger/store.py` deterministic-close fix, this root-cause checkpoint, and a temporary transport workflow `.github/workflows/fp6b-close-ledger-connections.yml`.
- Exact-head pull-request runs on `1129980…` (including FP6-B `36780718769`, WC6 `36780718826`, RDP11 Pre-Soak `36780718817`, F10 `36780718895`) completed as `action_required` with no jobs for the inspected FP6-B run. These are NOT acceptance results and MUST NOT be treated as PASS/FAIL evidence.
- The inspected FP6-B run reports `triggering_actor=github-actions[bot]` and zero jobs. Do not infer a product failure from this state.
- ACTIVE BLOCKER: remove the temporary transport workflow from the PR while preserving the source fix; then obtain a new exact candidate SHA and rerun/read actual acceptance jobs.
- NEXT ACTION: fetch exact blob SHA for `.github/workflows/fp6b-close-ledger-connections.yml`, delete that helper from this branch only, re-read PR head/diff, then inspect exact-head FP6-B + WC6 + RDP11 + F10 acceptance. No merge until all four have real jobs and their acceptance markers are verified on one exact SHA.
