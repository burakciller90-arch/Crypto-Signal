# Smart Capital Allocator — Slice 1: Epoch 2 Research Envelopes

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Implement Phase 10 without prematurely doing Phase 11 sizing or Phase 15 paper-ledger
activation.

The accepted Epoch 2 foundation already freezes:

- parent capital: **1,000 USDT**;
- Core Vault: **600 USDT**;
- Tactical Vault: **300 USDT**;
- Opportunity Reserve: **100 USDT**;
- no leverage;
- no borrowing;
- no martingale;
- separate future Epoch 2 ledger.

This slice reuses that contract. It does not duplicate or rescale it.

## Research-envelope semantics

The Smart Capital Allocator evaluates whether a frozen evidence candidate is eligible to
enter each vault's **research envelope**.

An eligible envelope is not a trade and not a position size.

Every vault decision preserves:

- exact candidate identity;
- exact Event Risk evidence identity;
- exact Confluence identity where present;
- tactical microstructure evidence identity where present;
- recovery evidence identity where present;
- fixed Epoch 2 starting budget;
- explicit eligibility state;
- explicit reason codes;
- mandatory Phase 11 sizing requirement before any trade;
- no cross-vault borrowing;
- no forced deployment;
- no production authority.

The allocator never emits a recommended notional in Slice 1.

## Core Vault

Core requires conservative evidence completeness:

- Event Risk circuit breaker must be `CLEAR`;
- M6 Confluence must exist;
- M6 resolution must be `MEASURED`;
- evidence coverage must be 100%;
- opposition score must be zero;
- material conflict must be absent;
- aggregate quality and freshness must be observable.

This deliberately does **not** hard-code a 70/75/80/85 threshold winner. M6 threshold
research did not authorize automatic winner selection.

## Tactical Vault

Tactical remains bounded to short-horizon microstructure research:

- Event Risk must be `CLEAR`;
- timeframe must be 1m or 5m;
- exact liquidity evidence identity is required;
- exact order-flow evidence identity is required;
- exact market-quality identity is required;
- CVD availability is explicit;
- absorption evidence availability is explicit;
- liquidity-sweep evidence availability is explicit;
- the bundle must declare complete evidence.

No leverage is introduced.

## Opportunity Reserve

Opportunity Reserve cannot blindly buy a crash.

Eligibility requires Event Risk `CLEAR` plus explicit evidence that all four recovery
dimensions are presently satisfied under this locked research policy:

- spread stabilized;
- liquidity recovered;
- price discovery stable;
- feed quality healthy.

Each dimension carries its own evidence identity.

Failure of any dimension leaves the reserve in `HOLD_CASH`.

## Cash is valid

`HOLD_CASH` is a professional allocator state, not an error.

CAUTION, EVENT_BLOCK, DEGRADED_DATA or ABSTAIN from the circuit breaker force all three
vaults to HOLD_CASH.

Each vault evaluates independently; one vault cannot borrow unused budget from another.

## Pre-activation metric truth

The Phase 10 allocator does not create `paper_fund_epoch2.sqlite3`.

Therefore current:

- cash;
- NAV;
- exposure;
- PnL;
- drawdown;
- cost;
- turnover;
- consolidated NAV

remain explicitly unavailable with `metrics_status = NOT_ACTIVATED`.

Only the immutable **starting budgets** are exposed.

Actual per-vault accounting belongs to the later Epoch 2 activation/accounting gate
(R21 / Phase 15). This prevents a pre-activation UI from displaying invented performance.

## Relationship to legacy paper engine

Existing Stage 6C planning/sizing/portfolio/performance modules are Epoch 1 / 100-USDT
contracts and remain untouched.

This slice does not silently reinterpret those records as 1,000 USDT or as vault-aware
accounting.

Phase 11 may reuse proven sizing mechanics only through an explicit Epoch 2/vault-aware
adapter with its own acceptance evidence.

## Acceptance checklist

1. Reuses exact accepted Epoch 2 identity.
2. Starting budgets remain exactly 600 / 300 / 100 and sum to 1,000.
3. No new Epoch 2 ledger is created.
4. Core fails closed on incomplete, opposed or conflicting Confluence evidence.
5. Tactical fails closed without complete 1m/5m microstructure evidence.
6. Opportunity Reserve fails closed without complete recovery evidence.
7. Any non-CLEAR Event Risk state forces all vaults to HOLD_CASH.
8. Cash is valid and no vault is forced to deploy.
9. No cross-vault transfer or borrowing authority.
10. No notional sizing authority.
11. Current vault NAV/PnL/drawdown/cost/turnover remain NOT_ACTIVATED rather than fabricated.
12. No network, exchange, ledger-write or runtime-control surface.
13. REAL_CAPITAL=0.
14. Focused pytest/Ruff/mypy plus full repository Python/JS/freshness regression.
15. Temporary hosted workflow removed after PASS.

After Slice 1 acceptance, the Phase 10 allocator decision contract is satisfied without
activating capital. The next locked frontier is Phase 11 Position Sizing Intelligence,
where Kelly remains disabled unless exact R19 calibration evidence exists.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
