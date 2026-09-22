# Paper Fund Epoch 2 — 1,000 USDT Foundation

Status: **v1.1 locked contract foundation**  
REAL_CAPITAL: **0**  
Parent roadmap: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Purpose

Move the canonical paper program from the historical 100 USDT experiment to a new
1,000 USDT epoch **without rewriting the original track record**.

This document does not authorize a production paper-ledger cutover by itself. It
defines the deterministic model and migration boundary that must exist before that
later gated activation.

## Immutable history rule

Epoch 1 stays exactly as written:

- epoch id: `paper-epoch-1-legacy-100-usdt`;
- starting cash: **100.00 USDT**;
- existing ledger filename: `paper_fund.sqlite3`;
- existing FundCreationRecord semantics remain v1 and are not edited;
- existing decisions, fills, mutations, NAV snapshots and benchmarks are not scaled,
  restated or copied into Epoch 2;
- Epoch 1 is legacy history and is not canonical for new activity.

No “100 -> 1,000” multiplication of historical PnL, positions or benchmark values is
permitted.

## Epoch 2 contract

Epoch 2 is the current paper-program contract for new activity:

- epoch id: `paper-epoch-2-current-1000-usdt`;
- starting cash: **1,000.00 USDT**;
- separate ledger filename: `paper_fund_epoch2.sqlite3`;
- predecessor: Epoch 1;
- REAL_CAPITAL=0;
- no real exchange order path;
- no leverage;
- no borrowing;
- no martingale.

The separate ledger filename is intentional. The existing Stage 6C ledger assumes one
fund creation per database and must remain replay-compatible with the immutable 100 USDT
history.

## Initial Smart Capital Allocator research envelope

Epoch 2 begins with a versioned research allocation:

| Vault | Starting cash | Role |
| --- | ---: | --- |
| Core | 600.00 USDT | highest-evidence, lower-frequency allocation |
| Tactical | 300.00 USDT | short-horizon microstructure research |
| Opportunity Reserve | 100.00 USDT | exceptional dislocation/recovery opportunities |

The allocations must sum exactly to 1,000 USDT.

These are starting research priors, not promises of safety or optimality. Cash is valid.
Canonical v1.1 does not enable leverage.

## Migration boundary

The safe migration path is:

1. keep `paper_fund.sqlite3` untouched and replayable as Epoch 1;
2. introduce the deterministic epoch registry and Epoch 2 identity;
3. add Epoch 2-aware accounting/benchmark/vault models in isolated development;
4. prove tests and replay compatibility;
5. create a new `paper_fund_epoch2.sqlite3` only at the later accepted activation gate;
6. initialize it once at 1,000 USDT with empty positions and REAL_CAPITAL=0;
7. expose Epoch 1 and Epoch 2 separately in UI/archive/performance;
8. allow only Epoch 2 to receive new canonical paper activity after activation;
9. never merge Epoch 1 and Epoch 2 into an unlabeled performance series.

## Acceptance for this foundation slice

- legacy `INITIAL_CASH_USDT` remains exactly 100.00;
- legacy `build_fund_creation` remains exactly 100.00;
- Epoch 1 ledger filename remains `paper_fund.sqlite3`;
- Epoch 2 is exactly 1,000.00;
- Epoch 2 uses a different ledger filename;
- vault allocation is exactly 600/300/100;
- one and only one epoch is current for new activity;
- deterministic epoch identities are stable;
- REAL_CAPITAL=0;
- invalid capital/vault/leverage contracts fail closed.

Production activation is a later gate; this slice performs no live paper-ledger mutation.
