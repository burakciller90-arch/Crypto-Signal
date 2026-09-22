# M2 Liquidity Intelligence 2.0 — Slice 3: Liquidity Sweep Engine

Status: development slice on top of accepted M2 Slice 2  
REAL_CAPITAL: 0  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Purpose

A touched price level is not automatically a stop hunt or sweep.

This slice emits a bounded liquidity-sweep candidate only when a persistent liquidity
pool is corroborated by multiple point-in-time evidence components:

1. persistent pool identity from accepted Liquidity Structure Slice 2;
2. material visible-depth depletion;
3. public-trade aggressor flow in the expected direction;
4. price displacement through the pool;
5. follow-through after displacement.

Recovery/reclaim is measured separately and is not required for a sweep candidate.

## Evidence inputs

- normalized order-book snapshots;
- public trades that are eligible for book-flow interpretation;
- accepted persistent-pool evidence derived from the same frozen snapshot window.

Block trades and RPI trades are excluded from book-sweep flow corroboration.

## PIT rules

A snapshot is eligible only when event/source/response/ingestion timestamps are all
<= `as_of_ms`.

A public trade is eligible only when event/source/ingestion timestamps are all
<= `as_of_ms`.

Late or future evidence cannot rewrite a historical freeze.

## Candidate semantics

Possible aggregate states:

- `bid_side_liquidity_sweep_candidate`;
- `ask_side_liquidity_sweep_candidate`;
- `both_sides_liquidity_sweep_candidate`;
- `none`;
- `unavailable`.

Every qualified candidate preserves:

- pool price;
- pool persistence/materiality;
- interaction window;
- aggressive/opposing notional;
- aggressor share;
- depth-depletion fraction;
- maximum displacement;
- follow-through count;
- recovery/reclaim state and time;
- explicit uncertainty.

A candidate is not proof of:

- a stop hunt;
- manipulation;
- a market maker;
- an institution;
- actor intent.

## Separation from M3

This slice uses public-trade aggressor direction only as corroboration for a bounded
sweep candidate. It does not yet implement the full M3 Order Flow engine, CVD,
absorption, large-print classification or breakout confirmation matrix.

## Fail-closed conditions

- too few order-book snapshots;
- too few eligible public trades;
- stale order book;
- stale public trade tape;
- excessive snapshot gap;
- unresolved structure evidence;
- duplicate identities;
- mixed market context.

## Acceptance

- deterministic output independent of input ordering;
- future/late evidence exclusion;
- candidate requires depletion + flow + displacement + follow-through;
- level touch alone is insufficient;
- weak/opposing aggressive flow is insufficient;
- block/RPI trades cannot create sweep evidence;
- immutable evidence/freeze identities;
- explicit candidate uncertainty;
- no trading authority;
- REAL_CAPITAL=0.
