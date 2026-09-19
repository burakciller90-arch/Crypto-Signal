# ADR 0002 — Candle Persistence and Finalization

Status: Accepted for Phase 1 Slice 2
Date: 2026-09-19

## Storage
Use project-local SQLite for the V1 data-truth baseline.
The database lives under the Git-ignored project `/runtime/` tree.
SQLite runs in WAL mode.

## Canonical identity
A candle key is:
exchange + market type + symbol + timeframe + open time.

## Write policy
- First observation inserts one canonical row.
- Repeated equivalent delivery is idempotent.
- An open candle may update when a newer source observation arrives.
- An older open update is ignored as stale.
- An open candle may transition to closed/finalized.
- A finalized candle cannot transition back to open.
- An equivalent finalized re-delivery is unchanged.
- A different finalized payload raises an explicit conflict; it is never silently overwritten.

## Precision and provenance
Decimal market values are stored as text, not floating-point.
Source type, source timestamp, local ingest timestamp and adapter version remain on the canonical row.

## Future boundary
If multi-process write volume or operational scale outgrows SQLite, migration is a separate bounded decision.
Do not introduce PostgreSQL merely for architectural fashion before evidence requires it.
