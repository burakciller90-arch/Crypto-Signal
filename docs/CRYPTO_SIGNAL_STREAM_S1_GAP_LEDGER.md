# Crypto Signal — Stream S1 Gap Ledger

Status: **CANONICAL STREAM GAP LEDGER / S6 CLOSEOUT APPLIED**  
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
| S1-G002 | Source event projectors | **S2 CONTRACT CLOSED** — accepted projector registry exists; forecast issuance/resolution are IMPLEMENTED; other families are explicitly gated | implement material market/intelligence/risk/system projectors only after S3-S4 change detection; capital remains S11 | ADAPT | S3-S4 / S11 |
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
| S1-G024 | One-panel Stream shell | current deployed UI is multi-section GALACTECH V2 | new messaging-first shell only | UI | S7 |
| S1-G025 | Compact expandable bubble | no final Stream V1 interaction | collapsed paragraph + chips; inline expansion preserving scroll | UI | S7-S8 |
| S1-G026 | Evidence Window Manager | current product uses conventional UI/modal patterns | draggable/resizable/minimize/pin/multi-window/detach manager | UI | S9 |
| S1-G027 | Context education in evidence windows | education API exists, not bound to message evidence | “Bu nedir?” concept mapping + message-specific “neden önemli?” | ADAPT/UI | S9 |
| S1-G028 | Notification chime/settings | not implemented | original sound + unlock/volume/mode/persistence; replay must be silent | UI | S13 |
| S1-G029 | Unread/new-message behavior | current polling feed does not implement messaging UX | bottom anchor + N-new control + no forced scroll | UI | S7 |
| S1-G030 | Long-session feed performance | current UI not designed as all-day message stream | virtualization/reverse pagination/memory/reconnect tests | UI/ACCEPTANCE | S14 |
| S1-G031 | Stream visual-snapshot coverage | existing UID504 `visualsnapshot` already captures Chromium-family desktop/mobile PNG artifacts; UID501 already provides `visualcleanup504` maintenance | reuse/extend existing capture path for deterministic Stream states, additional viewports, exact-message/evidence-window fixtures and review gates; do **not** build a second screenshot stack | ADAPT/ACCEPTANCE | S7-S16 |
| S1-G032 | Detached proof / second-monitor workflow | not implemented | browser pop-out window tied to exact message/evidence identity | UI | S9-S10 |
| S1-G033 | Historical activation boundary | **CLOSED THROUGH S6** — S2 rejects pre-activation rich source events; S5 narratives remain bound to that chain; S6 only reads/transports persisted narratives and exposes no backfill writer | preserve this no-synthesis rule through UI/cutover | ACCEPTANCE | S6 PASS |
| S1-G034 | Message materiality policy | **CLOSED S4 CORE** — versioned Analytical Policy deterministically maps exact S3 changes to PUBLISH/SILENT + reason codes | future source-specific projectors must consume this contract rather than invent ad-hoc spam thresholds | ACCEPTANCE | S4 PASS |
| S1-G035 | Secondary-engine Stream classification | **CLOSED THROUGH S5 CORE** — accepted projector registry still keeps deferred/research-only/later-phase sources out of canonical Stream truth and S5 renders only accepted upstream views | maintain classification as new S6+ source integrations are added | ACCEPTANCE | S5 PASS / ongoing invariant |

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
