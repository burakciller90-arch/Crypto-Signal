# Crypto Signal Frontend M1 — Backend Capability Matrix & Gap Ledger

> **NO LONGER THE ACTIVE FRONTEND FRONTIER — 2026-09-25**  
> Current execution authority is `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`.  
> This matrix remains valuable evidence about verified backend capabilities and gaps. Reuse/refresh those facts during Stream S1, but do not execute its old multi-screen IA sequence.

Status: **HISTORICAL DISCOVERY EVIDENCE — SUPERSEDED AS EXECUTION FRONTIER**  
Observed runtime/code baseline: repository main at `26cc5b05f9b15a0a8569042c534886e4681b4502`  
Frontend canonicalization merge: `59d2bd51ff4696945cb8a963ed490d6abe3bdfb8` (PR #1254, documentation/authority only)  
Baseline validity: PR #1254 and follow-up PR #1255 are documentation-only and do not change the runtime/backend code inspected for this matrix.  
Purpose: map real backend truth to future frontend capability without invention, and prevent accepted backend capability from remaining dormant merely because a product adapter/UI has not yet been written.

Current code re-check: the documentation-only PRs #1254/#1255 did not alter the backend baseline. This M1 pass now additionally audits accepted-but-unsurfaced intelligence/capital capability against current main.

## 1. Classification

REUSE — existing contract can be consumed substantially as-is.  
ADAPT — canonical truth exists but product query/read model needs extension.  
DISCOVER — likely underlying evidence exists, but exact product contract/renderable semantics are not yet proven.  
NOT_AVAILABLE — required evidence has not been established; frontend must fail closed.  
ADD_PRESENTATION — canonical facts exist; non-authoritative UX/narrative layer is needed.

## 2. Current product API inventory

| Surface | Current route | Verified capability | M1 class | Frontend implication |
|---|---|---|---|---|
| Health | /api/health | read-only product/runtime health | REUSE | global health source |
| Command center | /api/command-center | counts + recent frozen signals | REUSE/ADAPT | Home baseline; may need richer decision projection |
| Market radar | /api/market-radar | latest frozen signal per context | REUSE | opportunity/radar candidate |
| Navigation | /api/navigation | available market contexts | REUSE | asset/timeframe discovery |
| Asset cockpit | /api/assets/{symbol}/{timeframe} | latest-by-provider + recent signals | REUSE | Markets baseline |
| Signal archive | /api/signals | frozen signals, limit/offset | ADAPT | filters/stable pagination required |
| Proof wall | /api/archive/proof-wall | frozen signal + latest outcome, limit/offset | ADAPT | server filters + keyset/cursor preferred |
| Signal detail | /api/signals/{signal_freeze_identity} | methodologies, selected evidence, geometry, frozen candle metadata/bundle | REUSE/DISCOVER | strong proof/markets source; visual-coordinate audit required |
| Decision Proof by signal | /api/decision-proof/{signal_freeze_identity} | persisted immutable proof or explicit unavailable/empty | REUSE | exact proof route |
| Decision Proof by forecast | /api/decision-proof/forecast/{forecast_identity} | exact SHA256 forecast lookup | REUSE | identity-safe drill-down |
| Intelligence Feed | /api/intelligence-feed | persisted feed, currently forecast issued/resolved event kinds | ADAPT | broaden product timeline without fabricating events |
| WC2 Actionability | /api/wc2/action/{forecast_identity} | exact forecast actionability | REUSE | decision/action surface |
| Decision evidence status | /api/decision-evidence/status | decision-evidence runtime truth | REUSE | system/proof health |
| Shadow rail status | /api/shadow-decision-rail/status | research/shadow status | REUSE | advanced/research-only |
| Shadow forecast cycle | /api/shadow-decision-rail/forecast/{forecast_identity} | exact forecast shadow cycle | REUSE | advanced lineage |
| Operational truth | /api/r25/operational-truth | reconciled runtime/product evidence | REUSE | System Health |
| Market Tape runtime | /api/market-tape-runtime/status | collector/tape runtime truth | REUSE | health/data quality |
| Provider divergence | /api/provider-divergence/status | persisted divergence snapshot identity and lookback | REUSE | provider truth/advanced Markets |
| Event Source runtime | /api/event-source-runtime/status | event-source runtime truth | REUSE | health/event quality |
| Cold Archive | /api/cold-archive/status | archive verification/replay truth | REUSE | System Health |
| Alerts | /api/alerts | alert center read surface | REUSE/ADAPT | notification-source candidate |
| Education | /api/education | concept catalog | REUSE | contextual education |
| Education detail | /api/education/{concept_id} | concept detail | REUSE | tooltip/learn drawer |
| Paper epoch contract | /api/paper/epoch-contract | epoch constitution/runtime binding | REUSE | Capital authority/context |
| Epoch 2 state | /api/paper/epoch2-state | activation, vault and consolidated state | REUSE | Capital |
| Paper mission control | /api/paper/mission-control | read-only paper snapshot | REUSE | Capital |
| Intelligence center | /api/intelligence-center | learning/intelligence center snapshot | REUSE/DISCOVER | advanced intelligence context |
| Performance | /api/performance | performance availability/trust surface | REUSE | Performance/Trust |

## 3. Evidence and lineage already present

### 3.1 Decision Proof
Verified model contains:
- proof_identity;
- forecast_identity;
- signal_freeze_identity;
- confluence_identity;
- event_context_identity;
- probability authorization/calibration identities when applicable;
- asset/symbol/timeframe;
- issued_at_ms;
- source_as_of_ms;
- trigger zone;
- target zone;
- invalidation;
- uncertainty flags;
- source evidence identities;
- evidence slices;
- read_only=true;
- production_authority=false;
- REAL_CAPITAL=0.

Decision Proof evidence slices already separate:
- domain;
- availability;
- verdict;
- evidence identities;
- market_available_at_ms;
- observed_at_ms;
- freshness;
- source quality.

This is a strong REUSE base for multi-axis truth and temporal integrity.

### 3.2 Frozen signal detail
Verified current product model includes:
- immutable bundle and signal-freeze identities;
- exchange;
- market type;
- symbol;
- timeframe;
- as_of_ms;
- frozen_at_ms;
- source cutoff;
- state/direction;
- confluence semantics;
- uncertainty;
- methodologies;
- selected evidence;
- key levels;
- metrics;
- entry zone;
- invalidation;
- targets;
- frozen candle bundle metadata.

Frozen OHLC therefore has a real product source. It is not a mock-only capability.

### 3.3 Market Tape temporal/microstructure storage
Verified Market Tape runtime schema includes canonical tables for:
- order books;
- trades;
- derivatives;
- liquidations;
- liquidation coverage.

Order-book rows include:
- snapshot_identity;
- exchange;
- market_type;
- symbol;
- event_at_ms;
- source_timestamp_ms;
- ingested_at_ms;
- update_id;
- sequence;
- source;
- adapter_version;
- payload_json.

Conclusion: exact order-book data appears to exist in Market Tape storage, but current product API does not yet prove a Decision-Proof-bound render contract for bid/ask levels. Classification: DISCOVER -> likely ADAPT, not automatically REUSE.

## 3.4 Accepted capability is not the same as surfaced capability

The current product layer already exposes an accepted intelligence catalog whose entries explicitly report `runtime_evidence_status = not_exposed_as_live_feed`. The repository also contains accepted intelligence engines and evidence contracts for regime, trend/momentum, mean reversion, breakout/volatility, derivatives, order flow/microstructure, on-chain, sentiment/attention, cross-market context, liquidity/liquidation families and related event-risk evidence.

This means a missing live frontend card is often a **projection gap**, not missing backend science.

Capital has the same distinction:
- Smart Capital Allocator is accepted for all three Epoch 2 vaults;
- Core eligibility, Tactical 1m/5m microstructure eligibility, and Opportunity Reserve recovery eligibility are all explicitly modeled;
- Position Sizing Bridge is canonical-three-vault aware;
- R22 Transaction Tape and R21 Epoch 2 accounting are vault-aware and already define exact per-vault intent/fill/accounting lineage;
- R22Epoch2AtomicTape can atomically persist an accepted fill plus all three post-trade vault snapshots and the consolidated Epoch 2 snapshot;
- the currently accepted forward paper-execution runtime is specifically bound to **CORE** and `paper_autonomy_v2_exact_dual_provider_4h`, and writes its own WC2 execution journal rather than automatically advancing the canonical R22/R21 Epoch 2 transaction/accounting tape;
- current status therefore may truthfully show successful forward execution engineering while canonical R22 Epoch 2 mutation tables still contain zero real forward bundles.

Therefore the missing product closure is broader than Tactical: **one canonical three-vault forward virtual-capital runtime** must bind each vault's accepted eligibility/sizing policy to deterministic simulated execution and canonical R22/R21 accounting. Existing Core execution logic should be reused, not discarded; Tactical and Opportunity require their own evidence/policy adapters.

## 3.5 Five-layer institutional intelligence coverage

The user's target intelligence architecture maps strongly to existing backend evidence engines:

| Layer | Backend evidence already present | Current truth caveat | Product action |
|---|---|---|---|
| Liquidity / Order Book Dynamics | liquidity dynamics, liquidity structure, liquidation heatmap/sweep, spoofing candidates, hidden-liquidity candidates | candidate evidence is not proof of market-maker intent; exact live/frozen projection must be traced | SURFACE_ADAPTER / DISCOVER |
| Order Flow / Absorption | temporal order flow, CVD, price-CVD divergence candidates, absorption candidates, order-flow patterns | candidate evidence is not a return prediction or proof of iceberg actor | SURFACE_ADAPTER |
| Derivatives Intelligence | funding, OI, basis, crowding and OI/price dynamics | derivatives context is evidence, not an automatic contrarian trade command | SURFACE_ADAPTER |
| Smart Money / On-chain | exchange inflow/outflow anomalies, large-transfer clusters, wallet cohorts, Bitcoin network context | cohort performance is not actor identity/future return; flow context is not price direction | SURFACE_ADAPTER / RESEARCH_ONLY depending source |
| Event-Driven Risk | structured event calendar, news evidence, event-risk states, circuit breaker | event risk is context/veto, not directional price truth | SURFACE_DIRECT / SURFACE_ADAPTER |

The M6 Confluence Matrix already uses the target family priors:
- Geometry 20%;
- Liquidity 25%;
- Order Flow / Absorption 25%;
- Derivatives 15%;
- On-chain 15%.

Its canonical semantic is `weighted_support_opposition_points_not_probability`; probability remains `not_calibrated`; Event Risk remains outside the 100-point score; the matrix itself has no automatic production activation authority.

Therefore a frontend that shows only a thin forecast sentence would materially under-surface the accepted backend architecture.

### Capability pipeline audit

For every major engine/family M1 must record five separate stages instead of collapsing them into "data exists / does not exist":

1. ENGINE — analysis/contract implementation exists;
2. LIVE_SOURCE — current source collection exists and has freshness/quality truth;
3. PERSISTED_EVIDENCE — exact PIT/frozen evidence is stored;
4. PRODUCT_PROJECTION — safe read-only adapter/API exists;
5. UI_SURFACE — the new frontend actually exposes it.

A missing stage 4 or 5 must be classified as an adapter/product gap, not as missing stage 1-3 evidence.

## 4. Product Gap Ledger

| ID | Desired capability | Current truth | Gap | Class | Required next action |
|---|---|---|---|---|---|
| GAP-001 | Light-first final visual system | current deployed shell is dark | final visual foundation not implemented | ADD_PRESENTATION | user visual decisions -> M2 foundation |
| GAP-002 | User-approved final IA | current UI has 8 routes | old 8-route lock is superseded for new frontend | ADD_PRESENTATION | M1 product decision sessions |
| GAP-003 | Broad live Intelligence timeline | feed exists but event kinds are forecast_issued/resolved | liquidity/order-flow/derivatives/event/capital/system events not proven in one canonical timeline | ADAPT/DISCOVER | define event-source adapters; never infer |
| GAP-004 | Intelligence story/threading | no verified thread relation contract | grouping/causality metadata absent | ADAPT | add canonical presentation relation metadata |
| GAP-005 | Turkish human narrative | structured facts exist; deterministic/LLM narrative contract not canonical | versioned renderer/fact validation absent | ADD_PRESENTATION | M3 Narrative Layer |
| GAP-006 | Visual entry/target/invalidation | signal geometry already exists | chart binding/render schema needs standardization | ADAPT | Visual Evidence Contract |
| GAP-007 | Visual FVG/BPR/BOS/CHoCH/sweep regions | methodologies/evidence exist in repo, but exact product coordinate contract not yet proven | renderable coordinates/provenance may be incomplete per evidence type | DISCOVER | evidence-type-by-type coordinate audit |
| GAP-008 | Frozen chart | frozen candle bundle exists | need explicit provenance contract for chart renderer | ADAPT | bind chart to signal bundle/snapshot identity |
| GAP-009 | Frozen order book in Proof | Market Tape stores identified order-book rows; Decision Proof has ORDER_BOOK domain | exact proof->snapshot binding and UI-level bid/ask contract not yet proven | DISCOVER/ADAPT | trace evidence identity to snapshot and expose read model |
| GAP-010 | Archive server filters | proof wall exists | only limit/offset query verified | ADAPT | symbol/timeframe/date/status/outcome filters |
| GAP-011 | Stable archive navigation | ordering is stable within query but offset can shift as new rows arrive | deterministic user navigation across inserts | ADAPT | keyset/cursor data layer |
| GAP-012 | Deep links/refresh persistence | current SPA route state is primarily in-memory | canonical URL state missing | ADD_PRESENTATION | M2 routing/state |
| GAP-013 | Multi-axis truth states | backend has several typed status concepts | frontend lacks one normalized multi-axis presentation contract | ADD_PRESENTATION | M2 data normalization |
| GAP-014 | Common data resilience | endpoints exist | shared schema validation/cancel/retry/stale/error policy not formalized | ADD_PRESENTATION | M2 Data Access foundation |
| GAP-015 | Then-vs-Now archive compare | proof + outcomes exist | dedicated comparison read model/UI not canonical | ADAPT | compose identity-safe comparison |
| GAP-016 | Notification attention model | alert surface exists | feed vs interrupt semantics not unified | ADAPT/ADD_PRESENTATION | M5 notification projection |
| GAP-017 | Human <=10-second evidence | WC5 engineering accepted | human usability remains NOT_MEASURED | NOT_AVAILABLE | fixed-protocol formative + final studies |
| GAP-018 | Broad edge/performance conclusions | performance infrastructure exists | WC2/WC3 sufficiency blockers remain | NOT_AVAILABLE | display INSUFFICIENT_EVIDENCE until canonical readiness |
| GAP-019 | Real venue execution evidence | WC6 remains external dependency | no real venue evidence | NOT_AVAILABLE | do not represent local simulation as venue truth |
| GAP-020 | Executable real-money controls | REAL_CAPITAL=0 | no authority and intentionally prohibited | NOT_AVAILABLE | never add real Buy/Sell execution surface |
| GAP-021 | Full backend-capability surfacing audit | accepted intelligence/capital/research modules exceed current product projections | some accepted capability can be mistaken for "missing data" because no read model/UI exists | ADAPT/DISCOVER | classify every user-relevant accepted capability as SURFACE_DIRECT / SURFACE_ADAPTER / ADVANCED_ONLY / RESEARCH_ONLY / INTERNAL_ONLY / NOT_AVAILABLE |
| GAP-022 | Rich live Intelligence Feed | Decision Feed is currently forecast-issued/resolved while many accepted engines are not exposed as live feed | machine observations are hidden behind static/catalog/proof layers | ADAPT | build canonical read-only event projections for real liquidity/order-flow/derivatives/event-risk/on-chain/regime/data-quality/capital events; no inferred/fake events |
| GAP-023 | Canonical three-vault forward virtual-capital runtime | Core forward execution engineering exists; Core/Tactical/Opportunity allocator contracts + three-vault sizing/R22/R21 primitives exist | no single canonical runtime currently advances Epoch 2 R22/R21 for all three vaults; existing WC2 runtime is CORE/4h and journal-isolated | ADAPT | build/accept per-vault forward execution adapters over one canonical Epoch 2 transaction/accounting path; reuse Core rail, add Tactical 1m/5m and Opportunity recovery rails |
| GAP-024 | Capital events inside Intelligence Feed | Epoch 2/R22/WC2 decisions and fills exist in separate stores/read models | user cannot see WHY virtual capital held/deployed as part of the live story | ADAPT | add exact identity-bound capital timeline projection: ELIGIBLE/HOLD/BLOCK/SIZED/EXECUTED/EXITED/accounting-result events |
| GAP-025 | Zero-activity diagnosability | HOLD_CASH is valid but prolonged inactivity can be indistinguishable from a broken bridge in the UI | user may see idle capital without knowing whether no setup or subsystem gap caused it | ADAPT/ADD_PRESENTATION | expose decision cadence, candidates scanned, blockers, last eligible event, last executed simulation and data-quality reason without forcing trades |
| GAP-026 | Five-layer intelligence surfacing | backend implements the target Geometry/Liquidity/OrderFlow/Derivatives/On-chain evidence families plus Event Risk | current live feed/product projections expose only a fraction of this stack | ADAPT/DISCOVER | complete ENGINE -> LIVE_SOURCE -> PERSISTED_EVIDENCE -> PRODUCT_PROJECTION -> UI_SURFACE audit for every family and surface all safe accepted evidence |
| GAP-027 | Market-maker-style candidate semantics | spoofing/hidden-liquidity/absorption/flow engines exist | naive copy could overclaim manipulation, actor identity or causality | ADD_PRESENTATION | preserve candidate/uncertainty semantics in SIMPLE/PRO copy; never translate candidate into "market maker definitely did X" |
| GAP-028 | Confluence user presentation | exact 20/25/25/15/15 priors exist | score may be misread as probability or "80 means 80% accuracy" | ADD_PRESENTATION | show support/opposition/coverage/quality/freshness separately; label score as evidence confluence, never probability |

## 5. Temporal integrity observations

Already strong:
- FrozenSignalCard carries as_of_ms, frozen_at_ms, source_cutoff_open_time_ms.
- Decision Proof carries issued_at_ms and source_as_of_ms.
- Decision Proof slices carry market_available_at_ms and observed_at_ms.
- Market Tape distinguishes event_at_ms, source_timestamp_ms and ingested_at_ms.
- Provider/cold/event subsystems persist snapshot/coverage time.

M1 requirement:
- create a frontend temporal-field map before M2 normalization;
- never collapse all timestamps into one generic "time" field;
- NOW data must not enter THEN views.

## 6. Identity/lineage observations

Already strong:
- exact lowercase SHA256 forecast lookup;
- signal_freeze_identity route;
- proof identity;
- confluence/event-context identities;
- evidence identities;
- snapshot identities in runtime subsystems;
- outcome identities;
- WC2 exact forecast actionability.

M1 requirement:
- document canonical cross-surface identity graph;
- no symbol/time heuristic join;
- future story/thread IDs must be explicit presentation lineage, not inferred causality.

## 7. Current frontend baseline: retain vs replace

Retain:
- truthful read-only API behavior;
- Turkish-first copy principles;
- Intelligence Feed concept;
- Decision Proof drill-down;
- frozen evidence;
- Epoch 2 truth;
- fail-closed unavailable states;
- no fake probability/latency/ONLINE claims.

Replace/rethink:
- dark visual target;
- GALACTECH-as-product branding;
- assumption that the 8 current routes remain final;
- equal visual weight for technical/system data;
- offset-only archive UX;
- in-memory-only navigation behavior;
- proof visualization that does not yet show all claimed geometry directly on the frozen chart.

## 8. M1 unresolved product decisions

Do NOT re-ask already locked user inputs.

Ask the user only unresolved decisions, in small sessions.

Recommended sequence:
1. Home: what must be visible in the first ten seconds?
2. Primary navigation: final number and meaning of sections.
3. Intelligence: feed density, story behavior, SIMPLE/PRO/PROOF interaction.
4. Markets: workspace composition and chart interaction.
5. Proof: visual hierarchy and audit-depth exposure.
6. Capital: visible vs secondary paper metrics.
7. Archive: table/card/detail interaction.
8. Performance: beginner vs scientific layers.
9. Visual refinement: exact palette/typography/motion after foundation constraints.

## 9. M1 current conclusion

The backend is already substantially capable of supporting a serious product frontend.

The largest gaps are not "invent a new trading system." They are:
- frontend information architecture;
- product-friendly query/read models;
- comprehensive surfacing of accepted backend capability rather than treating adapter gaps as missing data;
- broader canonical intelligence timeline;
- the missing canonical three-vault forward paper-capital runtime that turns already-accepted Core/Tactical/Opportunity eligibility, sizing, simulated execution and R22/R21 accounting primitives into one active Epoch 2 experiment;
- identity-bound capital events in the live Intelligence Feed;
- renderable visual-evidence contracts;
- proof-bound microstructure exposure;
- stable archive querying;
- resilient client data layer;
- measured human usability.

No current evidence supports fabricating those missing contracts in the UI.

Next action after this baseline is accepted:
- formalize the identity graph and temporal map;
- run the first unresolved user product-decision session;
- freeze IA only after those decisions.

## 10. M1 PASS status

M1 is **ACTIVE and NOT YET PASS**.

Already established:
- initial mechanically verified product API/capability baseline;
- initial Product Gap Ledger;
- known frozen-signal / Decision-Proof / Market-Tape identity and temporal primitives;
- explicit REUSE / ADAPT / DISCOVER / NOT_AVAILABLE / ADD_PRESENTATION classification;
- no-fabrication boundaries for visual evidence, intelligence expansion, archive navigation and microstructure proof.

Still required before M1 can PASS:
- complete canonical cross-surface identity graph;
- complete frontend temporal-field map for critical product surfaces;
- completeness audit against every current product API and major evidence surface;
- remaining product-decision sessions, asked in small groups without re-asking locked decisions;
- user-approved final information architecture;
- final check that every planned visual/product feature is backed by REUSE/ADAPT truth or explicitly marked DISCOVER/NOT_AVAILABLE;
- accepted-backend surfacing audit complete, with no user-relevant accepted capability silently dropped because an adapter is missing;
- canonical three-vault forward-paper execution contract specified before M2 freezes Capital/Feed data dependencies, including Core reuse, Tactical 1m/5m execution, Opportunity recovery execution, fixture-vs-forward evidence separation, and atomic R22/R21 Epoch 2 accounting.

M2 Application Foundation must **not** freeze routes or final shell information architecture before these items pass.
