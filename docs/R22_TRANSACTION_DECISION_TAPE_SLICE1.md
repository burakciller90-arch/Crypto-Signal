# R22 Transaction & Decision Tape — Slice 1 (development-only)

Parent: docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md, Phase 17.
Baseline: accepted R20 forecast / R20.5 Decision Proof / R21 Epoch 2.
REAL_CAPITAL=0. This slice adds no production paper mutation and no exchange authority.

## Completed contract in this slice

- Freeze a distinct policy/sizing-backed intent before any simulated fill.
- For a trade intent require **exact** accepted R20 forecast and corresponding R20.5
  Decision Proof identities, symbol, issuance time and source-as-of.
- HOLD_CASH is a valid immutable decision with no fabricated forecast, sizing or fill.
- Bind each isolated simulated fill to a prior intent and to exact before/after
  R21 Epoch 2 per-vault accounting snapshot hashes.
- Require R21 after-snapshot source records to include the immutable R22 intent
  plus exact market mark evidence; require explicit outcome identity for a sale.
- Reconstruct buy/exit/reduce cash and position movement using filled quantity,
  simulated fill price and additional fee. Explicit spread+slippage must reconcile
  to the adverse difference between reference and fill prices, not be charged twice.
- Reconcile changes in cumulative fee/spread/slippage, turnover notional,
  realized/unrealized PnL and total NAV. Other-symbol mutations cannot hide inside
  this **one-fill-per-vault-snapshot** development audit.
- Separate append-only SQLite tape carries SHA-bound intent and fill payloads,
  per-vault predecessor chains, idempotent exact replay, timestamp/backfill/fork
  rejection and UPDATE/DELETE protection. Read-only verification hashes every row.

## Very important accounting interpretation

The fill price includes spread/slippage. Only the separately specified fee is
subtracted **again** from cash. The R21 snapshot's mark evidence explains
unrealized PnL and NAV differences; this audit does not invent an unobserved
mark or assign every mark-to-market move to the trade. A sale requires explicit
outcome evidence if its R21 closed-trade count increases.

The R20 forecast and Decision Proof are immutable evidence, **not permission
to trade**. The presence of a policy identity and a sizing identity in this
development tape does not grant canonical execution or promote shadow research.

## Not yet accepted: Phase 17 exit still open

This isolated implementation deliberately does NOT:

- open or mutate the live/accepted R21 Epoch 2 SQLite database;
- use the v1.0 Epoch 1 ledger for writes;
- create a real or simulated order-submission API;
- authorize a production Paper Fund scheduler/allocator mutation;
- atomically commit across R21 and R22 ledger databases;
- handle a batch of multiple fills inside a single R21 vault snapshot;
- bind a real feed or deploy to the SSD.

A future Phase 17 integration slice must define atomic commit or a provably
recoverable two-phase/outbox protocol, and demonstrate replay from the frozen
R22 tape back into exact R21 vault and consolidated snapshots. Before any
production enablement: fresh mechanical state, explicit human-impact approval,
hosted full gate, UID504 bounded verification and read-only production audit.

## Slice 1 acceptance

- focus tests for BUY/EXIT, HOLD, identity mismatch, future data, cost
  double-counting, bad cash, missing mark and missing outcome;
- SQLite idempotency and UPDATE/DELETE protection;
- focused pytest + Ruff + strict mypy;
- whole-repository pytest/Ruff/mypy/JS/freshness hosted regression;
- independent exact branch SHA check before acceptance;
- no wake/lease replay and no Cursor workers.

Status remains CANDIDATE until gates pass. Passing Slice 1 does not by itself
close Phase 17 or authorize production capital mutations.
