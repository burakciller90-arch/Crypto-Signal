# GALACTECH Product Rail — Performance & Trust Slice 6

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
Predecessor: accepted GALACTECH Archive / Proof Wall PR #928.
REAL_CAPITAL=0.

## Scope

This slice binds the customer Performance surface only to runtime evidence that is
currently persisted and exposed by accepted read-only APIs.

Available product sources:

- `GET /api/performance` for immutable outcome-evaluation cohorts;
- `GET /api/paper/epoch2-state` for canonical R21 Epoch 2 capital truth.

The accepted R24 calculation engine remains a stronger analytical contract, but current
product runtime does not persist/expose every R24 input as one customer-readable artifact.
The UI therefore does not fabricate Brier, reliability, Event Block effectiveness,
Sharpe/Sortino or forecast-version comparison.

## Outcome cohorts

The UI preserves evidence-class separation:

- RETROSPECTIVE;
- WALK-FORWARD;
- LIVE UNTOUCHED-FORWARD.

Each horizon/segment shows exact available counts:

- total;
- winners;
- stop losses;
- ambiguity;
- timeout;
- invalidation;
- R-evaluable observations.

Historical decisive success fraction is labelled:

**descriptive frequency · not probability**

and is never presented as calibrated win probability.

Empty evidence remains NOT MEASURED, not 0%.

## Canonical paper track record

The customer surface uses the same canonical R21 Epoch 2 state as Capital Center:

- NAV;
- realized/unrealized PnL;
- current drawdown;
- closed trades and outcome counts;
- expectancy or NOT YET MEASURED;
- turnover;
- fee + spread + slippage;
- Core / Tactical / Opportunity Reserve NAV/drawdown comparison.

Forecast hit-rate is never substituted for paper-fund performance.

## Intentionally unavailable metrics

### Calibration / Brier / reliability

R24 supports these diagnostics from exact calibrated live untouched-forward forecasts,
but the current product runtime has no persisted R20/R19 calibration-stream adapter.

Therefore customer UI says **NOT EXPOSED**.

No probability is inferred from:
- confluence;
- historical success fraction;
- archive outcomes.

### Sharpe / Sortino

Remain **NOT YET MEASURED** without accepted fixed-period return-series,
annualization and risk-free policy.

### Event Block effectiveness

Remains **NOT YET MEASURED** without accepted counterfactual outcome evidence.

### Forecast version comparison

R24 can compare exact version cohorts when full inputs are provided. Current
`/api/performance` setup/methodology segments are not silently relabelled as version
comparison. Customer UI says **NOT EXPOSED**.

## Authority

Read-only projection only:
- no private reasoning;
- no ledger mutation;
- no order submission;
- no credentials;
- no production authority;
- REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
