# Crypto Signal — Stream S1 Gap Ledger

Status: **ACTIVE / CANONICAL S1 WORKING LEDGER**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
Baseline: `993e916bf8ab30157f529d4ef2c1fe456a1eccf9`

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
| S1-G001 | Rich canonical Stream event/message ledger | R20.5 ledger persists issuance/resolution only | versioned append-only Stream message/event store with source/story/evidence/capital refs | BUILD | S2 |
| S1-G002 | Source event projectors | intelligence families exist but do not emit customer Stream events | deterministic projectors per material intelligence/risk/decision/capital event | ADAPT | S2-S4 |
| S1-G003 | Story identity and relation graph | forecast identity exists; no general message story graph | explicit story_identity + relation/supersession semantics | BUILD | S3 |
| S1-G004 | Change detection | current feed events do not encode “what changed” | deterministic previous->current evidence/stance/score/risk/capital delta | BUILD | S3 |
| S1-G005 | Analytical View contract | facts/proof exist; no unified Stream opinion structure | stance/support/contradiction/next-condition/capital-consequence structure | BUILD | S4 |
| S1-G006 | Story-aware Turkish Narrative Engine | R23 SIMPLE/PRO exists but is not story-aware analyst prose | Fact Bundle -> Change Set -> Analytical View -> Narrative Plan -> renderer -> validator | BUILD | S5 |
| S1-G007 | Narrative persistence/versioning | no published rich Stream message text/version store | narrative schema, renderer version, original published text preserved | BUILD | S2/S5 |
| S1-G008 | Realtime delivery | product has GET feed only | SSE/WebSocket + cursor + reconnect catch-up + dedupe + polling fallback | BUILD | S6 |
| S1-G009 | Cursor/history API | current feed has limit only | stable older-history cursor and exact message lookup | BUILD | S6 |
| S1-G010 | Search/filter API | no Stream filtering/full-text | asset/category/timeframe/vault/evidence/state/importance/date/text search | BUILD | S6/S12 |
| S1-G011 | M6 family breakdown projection | aggregate score/proof exists, exact family contribution not a Stream/product payload | read model exposing 20/25/25/15/15 contribution/support/opposition/quality/freshness by exact confluence identity | ADAPT | S1/S4 |
| S1-G012 | Evidence object lookup by identity | proof exposes evidence identities but not every rich evidence object | read-only identity lookup for frozen orderbook/liquidity/order-flow/derivatives/on-chain/event objects | ADAPT | S1/S10 |
| S1-G013 | Visual annotation coordinate contract | frozen chart/geometry exists; not every technical claim has drawable coords | exact time/price/region coordinates + evidence identity + version | ADAPT | S10 |
| S1-G014 | Frozen order-book proof retrieval | Market Tape stores order books and proof can bind identity | exact snapshot-identity -> frozen orderbook product projection | ADAPT | S10 |
| S1-G015 | Order-flow visual proof | CVD/divergence/absorption evidence exists but no unified customer graph payload | frozen series/measurement projection tied to message evidence | ADAPT | S10 |
| S1-G016 | On-chain/Smart-Money live-source trace | engines/models/adapters exist, full live runtime not yet proven | trace provider/collector/store/freeze chain per sub-family; explicitly mark unavailable pieces | DISCOVER | S1 |
| S1-G017 | Liquidation continuous-source truth | bounded wire collector exists; production continuous status not proven in this wave | verify accepted runtime/coverage and define Stream availability semantics | DISCOVER | S1 |
| S1-G018 | Event Risk messages | event source + circuit breaker exist; no Stream events | material event-approach/risk-change/block/recovery projector | ADAPT | S2-S4 |
| S1-G019 | Provider/data-quality messages | status endpoints exist; no decision-relevant Stream projector | emit only material degradation/recovery messages | ADAPT | S2-S4 |
| S1-G020 | Three-vault canonical forward runtime | allocator/sizing/R22/R21 exist; current accepted execution rail is CORE/4h journal-isolated | one canonical Core/Tactical/Opportunity forward paper runtime mutating R22/R21 Epoch2 | INTEGRATE | S11 |
| S1-G021 | Capital event projection | Epoch2/R22 truth exists; no Stream event model | HOLD/BLOCK/ELIGIBLE/SIZED/EXECUTED/REDUCED/EXITED/accounting event projector | ADAPT | S11 |
| S1-G022 | Capital read models | Epoch2 summary route exists; transaction/sizing/assessment detail is not Stream-ready | exact assessment/sizing/intent/fill/bundle lookup contracts | ADAPT | S11 |
| S1-G023 | Zero-activity diagnostics | no single Stream truth explains long HOLD periods | candidates scanned, strongest candidate, blockers, last eligible/execution, source quality | BUILD/ADAPT | S11 |
| S1-G024 | One-panel Stream shell | current deployed UI is multi-section GALACTECH V2 | new messaging-first shell only | UI | S7 |
| S1-G025 | Compact expandable bubble | no final Stream V1 interaction | collapsed paragraph + chips; inline expansion preserving scroll | UI | S7-S8 |
| S1-G026 | Evidence Window Manager | current product uses conventional UI/modal patterns | draggable/resizable/minimize/pin/multi-window/detach manager | UI | S9 |
| S1-G027 | Context education in evidence windows | education API exists, not bound to message evidence | “Bu nedir?” concept mapping + message-specific “neden önemli?” | ADAPT/UI | S9 |
| S1-G028 | Notification chime/settings | not implemented | original sound + unlock/volume/mode/persistence; replay must be silent | UI | S13 |
| S1-G029 | Unread/new-message behavior | current polling feed does not implement messaging UX | bottom anchor + N-new control + no forced scroll | UI | S7 |
| S1-G030 | Long-session feed performance | current UI not designed as all-day message stream | virtualization/reverse pagination/memory/reconnect tests | UI/ACCEPTANCE | S14 |
| S1-G031 | Visual screenshot acceptance | code tests cannot prove rendered UX | CI preview/browser screenshots as artifacts + visual review at key states/viewports | ACCEPTANCE | S7-S16 |
| S1-G032 | Detached proof / second-monitor workflow | not implemented | browser pop-out window tied to exact message/evidence identity | UI | S9-S10 |
| S1-G033 | Historical activation boundary | old feed contains issuance/resolution but not rich story events | define forward activation boundary; do not synthesize rich history with future knowledge | BUILD | S2/S6 |
| S1-G034 | Message materiality policy | no general customer-message threshold | versioned rules deciding what deserves a message vs silent state update | BUILD | S2-S4 |
| S1-G035 | Secondary-engine Stream classification | accepted Intelligence Center engines are catalogued but not live feed | classify STREAM_PRIMARY / STREAM_CONTEXT / EVIDENCE_WINDOW_ONLY / RESEARCH_ONLY / INTERNAL_ONLY | DISCOVER | S1 |

## Highest-priority closure order

S1 should resolve discovery contracts before implementation:
1. S1-G011 / G012 / G016 / G017 / G022 / G035.
2. Freeze source-to-message and identity/temporal maps.
3. Then S2 begins with G001/G002/G003/G007/G033/G034.

Do not jump to visual UI before the backend/message contracts above are exact.

## S1 PASS gate

S1 may close only when:
- every major user-relevant capability is classified across all six pipeline stages;
- exact identity and temporal lineage for every planned Stream message family is documented;
- no “adapter missing = data missing” ambiguity remains;
- every S2 message source is either mechanically proven or explicitly excluded;
- open DISCOVER items above are resolved or deliberately deferred with an explicit product reason;
- current repo has been rechecked before marking PASS.
