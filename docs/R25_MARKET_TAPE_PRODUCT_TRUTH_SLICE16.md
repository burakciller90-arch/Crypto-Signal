# R25 Slice 16 — Market Tape / Cold Archive Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice replaces the old static GALACTECH `NOT EXPOSED` labels for Hot Market
Tape and Cold Archive with bounded, read-only runtime evidence adapters.

It deliberately does **not** claim a collector process is ONLINE merely because
persisted evidence is readable.

## Hot Market Tape truth

`GET /api/market-tape-runtime/status`

The adapter opens the configured normalized Market Tape SQLite database with
`mode=ro` and `query_only=ON`.

It verifies:
- SQLite `PRAGMA quick_check`;
- accepted Market Tape schema version;
- required table presence;
- required accepted schema columns;
- row counts per evidence class;
- latest persisted evidence timestamp;
- age of the latest persisted evidence at the requested observation time.

The Product surface reports:
- persisted row count;
- latest evidence age;
- read-only integrity.

It always reports:
- collection process status = `NOT_MEASURED`;
- ONLINE status = `NOT_ASSERTED`.

The endpoint never calls `MarketTapeStore.initialize()`, never creates a missing
database and never performs migration or WAL writes.

## Cold Archive truth

`GET /api/cold-archive/status?verify_limit=N`

The adapter:
- requires an explicitly configured archive directory;
- discovers immutable hourly partition manifests;
- enforces accepted v1/1 or v1/2 table-key contracts;
- enforces exact accepted parquet filenames;
- validates row/file metadata;
- verifies file byte length and SHA256 for the selected latest partitions;
- never creates an archive directory or partition.

GALACTECH boot requests the latest 24 partitions. The R25 operational summary checks
only the latest partition so boot reconciliation does not repeatedly hash a large
archive.

This Product adapter does not import PyArrow and therefore does not replay Parquet
rows to recompute the canonical row digest. It reports
`canonical_row_digest_replay = NOT_MEASURED` rather than overstating verification.

Archive-process liveness remains `NOT_MEASURED`.

## GALACTECH System Truth

The previous static cards become dynamic:
- MARKET TAPE RUNTIME: persisted row evidence when configured and verified;
- COLD ARCHIVE: verified / total partition scope;
- EVENT SOURCE RUNTIME remains `NOT EXPOSED` until a separate exact runtime adapter exists.

The UI explicitly says:
- ONLINE NOT ASSERTED;
- process NOT MEASURED;
- universal freshness is not inferred.

## Operational Truth

Market Tape and Cold Archive are added as informational components to the existing R25
operational reconciliation.

They are **not** added to the existing required R25 decision/capital evidence set, so
absence of optional market-data runtime wiring cannot silently invalidate already
accepted Decision Evidence / Shadow / Epoch 2 runtime truth.

## Authority

No:
- exchange/network credentials;
- collector activation;
- runtime supervisor change;
- canonical Epoch 2 mutation;
- order/fill authority;
- production cutover;
- real capital.

REAL_CAPITAL=0.

## Next frontier

After exact-head and whole-repository acceptance, inspect Event Risk calendar/news
runtime persistence. Only if an exact persisted runtime-health source exists should
GALACTECH replace EVENT SOURCE RUNTIME = NOT EXPOSED. Otherwise the truthful state
must remain unexposed.
