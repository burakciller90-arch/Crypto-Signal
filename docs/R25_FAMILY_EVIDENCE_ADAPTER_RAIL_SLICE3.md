# R25 — Family Evidence Adapter Rail / Slice 3

Status: development candidate
Parent: R25 Unified Decision Runtime Core
Safety invariant: REAL_CAPITAL=0

## Purpose

This slice binds accepted M2-M5 immutable evidence freezes into the exact five-family M6
decision contract and the same R20.5 Decision Proof domains.

The adapter layer is deliberately not a new alpha engine. It may transport a direction only
when an upstream accepted engine already produced a directional state. Context-only evidence
must remain context-only.

## Direction semantics

- Geometry: carries the already-frozen SignalDecision direction and decision bundle.
- Liquidity: ABSTAIN/context-only. A liquidity pool, sweep candidate or observed liquidation
  is not automatically bullish or bearish.
- Order Flow: direction can come from resolved book + taker alignment
  (BUY_PRESSURE / SELL_PRESSURE). Window-local CVD is proof/context and can expose conflict,
  but does not independently invent the family direction.
- Derivatives: ABSTAIN/context-only. Long crowding, short crowding, deleveraging and squeeze
  context are not direct trade instructions.
- On-chain / Smart Money: ABSTAIN/context-only. Exchange flows, wallet cohorts and large
  transfers do not become price-direction votes.

## Exact proof binding

Adapter family source identities must be covered by the Decision Proof fragments they emit.
The proof composer merges duplicate domains instead of manufacturing parallel truths.

Examples:
- ORDER_BOOK may contain exact M2 liquidity-structure and M3 microstructure freezes.
- LIQUIDITY_MAP may combine exact liquidity-structure and sweep freezes.
- DERIVATIVES binds the crowding freeze and its exact derivatives/liquidation parents.
- ONCHAIN binds exact exchange-flow, wallet-cohort and large-transfer freezes.

Event Risk and optional R19 calibrated probability have dedicated proof fragments and are
merged into the same one-slice-per-domain R20.5 contract.

## Scientific constraints

The adapter layer must not:
- infer "OI up = bullish";
- infer "exchange inflow = bearish";
- infer "whale transfer = buy/sell";
- call an observed liquidation map a future liquidation-risk map;
- call a sweep candidate a stop hunt or manipulation;
- expose an unrelated proof object merely because it belongs to the same named family.

## Authority boundary

No orders, exchange credentials, leverage, broker authority, paper-fund mutation, production
cutover or real capital are enabled by this slice.

REAL_CAPITAL=0 remains mandatory.
