# M2 Integrated Main Acceptance — v1

Status: development integration gate  
Parent roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
Safety: `REAL_CAPITAL=0`

## Purpose

Consolidate the already accepted M1 Market Tape foundations and M2 Liquidity /
Liquidation slices onto the current `main` product line without carrying stale Product
UI history or production-deploy workflows from the stacked research branches.

## Included accepted lineage

### M1 dependencies

- append-only Market Tape foundation;
- Bybit public microstructure WebSocket stream;
- raw wire journal;
- normalized Market Tape store and collection helpers.

### M2 accepted slices

- Slice 1 — temporal liquidity dynamics;
- Slice 2 — persistent liquidity structure;
- Slice 3 — bounded liquidity sweep evidence;
- Slice 4 — observed liquidation heatmap;
- Slice 5 — liquidation Market Tape persistence;
- Slice 6A — disabled-by-default liquidation collector/readiness;
- Slice 6B — liquidation Hot SQLite -> Cold Parquet/Zstd archive and replay.

## Explicit exclusions

This integration must not import stale historical Product branch changes.

Excluded from the integration commit:

- Product HTML/CSS/JS/web changes from old stacked branches;
- old world-class roadmap copies that conflict with the locked roadmap;
- production deploy workflows;
- live collector enablement;
- production SSD mutation;
- supervisor ownership changes;
- exchange order or real-money authority.

## Scientific invariants

- point-in-time evidence only;
- late/future evidence cannot rewrite historical freezes;
- confluence != probability;
- observed liquidation history != future liquidation risk;
- spoofing / hidden-liquidity / sweep remain bounded candidate semantics;
- actor intent is never inferred from order-book/trade/liquidation evidence;
- missing/stale/degraded evidence fails closed;
- REAL_CAPITAL=0.

## Integrated acceptance

The branch is acceptable only if all of the following pass on the exact integration head:

1. focused Market Tape / microstructure / liquidity / liquidation pytest;
2. focused Ruff;
3. focused mypy;
4. full repository pytest;
5. full repository Ruff;
6. full repository mypy;
7. Product JavaScript syntax + freshness contract;
8. real PyArrow 22.x cold-archive tests.

Hosted PASS is development acceptance only. It does not activate the production
liquidation collector and does not deploy the integrated source to UID504 runtime.

## After PASS

- merge the clean integration PR into current `main`;
- close M2 development integration as accepted;
- advance the primary intelligence frontier to M3 Order Flow / Absorption 2.0;
- keep any production collector activation as a separate explicit human-impact gate.
