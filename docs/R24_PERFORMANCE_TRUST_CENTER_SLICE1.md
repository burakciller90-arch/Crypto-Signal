# R24 Performance & Trust Center — Phase 19 Slice 1

Parent: \`docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md\`, Phase 19.
REAL_CAPITAL=0.

R24 is a read-only evidence projection. It never turns missing samples into performance,
never mixes evidence classes into an unlabeled accuracy number, and never hides losers.

## Forecast truth

Forecast outcomes are reported separately for:

- retrospective;
- walk-forward;
- live untouched-forward.

Each cohort shows HIT_TARGET, INVALIDATED, EXPIRED, AMBIGUOUS, NOT_EVALUABLE and
CANCELLED counts. The only accuracy fraction is explicitly:

\`HIT_TARGET / (HIT_TARGET + INVALIDATED)\`

and is labelled as that decisive denominator. It is not an all-outcome success rate.

Winners and losers are always visible together.

## Calibration / Brier / reliability

R24 computes descriptive calibration diagnostics only from forecasts that satisfy all of:

- exact immutable R20 forecast;
- exact final R20 resolution;
- \`LIVE_UNTOUCHED_FORWARD\` evidence class;
- decisive HIT_TARGET or INVALIDATED outcome;
- exact calibrated probability already present in the forecast.

Uncalibrated forecasts are not assigned a probability.

The Brier score is the mean squared error of those accepted probability/outcome pairs.
Reliability groups observations by the exact frozen probability value rather than
inventing a new calibration-bin policy. These diagnostics are descriptive trust metrics,
not a new R19 probability authorization gate.

## Decision behavior

From immutable SignalDecision population R24 exposes separately:

- abstain rate: NO_SIGNAL + NEUTRAL;
- conflict rate: opposing methodology / CONTRADICT evidence;
- ambiguity rate: INTERNAL_AMBIGUITY evidence.

The three rates are not forced to sum to 1 because the categories answer different
questions and may overlap.

## Event Block

R24 exposes Event Block frequency from exact CircuitBreakerAnalysis evidence.
It deliberately reports counterfactual Event Block **effectiveness** as
\`NOT_YET_MEASURED\` because current accepted evidence does not prove what would have
happened had a blocked trade been taken. No avoided-loss claim is fabricated.

## Canonical Epoch 2 paper capital

R24 projects:

- consolidated NAV;
- realized/unrealized PnL;
- maximum observed drawdown across supplied immutable R21 consolidated history;
- fees, spread, slippage and turnover;
- closed-trade outcome counts;
- expectancy;
- per-vault performance for Core / Tactical / Opportunity Reserve;
- profit factor when complete R22 closed-fill history makes it defined.

The complete R22 fill history must reconcile to R21 closed-trade count and realized PnL.
If no closed trades exist, profit factor is \`NOT_YET_MEASURED\`. If gross loss is zero,
profit factor is \`UNDEFINED\` rather than infinity.

## Risk-adjusted metrics

Sharpe/Sortino remain \`NOT_YET_MEASURED\` until an accepted fixed-period return-series
and annualization/risk-free policy exists. Event-driven NAV snapshots are not silently
treated as equally spaced returns.

## Version comparison

Resolved forecasts are grouped by exact forecast version references and evidence class.
Backtest/walk-forward/untouched-forward results remain labelled and separate.

## Authority

R24:
- exposes no private chain-of-thought;
- writes no ledger;
- submits no orders;
- handles no exchange credentials;
- grants no production authority;
- keeps REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
