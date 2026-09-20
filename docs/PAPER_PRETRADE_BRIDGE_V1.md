# PAPER PRE-TRADE BRIDGE V1

Status: candidate Stage 6C pure pre-trade bridge. It does not activate PAPER/STABLE trading.

Policy version: `paper_pretrade_bridge_policy.v1`.

## Frozen venue/cost input boundary

Crypto Signal currently has canonical candle truth but no canonical persisted Binance symbol-rule metadata source. V1 therefore **does not invent or fetch venue rules**.

The bridge requires an already-created `FrozenExecutionSnapshot` and fails closed unless:
- symbol matches the sizing decision;
- execution policy version matches the persistent paper fund;
- snapshot `venue_reference` exactly equals the accepted frozen execution-input `venue_reference`.

A later runtime/source gate must supply and persist authoritative venue rule snapshots before PAPER/STABLE activation.

## Quantity normalization

- BUY raw sizing quantity is rounded **down only** to frozen `quantity_step`;
- rounded quantity may never exceed the sizing ceiling;
- frozen minimum quantity and minimum notional are enforced before planning;
- EXIT must close the exact full long quantity; if the current holding is not an exact frozen venue step, V1 rejects rather than silently leaving dust.

## Explicit execution-cost budget

The bridge derives fee/spread/slippage budget with the same deterministic adverse-price convention used by the paper execution simulator:
- BUY fill reference moves adversely upward by spread + slippage;
- EXIT fill reference moves adversely downward by spread + slippage;
- fee is computed on simulated fill notional;
- spread and slippage are computed on reference notional.

The resulting exact total is passed to `paper_risk_policy.v1` as `cost_budget_usdt`.

## Independent planner gate

The existing paper planner remains independently authoritative for:
- available cash;
- minimum 20 USDT cash reserve;
- 25% single-position concentration;
- 50% maximum gross exposure;
- no leverage, borrowing, shorting, derivatives or martingale.

Planner rejection is a normal fail-closed pre-trade result, not a trade.

## Authority boundary

This module does not:
- fetch venue metadata;
- simulate or create a fill;
- mutate the paper ledger;
- create an exchange/network/credential/order path.

Next gate after acceptance is orchestration + atomic bundle integration, followed by persistent activation/watermark/processed-event state and authoritative venue-rule snapshot sourcing.

REAL_CAPITAL remains 0.
