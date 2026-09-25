# Crypto Signal — Stream S1 Gap Ledger

Status: **CANONICAL STREAM GAP LEDGER / S2 CLOSEOUT APPLIED**  
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
| S1-G003 | Story identity and relation graph | S2 now provides forecast-root story identity plus relation/supersession schema; current/previous story state and continuity engine are not built | deterministic story state + exact prior-message relations without heuristic time-only joins | BUILD | S3 |
| S1-G004 | Change detection | current feed events do not encode “what changed” | deterministic previous->current evidence/stance/score/risk/capital delta | BUILD | S3 |
| S1-G005 | Analytical View contract | facts/proof exist; no unified Stream opinion structure | stance/support/contradiction/next-condition/capital-consequence structure | BUILD | S4 |
| S1-G006 | Story-aware Turkish Narrative Engine | R23 SIMPLE/PRO exists but is not story-aware analyst prose | Fact Bundle -> Change Set -> Analytical View -> Narrative Plan -> renderer -> validator | BUILD | S5 |
| S1-G007 | Narrative persistence/versioning | S2 reserves analytical/narrative/renderer version fields and preserves projector/materiality lineage; no published Turkish message text exists yet | S5 must persist original published narrative text/version and never silently rewrite it | BUILD | S5 |
| S1-G008 | Realtime delivery | product has GET feed only | SSE/WebSocket + cursor + reconnect catch-up + dedupe + polling fallback | BUILD | S6 |
| S1-G009 | Cursor/history API | current feed has limit only | stable older-history cursor and exact message lookup | BUILD | S6 |
| S1-G010 | Search/filter API | no Stream filtering/full-text | asset/category/timeframe/vault/evidence/state/importance/date/text search | BUILD | S6/S12 |
| S1-G011 | M6 family breakdown persistence/projection | **CLOSED S2 PERSISTENCE** — full five-family M6 snapshot is frozen in Stream decision context and Fact Bundle | S4 may consume the exact persisted family breakdown for analytical composition; no recomputation from future data | ADAPT | S4 |
| S1-G012 | Evidence object persistence/lookup by identity | S2 persists exact evidence-reference identities in source/message truth; universal rich evidence-object lookup adapters are still absent | S10 must resolve supported identities to frozen proof objects without reconstructing history from current data | ADAPT | S10 |
| S1-G013 | Visual annotation coordinate contract | frozen chart/geometry exists; not every technical claim has drawable coords | exact time/price/region coordinates + evidence identity + version | ADAPT | S10 |
| S1-G014 | Frozen order-book proof retrieval | Market Tape stores order books and proof can bind identity | exact snapshot-identity -> frozen orderbook product projection | ADAPT | S10 |
| S1-G015 | Order-flow visual proof | CVD/divergence/absorption evidence exists but no unified customer graph payload | frozen series/measurement projection tied to message evidence | ADAPT | S10 |
| S1-G016 | On-chain/Smart-Money Stream runtime | discovery resolved: Bitcoin network has real public Blockstream source but no always-on Stream runtime; Exchange Flow/Wallet Cohort/Large Transfer have no live provider activation | add runtime persistence only for explicitly selected/accepted sub-families; keep non-live M5 provider-neutral engines research/evidence-only | ADAPT/DEFERRED_BY_SOURCE | S2+ |
| S1-G017 | Liquidation continuous-source activation | discovery resolved: bounded collector + hot/cold persistence exist, but production continuous collector is explicitly disabled | Stream may use exact persisted liquidation evidence when available; live liquidation messages require separate accepted collector activation | DEFERRED_BY_ACTIVATION | S2+ |
| S1-G018 | Event Risk messages | S2 projector registry defines Event Risk as REQUIRES_CHANGE_DETECTION; no premature live projector is active | S3-S4 must detect material approach/block/recovery transitions before publication | ADAPT | S3-S4 |
| S1-G019 | Provider/data-quality messages | S2 projector registry defines provider/data-quality as REQUIRES_CHANGE_DETECTION | S3-S4 must emit only decision-relevant degradation/recovery transitions | ADAPT | S3-S4 |
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
| S1-G033 | Historical activation boundary | **CLOSED S2** — one immutable forward activation boundary rejects rich pre-activation backfill | S6 history/reconnect must respect the same activation boundary | ACCEPTANCE | S6 |
| S1-G034 | Message materiality policy | **CORE S2 CLOSED** — versioned policy identity + immutable PUBLISH/SILENT decision is bound into message identity for accepted issuance/resolution events | S3-S4 extend policy with deterministic change thresholds for new material event families | BUILD/ADAPT | S3-S4 |
| S1-G035 | Secondary-engine Stream classification | **S2 ENFORCEMENT CONTRACT ADDED** — accepted projector registry keeps deferred/research-only/later-phase sources out of implemented live projectors | maintain the classification while S3-S5 projectors/narrative are added | ACCEPTANCE | S3-S5 |

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
