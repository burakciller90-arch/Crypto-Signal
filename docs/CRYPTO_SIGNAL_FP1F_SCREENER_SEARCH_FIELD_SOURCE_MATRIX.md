# Crypto Signal — FP1-F Screener + Federated Global Search Field-Source Matrix

Status: **ACCEPTED / REVIEW READY**
Date: 2026-09-29
Base main: `ef408ee105e1f226b199b7b1a185a1fdb990159f`
Active branch: `fp1f/screener-federated-search`
Safety: **REAL_CAPITAL=0**
Persistent search index: **NOT AUTHORIZED**

## 1. Purpose

FP1-F closes the FP1 read-model layer with:
1. customer-safe Screener rows;
2. one bounded federated global-search contract.

It must not:
- create a new market/evidence/search truth database;
- rebuild Stream full-text/history/SSE;
- reinterpret legacy latest-signal radar as current market truth;
- query canonical DBs with duplicate business logic;
- fabricate unsupported proof/event/trade matches;
- mutate Product/Development/RDP11 runtime.

## 2. Screener source contract

### 2.1 Current truth authority

Use existing FP1-A:
`FinalProductReadModel.market_pulse(...)`

Reason:
- Market Pulse already resolves current Stream system-view/family truth;
- it exposes freshness, stance, support/opposition, evidence coverage, event risk, provider quality, trigger/target/invalidation, contradiction and five-family customer rows;
- it is already frontend-safe and accepted.

FP1-F Screener is therefore **EXTEND presentation**, not a second market engine.

### 2.2 Legacy radar classification

`DashboardReader.market_radar()` is **REUSE for historical/latest-signal navigation only**.

Its semantics are:
- latest frozen signal per exchange / market type / symbol / timeframe;
- not current cross-source family state;
- not sufficient authority for a final current screener row.

FP1-F must not blend radar age/history into Market Pulse as if it were fresh current truth.

### 2.3 Screener row

Customer row fields:
- symbol;
- timeframe;
- updated-at;
- freshness label;
- stance label;
- support score;
- opposition score;
- evidence coverage;
- event-risk label;
- provider-quality label;
- main contradiction;
- summary;
- compact family state labels.

No new ranking/confidence score is authorized.
Default ordering is deterministic by symbol/timeframe.

Audit may retain the current Market Pulse narrative identity.

## 3. Federated global-search contract

Search is **read-only federation**, not persistence.

### 3.1 Stream search — REUSE

Use:
`IntelligenceStreamReadModel.read_messages(StreamMessageQuery(text=query, ...))`

Capabilities reused:
- full-text customer prose;
- symbol/timeframe/category/state filters;
- deterministic pagination/order;
- capital decision/sizing/execution/lifecycle inclusion.

If query looks like an exact configured symbol, an additional exact `symbol=query` Stream query may be used and deduped by narrative identity.

Exact 64-hex narrative lookup may use:
`read_message(narrative_identity)`.

No Stream message/history/search identity changes.

### 3.2 Asset result — REUSE Screener

The provided configured Screener symbol set is filtered by query.
Exact symbol match returns an **Asset** search result backed by accepted Screener/Market Pulse truth.

No unsupported market universe is invented.

### 3.3 Event search — REUSE Event Rail

Use existing:
`FinalProductReadModel.event_rail(..., include_audit=True)`

Search only inside the explicit caller-provided event window.
Match customer fields:
- title;
- category label;
- provider;
- affected assets;
- exact event identity when the event is inside the verified window.

No unbounded event-DB scan is added.

### 3.4 Trade search — REUSE Stream + Trade Passport

Text/symbol trade discovery:
- accepted Stream capital records may yield trade-capital matches;
- if a Stream capital execution record carries an exact R22 bundle identity, the search result is classified as **Trade** and audit binds that bundle.

Exact 64-hex bundle lookup:
`trade_passport(bundle_identity=query)`.

Unknown identity remains no match.

No R22 history re-index is created in FP1-F.

### 3.5 Proof search — REUSE supported Decision Evidence APIs

When Decision Evidence source is configured and query is exact 64-hex:
1. try `read_issuance_for_signal(query)`;
2. if absent, try `read_proof_for_forecast(query)`.

A verified match yields a **Proof** result with human symbol/timeframe/thesis context and audit exact identities.

Direct lookup by raw proof identity is **EXPLICITLY_UNAVAILABLE in FP1-F** because the accepted ledger has no canonical `read_proof_by_identity` API.
FP1-F must not bypass that contract with direct SQL.

### 3.6 Exact event identity limitation

Exact event identity is searchable only when that event falls inside the caller-provided verified Event Rail window.
No unbounded exact event lookup API exists in the accepted Product reader.

## 4. Result taxonomy

Customer kinds:
- **Varlık**
- **Akış**
- **Olay**
- **İşlem**
- **Kanıt**

Each result exposes:
- kind label;
- title;
- plain-language summary;
- optional symbol;
- optional timestamp;
- source label.

Audit-only:
- Stream narrative identity;
- Event identity;
- R22 bundle identity;
- forecast/proof/signal identities;
- raw category/subtype where relevant.

## 5. Deterministic ordering

No relevance ML/ranking score.

Priority:
1. exact identity match;
2. exact configured asset-symbol match;
3. Stream text/symbol match;
4. Event Rail text/asset/provider match.

Within the same priority:
- newest timestamp first where a timestamp exists;
- stable kind/title/identity tie-break.

Duplicates are removed by source-kind + exact source identity.

## 6. Missing-source semantics

- missing Stream DB: screener may be unavailable; Stream search contributes zero matches and coverage label says unavailable;
- missing Event Source DB: events contribute zero matches and coverage says unavailable;
- missing Epoch 2/R22 DB: exact trade lookup contributes no match;
- missing Decision Evidence DB: proof lookup contributes no match;
- missing canonical source never becomes synthetic placeholder result.

Global search may still return results from healthy sources when another source is unavailable.

## 7. Acceptance

FP1-F PASS requires:
1. Screener reuses Market Pulse only;
2. legacy radar is not treated as current truth;
3. no new search/index DB;
4. Stream full-text identity/order unchanged;
5. configured asset exact match supported;
6. bounded event search supported;
7. Stream capital trade classification supported where bundle lineage exists;
8. exact R22 bundle lookup supported;
9. Decision Evidence signal/forecast exact lookup supported;
10. direct proof-id limitation explicit;
11. deterministic dedupe/order;
12. customer payload hides SHA/raw enum/database vocabulary by default;
13. audit preserves exact identities;
14. missing sources remain explicit in source coverage;
15. focused pytest PASS;
16. Ruff PASS;
17. strict mypy PASS;
18. Product/Development non-mutation PASS;
19. project isolation PASS;
20. REAL_CAPITAL=0.

## 8. Exact next action

Implement `ScreenerRow/View`, `GlobalSearchItem/View`, `screener(...)` and `global_search(...)` inside `final_product_read_model.py` plus focused tests.

Do not edit Product routes/frontend, Stream persistence/query semantics, Event Source persistence, R21/R22 writers, Decision Evidence writers, runtime or deploy configuration.


## 9. UID504 acceptance

Status: **PASS**

Accepted exact-head:
- head SHA: `e1137086c5044f6e52b50950073947d7b2c146b3`;
- run: `36583882210`;
- job: `109458903547`;
- conclusion: **SUCCESS**.

Mechanical markers:
- `MESSAGE_INTELLIGENCE_MI1_EXACT_SOURCE_PASS=YES`;
- focused/regression pytest reached **100% PASS**;
- Ruff: **All checks passed!**;
- strict mypy: **Success: no issues found in 5 source files**;
- `MESSAGE_INTELLIGENCE_MI1_NON_MUTATING_PASS=YES`;
- `PROJECT_ISOLATION_PASS=YES`;
- `REAL_CAPITAL=0`.

Cleanup:
- temporary acceptance workflow restored in `09200a11130de9b24c57d034ea3e5bfab1460f73`;
- branch workflow blob equals current-main workflow blob `394051a78c665d84cf78830cedc8799a13474baa`.

Accepted FP1-F result:
- Screener reuses accepted Market Pulse current truth;
- global search is read-only federation with no persistent search index;
- Stream full-text/history identity remains unchanged;
- bounded verified Event Rail search works;
- exact R22 bundle opens Trade Passport;
- exact frozen signal and Decision Evidence signal/forecast lookup work;
- raw proof-id direct lookup remains explicitly unavailable;
- deterministic ordering/dedupe is tested;
- missing sources remain explicit;
- customer payload hides exact identities by default;
- canonical sources remain unmodified.
