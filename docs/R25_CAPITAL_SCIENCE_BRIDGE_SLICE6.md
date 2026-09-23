# R25 Slice 6 — Unified Decision → Capital Science Bridge

Status: development candidate. REAL_CAPITAL=0.

## Integration bug closed

The accepted intelligence stack intentionally scopes:
- M6 / forecasts / paper markets as market symbols such as `BTCUSDT`;
- Event Risk as affected base assets such as `BTC`.

The original Smart Capital Allocator unit tests used `BTCUSDT` for both, so isolated tests passed while the merged Unified Decision Runtime could not be passed directly into the allocator.

Slice 6 makes this boundary explicit. Smart Capital accepts either:
- exact same event/market asset; or
- the locked USDT market form `{event_asset}USDT`.

This is exact equality, **not** a fuzzy prefix match and it does not rewrite the Event Risk artefact or identity.

## Bridge contract

`assess_unified_decision_capital` requires:
- exact R20 forecast ↔ M6 identity;
- exact R20.5 proof ↔ forecast/M6 identity;
- exact Event Risk identity already frozen into the forecast;
- exact Event Risk evidence present in the Decision Proof;
- exact base-asset and PIT cutoff;
- optional Tactical/Opportunity evidence only when explicitly supplied with the same market/PIT context.

It then reuses the accepted Smart Capital Allocator to produce the canonical Epoch 2 research envelopes:
- Core 600 USDT;
- Tactical 300 USDT;
- Opportunity Reserve 100 USDT.

No tactical evidence is synthesized from a 4h decision. No recovery evidence is synthesized. Missing evidence therefore keeps the corresponding vault in HOLD_CASH.

## Authority

The bridge selects:
- no sizing method;
- no notional;
- no paper action;
- no simulated fill;
- no canonical ledger mutation;
- no exchange order.

Allocator `automatic_sizing_authority` and `automatic_trade_authority` remain false. REAL_CAPITAL remains 0.

Next frontier after acceptance: bind exact risk-context inputs to Position Sizing Intelligence, then materialize a non-mutating R22 intent preview before any canonical Epoch 2 writer activation.