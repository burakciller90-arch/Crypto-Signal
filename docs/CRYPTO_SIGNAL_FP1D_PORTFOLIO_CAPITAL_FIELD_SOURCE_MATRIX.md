# Crypto Signal — FP1-D Portfolio + Capital Movements Field-Source Matrix

Status: **D1 ACCEPTED / D2 AUDIT COMPLETE / D2 IMPLEMENTATION NEXT**
Date: 2026-09-29
Base main: `e16bf10e6cd6a653cb9ab96616cea88d1df5e242`
Active branch: `fp1d/portfolio-capital-movements-current`
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**

## 1. Purpose

FP1-D adds final-product read models for:

1. **Portfolio Summary**
2. **Daily Capital Movements**

It does not create or mutate:
- capital accounting;
- transaction tape;
- performance engine;
- paper execution;
- Stream Capital ledger;
- Product/Development runtime;
- historical Epoch 1/Epoch 2 evidence.

Epoch 1 and legacy `/api/paper/mission-control` remain separate historical/legacy programs and are not canonical final Portfolio truth.

## 2. Portfolio Summary canonical source

### 2.1 R21 Epoch 2 accounting

**Classification: REUSE + customer projection EXTEND**

Canonical read API:

`read_epoch2_state_read_only(path)`

Safety:
- missing file -> `None`;
- required schema incomplete -> fail closed;
- SQLite opened `mode=ro`;
- `PRAGMA query_only=ON`;
- read does not initialize the DB.

Canonical state:
- activation;
- exactly three latest vault snapshots;
- one latest consolidated snapshot;
- strict activation/vault/consolidated identity reconciliation.

Consolidated fields available exactly:
- current NAV/equity;
- cash;
- marked exposure;
- realized PnL;
- unrealized PnL;
- high-water NAV;
- current drawdown fraction;
- fee;
- spread;
- slippage;
- turnover;
- closed trade count;
- win/loss/breakeven counts;
- expectancy when measured;
- metrics status.

Per-vault fields available exactly:
- vault id;
- starting cash;
- cash;
- positions;
- marked exposure;
- NAV;
- realized/unrealized PnL;
- high-water NAV;
- drawdown;
- costs;
- turnover;
- closed trade count/outcomes;
- expectancy/metrics status.

### 2.2 Allowed Portfolio composition

FP1-D may derive only identities already enforced by R21 arithmetic:

- total PnL label from `realized_pnl + unrealized_pnl`;
- used capital from `marked_exposure_usdt`;
- open position count from exact non-zero `positions`;
- starting capital from Epoch 2 activation;
- cash fraction / exposure fraction only from exact consolidated NAV/cash/exposure when denominator is non-zero.

These are display compositions over a reconciled snapshot, not a second accounting engine.

### 2.3 R24 Performance & Trust

**Classification: REUSE, not recompute inside FP1-D**

R24 already owns:
- max-drawdown-over-history semantics;
- profit factor;
- gross profit/loss;
- performance cohorts;
- calibration/trust;
- risk-adjusted metric availability.

FP1-D must not rebuild `build_performance_trust_center`.

Core Portfolio Summary may use R21 current drawdown and current accounting now.

R24-only metrics remain **EXPLICITLY UNAVAILABLE in FP1-D core** unless a separately accepted/precomputed R24 source is later supplied to the final read model.

Do not label R21 current drawdown as historical maximum drawdown.

## 3. Portfolio customer contract

Customer-facing fields:

### Consolidated
- program label: **Paper Capital · Epoch 2**;
- status;
- snapshot time;
- starting capital;
- current equity/NAV;
- cash;
- used capital / marked exposure;
- realized PnL;
- unrealized PnL;
- total PnL;
- current drawdown;
- fees;
- spread cost;
- slippage cost;
- turnover;
- open position count;
- closed trade count;
- win/loss/breakeven;
- expectancy if measured;
- performance status.

### Vault rows
For Core / Tactical / Opportunity:
- starting budget;
- cash;
- NAV;
- used capital;
- realized/unrealized PnL;
- current drawdown;
- open positions;
- trade counts;
- expectancy if measured.

### Position rows
Only exact R21 position truth:
- vault;
- symbol;
- quantity.

R21 does not carry per-position entry price/current mark/PnL in the canonical snapshot object, so FP1-D must not invent those fields.

### Audit-only
- activation identity;
- consolidated snapshot identity;
- vault snapshot identities;
- source record identities;
- schema/engine versions.

## 4. Daily Capital Movements canonical source

### 4.1 Stream Capital ledger

**Classification: REUSE + customer query/projection EXTEND**

`IntelligenceStreamReadModel.read_messages(StreamMessageQuery(...))` already merges verified capital message tables and supports:
- category=`capital`;
- vault filter;
- symbol/timeframe filter;
- state/subtype filter;
- from/to time;
- cursor pagination;
- deterministic event-time ordering.

Accepted capital message kinds include:

1. **Capital Decision**
   - vault;
   - disposition;
   - symbol/timeframe;
   - event/source-as-of time;
   - starting budget;
   - exact reason codes;
   - event risk state;
   - immutable lineage.

2. **Capital Sizing**
   - vault;
   - fraction of vault;
   - canonical notional;
   - current cash;
   - current NAV;
   - exact reason codes.

3. **Capital Execution / Story**
   - action BUY / REDUCE / EXIT;
   - quantity;
   - reference price;
   - simulated fill price;
   - notional;
   - before/after cash;
   - before/after vault NAV;
   - before/after consolidated NAV;
   - fee/spread/slippage;
   - sell outcome/PnL where applicable;
   - exact R21/R22 lineage.

4. **Capital Lifecycle**
   - candidate;
   - accounting updated;
   - outcome;
   - before/after accounting;
   - realized-PnL delta / position before-after when exact.

### 4.2 R22

**Classification: REUSE lineage authority; no duplicate timeline query needed in D2**

R22 is the immutable transaction/decision authority behind accepted execution/bundle records.

Daily Capital Movements may rely on verified Stream Capital execution/lifecycle records because those messages already preserve the R22 bundle/intent/fill identities and R21 before/after snapshot identities.

FP1-D must not create a second R22 event ledger.

Trade-level deep reconstruction stays FP1-E Trade Passport.


### 4.3 Exact D2 read/query contract

**Frozen before D2 production code.**

Canonical reader:
`IntelligenceStreamReadModel(stream_ledger_path)`

Canonical query:
`StreamMessageQuery(category="capital", limit=..., vault=..., from_ms=..., to_ms=...)`

Rules:
- `primary_surface=False`; D2 is a dedicated Capital projection, not the primary-message suppression view;
- no default `state` filter; all accepted Capital subtypes may appear;
- no direct SQLite query is added in Final Product;
- no direct R22/R21 table scan is added for the timeline;
- `read_messages` verifies stored payload digest, canonical identity, schema/engine, read-only authority and `REAL_CAPITAL=0` before D2 sees a record;
- default ordering is newest-first by `event_at_ms` then `narrative_identity`;
- `vault`, `from_ms` and `to_ms` are delegated to the accepted Stream query semantics;
- R22/R21 remain lineage/accounting authorities; their identities are surfaced only in audit.

Verified message classes admitted by D2:
- `capital_eligible`, `capital_hold`, `capital_blocked`;
- `capital_sized`;
- `capital_executed`, `capital_reduced`, `capital_exited`;
- `capital_candidate`;
- `capital_accounting_updated`;
- `capital_outcome`.

Field precedence:
- action label comes only from exact `subtype` plus exact persisted `action` when the subtype requires it;
- customer text comes from persisted `text.capital_text`; no generated market claim is added;
- `source_as_of_ms` is exposed only when present in the accepted payload; execution/story records that do not persist it remain unavailable;
- decision starting budget is labelled budget, never executed notional;
- sizing notional/cash/NAV comes only from sizing payload;
- execution quantity/notional/fill/cost and before/after accounting come only from execution payload;
- accounting lifecycle before/after cash/NAV comes only from `capital_accounting_updated`;
- realized PnL / position before-after comes only from exact execution/outcome payload where present;
- absent optional numeric fields remain `None`, never zero-filled.

Customer action labels:
- `capital_eligible` -> **İşleme uygun bulundu**;
- `capital_hold` -> **Nakit korunuyor / işlem yapılmadı**;
- `capital_blocked` -> **İşlem engellendi**;
- `capital_sized` -> **Pozisyon boyutu belirlendi**;
- BUY execution -> **Pozisyon açıldı / artırıldı**;
- REDUCE execution -> **Pozisyon azaltıldı**;
- EXIT execution -> **Pozisyon kapatıldı**;
- `capital_candidate` -> **Aday sermaye değerlendirmesi**;
- `capital_accounting_updated` -> **Portföy hesabı güncellendi**;
- `capital_outcome` -> **İşlem sonucu kaydedildi**.


## 5. Daily Capital Movements customer semantics

The customer timeline is a projection, not a new ledger.

Suggested customer actions:
- `capital_decision_eligible` -> **İşleme uygun bulundu**
- `capital_decision_hold` / blocked -> **Nakit korunuyor / işlem yapılmadı**
- `capital_sized` -> **Pozisyon boyutu belirlendi**
- execution BUY -> **Pozisyon açıldı / artırıldı**
- REDUCE -> **Pozisyon azaltıldı**
- EXIT -> **Pozisyon kapatıldı**
- `capital_accounting_updated` -> **Portföy hesabı güncellendi**
- `capital_outcome` -> **İşlem sonucu kaydedildi**
- candidate -> **Aday sermaye değerlendirmesi**

Exact subtype/action must be mapped from persisted values only.

Customer fields:
- event time;
- source/as-of time;
- vault label;
- symbol/timeframe;
- action label;
- concise persisted Stream text;
- notional/quantity where exact;
- cash/NAV before-after where exact;
- costs where exact;
- realized-PnL delta where exact;
- outcome label where exact.

No unsupported field should be represented as zero.

Audit-only:
- narrative/story/source-event/stream-event identities;
- R22 bundle/intent/fill identities;
- R21 snapshot identities;
- allocator/selection/eligibility identities;
- raw reason codes/subtypes.

## 6. Epoch isolation rule

**Hard rule:**
- Portfolio Summary = Epoch 2 only.
- Daily Capital Movements = canonical Stream Capital messages bound to accepted current capital program.
- Legacy Epoch 1 / 100-USDT Mission Control does not merge into these views.
- No combined return, trade count, NAV, or timeline across epochs.

If the Epoch 2 DB is unavailable:
- Portfolio Summary returns explicit unavailable;
- it does not fall back to legacy Mission Control.

## 7. FP1-D implementation slicing

### FP1-D1 — Portfolio Summary

Implement first:
- optional `epoch2_path` on `FinalProductReadModel`;
- customer-safe `PortfolioSummaryView`;
- consolidated/vault/position projections;
- exact read-only R21 state;
- no R24 recomputation;
- no capital Stream query in the same patch.

### FP1-D2 — Daily Capital Movements

After D1 acceptance:
- query verified Stream Capital messages;
- bounded time window;
- optional vault filter;
- deterministic newest-first customer timeline;
- customer-safe action/amount/accounting projection;
- audit provenance optional.

## 8. FP1-D acceptance

### D1
1. missing Epoch 2 DB explicit and non-creating;
2. incomplete/corrupt R21 schema fails closed;
3. exactly Epoch 2 only;
4. consolidated/vault arithmetic comes from accepted snapshot values;
5. open positions count uses exact R21 positions only;
6. no max-drawdown claim from current drawdown;
7. unmeasured expectancy remains unavailable;
8. normal payload hides SHA/raw metrics enum/database vocabulary;
9. audit preserves exact identities;
10. canonical Epoch 2 DB bytes unchanged; missing DB is never initialized;
11. REAL_CAPITAL=0.

### D2
1. missing Stream DB explicit and non-creating;
2. category capital only;
3. time/vault filters reuse accepted query semantics;
4. deterministic ordering;
5. no duplicate event ledger;
6. no invented amount when field absent;
7. R22/R21 identities audit-only;
8. default payload hides raw subtype/reason/identity vocabulary;
9. Stream DB and sidecars unchanged;
10. REAL_CAPITAL=0.

All slices also require:
- focused pytest;
- Ruff;
- strict mypy;
- Product/Development non-mutation;
- project isolation;
- no RDP11 runtime mutation.

## 9. Exact next action

Implement **FP1-D2 only** in `final_product_read_model.py` plus focused tests:
- add customer-safe Daily Capital Movements view over the frozen `StreamMessageQuery(category="capital", ...)` contract;
- preserve exact optionality and audit lineage;
- do not edit `web.py`, frontend files, legacy Mission Control, R22/R21 writers or runtime/deploy configuration.

D1 Portfolio Summary is already mechanically accepted and must not be rebuilt.


## 10. FP1-D2 exact verified Stream Capital source contract — 2026-09-29 audit

This section supersedes the older generic D2 notes above for implementation detail.

### 10.1 Query authority

Use only:

`IntelligenceStreamReadModel.read_messages(StreamMessageQuery(...))`

with:
- `category="capital"`;
- bounded `from_ms` / `to_ms`;
- optional exact `vault`;
- bounded `limit`.

The accepted read model already merges and verifies:
- `stream_capital_messages`;
- `stream_capital_decision_messages`;
- `stream_capital_sizing_messages`;
- `stream_capital_lifecycle_messages`.

Ordering is already deterministic newest-first when `after` is absent:
- `event_at_ms DESC`;
- immutable narrative identity DESC as tie-breaker.

FP1-D2 must not re-query those tables directly and must not create a second sort key or confidence score.

### 10.2 Capital Decision verified payload

Exact fields available:
- narrative/source-event/stream-event/story identities;
- decision / allocator assessment / allocator candidate identities;
- vault id;
- disposition;
- asset/symbol/timeframe;
- event time and source-as-of time;
- starting budget;
- exact reason codes;
- event-risk state;
- capital reference identities;
- persisted Stream text.

Customer projection:
- eligible -> **İşleme uygun bulundu**
- hold / blocked / ineligible style disposition -> **Nakit korunuyor / işlem yapılmadı**
- amount fields not carried by the exact decision payload remain unavailable.

Audit-only:
- decision / allocator / source identities;
- raw disposition;
- reason codes.

### 10.3 Capital Sizing verified payload

Exact fields available:
- sizing event / selection / eligibility proof / allocator candidate identities;
- vault id;
- symbol/timeframe;
- event/source-as-of times;
- fraction of vault;
- canonical notional;
- current cash;
- current NAV;
- exact reason codes;
- persisted Stream text.

Customer action:
**Pozisyon boyutu belirlendi**

No fill/execution claim may be inferred from sizing.

### 10.4 Capital Execution / Story verified payload

Exact `StreamCapitalMessage` fields:
- action: `BUY`, `REDUCE`, `EXIT`;
- subtype is mechanically bound:
  - BUY -> `capital_executed`;
  - REDUCE -> `capital_reduced`;
  - EXIT -> `capital_exited`;
- quantity;
- reference price;
- simulated fill price;
- notional;
- cash before/after;
- vault NAV before/after;
- consolidated NAV before/after;
- fee/spread/slippage;
- sell outcome fields only for REDUCE/EXIT;
- exact R21/R22 intent/fill/bundle/snapshot lineage.

Customer action:
- BUY -> **Pozisyon açıldı / artırıldı**
- REDUCE -> **Pozisyon azaltıldı**
- EXIT -> **Pozisyon kapatıldı**

All execution amounts come directly from the verified Stream Capital record. No extra execution calculation is allowed in D2.

### 10.5 Capital Lifecycle verified payload

Exact subtypes:
- `capital_candidate`;
- `capital_accounting_updated`;
- `capital_outcome`.

Candidate:
- vault is absent;
- allocator candidate/assessment lineage exact;
- no trade/accounting amounts may be invented.

Customer action:
**Aday sermaye değerlendirmesi**

Accounting updated:
- vault/bundle/forecast/proof/decision-context exact;
- action exact;
- cash before/after;
- vault NAV before/after;
- consolidated NAV before/after.

Customer action:
**Portföy hesabı güncellendi**

Outcome:
- REDUCE/EXIT only;
- financial outcome exact;
- realized-PnL delta exact;
- position quantity before/after exact.

Customer action:
**İşlem sonucu kaydedildi**

### 10.6 D2 customer contract

Each item may expose only when exact:
- event time;
- source-as-of time;
- freshness label;
- vault label;
- symbol/timeframe;
- action label;
- persisted customer Stream headline/detail;
- quantity;
- notional;
- fraction of vault;
- cash before/after or current cash;
- vault NAV before/after or current NAV;
- consolidated NAV before/after;
- fee/spread/slippage;
- realized-PnL delta;
- outcome label.

No missing numeric value is rendered as zero.

Audit-only:
- narrative/story/source-event/stream-event;
- R21/R22 bundle/intent/fill/snapshot;
- allocator/decision/sizing/outcome identities;
- raw subtype/action/disposition/reason codes.

### 10.7 Empty / missing semantics

- missing Stream DB -> **Sermaye hareketleri verisi kullanılamıyor**, and the file must not be created;
- valid Stream DB with no capital messages in the requested interval/filter -> **Bu aralıkta sermaye hareketi yok**;
- this empty state must not be interpreted as "cash unchanged" unless a canonical capital message says so.

### 10.8 D2 implementation authorization

After this audit:
- **REUSE**: Stream capital tables, verification, query/filter/order, persisted customer text, R21/R22 lineage;
- **EXTEND**: one customer timeline projection;
- **BUILD**: customer dataclasses + field mapping only;
- **EXPLICITLY_UNAVAILABLE**: any amount/outcome not present in the exact source record.

Exact next action:
Append D2 implementation-start checkpoint if not already present, then implement only the final-product Capital Movements projection and focused tests. No route/frontend/deploy.
