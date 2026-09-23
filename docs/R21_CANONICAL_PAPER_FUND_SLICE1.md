# R21 Canonical Paper Fund — Slice 1: Epoch 2 Activation & Vault Accounting

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Activate the accepted Paper Fund Epoch 2 contract as a separate, append-only
1,000 USDT accounting program without rewriting the immutable 100 USDT Epoch 1 history.

This slice establishes canonical paper-fund accounting truth only. It does not submit
exchange orders, enable leverage, borrow between vaults, or create real-money authority.

## Immutable Epoch boundary

Epoch 1 remains exactly as accepted:

- epoch: `paper-epoch-1-legacy-100-usdt`;
- starting cash: 100 USDT;
- ledger: `paper_fund.sqlite3`;
- all legacy records remain byte-for-byte untouched.

Epoch 2 uses its already accepted separate ledger:

- epoch: `paper-epoch-2-current-1000-usdt`;
- starting cash: 1,000 USDT;
- ledger: `paper_fund_epoch2.sqlite3`;
- predecessor: exact Epoch 1 identity.

R21 activation stores the raw SHA-256 of the Epoch 1 database and refuses activation unless
that database contains exactly one valid legacy 100 USDT fund creation.

## Initial vaults

Activation creates cash-only initial accounting snapshots:

- Core: 600 USDT;
- Tactical: 300 USDT;
- Opportunity Reserve: 100 USDT.

At activation:

- positions are empty;
- marked exposure is 0;
- realized/unrealized PnL is 0;
- drawdown is 0;
- execution cost and turnover are 0;
- closed trade count is 0;
- expectancy is **None / NOT_YET_MEASURED**, not fabricated as zero performance.

## Append-only accounting

R21 adds three immutable table families inside the separate Epoch 2 database:

1. one immutable Epoch 2 activation row;
2. append-only per-vault accounting snapshots;
3. append-only consolidated parent snapshots.

SQLite UPDATE and DELETE are blocked by database triggers.

Every vault snapshot chains to the exact previous snapshot identity. A stale previous
identity, duplicate timestamp fork, or historical backfill fails closed.

Every consolidated snapshot chains to the previous parent snapshot and must reference the
latest same-timestamp snapshots for all three vaults.

## Vault accounting truth

Each vault snapshot tracks:

- cash;
- normalized positions;
- marked exposure;
- NAV;
- realized PnL;
- unrealized PnL;
- high-water NAV;
- drawdown;
- fees;
- spread cost;
- slippage cost;
- turnover notional;
- turnover fraction;
- closed trade count;
- win / loss / breakeven count;
- expectancy when measurable;
- outcome distribution;
- exact source record identities.

Reconciliation invariants:

- `NAV = cash + marked exposure`;
- `NAV = starting cash + realized PnL + unrealized PnL`;
- drawdown is derived from the vault's historical high-water NAV;
- turnover fraction is turnover notional divided by that vault's starting cash;
- no realized PnL is allowed before a closed trade exists.

## Consolidated fund truth

The parent fund aggregates the three same-time vault snapshots.

It tracks the same accounting metrics and enforces:

- exact cash/exposure/NAV aggregation;
- exact realized/unrealized PnL aggregation;
- exact explicit-cost aggregation;
- exact turnover aggregation;
- exact outcome-count aggregation;
- parent high-water NAV from **parent history**, not the sum of independently-timed vault peaks.

This avoids overstating consolidated high-water NAV when vaults peak at different times.

## Activation semantics

`initialize_epoch2_canonical_fund(...)` is idempotent for the exact same activation.

It:

1. verifies Epoch 1 legacy truth;
2. records Epoch 1 raw SHA-256;
3. creates the separate Epoch 2 activation;
4. creates Core/Tactical/Reserve initial snapshots;
5. creates the initial consolidated 1,000 USDT snapshot;
6. verifies Epoch 1 bytes remain unchanged;
7. returns the reconstructed canonical Epoch 2 state.

A different activation attempt against an already-activated Epoch 2 ledger fails closed.

## Phase boundaries

R21 accounting is intentionally narrower than later roadmap phases:

- Phase 17 Transaction & Decision Tape will provide richer mutation/fill lineage;
- this slice already requires source record identities for non-initial snapshots;
- no cross-vault transfer API exists;
- no order submission API exists;
- no network/exchange credentials are used;
- no real-capital authority exists.

## Acceptance checklist

1. Existing Epoch 1 ledger remains byte-for-byte unchanged.
2. Epoch 1 and Epoch 2 paths must remain separate.
3. Epoch 1 must contain exactly one valid accepted legacy fund creation.
4. Epoch 2 activates exactly 1,000 USDT.
5. Initial vault cash is exactly 600 / 300 / 100.
6. Initial consolidated NAV is exactly 1,000 USDT.
7. Empty-history expectancy remains NOT_YET_MEASURED.
8. Vault NAV/PnL/cost/turnover/outcome accounting reconciles.
9. Parent accounting exactly reconciles to three same-time vaults.
10. Parent high-water/drawdown uses parent history rather than summed vault peaks.
11. Snapshot previous-identity lineage prevents forks and stale backfills.
12. SQLite UPDATE/DELETE immutability triggers hold.
13. Initialization is idempotent for exact same activation.
14. No leverage, borrowing, martingale, cross-vault transfer, network/order or real-money authority.
15. REAL_CAPITAL=0.
16. Focused R21 + legacy Epoch/paper tests pass.
17. Full repository pytest/Ruff/mypy/JS/freshness regression passes.
18. Temporary hosted workflow is removed after PASS.

After acceptance, Phase 15 infrastructure exit is satisfied. The canonical Epoch 2 paper
fund has a truthful 1,000 USDT activation/accounting spine while real exchange authority
remains closed.

The next locked frontier is Phase 16 — R21.5 Shadow Lab 2.0.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
