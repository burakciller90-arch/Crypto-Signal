# R25 Slice 9 — Isolated Shadow Intent Journal

Status: development candidate. REAL_CAPITAL=0.

This slice adds an append-only SQLite journal for R22 intent **preview evidence only**. It is intentionally separate from canonical Epoch 2 accounting and from the accepted R22 transaction tape.

## Isolation

The journal accepts only paths ending in `.shadow-intent.sqlite3`.

Before creating its own schema, it inspects the target database. If any non-shadow table already exists, initialization fails closed. This prevents an accidental path from adding shadow tables to a canonical R21/R22 database.

The journal never imports or calls:
- canonical Epoch 2 accounting committers;
- R22 atomic transaction tape writers;
- exchange/network/credential code.

## Integrity

Each persisted preview stores the canonical preview payload excluding its self-identity. The stored payload SHA256 must equal the immutable `preview_identity`.

Each journal row has its own immutable record identity binding:
- preview identity;
- vault;
- event time;
- previous journal record;
- schema/engine;
- authority flags.

Per-vault event time is strictly monotonic. Backfill and same-time forks fail closed. Re-appending the exact same preview is idempotent.

UPDATE and DELETE are blocked with SQLite triggers.

Read-only verification:
- opens SQLite in `mode=ro`;
- runs `PRAGMA quick_check`;
- validates journal metadata;
- re-hashes every persisted preview payload;
- verifies every journal record identity;
- verifies per-vault predecessor chains;
- verifies all persisted authority flags remain false and REAL_CAPITAL=0.

## Authority

This journal records research/shadow intent evidence only.

It does not create:
- canonical Epoch 2 mutation;
- simulated fill;
- position/cash mutation;
- order authority;
- exchange credential use;
- leverage or borrowing;
- production deployment.

## Next frontier

After exact-head + whole-repository acceptance, add bounded restart/replay orchestration around the accepted decision → capital → sizing → preview → shadow-journal path. That orchestration must remain development/shadow-only and must prove idempotence across process restart before any separately authorized canonical paper writer activation.