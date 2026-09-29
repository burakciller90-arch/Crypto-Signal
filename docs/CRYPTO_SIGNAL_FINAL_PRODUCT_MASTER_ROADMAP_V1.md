# Crypto Signal — Final Product Master Roadmap V1

Status: **CANONICAL FINAL PRODUCT PROGRAM — ACTIVE**
Date opened: 2026-09-29
Company: GALACTECH
Product: Crypto Signal
Repository: `burakciller90-arch/Crypto-Signal`
Safety: **REAL_CAPITAL=0**
Canonical workbench: `/Volumes/Crypto-504/Crypto-Signal-Workbench`

Current mechanically active gate:

**FP0 / RDP11 — Continuous soak + final Evidence PASS**

The final product program is open. The active RDP11 soak blocks mutation/cutover of the soaked runtime and blocks final Evidence PASS, but it does **not** require engineering to sit idle: later Paper Capital and Product/UI slices may be developed and tested in isolated branches/worktrees with fixtures, temporary databases and read-only canonical inputs as long as they cannot mutate the soaked Product/Development target, observer contract or frozen/historical evidence.

---

## 0. Why this roadmap exists

Crypto Signal already contains a large accepted backend, paper-capital and frontend history. The final product must therefore **integrate and productize accepted truth**, not rebuild the project from zero.

This roadmap is the canonical bridge from the accepted Evidence Data Plane + Intelligence Stream + paper-capital infrastructure to the final customer product.

The final product has two equally important spines:

1. **Command Center / Intelligence UX**
   - the user understands the market in roughly ten seconds;
   - the default surface gives the answer first, then action, reason and proof;
   - the user can progressively drill from market state → setup → family evidence → raw/frozen evidence;
   - technical plumbing, hashes, internal enum names and backend table vocabulary remain hidden from normal customer UX.

2. **Paper Capital Autopilot / Trust UX**
   - the system demonstrates what its own decisions would have done to virtual capital;
   - history is immutable and append-only;
   - losses, abstention, cash and failed fills remain visible;
   - execution is conservative and cost-aware;
   - every capital mutation is traceable to the exact decision and exact frozen evidence that existed at the time.

The final product story is:

```text
MARKET TRUTH
   ↓
SYSTEM VIEW
   ↓
DECISION / ABSTENTION
   ↓
PAPER CAPITAL DECISION
   ↓
SIMULATED EXECUTION
   ↓
OUTCOME
   ↓
IMMUTABLE ARCHIVE
   ↓
CUSTOMER-INSPECTABLE PROOF
```

---

## 1. Authority and supersession

### 1.1 Current execution authority

This document is the **final product umbrella roadmap**.

While RDP11 is active:
- `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md` remains the mechanical authority for the RDP11 PASS gate;
- this roadmap's FP0 mirrors that gate;
- no product implementation may mutate the frozen Product/Development soak target, RDP11 observer contract, historical evidence, or canonical runtime merely to advance a later product phase.

After RDP11 PASS, this roadmap becomes the primary execution sequence for Paper Capital + final frontend/product completion.

### 1.2 Historical frontend documents

The following remain valuable acceptance/discovery history, but are not the new product-architecture authority:
- `docs/CRYPTO_SIGNAL_FRONTEND_MASTER_ROADMAP_V1.md`;
- `docs/CRYPTO_SIGNAL_FRONTEND_M1_CAPABILITY_GAP_LEDGER.md`;
- historical `docs/GALACTECH_*.md`;
- older Mission Control / Gift Edition product acceptance records.

Their accepted backend facts and reusable components remain valid unless contradicted by newer mechanical evidence.

### 1.3 Intelligence Stream authority

Intelligence Stream V1 S0-S16, F0-F10 and Message Intelligence MI1-MI6 remain **accepted**.

Do not rebuild:
- canonical Stream ledger;
- story/change engine;
- analytical composer;
- deterministic narrative/fact locks;
- SSE/history/reconnect;
- Stream search/filter/deep-link;
- notification chime foundation;
- five-family system-view rows;
- exact family proof interaction;
- accepted browser/visual-audit infrastructure.

The new Command Center **contains and reuses** the accepted Intelligence Stream. It does not replace the Stream truth model with a second competing message system.

---

## 2. Final product constitution

### 2.1 The four permanent UX rules

Every customer surface follows:

1. **Answer first** — What is happening?
2. **Action/state second** — What is the system doing or waiting for?
3. **Reason third** — Why?
4. **Proof fourth** — Show the exact evidence.

### 2.2 Progressive disclosure

The normal customer must never need to understand backend implementation vocabulary.

Normal UX must not expose:
- SHA256 identities;
- `READY_EXACT`;
- `IDENTITY_ONLY_EXACT`;
- `UNAVAILABLE_EXPLICIT`;
- raw database/table names;
- internal workflow/runtime vocabulary;
- `REAL_CAPITAL=0` as a normal decorative UI label.

Those values remain available to admin/debug/audit tooling.

Customer wording is human:
- Doğrulanmış veri;
- Veri eksik;
- Güncel değil;
- Karışık;
- Destekliyor;
- Çelişiyor;
- Tetik bekleniyor;
- İşlem yapılmadı;
- Fill kanıtlanamadı.

### 2.3 Truth is never hidden

- Confluence/support score is not probability.
- Missing evidence is not zero evidence.
- No-data is not neutral.
- A losing trade is never deleted.
- A historical chart is never rebuilt from current data.
- A later model version never rewrites an old trade.
- A current live chart is never shown as an issuance-time chart.
- Paper performance is never presented as real-money performance.
- Cash is a valid portfolio decision.
- No setup is a valid system state.
- REAL_CAPITAL stays 0.

### 2.4 Default interaction model

Default:
- one calm Command Center;
- inline expandable cards;
- one large context/workspace panel;
- progressive drill-down.

Floating/detached windows:
- optional **PRO WORKSPACE** feature only;
- never the default interaction model;
- must not recreate multi-window workstation chaos.

---

## 3. Locked first-screen hierarchy

Target desktop acceptance viewport: **1440×900**.

The first screen order is locked as:

1. global top bar;
2. **PİYASA ŞİMDİ / PİYASA NABZI**;
3. **SANAL PORTFÖY**;
4. **DİKKAT GEREKTİREN DURUMLAR**;
5. **INTELLIGENCE STREAM**;
6. persistent compact Event Rail when space permits.

The customer should answer within roughly ten seconds:
- What is the market doing?
- What matters now?
- Does the system see a setup?
- What did virtual capital do?
- What is the main risk?

The first screen is not a data dump.

---

## 4. Final navigation model

Primary product destinations are intentionally limited.

### 4.1 Command Center
Default home and primary daily workspace.

### 4.2 Markets / Asset Intelligence
Screener + asset intelligence when the user explicitly wants broader market discovery.

### 4.3 Events
Economic/event calendar and event-risk drill-down.

### 4.4 Portfolio
Paper Capital Autopilot, accounting, performance and Trade Passports.

### 4.5 History
Signals, decisions, paper trades and immutable proof archive.

The accepted Intelligence Stream remains embedded as a first-class Command Center module rather than becoming a redundant separate universe.

Global search / command palette may jump directly into any exact asset, event, signal, trade or proof context.

---

## 5. Mechanical repository baseline — duplicate-work map

This section is mandatory reading before every implementation slice.

| Capability | Current truth | Final-roadmap treatment |
|---|---|---|
| RDP0-RDP10 Evidence Data Plane | PASS | REUSE; do not reopen |
| RDP11 72h soak | ACTIVE | FP0 blocker |
| Intelligence Stream S0-S16 | PASS | REUSE |
| Stream F0-F10 deficiency closure | PASS | REUSE |
| Message Intelligence MI1-MI6 | PASS | REUSE |
| five-family 20/25/25/15/15 model | PASS | REUSE; not probability |
| RDP10 exact family proof | PASS | REUSE source truth |
| frozen Geometry visual proof | ACCEPTED | REUSE |
| Liquidity/Flow/Derivatives/On-chain customer visuals | exact data exists to varying depth; final visual UX incomplete | BUILD deterministic visual projections only |
| R21 Epoch 2 accounting | ACCEPTED | REUSE; never rewrite |
| R22 Transaction & Decision Tape | ACCEPTED | REUSE |
| R24 Performance & Trust engine | ACCEPTED | REUSE |
| Smart Capital Allocator | ACCEPTED foundation | EXTEND versioned policy; do not rewrite history |
| fixed-fractional paper sizing | ACCEPTED | REUSE default |
| Kelly | research/calibration gated | KEEP OFF until accepted calibration |
| S11 three-vault Capital Story lifecycle | PASS in accepted implementation/fixtures | REUSE |
| natural post-activation Capital production proof | insufficient/deferred in later F5/F10 closeout | CLOSE FORWARD-LIVENESS GAP |
| current paper execution v1 | deterministic full fill; fee/spread/slippage | EXTEND |
| partial fills | explicitly unsupported | BUILD V2 or show FILL NOT PROVEN |
| queue/limit-fill realism | not accepted | BUILD fail-closed |
| order-book depth impact | source truth exists; paper execution does not fully consume it | BUILD |
| latency/funding-aware execution | not fully accepted | BUILD where instrument requires |
| GALACTECH Command Center | historical accepted surface | REUSE patterns/read models, REDESIGN UX |
| GALACTECH Markets | historical accepted provider/frozen PA workspace | REUSE adapters; extend family visuals |
| GALACTECH Capital Center | historical accepted read-only Epoch 2 UI | REUSE accounting projection |
| GALACTECH Archive | historical accepted Proof Wall | REUSE |
| GALACTECH Performance | historical accepted trust UI | REUSE |
| Stream search/filter/history | PASS | REUSE |
| global command search across assets/events/trades | not final | BUILD |
| alerts/outbox foundation | ACCEPTED | EXTEND semantic rules |
| watchlist | no final accepted product contract | BUILD |
| Event Source / Event Risk | RDP8 PASS | REUSE; build customer Event Center |
| shared Chromium visual audit | ACCEPTED | REUSE; do not create second screenshot stack |
| Trade Passport backend lineage | R21/R22/RDP10 facts exist | BUILD read model + UX |
| Strategy Vault comparison | not final accepted product | BUILD later, isolated |

### 5.1 Mandatory duplicate guard

Before every phase:
1. inspect current main;
2. search merged PRs/branches/workflows for that exact slice;
3. inspect current implementation, not just doc titles;
4. classify each requirement as `REUSE / EXTEND / BUILD / EXPLICITLY_UNAVAILABLE`;
5. write the classification into CURRENT_FRONTIER before coding.

A feature is not rebuilt merely because an old UI is no longer the final design.

---

# 6. Execution program

## FP0 — RDP11 Evidence Soak Guard

Status: **ACTIVE / WAITING ON REAL TIME**

Frozen runtime subject:
`3d9f33db3f1189571d40566125fbeabd00c04930`

Soak start:
`2026-09-29T09:13:21.134000Z`

Earliest 72h eligibility:
`2026-10-02T09:13:21.134000Z`

PASS requires the RDP11 roadmap's real accumulated evidence, not elapsed time alone:
- non-invalidated immutable anchor;
- mandatory source freshness or explicit fail-closed state;
- gap/reconnect behavior;
- DB/read health;
- frozen-proof integrity;
- no-future integrity;
- Product/Stream continuity;
- explicit unresolved source limitations;
- REAL_CAPITAL=0.

### During FP0

Allowed:
- documentation and read-only audits;
- isolated FP1+ implementation branches/worktrees;
- unit/contract/browser development against deterministic fixtures;
- temporary/copy-on-write paper databases;
- read-only canonical evidence inputs;
- new Product/UI preview code that is not deployed into the soaked Product/Development target;
- parallel Paper Capital and frontend work when file/schema ownership is disjoint.

Required isolation:
- no FP1+ branch may alter the active soak anchor, observer contract or frozen runtime subject;
- no acceptance may relabel fixture success as final forward/live acceptance;
- merge to main is allowed only when the change cannot alter the active soaked runtime behavior, otherwise hold the merge/deploy until the soak boundary is deliberately closed/restarted;
- final integrated Product deployment/cutover waits for FP0 PASS.

Forbidden:
- changing soaked Product/Development target;
- changing observer contract and pretending the same epoch remains valid;
- historical/frozen backfill;
- deploying a new Product runtime into the active epoch;
- claiming RDP11 PASS early.

FP0 PASS unlocks **final integrated runtime acceptance/cutover**. FP1+ engineering may proceed in parallel during the soak under the isolation rules above.

---

## FP1 — Final Product Contract & Human Read-Model Layer

Goal:
create one frontend-safe product contract over already accepted evidence/capital truth.

Do **not** create a second evidence engine.

Build/extend read models for:
- Market Pulse;
- Attention situations;
- signal/workspace summary;
- five-family customer summaries;
- Event Rail;
- portfolio summary;
- daily capital movements;
- Trade Passport;
- screener rows;
- global search index.

Every customer payload must preserve exact identity internally while exposing human fields by default.

Required customer fields where relevant:
- state;
- plain-language explanation;
- source/provider label;
- source time;
- as-of time;
- freshness;
- uncertainty;
- trigger/invalidation/targets;
- family support/contradiction;
- proof availability;
- capital consequence;
- execution/outcome status.

PASS:
- normal API/UI can operate without rendering hashes/internal enums;
- audit/debug route still retains exact identity/provenance;
- every displayed numeric value has canonical source lineage;
- no source truth is duplicated into a divergent second database merely for UI convenience.

---

## FP2 — Paper Vault V3 Constitution

Goal:
introduce the final Paper Capital product model **without rewriting Epoch 1 or Epoch 2**.

Historical programs remain immutable:
- Epoch 1: 100 USDT legacy history;
- Epoch 2: 1,000 USDT / 600-300-100 accepted historical/current contract.

The final product adds a new versioned **Paper Vault** abstraction.

A Paper Vault freezes:
- vault identity;
- creation timestamp;
- starting virtual capital;
- policy version;
- permitted instruments;
- fee/execution policy;
- risk policy;
- allocation policy;
- evidence-policy versions.

Default final-product starting capital may be 10,000 USDT, but the amount is part of the immutable vault constitution rather than a global truth.

### No reset

There is no destructive reset.

A user may:
- create a NEW PAPER VAULT;
- archive/stop a vault;
- compare vaults.

A user may not:
- erase losing history;
- reset equity to hide drawdown;
- retrofit a new policy into an old trade.

### Dynamic books

Core / Tactical / Opportunity remain useful policy sleeves, but **60/30/10 is not universal law**.

The new allocation policy may dynamically assign:
- Core;
- Tactical;
- Opportunity;
- Cash.

100% cash is valid.

PASS:
- Epoch 1/2 bytes/history remain unchanged;
- new vault history is append-only;
- allocation policy is versioned and replayable;
- no forced minimum market exposure;
- no cross-vault borrowing unless a future separately accepted contract explicitly introduces it;
- REAL_CAPITAL=0.

---

## FP3 — Canonical Paper Capital Autopilot Forward Runtime

Goal:
make the already accepted S11/R21/R22 machinery operate as one canonical forward virtual-capital runtime.

Reuse:
- Smart Capital Allocator;
- fixed-fractional sizing;
- S11 lifecycle;
- R21 accounting;
- R22 intent/fill/bundle;
- Decision Proof lineage;
- existing capital Stream projectors.

The runtime must support, when exact policy permits:
- HOLD_CASH;
- OPEN;
- SCALE_IN;
- REDUCE;
- STOP_UPDATE;
- PARTIAL_TAKE_PROFIT;
- TAKE_PROFIT;
- STOP;
- CLOSE.

Each event is append-only.

Every event freezes:
- decision/proof identity;
- market/evidence snapshot;
- action;
- quantity/notional;
- execution policy;
- costs;
- before/after accounting;
- reason;
- event time.

Natural forward liveness is mandatory.

PASS:
- at least one genuine post-activation forward candidate is processed without fixture fabrication;
- all three sleeves can independently HOLD/BLOCK/ELIGIBLE under their exact rules;
- canonical action lineage reaches R22/R21 when a genuine eligible action occurs;
- restart/replay is idempotent;
- no discretionary “fear veto” is added after all preregistered gates pass;
- no gate is weakened merely to generate trades.

---

## FP4 — Paper Execution Realism V2

Goal:
make virtual performance deliberately conservative.

### Existing truth to retain
- fee;
- spread;
- slippage;
- venue rule snapshot;
- deterministic adverse fill.

### Add

For supported instruments:
- exact contemporaneous order-book depth;
- notional-dependent VWAP/impact;
- configurable latency;
- queue/limit-order uncertainty;
- partial-fill state;
- timeout/cancel state;
- fill-not-proven state;
- funding for perpetual simulation;
- instrument-specific fee schedule;
- exchange precision/min-notional rules.

Rules:
- candle wick touch is not sufficient proof of a limit fill;
- uncertain queue position may produce `FILL NOT PROVEN`;
- missing book depth cannot be replaced with an optimistic fill;
- partial-fill support is versioned and explicit;
- execution assumptions are frozen per event.

PASS:
- full, partial, not-filled and not-proven outcomes are deterministic/replayable;
- simulated average fill reconciles exactly to consumed depth when depth-based mode is used;
- costs are not double-counted;
- future book state cannot enter historical execution;
- pessimistic/fail-closed behavior is preferred over optimistic invention.

---

## FP5 — Capital Allocator V2 / Portfolio Risk

Goal:
size capital from evidence **and portfolio risk**, not score alone.

Inputs:
- accepted evidence/decision state;
- conflict;
- volatility;
- liquidity;
- event risk;
- current drawdown;
- current cash;
- existing exposure;
- asset/market correlation clusters;
- transaction cost;
- stop/invalidation distance.

### Default sizing

Use fixed-fractional/risk-budgeted sizing first.

Confluence 80 is never converted into 80% win probability.

### Kelly

Kelly remains disabled until:
- sufficient untouched-forward outcomes exist;
- an accepted calibrated probability contract exists;
- probability calibration is current for the policy/version/regime;
- transaction-cost assumptions are included.

If later enabled:
- use fractional Kelly only;
- hard portfolio risk caps still dominate;
- no automatic leverage escalation.

### Correlation / cluster risk

Examples:
- BTC/ETH/SOL long exposure may represent one crypto-beta cluster;
- a new AVAX long cannot be treated as independent merely because the symbol differs.

PASS:
- cluster exposure is explicit;
- drawdown/event/liquidity/conflict gates fail closed;
- cash remains valid;
- allocator can deploy capital when evidence is eligible without forced under-use;
- allocator can hold 100% cash without being marked failed.

---

## FP6 — Trade Passport & Immutable Capital Archive

Goal:
turn R21/R22/RDP10 lineage into a customer-readable permanent trade record.

A Trade Passport contains:

### Identity
- asset;
- side/action;
- vault/policy;
- opened/closed timestamps;
- size/notional;
- result.

### “What did the system see?”
- frozen Market Story Chart;
- exact five-family states;
- source/provider/time;
- Event Risk;
- exact trigger/invalidation/targets.

### Execution
- signal/reference price;
- simulated average fill;
- fill status;
- fee;
- spread;
- slippage;
- funding where applicable;
- latency/partial-fill/queue status.

### Lifecycle
Append-only timeline:
- OPEN;
- SCALE_IN;
- STOP_UPDATE;
- PARTIAL_TAKE_PROFIT;
- REDUCE;
- CLOSE;
- CORRECTION/SUPERSEDED when required.

No event is deleted.

PASS:
- passport can be reconstructed solely from accepted immutable records;
- every lifecycle event opens the exact proof that existed then;
- a losing trade is as inspectable as a winning trade;
- later model versions cannot alter historical passport content.

---

## FP7 — Performance & Trust Read Model V2

Reuse R24; do not invent a new “trust score.”

Expose:
- starting capital;
- current equity/NAV;
- total return;
- realized PnL;
- unrealized PnL;
- max drawdown;
- trade count;
- wins/losses/breakeven;
- expectancy;
- profit factor when defined;
- fees;
- spread cost;
- slippage cost;
- funding cost where applicable;
- turnover;
- time in cash;
- time invested;
- per-vault/policy comparison;
- benchmark comparison.

Always show:
- growth;
- risk taken to achieve growth.

No single “SYSTEM TRUST 98/100” marketing score.

PASS:
- all metrics reconcile to immutable tape/accounting;
- empty samples remain NOT YET MEASURED;
- undefined metrics remain undefined;
- performance cohorts preserve evidence/policy/version boundaries;
- no backtest/walk-forward/live-forward mixing.

---

## FP8 — Command Center V3: 10-Second Surface

Goal:
build the final first screen.

### Top bar
Customer-facing:
- GALACTECH · CRYPTO SIGNAL;
- compact live/freshness state;
- global command search;
- notifications;
- sound;
- settings.

No hashes/internal runtime labels.

### PİYASA ŞİMDİ
At-a-glance:
- general regime;
- BTC/ETH/SOL or chosen watch universe;
- volatility;
- market risk;
- next critical event.

### SANAL PORTFÖY
At-a-glance:
- current equity;
- starting capital;
- all-time result;
- today;
- open positions;
- used capital;
- cash;
- max drawdown;
- mini equity curve.

### DİKKAT GEREKTİREN DURUMLAR
Only top 3–5 material situations.

Each card:
- asset/timeframe;
- scenario state;
- current/reference price;
- directional support (not probability);
- evidence coverage;
- trigger;
- invalidation;
- targets;
- one-line why-now;
- main risk;
- five family compact state;
- capital eligibility/execution state if available.

### Intelligence Stream
Reuse accepted Stream.
Only material changes remain in the primary customer surface.

PASS:
- 1440×900 captures top hierarchy without scrolling to understand core state;
- a first-time user can identify market state, important setup, portfolio state and primary risk in a timed usability test;
- no backend vocabulary leak;
- Stream history/search/sound remain intact.

---

## FP9 — Signal / Asset Intelligence Workspace + Market Story Chart

Goal:
one click from an attention card opens deeper intelligence without losing context.

Top summary:
- What do we expect?
- What invalidates it?
- Where are targets?
- What should happen next?
- Is trigger still pending?
- What did Paper Capital do?

### Market Story Chart

Not a blank candlestick chart.

Render only exact supported marks:
- trigger/entry;
- invalidation;
- targets;
- support/resistance;
- swing highs/lows;
- structure break;
- liquidity sweep;
- imbalance;
- methodology annotations;
- relevant event times.

Required mode switch:
- **CANLI GRAFİK**
- **SİNYAL ANINDAKİ GRAFİK**

Signal-time mode is immutable and cannot read current market data.

PASS:
- every historical annotation resolves to frozen coordinates/provenance;
- unsupported annotation remains absent/explicit rather than estimated;
- live and frozen modes can never be confused visually.

---

## FP10 — Five Family Visual Intelligence Workspaces

Goal:
turn RDP10 exact proof into human visual proof.

### Geometry
Reuse accepted frozen chart and extend only where exact:
- Price Action;
- Elliott;
- Harmonic;
- structure/levels/PRZ.

### Liquidity
Render, where exact:
- depth;
- bid/ask;
- spread;
- imbalance;
- depth change;
- sweep;
- replenishment/depletion;
- observed liquidity vs inferred candidate clearly separated.

### Order Flow
Render, where exact:
- taker buy/sell;
- delta;
- local CVD;
- trade tape;
- book pressure;
- absorption candidate;
- divergence.

### Derivatives
Render, where exact:
- OI;
- funding;
- basis;
- crowding;
- observed liquidation feed;
- options IV/term structure/skew/OI where accepted.

No predictive liquidation heatmap is shown as observed truth.

### On-chain
Show only accepted provider-backed evidence.
If only stablecoin context is accepted:
- show that exact context;
- keep exchange flows/wallet cohorts/large transfers explicitly unavailable.

### Universal family-card contract
Each family starts with:
**ŞU ANDA NE SÖYLÜYOR?**

Then:
- concise answer;
- exact visualization;
- source;
- data time;
- freshness;
- uncertainty.

PASS:
- no current-data substitution;
- no SHA required for normal customer comprehension;
- every visual mark traces internally to exact persisted evidence;
- missing evidence produces a useful explicit no-data state.

---

## FP11 — Markets / Coin Intelligence / Screener

Goal:
answer “Which assets currently deserve attention?”

### Markets table
Columns may include:
- price;
- 24h;
- trend/state;
- signal/setup state;
- directional support;
- evidence coverage;
- Liquidity;
- Order Flow;
- Derivatives;
- Event Risk;
- last material change.

Filters:
- strong setups;
- direction changed;
- liquidity anomaly;
- OI move;
- low event risk;
- watchlist only.

### Asset Intelligence
Search/selecting BTC/ETH/SOL/... opens:
- price/trend/momentum/volatility;
- market structure;
- five families;
- Event Risk;
- latest signals;
- historical system views;
- paper exposure if any.

PASS:
- table rows are server/read-model backed;
- no missing family is rendered as zero;
- screener sorting/filtering never changes underlying evidence;
- asset page can be opened by exact route/deep link.

---

## FP12 — Event Center + Event Rail

Goal:
the user should not need a separate economic-calendar site for supported events.

Event Rail:
- today/upcoming;
- countdown;
- importance;
- affected assets;
- current circuit-breaker state.

Event detail, where exact:
- previous;
- expectation;
- actual;
- source/provider;
- timestamp;
- affected assets;
- system interpretation;
- linked decisions/signals.

Historical reaction is shown only if a point-in-time reaction dataset is mechanically accepted. It is never invented from current candles.

PASS:
- Event Risk UI reads RDP8 truth;
- stale/missing event sources fail closed;
- countdown is derived from exact event time;
- event-block/caution behavior is linked to capital/decision state without claiming counterfactual avoided profit/loss.

---

## FP13 — Watchlist + Semantic Alerts + Global Command Search

### Watchlist

User can star assets/contexts.

Watchlist does not create a second market truth store.

It stores user preference only.

Material changes for watchlisted assets can raise Stream/notification attention.

### Semantic alerts

Extend existing alert/outbox foundation.

User rules may include:
- directional support crosses threshold;
- family state changes;
- liquidity sweep;
- abnormal OI change;
- setup becomes READY/ELIGIBLE;
- Event Risk transition;
- capital execution/outcome.

Alert eligibility must be based on canonical state transitions, not repeated polling spam.

### Global Command Search

`⌘K` / search opens:
- asset;
- current Asset Intelligence;
- latest signals;
- exact family view;
- past decisions;
- paper trades;
- events;
- proof/archive entries.

PASS:
- alert dedupe/replay safety;
- user preference does not mutate market evidence;
- search results preserve exact entity identity;
- stale results remain labelled stale;
- no notification fires again merely because history was reloaded.

---

## FP14 — Portfolio Center

Goal:
make Paper Capital the product's trust center.

Top:
- equity/NAV;
- all-time return;
- equity curve;
- starting capital;
- high-water mark;
- max drawdown;
- realized/unrealized PnL;
- active risk budget;
- current allocation.

### “Sistem şu anda parayı nerede tutuyor?”
Show:
- asset exposures;
- Core/Tactical/Opportunity sleeves;
- cash;
- risk clusters.

### “Sistem bugün ne yaptı?”
Timeline:
- OPEN;
- ADD;
- REDUCE;
- TAKE PROFIT;
- STOP;
- CLOSE;
- HOLD/BLOCK when materially important.

Each item opens Trade Passport.

### Strategy Vaults

A later sub-phase may create multiple immutable policy vaults:
- Balanced;
- Conservative;
- Tactical;
- other explicitly versioned policies.

Rules:
- identical starting conditions when comparison claims require them;
- no destructive reset;
- show return together with drawdown, turnover, fees and volatility;
- never rank one strategy solely by ending balance.

PASS:
- Portfolio reconciles exactly to canonical accounting;
- no performance cherry-picking;
- every transaction opens exact decision/execution proof;
- a new vault never rewrites another vault.

---

## FP15 — Unified History / Archive / Trust

Goal:
one immutable history plane with typed records, not one mixed misleading statistic.

History types:
- system views;
- decisions;
- signals;
- outcomes;
- paper trades;
- capital events;
- Event Risk transitions.

Filters:
- winner/loser;
- asset;
- long/short where instrument policy supports it;
- vault/policy;
- evidence class;
- date;
- outcome.

For every historical item:
- THEN = frozen issuance/action truth;
- NOW/OUTCOME = later appended truth.

Never rewrite THEN.

PASS:
- failed signals/trades remain visible;
- pagination/search preserves identity;
- frozen chart/evidence opens from historical context;
- Signal Archive and Trade Archive are related but not silently conflated.

---

## FP16 — UX, Accessibility, Responsive & Long-Session Acceptance

Reuse the accepted shared Chromium visual-audit stack.

Required deterministic captures:
- 1440×900 Command Center;
- exact mobile viewport;
- high-DPI/large desktop workspace;
- empty/no-evidence state;
- active setup;
- event-risk state;
- portfolio all-cash state;
- portfolio with open positions;
- losing Trade Passport;
- family visual workspaces;
- search/watchlist/alerts;
- 1k+ and 10k+ Stream/history state.

Acceptance:
- keyboard;
- focus return;
- screen reader semantics;
- reduced motion;
- zoom/font scaling;
- no whole-page horizontal overflow;
- no unreadable dense cards;
- no layout shift from live updates;
- reconnect/history load does not steal focus;
- long sessions stay responsive.

Detached PRO workspace is tested separately and is not required for beginner-first flow.

---

## FP17 — End-to-End Final Product Acceptance

The product is not accepted because the UI looks good.

One real forward narrative must be mechanically traceable:

```text
real accepted source evidence
→ family evidence
→ system view
→ attention card / signal context
→ exact Decision Proof
→ paper allocator decision
→ sizing
→ simulated execution or explicit no-fill/HOLD
→ immutable R22/R21 accounting
→ Stream capital event
→ Portfolio state
→ Trade Passport
→ later outcome
→ History / Performance
```

Required:
- no fabricated event;
- no synthetic “winning demo” counted as forward evidence;
- exact Product runtime;
- exact database lineage;
- browser acceptance;
- restart/replay acceptance;
- frozen proof integrity;
- capital accounting reconciliation;
- performance reconciliation;
- alert/search/history identity preservation;
- REAL_CAPITAL=0.

---

## FP18 — Controlled Product Cutover & Release Freeze

Only after FP0-FP17 PASS.

Steps:
1. final latest-main hosted gate;
2. UID504 exact Workbench sync;
3. exact Development fulltest;
4. rollback-safe Product preview;
5. full browser/visual acceptance;
6. exact Product deployment;
7. independent Product state/health;
8. final release manifest;
9. immutable tag/release record.

Rollback target remains explicit until final acceptance.

No real exchange order capability is part of this release.

---

# 7. Agent parallelization rules

Parallel work is allowed only when workspaces and authority boundaries are disjoint.

One agent/task = one branch/worktree.

During FP0, safe isolated parallel work is explicitly encouraged so the 72-hour soak is not idle time. Work that changes the soaked runtime behavior stays unmerged/undeployed until its effect on the epoch is resolved.

Safe examples during/after FP0:
- Paper execution realism adapter;
- family visual renderer;
- global search read model;
- Event Center;
- Watchlist preference store.

Unsafe parallelism:
- two agents editing the same canonical read model;
- two agents mutating paper ledger schema;
- UI work inventing fields before backend contract is frozen;
- runtime deploy while another agent is accepting the same runtime target.

Every agent must record:
- exact task-start main;
- branch/worktree;
- duplicate audit;
- REUSE/EXTEND/BUILD classification;
- PASS gate;
- blocker;
- one nextAction.

---

# 8. Permanent scientific / safety boundaries

Never claim:
- confluence = win probability;
- 80/100 = 80% success;
- fixed monthly return;
- risk-free arbitrage;
- “institution/market maker intent” from patterns;
- spoofing candidate = proven manipulation;
- absorption candidate = proven hidden actor;
- stablecoin mint = automatic bullish signal;
- funding/OI = deterministic future direction;
- options OI/max pain = deterministic target;
- historical success = calibrated probability;
- paper result = real executable result.

REAL_CAPITAL remains 0.

No exchange credentials/order/withdrawal authority are introduced by this roadmap.

---

# 9. Definition of final product done

Crypto Signal Final Product V1 is complete only when all are true simultaneously:

1. RDP11 Evidence Data Plane is PASS.
2. Command Center first screen passes real 10-second comprehension acceptance.
3. Market Pulse is live and truth-backed.
4. top attention cards are materiality-filtered and identity-bound.
5. Intelligence Stream remains persistent, live, searchable and exact.
6. signal/asset workspace preserves context without page chaos.
7. live vs signal-time chart modes are mechanically separated.
8. five evidence families expose strongest truthful human proof.
9. unavailable family evidence stays explicit.
10. Event Center is source/freshness aware.
11. Markets/Screener exposes truthful family states without invented zeros.
12. Watchlist is preference-only and cannot mutate evidence.
13. semantic alerts dedupe correctly and are transition-driven.
14. Paper Vault history is immutable and non-resettable.
15. historical Epoch 1/2 remain untouched and separately labelled.
16. final Paper Autopilot is forward-only.
17. cash is a valid allocation.
18. no forced deployment rule exists.
19. allocator uses portfolio risk/correlation/event/liquidity/drawdown context.
20. fixed fractional remains the default until probability calibration justifies otherwise.
21. execution accounts for accepted realistic costs and fill uncertainty.
22. unsupported partial/limit fill is never optimistically assumed.
23. each trade has an immutable Trade Passport.
24. each trade event freezes its own evidence/reason/cost/accounting context.
25. losses and stops remain visible forever.
26. equity curve and return are shown with drawdown/risk/cost.
27. R24/performance metrics reconcile to R21/R22.
28. global search can reach asset/event/signal/trade/proof by exact identity.
29. normal UX shows no SHA/internal enum/database vocabulary.
30. desktop/mobile/accessibility/long-session browser acceptance passes.
31. Product rollback/recovery path passes.
32. Durdurulmaz remains untouched.
33. Quantum Capital remains untouched.
34. REAL_CAPITAL=0.

Only then may the program status become:

**CRYPTO_SIGNAL_FINAL_PRODUCT_V1_ACCEPTED**
