# Crypto Signal — FP2 Paper Vault V3 Constitution Matrix

Status: **ACCEPTED / REVIEW READY**
Date: 2026-09-29
Base main: `3b7cd1bc63446d818a6c5fff852b9ff10c7797b3`
Active branch: `fp2/paper-vault-v3-constitution`
Safety: **REAL_CAPITAL=0**
Historical rewrite/backfill: **FORBIDDEN**
RDP11 soaked-runtime mutation: **FORBIDDEN**

## 1. Purpose

FP2 introduces a new final-product **Paper Vault V3 constitution** without changing Epoch 1 or Epoch 2.

The constitution is immutable product truth for a newly created virtual-capital vault. It does not execute, size, allocate a live candidate, calculate PnL, or rewrite historical paper programs.

Classification:
- **REUSE immutable**: Epoch 1 / Epoch 2 files and history;
- **REUSE type**: current `PaperSymbol` supported paper universe;
- **REUSE policy references**: current execution and risk policy version strings;
- **REUSE concept only**: Smart Capital Allocator sleeves / no borrowing / cash-valid semantics;
- **BUILD separate**: V3 constitution, V3 allocation-constraint policy, append-only V3 constitution/lifecycle store;
- **DO NOT EXTEND IN PLACE**: `PaperFundEpochSpec`, `PaperVaultId`, R21 Epoch2 accounting, R22 tape, S11 canonical sizing/decisions.

## 2. Historical isolation

These remain byte-immutable and semantically unchanged:
- Epoch 1: `paper_fund.sqlite3`;
- Epoch 2: `paper_fund_epoch2.sqlite3`;
- `EPOCH_1_SPEC`;
- `EPOCH_2_SPEC`;
- Epoch 2 fixed 600/300/100 starting allocations;
- Epoch 2 `PaperVaultId.CORE / TACTICAL / OPPORTUNITY_RESERVE`;
- Smart Capital Allocator V1 Epoch2 hard-binding.

FP2 V3 persistence must use a **separate caller-supplied database path**.

No migration, attach, copy, backfill or ALTER of Epoch 1/2 is authorized.

## 3. V3 constitution contract

### 3.1 PaperVaultV3Constitution

Immutable fields:
- `vault_identity`: canonical SHA256 of the full constitution payload;
- `created_at_ms`;
- `starting_virtual_capital_usdt`;
- `constitution_policy_version`;
- `permitted_instruments`: sorted unique tuple of supported `PaperSymbol`;
- `execution_policy_version`;
- `risk_policy_version`;
- nested immutable `allocation_policy`;
- sorted unique `evidence_policy_versions`;
- `cross_vault_borrowing_allowed=False`;
- `real_capital=0`;
- `production_authority=False`.

Default builder capital may be **10,000 USDT**, but the exact amount is serialized inside each constitution and therefore is not a mutable/global account truth.

Starting capital must be finite and positive.

### 3.2 Existing policy references

Default execution reference:
`PAPER_EXECUTION_POLICY_VERSION`

Default risk reference:
`PAPER_RISK_POLICY_VERSION`

These are frozen strings in the constitution. FP2 does not modify their implementations.

A separate `constitution_policy_version` identifies the V3 constitution contract itself.

### 3.3 Evidence policy references

Each reference contains:
- canonical domain key;
- non-empty version.

References must be sorted by domain and unique.

FP2 does not create a new evidence engine. These references freeze which accepted evidence-policy versions a later forward runtime must obey.

## 4. V3 allocation constitution

### 4.1 Books

V3 policy books:
- `CORE`;
- `TACTICAL`;
- `OPPORTUNITY`;
- `CASH`.

These are V3 policy books, not the Epoch2 `PaperVaultId` accounting identities.

### 4.2 Allocation policy

Immutable `PaperVaultV3AllocationPolicy` fields:
- `policy_identity`;
- `version`;
- sorted unique permitted books;
- `minimum_market_exposure_fraction=0`;
- `maximum_market_exposure_fraction=1`;
- `cash_is_valid=True`;
- `cross_vault_borrowing_allowed=False`;
- `forced_deployment=False`;
- `real_capital=0`;
- `production_authority=False`.

This freezes the allocation constraints and makes the policy configuration replayable.

FP2 does **not** choose a live target allocation. Dynamic candidate allocation belongs to later capital-policy/runtime phases.

100% cash is explicitly valid because:
- CASH is a permitted book;
- minimum market exposure is exactly zero;
- forced deployment is false.

No policy may require a positive minimum Core/Tactical/Opportunity exposure in FP2.

## 5. No-reset lifecycle

Constitution creation implies initial status **ACTIVE**.

Authorized append-only lifecycle actions:
- `STOP`;
- `ARCHIVE`.

Allowed transitions:
- ACTIVE -> STOPPED;
- ACTIVE -> ARCHIVED;
- STOPPED -> ARCHIVED.

Forbidden:
- STOPPED -> ACTIVE;
- ARCHIVED -> any state;
- reset starting capital;
- replace policy versions;
- delete losing history;
- UPDATE/DELETE any constitution/event.

To start again under different capital or policy, create a **new constitution with a new identity**.

## 6. Persistence

New module owns one separate SQLite store with:
- schema/meta table;
- `paper_vault_v3_constitutions`;
- `paper_vault_v3_lifecycle_events`.

Both truth tables are append-only and protected by UPDATE/DELETE abort triggers.

Stored rows include canonical JSON + SHA256 digest and must be verified on read.

Writer semantics:
- identical constitution append is idempotent;
- identity/payload conflict fails closed;
- lifecycle events must reference an existing constitution;
- lifecycle chronology and transition graph are enforced;
- exact duplicate event is idempotent.

Read semantics:
- missing V3 DB -> no data, no creation;
- reads use SQLite read-only mode;
- payload digest/canonical identity/REAL_CAPITAL/authority boundaries are verified;
- current status is derived from immutable lifecycle events.

## 7. Non-goals

FP2 does not:
- activate a forward autopilot;
- rewrite Smart Capital Allocator V1;
- size a trade;
- produce an R22 fill;
- mutate R21;
- implement Execution Realism V2;
- deploy Product/Development;
- bind a new runtime while RDP11 soak is active.

Those belong to later FP3+ phases.

## 8. Acceptance

FP2 PASS requires:
1. Epoch 1/2 code and files are untouched;
2. V3 constitution identity is deterministic over complete immutable payload;
3. starting capital is frozen per constitution;
4. permitted instruments are canonical/sorted/unique;
5. execution/risk/constitution/evidence policy versions are frozen;
6. V3 allocation policy identity/config is deterministic and replayable;
7. minimum market exposure is zero;
8. 100% cash is valid;
9. borrowing and forced deployment are impossible;
10. V3 store is physically separate from Epoch 1/2;
11. constitution/event UPDATE and DELETE fail;
12. append is idempotent but conflicting payload fails closed;
13. STOP/ARCHIVE lifecycle is append-only and cannot reactivate;
14. missing DB read is non-creating;
15. source/legacy sentinel bytes remain unchanged in focused tests;
16. REAL_CAPITAL=0;
17. focused pytest PASS;
18. Ruff PASS;
19. strict mypy PASS;
20. Product/Development non-mutation PASS;
21. project isolation PASS.

## 9. Exact next action

Implement a new isolated `src/crypto_signal/paper/vault_v3.py` module plus focused `tests/test_paper_vault_v3.py`.

Do not edit Epoch 1/2 accounting/tape/allocator implementations, Product routes/frontend, runtime/deploy configuration or the RDP11 observer.


## 10. UID504 acceptance

Status: **PASS**

Accepted exact-head:
- head SHA: `7d98300ffbd3b0e32b9f4aac7f3eb44514c224cf`;
- run: `36587124704`;
- job: `109470381739`;
- conclusion: **SUCCESS**.

Mechanical markers:
- exact-source checkout PASS;
- focused/regression pytest 100% PASS;
- Ruff: **All checks passed!**;
- strict mypy: **Success: no issues found in 5 source files**;
- Product/Development non-mutation PASS;
- project isolation PASS;
- `REAL_CAPITAL=0`.

Cleanup:
- temporary UID504 workflow restored in `cd6a714523e032496809d33d8edf9875b77e2eda`;
- branch workflow blob equals current-main workflow blob `394051a78c665d84cf78830cedc8799a13474baa`.

Accepted FP2 result:
- Epoch 1/2 implementations remain untouched;
- Paper Vault V3 has a separate immutable constitution/store namespace;
- constitution identity freezes starting capital, policy versions, instruments, allocation policy and evidence-policy refs;
- default 10,000 USDT is per-constitution truth, not a resettable global balance;
- allocation policy freezes minimum exposure 0, maximum exposure exactly 1, 100% cash valid, borrowing=false and forced-deployment=false;
- STOP/ARCHIVE lifecycle is append-only and cannot reactivate/reset;
- exact duplicate appends are idempotent;
- UPDATE/DELETE are trigger-blocked;
- missing-store reads are non-creating/read-only;
- corrupted persisted payloads fail closed;
- legacy Epoch1/Epoch2 sentinel bytes remain unchanged;
- no runtime/deploy/RDP11 mutation occurred.
