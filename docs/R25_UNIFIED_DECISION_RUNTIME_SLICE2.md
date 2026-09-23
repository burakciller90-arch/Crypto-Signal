# R25 — Unified Decision Runtime Core / Slice 2

Status: development candidate  
Predecessor: R25 Decision Evidence Product Bridge / PR #933  
Safety invariant: REAL_CAPITAL=0

## Purpose

Accepted v1.1 engines previously existed as individually-tested modules. Slice 2 creates the
first deterministic orchestration boundary that binds one exact point-in-time decision
window across:

1. the immutable SignalDecision;
2. exactly five M6 family evidence objects;
3. Event Risk / circuit-breaker context outside the M6 score;
4. optional exact-scope R19 calibrated probability;
5. R20 Immutable Forecast;
6. R20.5 Decision Proof;
7. R20.5 Live Intelligence Feed issuance;
8. atomic append-only persistence in the R25 decision evidence ledger.

This is the decision spine needed before any paper-capital runtime can honestly claim that
the accepted intelligence modules participate in the same decision.

## Exact evidence / UI invariant

The proof shown to a customer must be the evidence used by the decision runtime.

M6 family source identities therefore have mandatory proof coverage:

- Geometry -> Frozen Chart / Consumed Candles;
- Liquidity -> Order Book / Liquidity Map / Liquidation Map;
- Order Flow -> Order Book / Order Flow CVD;
- Derivatives -> Derivatives;
- On-chain -> On-chain.

An unrelated evidence object cannot be substituted simply because it belongs to the same
named intelligence family.

## PIT boundary

All family evidence shares the exact:

- symbol;
- timeframe;
- regime;
- as-of cutoff.

Event Risk shares the exact base asset and as-of cutoff. Available proof slices cannot have
an observed timestamp after that cutoff.

Calibrated R19 probability is optional. When present it must:

- already exist by the source as-of;
- match the exact R19 calibration scope accepted by R20;
- expose the exact authorization/calibration/source-prediction/source-forecast/walk-forward
  identities in the probability proof domain.

Otherwise the forecast remains NOT_CALIBRATED.

## Atomic issuance

Forecast + Decision Proof + FORECAST_ISSUED event are one SQLite transaction. A failure in
the final event insert rolls back all earlier rows. Partial issuance bundles fail closed
instead of being silently repaired or presented to the customer as complete.

## Authority boundary

This runtime is still evidence/research infrastructure:

- no exchange or broker order;
- no credentials;
- no leverage/borrowing/martingale;
- no automatic production deployment;
- no canonical Paper Fund mutation;
- no production UI cutover;
- no real capital.

A non-CLEAR Event Risk state is preserved in the forecast/proof and never hidden. Slice 2
does not turn a directional forecast into capital authority.

## Next frontier

After this slice passes hosted + full-repository acceptance, the next missing layer is the
**family evidence adapter rail**:

- accepted M2 Liquidity freezes -> M6 Liquidity + Decision Proof domains;
- accepted M3 Order Flow/Absorption freezes -> M6 Order Flow + Decision Proof;
- accepted M4 Derivatives freezes -> M6 Derivatives + Decision Proof;
- accepted M5 On-chain/Smart-Money freezes -> M6 On-chain + Decision Proof;
- accepted PA/geometry freeze -> M6 Geometry + frozen chart/candle proof.

Those adapters must be deterministic, PIT-safe and source-ID preserving. Only after replay
acceptance should a 7/24 writer be considered for a separately authorized production gate.
