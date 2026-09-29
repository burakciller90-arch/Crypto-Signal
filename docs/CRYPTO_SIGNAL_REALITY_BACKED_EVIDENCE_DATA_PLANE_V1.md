# Crypto Signal — Reality-Backed Evidence Data Plane V1

Status: **ACTIVE EXECUTION ROADMAP**
Date opened: 2026-09-27
Company: GALACTECH
Product: Crypto Signal
Repository: `burakciller90-arch/Crypto-Signal`
Canonical work root: `/Volumes/Crypto-504/Crypto-Signal-Workbench`
Primary workstream: `01_EVIDENCE_DEPTH`
Safety: **REAL_CAPITAL=0**

## 0. Purpose

Crypto Signal already contains substantial signal, market-structure, microstructure, derivatives, on-chain, event-risk and proof infrastructure. The remaining problem is not "invent more indicators." The problem is to make every accepted evidence family **reality-backed, continuously collected, PIT-safe, freshness-gated, immutable when used, and directly inspectable**.

This roadmap is the execution authority for that data-plane completion.

It sits under the accepted umbrella:

`docs/CRYPTO_SIGNAL_EVIDENCE_DEPTH_VISUAL_PROOF_FRONTIER_V1.md`

The five-family decision matrix remains:

- Geometry — 20
- Liquidity — 25
- Order Flow — 25
- Derivatives — 15
- On-chain — 15

Event Risk remains outside the 100-point matrix.

No new family is added merely because a new dataset exists. New evidence must either:
1. enrich an existing family without double counting, or
2. remain a score-external context / quality / veto layer.

Confluence remains weighted evidence support/opposition, **not probability**.

## 1. Locked product truth

The target system must be able to answer, for any new forward signal:

1. **What did the system actually observe?**
2. **From which source/provider/venue?**
3. **At what source time, observation time and ingestion time?**
4. **Was the observation fresh enough for that evidence family?**
5. **Which engine transformed the observation into evidence?**
6. **Was that evidence directional, contextual, contradictory, stale or unavailable?**
7. **Which exact payloads were frozen when the decision was made?**
8. **Can a customer inspect those frozen measurements visually without reading hashes?**
9. **Can the system prove no future information was used?**
10. **Can the system fail closed when a source is stale, missing or contradictory?**

If the answer to any required item is no, that evidence rail is not production-ready.

## 2. Current reality baseline — 2026-09-27

This roadmap is based on live UID504 read-only audits, not repository assumptions.

### 2.1 Latest Market Tape / Stream audit

UID504 run: `36345746684`

Observed at `2026-09-27T19:49:40.187Z`:

- order books: 457,710 rows; latest source event age ~34.1s;
- public trades: 2,124,933 rows; latest source event age ~34.7s;
- derivatives: 195 rows; latest observation age ~23.7h;
- liquidations: 0 rows;
- liquidation coverage: 0 rows;
- collector heartbeat: live; latest successful ingestion age effectively 0;
- normalized Market Tape rows: 2,582,913;
- checked 15m candle cache close: ~49.7m old;
- Stream system-view latest event: ~36.2s old;
- Product Stream HTTP: 200;
- REAL_CAPITAL=0.

Interpretation:
- the Market Tape collector is alive;
- order-book/trade truth is genuinely being accumulated;
- derivatives is stale;
- liquidation truth is absent;
- one checked candle-cache rail is stale and must be diagnosed even though live signal freezing continued in runtime logs.

### 2.2 Event-source audit

UID504 run: `36345747792`

Observed truth:

- persisted event DB exists;
- `runtime_status=PERSISTED_EVIDENCE_ONLY`;
- `online_status=NOT_ASSERTED`;
- `process_status=NOT_MEASURED`;
- `coverage_claim=SOURCE_SCOPED_ONLY`;
- latest successful source fetch age ~25.7h;
- Fed RSS and FRED CPI/employment persistence exist;
- BLS source returned HTTP 403;
- REAL_CAPITAL=0.

Event Risk code exists, but continuous fresh operation is not yet accepted.

### 2.3 Runtime error audit

UID504 run: `36346024642`

Observed examples:

- REST candle calls with SSL `WRONG_VERSION_NUMBER`;
- DNS resolution failures;
- request timeout;
- Market Tape heartbeat/database `database is locked`;
- gap-monitor ingestion-time regression errors;
- async close errors after collector failures.

The live system is functioning, but the data plane is not yet robust enough to claim uninterrupted professional evidence coverage.

## 3. Architecture to build

Every evidence rail must follow the same controlled chain:

```text
External source / venue
        ↓
Read-only collector
        ↓
Raw source envelope
        ↓
Normalization
        ↓
Coverage + gap ledger
        ↓
Freshness / quality gate
        ↓
PIT evidence engine
        ↓
Family evidence adapter
        ↓
Immutable decision freeze
        ↓
Exact customer proof projection
        ↓
Visual renderer / Portfolio provenance
```

### 3.1 Raw source envelope

Every accepted observation must retain, where available:

- provider;
- venue;
- market/instrument type;
- symbol / asset / network;
- provider-native event identity;
- provider/source timestamp;
- local observed timestamp;
- local ingested timestamp;
- sequence/update identity when the source provides one;
- adapter version;
- normalized payload;
- raw payload identity or raw-body digest where legally/technically appropriate.

A normalized value without source timing/coverage truth is not enough.

### 3.2 Coverage ledger

Every live rail must persist explicit coverage:

- collection start/end;
- connected/disconnected periods;
- provider gaps;
- sequence gaps;
- REST recovery windows;
- source-specific failures;
- stale intervals;
- unsupported symbols/instruments.

"No rows" and "no activity" must never be confused.

### 3.3 Fail-closed rule

Stale or missing input cannot silently retain its previous vote.

Allowed outcomes include:

- OBSERVED;
- PARTIAL;
- STALE;
- UNAVAILABLE;
- CONFLICT;
- NOT_EVALUABLE.

The customer can receive an explanation, but no fabricated measurement.

## 4. Evidence model — what is required

## 4.1 Geometry — 20 points

Geometry is the chart/structure family and canonically contains:

- Price Action;
- Elliott Wave;
- Harmonic Patterns.

Target collection/input:

- closed candles for accepted symbols/timeframes;
- provider timestamps;
- source completeness;
- multi-timeframe context;
- provider divergence where available.

Target frozen evidence:

- exact consumed OHLC candles;
- Price Action structures/levels/displacement/imbalances actually used;
- Elliott count/candidate/state actually used;
- Harmonic candidate/pattern/PRZ actually used;
- entry/trigger zone;
- invalidation;
- targets;
- methodology versions;
- conflict/absence between methodologies.

Important:
- an Elliott/Harmonic/PA engine returning "no accepted candidate" is valid evidence state;
- a signal must never reconstruct an old geometry chart from current candles.

## 4.2 Liquidity — 25 points

Current live baseline:
- order-book snapshots;
- `liquidity_dynamics`.

Promote, when source quality permits:

- persistent liquidity-pool candidates;
- depth addition/removal;
- depletion;
- replenishment;
- sweep candidates;
- spoofing candidates;
- hidden-liquidity candidates;
- observed liquidation context when real coverage exists.

Required source truth:

- L2 depth;
- provider sequence/update IDs where available;
- bids/asks and quantities;
- source/ingest time;
- explicit depth level coverage.

Scientific boundaries:

- spoofing = candidate behavior, never intent attribution;
- hidden liquidity = candidate, never proof of a specific actor;
- liquidity levels are measurements/candidates, not guaranteed "magnets."

## 4.3 Order Flow — 25 points

Current live baseline:
- public trades;
- order-book pressure;
- taker-flow state.

Promote:

- exact buy/sell delta;
- window-local CVD;
- temporal flow;
- price/CVD divergence candidate;
- bounded absorption candidate;
- price-response context.

Required source truth:

- provider trade identity;
- event timestamp;
- price;
- quantity/notional;
- aggressor/taker side where source semantics support it;
- exact associated order-book context.

Important:
- CVD is explicitly local to the accepted window/source, not "global market CVD";
- absorption does not prove iceberg/manipulation/actor identity.

## 4.4 Derivatives — 15 points

Required live baseline:

- mark/index price;
- open interest;
- funding rate;
- basis;
- timestamped instrument metadata.

Promote after freshness restoration:

- price/OI dynamics;
- funding percentile;
- funding acceleration;
- basis dynamics;
- crowding;
- squeeze-risk context;
- observed liquidation context.

### New required enrichment: Options / volatility positioning

Options belong inside **Derivatives**, not as a sixth family.

Priority coverage for BTC/ETH:

- ATM implied volatility;
- volatility index where a provider supplies it;
- IV term structure;
- call/put skew such as 25-delta skew when correctly computable;
- option open interest by expiry/strike;
- volume by expiry/strike where source quality permits;
- put/call OI and volume context;
- major expiry concentration.

Provider candidates may include crypto-native options venues and institutional futures/options markets, subject to licensing and source-contract acceptance.

Do not claim:
- dealer gamma positioning unless the required positions/assumptions are explicit and defensible;
- max-pain as a deterministic price target;
- options OI as directional proof by itself.

## 4.5 On-chain — 15 points

No standalone live on-chain vote is authorized until a real accepted provider/source exists.

Required priority evidence:

1. exchange inflow/outflow;
2. large-transfer observations with provider-backed attribution;
3. exchange/non-exchange cluster role where evidence supports it;
4. wallet cohorts with PIT admission rules;
5. stablecoin capital/liquidity flow context.

### New required enrichment: Stablecoin liquidity

Inside On-chain / capital-flow context:

- exchange stablecoin inflow/outflow where reliable;
- large mint/burn events where source semantics are exact;
- supply changes;
- major bridge/chain flow only if provider/network coverage is explicit.

Important:
- a stablecoin mint is not automatically bullish;
- an exchange transfer is not automatically a sell/buy;
- wallet clusters are not "insiders" or "institutions" unless the provider explicitly and defensibly attributes them.

Bitcoin network cadence/utilization may remain contextual but is not a substitute for real capital-flow evidence.

## 4.6 Event Risk — score external

Required:

- economic calendar;
- central-bank events;
- inflation/employment releases;
- high-impact news/event observations;
- event countdown;
- source timestamp;
- update process health.

Event Risk can:

- WAIT;
- REDUCE;
- VETO new exposure;
- mark high uncertainty.

It does not receive points in the 100-point directional matrix.

## 4.7 Cross-market / macro regime — score external

Existing code already supports VIX / Treasury context.

Professional target may extend to additional accepted macro references such as:

- USD regime / dollar index source;
- real/nominal rates where source semantics are stable;
- broad risk-stress context.

This is regime/context, not an automatic long/short vote.

## 4.8 New required layer: Cross-venue confirmation and dislocation

This is **not a sixth family**.

Purpose:

- detect whether a claimed market event is venue-local or broad;
- compare spot/perpetual prices;
- compare spreads/depth where comparable;
- compare funding/OI when multiple accepted venues expose compatible semantics;
- detect provider divergence/data anomalies.

Examples:

- Bybit order-flow shock with no confirmation elsewhere → reduce confidence / mark venue-local;
- price dislocation between venues → explicit context;
- one provider stale while another is fresh → no silent substitution.

Existing provider-divergence infrastructure should be extended rather than replaced.

## 4.9 Sentiment / attention — research context only

Existing Fear & Greed / attention code may remain useful for regime narration and research.

It is **not mandatory directional evidence** for V1 closure because:

- source cadence is slow;
- semantics are broad;
- overlap with price/regime can be high.

It must not dilute stronger market microstructure evidence.

## 4.10 ETF / institutional flow — later context, not closure blocker

Spot BTC/ETH ETF flows may become useful medium-horizon context if a reliable timestamped source contract is accepted.

For V1:
- optional;
- slow context;
- no intraday directional shortcut;
- not a blocker for evidence-data-plane PASS.

## 5. Evidence dependency / double-counting control

This is mandatory.

The system must know when two claims derive from the same underlying observation.

Examples:

- liquidity replenishment and order-flow absorption may share the same L2 book;
- taker flow and CVD share the same public trades;
- derivatives crowding may depend on funding + OI + liquidation evidence;
- exchange flow and large-transfer clusters may overlap.

Each family freeze must carry an **evidence dependency graph** or equivalent lineage grouping.

Confluence must not treat correlated derivatives of the same source event as independent votes.

Rules:

- enrichment can improve evidence quality/context without automatically increasing directional points;
- one raw observation may support multiple visual explanations but must not create duplicated statistical confidence;
- cross-family overlap must be explicit in acceptance tests.

## 6. Initial engineering freshness SLOs

These are versioned engineering targets, **not claims about market predictability or universal provider guarantees**.

| Rail | Initial target |
|---|---|
| collector heartbeat | <= 5s |
| spot order book / public trades | <= 10s at family evaluation |
| liquidation events | <= 10s when venue feed is connected |
| derivatives OI/mark/basis | <= 120s |
| funding observation | <= 5m unless provider updates more frequently |
| BTC/ETH options surface | <= 120s where real-time provider permits |
| closed 15m candle availability | <= 90s after close |
| higher-timeframe candle | <= 120s after close |
| event calendar process | scheduled refresh <= 15m plus exact event timestamps |
| breaking/news event source | <= 120s where source supports it |
| on-chain exchange/transfer feeds | provider-specific, target <= 10m |
| cross-market daily sources | source-session aware; no false intraday freshness |

A rail outside its accepted freshness budget is stale and cannot masquerade as current.

## 7. Source strategy

### 7.1 Prefer streaming for high-frequency truth

Primary streaming candidates:

- order books;
- public trades;
- liquidations;
- real-time derivatives updates;
- real-time options surface where available.

REST may be used for:

- bootstrap snapshots;
- reconciliation;
- gap repair;
- lower-frequency context.

### 7.2 Multi-provider truth

Use multiple providers only when semantics can be normalized honestly.

Provider disagreement is evidence about data quality/venue state, not something to average away automatically.

### 7.3 Read-only authority

All evidence collectors are read-only.

If provider credentials are needed:
- market-data/read scopes only;
- secrets outside repository;
- no order permissions;
- no withdrawal permissions;
- no REAL_CAPITAL authority.

## 8. Execution phases

## RDP0 — Authority + live audit

Status: **PASS**

Completed:
- repository capability audit;
- live Market Tape freshness audit;
- event-source state audit;
- runtime-error audit;
- evidence gaps classified as source, runtime, wiring, proof or UI.

Acceptance evidence:
- UID504 `36345746684`;
- UID504 `36345747792`;
- UID504 `36346024642`.

## RDP1 — Collector and runtime reliability

Status: **PASS**

Goal:
- make the existing data substrate continuously trustworthy before expanding it.

Work:
- diagnose/fix SSL/proxy/DNS failures;
- remove Market Tape writer-lock/gap-time regression failure modes;
- verify single-writer/transaction behavior;
- prove supervisor recovery after process/provider failure;
- diagnose stale candle-cache rail;
- add rail-specific heartbeat/freshness/coverage checks;
- distinguish "collector process alive" from "source truth fresh."

PASS:
- no silent stale rail;
- no repeated DB-lock collector crash;
- closed-candle SLO accepted;
- book/trade continuity proven across restart;
- read-only soak reports persist explicit gaps.

Acceptance evidence:
- cadence merge PR #1548 / main `fabaa8830bd599e564bf76c1e0adbee89ec9b5f3`;
- UID504 R11 exact-main recovery `36357042192`: Product healthy/read-only, collector alive, ingestion fresh, REAL_CAPITAL=0;
- UID504 post-boundary freshness `36357255060`: orderbook 0.339s, trades 0.058s, derivatives 12.464s, collector ingestion 24.872s, Stream/Product live; latest closed 15m candle present 83.680s after close;
- UID504 six-context read-only acceptance `36357353548`: Bybit BTC/ETH/SOL availability lag 8.958s / 11.406s / 13.663s; Binance BTC/ETH/SOL 16.163s / 20.413s / 24.332s; `RDP1_CLOSED_CANDLE_SLO_PASS=YES`;
- liquidation coverage may remain zero/unsupported at this phase and is not an RDP1 blocker.

## RDP2 — Canonical source envelope + coverage ledger

Status: **PASS**

Goal:
- enforce one professional contract across every evidence rail.

Work:
- canonical source/observed/ingested timestamps;
- provider-native IDs and sequence semantics;
- raw/normalized identity;
- coverage ledger;
- gap/recovery ledger;
- source capability registry;
- explicit freshness state.

Progress:
- **RDP2-A source-contract foundation ACCEPTED** on main `585378dc32753d2e31894bd666eb1e084802e6ab` via PR #1555;
- **RDP2-B live Bybit WebSocket Market Tape wiring ACCEPTED** on main `b2f6bdc64e4830de7a021250155c3cea6f587922` via PR #1557;
- **RDP2-C Bybit REST Market Tape snapshot provenance ACCEPTED** on main `199cf203a41d403d14a38ce73acb226fd271cd16` via PR #1559;
- **RDP2-D live Bybit/Binance candle provenance ACCEPTED** on main `823dfe1df0dddcf24cc2f26e58a0301ed31702cd` via PR #1561;
- UID504 `36384253135`: exact Workbench/source PASS, 44 tests PASS, Ruff PASS, mypy 9 source files PASS, py_compile PASS, REAL_CAPITAL=0; RDP1 candle regression `36384253098` PASS;
- Geometry candle fetches now preserve exact provider source proof across direct fetch, cutoff probe and historical recovery and resolve each envelope to the CandleStore truth actually persisted;
- Market Tape and candle rails can answer PIT source existence/absence through canonical envelope/coverage semantics; unsupported/deferred rails remain explicit rather than fabricated;
- clean Workbench bootstrap `36384319438` = exact `823dfe1df0dddcf24cc2f26e58a0301ed31702cd`;
- **RDP2 PASS**. Next: **RDP3-A — deterministic frozen Geometry Proof/annotation contract from immutable DecisionFreezeBundle only.**

PASS:
- every family can explain what data existed and what data did not exist at an as-of time.

## RDP3 — Geometry production truth

Status: **PASS**

Progress:
- **RDP3-A frozen Geometry Proof ACCEPTED** on main `abf1dfdc64c8dc51fe49487129a17a6a2432d74f` via PR #1563;
- UID504 `36385612839`: exact Workbench/source PASS, focused Geometry Proof acceptance PASS, Ruff PASS, mypy PASS, py_compile PASS, REAL_CAPITAL=0;
- proof annotations for Price Action, Harmonic, Elliott and selected signal geometry are deterministic, SHA-addressed, consumed-candle scoped and derived only from immutable DecisionFreezeBundle data; current CandleStore/Market Tape/methodology-engine reads are forbidden;
- exact selected-evidence lineage across frozen methodology results, confluence selections and SignalDecision is fail-closed;
- **RDP3-B immutable Geometry Proof replay ACCEPTED** on main `656c19fc6f4a39634e0594c51d021c741c288750` via PR #1564;
- UID504 `36386203825`: exact Workbench/source PASS, atomic replay/ledger acceptance PASS, Ruff PASS, mypy PASS, py_compile PASS, REAL_CAPITAL=0;
- every new forward signal freeze atomically writes one immutable Geometry Proof in the same ledger transaction; proof rows are read-only replayable by signal or bundle and SQLite enforces the exact bundle+signal parent pair;
- historical freezes are deliberately not proof-backfilled; forward-only truth is preserved;
- clean Workbench bootstrap `36386287130` = exact `656c19fc6f4a39634e0594c51d021c741c288750`;
- **RDP3 PASS**. Next: **RDP4-A — rich Liquidity Structure/Sweep + Temporal Order Flow live family wiring.**

Goal:
- make PA + Elliott + Harmonic jointly inspectable as Geometry.

PASS:
- new forward signal can replay its exact Geometry evidence with no current-data substitution.

## RDP4 — Rich Liquidity + Order Flow live wiring

Status: **PASS**

Progress:
- **RDP4-A rich Market Tape family wiring ACCEPTED** on main `0356f6c1024935bfeffbcc7e61b2a7d95bd9ecc5` via PR #1566; UID504 `36387736662` PASS;
- **RDP4-B Absorption + Price/CVD dependency wiring ACCEPTED** on main `1e2ad0540d3c1c2b7d40b98abbd88126f8ce01a9` via PR #1568;
- UID504 `36392872215`: exact Workbench/source PASS, focused pattern-dependency + RDP4-A + live-clock/candle regressions PASS, Ruff PASS, mypy PASS, py_compile PASS, REAL_CAPITAL=0;
- separate RDP4-A regression `36392872158` PASS and RDP2 candle-source regression `36392872168` PASS;
- Liquidity Structure/Sweep, Temporal Order Flow, Absorption and Price/CVD Divergence now appear inside the existing Liquidity/Order Flow family proof without new family weights;
- exact PIT/dependency/overlap lineage is preserved; Absorption reuses the exact existing structure/flow freezes; divergence reads canonical 15m CandleStore data read-only and remains explicit UNRESOLVED when the 2m flow window lacks compatible closed-candle coverage;
- no actor-intent claims, no synthetic lower-timeframe price rail, no context-only direction invention, and missing candle cache fails without initialization;
- clean Workbench bootstrap `36393163025` = exact `1e2ad0540d3c1c2b7d40b98abbd88126f8ce01a9`;
- **RDP4 PASS**. Next: **RDP5-A — continuous liquidation runtime + explicit connected/silence/stale coverage/fail-closed freshness, reusing the existing Bybit allLiquidation parser/persistence/coverage model.**

Goal:
- promote existing rich M2/M3 engines into the forward-only family path.

Liquidity:
- dynamics;
- structure;
- persistent pool candidate;
- sweep;
- spoofing candidate;
- hidden-liquidity candidate.

Order Flow:
- microstructure;
- temporal delta;
- window-local CVD;
- divergence;
- absorption.

PASS:
- exact PIT freezes;
- dependency/overlap lineage;
- rich evidence appears in family proof;
- no actor-intent claims;
- no direction invented from context-only engines.

## RDP5 — Derivatives + liquidation restoration

Status: **PASS**

Progress:
- continuous Bybit `allLiquidation` collection is supervisor-owned on SSD504 under `REAL_CAPITAL=0`, with explicit heartbeat and transport connected/stale/disconnected coverage;
- transport liveness is stored separately from provider liquidation-event coverage; silence is never converted into zero-event evidence;
- Derivatives Context + Dynamics are live inside the existing Derivatives family, with mark/index/OI/funding/basis preserved through canonical source provenance;
- observed Liquidation Heatmap + Derivatives Crowding are wired into the same Derivatives family with no new score family and no direction invention;
- provider coverage is consumed PIT-safely at `observed_at_ms`; incomplete event-batch coverage remains unresolved rather than becoming a zero-event claim;
- PR #1590 established RDP5-C on main `19cc65f9b5dbcbf8ee05ba57368145c3f12f6722`; live-discovered PIT fix PR #1594 merged as main `b2d687e903f9b2fa3eaa66f8e6abf6d51db5747d`;
- exact-head focused acceptance: RDP5-C `36411477120` PASS (61 tests + Ruff + mypy + py_compile), RDP5 Dynamics `36411477020` PASS, RDP4 Rich Market Tape `36411477034` PASS, RDP4 Order Flow dependencies `36411477037` PASS;
- final read-only UID504 exact-main diagnostic #1596 run `36411983878` PASS: stable collector, heartbeat/connection age 6082ms, transport age 0ms, 116 liquidation rows, 69 provider coverage rows, every coverage row backed by a non-empty Bybit provider event batch; BTC/ETH preserved no-coverage backward compatibility and SOL with real event+coverage remained fail-closed `coverage_present_unresolved`, direction `None`.

Goal:
- make M4 continuously fresh.

Work:
- repair live derivatives source;
- mark/index/OI/funding/basis;
- dynamics;
- crowding;
- liquidation public-feed collection;
- liquidation coverage ledger;
- exact observed liquidation evidence.

PASS:
- derivatives inside freshness budget;
- liquidation feed has explicit connected coverage;
- stale or missing provider event coverage fails closed;
- no fabricated zero-liquidation or future-liquidation-risk claim.

## RDP6 — Options / volatility intelligence

Status: **PASS**

Progress:
- immutable BTC/ETH options contracts, Bybit source lineage/PIT store, options-volatility evidence and existing Derivatives-family wiring accepted;
- canonical live options collection/runtime merged through main `b88121a8ab897c9b63a74107790af1f1eddcc427`;
- exact-main diagnostic PR #1606 remained unmerged; UID504 run `36419310127` PASS with fresh BTC/ETH surfaces + source coverage, no unsupported dealer-gamma/max-pain claim, no new score family/direction, `REAL_CAPITAL=0`.

Goal:
- add the most important missing BTC/ETH derivatives context.

Work:
- accepted options provider contract;
- IV / term structure;
- skew;
- expiry/strike OI;
- volume;
- volatility index where available;
- expiry concentration;
- exact PIT-safe freezes;
- enrich the existing Derivatives family only.

PASS:
- data-source semantics documented;
- no unsupported dealer-gamma/max-pain claim;
- evidence enriches Derivatives without creating a new score family.

## RDP7 — Real On-chain / capital-flow rail

Status: **PASS**

Progress:
- RDP7-A/A1 accepted canonical source coverage plus append-only On-chain capital-flow PIT storage and removed circular stablecoin lineage;
- RDP7-C/C3 accepted real public DefiLlama USDT/USDC stablecoin-supply truth and supervisor-owned 300s collection; canonical float-token boundary fix merged as `3fda58d6b30f5b671cd7797f6529e33b0a2e72bb`;
- exchange-flow entitlement is `UNAVAILABLE_EXPLICIT` because no accepted Glassnode/CryptoQuant credential exists; large-transfer and wallet-cohort rails remain explicit unavailable because defensible transfer/cluster identity + coverage is absent. No whale/institution identity is fabricated;
- RDP7-F PR #1619 merged as main `0c23165e831d9aa8b8d41050354dfd45abc995d7`; UID504 run `36431658023` PASS. Accepted fresh stablecoin context now projects into the existing `ConfluenceFamily.ONCHAIN` only, with `direction=None` and exact RDP10-resolvable source/freeze lineage;
- RDP7-G diagnostic PR #1620 remained unmerged. Exact-main UID504 run `36433299821`, rerun job `108966224227`, PASS after canonical R11 recovery issue #1621: Workbench/Development exact main, real DefiLlama snapshot, raw → envelope → coverage → normalized observation → PIT freeze/analysis → BTC/ETH/SOL ONCHAIN family identity resolution, stale/gap/PIT fail-closed regressions, supervisor alive, `RDP10_EXACT_PROOF_LINEAGE=RESOLVABLE`, `REAL_CAPITAL=0`.

Goal:
- remove `ONCHAIN_STANDALONE=DEFERRED_SOURCE` only when justified.

Work:
- accepted provider/source;
- exchange flows;
- large transfers;
- wallet-cohort admission/forward measurement;
- stablecoin capital-flow context;
- provider attribution/version;
- source coverage.

PASS:
- real forward observations exist;
- no synthetic whale/institution claims;
- On-chain can be OBSERVED only from accepted fresh provider evidence.

If no acceptable provider is available, On-chain remains explicitly unavailable and the project does not fabricate a replacement.

## RDP8 — Event Risk + cross-market runtime

Status: **PASS**

Progress:
- RDP8-A canonical Event Source scheduler merged as `34eb9c55614afa3e822f760c91ebf0a8caca076c`; 900s supervisor clock, single-writer lock, FRED CPI + Employment fallback and Fed RSS accepted while BLS HTTP 403 remains explicit fail-closed;
- exact-main RDP8-A UID504 run `36439676631` PASS with fresh official/accepted event truth and no stale Event Risk masquerading as current;
- RDP8-B official VIX/Treasury runtime merged as `b343e3bf20677df2caa4d4de5d7a47ee3e1ff01c`; exact raw response → source envelope → coverage → normalized observation lineage persists in append-only PIT storage and the canonical supervisor owns an hourly single-writer snapshot clock;
- focused UID504 run `36440855017` PASS proved real Cboe redirect + U.S. Treasury source lineage without production mutation;
- final diagnostic PR #1630 remained unmerged. Exact-main UID504 run `36442983256`, job `108997967133`, PASS: exact Workbench/Development main, R11 restart, successful canonical cross-market cycle, live VIX/Treasury lineage, score-external cross-market freeze, stale Event Risk → circuit-breaker `DEGRADED_DATA`, `STALE_EVENT_TREATED_AS_FRESH_VETO=NO`, focused regressions and `REAL_CAPITAL=0`.

Goal:
- make score-external risk/context continuously trustworthy.

Work:
- fresh event-source scheduler;
- BLS failure handling / alternate official route where appropriate;
- Fed/FRED health;
- VIX/Treasury cross-market refresh;
- optional USD-regime source;
- news/event freshness and circuit-breaker behavior.

PASS:
- process state measured;
- online state asserted only when proven;
- stale event data cannot gate a trade as if fresh.

## RDP9 — Cross-venue quality + evidence-overlap engine

Status: **PASS**

Closure evidence:
- RDP9-A PR #1633 / main `4763bb27ad432a761e3abcee4aceb75e588cb6eb` established score-external venue-local/broad quality classification.
- RDP9-B PR #1634 / main `2fcbefabec0360a58424a177048828d49d16c7d7` bound exact family dependency/raw-evidence overlap into immutable decision lineage.
- RDP9-C PR #1635 / main `371bc013337e2e304fac465c4ab284d37539efc9` made material venue disagreement visible to the unified decision layer without adding score or directional authority.
- UID504 overlap acceptance `36447590945` / job `109013794664`: `DUPLICATE_EVIDENCE_WEIGHT_INFLATION=BLOCKED`, `OVERLAP_LINEAGE_IN_DECISION_PROOF=YES`.
- UID504 decision acceptance `36447590574` / job `109013790085`: `MATERIAL_VENUE_DISAGREEMENT_VISIBLE=YES`, score authority NO, directional authority NO.
- Exact-current-main bootstrap `36451104263` / job `109025778311` on `e8fd12f2b3e56f2feb2050d938b4ef0883accfb5`: focused RDP9 acceptance PASS, provider-divergence DB quick-check OK, live BTC/ETH/SOL read-only classification PASS.
- Workbench bootstrap `36451104302` / job `109025778585`: canonical Workbench `repo/main` exact `e8fd12f2b3e56f2feb2050d938b4ef0883accfb5`, dirty count 0.
- Both RDP9 PASS conditions are therefore mechanically satisfied. The live observation was broad confirmation; no live venue conflict was fabricated.
- `REAL_CAPITAL=0`.

Goal:
- stop local anomalies and duplicate evidence from masquerading as broad confirmation.

Work:
- provider-divergence expansion;
- venue-local/broad classification;
- family dependency lineage;
- overlap detection;
- confluence integration without weight inflation.

PASS:
- same raw truth cannot silently create duplicate confidence;
- material venue disagreement is visible to the decision layer.

## RDP10 — Exact frozen customer-proof contract

Status: **PASS**

Closure:
- RDP10 exact frozen customer-proof contract is mechanically accepted before the active RDP11 soak.
- Geometry, Liquidity, Order Flow, Derivatives, On-chain and Event Risk/context retain exact/fail-closed proof semantics; hashes remain provenance metadata rather than the customer-facing proof itself.
- Durable closure evidence is recorded in `docs/agent/CURRENT_FRONTIER.md` and `docs/agent/HANDOFF_LOG.md`.
- `REAL_CAPITAL=0`.

Goal:
- finish the backend contract required by the later frontend.

Every family must return, when available:

- human-readable state;
- exact frozen measurements;
- exact source objects;
- visualization-ready series/levels;
- source time;
- as-of time;
- freshness;
- uncertainty;
- source/provider label;
- explicit unavailable/stale state.

Hashes remain internal provenance/debug metadata and are not required customer UI.

PASS:
- Geometry, Liquidity, Order Flow, Derivatives and On-chain each expose the strongest exact proof actually available;
- Event Risk/context exposes exact source records;
- historical proof never reads current live data.

## RDP11 — Continuous soak + final Evidence PASS

Status: **ACTIVE — PRIOR EPOCH INVALIDATED / R2 RE-ANCHOR PENDING**

Current checkpoint:
- observer/anchor PR #1666 originally created epoch `rdp11-3d9f33db-20260929` against frozen runtime target `3d9f33db3f1189571d40566125fbeabd00c04930`;
- that epoch is now **INVALIDATED** and remains immutable historical sidecar evidence;
- first mechanical invalidation proof: scheduled observer run `36622461578` / job `109591020809`;
- failure surface: observer `GET /api/intelligence-center` after the workflow latency probes had returned HTTP 200;
- failure: `ConnectionResetError:[Errno 54] Connection reset by peer`;
- subsequent observations correctly fail closed with `soak epoch is already invalidated`;
- the old soak start `2026-09-29T09:13:21.134000Z` and old `2026-10-02T09:13:21.134000Z` eligibility timestamp can no longer close RDP11;
- frozen Product/Development target remains unchanged at `3d9f33db3f1189571d40566125fbeabd00c04930`;
- replacement epoch candidate: `rdp11-3d9f33db-20260930-r2`;
- replacement state: **PENDING_MERGED_MAIN_ANCHOR**;
- new start/72h eligibility: **NOT ASSERTED until a successful merged-main non-dry-run observation creates the fresh immutable anchor**;
- old epoch deletion/rewrite/backfill: FORBIDDEN;
- observer semantics/thresholds are not weakened for the restart;
- `RDP11_SOAK_SIDE_CAR_ONLY=YES`;
- `RDP11_CANONICAL_RUNTIME_MUTATED=NO`;
- `HISTORICAL_BACKFILL=NO`;
- `REAL_CAPITAL=0`.

Goal:
- prove the system survives real time, not only tests.

Minimum engineering soak:
- 72 hours of UID504 observation before final closure.

Monitor:
- uptime;
- freshness;
- source gaps;
- reconnections;
- database locks;
- sequence/gap behavior;
- service restarts;
- frozen-proof integrity;
- no-future violations;
- Stream/Product continuity.

PASS:
- all mandatory rails meet their accepted SLO or fail closed;
- unresolved source limitations are explicitly documented;
- rich engines consume only accepted source truth;
- real Product proof is inspectable;
- REAL_CAPITAL=0.

Only after **RDP11 PASS** may Evidence Data Plane V1 be marked complete.

## 9. Portfolio gate

Paper Capital / Portfolio implementation follows this program.

Portfolio may be designed in parallel, but full integration must not treat an evidence rail as trustworthy until its RDP acceptance gate is passed.

Required sequence:

```text
Reality-Backed Evidence Data Plane PASS
        ↓
Paper Capital / Portfolio
        ↓
New Command Center frontend
```

The later Portfolio must be able to freeze, for every paper trade, the exact accepted evidence bundle that existed when the capital decision was made.

## 10. Priority classification

### P0 — mandatory for Evidence PASS

- collector/runtime reliability;
- Geometry candle truth;
- rich Liquidity;
- rich Order Flow;
- fresh Derivatives;
- real liquidation coverage or explicit unsupported state;
- Event Risk runtime health;
- exact frozen proof contract;
- overlap/double-counting protection;
- cross-venue/data-quality context.

### P0 provider-dependent

- real On-chain exchange/capital flows;
- BTC/ETH Options intelligence.

These are architecturally required targets, but may remain explicit unavailable until a legally/technically acceptable source is active. No fake substitute is allowed.

### P1

- stablecoin capital-flow enrichment;
- broader macro/FX regime context;
- additional derivatives venues;
- richer options surface.

### P2 / research-only unless separately accepted

- ETF flow context;
- sentiment/attention as directional evidence;
- social-media scores;
- inferred dealer gamma without defensible source;
- "smart money" identity labels;
- predictive liquidation maps built from estimates only.

## 11. Non-negotiable scientific boundaries

Never claim:

- 80 points = 80% win probability;
- achieved 80%+ accuracy without forward evidence;
- market-maker/institution intent from order-book patterns;
- spoofing as proven manipulation;
- absorption as proven hidden actor;
- large transfer = impending buy/sell;
- stablecoin mint = bullish;
- funding extreme = next move;
- option OI/max-pain = deterministic target;
- observed liquidation map = future liquidation map;
- cross-venue agreement = guaranteed outcome;
- LLM narration = market evidence.

## 12. New-agent handoff

Every new agent working on this program must read, in order:

1. `/Volumes/Crypto-504/Crypto-Signal-Workbench/WORKSPACE_READ_FIRST.md`
2. `00_CONTEXT/READ_FIRST_CRYPTO_SIGNAL.md`
3. `00_CONTEXT/CURRENT_STATUS.md`
4. `00_CONTEXT/PROJECT_CHRONICLE.md`
5. `01_EVIDENCE_DEPTH/ACTIVE_ROADMAP.md`
6. `00_CONTEXT/EVIDENCE_DEPTH_FRONTIER.md`

Current exact frontier:

**RDP11 — Continuous soak + final Evidence PASS**

The observer is anchored and scheduled. RDP11 remains ACTIVE until the real 72-hour minimum has elapsed without epoch invalidation and final Evidence PASS is mechanically verified.

Do not skip forward to Portfolio or frontend implementation while RDP1–RDP11 remain open unless the user explicitly authorizes parallel preparatory work.

## 13. Project isolation

Only Crypto Signal is in scope.

Do not modify:
- Durdurulmaz;
- Quantum Capital;
- their private volumes/data.

Shared host tooling may only be changed when explicitly authorized.

**REAL_CAPITAL=0**
