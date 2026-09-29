# Crypto Signal — FP1-C Event Rail Field / Source Matrix

Status: **AUDIT COMPLETE / IMPLEMENTATION NOT YET STARTED**
Date: 2026-09-29
Base main: `bb083c062154dd804e087777310c43d4710d29c0`
Active branch: `fp1c/event-rail-read-model`
Authority:
- `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
- `docs/CRYPTO_SIGNAL_FP1_HUMAN_READ_MODEL_CAPABILITY_MATRIX.md`
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**

## 1. Purpose

FP1-C builds a customer Event Rail by querying already-persisted Event Source truth read-only.

It does not:
- fetch new calendar/news data;
- create a second event database;
- calculate a new Event Risk score;
- infer price direction from events;
- mix scheduled calendar events with news observations as if they had the same temporal meaning;
- backfill historical event data;
- add a Product route or frontend in this slice.

## 2. Canonical persistence source

**REUSE**

`EventSourceRuntimeStore` persists append-only:
- exact raw source payloads;
- calendar coverage observations;
- structured scheduled event observations;
- news event observations;
- fetch observations.

Canonical schema:
`event-source-runtime-v1/2`

Every persisted normalized observation has immutable identity lineage. UPDATE/DELETE are blocked by SQLite triggers.

## 3. Product-safe read boundary

**REUSE + EXTEND**

`read_event_source_runtime_truth(path, observed_at_ms=...)` already proves the safe Product read pattern:

1. missing DB fails without creating it;
2. any non-empty SQLite WAL fails closed as uncheckpointed evidence;
3. DB bytes are copied into an in-memory detached SQLite database;
4. `PRAGMA query_only=ON`;
5. `PRAGMA quick_check` must pass;
6. required schema/tables are verified;
7. persisted payload identities are recomputed and verified;
8. raw payload lineage is hash-verified;
9. calendar coverage/item provider lineage is verified;
10. latest fetches are point-in-time: `fetched_at_ms <= observed_at_ms`;
11. runtime remains `PERSISTED_EVIDENCE_ONLY`; online/process state is not asserted;
12. REAL_CAPITAL=0.

FP1-C should extend this Product-safe detached read boundary rather than open the canonical event DB with a normal writable SQLite connection.

## 4. Scheduled Event Rail source

### 4.1 Structured event

**REUSE**

`StructuredEventObservation` provides exact:
- `event_identity`;
- provider event id;
- title;
- category;
- scheduled time;
- affected assets;
- source provider;
- source quality;
- source type;
- source timestamp;
- ingestion timestamp;
- adapter version.

Point-in-time eligibility:
- `ingested_at_ms <= observed_at_ms`;
- source timestamp must already be valid by the observation time;
- an observation ingested later must not rewrite an earlier Event Rail.

### 4.2 Calendar coverage

**REUSE**

`EventCalendarCoverage` provides exact:
- coverage start;
- coverage end;
- covered categories;
- provider;
- source quality;
- source type;
- observed time;
- adapter version;
- immutable coverage identity.

Coverage is source-scoped only.

A customer-facing claim that an interval contains “no scheduled events” is allowed only when a verified point-in-time calendar coverage observation:
- was observed by `observed_at_ms`;
- covers the requested time window;
- covers the requested category set;
- belongs to a calendar provider whose point-in-time latest fetch is successful and references that exact coverage.

If this cannot be proven, empty results must be labelled **coverage unavailable / incomplete**, not “no event.”

## 5. News scope decision

### 5.1 News observations

**REUSE but EXCLUDED FROM FP1-C SCHEDULED RAIL**

`NewsEventObservation` has:
- publication time, not scheduled time;
- event cluster key;
- extraction method/version;
- relevance confidence;
- source/provider lineage.

News evidence uses a different accepted intelligence policy:
- clusters observations;
- can distinguish single-source / multi-source / provider disagreement;
- explicitly states news context is not directional price truth.

Therefore FP1-C will **not** insert news rows into the scheduled Event Rail.

Reason:
- a published article is not an upcoming scheduled event;
- news has no calendar coverage contract;
- mixing both would make ordering/empty-state/coverage semantics misleading.

News remains reusable for a later separate Event Center “recent news events” surface.

## 6. RDP8 Event Risk boundary

**REUSE / DO NOT REIMPLEMENT**

Existing Event Risk logic already owns:
- pre-event caution windows;
- event-block windows;
- post-event stabilization windows;
- required-category coverage policy;
- stale/unverified/incomplete coverage degradation;
- asset/global relevance;
- nearest-event selection.

Existing tests explicitly establish:
- Event Risk is context/veto, not a directional signal;
- CLEAR requires complete coverage;
- missing/future/stale/incomplete/unverified coverage degrades fail-closed;
- future/late-ingested evidence cannot rewrite historical state.

FP1-C Event Rail must not copy these risk-window rules into Product.

Event Rail may expose:
- schedule relationship such as upcoming/recent;
- exact source/coverage/freshness state.

It must not independently label an event “block,” “safe,” “bullish,” “bearish” or calculate risk severity.

## 7. Event Rail query contract

**BUILD query/composition over REUSE truth**

Proposed Product-safe adapter:
`read_event_source_calendar_rail(...)`

Inputs:
- event source runtime path;
- `observed_at_ms`;
- `window_start_ms`;
- `window_end_ms`;
- optional exact asset filter;
- optional category filter;
- bounded limit.

Rules:
- `window_start_ms <= window_end_ms`;
- only structured events whose `scheduled_at_ms` is inside the requested window;
- only rows with `ingested_at_ms <= observed_at_ms`;
- asset filter matches:
  - event `affected_assets` contains requested asset; or
  - empty `affected_assets` means global event;
- category filter is exact;
- deterministic ordering:
  1. `scheduled_at_ms` ascending;
  2. immutable `event_identity` ascending;
- limit is presentation-only and never alters coverage truth.

No predictive/materiality score is introduced.

## 8. Customer Event Rail fields

| Customer field | Exact source | Classification |
|---|---|---|
| title | StructuredEventObservation | REUSE |
| category label | EventCategory | EXTEND label only |
| scheduled_at_ms | StructuredEventObservation | REUSE |
| temporal label | scheduled time vs observed time | BUILD deterministic presentation |
| affected assets | StructuredEventObservation | REUSE |
| scope label | empty assets = global; otherwise asset-scoped | EXTEND label |
| source provider | StructuredEventObservation | REUSE |
| source quality label | EventSourceQuality | EXTEND label |
| source timestamp | StructuredEventObservation | REUSE |
| ingested timestamp | StructuredEventObservation | audit/default source metadata as needed |
| freshness label | source/coverage age vs configured display threshold | EXTEND presentation only |
| coverage label | verified EventCalendarCoverage + latest successful fetch | BUILD composition |
| coverage window | exact coverage | REUSE |
| event identity | exact persisted identity | AUDIT ONLY |
| coverage identity | exact persisted identity | AUDIT ONLY |
| adapter/source enum | exact persisted source | AUDIT ONLY unless human label required |

## 9. Customer labels

Source quality:
- official -> **Resmî kaynak**
- primary_provider -> **Birincil sağlayıcı**
- secondary_aggregator -> **İkincil toplayıcı**
- unverified -> **Doğrulanmamış kaynak**

Temporal:
- scheduled time > observed time -> **Yaklaşan olay**
- scheduled time == observed time -> **Şimdi**
- scheduled time < observed time -> **Yakın geçmiş olayı**

This is temporal description only; it is not risk/severity.

Coverage:
- exact requested window/categories covered by a successful point-in-time calendar fetch -> **Takvim kapsamı doğrulandı**
- some query requirements not covered -> **Takvim kapsamı eksik**
- no usable point-in-time calendar coverage -> **Takvim kapsamı kullanılamıyor**

Empty rail:
- covered + no rows -> **Bu kapsamda planlı olay yok**
- uncovered + no rows -> **Planlı olay verisi doğrulanamadı**

## 10. Freshness rule

FP1-C may label source/coverage age for customer comprehension, but must not invent the RDP8 risk-policy stale threshold.

Use a Product display threshold supplied to the read model (default may be a bounded product freshness duration), solely for:
- **Güncel kaynak**
- **Kaynak güncel değil**

The threshold does not change Event Risk state and is not a trading signal.

## 11. Implementation slicing

### FP1-C1 — Product-safe Event Source query adapter

Extend `src/crypto_signal/product/event_source_runtime.py`:
- add immutable dataclass(es) for verified calendar coverage/event query truth;
- reuse detached SQLite verification boundary;
- point-in-time coverage/event selection;
- no canonical DB sidecars/writes.

### FP1-C2 — Final Product Event Rail projection

Extend `src/crypto_signal/product/final_product_read_model.py`:
- optional `event_source_runtime_path`;
- `event_rail(...)`;
- customer-safe labels;
- audit-only identities;
- no news rows;
- no event-risk calculation.

Focused tests:
- `tests/test_event_source_product.py`
- `tests/test_final_product_read_model.py`

## 12. Acceptance

Required:
1. missing DB is explicit and non-creating;
2. non-empty WAL fails closed;
3. DB/schema/payload identities are verified before query truth is trusted;
4. event ingested after `observed_at_ms` is excluded;
5. point-in-time future coverage observation is excluded;
6. empty covered interval is distinct from uncovered interval;
7. category filter is exact;
8. asset filter includes exact asset + global events only;
9. news observations never appear in scheduled Event Rail;
10. deterministic ordering and bounded limit;
11. no Event Risk window/scoring duplication;
12. no directional claim;
13. default customer payload hides SHA/raw enums/database vocabulary;
14. audit preserves event/coverage identities;
15. source DB bytes and sidecar state remain unchanged;
16. Product/Development non-mutation;
17. project isolation;
18. RDP11 untouched;
19. REAL_CAPITAL=0.

## 13. Exact next action

Append FP1-C1 implementation-start checkpoint. Implement the Product-safe calendar query adapter first and accept it before adding the final customer Event Rail projection.
