# Crypto Signal — Stream S1 Capability Matrix

Status: **S1 PASS / CANONICAL DISCOVERY BASELINE**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
Observed main baseline: `2a61ad47e1f09640f3b36e4ccf09f6ed46dde7ef`  
Purpose: map accepted backend capability to the exact Intelligence Stream pipeline without confusing “adapter missing” with “backend capability missing”.

## 1. Audit semantics

Each capability is evaluated across six independent stages:

1. **ENGINE** — analysis/decision/accounting implementation exists.
2. **LIVE_SOURCE** — a current collector/adapter/runtime path is mechanically established.
3. **PERSISTED_EVIDENCE** — exact point-in-time evidence is persisted with identity/time lineage.
4. **PRODUCT_PROJECTION** — a safe read-only API/read model can expose the truth.
5. **MESSAGE_PROJECTION** — a canonical Stream event/message projector exists.
6. **UI_SURFACE** — Intelligence Stream V1 can show/open the capability.

Stage values:

- **YES** — mechanically established in current source/contracts.
- **PARTIAL** — some accepted path exists but required Stream semantics are incomplete.
- **DISCOVER** — implementation/model/adapters exist, but current live/persisted path is not yet proven end to end.
- **NO** — required Stream stage does not exist today.
- **N/A** — intentionally not part of the customer Stream.

A later missing stage does not erase an earlier one. For example, ENGINE=YES and MESSAGE_PROJECTION=NO means **build the projector**, not “data yok”.

---

## 2. Core Stream truth surfaces

| Capability | ENGINE | LIVE_SOURCE | PERSISTED_EVIDENCE | PRODUCT_PROJECTION | MESSAGE_PROJECTION | UI_SURFACE | S1 finding |
|---|---|---:|---:|---:|---:|---:|---|
| Frozen signal / geometry | YES | YES | YES | YES | PARTIAL | PARTIAL | Signal freeze bundle, entry zone, target and invalidation already exist; current feed does not expose rich geometry-change messages |
| Five-family Confluence | YES | YES/PARTIAL | **PARTIAL** | YES/PARTIAL | NO | PARTIAL | Full five-family contribution exists in `ConfluenceMatrixSnapshot` at issuance, but Decision Ledger does not persist that snapshot; Forecast/Proof preserve identity + aggregate truth only. Historical family windows therefore require new immutable decision-context persistence. |
| Decision Proof | YES | YES | YES | YES | PARTIAL | PARTIAL | Strong immutable source for expanded message + proof drill-down |
| Forecast issued | YES | YES | YES | YES | YES | PARTIAL | Current R20.5 feed already publishes issuance |
| Forecast resolved | YES | YES | YES | YES | YES | PARTIAL | Current R20.5 feed already publishes resolution |
| SIMPLE / PRO explainability | YES | YES via Proof | YES via Proof | YES | NO | NO for Stream V1 | R23 deterministically renders SIMPLE/PRO from same proof; new message pipeline should reuse rather than rewrite |
| Story/change memory | NO | N/A | NO | NO | NO | NO | New S3 requirement |
| Analytical View | NO as Stream contract | N/A | NO | NO | NO | NO | Existing decision facts are strong, but current system lacks the new structured “what changed / current view / next condition” contract |
| Natural Turkish Narrative Engine | PARTIAL | N/A | NO | NO | NO | NO | R23 text is deterministic/explanatory; story-aware original Turkish composer does not exist |
| Rich append-only message ledger | PARTIAL | YES | PARTIAL | PARTIAL | NO | NO | Decision ledger persists only issuance/resolution feed events; Stream V1 needs its own richer canonical message/event projection |
| Realtime push | NO | N/A | N/A | NO | NO | NO | Product exposes request/response GET feed only; no SSE/WebSocket route found |
| Stream search/filter/cursor history | NO | N/A | YES source history | NO | NO | NO | Current feed supports only newest `limit`; no cursor/filter/full-text API |

---

## 3. Five-family Intelligence coverage

### 3.1 Geometry / 20

Verified building blocks:
- immutable signal freeze;
- frozen candles in bundle;
- selected methodology/evidence;
- entry zone;
- invalidation;
- targets;
- M6 geometry family;
- Decision Proof methodology/frozen-chart/consumed-candles domains.

| Stage | State | Notes |
|---|---|---|
| ENGINE | YES | signal/confluence/methodology engines |
| LIVE_SOURCE | YES | canonical price/signal runtime already produces frozen signals |
| PERSISTED_EVIDENCE | YES | signal freeze + Decision Proof identities/times |
| PRODUCT_PROJECTION | YES | signal detail + Decision Proof |
| MESSAGE_PROJECTION | NO | no material geometry-change event family |
| UI_SURFACE | PARTIAL | deployed V2 can draw frozen chart; Stream window contract not implemented |

Main gap: exact reusable visual-annotation contract for every structure label beyond already frozen geometry.

### 3.2 Liquidity / 25

Verified building blocks:
- `liquidity_dynamics.py`;
- `liquidity_structure.py`;
- `liquidity_sweep.py`;
- `liquidation_heatmap.py`;
- Bybit order-book stream persisted by Market Tape;
- bounded Bybit liquidation wire collector;
- family/rich proof adapters;
- Decision Proof domains ORDER_BOOK / LIQUIDITY_MAP / LIQUIDATION_MAP.

| Stage | State | Notes |
|---|---|---|
| ENGINE | YES | multiple accepted liquidity engines |
| LIVE_SOURCE | PARTIAL | order-book stream is canonical; liquidation stream implementation exists but current continuous production enablement must be re-verified |
| PERSISTED_EVIDENCE | YES/PARTIAL | Market Tape order books are persisted; proof adapters freeze accepted identities; liquidation availability remains source-dependent |
| PRODUCT_PROJECTION | PARTIAL | proof exposes evidence identities/status, but no identity lookup API returns the full frozen liquidity/order-book object |
| MESSAGE_PROJECTION | NO | no liquidity/sweep/material-change Stream events |
| UI_SURFACE | NO for Stream V1 | new clickable evidence window not built |

Important: spoofing/hidden-liquidity/absorption-like semantics remain candidate evidence when that is what the engine emits.

### 3.3 Order Flow & Absorption / 25

Verified building blocks:
- public trades + order book Market Tape;
- `order_flow_microstructure.py`;
- `temporal_order_flow.py`;
- `order_flow_patterns.py`;
- CVD/delta/divergence/absorption proof semantics;
- Decision Proof ORDER_FLOW_CVD domain.

| Stage | State | Notes |
|---|---|---|
| ENGINE | YES | microstructure + temporal flow + rich pattern evidence |
| LIVE_SOURCE | YES | Bybit trade/order-book stream exists and persists raw/normalized data |
| PERSISTED_EVIDENCE | YES/PARTIAL | raw Market Tape persists source; frozen proof identities exist when accepted by issuance pipeline |
| PRODUCT_PROJECTION | PARTIAL | proof exposes identity/verdict; no general evidence-detail API for CVD/absorption object/visual series |
| MESSAGE_PROJECTION | NO | no CVD/absorption/divergence message projector |
| UI_SURFACE | NO for Stream V1 | evidence windows not built |

### 3.4 Derivatives / 15

Verified building blocks:
- Bybit derivatives adapter;
- Market Tape snapshot collection of derivatives;
- funding / OI / basis-oriented data contracts;
- derivatives context/crowding/dynamics engines;
- Decision Proof DERIVATIVES domain.

| Stage | State | Notes |
|---|---|---|
| ENGINE | YES | accepted derivatives families |
| LIVE_SOURCE | YES | `run_market_tape_snapshot.py` uses Bybit Linear derivatives adapter |
| PERSISTED_EVIDENCE | YES | Market Tape derivatives rows + frozen proof identity when consumed |
| PRODUCT_PROJECTION | PARTIAL | proof verdict/identity exists; rich metric lookup is not a dedicated product API |
| MESSAGE_PROJECTION | NO | no OI/funding/basis material-change messages |
| UI_SURFACE | NO for Stream V1 | no Stream evidence window |

### 3.5 On-chain / Smart Money / 15

Verified building blocks:
- Bitcoin network models + Blockstream adapter;
- exchange-flow contracts/engine;
- large-transfer clusters;
- wallet-cohort admission + forward evidence;
- on-chain network engine;
- Decision Proof ONCHAIN domain;
- rich proof adapters can consume accepted exchange-flow / large-transfer / wallet-cohort evidence.

| Stage | State | Notes |
|---|---|---|
| ENGINE | YES | on-chain/exchange-flow/transfer/cohort analysis exists |
| LIVE_SOURCE | PARTIAL | Bitcoin network has an accepted real public Blockstream adapter/source-quality gate, but no always-on Product/Stream collector is established. Exchange Flow / Wallet Cohort / Large Transfer explicitly have no live provider activation. |
| PERSISTED_EVIDENCE | PARTIAL | accepted freeze contracts exist; Bitcoin network/source engines are deterministic, but full always-on persisted Stream stores are not established. Provider-neutral M5 sub-families are not live-collected. |
| PRODUCT_PROJECTION | PARTIAL | Decision Proof domain can expose accepted identities; full detail lookup absent |
| MESSAGE_PROJECTION | NO | no exchange-flow/wallet/on-chain event projector |
| UI_SURFACE | NO for Stream V1 | not implemented |

S1 tracing is complete: Bitcoin network is a real accepted public-source engine but not an always-on Stream source; Exchange Flow / Wallet Cohort / Large Transfer remain provider-neutral research contracts without live provider activation. Stream must not call them live until a runtime/persistence path is explicitly added.

---

## 4. Event Risk and contextual intelligence

Verified:
- BLS calendar adapter;
- FRED CPI/employment fallback calendars;
- Federal Reserve monetary-news RSS;
- append-only raw payloads;
- append-only calendar/news/fetch tables;
- event-source status product endpoint;
- Event Risk/circuit-breaker engines;
- Decision Proof EVENT_CONTEXT domain.

| Stage | State |
|---|---|
| ENGINE | YES |
| LIVE_SOURCE | YES for established calendar/news providers |
| PERSISTED_EVIDENCE | YES |
| PRODUCT_PROJECTION | YES/PARTIAL |
| MESSAGE_PROJECTION | NO |
| UI_SURFACE | NO for Stream V1 |

Stream opportunity:
- scheduled event approaching;
- Event Risk state changed;
- trade/capital blocked by event gate;
- source degraded/recovered.

---

## 5. Additional intelligence engines

Current Intelligence Center catalog already lists accepted research surfaces such as:
- regime;
- trend/momentum;
- mean reversion;
- breakout/volatility;
- sentiment/attention;
- cross-market;
- meta-intelligence shadow;
- bounded Alpha/ML families;
- Learning Memory.

Important current product fact:
`accepted_intelligence_catalog()` labels catalog entries with `runtime_evidence_status = not_exposed_as_live_feed`.

S1 interpretation:
- these engines are not “missing”;
- they are not automatically eligible for the main customer stream either;
- each must be classified as one of:
  - STREAM_PRIMARY;
  - STREAM_CONTEXT;
  - EVIDENCE_WINDOW_ONLY;
  - RESEARCH_ONLY;
  - INTERNAL_ONLY.

This classification remains open in S1 and must be grounded in exact live/persisted evidence.

---

## 6. Capital capability

### 6.1 Canonical Epoch 2 accounting

Verified:
- 1,000 USDT Epoch 2;
- Core / Tactical / Opportunity Reserve;
- exact per-vault snapshots;
- consolidated snapshot;
- NAV / cash / exposure / realized and unrealized PnL / drawdown / turnover;
- immutable previous-snapshot lineage;
- read-only Product route `/api/paper/epoch2-state`.

Pipeline stages:

| Stage | State |
|---|---|
| ENGINE | YES |
| LIVE_SOURCE | YES for canonical current ledger state |
| PERSISTED_EVIDENCE | YES |
| PRODUCT_PROJECTION | YES |
| MESSAGE_PROJECTION | NO |
| UI_SURFACE | PARTIAL in old V2 / NO in Stream V1 |

### 6.2 Smart Capital Allocator

Verified:
- Core eligibility;
- Tactical 1m/5m evidence contract;
- Opportunity recovery evidence;
- explicit reason codes;
- HOLD_CASH / eligible-research-envelope semantics;
- all three starting budgets.

Pipeline:

| Stage | State |
|---|---|
| ENGINE | YES |
| LIVE_SOURCE | PARTIAL |
| PERSISTED_EVIDENCE | PARTIAL |
| PRODUCT_PROJECTION | NO dedicated rich assessment route |
| MESSAGE_PROJECTION | NO |
| UI_SURFACE | NO for Stream V1 |

### 6.3 Position sizing / transaction tape

Verified:
- three-vault-aware sizing bridge;
- R22 intent/fill models;
- R22 atomic Epoch2 tape;
- append-only intents/fills/bundles;
- exact target-vault mutation;
- non-target-vault mutation guard;
- exact post-trade three-vault + consolidated accounting bundle.

Pipeline:
- ENGINE=YES
- PERSISTED_EVIDENCE=YES as infrastructure
- current canonical forward runtime integration=PARTIAL
- PRODUCT_PROJECTION=NO for transaction-level Stream consumption
- MESSAGE_PROJECTION=NO

### 6.4 Current forward execution gap

Verified current WC2 execution runtime:
- requires canonical Epoch2 state;
- selects **CORE** snapshot;
- replays/commits a separate WC2 execution journal;
- produces simulated BUY/EXIT;
- does not by itself prove canonical R22/R21 all-vault mutation.

Therefore Stream S1 keeps the existing roadmap finding:

**one canonical three-vault forward virtual-capital runtime remains a required backend closure.**

This is necessary for capital messages to represent actual canonical Epoch2 state changes rather than parallel simulation journals.

---

## 7. Current feed and history reality

Current `/api/intelligence-feed`:
- reads `r20_5_live_feed_events`;
- accepts only `limit` (1..1000);
- returns newest-first;
- has no cursor;
- no asset/category/timeframe/vault filters;
- no full-text search;
- no realtime push;
- no story model.

Current event semantic:
- one FORECAST_ISSUED and at most one FORECAST_RESOLVED per forecast.

This is a valuable immutable seed ledger, but it is not the Stream V1 message backend.

---

## 8. Existing UI reality

Deployed GALACTECH V2:
- polls the current intelligence feed;
- already opens Decision Proof;
- already reads Epoch2/mission-control;
- already renders frozen OHLC from immutable bundle;
- contains archive/performance/education/system surfaces.

For Stream V1:
- these are implementation evidence/reusable logic;
- the old multi-screen UI is not the target;
- reusable proof/fetch/format helpers may be extracted only if doing so preserves Stream architecture and does not drag old IA into the new product.

---

## 9. Screenshot / visual acceptance capability

Code acceptance alone is insufficient for Stream V1.

This capability is **already materially implemented and must be reused** rather than rebuilt.

Current-main evidence:
- `.github/workflows/crypto-mac-command.yml` has the allowlisted `visualsnapshot` command;
- job `GALACTECH VISUAL SNAPSHOT UID504` captures the live local Product surface at `http://127.0.0.1:48700`;
- Chrome/Chromium-family headless capture is preferred, with Safari fallback;
- current headless viewports are desktop 1440x950 and mobile 430x860;
- PNGs + health/metadata are uploaded as a GitHub Actions artifact;
- exact Product HEAD, read-only state and REAL_CAPITAL=0 are recorded;
- hard browser timeout/process-group cleanup/renderer limits are already present;
- UID501 has an existing narrow bridge command `visualcleanup504` that can clean UID504 headless browser processes.

Therefore the Stream gap is **not screenshot infrastructure creation**. The gap is to extend the accepted visualsnapshot path with Stream-specific deterministic states, preview routing/fixtures and the additional viewport/state matrix below.

Required future screenshot states:
- empty/new-user stream;
- normal mixed stream;
- new-message arrival;
- expanded message;
- several evidence windows open;
- detached-proof affordance;
- search/filter active;
- long history state;
- sound/settings state;
- reconnect/degraded-data state;
- desktop common viewport(s);
- laptop viewport;
- mobile sanity viewport.

The assistant cannot directly view the user’s local `127.0.0.1` screen without a supplied image or artifact. User-uploaded screenshots and CI-generated screenshot artifacts are valid visual-review inputs.

---

## 10. S1 audit status

### Mechanically established in this wave
- current message feed is issuance/resolution only;
- rich five-family backend evidence substantially exists;
- R23 SIMPLE/PRO exists and is proof-bound;
- current Product has no realtime push;
- current Product feed has no search/cursor/filter model;
- Market Tape supplies live order-book/trade/derivatives paths;
- Event Source supplies persisted calendar/news paths;
- on-chain/smart-money live status is resolved: Bitcoin network has a real public source but no always-on Stream runtime; Exchange Flow / Wallet Cohort / Large Transfer have no live provider activation;
- capital accounting/tape primitives are stronger than the current Product projection;
- canonical three-vault forward runtime remains incomplete;
- existing UID504 Chromium screenshot-artifact acceptance is reusable; Stream-specific fixture/state coverage must be added and should remain mandatory during UI stages.

### Wave-2 closeout findings

Resolved mechanically:
- exact identity + temporal lineage is documented in `CRYPTO_SIGNAL_STREAM_S1_IDENTITY_TEMPORAL_MAP.md`;
- source-to-message mapping and secondary-engine classification are documented in `CRYPTO_SIGNAL_STREAM_S1_SOURCE_MESSAGE_MAP.md`;
- liquidation collector status is resolved: implementation/persistence exists, production continuous collector is explicitly disabled;
- on-chain/smart-money status is resolved by sub-family rather than one vague bucket;
- M6 family breakdown persistence gap is exact: contribution data exists at issuance but is not persisted in the R20/R20.5 Decision Ledger;
- universal evidence-by-identity lookup does not exist; geometry, Market Tape and Event Source have different persistence/read paths, while some accepted research freezes need future immutable Stream evidence persistence;
- rich Capital Science / Position Sizing runtime objects are not fully persisted/projected; R22 preview and canonical R22/R21 transaction/accounting infrastructure are separately persisted;
- existing Chromium visual acceptance is already reusable.

### S1 PASS conclusion

S1 discovery is **PASS** at the contract/audit level.

All major user-relevant capabilities are now classified, open DISCOVER items have been converted into exact implementation gaps or explicit not-live boundaries, and the source/identity/time/message contracts needed to begin S2 are documented.

S1 PASS does **not** mean those gaps are implemented. S2+ must build the missing immutable Stream message/evidence/context projections without inventing historical truth.
