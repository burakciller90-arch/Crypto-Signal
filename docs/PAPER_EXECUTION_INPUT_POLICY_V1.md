# PAPER EXECUTION INPUT POLICY V1

Status: candidate Stage 6C execution-input truth. It does not activate PAPER/STABLE trading.

Policy version: `paper_execution_input_policy.v1`.

V1 reference rule:
- Binance spot only;
- canonical 15m base-candle cache;
- cache access is SQLite `mode=ro` plus `PRAGMA query_only=ON`;
- select the first fully closed, already-ingested candle whose `open_time_ms` is strictly greater than the autonomy signal `as_of_ms`;
- use that candle's OPEN as the reference price.

Strict greater-than prevents reaching backward into a candle that began at or before the signal decision. If the next eligible candle is not yet closed/observed, the policy returns `WAITING_FOR_NEXT_CLOSED_CANDLE` rather than inventing a price.

Bybit remains required for autonomy consensus; Binance alone is the deterministic V1 simulated execution reference venue. This is a paper-simulation convention, not a claim about best real execution.

The frozen input identity binds action, symbol, both source freeze identities, signal as-of, source exchange/market/timeframe, candle open/close/ingest timestamps, adapter version, OPEN price and policy version.

This object is not a fill, does not choose quantity, does not mutate the cache or paper ledger and performs no exchange/network action. Next gate is conservative position sizing from autonomy risk budget + frozen reference + signal invalidation geometry, followed by the existing planner and simulated-cost policy.

REAL_CAPITAL remains 0.
