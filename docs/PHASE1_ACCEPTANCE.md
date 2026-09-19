# PHASE 1 — DATA TRUTH ACCEPTANCE

Phase 1 is accepted only when:

- Provider-neutral Candle contract exists and rejects impossible OHLC/time data.
- 15m is the canonical base candle interval.
- Bybit REST backfill normalizes real public market data.
- Live Bybit WebSocket closed-candle ingestion works with reconnect handling.
- Persistence preserves candle identity, provenance and closed/open state safely.
- Duplicate delivery is idempotent.
- Missing intervals and stale feeds are detectable and explicit.
- 1h, 4h, 1D and 1W candles are deterministically aggregated from closed 15m candles.
- Daily/Weekly/Monthly/Yearly Opens are deterministic and PIT-safe.
- Binance adapter reaches semantic parity with the same Candle contract.
- Native-source reconciliation can detect material mismatches.
- Restart/recovery does not create silent data holes.
- Unit tests and live integration probes pass.
- No V2+ market microstructure or execution scope is introduced.

REAL_CAPITAL remains 0.
