# Crypto Signal v1.1 — LOCKED MASTER ROADMAP

Status: **LOCKED / GOVERNING POST-v1.0 PRODUCT CONTRACT**  
Locked by user: **2026-09-22**  
Baseline: **crypto-signal-full-version-v1.0.0 (immutable)**  
Safety invariant: **REAL_CAPITAL=0**  
Canonical paper program: **Epoch 2 starts at 1,000 USDT; Epoch 1 (100 USDT) remains immutable history**

> **FRONTEND-SPECIFIC AUTHORITY UPDATE — 2026-09-25**
>
> This locked roadmap remains the global v1.1 product/science/capital contract. Its high-level Product rail remains valid. For **current frontend architecture, brand hierarchy, information architecture, visual direction and frontend execution order**, read `docs/CRYPTO_SIGNAL_FRONTEND_MASTER_ROADMAP_V1.md`, `docs/CRYPTO_SIGNAL_FRONTEND_M0_CONSTITUTION.md` and the active `docs/CRYPTO_SIGNAL_FRONTEND_M1_CAPABILITY_GAP_LEDGER.md`.
>
> Older frontend route counts, dark-theme targets, GALACTECH-as-product wording and screen-order details in this or historical slice documents are retained as history where applicable; they are not current frontend design authority when they conflict with the canonical frontend program. Scientific, evidence, persistence, capital-safety and REAL_CAPITAL=0 rules are unchanged.

## 0. Authority and interpretation

This document is the canonical post-v1.0 product roadmap. New agents must read it after
`READ_FIRST_CRYPTO_SIGNAL.md` and `CURRENT_STATUS.md` and before proposing or implementing
new product work.

It supersedes older v1.1 product-scope language where the two conflict, while preserving:

- all accepted v1.0 scientific rules and release history;
- accepted R15 / Market Tape / M2 evidence;
- immutable historical ledgers and forecasts;
- REAL_CAPITAL=0;
- explicit production/human-impact approval gates;
- no future leakage, no history rewriting, no fabricated numeric truth.

The locked roadmap runs on **three parallel rails**:

1. **Intelligence** — Market Tape -> Liquidity -> Order Flow -> Derivatives -> On-chain/Event -> Confluence -> Forecast/Decision Proof.
2. **Capital / Science** — calibration -> Paper Fund Epoch 2 -> Smart Capital Allocator -> sizing -> Shadow Lab -> transaction/performance truth.
3. **Product** — complete frontend rebuild -> Command Center -> Evidence Room -> Markets -> Capital -> Archive -> Performance -> Learn/System.

Safe development proceeds without unnecessary user-approval pauses. A new production or
human-impact mutation remains a separate gate.

## 1. Locked scientific constitution

1. Point-in-time truth only; no future leakage.
2. Forecast/decision freezes before outcome.
3. Original forecasts and decisions are never rewritten after outcomes.
4. Loss, invalidation, expiry, timeout, abstain, conflict and not-evaluable remain visible.
5. Missing/stale evidence is explicit; data is never invented.
6. **Confluence is not probability.**
7. **Historical hit rate is not calibrated probability.**
8. Backtest is never presented as untouched-forward evidence.
9. Numeric market truth comes from deterministic/statistical evidence, never invented LLM prose.
10. Cash / WATCH / ABSTAIN / CONFLICT / EVENT_BLOCK / DEGRADED_DATA are valid professional states.
11. The system never forces activity merely to appear active.
12. Shadow/research results never mutate canonical NAV/PnL/performance history.
13. Every promoted model, threshold, policy or weight set is versioned and gated.
14. Spoofing, iceberg, smart-money and liquidation inferences are bounded candidate/context evidence, not unsupported claims of actor intent.
15. REAL_CAPITAL remains 0. No real exchange order, trading credential, leverage or withdrawal authority is created by this roadmap.

## 2. Accepted baseline and no-replay boundary

Do **not** restart completed work simply because an older document or wake mentions it.

Already accepted / closed foundations include:

- immutable v1.0.0 release baseline;
- v1.0 data truth, PA/SMC/ICT, Harmonic, Elliott, Confluence, signal lifecycle, immutable ledger and outcome model;
- R15 SSD/runner recovery work and physical detach/remount acceptance;
- Market Tape raw/normalized persistence foundations;
- measured Hot SQLite -> Cold Parquet/Zstd architecture;
- R11 Terminal/TCC single-owner production topology;
- Hot/Cold live acceptance and heartbeat hardening;
- M2 Liquidity Dynamics Slice 1 hosted/live/persisted-replay acceptance.

The first action in every new agent session is **state reconciliation**, not replay.

## 3. Phase 0 — Current-state reconciliation and real Cold Archive truth

Before writing new product code, read-only verify:

- SSD mounted and canonical project root available;
- exactly one top-level SSD supervisor;
- exactly one Market Tape supervisor;
- exactly one Market Tape runtime;
- fresh runtime/supervisor heartbeats;
- raw Market Tape rows advancing;
- dashboard health is truthful and `read_only=true`;
- REAL_CAPITAL=0;
- critical SQLite `PRAGMA quick_check` passes;
- free-space / hot-cap / cold-cap guards are healthy.

Because enough time may now have passed, inspect the **first real 26h+ production cold
partition** if present:

- manifest validity;
- row counts;
- canonical row digests;
- Parquet hashes;
- successful readback;
- hot prune only after verification;
- post-prune SQLite integrity;
- expected hot-window size;
- cold bytes increasing;
- free-space reserve intact.

Start read-only. Do not force archive/prune before mechanical state is known.

**Exit:** current production/data plane is mechanically healthy. M1/R15 remain closed.

## 4. Phase 1 — Constitution v1.1.1 and Paper Fund Epoch 2

### Epoch model

Historical Epoch 1 remains immutable:

- **Epoch 1 — Legacy**
- starting NAV: **100 USDT**
- existing ledger/performance remains unchanged.

New canonical paper history starts as a distinct epoch:

- **Epoch 2 — Current**
- starting NAV: **1,000.00 USDT**

Never multiply, restate or rewrite Epoch 1 history to simulate the new capital amount.

The UI and data model must expose epoch identity explicitly.

### Capital hard boundaries

- REAL_CAPITAL=0;
- no real orders;
- no leverage in accepted canonical v1.1 lane;
- no borrowing;
- no martingale;
- no history rewrite;
- no shadow-to-canonical contamination;
- fee/spread/slippage remain mandatory;
- cash remains a valid state.

**Exit:** versioned Epoch 2 spec/model/migration path accepted without modifying Epoch 1 history.

## 5. Phase 2 — Market Tape v2: unified evidence time machine

Extend the existing Market Tape rather than replacing it.

Retain and version, where reliable sources exist:

- raw public microstructure wire evidence;
- normalized order books;
- public trades;
- liquidation events;
- funding observations;
- open-interest observations;
- mark/index/basis observations;
- on-chain observations;
- exchange-flow observations;
- wallet-cohort observations;
- event/macro observations;
- news/NLP observations.

Every retained observation should carry as applicable:

- source timestamp;
- ingestion timestamp;
- PIT cutoff;
- provider/source identity;
- semantic identity;
- schema/adapter version;
- freshness;
- source quality;
- raw evidence reference.

Raw evidence and derived features remain separable so algorithms can be recomputed later.

## 6. Phase 3 — M2 Liquidity Intelligence 2.0

Build on accepted M2 Slice 1.

### Persistent liquidity map

Measure over time:

- bid/ask depth;
- persistent walls/pools;
- appearance velocity;
- cancellation velocity;
- replenishment;
- depletion;
- price distance;
- survival time;
- freshness and source quality.

Distinguish:

- confirmed visible liquidity;
- persistent liquidity region;
- potential liquidation cluster;
- uncertain liquidity zone.

### Liquidation Heatmap

Add a distinct research layer where data supports it.

Keep separate concepts:

- observed liquidation;
- estimated leverage concentration;
- liquidation-risk zone.

Do not claim exact retail stops unless the source truly provides that information.

### Sweep Engine

A level touch alone is not a stop hunt. Evaluate:

- pool interaction;
- depth depletion;
- aggressive flow;
- displacement;
- recovery;
- follow-through.

Output bounded semantics such as `LIQUIDITY_SWEEP_CANDIDATE`.

### Spoofing / ghost-order candidate

Model order appearance -> persistence -> price approach -> cancellation -> recurrence.

Output `SPOOFING_CANDIDATE`, never “market maker manipulation proven.”

### Iceberg / hidden-liquidity candidate

Repeated execution plus replenishment against low visible size may produce
`HIDDEN_LIQUIDITY_CANDIDATE`.

Never infer a specific institution or actor without evidence.

**Exit:** PIT-safe deterministic identities, uncertainty/freshness semantics, replay tests and live bounded acceptance.

## 7. Phase 4 — M3 Order Flow & Absorption 2.0

Derive and freeze:

- aggressive buy volume;
- aggressive sell volume;
- delta;
- CVD / rolling CVD;
- price-CVD divergence;
- volume imbalance;
- trade velocity;
- large aggressive prints.

### Absorption

Combine aggressive flow with price non-response and replenishment. Examples:

- `ASK_ABSORPTION_CANDIDATE`;
- `BID_ABSORPTION_CANDIDATE`.

Absorption is evidence, **not** an automatic long/short command.

### Fakeout / breakout intelligence

Evaluate:

- liquidity cleared?;
- CVD confirms?;
- aggressive flow confirms?;
- OI confirms?;
- price accepted beyond level?;
- re-entry occurred?

Possible evidence states include:

- `BREAKOUT_CONFIRMED`;
- `BREAKOUT_FAILURE_CANDIDATE`.

### Sweep + absorption interaction

Freeze combined temporal patterns such as sweep -> aggressive continuation -> absorption -> rejection.

**Exit:** deterministic evidence objects, live/replay acceptance and no automatic trade authority.

## 8. Phase 5 — M4 Derivatives Intelligence 2.0

Reuse existing derivatives infrastructure.

### OI x Price state machine

Represent states including:

- price up / OI up;
- price up / OI down;
- price down / OI up;
- price down / OI down;
- price flat / OI expanding.

These are context states, not universal directional rules.

### Funding intelligence

Use where provided:

- current funding;
- predicted/next funding;
- percentile;
- acceleration;
- cross-venue divergence.

### Basis intelligence

- perpetual vs spot;
- mark vs index;
- cross-venue basis.

### Crowding engine

Combine OI, funding, basis, liquidations and volatility into bounded context:

- `LONG_CROWDING`;
- `SHORT_CROWDING`;
- `SQUEEZE_RISK`;
- `DELEVERAGING`.

**Exit:** PIT-safe derivatives evidence and no “funding high => short” shortcut.

## 9. Phase 6 — M5 Smart Money / On-chain 2.0

### Exchange-flow engine

For supported assets/stablecoins track:

- inflow anomaly;
- outflow anomaly;
- netflow;
- historical percentile;
- velocity.

No rule such as “USDT inflow => guaranteed pump.”

### Large-transfer clusters

Prefer repeated relationships, known exchange clusters, temporal clustering and size normalization over one-off whale headlines.

### PIT Wallet Cohort Registry

Avoid survivorship/selection bias.

A wallet/cohort’s admission time is frozen. Performance after admission is measured
forward. Do not label a wallet “insider” without defensible evidence.

**Exit:** auditable source/attribution quality and forward-measurable cohort identity.

## 10. Phase 7 — Event Risk + NLP Intelligence

Treat Event Risk as a safety/veto layer.

### Structured macro/event calendar

Where sources permit:

- CPI/inflation;
- FOMC/Fed/rate decisions;
- employment;
- major regulatory events;
- exchange/security/listing/delisting events.

### News intelligence

Each event carries:

- event identity;
- source;
- publication timestamp;
- ingest timestamp;
- affected assets;
- category;
- confidence/source quality.

### Circuit-breaker policy

A ±15 minute window may be an initial research rule, never a universal law.

Possible states:

- pre-event caution;
- `EVENT_BLOCK`;
- post-event stabilization;
- `DEGRADED_DATA`;
- `ABSTAIN`.

Also trigger on abnormal spread, depth loss, feed delay, price gaps or provider disagreement.

**Exit:** event windows are versioned/evaluated and the system fails closed when evidence quality degrades.

## 11. Phase 8 — M6 Confluence Matrix 2.0

Locked v1.1 **research priors**:

- Geometry / PA / Elliott / Harmonic: **20%**
- Liquidity: **25%**
- Order Flow / Absorption: **25%**
- Derivatives: **15%**
- On-chain / Smart Money: **15%**

Event Risk is outside the 100-point matrix as veto/context.

These are priors, not probabilities and not proof of optimality.

### Threshold research

A nominal ACTIVE threshold near 80 is a **hypothesis**, not a promise. Shadow Lab
must compare at least 70 / 75 / 80 / 85 under chronological forward evidence.

### Conflict veto

Keep separately:

- support score;
- opposition score;
- independent conflicts;
- evidence quality;
- freshness.

A high arithmetic total must not override material contradictory evidence.

**Invariant:** `Confluence 82/100` may coexist with `Probability: NOT CALIBRATED`.

## 12. Phase 9 — R19 calibrated probability

Percent probability is earned, not fabricated.

A user-visible probability requires:

- exact outcome event definition;
- horizon;
- asset/timeframe/regime scope;
- model/calibrator version;
- training/evaluation cutoff;
- chronological/walk-forward fitting;
- untouched holdout/forward evidence;
- sample count;
- class counts;
- Brier score;
- reliability/calibration error;
- evidence identity.

If acceptance is insufficient, display **NOT CALIBRATED**.

A target such as “80%+ accuracy” is a research aspiration only; it is never a guarantee
or a substitute for calibration evidence.

## 13. Phase 10 — Smart Capital Allocator

Epoch 2 begins from **1,000 USDT** with an initial research allocation:

- **CORE VAULT — 600 USDT**
- **TACTICAL VAULT — 300 USDT**
- **OPPORTUNITY RESERVE — 100 USDT**

This is a starting research policy, not a guaranteed optimal allocation.

### Core Vault

- highest evidence completeness;
- low conflict tolerance;
- lower trade frequency;
- event-risk respect;
- no forced deployment.

### Tactical Vault

- short-horizon / microstructure research;
- 1m/5m evidence where data quality allows;
- order flow / CVD / absorption / liquidity sweep;
- **no leverage in canonical v1.1**.

### Opportunity Reserve

Do not blindly buy a crash. Require recovery/stabilization evidence such as:

- spread stabilization;
- liquidity recovery;
- event-risk state;
- price discovery;
- feed quality.

Every vault exposes its own NAV, cash, exposure, PnL, drawdown, cost and turnover while
the parent fund exposes consolidated NAV.

## 14. Phase 11 — Position Sizing Intelligence

Sizing may consider:

- expected edge;
- calibrated probability;
- loss magnitude;
- correlation;
- current drawdown;
- volatility;
- liquidity;
- transaction cost.

### Kelly boundary

Kelly remains **disabled until R19 calibration is accepted**.

Shadow research may compare:

- full Kelly;
- 1/2 Kelly;
- 1/4 Kelly;
- fixed fractional.

Canonical promotion requires explicit evidence and bounded risk. Martingale remains forbidden.

## 15. Phase 12 — Market-neutral / arbitrage research

Shadow-only research families may include:

- cross-exchange spread;
- spot-perpetual basis;
- funding capture;
- delta-neutral.

Never describe these as “risk-free” or guaranteed. Model execution, latency, fees,
slippage, funding changes, transfer constraints and counterparty/exchange risk.

No direct canonical mutation without promotion gates.

## 16. Phase 13 — R20 Immutable Forecast Stream

Every forecast carries:

- forecast identity;
- asset/symbol;
- timeframe;
- issued_at;
- condition/trigger;
- direction;
- target/target zone;
- invalidation;
- horizon;
- confluence;
- calibrated probability only if R19 allows;
- event context;
- engine/evidence IDs;
- model/policy versions;
- freshness and uncertainty.

Forecast is frozen pre-outcome.

Later append only:

- HIT_TARGET;
- INVALIDATED;
- EXPIRED;
- AMBIGUOUS;
- NOT_EVALUABLE;
- other accepted resolution states.

Original forecast text/state is never edited.

## 17. Phase 14 — R20.5 Decision Proof / Live Intelligence Feed

This is the signature bridge between intelligence and product.

A card must show:

- state;
- asset/timeframe;
- timestamp;
- one-sentence conditional thesis;
- trigger;
- target;
- invalidation;
- evidence summary;
- freshness;
- authority (canonical/shadow/research);
- probability or NOT CALIBRATED.

**PROOF / KANITI AÇ** opens the exact issuance-time world:

- frozen chart;
- exact consumed candles;
- order book;
- liquidity map;
- liquidation map where supported;
- CVD/order flow;
- OI/funding/basis;
- on-chain/event context;
- methodology support/conflict;
- exact immutable identities.

Simple and technical explanations derive from the same structured evidence. Simple prose
may reduce jargon but never increase certainty.

## 18. Phase 15 — R21 Canonical 1,000 USDT Paper Fund

Activate Epoch 2 only after its spec/data migration path and policy are accepted.

Parent fund: **1,000 USDT**

Initial vaults:

- Core 600;
- Tactical 300;
- Reserve 100.

For each vault and consolidated fund track:

- NAV;
- cash;
- positions/exposure;
- realized/unrealized PnL;
- drawdown;
- fees/spread/slippage;
- turnover;
- expectancy;
- win/loss and outcome distribution.

Cash is a valid position. No vault may rewrite another vault or Epoch 1 history.

## 19. Phase 16 — R21.5 Shadow Lab 2.0

Research may compare:

- confluence thresholds;
- alternative priors/weights;
- scalping/microstructure policies;
- fractional-Kelly sizing;
- arbitrage/market-neutral policies;
- entry/exit alternatives;
- horizon alternatives;
- event windows;
- liquidity definitions;
- wallet filters.

Shadow success never auto-promotes itself. Champion/challenger promotion remains explicit,
versioned and forward-validated.

## 20. Phase 17 — R22 Transaction & Decision Tape

Every canonical paper capital mutation must be traceable to:

- forecast ID;
- vault;
- policy;
- entry/fill;
- reference and simulated fill price;
- slippage/spread/fee;
- sizing decision;
- cash/position before and after;
- exit;
- PnL;
- outcome;
- evidence IDs;
- immutable record/hash identity.

The user must be able to explain any NAV movement from the tape.

## 21. Phase 18 — R23 Explainable Intelligence

Two views of the same evidence:

### SIMPLE

Plain-language market mechanics for a beginner.

### PRO

CVD, delta, absorption, order-book imbalance, liquidity/liquidations, OI/funding/basis,
event risk, PA/methodology evidence, source quality and exact timestamps.

Simple mode may never be more certain than the technical evidence.

## 22. Phase 19 — R24 Performance & Trust Center

Expose truthful performance including:

- forecast accuracy/outcome distribution;
- calibration;
- Brier score;
- reliability;
- expectancy;
- profit factor;
- max drawdown;
- risk-adjusted metrics where properly defined;
- vault performance;
- fees/slippage;
- abstain/conflict/ambiguous rates;
- event-block effectiveness;
- version comparison;
- untouched-forward cohorts.

Winners and losers are shown together.

Backtest and untouched-forward performance are never merged into one unlabeled metric.

## 23. Product rail — complete frontend rebuild

The current frontend is **not** the locked target design. Do not keep patching it into the
new product. Rebuild the customer frontend from first principles while reusing truthful
APIs/evidence contracts.

Brand/product thesis:

# GALACTECH // CRYPTO SIGNAL

**Bloomberg precision × cinematic sci-fi.**

The interface should make a trader feel that a very complex market-intelligence machine
is working underneath, while the surface itself remains calm, legible and controlled.

### Visual language

Base:

- deep-space background around `#06080C -> #0B0F17`;
- dark clean primary surfaces;
- glass/frosted treatment reserved for floating proof/modal layers.

Semantic accents:

- Cyan: intelligence / live data;
- Emerald: bullish/positive confirmation;
- Crimson/Magenta: bearish/risk;
- Amber: watch/event/uncertainty;
- optional Purple: Shadow/Research authority.

Neon is semantic, not decorative. Approximately 80% of the screen should remain calm;
20% may carry cinematic emphasis.

Typography:

- body/UI: Inter or Plus Jakarta Sans;
- prices/timestamps/hashes/technical IDs: JetBrains Mono or equivalent tabular mono.

### Motion

Rule: **zero meaningless motion**.

Motion is reserved for:

- fresh tick;
- genuine state change;
- new intelligence event;
- active risk;
- live tape.

Support reduced motion. Sound is optional and off by default.

### Cold-start boot

A short first-load/cold-start sequence may show truthful checks such as:

- MARKET TAPE ... ONLINE
- LIQUIDITY ENGINE ... ONLINE
- LEDGER ... VERIFIED
- REAL CAPITAL ... DISABLED

No repeated blocking animation during normal navigation.

## 24. Product information architecture

Primary navigation is locked to:

1. **COMMAND**
2. **MARKETS**
3. **INTELLIGENCE**
4. **CAPITAL**
5. **ARCHIVE**
6. **PERFORMANCE**
7. **LEARN**
8. **SYSTEM**

Global asset focus begins with ALL / BTC / ETH / SOL and can later become searchable.

### COMMAND CENTER

Top situation strip:

- BTC/ETH/SOL state;
- Event Risk;
- data freshness;
- live connection health/latency if genuinely measured;
- Paper NAV.

Center stage: sparse Intelligence Feed with meaningful state transitions only.

Left rail: parent NAV + Core/Tactical/Reserve state + compact equity curve.

Right rail: Critical Radar for only material events:

- EVENT_BLOCK;
- liquidity anomaly;
- feed degradation;
- major liquidation/OI event;
- material wallet anomaly;
- forecast invalidation.

### EVIDENCE ROOM

Full-screen signature proof experience.

Recommended composition:

- frozen chart;
- order book / liquidity / liquidation overlays;
- CVD + OI + funding context;
- evidence stack with SUPPORT / CONTRADICT / NEUTRAL / INSUFFICIENT;
- confluence;
- probability or NOT CALIBRATED;
- issued timestamp;
- freeze/evidence identity.

### MARKETS

Professional chart workspace with explicit layer toggles:

- PA;
- LIQ;
- FLOW;
- DERIV;
- ONCHAIN.

Do not render every layer simultaneously by default.

### CAPITAL

Show:

- total NAV;
- vault allocations;
- exposure/cash;
- positions;
- risk budget;
- PnL;
- equity curve;
- drawdown;
- fees/slippage;
- “Why this allocation?” evidence.

### ARCHIVE / PROOF WALL

Filter immutable historical decisions/forecasts:

- winners;
- losers;
- expired;
- invalidated;
- ambiguous;
- abstain/not-evaluable.

Always preserve issuance snapshot beside later outcome.

### PERFORMANCE

Calibration, Brier, forward performance, drawdown, expectancy, vault/version/cohort
comparison. Clearly separate backtest from live untouched-forward.

### LEARN

Explain concepts against real evidence where possible:

- What is CVD?
- What is absorption?
- Why did the system abstain?
- What made this forecast invalid?

### SYSTEM

Expose truthful technical health:

- Market Tape;
- data providers;
- latency/freshness;
- Cold Archive;
- ledger;
- Paper Engine;
- Event Feed;
- REAL_CAPITAL.

Beginner view stays simple; developer view may drill down.

## 25. Product truth and UX invariants

- No fake latency.
- No fake “LIVE”.
- No fake probability.
- No fake whale attribution.
- No fake spoofing certainty.
- No stale data hidden behind green health.
- Color is never the only state indicator.
- Reduced motion supported.
- Desktop-first but responsive.
- Aim for 60 FPS without delaying market data for animation.
- The interface should not look complex; it should communicate that it is **managing complexity** for the user.

## 26. Parallel execution map

| Intelligence | Capital / Science | Product |
| --- | --- | --- |
| M2 Liquidity 2.0 | R19 Calibration | UI rebuild foundation |
| M3 Order Flow | Paper Epoch 2 spec | Command Center |
| M4 Derivatives | Smart Capital Allocator | Evidence Room |
| M5 On-chain/Event | Position Sizing | Markets / Capital |
| M6 Confluence | Shadow Lab 2.0 | Archive |
| Forecast Engine | Transaction Tape | Performance |
| Decision Proof | Trust Metrics | Learn / System |

The tracks advance in parallel. Product does not wait for all research; research does not
invent fake data to make Product look complete.

## 27. Locked critical path

Primary path:

**Runtime/Cold truth -> Paper Epoch 2 constitution -> Market Tape v2 -> M2 Liquidity 2.0 -> M3 Order Flow -> M4 Derivatives -> M5 On-chain/Event -> M6 Confluence -> R19 Calibration -> Smart Capital Allocator -> R20 Forecast -> Decision Proof -> 1,000 USDT Canonical Fund -> Shadow Lab -> Transaction Tape -> Explainability -> Performance/Trust -> full integrated acceptance -> v1.1.0.**

Product path in parallel:

**retire current visual target -> new design system -> Command Center -> Evidence Room -> Capital Center -> Markets -> Archive -> Performance -> Learn/System -> accessibility/performance polish -> production UI cutover.**

## 28. Release and acceptance

v1.0.0 remains immutable.

A v1.1.0 release requires:

- exact merged-main identity;
- hosted full regression;
- UID504/runtime acceptance;
- deployed source hashes matching accepted tree;
- single-owner supervisors/runtimes;
- fresh heartbeats;
- critical SQLite integrity;
- healthy Hot/Cold Market Tape;
- truthful dashboard health/freshness;
- deterministic forecast/archive replay;
- paper transaction audit replay;
- probability truth checks;
- frontend accessibility/reduced-motion/responsive acceptance;
- REAL_CAPITAL=0.

Hosted PASS does not replace live acceptance.

## 29. Human-impact / production authority

The user has authorized continuous safe development. Do not repeatedly ask for permission
between normal bounded development stages.

However, a new production/human-impact action still requires explicit human approval,
including examples such as:

- enabling a new production mutation path;
- destructive/irreversible production data operations;
- reboot/logout/physical SSD manipulation;
- credential or authority expansion;
- any future real-money enablement.

Development, hosted tests, read-only diagnostics and isolated paper/research work may
continue under the existing autonomy contract when no separate human-impact gate is crossed.

## 30. New-agent start rule

A fresh agent must:

1. read `READ_FIRST_CRYPTO_SIGNAL.md`;
2. read `CURRENT_STATUS.md`;
3. read this locked roadmap;
4. read newest relevant Chronicle entries;
5. inspect actual Git/PR/runtime/continuity state;
6. NOOP completed/stale work;
7. continue from the first incomplete locked frontier;
8. preserve REAL_CAPITAL=0 and every scientific invariant above.

**Do not replace this roadmap with an older chat summary or stale branch note.**


## 31. Execution tooling addendum — no Cursor worker/composer

User-authorized process update (2026-09-22):

- New work must **not** be delegated to Cursor workers, Cursor composer, or `supervisor-*` Cursor worktrees.
- That path is disabled because prior use produced repeated errors and slowed project completion.
- The preferred safe-development path is direct GitHub branch/PR implementation, hosted acceptance gates, and narrowly scoped self-hosted runtime verification where needed.
- Cursor tooling may be inspected only for stale-state detection; stale work is reconciled/NOOPed rather than resumed.
- This changes execution mechanics only; it does not alter any locked product/scientific scope, REAL_CAPITAL=0, or production/human-impact authority boundaries.
