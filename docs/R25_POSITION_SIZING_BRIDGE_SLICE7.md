# R25 Slice 7 — Explicit Risk-Bound Position Sizing Bridge

Status: development candidate. REAL_CAPITAL=0.

This slice connects the accepted Unified Decision + Capital Science lineage to the existing Position Sizing Intelligence without inventing risk numbers and without selecting a winner.

## Scientific boundary

The following values are **not derivable from a forecast merely because the forecast exists**:
- expected win R;
- expected loss R;
- transaction cost R;
- portfolio correlation;
- current drawdown;
- volatility;
- liquidity score.

They must therefore arrive as an explicit `AcceptedSizingRiskInputs` object with exact SHA256 source evidence.

For each Epoch 2 vault:
- allocator HOLD_CASH -> `HOLD_ALLOCATOR`, no fabricated sizing context;
- allocator eligible but no risk inputs -> `MISSING_RISK_INPUTS`;
- allocator eligible + exact risk inputs -> Position Sizing Intelligence runs in shadow mode.

Supplying risk inputs for a vault that the allocator has already placed in HOLD_CASH fails closed.

## Probability / Kelly boundary

Without exact R19 calibrated probability:
- fixed-fractional may exist as the accepted shadow baseline;
- full / half / quarter Kelly remain disabled.

When calibrated probability is supplied, its exact authorization and numeric probability must match the already-frozen R20 forecast. A different probability artefact is rejected.

Even when all sizing methods are available:
- no method is selected;
- no canonical notional is produced;
- no paper trade is authorized.

## PIT boundary

A risk snapshot used for sizing must be measured no earlier than the immutable forecast issuance and no later than the sizing timestamp. Its source identities, risk identity, Decision Proof identity and Capital Science bridge identity are carried into the sizing context.

## Authority

No paper action, fill, accounting mutation, exchange order, credential, leverage, deployment, wake/lease change or real capital is created here.

Next frontier after acceptance: an R22 **intent preview / reviewed-selection adapter** that can consume one explicitly reviewed AVAILABLE_SHADOW sizing result. It must still remain non-mutating until a separate canonical-paper writer activation gate.