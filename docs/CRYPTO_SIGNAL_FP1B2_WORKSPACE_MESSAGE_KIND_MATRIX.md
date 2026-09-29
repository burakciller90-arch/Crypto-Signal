# Crypto Signal — FP1-B2 Workspace Message-Kind / Source Matrix

Status: **AUDIT COMPLETE / IMPLEMENTATION NOT YET STARTED**
Date: 2026-09-29
Base main: `a67f7192dd4b6a36a33d7aacf2b7e304cafdf509`
Active branch: `fp1b/attention-workspace-family-summary`
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**

## 1. Purpose

FP1-B2 creates one customer-safe Workspace Summary for an already persisted Stream narrative.

It must branch by verified message kind. It must never assume that every Stream narrative is a forecast/decision message.

No new:
- signal/evidence calculation;
- materiality score;
- probability model;
- database;
- writer;
- Product route;
- frontend;
- runtime deployment.

## 2. Canonical detail-kind classifier

`IntelligenceStreamReadModel.read_message_detail(narrative_identity)` is the authority.

Verified kinds:

| Verified detail shape | Workspace kind | B2 support |
|---|---|---|
| `system_view` present | System View | **SUPPORTED** |
| `fact_bundle.projector_id` present | Family narrative | **SUPPORTED** |
| generic `fact_bundle.forecast_identity` / decision fact | Decision / Outcome | **SUPPORTED** |
| `capital_story` | Capital story | **EXPLICITLY DEFERRED TO FP1-D** |
| `capital_decision` | Capital decision | **EXPLICITLY DEFERRED TO FP1-D** |
| `capital_sizing` | Capital sizing | **EXPLICITLY DEFERRED TO FP1-D** |
| `capital_lifecycle` | Capital lifecycle | **EXPLICITLY DEFERRED TO FP1-D** |

Capital messages may return a customer-safe "workspace not available for this message type" result, but B2 must not reinterpret capital semantics.

## 3. Shared customer fields

For supported kinds:

- symbol;
- timeframe;
- updated time;
- source/as-of time when canonical;
- freshness label;
- short headline;
- simple explanation;
- state label;
- direction label where exact;
- event-risk label where exact;
- uncertainty summary;
- evidence-resolution summary;
- trigger / target / invalidation only where exact;
- probability wording only where exact;
- optional audit envelope.

Normal customer output must not require:
- SHA256;
- schema/engine versions;
- raw reason codes;
- raw enum values;
- database/table vocabulary.

## 4. System View

Canonical source: verified `stream_system_view_messages`.

Reusable exact fields:
- `event_at_ms`;
- `symbol`;
- `timeframe`;
- `state`;
- deterministic customer text;
- stance support/opposition;
- trigger/target/invalidation when present;
- event-risk/provider-quality states;
- main contradiction;
- family contributions.

B2 customer semantics:
- source time = system-view event time;
- probability = "Kalibre edilmiş olasılık değil" when source says `not_calibrated`;
- no Exact Evidence resolver call is required for System View itself because the System View is a composed presentation record, not a decision/family evidence binding;
- family proof detail remains available through FP1-B1 family summaries.

Classification: **REUSE + presentation EXTEND**.

## 5. Family narrative

Canonical source:
- verified family narrative;
- verified family fact bundle;
- verified family analytical view.

Exact family fields:
- family;
- state label;
- direction;
- source quality;
- `source_as_of_ms`;
- evidence domains;
- evidence identities;
- uncertainty flags;
- changed components;
- previous/current family state.

Exact Evidence:
`IntelligenceStreamExactEvidenceReadModel.read_for_narrative(...)` is valid for family narratives.

Its canonical resolution states are:
- `READY_EXACT`;
- `IDENTITY_ONLY_EXACT`;
- `UNAVAILABLE_EXPLICIT`.

B2 only summarizes those states into customer wording. It does not reproduce domain-resolution logic.

Trigger / target / invalidation:
- **EXPLICITLY UNAVAILABLE** unless present in the exact family source itself;
- B2 will not borrow them from a different narrative.

Classification: **REUSE + presentation EXTEND**.

## 6. Decision / Outcome narrative

Canonical Stream fact already provides:
- decision state;
- direction;
- trigger zone;
- target zone;
- invalidation price;
- support/opposition scores;
- event context;
- probability status;
- calibrated probability only if canonical source carries it;
- freshness;
- uncertainty flags;
- evidence domains;
- forecast identity;
- proof identity;
- resolution/outcome fields when resolved.

Canonical analytical view provides:
- effective stance;
- strength;
- dominant support;
- secondary support;
- main contradiction;
- uncertainty counts;
- next condition;
- invalidation condition;
- capital consequence;
- materiality reasons.

### Optional Decision Evidence join

When `decision_evidence_path` is configured and exists:

`ImmutableDecisionEvidenceLedger.read_proof_for_forecast(forecast_identity)`

may be used read-only.

Mandatory consistency:
- returned forecast identity must equal Stream fact forecast identity;
- returned proof identity must equal Stream fact proof identity;
- conflict = fail closed with `FinalProductReadError`.

When Decision Evidence is not configured/missing:
- Workspace still works from verified Stream fact;
- customer label says the additional decision-proof source is not connected;
- B2 must not create the file.

### Optional Exact Evidence join

For decision narratives:
`IntelligenceStreamExactEvidenceReadModel.read_for_narrative(...)`

If signal + decision evidence paths are configured, the existing Visual Proof resolver may yield `READY_EXACT`.

If not configured, the existing resolver explicitly degrades available decision evidence domains to `IDENTITY_ONLY_EXACT`.

B2 summarizes this state only.

Classification: **REUSE + presentation EXTEND**.

## 7. Optional signal detail

`DashboardReader.signal_detail(signal_freeze_identity)` is a read-only reusable source.

B2 does **not require** Signal Detail to build core Workspace Summary because trigger/target/invalidation and evidence state already exist in the verified Stream/Decision Proof contracts.

If a future B2 extension uses it:
- only when an exact `signal_freeze_identity` is available;
- only when `signal_ledger_path` is explicitly configured;
- missing ledger/schema/signal remains explicit;
- no fallback to latest/current signal.

Classification: **OPTIONAL REUSE / NOT REQUIRED FOR B2 CORE**.

## 8. Customer evidence-resolution labels

B2 summary contract:

- any `READY_EXACT > 0` -> **Doğrulanmış kanıt mevcut**
- no ready, but any `IDENTITY_ONLY_EXACT > 0` -> **Kanıt kimliği doğrulandı; ayrıntı sınırlı**
- only `UNAVAILABLE_EXPLICIT` or zero domains -> **Kanıt ayrıntısı kullanılamıyor**

This is availability, not confidence or probability.

## 9. Probability rule

- `probability_status == not_calibrated` and no calibrated probability -> **Kalibre edilmiş olasılık değil**
- calibrated value may be shown only if exact persisted source carries a non-null calibrated probability;
- confluence support/opposition must never be converted into probability.

## 10. B2 implementation boundary

Extend only:
- `src/crypto_signal/product/final_product_read_model.py`
- `tests/test_final_product_read_model.py`

Constructor may add optional read-only paths:
- `decision_evidence_path`;
- `signal_ledger_path`.

Core method:
- `workspace_summary(narrative_identity, observed_at_ms, ...)`

No `web.py` change in B2.

## 11. B2 acceptance

Required:
1. missing Stream DB is explicit and non-creating;
2. unknown narrative is explicit;
3. System View Workspace uses only verified System View fields;
4. Family Workspace does not fabricate decision trigger/target;
5. Family exact-evidence state is summarized without raw resolution enum leakage;
6. Decision Workspace exposes trigger/target/invalidation from exact Stream fact;
7. no confluence-to-probability inference;
8. optional missing Decision Evidence does not create a DB and does not break core Workspace;
9. configured conflicting Decision Proof fails closed;
10. capital message kinds are explicitly deferred, not misclassified;
11. default customer payload contains no SHA/raw enum/database vocabulary;
12. audit mode preserves exact identities;
13. SQLite source bytes / pre-existing WAL remain unchanged;
14. Product/Development non-mutation;
15. REAL_CAPITAL=0;
16. no RDP11 runtime mutation.

## 12. Exact next action

Append FP1-B2 implementation-start checkpoint, then implement the smallest supported Workspace Summary for System View, Family and Decision/Outcome kinds with optional Decision Evidence + Exact Evidence read-only joins. Do not add a route or frontend.
