# Market Tape Runtime Retention V1

Updated: 2026-09-22  
Scope: Crypto Signal v1.1 M1 runtime  
REAL_CAPITAL: 0

## Purpose

The Market Tape is a research evidence store, not an assumption of unlimited disk.
The collector must preserve evidence integrity while preventing the dedicated SSD
from being consumed without a hard bound.

## Measured pilot basis

A canonical SSD pilot first persisted 500 public Bybit wire messages and then an
extended bounded sample persisted another 5,000 messages.

Extended sample evidence:

- 5,000 raw wire messages in 71 wall-clock seconds;
- normalized DB grew by 1,916,928 bytes;
- raw DB grew by 2,826,240 bytes;
- both SQLite stores returned `PRAGMA quick_check=ok`;
- SSD free space remained above 923 GB at the sampled instant.

The observed sample corresponds to roughly 5.8 GB/day if that short-window rate
were sustained continuously. This is a capacity-planning observation, not a promise
of future message rate or storage growth.

## V1 runtime bounds

The runtime is size-bounded rather than pretending a fixed number of days is always
safe:

- active generation seal threshold: **25 GiB**;
- maximum sealed generations: **10**;
- global Market Tape hard cap: **300 GiB**;
- minimum SSD free-space reserve: **250 GiB**;
- collection chunk: **100,000 wire messages**;
- guarded recheck interval: **300 seconds**.

At the measured sample rate the configured generation count is on the order of
several weeks of history, but actual retention duration varies with market activity
and payload size.

## Append-only and rotation semantics

Rows are never aged out of an active SQLite database.

When the active generation reaches its seal threshold:

1. normalized and raw stores must pass `PRAGMA quick_check`;
2. WAL is checkpointed with `TRUNCATE` and must report `busy=0`;
3. the two SQLite databases are moved together into one timestamped sealed
   generation directory;
4. a manifest records row counts, event-time bounds, byte sizes and SHA256 hashes;
5. the next collection chunk initializes a fresh active pair.

This keeps each retained generation immutable at file level instead of deleting old
rows from a live append-only store.

## Retention deletion

Normal retention keeps at most ten sealed generations.

Deletion is whole-generation only. Before an old generation can be removed, both
database files must still match the byte sizes and SHA256 hashes recorded in the
manifest and both must pass SQLite `quick_check`.

A verification failure stops deletion rather than guessing.

Under global-cap or free-space pressure, verified oldest generations may be removed
until collection becomes safe again, but V1 keeps at least one sealed generation.
If the reserve still cannot be restored, collection enters a guarded state instead
of consuming more disk.

## Compaction policy

V1 compaction is deliberately conservative:

- WAL checkpoint/truncation occurs at generation seal;
- no live `VACUUM` is performed during collection;
- no lossy JSON rewriting or derived-data substitution is used;
- sealed SQLite files remain directly reproducible and queryable.

Future archival compression can be added only with manifest/hash verification and a
replay acceptance gate.

## Runtime health

The service writes
`Development/runtime/market_tape/runtime_status.json` atomically with:

- collector state;
- latest cycle;
- latest persisted counts;
- active generation bytes;
- total tape bytes;
- SSD free bytes;
- capacity decision;
- sealed-generation count;
- rotation/pruning events;
- `real_capital=0`.

The production service has no internal-Mac data fallback. If the canonical
`/Volumes/Crypto-504` root is unavailable, startup fails closed and launchd retries
after its throttle interval.
