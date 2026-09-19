# ADR 0001 — V1 Data Truth Source

Status: Accepted for Phase 1 initial implementation
Date: 2026-09-19

## Decision
Use a provider-neutral market-data contract.
Implement Bybit V5 Spot as the first canonical adapter.
Add Binance Spot as the second adapter after the shared contract/store/live path is proven.

## Why Bybit first
- Public REST and WebSocket endpoints are reachable from the isolated runtime.
- V5 exposes spot and derivatives behind one consistent API family.
- WebSocket kline payloads explicitly expose a `confirm` closed-candle flag.
- V1 can start without API credentials or execution capability.

## Canonical base timeframe
Use 15m closed candles as the initial canonical base series.
Construct 1h, 4h, 1D and 1W deterministically from closed 15m candles.
Native exchange higher-timeframe candles may later be used for reconciliation, not silently substituted.

## Truth rules
- Decimal strings remain Decimal; never convert price/volume through float.
- Raw exchange timestamp is preserved.
- REST and WebSocket source/provenance are explicit.
- Open/incomplete candles never masquerade as closed evidence.
- Missing intervals are gaps, never synthesized.
- Adapter-specific payloads are normalized before downstream use.

## V1 scope
No order book, funding, OI, liquidation or execution work is part of this decision.
