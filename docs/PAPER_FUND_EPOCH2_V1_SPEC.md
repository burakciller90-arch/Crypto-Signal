# PAPER FUND EPOCH 2 — 1,000 USDT CONTRACT

Status: **locked development specification; not production-activated**  
Governing roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
Safety invariant: **REAL_CAPITAL=0**

## 1. Purpose

Paper Fund Epoch 2 creates a new canonical virtual-capital history beginning at
**1,000.00 USDT** without rewriting, rescaling, deleting or merging the accepted
100 USDT Epoch 1 track record.

This document does not activate a paper writer and does not grant any real-order,
broker, credential, leverage, borrowing or withdrawal authority.

## 2. Epoch boundary

### Epoch 1 — Legacy / immutable

- epoch id: `epoch1-legacy-100-usdt`;
- accepted starting cash: **100.00 USDT**;
- existing fund creation, decisions, fills, mutations, NAV, benchmarks and outcomes
  remain exactly as historically recorded;
- the legacy `INITIAL_CASH_USDT` constant and v1 FundCreationRecord semantics are
  not changed to 1,000 USDT;
- Epoch 1 history is never multiplied by ten to make it resemble Epoch 2.

### Epoch 2 — Current program / not yet activated

- epoch id: `epoch2-current-1000-usdt`;
- starting virtual NAV: **1,000.00 USDT**;
- positions at epoch creation: none;
- REAL_CAPITAL=0;
- capital is a **new virtual seed**, not a transfer, profit, deposit or balance carry
  from Epoch 1;
- production activation requires a separate accepted implementation and the existing
  human-impact/production gate.

## 3. Initial Smart Capital Allocator research policy

The locked starting research allocation is:

| Vault | Virtual allocation |
| --- | ---: |
| Core | 600.00 USDT |
| Tactical | 300.00 USDT |
| Opportunity Reserve | 100.00 USDT |
| **Total** | **1,000.00 USDT** |

This split is a research policy, not a promise of optimal allocation or return.

### Core

- highest evidence completeness;
- low contradiction tolerance;
- lower expected trade frequency;
- respects Event Risk;
- cash/no-position is allowed.

### Tactical

- short-horizon microstructure research;
- liquidity/order-flow/CVD/absorption evidence where data quality supports it;
- no leverage in the accepted v1.1 canonical lane.

### Opportunity Reserve

- remains cash unless an accepted opportunity policy is satisfied;
- a price crash alone is never sufficient;
- stabilization, liquidity, feed quality and Event Risk remain relevant.

## 4. Transition semantics

The Epoch 1 -> Epoch 2 transition is modeled as:

`new_virtual_seed_no_balance_carry`

Required properties:

1. source Epoch 1 fund identity is preserved;
2. source initial cash remains exactly 100.00 USDT;
3. source history action is `preserve_immutable`;
4. target Epoch 2 starts at exactly 1,000.00 USDT;
5. no Epoch 1 NAV/PnL is copied into the Epoch 2 opening balance;
6. transition planning is pure/read-only and cannot mutate a ledger;
7. a new canonical epoch ledger/namespace must be explicit before activation.

## 5. Scientific and safety boundaries

- REAL_CAPITAL=0;
- no real exchange order;
- no trading credential authority;
- no leverage, borrowing or martingale in canonical v1.1;
- fees/spread/slippage remain mandatory when simulated execution is later activated;
- Shadow Lab never mutates canonical Epoch 2 history;
- R19 calibration is required before calibrated probability can drive any promoted
  probability-based sizing policy;
- Kelly remains ineligible until R19 acceptance and separate sizing promotion evidence.

## 6. Acceptance for this development slice

This slice is accepted when:

- Epoch 1 tests continue to prove exact 100 USDT semantics;
- Epoch 2 spec deterministically proves exact 1,000 USDT starting NAV;
- vault allocation is exactly 600/300/100 and sums to 1,000;
- transition plan explicitly preserves Epoch 1 and prohibits balance carry;
- identities are deterministic;
- REAL_CAPITAL remains 0;
- focused pytest, Ruff and mypy pass;
- no production paper ledger is modified.

A later slice will implement a dedicated Epoch 2 ledger/runtime namespace and migration
acceptance. That later production activation remains separately gated.
