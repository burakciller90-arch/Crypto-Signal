# Phase 12 — Market-neutral / Arbitrage Research Slice 1

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Implement the locked Phase 12 market-neutral/arbitrage research contract as a **shadow-only
feasibility layer**.

Supported research families:

- cross-exchange spread;
- spot-perpetual basis;
- funding capture;
- delta-neutral.

This slice does not place orders, move capital, mutate a paper ledger or claim that any
opportunity is risk-free.

## Existing evidence reused

Accepted derivatives engines already expose PIT-safe funding, basis and open-interest
context. Phase 12 does not duplicate those engines.

The market-neutral layer consumes immutable source identities and adds the execution/risk
terms needed to decide whether an apparent spread remains interesting after realistic
frictions.

## Executable leg evidence

Each long/short leg freezes:

- exchange;
- spot or linear-perpetual instrument type;
- symbol;
- market-available timestamp;
- observed timestamp;
- executable bid/ask;
- round-trip fee estimate in bps;
- round-trip slippage estimate in bps;
- exact source evidence identity.

A long leg enters at **ask**. A short leg enters at **bid**. The gross price edge is derived
from these executable sides, not from midpoint fantasy fills.

## Explicit risk context

The separate risk context freezes:

- execution latency;
- latency penalty;
- expected funding benefit;
- adverse funding-change stress;
- transfer-required flag;
- transfer cost;
- transfer delay;
- long-leg counterparty/exchange risk score;
- short-leg counterparty/exchange risk score;
- hedge mismatch fraction;
- exact source evidence identities.

Counterparty, transfer and hedge risks remain visible gates; they are not hidden inside one
profit number.

## Net-edge decomposition

For an evaluable candidate:

`net edge = gross executable price edge + expected funding benefit - fees - slippage - latency penalty - funding-change stress - transfer cost`

The result exposes every component separately.

A positive gross spread can therefore become `HOLD_NO_NET_EDGE` after costs.

## Family structure

### Cross-exchange spread

Requires distinct exchanges.

### Spot-perpetual basis

Requires exactly one spot leg and one linear-perpetual leg.

### Funding capture

Requires exactly one spot leg and one linear-perpetual leg. Expected funding is evidence,
not guaranteed future income; funding-change stress is deducted and separately gated.

### Delta-neutral

Requires at least one perpetual hedge leg. Hedge mismatch remains an explicit risk input.

## Fail-closed states

- `NOT_EVALUABLE`
  - stale leg;
  - excessive market-time skew;
  - transfer required but delay evidence unavailable.
- `HOLD_RISK_GATE`
  - excessive execution latency;
  - transfer delay above policy;
  - counterparty/exchange risk above policy;
  - hedge mismatch above policy;
  - funding-change stress above policy.
- `HOLD_NO_NET_EDGE`
  - fully evaluated net edge below the caller-supplied versioned research minimum.
- `ELIGIBLE_SHADOW`
  - synchronized/evaluable evidence;
  - risk gates pass;
  - net edge remains above the versioned minimum after all explicit costs/stresses.

Policy thresholds are research inputs, not universal market truths.

## Scientific and authority boundaries

- Never call an opportunity risk-free or guaranteed.
- Net edge is a research estimate, not guaranteed realized PnL.
- Funding may change before settlement.
- Cross-exchange opportunities carry execution/latency/transfer/counterparty risk.
- Delta-neutral does not mean zero residual risk.
- No position sizing in Slice 1.
- No canonical capital mutation.
- No automatic promotion.
- No paper ledger write.
- No network/exchange/order path.
- REAL_CAPITAL=0.

## Acceptance checklist

1. Four locked Phase 12 families are represented.
2. Cross-exchange family requires distinct venues.
3. Spot/perpetual families require one spot + one perpetual leg.
4. Long ask / short bid drive gross price edge.
5. Fees, slippage, latency, funding stress and transfer cost are explicit.
6. Apparent positive gross edge can fail after costs.
7. Stale or unsynchronized legs fail closed.
8. Missing transfer-delay evidence is NOT_EVALUABLE.
9. Excessive transfer delay remains a separate risk veto.
10. Counterparty/exchange risk remains a separate veto.
11. Hedge mismatch remains a separate veto.
12. Funding-change stress remains a separate veto.
13. Policy thresholds are versioned caller inputs.
14. Immutable identity tampering fails closed.
15. No sizing, canonical mutation, promotion, ledger/order/network authority.
16. REAL_CAPITAL=0.
17. Existing Alpha Factory research gate PASS.
18. Focused Phase 12 + full repository pytest/Ruff/mypy/JS/freshness PASS.
19. Temporary hosted workflow removed after PASS.

After acceptance, Phase 12 infrastructure is satisfied. The next locked frontier is
**Phase 13 — R20 Immutable Forecast Stream**.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
