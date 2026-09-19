# ADR 0003 — Live Bybit Kline Ingestion

Status: Accepted for Phase 1 Slice 3
Date: 2026-09-19

## Live source
Use Bybit V5 public Spot WebSocket kline topics behind the same provider-neutral Candle contract.

## Connection policy
- Subscribe to `kline.{interval}.{symbol}`.
- Treat subscription acknowledgements and heartbeat responses as control messages, not market data.
- Send Bybit application heartbeat `{"op":"ping"}` every 20 seconds.
- Keep protocol-level WebSocket ping/pong enabled.
- Use the modern websockets asyncio client reconnect iterator for transient failures.
- Re-subscribe after every reconnect.

## Truth policy
- Preserve Bybit `confirm` as the closed/finalized state.
- Preserve exchange system timestamp separately from local ingest timestamp.
- Validate kline start/end bounds against the canonical timeframe duration.
- Reject unexpected topics/intervals rather than silently reinterpret them.

## Persistence bridge
A generic CandleIngestor applies the canonical store finalization policy to live stream events.
Open updates may evolve; a finalized candle cannot be silently rewritten or reopened.

REAL_CAPITAL remains 0.
