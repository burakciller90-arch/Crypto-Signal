# RDP10 Frozen Proof Contract — Implementation Preparation

Status: **PREP ONLY — NO PRODUCTION ACTIVATION**
Prepared against main: `7d3a209b07e02c17f8f3fddeba4dd1c626392617`
Branch: `prep/rdp10-proof-contract`
Safety: **REAL_CAPITAL=0**
Execution authority: `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md`

## 1. Scope and sequencing

RDP10 is the exact frozen customer-proof contract. Its purpose is not to invent a new evidence engine. It must expose the strongest proof that already exists for each accepted evidence rail and fail closed for everything else.

This preparation is intentionally parallel to RDP5-C live acceptance. It does not modify RDP5 runtime, Market Tape collection, liquidation collection, Stream production runtime, score weights, or merge authority.

The locked execution roadmap places RDP10 after RDP9. The **generic RDP10 proof store/resolver contract can be implemented after RDP5 PASS**, but RDP10 cannot be declared PASS until upstream RDP6–RDP9 rails that are required by the roadmap have either produced accepted exact proof objects or remain explicitly unavailable under their accepted boundaries.

No SHA256 value is customer evidence by itself. Hashes are provenance/debug metadata. A customer proof must contain exact human-inspectable measurements or an explicit unavailable state.

## 2. Existing canonical resolution states

Current main already defines the correct three-state customer contract in:

`src/crypto_signal/product/intelligence_stream_evidence_contract.py`

- `READY_EXACT`
- `IDENTITY_ONLY_EXACT`
- `UNAVAILABLE_EXPLICIT`

These states should remain canonical.

### READY_EXACT

Use only when the requested proof domain can return the exact persisted/frozen payload actually used at or before the decision/family `as_of_ms`, including enough typed measurements to render the proof without consulting current live data.

### IDENTITY_ONLY_EXACT

Use when an exact evidence/freeze identity is genuinely bound to the message/decision, but the exact persisted customer payload for that identity cannot currently be resolved.

This is not a visual proof state.

### UNAVAILABLE_EXPLICIT

Use when the evidence did not exist, was not accepted, was stale/gapped, was research-only, or no exact historical payload is available.

Never upgrade UNAVAILABLE to IDENTITY_ONLY by inventing a hash and never upgrade IDENTITY_ONLY to READY merely because some parent raw source object exists.

## 3. Current proof architecture verified on main

### 3.1 Immutable decision / Geometry stack

Files:

- `src/crypto_signal/ledger/bundle.py`
- `src/crypto_signal/ledger/store.py`
- `src/crypto_signal/ledger/geometry_proof.py`
- `src/crypto_signal/product/intelligence_stream_visual_proof.py`

Current strengths:

- signal decision bundle is immutable and SHA-addressed;
- exact consumed candles are frozen inside the decision bundle;
- PIT/no-future checks exist;
- `geometry_proofs` are persisted atomically with new signal freezes;
- Geometry Proof contains Price Action, Harmonic, Elliott and selected Signal methodology states/annotations;
- Geometry Proof is SQL-immutable and parent-bound to bundle + signal;
- current visual proof refuses current-data substitution;
- current visual proof validates each frozen candle against the proof cutoff.

Important limitation:

The strongest RDP3 `FrozenGeometryProof` exists in `geometry_proofs`, but the current Stream Geometry family snapshot does **not** bind `proof_identity` and `IntelligenceStreamExactEvidenceReadModel` does not resolve the `geometry_proofs` table.

The current customer chart renderer therefore shows the exact frozen candle bundle plus selected signal entry/invalidation/targets, but not the full persisted Price Action + Elliott + Harmonic Geometry Proof.

### 3.2 F6 exact source resolver

File:

`src/crypto_signal/product/intelligence_stream_exact_evidence.py`

It can currently resolve exact persisted objects for:

- signal freeze / decision freeze bundle;
- Market Tape order-book snapshots;
- Market Tape public trades;
- Market Tape perpetual derivatives observations;
- Event Source calendar coverage;
- structured event observations;
- provider-divergence snapshots.

It enforces:

- read-only SQLite access;
- identity verification;
- top-level source/event/observed/ingested timestamp <= message source-as-of;
- `current_data_substitution=False`.

It does **not** currently resolve:

- `geometry_proofs`;
- liquidity dynamics freeze;
- liquidity structure freeze;
- liquidity sweep freeze;
- order-flow microstructure freeze;
- temporal order-flow freeze;
- absorption freeze;
- price/CVD divergence freeze;
- derivatives context freeze;
- derivatives dynamics freeze;
- liquidation events;
- liquidation event coverage;
- liquidation heatmap freeze;
- derivatives crowding freeze;
- On-chain research freezes;
- future RDP6 Options freezes;
- future RDP7 accepted On-chain/stablecoin freezes.

### 3.3 Current family projections

File:

`src/crypto_signal/product/intelligence_stream_family_sources.py`

The family snapshots already bind many exact identities.

#### Geometry

Bound:

- decision bundle identity;
- signal freeze identity;
- selected methodology evidence IDs;
- selected geometry source evidence ID.

Not bound:

- persisted RDP3 `geometry_proof.proof_identity`.

#### Liquidity

Bound identities include:

- liquidity dynamics freeze + analysis identities;
- liquidity structure freeze + analysis identities;
- liquidity sweep freeze + analysis identities;
- exact order-book snapshot identities;
- exact public-trade identities when consumed.

The rich derived freezes are computed in memory for the family projection. Their payloads are not persisted as general exact proof objects.

#### Order Flow

Bound identities include:

- microstructure freeze + analysis;
- exact order-book source;
- exact public trades;
- temporal order-flow freeze + analysis;
- absorption freeze + analysis when available;
- price/CVD divergence freeze + analysis when available;
- dependent liquidity-structure identities.

Again, most derived freeze payloads are not persisted for later customer replay.

#### Derivatives

Bound identities include:

- derivatives context freeze + analysis;
- derivatives dynamics freeze + analysis;
- exact perpetual derivatives observations;
- observed liquidation event identities;
- liquidation coverage identity;
- historical dynamics identity;
- liquidation heatmap freeze + analysis;
- derivatives crowding freeze + analysis.

Only the ordinary perpetual observations are currently resolved by F6. The liquidation tables and derived freeze payloads are not part of the current exact resolver.

#### On-chain

Current live Stream intentionally does not activate accepted standalone On-chain truth.

Research contracts exist for:

- Bitcoin network;
- exchange flow;
- wallet cohorts;
- large transfer clusters.

They are not accepted production-live customer proof on current main.

## 4. Critical RDP10 findings

## 4.1 Unknown-domain READY fallback can overstate exactness

Current `_objects_for_domain()` uses an explicit map for some domains, but an unknown domain receives no object-kind restriction.

Current `_family_domain_resolution()` then has a generic fallback:

`selected_objects + state_components => READY_EXACT`.

This creates a semantic overclaim risk.

Examples of current family domains not explicitly typed by F6 include:

- `liquidity_structure`;
- `liquidity_sweep`;
- `temporal_order_flow`;
- `window_local_cvd`;
- `absorption`;
- `candle_15m`;
- `price_cvd_divergence`;
- `derivatives_context`;
- `derivatives_dynamics`;
- `observed_liquidation_events`;
- `derivatives_crowding`;
- `liquidation_event_coverage`;
- `observed_liquidation_heatmap`.

A raw order book, trade or derivatives row can therefore make one of these derived domains look READY even though the exact derived freeze payload itself cannot be resolved.

**RDP10 requirement:** remove this generic readiness fallback. An unregistered proof domain must never become READY_EXACT.

## 4.2 Raw source exactness is not derived-proof exactness

A persisted order book proves the book snapshot.

It does not by itself prove the exact persisted:

- liquidity pool candidates;
- spoofing/hidden-liquidity candidate set;
- sweep candidate;
- absorption candidate;
- CVD divergence;
- liquidation heatmap;
- derivatives crowding state.

These require either:

1. their exact immutable derived freeze payload, or
2. an explicitly versioned frozen proof projection persisted at the same PIT cutoff.

Re-running today's engine over old raw data is not an acceptable substitute for the original historical proof.

## 4.3 Geometry strongest-proof gap

Current customer Geometry proof is valid but weaker than the strongest persisted backend truth.

Today:

- frozen candles: exact;
- selected signal entry/invalidation/targets: exact;
- full persisted RDP3 Geometry Proof: exists, but not bound/resolved in family proof.

RDP10 must expose the existing persisted `FrozenGeometryProof`, including:

- methodology states;
- PA structure/imbalance/liquidity annotations;
- Harmonic annotations;
- Elliott annotations;
- signal annotations;
- conflict/ambiguity flags.

Do not rebuild this from current candles.

## 4.4 Exact-source object cap cannot become proof completeness

F6 currently limits returned domain source objects with `_MAX_OBJECTS_PER_DOMAIN = 12`.

That is acceptable for debug/source sampling.

It is not sufficient for proof domains such as:

- full CVD window;
- absorption window;
- sweep evidence;
- liquidation event window;
- historical derivatives window.

A customer visualization must not compute a canonical metric from only the first/twelve returned objects unless that twelve-object set is the exact consumed set.

RDP10 must return a complete frozen derived proof payload or a versioned paginated exact source manifest.

## 4.5 PR #1478 is useful but not the RDP10 backend solution

Open PR #1478, `ED1: resolve exact family payloads for human proof`, is based on old main `0253e5d...` and is currently stale/non-mergeable against current main.

Useful ideas in that PR:

- family row opens its own exact proof;
- Geometry/Liquidity/Order Flow/Derivatives get dedicated renderers;
- hashes are kept under technical provenance;
- renderer refuses current-data substitution;
- Order Flow UI explicitly says its public-trade sample does not claim CVD/absorption.

Limitations:

- it changes frontend/rendering only;
- it relies on current F6 raw-object resolver;
- it does not persist/resolve the rich derived freezes;
- its Order Flow notional view is calculated from a capped source sample, not the canonical consumed family window;
- it does not fix the unknown-domain READY fallback;
- it does not expose the persisted RDP3 full Geometry Proof;
- it predates RDP5-C current main.

Do not duplicate #1478. Rebase/reuse its UI work only after the RDP10 backend contract is corrected.

## 5. Current exact-proof classification

The classification below is **customer-proof readiness on current main**, not whether an engine dataclass exists in source code.

| Family / evidence | Current class | Reason |
|---|---|---|
| Geometry frozen OHLC candles | **READY_EXACT** | exact immutable decision bundle, PIT checked, visual proof exists |
| Geometry selected entry/trigger zone | **READY_EXACT** | exact selected signal geometry frozen in bundle |
| Geometry selected invalidation | **READY_EXACT** | exact selected signal geometry frozen in bundle |
| Geometry selected targets | **READY_EXACT** | exact selected signal geometry frozen in bundle |
| Full RDP3 Price Action annotations | **IDENTITY_ONLY_EXACT** | exact Geometry Proof is persisted, but proof identity/payload is not exposed through family exact resolver |
| Full RDP3 Harmonic annotations | **IDENTITY_ONLY_EXACT** | same persisted Geometry Proof gap |
| Full RDP3 Elliott annotations | **IDENTITY_ONLY_EXACT** | same persisted Geometry Proof gap |
| Geometry methodology/conflict states | **IDENTITY_ONLY_EXACT** | exact in `geometry_proofs`, not customer-resolved |
| Liquidity exact order-book levels | **READY_EXACT** | persisted Market Tape order book resolves exactly |
| Liquidity public trades used by sweep | **READY_EXACT** | persisted trades resolve exactly when bound |
| Liquidity dynamics derived freeze | **IDENTITY_ONLY_EXACT** | freeze identity bound; exact freeze payload not persisted/resolved |
| Liquidity structure levels/candidates | **IDENTITY_ONLY_EXACT** | structure freeze/analysis identities bound; payload unavailable to resolver |
| Liquidity sweep candidate/point | **IDENTITY_ONLY_EXACT** | sweep freeze identity bound; payload unavailable |
| Canonical spoofing candidate geometry | **IDENTITY_ONLY_EXACT** | candidate count may be in Stream fact but exact candidate payload is not replayable |
| Canonical hidden-liquidity candidate geometry | **IDENTITY_ONLY_EXACT** | same |
| Order Flow exact source order book | **READY_EXACT** | persisted source snapshot resolves |
| Order Flow exact public trades | **READY_EXACT** | persisted source trades resolve |
| Book-pressure scalar in family fact | **READY_EXACT** | immutable Stream fact component |
| Taker-flow scalar in family fact | **READY_EXACT** | immutable Stream fact component |
| Window-local delta/CVD-end scalar | **READY_EXACT** | exact scalar is frozen in family state components when measured |
| Full temporal-flow freeze | **IDENTITY_ONLY_EXACT** | freeze identity bound; payload not persisted/resolved |
| Visualization-ready CVD series | **IDENTITY_ONLY_EXACT** | consumed identities exist, but canonical full series is not persisted/exposed |
| Absorption candidates | **IDENTITY_ONLY_EXACT** | freeze/analysis identities bound; exact candidate payload not resolved |
| Price/CVD divergence relation | **IDENTITY_ONLY_EXACT** | freeze/analysis identities bound; exact relation/candle payload not resolved |
| Exact 15m candles consumed by divergence | **IDENTITY_ONLY_EXACT** | historical candle source is not resolved as a bound RDP10 proof object |
| Derivatives funding/OI/mark/index observations | **READY_EXACT** | persisted Market Tape derivatives payload resolves |
| Derivatives context freeze | **IDENTITY_ONLY_EXACT** | identity bound; exact derived freeze payload not resolved |
| Derivatives dynamics freeze | **IDENTITY_ONLY_EXACT** | identity bound; exact derived freeze payload not resolved |
| Dynamics scalar components in Stream fact | **READY_EXACT** | frozen family state components |
| Raw observed liquidation events | **IDENTITY_ONLY_EXACT** | rows are persisted and identities bound, but F6 resolver does not query liquidation table |
| Liquidation provider coverage | **IDENTITY_ONLY_EXACT** | persisted/identity bound, but F6 resolver does not query coverage table |
| Observed liquidation heatmap freeze | **IDENTITY_ONLY_EXACT** | freeze identity bound; derived payload not persisted/resolved |
| Derivatives crowding freeze | **IDENTITY_ONLY_EXACT** | freeze identity bound; derived payload not persisted/resolved |
| Future liquidation-risk map | **UNAVAILABLE_EXPLICIT** | explicitly not claimed by RDP5 scientific boundary |
| Estimated dealer/leverage positions | **UNAVAILABLE_EXPLICIT** | unsupported source/assumption |
| BTC/ETH Options proof | **UNAVAILABLE_EXPLICIT** | RDP6 not implemented/accepted yet |
| Production On-chain exchange flow | **UNAVAILABLE_EXPLICIT** | RDP7 accepted provider rail not active |
| Production On-chain large transfers | **UNAVAILABLE_EXPLICIT** | RDP7 accepted provider/coverage not active |
| Production wallet cohorts | **UNAVAILABLE_EXPLICIT** | RDP7 accepted provider/admission rail not active |
| Production stablecoin capital flow | **UNAVAILABLE_EXPLICIT** | RDP7 not active |
| Bitcoin network research/source proof | **UNAVAILABLE_EXPLICIT** for live family | real public adapter exists, but current Stream policy is DEFERRED_SOURCE |
| Event calendar persisted source records | **READY_EXACT** when bound and PIT-valid | F6 resolves exact coverage/structured event payloads |
| Event Risk state over exact event record | **READY_EXACT** when bound and fresh | exact source + frozen state components; RDP8 freshness/runtime still governs live availability |
| Provider divergence snapshot | **READY_EXACT** when bound | persisted exact object resolver exists |
| Cross-venue RDP9 proof | **UNAVAILABLE_EXPLICIT** | RDP9 not accepted yet |

## 6. Required RDP10 frozen proof object contract

The lowest-risk design is to preserve all existing engine freeze identities and add one generic append-only **customer-proof object registry** for derived evidence.

Suggested file:

`src/crypto_signal/product/frozen_proof_store.py`

Suggested schema version:

`frozen-proof-object-v1/1`

### FrozenProofObject

Minimum fields:

- `object_identity` — existing freeze/proof identity, not a replacement hash;
- `analysis_identity` — optional exact child evidence identity;
- `object_kind`;
- `family`;
- `domains`;
- `symbol` / asset / network when applicable;
- `timeframe`;
- `as_of_ms`;
- `market_available_at_ms`;
- `observed_at_ms`;
- `source_provider`;
- `source_quality`;
- `freshness_state`;
- `freshness_age_ms`;
- `uncertainty_flags`;
- `source_object_identities`;
- `depends_on_evidence_identities`;
- `payload_json`;
- `visualization_json` or a versioned renderer contract;
- `renderer_contract_version`;
- `persisted_at_ms`;
- `production_authority=False`;
- `real_capital=0`.

### Persistence rule

The exact canonical derived freeze must be persisted **before** its family Stream event can claim READY_EXACT.

If proof persistence fails:

- do not publish a READY_EXACT domain;
- publish IDENTITY_ONLY_EXACT only if the exact identity is still legitimately frozen/bound;
- otherwise UNAVAILABLE_EXPLICIT.

An orphan persisted proof object is acceptable if Stream publication later fails. A Stream READY claim whose proof object does not exist is not acceptable.

### Immutable behavior

- INSERT or exact idempotent replay only;
- same identity + different canonical payload => conflict;
- SQL UPDATE/DELETE rejected;
- read-only historical lookup;
- no historical backfill that recomputes old engine output from current code.

## 7. Exact source vs derived proof lineage

Every customer proof must distinguish:

### source_objects

Exact source facts:

- order book;
- trades;
- derivatives observations;
- liquidation events;
- coverage;
- event records;
- future options/on-chain source payloads.

### derived_object

Exact frozen engine output:

- liquidity structure;
- sweep;
- temporal flow;
- absorption;
- divergence;
- derivatives dynamics;
- heatmap;
- crowding;
- Geometry Proof;
- later Options/On-chain/Cross-venue freezes.

### dependency lineage

A proof must state which source/derived objects it depends on.

This is required both for customer provenance and for RDP9 overlap/double-counting control.

## 8. Domain resolver contract change

Replace the permissive current domain behavior with an explicit registry.

Suggested conceptual map:

```text
domain
  -> accepted object kinds
  -> required exact payload kind
  -> allowed source support kinds
  -> renderer contract
```

Rules:

1. Unknown domain => never READY_EXACT.
2. Derived domain => requires exact derived proof object.
3. Raw-source domain => exact source row may be sufficient.
4. Scalar-only domain => immutable family fact component can be READY for that scalar only.
5. One READY capability must not upgrade every capability in the same domain.

Remove:

- generic `selected_objects + components => READY_EXACT`.

## 9. Capability-level resolution

One domain can contain mixed proof quality.

Example Liquidity:

- exact source orderbook = READY_EXACT;
- persistent pool coordinates = IDENTITY_ONLY_EXACT today;
- sweep point = IDENTITY_ONLY_EXACT today.

Therefore RDP10 response must not expose only one undifferentiated domain state.

Recommended response:

```json
{
  "domain": "liquidity",
  "resolution_state": "IDENTITY_ONLY_EXACT",
  "capabilities": {
    "source_orderbook": "READY_EXACT",
    "persistent_pool_levels": "IDENTITY_ONLY_EXACT",
    "sweep_candidates": "IDENTITY_ONLY_EXACT"
  }
}
```

The domain-level state should represent the requested canonical derived proof, while capability states expose weaker/stronger subparts.

## 10. Family frozen proof requirements

## 10.1 Geometry

Canonical frozen proof:

- persisted RDP3 `FrozenGeometryProof`.

Must expose:

- frozen OHLC series;
- source/provider/time provenance;
- Price Action methodology state;
- PA structure break lines/markers;
- FVG/BPR/other exact zones present in proof;
- liquidity pools that belong to Geometry/PA methodology;
- Harmonic pattern points/PRZ when present;
- Elliott wave points/labels when present;
- selected trigger/entry;
- invalidation;
- targets;
- conflict/ambiguity flags.

Implementation changes:

- bind `geometry_proof.proof_identity` into Geometry family snapshot;
- add `geometry_proofs` resolver;
- customer renderer consumes persisted proof annotations, not only `signal_decision.geometry`.

No accepted candidate is valid exact proof state.

## 10.2 Liquidity

Canonical frozen proofs:

- `LiquidityDynamicsEvidenceFreeze`;
- `LiquidityStructureEvidenceFreeze`;
- `LiquiditySweepEvidenceFreeze`.

Must expose:

- exact source order-book snapshots;
- relevant trades for sweep when consumed;
- bid/ask levels;
- persistent-pool candidates;
- depletion/replenishment state;
- spoofing candidate labels only as candidates;
- hidden-liquidity candidate labels only as candidates;
- sweep candidates/coordinates/time;
- quality/uncertainty;
- engine versions.

Visualization-ready contract:

- depth bars or level table;
- price levels/zones;
- sweep markers;
- no actor-intent labels.

## 10.3 Order Flow

Canonical frozen proofs:

- `OrderFlowMicrostructureEvidenceFreeze`;
- `TemporalFlowEvidenceFreeze`;
- `AbsorptionEvidenceFreeze`;
- `DivergenceEvidenceFreeze`.

Must expose:

- exact order-book context;
- exact consumed public trades or complete consumed identity manifest;
- taker-side delta;
- window-local cumulative CVD series or deterministic frozen series projection;
- trade velocity;
- large-buy/sell candidate counts;
- absorption candidate coordinates/window;
- divergence relation + exact consumed candle series;
- quality/uncertainty.

Do not compute canonical buy/sell/CVD proof from the UI's capped 12-object source sample.

## 10.4 Derivatives

Canonical frozen proofs:

- `DerivativesContextEvidenceFreeze`;
- `DerivativesDynamicsEvidenceFreeze`;
- `LiquidationHeatmapEvidenceFreeze`;
- `DerivativesCrowdingEvidenceFreeze`;
- raw `LiquidationObservation`;
- `LiquidationFeedCoverage`.

Must expose:

- funding;
- OI;
- mark/index;
- basis;
- price/OI dynamics;
- funding percentile/acceleration;
- liquidation event rows;
- exact provider coverage interval and availability time;
- heatmap observed bins/clusters;
- none-observed only when coverage proves it;
- crowding/squeeze context;
- explicit unsupported future-risk/leverage claims.

PIT note:

RDP5-C main `b2d687e...` correctly moved live liquidation replay to the provider coverage **observation cutoff**, not merely coverage-end. RDP10 must preserve that knowledge-time semantic in customer proof.

Never present `coverage_end_ms` alone as the time at which evidence was known.

## 10.5 On-chain

Until RDP7 accepted live provider evidence exists:

- family proof = `UNAVAILABLE_EXPLICIT`.

When RDP7 becomes accepted, canonical proof objects should include:

- exchange-flow freeze;
- stablecoin-capital-flow freeze;
- large-transfer freeze + exact coverage;
- wallet-cohort admission/forward freeze;
- source provider/attribution version.

Research-only M5 artifacts must not silently become live READY proof.

## 10.6 Options / volatility

RDP6 output will belong to Derivatives.

RDP10 must be ready to consume:

- exact option surface freeze;
- ATM IV term structure;
- 25D skew;
- OI/volume by expiry;
- expiry concentration;
- source/provider timestamps.

Until RDP6 acceptance:

- `UNAVAILABLE_EXPLICIT`.

## 10.7 Event Risk / score-external context

Exact proof should expose:

- exact structured event record;
- coverage state;
- scheduled/event timestamps;
- source/provider;
- event-risk state;
- temporal relationship to decision;
- freshness/process uncertainty.

If RDP8 runtime is stale/unproven, live proof must say stale/unavailable even if an old exact event record exists.

## 10.8 Cross-venue / data quality

Provider divergence is already exact-resolvable.

RDP9 future proof should add:

- compared providers/venues;
- normalized compatible measurements;
- venue-local/broad classification;
- disagreement metrics;
- dependency lineage;
- overlap flags.

This is quality/context, not a sixth score family.

## 11. Semantic duplication / lineage findings

## 11.1 Same raw source appears under multiple domains

Examples:

- order book supports both Liquidity and Order Flow;
- public trades support temporal flow, CVD, sweep and absorption;
- derivatives observations support context, dynamics and crowding;
- liquidation events support heatmap and crowding.

RDP10 must show shared lineage, not visually imply independent confirmations.

Add:

- `source_object_identities`;
- `depends_on_evidence_identities`;
- optional `overlap_group_ids` supplied by RDP9.

## 11.2 Historical R25 liquidation ownership differs from current live RDP5

`rich_family_proof_adapters.py` historically enriches a `LIQUIDATION_MAP` into Liquidity context.

Current RDP5 live family projection owns liquidation heatmap/crowding inside **Derivatives**.

RDP10 must preserve origin adapter/family version and must not render one historical liquidation proof as two independent current family proofs.

Current live ownership for RDP5 is Derivatives.

## 11.3 Decision Proof domain != independent confidence unit

`ORDER_BOOK`, `LIQUIDITY_MAP`, `ORDER_FLOW_CVD`, etc. can share parent truth.

RDP10 presentation must not turn each proof panel into another implied vote.

RDP9 controls overlap in scoring; RDP10 must expose the dependency so the UI can explain it.

## 12. Future-leakage audit

### Already strong

- immutable decision bundle candle cutoff;
- Geometry visual proof candle close/ingest checks;
- signal freeze as-of check;
- Market Tape exact object top-level event/source/ingest cutoff;
- Event Source exact identity verification;
- provider divergence exact identity verification;
- current RDP5 liquidation observation-cutoff fix.

### RDP10 additions required

1. Nested derived proof verifier:
   - every consumed event/source/observed/ingested timestamp in a proof payload <= proof `as_of_ms`.

2. Availability semantics:
   - `market_available_at_ms` must be the time the evidence could actually have been known, not merely event/window end.

3. Persisted-at rule:
   - a proof object cannot be attached to an earlier family message if it was first persisted/observed after the message's PIT cutoff, unless the proof object itself demonstrates prior availability and the production contract explicitly allowed that persistence delay.

4. Historical provider revisions:
   - never replace the originally frozen payload with a later provider revision.

5. No current DB fallback:
   - if exact frozen object is absent, return IDENTITY_ONLY or UNAVAILABLE; do not query latest source rows to "fill" a historical proof.

## 13. Fabricated-evidence audit

Explicitly prohibited:

- treating a hash as a chart;
- treating a parent order book as the exact derived liquidity structure;
- treating twelve returned trades as the canonical full CVD window;
- rebuilding old derived proof with current engine code;
- showing stale last-known source values as current;
- filling missing On-chain/Options with synthetic fixtures;
- turning a research adapter artifact into production-live truth;
- drawing future liquidation zones not present in observed evidence;
- inferring dealer gamma, institution/whale identity or actor intent.

## 14. Customer proof response contract

Recommended top-level response:

```text
schema_version
narrative_identity
family
domain
resolution_state
reason_codes
human_state
as_of_ms
market_available_at_ms
observed_at_ms
freshness
source
uncertainty_flags
measurements
visualization
source_objects
lineage
current_data_substitution=false
read_only=true
production_authority=false
real_capital=0
```

### source

- provider;
- venue/network;
- endpoint/channel semantic;
- adapter version;
- attribution methodology/version when applicable.

### freshness

- state: FRESH / STALE / GAP / UNAVAILABLE;
- age_ms;
- accepted budget;
- reason codes.

### lineage

Keep hashes here, not as primary customer content:

- proof/freeze identity;
- analysis/evidence identity;
- raw/source object identities;
- parent freeze identities;
- engine version;
- renderer contract version.

## 15. Visualization contract

Each READY proof must carry a typed visualization contract.

Suggested kinds:

- `ohlc_annotations`
- `orderbook_depth`
- `price_levels_zones`
- `trade_flow_series`
- `cvd_series`
- `derivatives_timeseries`
- `liquidation_clusters`
- `options_surface`
- `capital_flow_timeseries`
- `event_timeline`
- `data_quality_comparison`

A proof may expose multiple views.

The visualization must be generated exclusively from the frozen proof object and its exact source parents.

## 16. Minimal implementation sequence

## RDP10-A — close false READY states

Files primarily:

- `intelligence_stream_exact_evidence.py`
- tests only around contract behavior.

Work:

- remove generic unknown-domain READY fallback;
- add explicit domain/object-kind registry;
- unknown derived domains => IDENTITY_ONLY or UNAVAILABLE;
- capability-level states;
- regression tests for current rich domain names.

This can be implemented first after RDP5 PASS without changing production data collection.

## RDP10-B — Geometry Proof binding

Work:

- resolve `geometry_proofs`;
- bind exact `proof_identity` to Geometry family;
- expose full RDP3 annotations/methodology states;
- renderer uses persisted Geometry Proof;
- preserve existing frozen chart as source view.

## RDP10-C — generic immutable derived-proof store

Work:

- add append-only `FrozenProofStore`;
- serializer/validator contract;
- proof object identity equals existing freeze identity;
- optional analysis identity alias;
- SQL immutability;
- read-only as-of lookup;
- no retroactive recomputation/backfill.

## RDP10-D — Liquidity + Order Flow persistence

Persist at family snapshot creation:

- dynamics;
- structure;
- sweep;
- microstructure;
- temporal flow;
- absorption;
- divergence.

Add exact render projections:

- zones/levels;
- sweep markers;
- CVD series;
- absorption/divergence relationship.

## RDP10-E — Derivatives persistence

Persist/resolve:

- context;
- dynamics;
- liquidation events;
- liquidation coverage;
- heatmap;
- crowding.

Preserve RDP5 observation-cutoff PIT semantics.

## RDP10-F — upstream adapter slots

Add proof-store object kinds/resolver registration for:

- RDP6 Options;
- RDP7 On-chain/stablecoin;
- RDP8 Event Risk enhancements;
- RDP9 cross-venue/overlap.

Do not mark these READY until upstream acceptance.

## RDP10-G — API/UI cutover

Only after backend state is truthful:

- family-owned proof endpoints use RDP10 response;
- rebase/reuse safe parts of PR #1478;
- hashes move under provenance details;
- no renderer computes canonical evidence from truncated raw samples.

## 17. Test / gate matrix

| Gate | Required proof |
|---|---|
| Resolution enum | only READY_EXACT / IDENTITY_ONLY_EXACT / UNAVAILABLE_EXPLICIT |
| Unknown domain | never becomes READY from generic raw object fallback |
| Exact derived payload | READY derived domain requires matching persisted frozen proof object |
| Hash-only | identity without payload remains IDENTITY_ONLY |
| Missing | no identity/payload becomes UNAVAILABLE_EXPLICIT |
| Geometry | full persisted Geometry Proof resolves by proof/bundle/signal lineage |
| Geometry future | every annotation/candle belongs to consumed frozen scope |
| Liquidity | structure/sweep READY only with exact persisted derived freeze |
| Order Flow | full CVD proof cannot be built from truncated source sample |
| Absorption/divergence | exact freeze + exact parents required |
| Derivatives raw | funding/OI/mark/index exact source remains READY |
| Liquidation raw | event and coverage rows resolve exactly |
| Liquidation none-observed | only complete observed coverage can prove zero events |
| RDP5 cutoff | coverage observed-at availability is preserved |
| Heatmap/crowding | derived READY requires persisted exact freeze |
| On-chain | remains UNAVAILABLE until RDP7 accepted source |
| Options | remains UNAVAILABLE until RDP6 accepted source |
| Event | stale/process-unproven live context fails closed |
| Provider divergence | exact resolver remains identity/PIT checked |
| Dependency lineage | shared source truth is explicit; no independent-proof implication |
| Nested future check | any future child timestamp rejects proof |
| Historical replay | no latest/current-data substitution |
| Identity tamper | canonical payload/identity mismatch fails closed |
| Immutable store | UPDATE/DELETE rejected; conflict on same ID/different payload |
| Determinism | input order does not alter canonical proof payload/identity |
| Renderer | visualization uses only supplied frozen proof payload |
| Source cap | debug object cap cannot truncate canonical visualization evidence |
| Research isolation | research-only freeze cannot be promoted to live READY |
| RDP5 regression | existing RDP5 gates remain green; no RDP5 production changes |
| Static quality | focused pytest + Ruff + mypy + py_compile |
| API | exact proof response exposes source/as-of/freshness/uncertainty |
| UI | SHA is provenance detail, never the main proof body |
| REAL_CAPITAL | always 0 |

## 18. Suggested focused regression cases

1. Unknown `liquidity_structure` domain + exact orderbook + components => **must not READY** without structure proof object.
2. Structure freeze identity exists but no payload => **IDENTITY_ONLY_EXACT**.
3. Structure freeze persisted with matching identity/parents => **READY_EXACT**.
4. Geometry bundle exists, Geometry Proof exists but family lacks proof binding => identity gap is detected.
5. Full Geometry Proof bound => PA/Harmonic/Elliott annotations returned exactly.
6. Twelve visible trades with 1,000 consumed trades => UI may show sample, but canonical CVD comes only from full frozen proof.
7. Liquidation coverage identity resolves from Market Tape and `observed_at_ms <= proof as_of_ms`.
8. `coverage_end_ms <= as_of_ms < observed_at_ms` => coverage is not PIT-visible yet.
9. Zero liquidation events + no complete coverage => UNAVAILABLE, never NONE_OBSERVED.
10. Heatmap identity without frozen heatmap payload => IDENTITY_ONLY.
11. Old research exchange-flow freeze in a live message => contract rejects production READY.
12. Future nested trade/candle/source timestamp => proof rejected.
13. Proof object payload tamper => identity mismatch failure.
14. Current provider/source DB contains newer data but historical proof object absent => no substitution.
15. Same source orderbook referenced by Liquidity and Order Flow => lineage shows shared parent without duplicate customer object inflation.

## 19. Open blockers

### BLOCKER 1 — derived freezes are mostly ephemeral

RDP4/RDP5 family generation computes rich freezes in memory and emits their identities, but does not persist a general replayable derived-proof payload.

Resolution:

- immutable FrozenProofStore.

### BLOCKER 2 — strongest Geometry Proof is not connected to family exact evidence

Resolution:

- bind persisted `geometry_proof.proof_identity`;
- add resolver/object kind.

### BLOCKER 3 — current F6 domain fallback can produce false READY

Resolution:

- explicit domain registry; remove generic fallback before RDP10 UI cutover.

### BLOCKER 4 — liquidation event/coverage tables are absent from exact resolver

Resolution:

- add exact object kinds for:
  - `market_tape_liquidation`;
  - `market_tape_liquidation_coverage`.

### BLOCKER 5 — source-object response is intentionally capped

Resolution:

- keep capped source preview for human debug;
- canonical derived visualization must come from complete frozen proof payload or exact paginated manifest.

### BLOCKER 6 — On-chain/Options/Cross-venue upstream rails are not yet accepted

Resolution:

- reserve object kinds/contracts now;
- remain UNAVAILABLE_EXPLICIT until RDP6/RDP7/RDP9 acceptance.

### BLOCKER 7 — PR #1478 is stale and frontend-first

Resolution:

- do not merge as RDP10 solution;
- salvage/rebase renderer work after backend proof states are truthful.

## 20. RDP10 PASS boundary

RDP10 is PASS only when:

- every customer proof domain uses the three canonical states truthfully;
- no unregistered/derived domain becomes READY from parent raw data alone;
- Geometry exposes the strongest persisted RDP3 proof;
- Liquidity derived levels/sweeps have immutable replayable payloads;
- Order Flow has exact complete temporal/CVD/absorption/divergence proof where measured;
- Derivatives exposes exact raw + derived dynamics + liquidation coverage/heatmap/crowding proof;
- accepted RDP6 Options proof is integrated or explicitly unavailable according to upstream state;
- accepted RDP7 On-chain/stablecoin proof is integrated or explicitly unavailable according to upstream state;
- Event Risk/context returns exact source records with freshness/process truth;
- RDP9 dependency/overlap lineage is visible;
- historical proof never reads current live data;
- all nested PIT checks pass;
- SHA identities are technical provenance, not the user-facing evidence;
- stale/missing/research-only rails fail closed;
- REAL_CAPITAL=0.

## 21. Prep conclusion

The repository already has a strong foundation: immutable signal bundles, persisted Geometry Proof, PIT-safe family engines, exact Market Tape source rows, Event Source exact records, provider-divergence records, three canonical resolution states and a read-only exact-evidence API.

The remaining RDP10 problem is primarily **persistence and truthful resolution of rich derived evidence**.

The minimal safe strategy is:

1. close false READY fallback;
2. connect the already-persisted full Geometry Proof;
3. persist RDP4/RDP5 derived freezes under their existing identities;
4. extend the resolver by typed object kind;
5. render only from frozen proof payloads;
6. keep future RDP6/RDP7/RDP9 rails explicitly unavailable until accepted.

This avoids duplicate engine work and avoids turning SHA identities or parent raw source objects into fake visual evidence.
