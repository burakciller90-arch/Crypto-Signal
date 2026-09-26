# Crypto Signal — Stream S1 Gap Ledger

Status: **CANONICAL STREAM GAP LEDGER / S9 CLOSEOUT APPLIED**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
Baseline: `2a61ad47e1f09640f3b36e4ccf09f6ed46dde7ef`

This ledger tracks only gaps required to deliver Intelligence Stream V1.

Classification:
- **ADAPT** — backend truth exists; build projection/adapter.
- **BUILD** — new Stream-specific component is required.
- **DISCOVER** — exact current backend/live/persistence truth needs tracing.
- **INTEGRATE** — accepted components exist but are not connected end to end.
- **UI** — frontend interaction/rendering gap.
- **ACCEPTANCE** — validation/quality gate.

| ID | Gap | Current truth | Required closure | Class | Target phase |
|---|---|---|---|---|---|
| S1-G001 | Rich canonical Stream event/message ledger | **CLOSED S2** — forward activation, immutable source events, decision context, Fact Bundles and canonical Message Inputs are append-only persisted | preserve and extend without rewriting canonical history | ACCEPTANCE | S2 PASS |
| S1-G002 | Source event projectors | **CLOSED THROUGH S11** — forecast issuance/resolution plus canonical three-vault capital lifecycle are IMPLEMENTED in the accepted projector registry; deferred/research-only sources remain explicitly gated | preserve registry truth as later sources are activated | ACCEPTANCE | S11 PASS / ongoing invariant |
| S1-G003 | Story identity and relation graph | **CLOSED S3** — explicit Story Observation/State lineage uses exact previous-state identity; pre-publication observations do not require a message | preserve exact lineage; S4/S5 consume it without heuristic time-only joins | ACCEPTANCE | S3 PASS |
| S1-G004 | Change detection | **CLOSED S3** — deterministic stance/score/five-family/risk/trigger/capital-reference/outcome Change Set is persisted append-only | S4 consumes exact Change Set for analytical composition | ACCEPTANCE | S3 PASS |
| S1-G005 | Analytical View contract | **CLOSED S4** — versioned policy + deterministic identity-bound Analytical View covers stance/strength/support/contradiction/uncertainty/change/conditions/capital consequence/materiality | preserve exact S4 identity/version lineage into S5 narrative | ACCEPTANCE | S4 PASS |
| S1-G006 | Story-aware Turkish Narrative Engine | **CLOSED S5** — deterministic Turkish Narrative Plan/renderer consumes exact S4 view + S3 history; optional guarded local rewrite cannot invent market truth | preserve narrative identities/version/validation through S6+ transport/UI | ACCEPTANCE | S5 PASS |
| S1-G007 | Narrative persistence/versioning | **CLOSED THROUGH S6** — S5 persists original text/version/provenance and S6 transports the persisted payload without rerendering history | preserve exact narrative identity through UI/evidence/capital layers | ACCEPTANCE | S6 PASS |
| S1-G008 | Realtime delivery | **CLOSED S6** — cursor-safe SSE, EventSource Last-Event-ID reconnect/catch-up, dedupe, heartbeat/retry and GET polling fallback are accepted | S7 consumes this transport; do not add a parallel live channel without new need | ACCEPTANCE | S6 PASS |
| S1-G009 | Cursor/history API | **CLOSED S6** — stable before/after keyset cursors, upward history pagination and exact narrative lookup are accepted | S7/S12 preserve cursor position and original message identity | ACCEPTANCE | S6 PASS |
| S1-G010 | Search/filter API | **BACKEND CLOSED S6** — symbol/timeframe/story/source-kind/stance/category/importance/evidence/date/full-text query contract exists; vault awaits S11 capital projection | build messaging-first search/filter UX in S12 and add vault when canonical S11 references exist | UI/ADAPT | S12 / S11 dependency |
| S1-G011 | M6 family breakdown persistence/projection | **CLOSED S4 CONSUMPTION** — S2 freezes the full five-family snapshot and S4 deterministically ranks support/contradiction from that exact payload | preserve frozen family identities/points into S5/S10; never recompute history from current data | ACCEPTANCE | S4 PASS |
| S1-G012 | Evidence object persistence/lookup by identity | S2 persists exact evidence-reference identities in source/message truth; universal rich evidence-object lookup adapters are still absent | S10 must resolve supported identities to frozen proof objects without reconstructing history from current data | ADAPT | S10 |
| S1-G013 | Visual annotation coordinate contract | frozen chart/geometry exists; not every technical claim has drawable coords | exact time/price/region coordinates + evidence identity + version | ADAPT | S10 |
| S1-G014 | Frozen order-book proof retrieval | Market Tape stores order books and proof can bind identity | exact snapshot-identity -> frozen orderbook product projection | ADAPT | S10 |
| S1-G015 | Order-flow visual proof | CVD/divergence/absorption evidence exists but no unified customer graph payload | frozen series/measurement projection tied to message evidence | ADAPT | S10 |
| S1-G016 | On-chain/Smart-Money Stream runtime | discovery resolved: Bitcoin network has real public Blockstream source but no always-on Stream runtime; Exchange Flow/Wallet Cohort/Large Transfer have no live provider activation | add runtime persistence only for explicitly selected/accepted sub-families; keep non-live M5 provider-neutral engines research/evidence-only | ADAPT/DEFERRED_BY_SOURCE | S2+ |
| S1-G017 | Liquidation continuous-source activation | discovery resolved: bounded collector + hot/cold persistence exist, but production continuous collector is explicitly disabled | Stream may use exact persisted liquidation evidence when available; live liquidation messages require separate accepted collector activation | DEFERRED_BY_ACTIVATION | S2+ |
| S1-G018 | Event Risk messages | S4 Analytical View now consumes Event Risk state and can materialize risk changes deterministically; the dedicated live Event Risk source projector remains gated | implement the exact live projector only from accepted persisted source truth, then feed the accepted S4 policy; no synthetic risk events | ADAPT | S5+ source integration |
| S1-G019 | Provider/data-quality messages | S4 provides deterministic analytical materiality/change semantics, but provider-specific source projection is still not implemented | project only exact decision-relevant degradation/recovery events from accepted provider truth before S5 rendering | ADAPT | S5+ source integration |
| S1-G020 | Three-vault canonical forward runtime | allocator/sizing/R22/R21 exist; current accepted execution rail is CORE/4h journal-isolated | one canonical Core/Tactical/Opportunity forward paper runtime mutating R22/R21 Epoch2 | INTEGRATE | S11 |
| S1-G021 | Capital event projection | Epoch2/R22 truth exists; no Stream event model | HOLD/BLOCK/ELIGIBLE/SIZED/EXECUTED/REDUCED/EXITED/accounting event projector | ADAPT | S11 |
| S1-G022 | Capital context persistence/read models | Epoch2 summary and canonical R22/R21 persistence exist; rich Capital Science/Sizing objects are not fully persisted/projected, while Shadow Preview persists only downstream preview payload | persist/read exact assessment + sizing context and expose intent/fill/bundle lineage without confusing shadow evidence with canonical Epoch2 mutation | BUILD/ADAPT | S11 |
| S1-G023 | Zero-activity diagnostics | no single Stream truth explains long HOLD periods | candidates scanned, strongest candidate, blockers, last eligible/execution, source quality | BUILD/ADAPT | S11 |
| S1-G024 | One-panel Stream shell | **CLOSED S7** — isolated browser-rendered messaging shell exists at `/stream-preview`; production root remains GALACTECH V2 until S16 | preserve one-panel IA through S8-S16 and cut over only at S16 | ACCEPTANCE | S7 PASS |
| S1-G025 | Compact expandable bubble | **CLOSED S8** — same immutable message now expands inline to SIMPLE/PRO/INTELLIGENCE/DECISION/geometry/CAPITAL/PROOF; exact persisted detail projection is fail-closed and Chromium proves 0px anchor drift | preserve inline-depth contract through S9-S16 | ACCEPTANCE | S8 PASS |
| S1-G026 | Evidence Window Manager | **CLOSED S9** — reusable exact-message windows support drag/resize/minimize/close/pin, multi-window focus/z-order, session restore and detach | preserve framework while S10 adds frozen visual payloads | ACCEPTANCE | S9 PASS |
| S1-G027 | Context education in evidence windows | **CLOSED S9** — deterministic education concepts are bound to window kinds; message-specific importance text is derived only from exact persisted detail | preserve non-generative education boundary | ACCEPTANCE | S9 PASS |
| S1-G028 | Notification chime/settings | not implemented | original sound + unlock/volume/mode/persistence; replay must be silent | UI | S13 |
| S1-G029 | Unread/new-message behavior | **CLOSED S7** — bottom anchor, no forced scroll while reading history, and buffered `N yeni mesaj` affordance are browser-rendered and accepted | preserve semantics through virtualization/reconnect/sound phases | ACCEPTANCE | S7 PASS |
| S1-G030 | Long-session feed performance | current UI not designed as all-day message stream | virtualization/reverse pagination/memory/reconnect tests | UI/ACCEPTANCE | S14 |
| S1-G031 | Stream visual-snapshot coverage | **CLOSED THROUGH S12** — UID504 Chromium covers one-panel Stream, evidence windows, frozen proof, ten-state Capital Story and full discovery/deep-link UX on desktop plus exact 430px mobile no-overflow | extend same path for sound, long-history and cutover states | ADAPT/ACCEPTANCE | S13-S16 |
| S1-G032 | Detached proof / second-monitor workflow | **S9 FRAMEWORK CLOSED** — detached evidence route is tied to exact narrative identity + evidence kind and re-reads persisted detail; frozen proof rendering remains S10 | add frozen visual payload to the exact detached proof window | ADAPT | S10 |
| S1-G033 | Historical activation boundary | **CLOSED THROUGH S12** — discovery/search reads only persisted immutable Stream truth and exact deep-links; no history rewrite, paper backfill/rescaling or current-data substitution is introduced | preserve no-synthesis/no-backfill rule through sound/cutover | ACCEPTANCE | S12 PASS |
| S1-G034 | Message materiality policy | **CLOSED S4 CORE** — versioned Analytical Policy deterministically maps exact S3 changes to PUBLISH/SILENT + reason codes | future source-specific projectors must consume this contract rather than invent ad-hoc spam thresholds | ACCEPTANCE | S4 PASS |
| S1-G035 | Secondary-engine Stream classification | **CLOSED THROUGH S11** — paper_capital_transition is now IMPLEMENTED with the exact ten-state lifecycle while deferred/research-only sources remain gated; no shadow/research evidence is silently promoted | maintain classification as later sources are activated | ACCEPTANCE | S11 PASS / ongoing invariant |

## S1 closeout

S1 discovery prerequisites are closed.

Canonical discovery outputs:
- `CRYPTO_SIGNAL_STREAM_S1_CAPABILITY_MATRIX.md`;
- `CRYPTO_SIGNAL_STREAM_S1_IDENTITY_TEMPORAL_MAP.md`;
- `CRYPTO_SIGNAL_STREAM_S1_SOURCE_MESSAGE_MAP.md`;
- this Gap Ledger.

The remaining rows are implementation/activation/acceptance work for S2+; they are no longer unknown discovery.

**S1 = PASS.**

## S2 closeout

Canonical S2 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S2_ACCEPTANCE.md`.

S2 closed:
- append-only event/message backbone;
- forward activation boundary;
- immutable five-family decision context;
- Fact Bundle + Message Input identities;
- story/relation schema;
- search/evidence/capital/version metadata slots;
- deterministic issuance/resolution projectors;
- versioned materiality/publication policy;
- accepted projector registry;
- exact replay/idempotence/chronology acceptance.

**S2 = PASS. S3 Story Engine and Change Detection is the active frontier.**

Do not jump to S4 or UI. S3 must first create deterministic previous -> current story state and explicit change sets without heuristic time-only joins.


## S3 closeout

Canonical S3 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S3_ACCEPTANCE.md`.

S3 closed:
- explicit Story Observation / Story State / Change Set contracts;
- exact previous-state continuity;
- deterministic stance/score/five-family/risk/trigger/capital/outcome deltas;
- pre-publication observation support;
- append-only story persistence;
- unrelated-story and chronology rejection;
- replay/idempotence/immutability acceptance.

**S3 = PASS. S4 Analytical Composer is the active frontier.**

Do not jump to S5 or UI. S4 must first create a deterministic structured system opinion from Fact Bundle + Change Set.


## S7 closeout

Canonical S7 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S7_ACCEPTANCE.md`.

S7 closed:
- one-panel messaging shell;
- compact collapsed narrative bubbles;
- S6 live/polling consumption;
- stable upward history;
- bottom-anchor + buffered unread behavior;
- search/filter and settings control surfaces;
- reserved floating-window layer;
- Stream runtime ledger binding;
- deterministic rendered fixture coverage;
- exact desktop/mobile browser acceptance.

**S7 = PASS. S8 Expandable Message Experience is the active frontier.**

Do not jump to S9. S8 must first expose all supported message depth inline from the same immutable narrative lineage and prove expansion preserves scroll position.


## S8 closeout

Canonical S8 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S8_ACCEPTANCE.md`.

S8 closed:
- inline expand/collapse;
- SIMPLE / PRO / INTELLIGENCE / DECISION;
- persisted five-family contribution display;
- trigger / target / invalidation trade geometry;
- CAPITAL narrative + structured consequence;
- exact forecast-bound proof action;
- fail-closed persisted message-detail projection;
- desktop/mobile 0px scroll-anchor acceptance.

**S8 = PASS. S9 Evidence Window Manager is the active frontier.**

Do not jump to S10. S9 must first deliver reusable exact-identity evidence windows with drag/resize/minimize/pin/multi-window/focus/session persistence/detach behavior while keeping the stream usable.


## S9 closeout

Canonical S9 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S9_ACCEPTANCE.md`.

S9 closed:
- reusable evidence-window framework;
- drag / resize / minimize / close / pin;
- multi-window focus and z-order;
- session-local geometry/state restore;
- exact narrative/kind detach route;
- all nine evidence-window kinds;
- context education binding;
- Chromium multi-window acceptance.

**S9 = PASS. S10 Frozen Visual Proof is the active frontier.**

S10 must resolve supported persisted evidence into exact point-in-time visuals with identity/provenance/coordinates and must fail closed where a historical visual cannot be recovered exactly.


## S10 closeout

Canonical S10 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S10_ACCEPTANCE.md`.

S10 closed:
- immutable frozen OHLC projection;
- supported geometry annotations;
- exact timestamp/provenance;
- score-component explanation;
- identity-only vs unavailable behavior for proof domains without bound visual payload;
- floating + detached proof rendering;
- current-data substitution rejection;
- desktop/mobile Chromium proof acceptance.

**S10 = PASS. S11 Capital Story Integration is the active frontier.**

Do not jump to S12. S11 must first complete canonical three-vault forward paper-capital behavior and project exact capital intent/fill/accounting lineage into the Stream while preserving Epoch separation and REAL_CAPITAL=0.


## S11 closeout

Canonical S11 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S11_ACCEPTANCE.md`.

S11 closed:
- canonical three-vault Epoch 2 paper runtime;
- exact Core / Tactical / Opportunity eligibility rules;
- fixed-fractional canonical sizing promotion;
- immutable eligible / hold / blocked decisions;
- restart-safe R22 predecessor lineage;
- simulated execution / reduction / exit;
- R22/R21 atomic accounting;
- accounting and outcome records;
- ten-state Capital Story projection into the same mixed Stream;
- exact decision/proof/evidence lineage;
- browser-rendered three-vault lifecycle on desktop and exact 430px mobile;
- no standalone Capital screen;
- REAL_CAPITAL=0.

**S11 = PASS. S12 Search, Filters and History UX is the active frontier.**

Do not jump to S13. S12 must first reuse S6/S7 primitives to complete full discovery controls, exact message deep-links and browser-rendered search/history behavior without creating permanent navigation sections.


## S12 closeout

Canonical S12 acceptance:
- `docs/CRYPTO_SIGNAL_STREAM_S12_ACCEPTANCE.md`.

S12 closed:
- full-text search;
- asset / category / timeframe / vault / evidence / state / importance / date filters;
- clear-filter behavior;
- exact immutable-message deep-link;
- direct URL and click-driven exact-message navigation;
- persisted detail/proof continuity;
- same mixed Stream as the default surface;
- desktop/mobile Chromium discovery acceptance.

**S12 = PASS. S13 Sound and Notifications is the active frontier.**

Do not jump to S14. S13 must first prove optional sound/notification behavior, user settings persistence, exactly-once sound for eligible new messages, and silence for history loading/reconnect replay.
