# R25 Slice 14 — Shadow Cycle Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice exposes the immutable Shadow Cycle Manifest through a dedicated
read-only Product API and upgrades GALACTECH to show persisted stage lineage
without confusing journal integrity with a runtime restart/replay observation.

## Product API

`GET /api/shadow-cycle/status` is read-only.

If no manifest runtime is configured:
- status = unavailable;
- restart/replay runtime = NOT_MEASURED;
- canonical Epoch 2 mutation = false;
- production authority = false.

If a configured manifest is missing:
- the endpoint remains unavailable;
- no file is created.

If the manifest exists:
- SQLite quick_check + immutable manifest verification runs;
- latest manifest records are returned;
- exact forecast, Decision Proof, Capital Science, Position Sizing, optional
  explicit review, R22 preview and shadow journal record identities are exposed;
- both manifest and journal remain byte-for-byte unchanged by the GET.

Malformed/non-manifest databases fail closed.

## GALACTECH truth correction

The prior shadow-journal surface used a label equivalent to “REPLAY VERIFIED”
when journal quick_check + read-only verification passed.

That is too broad.

Slice 14 changes the semantics:
- journal quick_check/read-only verification = JOURNAL INTEGRITY;
- persisted cycle manifest = LINEAGE PERSISTED;
- process restart/replay runtime observation = NOT MEASURED unless separately
  persisted as its own evidence.

A manifest does not prove that the deployed runtime restarted. CI acceptance
also does not prove deployed-runtime replay.

## Visible decision rail

When an immutable cycle manifest exists, GALACTECH can truthfully display:
Decision Proof -> Capital Science -> Position Sizing -> Review -> R22 Preview ->
Shadow Journal -> Cycle Manifest.

Missing manifest evidence remains NOT PERSISTED.

## Authority

Read-only Product projection only. No:
- shadow journal write;
- cycle manifest write;
- canonical Epoch 2 mutation;
- fill/cash/position mutation;
- exchange/network/credential authority;
- automatic sizing selection;
- production deployment;
- leverage/borrowing.

REAL_CAPITAL=0.

## Next frontier

Persist an explicit **runtime replay observation** only when a real runtime
restart/recovery execution actually occurs and reconciles the same cycle
identities. Until then the product must continue to show NOT MEASURED.