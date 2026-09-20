# PAPER BINANCE SPOT VENUE RULE SNAPSHOT V1

Status: candidate Stage 6C authoritative venue-rule source/cache. It does not activate PAPER/STABLE trading.

## Authoritative public source

V1 reads Binance Spot public `GET https://api.binance.com/api/v3/exchangeInfo?symbol=...`.

The parser fails closed unless:
- the exact requested BTCUSDT/ETHUSDT/SOLUSDT symbol is present once;
- status is `TRADING`;
- `isSpotTradingAllowed=true`;
- quote asset is USDT;
- MARKET is listed as a supported order type;
- exactly one LOT_SIZE and PRICE_FILTER are present;
- at least one MIN_NOTIONAL or NOTIONAL filter is present.

V1 freezes:
- LOT_SIZE minQty/maxQty/stepSize;
- PRICE_FILTER tickSize;
- the stricter minimum when both MIN_NOTIONAL and NOTIONAL are present;
- canonical source-symbol JSON and its SHA256;
- observation timestamp.

V1 uses LOT_SIZE rather than MARKET_LOT_SIZE because the current paper execution simulator does not model a real exchange order type. maxQty and tickSize are captured for audit/integration hardening even though the legacy FrozenExecutionSnapshot currently consumes quantity-step/minQty/minNotional only.

## Simulation cost policy

`paper_simulated_cost_policy.v1` freezes explicit conservative simulation assumptions:
- fee rate: 0.001;
- spread rate: 0.0005;
- slippage rate: 0.0005.

These values are simulation assumptions, not a claim about any user's actual Binance fee tier. No account endpoint, API key or credential is used.

## Immutable cache

`PaperVenueRuleStore` is append-only SQLite and may share the same file as the paper fund ledger. Every snapshot identity binds source payload hash, observation time, parsed rule values and simulated-cost policy. UPDATE/DELETE are rejected.

For deterministic replay, an execution input selects the latest stored rule snapshot whose observed_at is not after the execution-input observed_at. Future rule observations cannot be backdated into an earlier event.

## Execution snapshot binding

The authoritative execution venue reference contains:
- exact venue-rule snapshot identity;
- exact simulated-cost policy version;
- the full frozen execution-input venue reference ending in its input identity.

The resulting FrozenExecutionSnapshot therefore cryptographically binds the venue rules, cost rates and execution-input lineage without creating real exchange authority.

Remaining before stable activation:
- enforce captured maxQty in the authoritative pretrade bridge;
- add a stable one-shot rule refresh/cache operation and verify real public responses for BTCUSDT/ETHUSDT/SOLUSDT;
- only after that evaluate PAPER/STABLE virtual-trading activation.

REAL_CAPITAL remains 0.
