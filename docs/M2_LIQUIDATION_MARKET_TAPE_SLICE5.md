# M2 Liquidity Intelligence 2.0 — Slice 5
## Liquidation Market Tape persistence and PIT replay

Status: development / stacked on accepted Slice 4 (#789)

Safety:
- REAL_CAPITAL=0
- no broker/order authority
- no live collector activation
- no production deployment
- no cold-archive claim in this slice

## Purpose

Slice 4 introduced point-in-time observed liquidation evidence and a bounded
Liquidation Heatmap. Slice 5 makes that evidence persistable and replayable without
changing the meaning of the research layer.

The core truth requirement is:

> "No observed liquidation" is only a measurable state when the feed coverage for the
> exact analysis window was itself observed and persisted.

Therefore liquidation events and feed coverage are separate immutable evidence classes.

## Market Tape schema

Normalized Market Tape advances additively from:

- `market-tape-schema-v1/1`

to:

- `market-tape-schema-v1/2`

The v1/1 -> v1/2 migration is additive:
- existing normalized history is preserved;
- new liquidation tables are created;
- unknown schema versions fail closed;
- no destructive rewrite or backfill is performed.

New tables:

### `market_tape_liquidations`

Stores immutable normalized `LiquidationObservation` rows.

Each row preserves:
- liquidation identity;
- provider-event identity;
- exchange;
- instrument type;
- symbol;
- liquidated position side;
- bankruptcy size/price through canonical payload;
- event/source/ingest timestamps;
- source row index;
- source;
- adapter version;
- canonical payload.

Provider-event dedupe is based on:

- exchange;
- instrument type;
- symbol;
- event timestamp;
- provider source timestamp;
- provider row index.

This intentionally excludes `ingested_at_ms` and parser version. Re-ingesting the same
provider event cannot create a second market event merely because local ingest time or
adapter version changed.

If the same provider-event identity maps to different market truth, persistence fails
closed with a conflict instead of silently choosing one interpretation.

### `market_tape_liquidation_coverage`

Stores immutable `LiquidationFeedCoverage` evidence separately from event rows.

Coverage proves that an interval was actually observed. It does not estimate future
liquidation zones, leverage concentration, retail stops or actor intent.

Re-appending the exact same coverage object is idempotent. A later observation of the
same interval carries a different coverage identity because `observed_at_ms` is part of
the immutable evidence identity; it is appended as new evidence and never rewrites the
earlier observation.

## Coverage-last batch boundary

`persist_liquidation_batch(...)` validates the full batch before publishing coverage.

For every event:
- exchange/instrument/symbol must match coverage;
- event time must be inside the coverage interval;
- event/source/ingest timestamps must be observable by the coverage observation time.

Events are appended first. Coverage is appended last.

This creates a fail-closed property:

- if validation fails, no coverage is published;
- if event persistence conflicts part-way through, coverage is still not published;
- therefore replay cannot mistake a partial batch for a completely observed interval;
- retry remains safe because event writes are append-only/idempotent.

An empty event batch may publish coverage. That is the correct representation of an
observed interval with zero liquidation events.

## PIT replay

Replay is keyed by an exact persisted `coverage_identity` and an explicit
`as_of_ms`.

Replay:
- requires the coverage row to exist;
- rejects coverage that had not yet been observed at the requested cutoff;
- reads only the same exchange/instrument/symbol context;
- reads only events inside the persisted coverage interval;
- excludes any event whose event/source/ingest timestamp is after `as_of_ms`;
- orders evidence deterministically.

Slice 5 does not merge overlapping coverage intervals and does not infer complete
coverage from partial intervals. A later slice may add interval composition only with a
separate proof/acceptance contract.

## Explicit non-goals

This slice does **not**:
- activate Bybit `allLiquidation` WebSocket collection;
- mutate the live SSD Market Tape runtime;
- add liquidation files to Hot/Cold Parquet archives;
- claim future liquidation-risk zones;
- infer leverage concentration;
- infer stop locations;
- infer market-maker/institutional intent;
- assign production weight;
- emit calibrated probability;
- place or simulate real exchange orders.

Cold archive integration belongs to the later Hot/Cold integration slice after this
normalized persistence contract is accepted.

REAL_CAPITAL=0.
