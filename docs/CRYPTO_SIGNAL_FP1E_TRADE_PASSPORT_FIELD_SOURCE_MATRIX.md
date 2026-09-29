# Crypto Signal — FP1-E Trade Passport Field-Source Matrix

Status: **ACCEPTED / REVIEW READY**
Date: 2026-09-29
Base main: `5490bc184eb51f3507ede93bc72b488ea38cd5dd`
Active branch: `fp1e/trade-passport-read-model`
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**

## 1. Purpose

FP1-E adds one frontend-safe **Trade Passport** projection over accepted immutable paper-capital and proof truth.

It is not:
- a new trade ledger;
- a new accounting system;
- a new PnL calculator;
- a replacement for R21/R22;
- a new evidence engine;
- a historical backfill job;
- a Product route/frontend/deploy slice.

Classification:
- **REUSE** R22 immutable trade/accounting bundle;
- **REUSE** R21 before/after accounting snapshots;
- **REUSE** S11 canonical outcome evidence;
- **REUSE** Decision Proof / exact forecast lineage;
- **EXTEND** one customer projection;
- **EXPLICITLY_UNAVAILABLE** proof detail when the accepted Decision Evidence source is absent or missing;
- **BUILD** no new canonical truth store.

## 2. Canonical passport key

The passport lookup key is the immutable **R22 bundle identity**.

Reason:
- `R22Epoch2AtomicTape.read_bundle_story_context(bundle_identity)` already verifies the full persisted bundle;
- it returns exact intent, fill, optional sell outcome, target-vault before/after accounting, consolidated before/after accounting and immutable lineage;
- it is read-only and fails closed when any lineage is missing or inconsistent.

FP1-E must not infer or reconstruct a bundle from current market state.

## 3. Canonical source precedence

### 3.1 Trade/accounting source

Use only:

`R22Epoch2AtomicTape(epoch2_path).read_bundle_story_context(bundle_identity)`

Accepted fields:

**bundle**
- bundle identity;
- intent identity;
- fill identity;
- vault id;
- before/after vault snapshot identity set;
- before/after consolidated snapshot identities;
- accounting snapshot time;
- REAL_CAPITAL / authority boundary.

**intent**
- forecast identity;
- proof identity;
- signal freeze identity;
- policy identity;
- sizing assessment identity;
- sizing decision identity;
- allocator candidate identity;
- paper decision identity;
- source evidence identities;
- action;
- symbol;
- quantity;
- reference price;
- decision time;
- reason codes.

**fill**
- action;
- symbol;
- financial outcome;
- source fill identity;
- mutation identity;
- fill/mutation/snapshot times;
- quantity;
- reference price;
- simulated fill price;
- notional;
- fee/spread/slippage;
- execution policy version;
- venue reference;
- cash before/after;
- position quantity before/after;
- vault NAV before/after;
- realized/unrealized PnL delta;
- mark evidence identity;
- optional outcome evidence identity.

**R21 before/after target vault**
- cash;
- NAV;
- realized/unrealized PnL;
- positions;
- costs;
- source record identities.

**R21 before/after consolidated**
- total cash/NAV/exposure/PnL/cost state;
- exact three-vault snapshot lineage.

**S11 outcome**
- required for REDUCE/EXIT;
- absent for BUY by contract;
- financial outcome and realized PnL must match the exact fill;
- outcome identity must be present in the target R21 after-snapshot lineage.

No direct SQL is added in Final Product.

### 3.2 Decision Proof source

When `decision_evidence_path` is present and readable:

`ImmutableDecisionEvidenceLedger(decision_evidence_path).read_proof_for_forecast(forecast_identity)`

FP1-E must verify:
- returned forecast identity equals the R22 intent forecast identity;
- proof identity equals the R22 intent proof identity;
- signal freeze identity equals the R22 intent signal-freeze identity;
- `read_only=true`;
- `production_authority=false`;
- `REAL_CAPITAL=0`.

Customer-safe proof fields may then expose:
- timeframe;
- source-as-of time;
- conditional thesis;
- direction label;
- trigger zone;
- target zone;
- invalidation price;
- uncertainty summary;
- proof availability state.

If the Decision Evidence DB is not configured:
- Trade Passport remains available from R22/R21;
- proof label is explicit: **Karar kanıtı kaynağı bağlı değil**.

If the DB exists but exact proof is absent:
- Trade Passport remains available;
- proof label is explicit: **Karar kanıtı bulunamadı**.

A mismatched proof is a fail-closed `FinalProductReadError`.

### 3.3 RDP10 / exact evidence lineage

FP1-E does not build a second RDP10 resolver.

Exact proof/evidence lineage already enters R22 through:
- forecast identity;
- proof identity;
- signal freeze identity;
- `source_evidence_identities`.

Those identities remain **audit-only** in FP1-E.

Full family visual/evidence reconstruction remains owned by accepted RDP10/Stream proof readers and later product surfaces.

## 4. Customer contract

### 4.1 TradePassportView

Customer-readable fields:
- availability label;
- program label: Paper Capital · Epoch 2;
- action label;
- execution/outcome label;
- vault label;
- symbol;
- optional timeframe;
- decision time;
- fill time;
- accounting snapshot time;
- optional proof source-as-of time;
- decision thesis;
- optional direction label;
- optional trigger/target/invalidation;
- proof availability label;
- quantity;
- decision reference price;
- simulated fill price;
- notional;
- fee/spread/slippage;
- cash before/after;
- vault NAV before/after;
- consolidated NAV before/after;
- position quantity before/after;
- realized PnL delta;
- unrealized PnL delta;
- read-only + REAL_CAPITAL=0.

Customer action labels:
- BUY -> **Pozisyon açıldı / artırıldı**;
- REDUCE -> **Pozisyon azaltıldı**;
- EXIT -> **Pozisyon kapatıldı**.

Outcome labels:
- OPEN -> **Pozisyon açık**;
- PARTIAL_REDUCTION -> **Kısmi azaltma**;
- CLOSED_WIN -> **Kârla kapandı**;
- CLOSED_LOSS -> **Zararla kapandı**;
- CLOSED_BREAKEVEN -> **Başa baş kapandı**.

No internal enum is required for customer comprehension.

### 4.2 Audit payload

Optional audit may preserve:
- bundle/intent/fill identities;
- activation identity;
- forecast/proof/signal-freeze identities;
- policy/sizing/allocator/decision identities;
- source evidence identities;
- source fill/mutation/mark/outcome identities;
- before/after R21 snapshot identities;
- raw action/outcome/reason codes;
- execution policy / venue reference.

Audit metadata is never required for the default UI.

## 5. Empty / missing / corrupt semantics

- missing Epoch 2 DB -> **Trade Passport verisi kullanılamıyor**, no DB creation;
- unknown valid bundle identity -> **Trade Passport bulunamadı**;
- malformed identity -> input validation error;
- R22/R21 lineage corruption -> `FinalProductReadError`;
- proof source missing -> passport still available, proof explicitly unavailable;
- proof lineage mismatch -> `FinalProductReadError`;
- no current-data substitution;
- no historical reconstruction;
- no invented numeric zero.

## 6. Acceptance

FP1-E PASS requires:
1. missing Epoch 2 DB explicit/non-creating;
2. exact R22 bundle story context reused;
3. R21 accounting before/after values copied, not recomputed;
4. BUY/REDUCE/EXIT labels deterministic and fail-closed;
5. financial outcome copied from canonical fill/outcome truth;
6. Decision Proof optionality explicit;
7. Decision Proof lineage mismatch fails closed;
8. default customer payload hides SHA/raw enums/reason/database vocabulary;
9. audit preserves exact lineage;
10. source DB bytes unchanged;
11. focused pytest PASS;
12. Ruff PASS;
13. strict mypy PASS;
14. Product/Development non-mutation PASS;
15. project isolation PASS;
16. no RDP11 soaked-runtime mutation;
17. REAL_CAPITAL=0.

## 7. Exact next action

Implement only `TradePassportView` / `TradePassportAudit` and `FinalProductReadModel.trade_passport(bundle_identity, include_audit=False)` in `final_product_read_model.py`, plus focused tests.

Do not edit routes, frontend, R21/R22 writers, Decision Proof writers, runtime or deploy configuration.


## 8. UID504 acceptance

Status: **PASS**

Accepted exact-head run:
- head SHA: `587b6dfa29f707901a48f1ece399c7f001567edb`;
- run: `36577967469`;
- job: `109438394874`;
- conclusion: **SUCCESS**.

Mechanical markers:
- `MESSAGE_INTELLIGENCE_MI1_EXACT_SOURCE_PASS=YES`;
- Ruff: **All checks passed!**;
- strict mypy: **Success: no issues found in 5 source files**;
- `MESSAGE_INTELLIGENCE_MI1_NON_MUTATING_PASS=YES`;
- `PROJECT_ISOLATION_PASS=YES`;
- `REAL_CAPITAL=0`.

Cleanup:
- temporary UID504 workflow wiring restored in `e8958fb1b58b3576ee7d776f99dcba761def5977`;
- branch workflow blob equals exact current-main workflow blob `394051a78c665d84cf78830cedc8799a13474baa`.

Accepted result:
- Trade Passport composes R22/R21/S11/Decision Proof lineage read-only;
- no new accounting/trade/evidence truth store;
- customer payload is human-readable by default;
- exact immutable lineage remains optional audit metadata;
- missing proof remains explicit;
- corrupted/mismatched proof fails closed;
- canonical sources remain unmodified.
