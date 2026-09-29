# Crypto Signal — FP1 Human Read-Model Capability Matrix

Status: **FP1-A/B/C/D/E/F ACCEPTED / FP1 PROGRAM REVIEW READY**
Date: 2026-09-29
Authority: `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
Active mechanical gate: **FP0 / RDP11 soak remains ACTIVE / NOT PASS**
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**

## 1. Purpose

FP1 does not create a second evidence engine.

Its job is to compose already accepted immutable/read-only truth into a final customer-facing contract that:
- answers before exposing implementation detail;
- preserves exact source identity internally;
- never requires SHA256/internal enums/database vocabulary for normal comprehension;
- never creates a divergent Product truth database;
- fails closed on missing/stale/unsupported evidence;
- remains safe to develop while RDP11 runs because it is read-only and is not deployed into the soaked Product/Development target.

This file is the mandatory duplicate-work result required before FP1 implementation.

## 2. Classification legend

- **REUSE** — accepted capability already exists and should be consumed directly.
- **EXTEND** — canonical truth/read API exists, but a new customer projection or composition is required.
- **BUILD** — final product contract is genuinely absent; build only a read-only/product layer over accepted truth.
- **EXPLICITLY_UNAVAILABLE** — do not fabricate a field when its canonical source does not exist.

## 3. Existing canonical Product surfaces

Current `src/crypto_signal/product/web.py` already exposes:

- `GET /api/command-center`
- `GET /api/market-radar`
- `GET /api/navigation`
- `GET /api/assets/{symbol}/{timeframe}`
- `GET /api/signals`
- `GET /api/archive/proof-wall`
- `GET /api/signals/{signal_freeze_identity}`
- `GET /api/decision-proof/{signal_freeze_identity}`
- `GET /api/decision-proof/forecast/{forecast_identity}`
- `GET /api/stream/messages`
- `GET /api/stream/live`
- `GET /api/stream/messages/{narrative_identity}/detail`
- `GET /api/stream/messages/{narrative_identity}/evidence`
- `GET /api/stream/messages/{narrative_identity}/visual-proof`
- `GET /api/event-source-runtime/status`
- `GET /api/alerts`
- `GET /api/paper/epoch-contract`
- `GET /api/paper/epoch2-state`
- `GET /api/paper/mission-control`
- `GET /api/performance`

These are reusable source/read surfaces. They are not, by themselves, the FP1 final customer contract.

## 4. FP1 requirement matrix

| FP1 requirement | Classification | Existing exact source | Final gap |
|---|---|---|---|
| Market Pulse | **EXTEND** | `DashboardReader.command_center`, `market_radar`; Stream system view/family state | Existing Command Center is signal-freeze aggregate history, not a current cross-source market pulse with family/event/capital context |
| Attention Situations | **BUILD over REUSE** | Stream material messages, system-view messages, signal state/proof | No final top-3–5 material situation read model with deterministic ranking and explicit risk/why-now |
| Signal/workspace summary | **EXTEND** | `DashboardReader.signal_detail`; Stream `read_message_detail`; Decision Proof; exact evidence/visual proof | Needs one human contract that joins current view, trigger/invalidation/targets, contradiction, event/capital consequence without exposing raw identities |
| Five-family customer summaries | **REUSE + EXTEND presentation** | `IntelligenceStreamSystemViewRuntime`; MI3/MI4 family rows; `IntelligenceStreamExactEvidenceReadModel` | Exact family truth exists; final customer status vocabulary/source-time/freshness projection must hide internal state enums/identity plumbing |
| Event Rail | **BUILD over REUSE** | append-only `EventSourceRuntimeStore` structured events/news/calendar coverage; RDP8 Event Risk | Product currently exposes runtime health only; no read-only upcoming-event/customer Event Rail query |
| Portfolio summary | **EXTEND** | canonical `read_epoch2_state_read_only`; R24 paper metrics; R22 tape | Need one current-program customer projection. Do **not** treat legacy `/api/paper/mission-control` as canonical final portfolio |
| Daily capital movements | **REUSE + EXTEND query** | Stream capital decision/sizing/execution/lifecycle records; `StreamMessageQuery` category/vault/time filters | Need compact customer daily timeline projection; do not create a duplicate capital event ledger |
| Trade Passport | **EXTEND** | `R22Epoch2AtomicTape.read_trade_history`, `read_bundle_story_context`, R21 before/after accounting, S11 outcomes, Decision Proof/RDP10 evidence | Backend lineage exists; no customer-facing Trade Passport read model/API |
| Screener rows | **EXTEND** | `DashboardReader.market_radar`, current system-view/family snapshots, provider truth | Existing radar is latest signal per venue/timeframe, not final cross-family attention/screener row |
| Global search index | **BUILD query layer** | Stream full-text/filter/deep-link; signal archive; structured event DB; R22 history; proof archive | No one query contract searches assets + events + signals + paper trades + proof. Prefer federated read-only query first; do not create a new truth store |
| Customer-safe labels | **BUILD shared projection vocabulary** | accepted deterministic source states | Existing APIs expose enums/reason codes/identities. Need stable Turkish customer labels + machine state separately |
| Audit/debug provenance | **REUSE** | exact SHA/source identities everywhere | Keep exact provenance available in debug/audit fields/routes; do not put it on default customer layer |

## 5. Important duplicate findings

### 5.1 Do not rebuild Stream search/history/SSE

`IntelligenceStreamReadModel` already provides:
- immutable message lookup;
- message detail;
- full-text search;
- filters for symbol/timeframe/category/importance/vault/state/evidence domain/date;
- cursor pagination;
- capital decision/sizing/lifecycle inclusion;
- SSE transport through the existing Product API.

FP1 must reuse this infrastructure.

### 5.2 Do not rebuild five-family evidence resolution

`IntelligenceStreamExactEvidenceReadModel` already resolves exact persisted family proof and explicitly distinguishes exact, identity-only and unavailable states.

It already understands persisted domains such as:
- Geometry;
- frozen chart;
- order book;
- public trades;
- Liquidity dynamics/structure/sweep;
- Order Flow microstructure/temporal/absorption/divergence;
- Derivatives/options/liquidations where accepted;
- On-chain/stablecoin where accepted;
- Event/context records.

FP1 only adds human-facing wording and composition. It does not reinterpret the evidence.

### 5.3 Do not rebuild canonical capital accounting

Canonical final-product capital truth comes from:
- `read_epoch2_state_read_only`;
- R21 Epoch 2 accounting snapshots;
- `R22Epoch2AtomicTape`;
- S11 canonical capital outcome evidence;
- R24 performance/trust calculations;
- accepted Stream Capital decision/sizing/execution/lifecycle messages.

### 5.4 Legacy paper Mission Control is not the final portfolio source

`GET /api/paper/mission-control` composes the older paper runtime ledger configured through `selected_paper_path`.

It is valuable historical/reusable code for portfolio exposure, candidates, cost previews and benchmark ideas, but final Portfolio/Autopilot work must not silently merge this legacy program with canonical Epoch 2.

Final FP1 portfolio reads must be epoch-labelled and prefer the canonical current-program contract.

### 5.5 Event persistence exists; Event Rail read model does not

`EventSourceRuntimeStore` already persists immutable:
- raw source payloads;
- calendar coverage;
- structured event observations;
- news event observations;
- fetch observations.

`StructuredEventObservation` already carries:
- title;
- category;
- scheduled time;
- affected assets;
- source provider;
- source quality;
- source timestamp;
- ingestion timestamp.

The missing layer is a read-only customer query/projection for upcoming/recent events with point-in-time/freshness semantics.

### 5.6 Trade Passport is not a new accounting system

`R22Epoch2AtomicTape.read_trade_history(vault, symbol)` already returns verified intent/fill pairs.

`read_bundle_story_context(bundle_identity)` already reconstructs:
- exact intent;
- fill;
- outcome;
- before/after target-vault accounting;
- before/after consolidated accounting;
- immutable lineage.

Trade Passport is therefore an **EXTEND** read-model problem, not a new ledger.

## 6. Human-facing contract rules

Every FP1 customer projection uses two conceptual layers:

### 6.1 Customer layer

Allowed examples:
- `Doğrulanmış veri`
- `Veri eksik`
- `Güncel değil`
- `Karışık`
- `Destekliyor`
- `Çelişiyor`
- `Tetik bekleniyor`
- `İşlem yapılmadı`
- `Fill kanıtlanamadı`

Customer layer may expose:
- symbol / asset;
- timeframe;
- plain-language current state;
- direction/support semantic;
- source/provider label;
- source time;
- freshness;
- uncertainty;
- trigger;
- invalidation;
- targets;
- main contradiction;
- event risk;
- capital consequence;
- execution/outcome state.

### 6.2 Audit layer

May preserve:
- immutable identities;
- source record identities;
- schema/engine versions;
- exact reason codes;
- raw enum values;
- database lineage.

Audit metadata must not be required for normal product comprehension.

## 7. Proposed FP1 read-model boundary

Create one new product-only module:

`src/crypto_signal/product/final_product_read_model.py`

It must:
- open accepted sources read-only only;
- never initialize a missing canonical DB;
- never append/update/delete canonical records;
- compose canonical source modules instead of duplicating their algorithms;
- return deterministic dataclasses / canonical JSON;
- keep audit provenance nested/optional;
- provide explicit unavailable/stale states;
- remain independent of frontend rendering.

Initial bounded functions:

1. `market_pulse(...)`
2. `attention_situations(...)`
3. `workspace_summary(...)`
4. `family_summary(...)`
5. `event_rail(...)`
6. `portfolio_summary(...)`
7. `capital_movements(...)`
8. `trade_passport(...)`
9. `screener(...)`
10. `global_search(...)`

Do not implement all ten in one unreviewable slice.

## 8. FP1 implementation slicing

### FP1-A — shared customer contract + Market Pulse

Build:
- customer availability/freshness vocabulary;
- audit provenance envelope;
- `MarketPulseView`;
- deterministic current system-view selection for configured assets;
- no Product route/deploy yet.

### FP1-B — Attention + Workspace + Five-Family summary

Reuse:
- system view;
- signal detail;
- exact evidence;
- Decision Proof.

Build only projection/composition.

### FP1-C — Event Rail

Build a read-only event query adapter over the accepted event-source runtime DB.

No new event persistence.

### FP1-D — Portfolio + capital movements

Read canonical Epoch 2/R22/R24/Stream Capital only.

Never merge Epoch 1 and Epoch 2.

### FP1-E — Trade Passport

Compose R22/R21/S11/Decision Proof/RDP10 lineage into a customer projection.

### FP1-F — Screener + federated global search contract

Reuse radar/Stream filters/archive/event/R22 readers.

A persistent search index is not authorized unless query-performance evidence later proves one necessary.

## 9. FP1 acceptance gates

FP1 cannot PASS until:

1. each requirement has a REUSE/EXTEND/BUILD/EXPLICITLY_UNAVAILABLE classification;
2. no final Product field invents unavailable canonical truth;
3. customer payloads do not require SHA/internal enum/database vocabulary;
4. audit payload preserves exact provenance;
5. read models are deterministic and read-only;
6. missing source DBs return explicit unavailable state and are never initialized by reads;
7. Epoch 1 and Epoch 2 remain strictly separate;
8. Stream message/history/search identity remains unchanged;
9. no new evidence/calculation engine is introduced in Product;
10. no RDP11 observer/soak/runtime mutation occurs;
11. focused tests pass;
12. canonical checkout non-mutation is proven;
13. REAL_CAPITAL=0.

## 10. Current exact progress and next action

Accepted/merged:
- **FP1-A** — Market Pulse customer read model merged via PR #1671;
- **FP1-B** — Attention Situations, Workspace Summary and Five-Family Summary merged via PR #1672.

Accepted on isolated review branch:
- **FP1-C1** — point-in-time read-only structured calendar query adapter PASS on UID504 run `36565167503`;
- **FP1-C2** — customer-safe Event Rail projection PASS on UID504 run `36565945747`;
- branch: `fp1c/event-rail-read-model`;
- no Product/Development deploy and no RDP11 soak/runtime mutation.

Exact next action:
1. review and merge FP1-C only if the final diff contains no temporary workflow/runtime/deploy changes;
2. bootstrap again from the new main;
3. start **FP1-D — Portfolio + capital movements** with a fresh duplicate audit and task-start checkpoint;
4. use canonical Epoch 2 / R22 / R24 / Stream Capital only and keep Epoch 1 strictly separate.

Do not rebuild FP1-A, FP1-B or accepted FP1-C source/query semantics.


## 10.1 Progress update — 2026-09-29

- FP1-A merged.
- FP1-B merged.
- FP1-C merged/accepted.
- FP1-D Portfolio Summary + Daily Capital Movements merged via PR #1676 at main `5490bc184eb51f3507ede93bc72b488ea38cd5dd`.
- Current slice: **FP1-E — Trade Passport**.
- Duplicate check: no open FP1-E PR and no existing `fp1e/*` branch at task start.
- FP1-F remains later; do not start Screener/global search until FP1-E source contract is accepted or explicitly blocked.

Exact next action:
Audit and freeze the Trade Passport field/source contract over canonical R22/R21/RDP10 truth before implementation.


## 10.2 Progress update — FP1-F

- FP1-D merged via PR #1676.
- FP1-E Trade Passport merged via PR #1677 at main `ef408ee105e1f226b199b7b1a185a1fdb990159f`.
- Current slice: **FP1-F — Screener + federated global search contract**.
- Persistent search index remains unauthorized.
- Do not rebuild Stream search/history/SSE.
- Do not use legacy radar semantics as final current-truth screener rows without source audit.

Exact next action:
Audit and freeze the screener/federated-query source contract before implementation.


## 10.3 FP1 completion update — 2026-09-29

- FP1-A — Market Pulse: MERGED.
- FP1-B — Attention + Workspace + Five-Family: MERGED.
- FP1-C — Event Rail: MERGED.
- FP1-D — Portfolio Summary + Daily Capital Movements: MERGED via PR #1676.
- FP1-E — Trade Passport: MERGED via PR #1677.
- FP1-F — Screener + federated Global Search: UID504 ACCEPTED / REVIEW READY.
- Persistent search index: NOT BUILT / NOT REQUIRED.
- REAL_CAPITAL=0.
- FP0/RDP11 soak remains independently ACTIVE / NOT PASS.

Exact next action:
Review and merge FP1-F only if the diff remains source/read-model/test/docs-only and PR checks pass. After FP1-F merge, mark FP1 mechanically complete and proceed to the next canonical Final Product roadmap gate allowed during FP0 soak.
