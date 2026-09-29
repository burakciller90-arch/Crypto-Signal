# Crypto Signal — FP1-B Attention / Workspace / Five-Family Field-Source Matrix

Status: **AUDIT COMPLETE / IMPLEMENTATION NOT YET STARTED**
Date: 2026-09-29
Base main: `a67f7192dd4b6a36a33d7aacf2b7e304cafdf509`
Authority:
- `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
- `docs/CRYPTO_SIGNAL_FP1_HUMAN_READ_MODEL_CAPABILITY_MATRIX.md`
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**

## 1. FP1-B purpose

FP1-B composes accepted Product/Stream truth into three customer contracts:

1. **Attention Situations**
2. **Workspace Summary**
3. **Five-Family Summary**

It does not:
- create a new materiality score;
- recalculate confluence;
- reinterpret evidence;
- create a second Stream/search/evidence database;
- mutate canonical ledgers;
- deploy Product/Development during RDP11 soak.

## 2. Attention Situations

### 2.1 Canonical materiality source

**REUSE**

For canonical Stream narrative messages:

`StreamMessageInput` already freezes:
- `category`;
- `subtype`;
- `importance`;
- `materiality`;
- `publication_disposition`;
- materiality decision/policy identities;
- symbol/timeframe/event/source-as-of;
- exact evidence/proof/capital reference identities;
- search metadata.

`StreamMaterialityPolicy` already maps accepted source events to:
- `materiality=MATERIAL`;
- `publication_disposition=PUBLISH`;
- deterministic reason codes.

Known material publish rules include:
- forecast issuance;
- forecast resolution;
- geometry material change;
- trigger transition;
- liquidity material change;
- order-flow material change;
- derivatives material change;
- on-chain material change;
- event-risk block/change/recovery;
- provider-quality degraded/recovered.

FP1-B must use this existing decision. It must not invent a competing "attention score."

### 2.2 System View attention source

**REUSE + PRESENTATION EXTEND**

Persisted `stream_system_view_messages` do not carry a `StreamMessageInput` materiality decision.

They do carry:
- `importance`;
- `state`;
- `symbol`;
- `timeframe`;
- `event_at_ms`;
- deterministic customer text;
- stance/support/opposition/coverage;
- event-risk/provider-quality state;
- five family contributions.

System View composer currently writes:
- `importance=important` when stance is not `watch`;
- `importance=routine` when stance is `watch`.

FP1-B may therefore include **important System View** messages as attention candidates, but must label the source as a System View presentation signal rather than claiming a core materiality-policy decision.

### 2.3 Attention ranking contract

**BUILD deterministic ordering over REUSE inputs**

No numeric ranking score will be added.

Candidate admission:
- canonical narrative candidate: exact `message_input.materiality == material` and `publication_disposition == publish`;
- System View candidate: exact persisted `importance == important`;
- routine/silent candidates are excluded.

Ordering:
1. explicit `critical` importance before `important`;
2. newer `event_at_ms` before older;
3. immutable narrative identity as deterministic tie-breaker.

Deduplication:
- canonical narratives: latest per exact `story_identity`;
- System View: latest per `(symbol, timeframe, subtype)`.

Default bounded result:
- top 5;
- hard maximum 20.

This is a **presentation priority / recency ordering**, not win probability, confidence or predictive ranking.

### 2.4 Customer Attention fields

| Customer field | Source | Classification |
|---|---|---|
| symbol | persisted narrative/System View | REUSE |
| timeframe | persisted narrative/System View | REUSE |
| occurred/updated time | `event_at_ms` | REUSE |
| category label | message input or System View category | EXTEND label |
| importance label | accepted importance | EXTEND label |
| headline / why-now | persisted `text.collapsed_text` | REUSE |
| detail | persisted `text.simple_text` | REUSE |
| current stance/state | persisted message state / analytical stance | EXTEND label |
| materiality basis | exact materiality decision reason when available | EXTEND customer wording |
| risk label | only from exact event-risk/provider-quality/risk fields when present | EXTEND |
| source freshness | exact `source_as_of_ms` where available; System View event time otherwise | EXTEND |
| audit identities | exact source/materiality/narrative identities | REUSE, audit-only |

If a candidate does not have an exact risk field, FP1-B must show no risk assertion rather than infer one from prose.

## 3. Five-Family Summary

### 3.1 Current accepted source

**REUSE**

The latest verified System View already contains one canonical row for:
- Geometry;
- Liquidity;
- Order Flow;
- Derivatives;
- On-chain.

Each row already freezes:
- family;
- state;
- direction;
- source quality;
- timeframe;
- support/opposition points;
- evidence domains;
- source evidence identities;
- source narrative identity;
- family weight.

FP1-A already converts core row state/direction/source-quality to customer-safe labels.

### 3.2 Missing customer context and exact source

**EXTEND**

A System View family row does not directly carry all family source timestamps/uncertainty detail.

When `source_narrative_identity` exists, FP1-B must reuse:
`IntelligenceStreamReadModel.read_message_detail(source_narrative_identity)`

The verified family `fact_bundle` provides:
- `source_as_of_ms`;
- `available_evidence_domains`;
- `state_label`;
- `state_components`;
- `direction`;
- `source_quality`;
- `uncertainty_flags`;
- exact evidence identities.

The verified family analytical view provides:
- materiality reason codes;
- changed components;
- previous/current family state.

### 3.3 Family customer projection

Allowed customer fields:
- family label;
- state label;
- relationship to current stance;
- direction;
- source quality;
- source time;
- freshness label;
- evidence-domain labels;
- uncertainty summary;
- changed/not-changed explanation when exact;
- unavailable reason.

Audit-only:
- source narrative identity;
- source evidence identities;
- fact/analytical identities;
- raw state labels/codes.

No family value may be replaced with zero when the exact source says unavailable.

## 4. Workspace Summary

### 4.1 Stream detail source

**REUSE**

`IntelligenceStreamReadModel.read_message_detail(narrative_identity)` verifies immutable lineage across:
- narrative;
- analytical view;
- fact bundle;
- message input.

For canonical decision/outcome narratives, `StreamFactBundle` already provides:
- asset/symbol/timeframe;
- event and source-as-of times;
- decision state;
- direction;
- support/opposition scores;
- five family contributions;
- event context;
- trigger zone;
- target zone;
- invalidation;
- probability status;
- calibrated probability only when authorized;
- freshness;
- uncertainty flags;
- available evidence domains;
- evidence summary;
- forecast identity;
- proof identity;
- resolution/outcome fields when resolved.

The analytical view already provides:
- effective stance;
- strength;
- dominant/secondary support;
- main contradiction;
- uncertainty counts/codes;
- next condition;
- invalidation condition;
- capital consequence;
- analytical materiality reason codes.

### 4.2 Decision Proof join

**REUSE**

`ImmutableDecisionEvidenceLedger` already provides read-only:
- `read_proof_for_signal(signal_freeze_identity)`;
- `read_proof_for_forecast(forecast_identity)`;
- issuance lookup;
- resolution lookup.

`DecisionProofSnapshot` provides:
- exact signal freeze identity;
- conditional thesis;
- trigger/target/invalidation;
- horizon;
- support/opposition;
- probability status;
- calibrated probability only when authorized;
- event context;
- freshness;
- uncertainty;
- per-domain evidence availability/verdict/source quality;
- exact evidence identity union.

FP1-B must never translate confluence score into probability.

### 4.3 Exact evidence join

**REUSE**

`IntelligenceStreamExactEvidenceReadModel.read_for_narrative(...)` already:
- verifies narrative lineage;
- resolves family/decision evidence;
- distinguishes exact ready / identity-only / explicitly unavailable states;
- prevents current-data substitution for historical/frozen evidence.

FP1-B may summarize resolution states for the customer, but must not duplicate evidence-domain resolution logic.

### 4.4 Signal-detail join

**REUSE when a signal identity is available**

`DashboardReader.signal_detail(signal_freeze_identity)` already reconstructs:
- frozen signal card;
- methodology selections;
- agreement/contradiction relations;
- geometry;
- evidence summary;
- frozen candle range.

FP1-B does not need a new signal ledger query.

### 4.5 Workspace customer projection

Allowed:
- customer headline and simple explanation;
- symbol/timeframe;
- state/direction;
- source/update time + freshness;
- trigger;
- invalidation;
- targets;
- support/opposition semantic;
- main contradiction;
- event context;
- uncertainty;
- probability status with explicit "not calibrated" wording;
- evidence-domain availability;
- family summaries;
- capital consequence text/state;
- resolution/outcome when exact.

Audit-only:
- narrative/fact/analytical/message identities;
- forecast/proof/signal identities;
- raw evidence identities and engine/schema versions.

## 5. FP1-B implementation slicing

### FP1-B1 — Attention + enriched Five-Family Summary

Implement first:
- read-only Attention candidates;
- canonical materiality admission;
- important System View admission;
- deterministic priority/recency ordering;
- family detail enrichment from exact source narratives;
- customer/audit separation.

Do not implement Workspace join in the same first patch.

### FP1-B2 — Workspace Summary

After FP1-B1 acceptance:
- verified Stream detail;
- Decision Proof join;
- exact evidence summary;
- optional signal-detail join;
- customer/audit separation.

## 6. FP1-B acceptance

Required for each sub-slice:
1. missing DB returns explicit unavailable without creating files;
2. all canonical SQLite reads remain read-only;
3. no invented materiality/predictive score;
4. routine/silent message is never promoted into Attention;
5. persisted material/important state is preserved;
6. ordering is deterministic;
7. normal customer payload contains no SHA256/raw enum/database vocabulary;
8. audit mode preserves exact provenance;
9. family unavailable stays unavailable;
10. probability is never inferred from confluence;
11. Product/Development checkouts remain untouched;
12. no RDP11 runtime mutation;
13. REAL_CAPITAL=0.

## 7. Exact next action

Implement **FP1-B1 only** in the existing `final_product_read_model.py` boundary plus focused tests.

Before production code change, append an FP1-B1 implementation-start checkpoint to `docs/agent/CURRENT_FRONTIER.md` and `docs/agent/HANDOFF_LOG.md`.
