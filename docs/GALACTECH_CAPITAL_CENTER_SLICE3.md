# GALACTECH Product Rail — Capital Center Slice 3

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
Predecessor: accepted GALACTECH Command + Evidence Room PR #925.
REAL_CAPITAL=0.

## Canonical source

Capital Center is bound to the accepted R21 Epoch 2 accounting ledger, not the legacy
Epoch 1 mission-control projection.

The product endpoint is:

`GET /api/paper/epoch2-state`

It opens the configured Epoch 2 SQLite file strictly read-only with SQLite URI
`mode=ro` and `PRAGMA query_only=ON`.

It does not call the mutable `Epoch2CanonicalLedger.initialize()` path and therefore
does not create tables, WAL state or an empty database as a side effect of a product read.

## Truth shown

When canonical Epoch 2 evidence is available, Capital Center exposes:

- consolidated NAV;
- cash;
- marked exposure;
- realized and unrealized PnL;
- drawdown;
- fees, spread and slippage;
- turnover;
- closed-trade outcome counts;
- expectancy or explicit NOT YET MEASURED;
- exact consolidated snapshot identity and timestamp;
- Core / Tactical / Opportunity Reserve vault states;
- per-vault starting cash, current cash, exposure, NAV, PnL, drawdown, costs,
  turnover, closed trades, expectancy and positions;
- activation identity and authority constraints.

The Command Center Paper NAV tile uses this same canonical R21 consolidated NAV.

## Allocation explanation

The 600 / 300 / 100 USDT Core / Tactical / Opportunity Reserve split is described as
the **accepted Epoch 2 constitution**.

It is not:
- inferred by the frontend;
- a fresh AI recommendation;
- an optimization claim;
- permission to mutate the vaults.

## Missing-evidence behavior

If the canonical Epoch 2 runtime is not configured, missing, not activated or internally
inconsistent, the UI remains explicit:

- runtime NAV = NOT MEASURED / UNAVAILABLE;
- constitution may still be shown as a contract;
- no PnL, allocation state or performance is fabricated from the constitution alone.

Empty trade history remains NOT YET MEASURED and is never displayed as 0% win rate.

## Authority

- read-only product projection;
- no ledger initialization or mutation;
- no real exchange order path;
- no credentials;
- no leverage, borrowing or martingale;
- REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
