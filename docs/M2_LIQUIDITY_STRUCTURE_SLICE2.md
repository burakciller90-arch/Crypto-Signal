# M2 Liquidity Intelligence 2.0 — Slice 2: Persistent Structure

Status: development slice on top of accepted M2 Liquidity Dynamics Slice 1  
REAL_CAPITAL: 0  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Purpose

Add point-in-time, deterministic order-book structure evidence without changing the
accepted Slice 1 temporal dynamics engine.

This slice measures:

- persistent bid/ask liquidity levels;
- per-level presence fraction and survival time;
- gross added/removed notional;
- appearance and cancellation notional/velocity;
- depletion and replenishment;
- repeated refresh cycles;
- distance of a level to contemporaneous mid-price;
- materiality relative to the same-side level population.

## Candidate semantics

The engine may emit three bounded level candidates:

- `persistent_liquidity_pool_candidate`;
- `spoofing_candidate`;
- `hidden_liquidity_candidate`.

These names are **research evidence labels**, not causal attribution.

A spoofing candidate requires a material level to appear near price and rapidly withdraw.
Order-book data alone cannot prove actor intent, manipulation, or whether every removed
order would have executed.

A hidden-liquidity candidate requires repeated depletion/replenishment at one material
price level. It explicitly requires later trade-flow confirmation before stronger
interpretation.

## PIT / leakage boundary

A snapshot is eligible only when all of its event/source/response/ingestion timestamps
are <= `as_of_ms`. Future or late-ingested snapshots cannot rewrite a historical freeze.

The engine fails closed when:

- the latest snapshot is stale;
- too few snapshots exist;
- configured depth is unavailable;
- a temporal gap exceeds the configured bound;
- there is no positive temporal span;
- duplicate identities or mixed market contexts are supplied.

## Separation from M3

This slice is order-book-only. It does **not** claim execution, absorption, aggressive
flow or true iceberg execution. M3 Order Flow/Absorption will combine trades/CVD with
these frozen structure objects.

## Acceptance

- deterministic output independent of input ordering;
- immutable evidence/freeze identities;
- persistent-pool detection;
- bounded rapid-withdrawal/spoofing candidate;
- bounded repeated-refresh/hidden-liquidity candidate;
- explicit uncertainty;
- future/late evidence exclusion;
- degraded-input fail-closed behavior;
- no real-money/order authority.
