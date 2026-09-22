# M2 Liquidation Hot/Cold Slice 6B

Status: development-only / stacked on accepted Slice 6A  
REAL_CAPITAL: 0  
Production collector activation: **NO**

## Purpose

Integrate accepted observed-liquidation evidence with the accepted Market Tape Hot SQLite
-> Cold Parquet/Zstd architecture without enabling the production liquidation collector.

This is a cross-stack development slice. It reuses the accepted Hot/Cold architecture
and adds liquidation-specific archive/replay semantics.

## Cold schema

New cold partitions use:

- `market-tape-cold-parquet-v1/2`

Added table files:

- `liquidations.parquet`
- `liquidation_coverage.parquet`

Existing v1/1 partitions remain verifiable. They are immutable history and are not
rewritten to manufacture liquidation support.

### Partition time columns

- raw/orderbooks/trades/derivatives/liquidations: `event_at_ms`
- liquidation coverage: `coverage_end_ms`

Coverage is partitioned by its end time because a coverage interval is not complete before
its end.

## Legacy fail-closed boundary

A legacy v1/1 cold partition may be reused only when there are no new hot evidence classes
missing from that immutable partition.

If a liquidation or liquidation-coverage row later appears for a legacy archived hour,
archive recovery fails closed before prune. The late hot evidence remains in SQLite.

## Verified-write-before-prune

The existing archive sequence remains:

1. read hot evidence;
2. write Parquet/Zstd to a temporary partition;
3. read back;
4. verify row counts;
5. verify canonical row digest;
6. verify file SHA;
7. write/verify manifest;
8. atomic rename;
9. only then prune matching hot rows;
10. WAL checkpoint and SQLite quick_check.

Liquidation evidence does not weaken this boundary.

## Cold PIT liquidation replay

Cold replay uses the same scientific key as hot replay:

- exact `coverage_identity`;
- explicit `as_of_ms`.

Replay:

- requires exact persisted coverage;
- rejects future coverage;
- composes liquidation events across every relevant hourly cold partition;
- preserves exchange/instrument/symbol context;
- includes only events inside the persisted coverage interval;
- excludes event/source/ingest timestamps after the cutoff;
- orders deterministically by event time, source time, row index and identity;
- supports a proven zero-event interval when the persisted coverage exists.

Cross-hour coverage therefore remains replayable even though the coverage row itself is
partitioned by `coverage_end_ms`.

## Explicit non-goals

This slice does **not**:

- enable the Bybit production liquidation WebSocket;
- mutate the live SSD Market Tape;
- modify launchd or runtime supervisors;
- deploy to production;
- infer future liquidation zones;
- estimate leverage concentration;
- infer retail stops or actor intent;
- assign production trading weight;
- create any real-money authority.

Production activation remains a separate explicit human-impact gate.

REAL_CAPITAL=0.
