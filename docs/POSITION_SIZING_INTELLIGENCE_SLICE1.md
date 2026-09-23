# Position Sizing Intelligence — Slice 1: Shadow Comparison

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Implement the locked Phase 11 sizing research contract without creating canonical order
size, ledger mutation, or automatic method promotion.

This slice compares:

- fixed fractional;
- full Kelly;
- 1/2 Kelly;
- 1/4 Kelly.

All outputs are shadow research.

## Explicit policy

Sizing thresholds are versioned research policy, not universal market laws.

The policy explicitly freezes:

- fixed vault fraction;
- maximum fraction of one vault;
- maximum absolute correlation;
- maximum current drawdown;
- maximum volatility;
- minimum liquidity score;
- maximum transaction cost in R;
- martingale forbidden;
- automatic method selection disabled;
- canonical notional authority disabled.

## Risk context

Each sizing context freezes exact evidence for:

- vault identity;
- asset/as-of;
- Smart Capital Allocator candidate lineage;
- expected win magnitude in R;
- expected loss magnitude in R;
- explicit transaction cost in R;
- absolute correlation;
- current drawdown;
- volatility;
- liquidity;
- exact source evidence identities.

A breached risk gate blocks every sizing method.

## R19 / Kelly boundary

Kelly methods are disabled unless the input is an exact
`CalibratedProbabilityEvidence` authorized by R19.

Without R19 calibration:

- fixed fractional may exist only as a shadow baseline;
- full/half/quarter Kelly are `DISABLED_NO_CALIBRATED_PROBABILITY`;
- no percentage is inferred from confluence or hit rate.

With R19 calibration:

- the exact frozen probability is consumed;
- transaction costs are incorporated in the win/loss payoff;
- expected edge is explicit;
- raw binary Kelly fraction is computed;
- full/half/quarter variants are compared;
- configured maximum vault fraction caps research fractions.

If calibrated expected edge is non-positive, **all methods** hold rather than displaying a
positive size.

## Formula boundary

For calibrated probability `p`:

- net win R = expected win R - transaction cost R;
- net loss R = expected loss R + transaction cost R;
- expected edge = `p * net_win - (1-p) * net_loss`;
- payoff ratio = `net_win / net_loss`;
- raw Kelly = `p - (1-p) / payoff_ratio`, floored at zero.

This is a research calculation, not proof that Kelly is optimal for the real market.

## No canonical selection

Every result remains:

`shadow_sizing_comparison_not_canonical_notional`

The assessment exposes all methods but always keeps:

- selected method = null;
- selected fraction = null;
- canonical notional = null;
- automatic method selection = false;
- production authority = false;
- REAL_CAPITAL=0.

Hypothetical notional is calculated only against the immutable Epoch 2 starting vault
budget to make methods comparable. It is not current cash and not an order amount.

## Relationship to legacy paper sizing

Existing `paper/sizing.py` remains the historical Epoch 1 deterministic mechanism. This
slice does not silently repoint it to Epoch 2 and does not mutate any paper ledger.

A later canonical sizing promotion requires explicit evidence and the separate activation
path.

## Acceptance checklist

1. Fixed fractional is available as shadow baseline without R19 probability.
2. Kelly full/half/quarter remain disabled without R19 CALIBRATED evidence.
3. Exact R19 probability enables deterministic Kelly comparison.
4. Correlation/drawdown/volatility/liquidity/cost gates fail closed.
5. Allocator HOLD_CASH prevents sizing.
6. Non-positive calibrated edge prevents every method from showing positive size.
7. Future probability evidence is rejected.
8. Martingale cannot be enabled.
9. No winner or canonical notional is selected.
10. No ledger/network/exchange/runtime-control surface.
11. REAL_CAPITAL=0.
12. Focused pytest/Ruff/mypy plus full repository Python/JS/freshness regression.
13. Temporary hosted workflow removed after PASS.

After acceptance, Phase 11 infrastructure is satisfied. The next locked frontier is
Phase 12 market-neutral/arbitrage research, shadow-only.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
