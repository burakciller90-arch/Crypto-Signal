# Market Tape Runtime Storage V1

Updated: 2026-09-22  
Scope: Crypto Signal v1.1 M1 runtime  
REAL_CAPITAL: 0

## Purpose

The Market Tape is proprietary research evidence. It must preserve raw exchange
messages and normalized evidence without allowing one SQLite B-tree to consume the
dedicated SSD indefinitely.

The accepted V1 direction is **Hot SQLite + Cold Parquet/Zstd**.

## Measured capacity basis

A canonical SSD sample persisted 6,500 raw Bybit wire messages plus normalized
Market Tape evidence.

A longer 5,000-message collection sample observed:

- 5,000 raw wire messages in 71 wall-clock seconds;
- normalized SQLite growth: 1,916,928 bytes;
- raw SQLite growth: 2,826,240 bytes;
- measured short-window rate: about 70.4 raw messages/second;
- extrapolated total SQLite write rate: about 5.38 GiB/day if that short-window
  rate were sustained continuously.

That extrapolation is a capacity-planning observation, not a promise of future
market traffic.

## Real compression benchmark

The canonical 6,500-row dataset was converted read-only with PyArrow 22.0.0 and
Zstandard compression. Every table was read back and compared with a canonical
SHA256 digest before acceptance.

Measured sizes:

- raw SQLite: 3,817,472 bytes;
- normalized SQLite: 2,871,296 bytes;
- combined SQLite: 6,688,768 bytes;
- raw JSONL.zst: 584,515 bytes;
- raw Parquet/Zstd: 578,259 bytes;
- order-book Parquet/Zstd: 87,089 bytes;
- trade Parquet/Zstd: 187,933 bytes;
- combined cold Parquet/Zstd: 853,281 bytes.

Measured compression on this real sample:

- raw Parquet/Zstd vs raw SQLite: **6.60x**;
- raw JSONL.zst vs raw SQLite: **6.53x**;
- full raw + normalized Parquet/Zstd vs full SQLite: **7.84x**.

The project therefore does **not** assume a theoretical 10x-20x compression ratio.
At the measured short-window write rate, 7.84x corresponds to roughly 0.69 GiB/day
of cold data. Actual future storage use depends on market traffic and payload mix.

## Hot tier

Canonical hot storage remains:

- `Development/runtime/market_tape/raw_market_tape.sqlite3`;
- `Development/runtime/market_tape/market_tape.sqlite3`.

Policy:

- target hot window: **24 hours**;
- late-arrival grace: **2 additional hours**;
- archive partition: **1 hour**;
- emergency hot physical-size cap: **25 GiB**;
- no live full `VACUUM` requirement.

SQLite remains useful for current UI/research reads and low-latency replay. Old
verified rows are deleted only after their cold partition is durably written and
verified. Freed SQLite pages are reused by future inserts.

## Cold tier

Canonical cold storage is:

- `/Volumes/Crypto-504/Crypto-Signal/MarketTapeCold/`.

Layout is hourly UTC partitions:

`year=YYYY/month=MM/day=DD/hour=HH/`

Each non-empty table is stored as Parquet with Zstandard level 8:

- `raw.parquet`;
- `orderbooks.parquet`;
- `trades.parquet`;
- `derivatives.parquet` when present.

Each partition also has `manifest.json` containing:

- exact time window;
- schema version;
- row count per table;
- canonical row SHA256 per table;
- Parquet file SHA256;
- file byte size;
- identity-column name;
- compression settings.

## No-loss archival transaction

Hot data is never deleted merely because a Parquet write succeeded.

For every hourly partition:

1. eligible hot rows are read from SQLite in query-only mode;
2. Parquet/Zstd files are written into a temporary partition directory;
3. each Parquet file is read back;
4. row counts and canonical row digests must match the hot source exactly;
5. file SHA256 values are recorded;
6. the complete temporary partition is verified from its manifest;
7. the directory is atomically renamed into its immutable final location;
8. only then are the corresponding hot rows deleted;
9. SQLite WAL is checkpointed and `PRAGMA quick_check` must remain `ok`.

If an existing immutable partition is encountered after an interrupted prune, hot
rows may be deleted only when every remaining identity is already present with
identical canonical content. A late row absent from the immutable archive causes a
fail-closed error; it is not silently discarded.

## Capacity guards

Cold proprietary history is not automatically deleted to make room.

Default bounds:

- hot emergency cap: **25 GiB**;
- cold archive cap: **600 GiB**;
- minimum SSD free-space reserve: **250 GiB**;
- maximum archive work per runtime cycle: **6 hourly partitions**;
- live collection chunk: **100,000 raw messages**.

Before an archive write, the runtime reserves worst-case headroom equal to the
entire current hot footprint. If that temporary duplicate-write headroom would
cross the cold cap or free-space reserve, archival and further collection stop
fail-closed.

At the measured 0.69 GiB/day cold rate, 600 GiB is on the order of 2.4 years of
history. This is an estimate, not a retention guarantee.

## Sampling boundary

The raw Bybit wire journal remains **lossless at the message level**. It is not
reduced to 250 ms or 500 ms snapshots because doing so would discard order-book
delta evidence that may later matter for microstructure, spoofing-candidate or
iceberg-candidate research.

The normalized order-book tape already uses a **1 second snapshot cadence** for
efficient higher-level analysis. All public trades continue to be normalized.

## Dependency isolation

PyArrow is not installed into the main Development virtual environment.

The cold archiver uses a dedicated SSD environment:

`RuntimeEnvs/market-tape-cold`

with pinned `pyarrow==22.0.0`. The collector's primary interpreter remains the
existing Development Python environment.

## Runtime health

The service writes
`Development/runtime/market_tape/runtime_status.json` atomically with:

- collector state and cycle;
- hot bytes;
- cold bytes;
- total tape bytes;
- SSD free bytes;
- capacity decision;
- archived/pruned row counts;
- latest persisted raw/order-book/trade counts;
- `real_capital=0`.

The production service has no internal-Mac data fallback. If the canonical
`/Volumes/Crypto-504` root, cold environment, archive program, integrity checks or
capacity guards are unavailable, collection stops rather than guessing.
