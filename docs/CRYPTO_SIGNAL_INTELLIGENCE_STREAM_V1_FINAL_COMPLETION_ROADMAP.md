# Crypto Signal — Intelligence Stream V1 Final Completion Roadmap

Status: **CANONICAL FINAL COMPLETION AUTHORITY**  
Company: GALACTECH  
Product: Crypto Signal  
Scope: **Close only the remaining deficiencies of the accepted Intelligence Stream V1 vision**  
Safety: **REAL_CAPITAL=0**  
User approval: 2026-09-26

---

## 0. Why this document exists

The original `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md` remains the canonical product-design and interaction vision for Intelligence Stream V1.

Its core product thesis remains unchanged:

> one primary Telegram/WhatsApp-like Intelligence Stream that turns the accepted backend into live, persistent, evidence-bound, story-aware messages with expandable analysis, frozen proof and virtual-capital consequences.

S0-S16 also remain valid historical acceptance records for the components they actually proved.

However, post-cutover live evidence exposed an important distinction:

- generic Stream architecture, UI, story, narrative, evidence-window and transport behavior were accepted;
- isolated/fixture-backed end-to-end acceptance proved those components can work together;
- production cutover proved the Product root and Stream runtime can operate;
- PR #1324 later had to add a missing live production bridge for forward WC2 issuance/resolution;
- current production coverage still does not prove that every user-relevant backend family required by the original roadmap can create genuine live Stream messages.

Therefore this document does **not** invent a new product, new screen architecture or new scientific program.

It exists to close the delta between:

**accepted Stream architecture**

and

**the original promised live product behavior.**

This is the final execution roadmap for that closure.

---

# 1. Locked product definition

The final product remains exactly the one-screen Intelligence Stream.

No new main tabs or permanent product sections are introduced.

The intended user experience is still:

**LIVE MARKET**  
→ **SYSTEM VIEW**  
→ **MATERIAL EVENT**  
→ **MESSAGE**  
→ **EXPAND**  
→ **SIMPLE / PRO / INTELLIGENCE / DECISION / CAPITAL**  
→ **CLICKABLE EVIDENCE**  
→ **FROZEN PROOF**  
→ **STORY CONTINUATION**

The Stream must feel as if Crypto Signal is a disciplined market analyst who:

- watches continuously;
- speaks only when something materially changes;
- remembers what it previously said;
- explains why its view changed;
- exposes exact evidence;
- states what would change its view;
- explains virtual-capital consequences;
- never rewrites a past message to hide a mistake;
- never invents missing evidence;
- never depends on an LLM to create market truth.

---

# 2. Non-negotiable scientific and safety invariants

These rules apply to every phase below.

1. `REAL_CAPITAL=0`.
2. No exchange order authority.
3. No credential authority.
4. No leverage/borrowing/martingale.
5. No historical rich-message backfill.
6. No retroactive creation of a message using information unavailable at its event time.
7. No deletion/rewrite of losses, invalidations, abstains or failed views.
8. Point-in-time truth only.
9. Confluence score is not probability.
10. Untouched-forward evidence is never rewritten to improve apparent performance.
11. Research/shadow evidence cannot silently mutate canonical paper truth.
12. Missing evidence remains explicit.
13. LLM/local-model prose is never numeric/factual authority.
14. Every live Stream message must trace to a canonical persisted source identity.
15. Every drawn historical proof mark must trace to frozen coordinates/identity.
16. If a source is not live or cannot be proven, the product must fail closed rather than fabricate activity.

---

# 3. What is already accepted and must be reused

The following foundations are already implemented and are **not** to be rebuilt from scratch:

- one-panel Stream shell;
- canonical source/message ledger;
- activation boundary;
- append-only immutable messages;
- story identities;
- story state and Change Set;
- Analytical View;
- versioned message materiality policy;
- deterministic Turkish Narrative Plan/renderer;
- optional local-model rewrite adapter;
- Fact Validator / semantic guard;
- realtime SSE;
- reconnect/cursor/catch-up;
- history pagination;
- exact-message lookup;
- search/filter API;
- inline SIMPLE / PRO / INTELLIGENCE / DECISION / CAPITAL sections;
- evidence-window framework;
- drag / resize / minimize / pin / z-order;
- detached proof-window route;
- frozen OHLC proof path;
- Decision Proof lineage;
- sound and notification settings;
- exactly-once new-message sound semantics;
- deep links;
- 1k/10k long-session UI mechanics;
- mobile/desktop responsive acceptance infrastructure;
- canonical three-vault paper-capital primitives and S11 Stream projector code;
- PR #1324 forward production bridge for WC2 issuance/resolution.

The purpose of this roadmap is to **activate, connect, complete and verify** the missing live paths around those foundations.

---

# 4. Current proven production truth

At the time this roadmap is opened:

- the live Stream ledger is activated;
- historical rich backfill is disabled;
- `/api/stream/messages` and `/api/stream/live` are healthy;
- the Product correctly shows an empty ready state when no canonical message exists;
- live Market/Signal collection continues;
- the accepted forward production bridge currently projects WC2 forecast issuance and forecast resolution;
- the latest read-only forward-progress audit observed:
  - 2,794 signal freezes;
  - 28 R20 forecasts;
  - 28 Decision Proofs;
  - 5 resolutions;
  - 28 WC2 cohort forecasts;
  - 0 WC2 cohort executions;
  - 628 signal freezes after the latest forecast;
  - 48 4h signal freezes after the latest forecast;
- therefore Stream emptiness cannot be treated as a frontend defect;
- it must be explained through exact upstream eligibility/projection truth.

This roadmap starts from that evidence.

---

# 5. Final execution sequence

Execute exactly in this order:

**F0 Authority + Gap Reconciliation — PASS**  
→ **F1 WC2 Forward-Liveness Truth — PASS**  
→ **F2 Production Source-to-Message Backbone — PASS**  
→ **F3 Five-Family Live Intelligence Projection — PASS**  
→ **F4 Risk + System Trust Projection — PASS**  
→ **F5 Three-Vault Capital Story — PASS FOR CURRENT FRONTEND SCOPE; LIVE PORTFOLIO/CAPITAL PROOF DEFERRED**  
→ **F6 Exact Frozen Evidence Closure — PASS**  
→ **F7 Guarded Local LLM/Ollama Activation — PASS**  
→ **F8 Real Production Multi-Category E2E Acceptance — PASS**  
→ **F9 Final Real-UI Product Acceptance — ACTIVE**  
→ **F10 Authority Freeze / Closeout**

Do not jump ahead across accepted frontend stages. F5 is accepted only under the revised frontend scope: its implementation and physical activation are complete, while natural live Portfolio/Capital behavior is explicitly deferred to a later dedicated workstream. Do not represent the deferred Capital proof as observed or tested.

---

# 6. F0 — Authority + Gap Reconciliation

## Goal

Create one final mechanical inventory of what the original roadmap promised versus what production can actually emit today.

## Work

Rebuild the six-stage matrix for every Stream-relevant family:

**ENGINE**  
→ **LIVE SOURCE**  
→ **PERSISTED EVIDENCE**  
→ **PRODUCT PROJECTION**  
→ **MESSAGE PROJECTOR**  
→ **LIVE SUPERVISOR/RUNTIME HOOK**

Families to audit:

- Market / Geometry;
- Liquidity;
- Order Flow / CVD / Absorption;
- Derivatives;
- On-chain / network;
- Event Risk;
- Decision;
- Capital;
- Outcome;
- Provider/Data Quality/System.

For each row classify only:

- `LIVE_COMPLETE`;
- `CODE_EXISTS_NOT_LIVE`;
- `PERSISTED_SOURCE_ONLY`;
- `NO_LIVE_SOURCE`;
- `RESEARCH_ONLY`;
- `EXTERNAL_DEPENDENCY`;
- `BLOCKED_BY_CORRECTNESS_DEFECT`.

## Required output

One final source-to-message closure ledger with:

- exact code path;
- exact database/table;
- exact identity key;
- exact projector;
- exact runtime caller;
- current production status;
- missing closure action;
- acceptance test.

## PASS

F0 passes only when no roadmap claim is represented by vague words such as “supported”, “implemented” or “accepted” without identifying whether it is actually live in production.

---

# 7. F1 — WC2 Forward-Liveness Truth

## Goal

Resolve why the decision/forecast stream stopped advancing while fresh signal freezes continued.

This phase must **diagnose before changing policy**.

## Work

For every eligible-timeframe freeze after the latest forecast, derive deterministic reason classification:

- before collection boundary;
- before activation boundary;
- wrong timeframe;
- wrong provider pairing;
- no dual-provider consensus requirement met;
- `NO_SIGNAL`;
- non-directional signal;
- missing geometry;
- ineligible source;
- missing prepared receipt;
- prepared receipt recovery path;
- duplicate/replay;
- issuance-delay violation;
- policy exclusion;
- provider/data-quality block;
- Event Risk block if applicable;
- actual forecast issuance.

Produce counts by:

- asset;
- provider;
- timeframe;
- state;
- reason code.

## Critical rule

Do **not** loosen WC2 rules merely to create messages.

If all post-forecast freezes were legitimately ineligible, that is a valid scientific outcome.

If an eligible freeze should have progressed but did not, fix only the proven correctness/runtime defect.

## Observability closure

The live runtime must emit or persist enough deterministic status to explain prolonged silence without reading private logs manually.

The product may later summarize:

- signals scanned;
- candidates considered;
- strongest current eligible candidate;
- dominant blocker;
- last forecast time;
- last eligible setup;
- data-quality state.

This is diagnostic truth, not fabricated market commentary.

## PASS

One of two conclusions must be mechanically proven:

### A — Correct silence
No post-forecast freeze satisfied the preregistered issuance contract.

or

### B — Correctness defect
A specific eligible freeze failed to issue because of a reproducible implementation/runtime defect, and the defect is fixed with exact-source regression + live verification.

---

## F1 final live closure — 2026-09-26

F1 is fully closed.

- exact-source mechanical audit: run `36251560197` → `CORRECT_SILENCE`;
- merged main: `71ff1ad4f2d1c9f58df65fab12a12c02754acfc6`;
- physical Development live activation: run `36252043820`;
- observed real supervisor marker:
  `wc2_liveness status=SUMMARY contexts=17 status_counts=no_prepared_receipt:17 reason_counts=no_preoutcome_prepared_receipt_for_source_freeze:17 POLICY_UNCHANGED=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0`;
- WC2 policy/protocol hashes unchanged;
- Product checkout unchanged;
- no historical backfill, synthetic activity or real-money authority.

Next exact frontier: **F2 — Production Source-to-Message Backbone**.

---

# 8. F2 — Production Source-to-Message Backbone

## Goal

Generalize the accepted Stream pipeline so production is not dependent only on WC2 forecast issuance/resolution.

## Principle

Every source-specific projector must enter the already accepted chain:

**persisted canonical source truth**  
→ **Stream Source Event**  
→ **Fact Bundle**  
→ **Story Observation / State**  
→ **Change Set**  
→ **Analytical View**  
→ **materiality policy**  
→ **Narrative Plan / renderer**  
→ **immutable message**  
→ **SSE**

Do not build parallel messaging systems.

## Required common contract

Every projector must provide:

- source event identity;
- category;
- subtype;
- importance;
- asset/symbol/market/timeframe where applicable;
- source event time;
- source-as-of time;
- evidence identities;
- story identity;
- exact current/previous-state references where applicable;
- materiality reason code;
- production_authority=false;
- REAL_CAPITAL=0.

## Message classes

The original categories remain:

- MARKET;
- INTELLIGENCE;
- DECISION;
- CAPITAL;
- RISK;
- OUTCOME;
- SYSTEM.

Routine summaries remain optional and cannot become spam.

## PASS

A reusable production source-projector interface exists and all later families plug into it without bypassing S3/S4/S5 truth controls.

---

## F2 final closure — 2026-09-26

F2 is fully accepted.

- canonical acceptance: `docs/CRYPTO_SIGNAL_STREAM_FINAL_F2_PRODUCTION_BACKBONE_ACCEPTANCE.md`;
- reusable fail-closed production projector boundary:
  `src/crypto_signal/product/intelligence_stream_production_projector.py`;
- common contract binds exact source/event/category/subtype/importance/market/time/evidence/story/current+previous references to the accepted materiality decision;
- downstream ownership remains the accepted Story → Analytical → materiality → Narrative → immutable ledger chain;
- unimplemented later-family registry entries remain rejected until their exact source-specific F3/F4 projector is implemented;
- UID504 exact-source run `36253512588` passed focused tests, ruff, strict mypy, broad repository regression, full source/test ruff, strict mypy over 237 source files and JavaScript freshness/syntax checks;
- no historical backfill, no synthetic activity, no production-authority expansion, `REAL_CAPITAL=0`.

Next exact frontier: **F3 — Five-Family Live Intelligence Projection**.

---

# 9. F3 — Five-Family Live Intelligence Projection

## Goal

Make the Stream speak about material changes in the actual analytical evidence, not only forecast issuance.

## 9.1 Market / Geometry

Project material changes such as:

- meaningful structure transition;
- trigger transition;
- invalidation transition;
- target/geometry transition;
- materially changed directional context.

Do not emit one message per candle.

## 9.2 Liquidity

Use exact persisted truth for supported events:

- material liquidity-zone interaction;
- sweep candidate when exact criteria/identity exist;
- meaningful liquidity-state transition;
- liquidation context only when exact persisted evidence exists.

## 9.3 Order Flow

Use exact persisted truth for:

- CVD support/opposition transition;
- divergence;
- absorption candidate/state;
- meaningful loss or arrival of order-flow confirmation.

## 9.4 Derivatives

Use exact persisted snapshots for material changes in:

- funding;
- open interest;
- basis;
- crowding;
- accepted derivatives dynamics.

## 9.5 On-chain / network

Do not pretend a source is live when it is not.

Closure policy:

- activate only accepted, real, persistent sub-families with a trustworthy runtime source;
- unsupported Exchange Flow / Wallet Cohort / Large Transfer features remain explicitly unavailable/research-only until a real provider is accepted;
- existing five-family Decision messages may still show frozen on-chain state when that state is present in the exact decision context;
- no standalone live on-chain message is published from non-live research truth.

## Materiality

Every family must reuse the accepted S4 materiality framework.

A message is emitted only when a change matters to user interpretation.

## PASS

At least Market/Geometry + Liquidity + Order Flow + Derivatives have complete source→projector→runtime wiring wherever exact live persisted source truth already exists.

Unsupported sources remain visibly gated rather than fabricated.

---

## F3 final live closure — 2026-09-26

F3 is fully accepted and physically live.

- canonical acceptance: `docs/CRYPTO_SIGNAL_STREAM_FINAL_F3_LIVE_INTELLIGENCE_ACCEPTANCE.md`;
- PR #1355 merged canonical Market/Geometry, Liquidity, Order Flow and Derivatives family projection through the F2 backbone;
- PR #1358 fixed the post-merge ordering defect by moving independent family projection before the existing WC2 outcome chronology fail-stop without weakening that fail-stop;
- exact merged main: `a589efa4a8a4040bec56bfa81611c7f9e3e30517`;
- UID504 final live closeout run `36260544411` passed;
- Development exact-main sync and canonical supervisor were live;
- persisted derivatives observations: 69 at acceptance;
- all four immutable family activation boundaries were present;
- canonical source/narrative counts after activation:
  - Geometry 7;
  - Liquidity 3;
  - Order Flow 3;
  - Derivatives 3;
- derivatives family events were forward of the immutable activation boundary;
- live `stream_family status=SUMMARY` was observed;
- unsupported standalone on-chain/network sources remain explicitly gated;
- no historical rich backfill, no synthetic activity, no real-money authority;
- `REAL_CAPITAL=0`.

Next exact frontier: **F4 — Risk + System Trust Projection**.

---

# 10. F4 — Risk + System Trust Projection

## Goal

Make the Stream explain when the user should trust the current analytical state less, or when a real risk condition changes.

## 10.1 Event Risk

Project exact persisted transitions such as:

- CLEAR → CAUTION;
- CAUTION → BLOCK;
- BLOCK → recovery/clear;
- material approach to a known event window.

No synthetic news/event message is allowed.

## 10.2 Provider/Data Quality/System

Publish only decision-relevant events:

- provider degraded;
- required provider missing/stale;
- decision evidence coverage materially reduced;
- provider divergence changed trust state;
- source recovered;
- decision pipeline recovered after a meaningful outage.

Do not spam the user with routine internal maintenance.

## Required behavior

A SYSTEM/RISK message must say:

- what degraded/changed;
- what analysis is affected;
- whether the system is abstaining, reducing confidence, blocking action or merely warning;
- what condition restores normal operation.

## PASS

A real provider degradation/recovery and a real or exact forward Event Risk transition can traverse the same canonical message pipeline and remain immutable.

---

## F4 final live closure — 2026-09-26

F4 is fully accepted and physically live.

- canonical acceptance: `docs/CRYPTO_SIGNAL_STREAM_FINAL_F4_RISK_SYSTEM_TRUST_ACCEPTANCE.md`;
- PR #1363 merged exact Event Risk and provider/data-quality trust projection through the existing F2/F3 canonical Stream backbone;
- routine initial `clear` / `healthy` baselines are silent; material caution/degraded/block and later recovery transitions remain publishable;
- RISK/SYSTEM narrative explicitly states the affected trust layer and restoration condition without inventing market direction, probability or order/capital authority;
- exact-source gate `36263227400` passed focused tests, broad repository regression, full source/test Ruff, strict mypy over 240 source files and a read-only real persisted provider degradation→recovery audit;
- real provider history proved `healthy → degraded_provider_stale → healthy` on the persisted Binance↔Bybit divergence source;
- final physical activation run `36263537425` proved exact Development main `3ec48a3728b919e3783546e57eab7afebab1d18d`, canonical supervisor reload, healthy Event Source/provider-divergence/Stream databases, both immutable F4 activation boundaries and live `stream_trust status=SUMMARY`;
- live persisted source counts at acceptance: 4 event coverages, 48 structured events, 159 provider-divergence snapshots;
- canonical F4 Stream source rows existed, including 3 `data_quality_degraded` rows;
- no synthetic risk/system event, no historical rich-message backfill, no production-authority expansion, `REAL_CAPITAL=0`.

Next exact frontier: **F5 — Three-Vault Capital Story Live Closure**.

---

# 11. F5 — Three-Vault Capital Story Live Closure

## Goal

Make the original roadmap promise true:

> the Stream explains what Core, Tactical and Opportunity Reserve did or did not do and why.

## Required production chain

**Decision / exact candidate**  
→ **three-vault eligibility**  
→ **sizing assessment**  
→ **canonical fixed-fractional selection where allowed**  
→ **simulated execution**  
→ **R22 transaction tape**  
→ **R21 Epoch 2 accounting**  
→ **Capital Stream projection**

## Required Stream lifecycle

Support exact canonical states:

- candidate;
- hold;
- blocked;
- eligible;
- sized;
- executed;
- reduced;
- exited;
- accounting updated;
- outcome.

## Critical separation

The WC2 paper-execution journal is not automatically canonical R21/R22 Epoch 2 mutation.

No CAPITAL message may claim a canonical vault action unless exact R21/R22 lineage exists.

## Zero-activity diagnostics

If no vault acts for a long period, the system should be able to explain truthfully:

- candidates scanned;
- strongest candidate;
- Core blocker;
- Tactical blocker;
- Opportunity blocker;
- last eligible;
- last simulated execution;
- current cash/exposure;
- current source quality.

## PASS

All three vaults can progress through their own accepted rules on forward paper truth, and every resulting canonical action or non-action state can be narrated in the same Stream.

---

## F5 live activation progress — 2026-09-26

F5 is **not yet PASS**. Implementation and physical activation are accepted; one genuine post-activation Capital projection is still required.

Accepted implementation evidence:
- PR #1369 merged F5 to main `97b2db05711d4b5504c47b4dfb8396d92fcd762f`;
- exact-source UID504 gate `36267123088` passed focused tests, whole-repository regression, Ruff, strict mypy, JavaScript checks and read-only live-ledger audit;
- the earlier Stream chronology failure was preserved as a valid anti-backfill guard and fixed by giving the genuine Decision → Capital assessment → Core → Tactical → Opportunity sequence deterministic forward timestamps;
- no historical Stream chronology rule was weakened.

Accepted physical activation evidence:
- UID504 run `36267383692` fast-forwarded Development to exact merged main;
- canonical supervisor reload passed headlessly;
- live Epoch2 and Stream SQLite quick checks are `ok`;
- required S11/R22 Capital lifecycle tables now physically exist;
- required Stream Capital tables now physically exist;
- immutable Capital activation identity:
  `bbd190a8ad282e69ce30edae334dc1cf06103bb86d777931fa5db106ad0ad4a8`;
- Capital activation time: `1790452197922`;
- live log marker `stream_capital status=ACTIVATED` observed;
- `HISTORICAL_BACKFILL=NO`;
- `REAL_CAPITAL=0`.

At the activation acceptance instant:
- post-activation CAPITAL source rows: 0;
- S11 vault decisions: 0;
- R22 Capital intents: 0;
- `stream_capital status=PROJECTED`: not yet observed.

Therefore the remaining F5 gate is exactly:

**one natural post-activation canonical forward Capital candidate/decision projection with real persisted lineage**.

Do not create synthetic candidates, sizing, fills, executions or historical Capital messages to satisfy this gate.

---

# 12. F6 — Exact Frozen Evidence Closure

## Goal

Make “show me” stronger than “trust me” for every supported message family.

## Required resolver model

For every clickable evidence reference:

**message evidence identity**  
→ **exact persisted evidence object**  
→ **frozen timestamped customer projection**

Never reconstruct historical proof from current market state.

## Required closures

### Geometry
- trigger;
- entry zone where canonical;
- target;
- invalidation;
- structure level;
- exact coordinates.

### Liquidity
- exact zone/level;
- sweep point when supported;
- source timestamp;
- persisted snapshot identity.

### Order Flow
- frozen CVD series/measurement;
- divergence relation;
- absorption evidence where exact representation exists.

### Derivatives
- exact OI/funding/basis/crowding values and source snapshot.

### Order book
- exact persisted snapshot;
- bids/asks/quantities;
- imbalance measurement;
- provider/exchange;
- event/source/ingested timestamps.

### Event Risk
- exact event/source record and temporal relationship to decision.

### Capital
- exact eligibility/sizing/intent/fill/accounting identities.

## UI rule

If exact visual coordinates do not exist:

- show identity-backed numeric/text proof;
- state that visual proof is unavailable;
- do not draw an illustrative line as fact.

## PASS

Every proof visible in a real live message is either:

- `READY_EXACT`;
- `IDENTITY_ONLY_EXACT`;
- or `UNAVAILABLE_EXPLICIT`.

There is no ambiguous “looks plausible” proof state.

---

# 13. F7 — Guarded Local LLM / Ollama Activation

## Goal

Activate the already-designed local-language polish path **after** deterministic live messaging is healthy.

## Role of the model

The local model may improve natural Turkish style.

It must not:

- invent facts;
- decide market direction independently;
- create prices/targets;
- change score;
- change vault state;
- change timestamps;
- add unsupported causal claims;
- alter TECHNICAL / INTELLIGENCE / DECISION / CAPITAL truth sections beyond the accepted safe rewrite boundary.

## Runtime requirements

- loopback-only;
- no cloud dependency required;
- bounded timeout;
- bounded tokens;
- low temperature;
- no proxy use;
- immutable model/config identity in provenance;
- deterministic fallback on any error.

The existing OpenAI-compatible local adapter may be used with Ollama-compatible endpoints.

The exact model is an operational configuration choice, not product truth.

## Acceptance

For identical facts:

- deterministic baseline remains valid;
- accepted local rewrite is more natural but semantically equivalent;
- validator rejects unsupported additions;
- local-model outage does not prevent message publication.

## PASS

Real live messages may use guarded local rewrite while exact original deterministic text/provenance remains auditable.

---

# 14. F8 — Real Production Multi-Category E2E Acceptance

## Goal

Replace fixture confidence with genuine production proof.

## Required scenarios

At least one genuine forward example for every source class that is currently claimed live:

1. MARKET or INTELLIGENCE;
2. DECISION issuance;
3. OUTCOME/resolution;
4. RISK or SYSTEM;
5. CAPITAL when canonical R21/R22 activity occurs.

For rare categories, do not fabricate an event merely to pass acceptance.

Acceptance remains open until a real forward event occurs or the product explicitly classifies that source as unavailable/deferred.

## Each accepted event must prove

source truth  
→ persisted identity  
→ projector  
→ story/change  
→ analytical materiality  
→ narrative  
→ Stream ledger  
→ SSE  
→ real browser  
→ immutable refresh/history  
→ search/deep-link  
→ evidence window  
→ exact proof/fail-closed proof.

## Negative acceptance

Also prove:

- non-material events do not spam;
- replay produces no duplicate bubble;
- reconnect produces no duplicate sound;
- historical records are unchanged;
- LLM outage does not break delivery;
- missing proof does not become fabricated proof.

## PASS

The Product is no longer accepted merely because a temporary ledger can exercise the feature.

The claimed live message classes must be demonstrated on the actual production path.

---

# 15. F9 — Final Real-UI Product Acceptance

## Goal

Only after the real message pipeline is alive, verify that the actual Product realizes the original visual/product intent.

This is **not** a redesign phase.

Fix only defects discovered in real production message states.

## Required real-browser checks

Desktop + exact mobile:

- ready/empty state;
- real mixed-message stream;
- incoming live message;
- message expansion;
- SIMPLE;
- PRO;
- INTELLIGENCE;
- DECISION;
- CAPITAL;
- evidence window;
- multiple evidence windows;
- detached proof;
- search/filter;
- deep link;
- sound controls;
- old-history position;
- unread/new-message affordance;
- degraded-source message;
- long-session behavior.

## 10-second comprehension test

A normal collapsed message should let a trader quickly answer:

- what changed?
- asset/timeframe?
- what does the system think?
- how important is it?
- what is the main next condition?
- where is the proof?

## PASS

The live Product — not only fixture screenshots — feels like:

**a calm Telegram intelligence channel on the surface, a professional evidence workstation underneath.**

---

# 16. F10 — Authority Freeze / Final Closeout

## Goal

Close Intelligence Stream V1 only when original roadmap intent and production reality match.

## Required closeout

Update:

- `READ_FIRST_CRYPTO_SIGNAL.md`;
- `CURRENT_STATUS.md`;
- `PROJECT_CHRONICLE.md`;
- original Master Roadmap status note;
- final source-to-message ledger;
- final acceptance record.

## Final status language

Only after F0-F9 pass may the project state say:

**INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ACCEPTED**

The old S0-S16 acceptance remains historical evidence.

The new final status means:

- all currently claimed live source families have real production message projection;
- unsupported source families are explicitly gated rather than implied;
- production silence is diagnosable;
- three-vault canonical paper truth is narratable;
- exact proof is available or explicitly unavailable;
- optional Ollama/local rewrite is safely bounded;
- real browser acceptance used real production events;
- no historical backfill or fabricated activity was used;
- REAL_CAPITAL=0 remains binding.

---

# 17. Explicitly out of scope

This final roadmap does **not** authorize:

- new standalone Markets page;
- new standalone Capital page;
- Performance dashboard;
- Archive screen;
- Education/Learn screen;
- System Health dashboard;
- multi-tab navigation;
- real-money trading;
- exchange credentials;
- leverage;
- backfilling historical rich messages;
- changing WC2 policy merely to increase activity;
- declaring profitability/calibration before evidence;
- activating research-only sources without a real live provider;
- replacing deterministic truth with LLM judgment.

---

# 18. Final Definition of Done

Crypto Signal Intelligence Stream V1 is finally complete only when all statements below are true at the same time:

1. The product still has one primary Stream surface.
2. Real backend material events can create real messages automatically.
3. The Stream is not dependent only on forecast issuance/resolution.
4. Silence is explainable through deterministic eligibility/source diagnostics.
5. Material Market/Geometry changes can be projected where exact source truth exists.
6. Material Liquidity changes can be projected where exact source truth exists.
7. Material Order Flow changes can be projected where exact source truth exists.
8. Material Derivatives changes can be projected where exact source truth exists.
9. Event Risk/System degradation/recovery can be narrated from exact persisted truth.
10. Unsupported On-chain/live-source capabilities remain explicit rather than fabricated.
11. Decision issuance/resolution remain immutable and live.
12. Core/Tactical/Opportunity canonical paper actions/non-actions are narratable from exact lineage.
13. Every published message is append-only and survives refresh/restart.
14. Story memory can explain what changed.
15. SIMPLE/PRO/INTELLIGENCE/DECISION/CAPITAL depth remains reachable from the same message.
16. Supported evidence opens by exact identity.
17. Frozen proof never substitutes current data.
18. Every unavailable proof is explicit.
19. Search/filter/history/deep-link continue to preserve original identity.
20. SSE/reconnect/dedupe/sound behavior remains exact.
21. Local LLM/Ollama, if enabled, can improve prose but cannot create truth.
22. LLM failure cannot stop Stream publication.
23. Actual production events, not only fixtures, have passed end-to-end browser acceptance.
24. Desktop and mobile real Product states pass visual acceptance.
25. No historical rich backfill was used.
26. No scientific policy was weakened to manufacture activity.
27. No real-money authority was added.
28. `REAL_CAPITAL=0`.

When these are true, the original Intelligence Stream V1 vision can be called **mechanically complete**, not merely architecturally accepted.
