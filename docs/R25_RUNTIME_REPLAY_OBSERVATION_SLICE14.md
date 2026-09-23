# R25 Slice 14 — Runtime Restart / Replay Observation

Status: development candidate. REAL_CAPITAL=0.

This slice introduces a separate immutable runtime observation artefact for one
specific persisted shadow cycle.

It is deliberately stronger than CI acceptance.

## VERIFIED requirements

A replay observation can be constructed only when:

1. First complete persisted run:
   - shadow intent journal = INSERTED;
   - shadow cycle manifest = INSERTED.
2. Exact replay:
   - shadow intent journal = IDEMPOTENT;
   - shadow cycle manifest = IDEMPOTENT.
3. The immutable lineage is byte/identity equivalent across both runs:
   - persisted cycle;
   - cycle;
   - forecast;
   - Decision Proof;
   - Capital Science;
   - Position Sizing;
   - optional explicit review;
   - R22 preview;
   - journal record;
   - cycle manifest;
   - vault / reviewed method.
4. Both observations are bound to one explicit immutable
   `runtime_instance_identity`.
5. Replay observation time is strictly later than first observation time.

If any condition fails, no VERIFIED observation can be created.

## Store isolation

Runtime replay observations are persisted only in a dedicated
`*.shadow-replay.sqlite3` database.

The store:
- refuses non-replay application tables;
- is append-only;
- blocks UPDATE/DELETE for observations and metadata;
- enforces one observation per runtime-instance + cycle;
- exact re-append is idempotent;
- conflicting rewrite fails closed;
- verifies SQLite quick_check and canonical payload SHA on read;
- supports exact forecast SHA lookup.

## Truth boundary

This artefact is the only source allowed to support a future product label such
as `RESTART / REPLAY VERIFIED` for a concrete runtime cycle.

Hosted CI tests by themselves do not create this runtime observation.

## Authority

The observation is audit evidence only. It does not grant:
- canonical Epoch 2 mutation;
- simulated fill;
- cash/position mutation;
- exchange order;
- network/credential authority;
- leverage/borrowing;
- production activation.

REAL_CAPITAL=0.

## Next frontier

After hosted focused + whole-repository acceptance, expose this observation
read-only through the exact forecast/cycle Product API and GALACTECH. When the
observation runtime is absent, the UI must remain `NOT MEASURED`.