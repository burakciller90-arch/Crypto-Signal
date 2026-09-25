# GALACTECH — Crypto Signal Frontend Master Roadmap v1.0

Status: CANONICAL FRONTEND PROGRAM ARCHITECTURE — M0 PASS / M1 ACTIVE  
Owner context: GALACTECH company / Crypto Signal product-project  
Safety: REAL_CAPITAL=0 / read-only product surface  
Execution model: M0 -> M7 with screen-by-screen completion loops

## 0. Authority and supersession

This document governs new Crypto Signal frontend/product work.

It supersedes older frontend-only assumptions where they conflict, including:
- prior locked navigation count;
- prior dark-theme visual target;
- prior brand interpretation that treated GALACTECH as the product name;
- any instruction to patch the existing GALACTECH V2 shell into the final design.

It does NOT supersede scientific, persistence, evidence, replay, immutable-history, capital-safety or production-authority invariants from the governing repository documents.

Canonical brand hierarchy:
- Company: GALACTECH
- Product/project: Crypto Signal

The current deployed GALACTECH V2 surface is a truthful production baseline and fallback, not the final frontend target.

### Historical frontend artifact handling

Repository history intentionally retains accepted frontend/deployment evidence, including `docs/GALACTECH_*.md`, older `POST_V1_*.md` acceptance records and frontend sections inside older v1.1 roadmaps.

Rules:
- historical acceptance remains audit evidence and must not be rewritten merely to match the new design;
- historical acceptance does **not** make an old theme, route count, brand interpretation or screen hierarchy current product authority;
- when an old frontend assumption conflicts with this roadmap/M0/M1, the old assumption is historical and the canonical frontend program wins;
- the deployed GALACTECH V2 surface remains production truth until controlled cutover, while the target Crypto Signal frontend remains a separate in-progress program;
- scientific, evidence, persistence, replay, capital-safety and production-authority rules continue to come from their governing contracts and are never weakened by frontend supersession.

## 1. Program objective

Crypto Signal must compress a complex market-intelligence machine into a calm decision surface.

The user should be able to answer the highest-priority questions in roughly ten seconds:
- What is happening?
- Does the system currently see a trade, watch state, or hold/cash state?
- Which asset and direction matter?
- What is the trigger or decision-change condition?
- What is the main risk?
- Why?
- What evidence supports or contradicts the decision?

Technical depth must remain available on demand through exact evidence and frozen point-in-time proof.

## 1.1 Two signature product pillars

### Pillar A — Live Intelligence Feed
The primary surface is not a thin signal list. It is an evidence-bound live intelligence timeline that can project accepted market observations, forecast/decision state, contradiction/risk, evidence availability changes, capital decisions and later resolution.

Target card hierarchy:
- exact event time + asset/timeframe + truthful state badge;
- one human-readable system sentence generated only from canonical facts;
- SIMPLE explanation;
- PRO technical evidence;
- trigger / target / invalidation when canonically available;
- exact evidence-status summary;
- **KANITI GÖR** action into frozen Proof;
- capital consequence when exact lineage exists.

The feed should feel alive through new real events and restrained micro-motion, never through synthetic chatter.

### Pillar B — Virtual Capital / Smart Capital
Epoch 2 is a first-class product system:
- 1,000 USDT canonical paper capital;
- Core 600;
- Tactical 300;
- Opportunity Reserve 100;
- exact per-vault + consolidated accounting;
- decision/sizing/fill/cost/outcome lineage;
- visible explanations for HOLD / BLOCK / ELIGIBLE / EXECUTED states.

Capital is not a decorative balance widget. The product must show what the machine did with simulated capital and why.

Program thesis:

**See what the machine sees. Understand why. See what simulated capital did. Open the proof in one action. Preserve history immutably.**

## 2. Global execution rules

### 2.1 ASK BEFORE LOCK
User-facing product decisions are not permanently locked without user input.

Examples:
- information architecture;
- number and meaning of primary sections;
- visual character;
- information density;
- what belongs on Home;
- terminology;
- how SIMPLE/PRO/PROOF is exposed.

### 2.2 DECISION RIGHTS
User product decisions and engineering implementation decisions are separate.

User decides product intent and experience. Engineering owns implementation details such as:
- DTO/internal schema mechanics;
- state-management technique;
- request orchestration;
- caching;
- rendering strategy;
- component internals;
- pagination implementation;
- test architecture;
- accessibility implementation;
- performance optimization.

### 2.3 BACKEND BEFORE UI
No user-facing feature is treated as real until its backend evidence/contract is mechanically identified.

### 2.4 NO FAKE UI
Unavailable evidence is displayed as unavailable. Frontend does not invent:
- prices;
- probabilities;
- targets;
- risk scores;
- health states;
- visual annotations;
- order-book snapshots;
- causality.

### 2.5 ONE SCREEN AT A TIME
Each major screen follows:

truth discovery -> open product decisions -> wireframe -> user approval -> visual prototype -> user approval -> just-in-time adapter if required -> real data -> screen acceptance -> formative usability -> close screen -> next screen.

The target is 100% accepted screens, not many 80%-finished screens.

### 2.6 FRONTEND AUTHORITY BOUNDARY
Crypto Signal frontend is a read-only product surface.

It has no credential, exchange-order dispatch, withdrawal, leverage, borrowing or REAL_CAPITAL authority.

The UI must not imply backend authority that does not exist. A decorative Buy/Sell control that appears executable is prohibited unless a future explicitly authorized sandbox-only contract exists and is truthfully labelled.

## 3. M0 — Product Constitution

M0 is the permanent frontend constitution.

### 3.1 Known user decisions

Already locked:
- GALACTECH is the company.
- Crypto Signal is the product/project.
- Turkish-first user experience.
- Light-first overall visual direction.
- Futuristic / advanced-technology / command-center feeling.
- Calm and legible rather than visually noisy.
- Trader should understand the decision surface in about ten seconds.
- Technical depth must be available without forcing it on the first layer.
- Intelligence is a central product value.
- Evidence must be real, frozen where applicable, and inspectable.
- Analysis should be shown on the chart when exact visual evidence exists.
- Historical archive is persistent.
- Losses and invalidations are not hidden.
- Missing evidence is not invented.
- REAL_CAPITAL=0.

Open product decisions remain open until explicitly decided.

### 3.2 Multi-axis truth state contract

A single overloaded UI state enum is prohibited. Canonical truth is represented on separate axes.

#### Availability
- READY
- EMPTY
- PARTIAL
- UNAVAILABLE

#### Freshness
- CURRENT
- STALE
- UNKNOWN

#### Quality
- HEALTHY
- DEGRADED
- UNKNOWN

#### Evidence sufficiency / measurement
- SUFFICIENT
- INSUFFICIENT_EVIDENCE
- NOT_MEASURED
- NOT_APPLICABLE
- UNKNOWN

Presentation states may be derived from these axes, but derived presentation must never erase the underlying truth.

Examples:
- STALE + PARTIAL remains both stale and partial.
- NOT_MEASURED must never render as zero.
- EMPTY is not automatically an error.
- Missing/unsupported evidence is not neutral evidence.
- INSUFFICIENT_EVIDENCE is not equivalent to poor performance.

### 3.3 Temporal Integrity Contract

Crypto Signal is point-in-time first.

Every canonical product datum should preserve the relevant time semantics where the source supports them:
- event_time / event_at_ms;
- source_timestamp;
- market_available_at;
- observed_at / ingested_at;
- as_of;
- issued_at;
- frozen_at;
- evaluated_at / resolved_at;
- coverage start/end;
- provider/exchange time where relevant.

Rules:
1. Later/live data must never be inserted into an issuance-time Decision Proof.
2. UI must distinguish event time from observation/ingestion time when the distinction matters.
3. All timestamps are transported canonically; locale/timezone formatting is presentation-only.
4. THEN views use issuance-time/frozen evidence only.
5. NOW/outcome views may use later evidence but cannot mutate THEN.
6. When temporal semantics are missing, UI must not infer them from proximity.

### 3.4 Entity Identity & Lineage Contract

UI joins use canonical immutable identities, never heuristics.

Forbidden authority:
- same symbol + nearby timestamp;
- same direction + nearby timestamp;
- similar price;
- UI guess that two records are probably the same decision.

Expected canonical lineage includes, where available:
- signal_freeze_identity;
- forecast_identity;
- proof_identity;
- evidence/slice identity;
- confluence identity;
- event-context identity;
- frozen snapshot/bundle identity;
- outcome identity;
- paper/capital cycle identity;
- story/thread identity when introduced.

Every cross-screen navigation must preserve the exact identity that proves the relationship.

### 3.5 Scientific UI invariants

- Confluence score != calibrated probability.
- Historical win rate != calibrated probability.
- Backtest != untouched-forward evidence.
- Missing evidence is never invented.
- Losers, invalidations, ambiguity and abstention remain visible.
- Historical issuance truth is never rewritten by later outcomes.
- Paper capital != real capital.
- Frontend cannot be more certain than backend evidence.
- LLM/narrative layers cannot create numeric or directional truth.
- REAL_CAPITAL remains 0.

### 3.6 Desktop workspace invariant

Primary desktop workspaces should behave like an application rather than an infinitely scrolling marketing page.

Preferred contract:
- bounded application shell;
- primary views target 100dvh where practical;
- feed scrolls in its own viewport;
- tables use controlled viewport/pagination;
- archive uses deterministic pagination;
- proof workspace may use controlled internal scrolling.

Exceptions require explicit UX justification.

### 3.7 M0 PASS gate

M0 passes only when:
- brand hierarchy is documented;
- Decision Rights are documented;
- multi-axis truth states are documented;
- temporal integrity rules are documented;
- identity/lineage rules are documented;
- authority boundary is documented;
- scientific UI invariants are documented;
- known user decisions are recorded without re-asking them.

## 4. M1 — Discovery & Product Architecture

M1 answers: what does the backend truthfully support, what is missing, and what should the user-facing information architecture be?

Work packages:
- backend capability inventory;
- current frontend autopsy;
- capability -> UI mapping;
- Product Gap Ledger;
- exact identity/lineage map;
- temporal-field map;
- open product-decision sessions;
- final information architecture.

Gap classes:
- REUSE: contract is already suitable.
- ADAPT: truth exists but needs a read-only product adapter or query shape.
- DISCOVER: underlying data may exist but exact product contract has not been proven.
- NOT_AVAILABLE: evidence does not exist; UI must show unavailable rather than fabricate.
- ADD_PRESENTATION: canonical facts exist; a non-authoritative presentation layer is needed.

M1 uses just-in-time contract development. No speculative backend expansion.

### M1 PASS gate
- capability matrix covers every current product API and major evidence surface;
- Gap Ledger classifies each planned frontend capability;
- exact identity joins are documented;
- temporal semantics are documented for critical surfaces;
- no planned visual feature depends on unproven data without a DISCOVER/NOT_AVAILABLE marker;
- user-approved information architecture exists before M2 shell routes are frozen.

## 5. M2 — Application Foundation

M2 builds a blank but production-grade application skeleton.

### 5.1 Routing and persistent state
Requirements:
- deep links;
- refresh-safe selected asset/timeframe where useful;
- archive filters and position;
- proof identity route;
- browser back/forward behavior;
- modal/drawer routing policy.

### 5.2 Data Access & Resilience Foundation
Common data layer must define:
- response schema/type validation;
- request cancellation;
- request deduplication;
- timeout policy;
- retry/backoff policy;
- error normalization;
- stale-data behavior;
- loading/empty/degraded semantics;
- polling/SSE/WebSocket strategy per surface;
- reconnect behavior;
- read-only enforcement.

Technology choice is an engineering decision.

### 5.3 Visual Foundation
Before screen-specific visual work:
- typography hierarchy;
- spacing scale;
- radius philosophy;
- surface hierarchy;
- information-density classes;
- borders/elevation;
- semantic status colors;
- focus states;
- grid;
- motion principles.

Final aesthetic polish comes later.

### 5.4 Accessibility foundation
Accessibility is cross-cutting from first component:
- keyboard navigation;
- focus management;
- reduced motion;
- contrast;
- screen-reader semantics;
- non-color-only meaning;
- live-region discipline;
- font scaling.

### 5.5 Performance foundation
Set budgets/fixtures for:
- initial shell load;
- request fan-out;
- DOM growth;
- feed retention;
- chart rendering;
- animation;
- long-running sessions;
- memory.

### 5.6 Component primitives
Examples:
- Panel;
- TruthState;
- AssetSelector;
- Tabs;
- Drawer;
- Modal;
- Tooltip;
- DataTable;
- EmptyState;
- ErrorState;
- EvidenceBadge.

### M2 PASS gate
- deep-link refresh PASS;
- back/forward state PASS;
- truth-state fixtures PASS;
- API schema/error fixtures PASS;
- keyboard-navigation baseline PASS;
- reduced-motion baseline PASS;
- performance-budget baseline recorded;
- blank application shell renders without production writes.

## 6. M3 — Intelligence Core

M3 builds the first complete product loop: intelligence -> explanation -> Home decision surface.

### 6.1 Event taxonomy
Canonical presentation taxonomy may include:
- liquidity;
- order flow;
- derivatives;
- on-chain;
- event risk;
- forecast;
- decision;
- invalidation;
- resolution;
- capital;
- data quality;
- system risk.

Backend truth decides which categories can be populated.

### 6.2 Importance / attention
Presentation attention levels may include:
- INFO;
- WATCH;
- ACTIONABLE;
- CRITICAL;
- SYSTEM_RISK.

These are attention semantics, not probability/confidence scores.

### 6.3 Threading / stories
Grouping is allowed only with canonical presentation metadata.

Required rule:
- frontend may group;
- frontend may not invent causal meaning.

Preferred future metadata:
- event_identity;
- thread/story_identity;
- relation_type;
- importance;
- supersedes/display relationship.

Time proximity alone is not authority to claim that one event confirms or causes another.

### 6.4 Narrative Layer
Pipeline:

canonical immutable facts
-> schema-validated structured narrative input
-> deterministic template
-> optional local LLM rewrite
-> fact validator
-> user-facing Turkish copy

Narrative metadata should include:
- narrative_schema_version;
- template_version;
- renderer_version;
- optional model/version identity when an LLM rewrite is used.

Rules:
- deterministic fallback always exists;
- narrative is presentation, not canonical evidence;
- LLM cannot create price, target, probability, risk score, direction, evidence selection or causal relation;
- archived canonical facts never change because a future renderer changes.

### 6.5 SIMPLE / PRO / PROOF
Same truth may have three depths:
- SIMPLE: what is happening and what should the user understand?
- PRO: technical evidence/context.
- PROOF: exact frozen evidence, identities, timestamps and provenance.

Whether these are tabs, expanders or another interaction is a user product decision.

### 6.6 Home / Command Center
Home is designed and accepted before advancing to other main screens.

Home must visibly unite the two signature pillars:
- Intelligence Feed is the dominant workspace;
- Capital Pulse shows current Epoch 2 consolidated + vault state from real read-only truth;
- a feed event may show a capital consequence only through exact canonical lineage;
- the Home surface must never reduce virtual capital to a static "1,000 USDT" card.

### 6.7 Rich Intelligence event projection — mandatory, not deferred

M3 must not stop at FORECAST_ISSUED / FORECAST_RESOLVED.

Before M3 PASS, build/accept the read-only event projection architecture capable of surfacing, where canonical source evidence exists:
- liquidity / sweep / liquidation state;
- order-flow / CVD / absorption;
- derivatives context;
- regime / trend / volatility;
- event risk;
- forecast issued / changed-state / resolved;
- actionability;
- capital eligibility / hold / block / sizing / simulated execution / exit;
- data-quality/system degradation.

An event category remains absent only when its canonical source cannot be established. "No product adapter yet" is an implementation gap and must not be represented as "no backend data."

### 6.8 Capital activity visibility

M3 does not wait for the full Capital Center to make capital behavior understandable.

Home/Feed must expose:
- last capital decision;
- vault;
- action/state;
- exact reason codes translated into human copy;
- last simulated execution when one exists;
- blocked/hold reason when no execution exists;
- candidate/decision cadence health so long inactivity is diagnosable.

No forced trade is allowed merely to produce activity.


### 6.9 Formative 10-second test
Use a fixed scenario dataset and a documented timer protocol.

Measure whether the tester can answer without prior prompting:
- trade/watch/hold state;
- asset;
- direction;
- trigger/change condition;
- main risk;
- short reason.

Owner-only testing is recorded as OWNER_ACCEPTANCE, not generalized human-usability evidence.

### M3 PASS gate
- event taxonomy contract PASS;
- narrative deterministic-fallback PASS;
- no-narrative-hallucination fixtures PASS;
- Home uses real backend/fixture truth, not invented demo values;
- formative 10-second test result recorded;
- user approves Home before M4 becomes the active screen frontier.

## 7. M4 — Evidence Core

M4 makes Crypto Signal prove what it says.

### 7.1 Evidence discovery
Mechanically determine which exact visual evidence exists:
- frozen OHLC;
- entry/trigger geometry;
- invalidation;
- targets;
- key levels;
- FVG/BPR coordinates;
- BOS/CHoCH/structure coordinates;
- liquidity sweep coordinates;
- absorption evidence;
- CVD relation;
- liquidation clusters;
- order-book snapshot;
- event markers;
- provider/venue identity.

### 7.2 Visual Evidence Contract
A production annotation must bind at minimum, when applicable:
- annotation_identity;
- schema_version;
- evidence_identity;
- type;
- symbol;
- timeframe;
- market_type;
- venue/exchange/provider;
- source_snapshot_identity;
- coordinate_semantics;
- start/end time;
- price low/high or exact level;
- verdict;
- source;
- frozen_at/as_of.

A price coordinate without market/symbol/time/source identity is not sufficient proof.

### 7.3 Frozen chart
Frozen chart must be sourced from the issuance-time point-in-time dataset or persisted frozen bundle.

It must never be implemented as "current chart shifted to the past."

### 7.4 Frozen microstructure / order book
If canonical point-in-time order-book evidence exists, product contract should expose:
- provider/exchange;
- market type;
- symbol;
- event/source/ingestion timestamps;
- snapshot identity;
- bid/ask levels and quantities;
- imbalance fields when canonically measured;
- adapter/schema version.

If the exact historical snapshot is absent, display that it is unavailable. Never reconstruct fake historical depth.

### 7.5 Decision Proof
Proof preserves two worlds:
- THEN: what was known at issuance/freeze time;
- NOW: later outcome/resolution.

NOW cannot mutate THEN.

### 7.6 Proof formative comprehension
Fixed proof fixture and documented questions:
- What was the decision?
- What supported it?
- What contradicted it?
- What was insufficient?
- When was it frozen?
- What happened later?

### 7.7 Markets
Markets UI is designed after visual-evidence capability is known, not before.

### M4 PASS gate
- every rendered annotation is evidence-bound;
- frozen-chart provenance PASS;
- no-current-data-in-past-proof fixture PASS;
- order-book unavailable behavior PASS where no snapshot exists;
- proof identity lineage PASS;
- formative proof comprehension result recorded.

## 8. M5 — Memory, Capital & Trust

### 8.1 Archive / Proof Wall
Requirements:
- backend-persistent history;
- server-side filtering;
- deterministic stable ordering;
- cursor/keyset pagination preferred in data layer;
- UI may display page-like controls without relying on unstable offset semantics;
- deep-link state;
- winner/loser/invalidated/expired/ambiguous/abstain/not-evaluable/unresolved remain visible.

### 8.2 THEN <-> NOW
Archive detail exposes issuance truth beside later outcome without rewriting issuance.

### 8.3 Capital Center — second signature surface
Paper Fund is professional but always visibly PAPER.

Capital Center is a mandatory flagship surface, not a secondary portfolio widget.

Required first-class areas:
- consolidated Epoch 2 state;
- three independent vault workspaces;
- current cash / NAV / exposure / PnL / drawdown / costs where canonically measured;
- open simulated positions;
- exact paper transaction history;
- allocation/eligibility decision reasons;
- sizing state and reason;
- before -> decision -> fill -> after accounting lineage;
- link from every eligible trade/fill back to forecast + Decision Proof;
- clear separation of measured, unavailable and not-yet-measured metrics.

Possible truthful fields when evidence exists:
- NAV;
- cash;
- exposure;
- positions;
- allocated capital;
- risk budget;
- PnL;
- fees/slippage;
- drawdown;
- equity;
- vault state;
- allocation explanation.

### 8.3.1 Tactical Paper Execution Rail — mandatory backend/product closure

The current repository already has:
- Tactical 1m/5m evidence contract;
- Smart Capital Allocator Tactical eligibility;
- vault-aware Position Sizing Bridge;
- vault-aware R22 Transaction Tape;
- three-vault R21 Epoch 2 accounting.

The accepted automatic forward execution runtime is currently CORE/4h only.

Therefore a dedicated **Tactical 1m/5m forward-only virtual-paper execution bridge** is a required product closure, not a future nice-to-have.

Acceptance must prove:
- forward-only/no historical backfill;
- exact Tactical evidence lineage;
- Event Risk gate;
- allocator eligibility;
- explicit risk/sizing evidence;
- deterministic simulated cost/fill policy;
- exact Tactical vault mutation only;
- R22 + R21 atomic/auditable persistence;
- restart/idempotence/duplicate prevention;
- HOLD/BLOCK outcomes persisted/exposed;
- no leverage, borrowing, martingale or real-order authority;
- REAL_CAPITAL=0.

The rail must be **capable of trading from its activation day when a canonical eligible setup occurs**. It must not fabricate or force a trade if no setup passes.

### 8.3.2 Capital -> Intelligence timeline

Every canonical capital state transition should have a read-only product event projection:
- candidate observed;
- vault eligible;
- HOLD_CASH;
- risk blocked;
- sizing blocked/available;
- simulated BUY/REDUCE/EXIT;
- accounting snapshot updated;
- position closed/outcome available.

This turns capital management into an auditable live story rather than a separate silent database.

### 8.4 Performance & Trust
First question: is there enough evidence?

Only expose metrics supported by the accepted evidence class and scientific review.

Backtest, walk-forward and LIVE_UNTOUCHED_FORWARD remain visibly separate.

### 8.5 Contextual education
Existing education capability should be reused; final placement is a product decision.

### 8.6 Health / operational truth
Normal layer: concise health/quality statement.
Advanced layer: exact technical evidence.

### 8.7 Notifications
Feed event != notification.
Interruption is reserved for attention states that justify it.

### M5 PASS gate
- archive stable-order/persistence PASS;
- backend-capability surfacing audit has no unexplained user-relevant omissions;
- Tactical 1m/5m virtual-paper rail accepted or explicitly blocked by a proven canonical prerequisite rather than deferred;
- Capital Center shows exact three-vault state and transaction lineage;
- Intelligence Feed receives exact capital-event projections;
- prolonged zero-trade state is diagnosable as genuine HOLD/BLOCK/data issue rather than silent inactivity;
- THEN/NOW immutability PASS;
- paper/real authority separation PASS;
- evidence-class separation PASS;
- missing scientific metrics fail closed;
- health UI does not claim ONLINE/HEALTHY without measured truth.

## 9. M6 — Hardening

Hardening is continuous from M2; M6 is exhaustive acceptance.

Coverage:
- responsive acceptance matrix: minimum supported desktop, common laptop, 1080p desktop, 1440p/4K class, tablet, mobile;
- keyboard/focus/screen-reader/reduced-motion;
- large feed/archive performance;
- 1000+ event stability fixture;
- long-running session;
- state persistence;
- error/reconnect behavior;
- scientific truth audit.

Scientific audit checks:
- fake probability;
- fake precision;
- fake latency;
- stale shown healthy;
- missing shown as zero/neutral;
- backtest/live mixing;
- paper/real mixing;
- hidden losses;
- historical mutation;
- UI certainty exceeding backend.

### M6 PASS gate
All required automated and manual hardening checks pass and a release-candidate identity is recorded.

## 10. M7 — Validation & Controlled Cutover

### 10.1 Preview
New frontend runs on a preview route such as /next while current production remains available.

### 10.2 Final 10-second protocol
Use fixed scenarios, no pre-coaching, explicit timer method and recorded answers.

Classify evidence honestly:
- OWNER_ACCEPTANCE: owner-only test;
- HUMAN_USABILITY_EVIDENCE: test with defined participant protocol/population.

Do not relabel owner acceptance as broad human evidence.

### 10.3 Final Proof comprehension
Repeat the fixed protocol on release candidate.

### 10.4 Operational acceptance
Verify API/runtime/archive/proof/market/paper/health truth.

### 10.5 Regression
Confirm no unintended mutation of scientific/runtime evidence collection.

### 10.6 Cutover
Only after all gates:
- preview becomes root;
- prior surface may remain at /legacy for rollback;
- rollback path is documented.

### M7 PASS gate
Production root is cut over only after all required gates pass on the exact release candidate.

## 11. Screen-by-screen implementation record

Every screen/work package must carry:
- roadmap ID;
- exact product decisions;
- backend sources;
- Gap Ledger entries;
- required adapters;
- acceptance fixtures;
- human acceptance state;
- exact PR/commit identity once implemented.

Recommended IDs:
- M1.CAPABILITY
- M1.GAP
- M2.SHELL
- M2.DATA
- M3.NARRATIVE
- M3.HOME
- M4.VISUAL_EVIDENCE
- M4.PROOF
- M4.MARKETS
- M5.ARCHIVE
- M5.CAPITAL
- M5.PERFORMANCE

## 12. Program order

M0 Constitution
-> M1 Discovery
-> M2 Foundation
-> M3 Intelligence Core
-> M4 Evidence Core
-> M5 Memory/Capital/Trust
-> M6 Hardening
-> M7 Validation/Cutover

Do not reopen macro architecture unless a newly discovered backend truth or explicit user decision invalidates it.

The active next frontier after this document is accepted is M1: complete the mechanically verified Backend Capability Matrix + Gap Ledger, then ask only unresolved product questions before freezing information architecture.
