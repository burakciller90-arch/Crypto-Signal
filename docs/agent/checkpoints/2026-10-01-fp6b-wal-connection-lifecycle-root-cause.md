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
