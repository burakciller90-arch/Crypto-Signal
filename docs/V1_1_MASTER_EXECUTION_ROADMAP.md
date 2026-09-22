# Crypto Signal v1.1+ — MASTER EXECUTION ROADMAP

Status: **governing post-v1.0 execution plan**
Updated: **2026-09-22**
Baseline release: **crypto-signal-full-version-v1.0.0**
Safety invariant: **REAL_CAPITAL=0**

This file exists so a fresh agent can reconstruct not only *what* to build, but
*why the sequence exists*, which work is already accepted, what must not be repeated,
what is research-only, what may affect the canonical paper track record, and which
mechanical gates must pass before deployment.

---

## 0. Read-this-first execution contract

Before changing project state:

1. Read `READ_FIRST_CRYPTO_SIGNAL.md`.
2. Read `CURRENT_STATUS.md`.
3. Read the newest relevant `PROJECT_CHRONICLE.md` entries.
4. Reconcile Git HEADs, open PRs, workflow results, UID504 runtime processes,
   SSD mount state, data freshness, wake/lease state and any human-impact gate.
5. Never assume an old wake, checkpoint, memory or chat summary is current.
6. Completed/stale/superseded work is NOOP/reconcile, never replay.
7. REAL_CAPITAL remains 0. No exchange-order/credential authority is created here.

The v1.0.0 release is immutable. v1.1 evolves above it through isolated branches,
hosted gates, UID504 acceptance and explicit deployment/rollback evidence.

---

## 1. Product thesis

Crypto Signal is a **market intelligence, evidence and education terminal**, not a
black-box BUY/SELL service.

The product should answer, at increasing depth:

- What matters now?
- What is the system observing?
- What does it expect conditionally?
- What evidence supports and contradicts that expectation?
- What exact event would activate or invalidate it?
- What did the system know at issuance time?
- What happened afterward?
- What did the canonical 100 USDT paper fund actually do?
- How well are forecasts and policies performing under untouched-forward evidence?
- What is still unknown or insufficiently sampled?

A premium visual experience is important, but visual confidence must never exceed
scientific confidence.

---

## 2. Non-negotiable truth rules

1. Point-in-time truth; no future leakage.
2. Freeze a decision/forecast before its outcome.
3. Historical claims are never rewritten after the result is known.
4. Losses, invalidations, timeouts and abstentions remain visible.
5. Missing evidence is explicit; never invent data.
6. Confluence score is not probability.
7. Historical hit rate is not calibrated probability.
8. Backtest is not untouched-forward performance.
9. LLM/NLG text may explain frozen deterministic/statistical evidence but may not
   invent numeric market facts or hidden reasoning.
10. Cash / WATCH / ABSTAIN / CONFLICT / EVENT_BLOCK are valid professional states.
11. No forced trade exists merely to make the portfolio look active.
12. Research/Shadow evidence cannot contaminate the canonical paper fund.
13. Every promoted model/policy/weight set has a versioned lineage and acceptance gate.
14. REAL_CAPITAL=0 until a future separately-authorized real-money program exists.

---

## 3. Program structure — parallel tracks

After R15 runtime safety is mechanically accepted, v1.1 proceeds in parallel.

### Track A — World-Class Customer Product

Owns:

- application shell;
- Overview;
- Markets;
- Signals;
- Paper Portfolio;
- Intelligence;
- Performance;
- Archive;
- Learn;
- System;
- chart/proof visualization;
- responsive/accessibility behavior;
- customer-visible freshness;
- dual-layer explanations;
- Live Intelligence Feed.

Track A must not wait for all research engines to be complete. The product should
become progressively visible and useful while deeper data accumulates.

### Track B — Market Intelligence Data & Research

Owns:

- Crypto Signal Market Tape;
- liquidity intelligence;
- order flow / absorption;
- derivatives intelligence;
- on-chain / smart-money context;
- event-driven risk;
- fixed research-prior confluence;
- later calibrated probability and policy learning.

Track B must begin collecting time-sensitive raw evidence early because historical
microstructure is difficult or expensive to reconstruct later.

### Bridge Layer — Decision / Forecast / Proof / Paper

This is the critical junction between Track A and Track B:

market evidence
-> analysis engines
-> decision state
-> immutable forecast
-> frozen evidence bundle
-> canonical/shadow action
-> later outcome
-> performance/calibration
-> customer explanation/archive.

The bridge is where Crypto Signal stops being a collection of indicators and becomes
an auditable intelligence system.

---

## 4. R15 — SSD hot-plug recovery and live-data freshness

R15 is the operational prerequisite for production deployment of v1.1.

Required semantics:

- SSD absent => canonical runtime is unavailable/stale; **never** silently fall back
  to an internal-Mac runtime.
- SSD remounted => recovery checks DB integrity before restart-sensitive actions.
- Process existence alone is not health.
- Runner liveness must include progress/heartbeat or equivalent anti-hang evidence.
- Dashboard HTTP health must be separated from market-data freshness.
- UI must display stale evidence as stale even if HTTP is 200.

Acceptance:

- physical detach/remount test;
- runner reconnect;
- dashboard/supervisor restart;
- SQLite quick_check;
- no internal runtime fallback;
- latest candle/signal evidence advances after recovery;
- REAL_CAPITAL=0.

### Current 2026-09-22 blocker

The UID504 SSD runner has been observed as a long-lived `Runner.Listener` consuming
~98% CPU while dashboard/supervisor processes remain alive. Therefore R15 is **not
accepted live** merely because processes exist.

UID501 currently lacks permission to read the existing
`/Volumes/Crypto-504/Crypto-Signal` tree. A prepared ACL command grants UID501
access without changing the UID504 owner. Once applied, verify:

- ledger newest freeze timestamp;
- 15m candle-cache newest close/open timestamp;
- dashboard /api/health freshness fields;
- alert/paper clock freshness where relevant;
- runner CPU/state/progress;
- SQLite quick_check.

Do not declare the “04:00 data cut” fixed until timestamps advance beyond the stale
cutoff under the live canonical runtime.

---

## 5. R16–R18 — World-Class UI, visual language and proof charts

### Stable workspace shell

Primary navigation:

1. Overview
2. Markets
3. Signals
4. Paper Portfolio
5. Intelligence
6. Performance
7. Archive
8. Learn
9. System

Overview remains intentionally sparse:

- Market Pulse;
- BTC/ETH/SOL state;
- strongest ACTIVE/WATCH candidate;
- latest conditional forecast;
- canonical paper NAV and deployed capital;
- live-data freshness;
- system health.

### Visual system

- tabular numerals;
- financial-density typography;
- bullish/bearish semantics distinct from profit/loss semantics;
- explicit stale/error/recovery colors;
- restrained depth and glow;
- keyboard focus and reduced motion;
- touch-friendly controls;
- no layout shift from numeric updates.

### Chart/proof experience

Only real/frozen evidence may draw overlays:

- PA / SMC / ICT structure;
- liquidity sweeps/pools;
- FVG/BPR;
- harmonic PRZ/invalidation/targets;
- Elliott competing counts and invalidations;
- forecast trigger/target/invalidation zones;
- later order-flow/liquidity evidence.

Historical forecast detail must render the exact state frozen at issuance time, not a
recalculated present-day interpretation.

---

## 6. M1 — Crypto Signal Market Tape

Goal: build a proprietary, reproducible historical market-data asset on the SSD.

### Existing accepted foundations that must be reused

The repository already contains:

- `OrderBookSnapshot`;
- `PublicTradeObservation`;
- Bybit spot microstructure adapter;
- derivatives observations;
- Bybit funding/OI/mark/index adapter;
- Order Flow / Microstructure analysis engine;
- Derivatives Context analysis engine.

Do **not** duplicate those engines.

### Foundation slice

The v1.1 Market Tape foundation persists:

- order-book snapshots;
- public trades;
- derivatives observations;
- immutable identities;
- replay-safe semantic dedupe;
- WAL;
- SQLite quick_check;
- deterministic recent reads;
- freshness timestamps;
- canonical SSD path.

Draft PR #726 is the current foundation slice and hosted full-gate run
`35718669274` passed.

### Next Market Tape expansion

Move from bounded REST snapshots toward continuous public streams where source
contracts are reliable:

- aggregated/public trades;
- order-book depth snapshot + delta sequencing;
- reconnect/resync semantics;
- source and ingestion timestamps;
- sequence-gap detection;
- funding/OI snapshots;
- liquidation events where available;
- basis inputs;
- adapter/source versions.

Raw evidence and derived features must be separable so improved algorithms can
recompute features from retained history.

Storage policy must explicitly define retention, compaction and integrity rather than
assuming “free unlimited history”.

---

## 7. M2 — Liquidity Intelligence

Research-only first.

Derived evidence candidates:

- bid/ask depth imbalance;
- persistent liquidity pools;
- sweep evidence;
- stop-run/liquidity-take candidates;
- replenishment;
- cancellation/appearance velocity;
- shallow-book state;
- spoofing/ghost-order **candidates**;
- iceberg/hidden-liquidity **candidates**.

Never claim malicious intent or hidden institutional orders as directly observed fact.

Each derived feature needs:

- exact source window;
- point-in-time cutoff;
- freshness;
- source quality;
- deterministic identity;
- uncertainty flags;
- versioned algorithm.

---

## 8. M3 — Order Flow & Absorption

Build on the existing microstructure engine.

Target evidence:

- aggressive buy/sell notional;
- delta;
- cumulative volume delta;
- price/flow divergence;
- absorption candidates;
- price non-response to aggressive flow;
- breakout confirmation/failure;
- sweep + absorption interaction.

Order flow is evidence, not an automatic command.

A future decision must be able to say:

- what supported the move;
- what contradicted it;
- what evidence was absent/stale;
- whether the observation was research/shadow or production-eligible.

---

## 9. M4 — Derivatives Intelligence

Use:

- funding;
- open interest;
- mark/index basis;
- OI/price state;
- liquidation concentration where reliable;
- crowding/squeeze/deleveraging context;
- volatility/leverage transitions.

Rules such as “funding high => short” or “OI up + price up => long” remain hypotheses,
not universal production triggers.

---

## 10. M5 — On-chain / Smart Money & Event Risk

### On-chain / smart-money context

Potential evidence:

- exchange inflow/outflow anomaly;
- stablecoin flow anomaly;
- large-transfer clusters;
- wallet-cluster research where attribution is defensible;
- network activity.

Important caveats:

- wallet attribution can be wrong;
- survivorship bias must be considered;
- exchange inflow does not imply deterministic selling;
- no single on-chain feature receives unconditional trade authority.

### Event Risk Engine

Separate veto/context layer:

- CPI/Fed and major scheduled macro events;
- exchange/security incidents;
- listing/delisting/platform events where source quality is reliable;
- abnormal spread;
- abnormal volatility;
- abnormal depth loss;
- feed degradation.

Decision states may include:

- EVENT_BLOCK;
- WATCH;
- ABSTAIN;
- DEGRADED_DATA.

A fixed ±15-minute blackout may be an initial research rule, but final policy should
be conditioned on event classification and observed liquidity/volatility impact.

---

## 11. M6 — v1 fixed research priors

v1.1 starts with interpretable fixed priors:

- Geometry / PA / Elliott / Harmonic — **20%**
- Liquidity — **25%**
- Order Flow / Absorption — **25%**
- Derivatives — **15%**
- On-chain / Smart Money — **15%**

Event Risk is an external veto/context layer, not another additive weight.

These values are:

- research priors;
- not probability;
- not promised optimal weights;
- not automatic production authority.

The purpose is to collect clean forward evidence before building a complex adaptive
meta-model.

---

## 12. R19 — Calibrated Probability

Confluence and probability remain independent.

A displayed probability requires:

- exact outcome event definition;
- horizon;
- asset/timeframe/direction/setup scope;
- model/calibration version;
- training/evaluation cutoff;
- chronological/walk-forward fitting;
- untouched holdout/forward evaluation;
- sample count;
- class counts;
- Brier score;
- calibration error/reliability;
- evidence identity.

Current calibration foundation is in draft PR #723 and passed hosted gate
`35715364284`.

If acceptance fails or sample size is insufficient, UI says **NOT CALIBRATED**.
It never converts an 85 confluence score into “85% probability”.

---

## 13. R20 — Forecast Stream

Create immutable pre-outcome forecast objects.

Each forecast should contain:

- `forecast_identity`;
- issued_at;
- symbol;
- source timeframe;
- conditional trigger;
- direction;
- target zone;
- invalidation;
- forecast horizon;
- ETA window only when evidence supports it;
- confluence state;
- calibrated probability only when accepted;
- engine/evidence identities;
- market regime/context;
- plain-language rationale;
- technical rationale;
- uncertainty;
- status: OPEN / HIT_TARGET / INVALIDATED / EXPIRED / UNRESOLVED;
- immutable resolution/scoring record.

Preferred language is conditional:

“BTC 1h: 67,420 üzerinde kabul edilmiş kırılım korunursa 68,100–68,450 bölgesi
1–3 saatlik ufukta izleniyor. 67,050 altı kapanış tahmini geçersizleştirir.”

Never claim an exact future path is guaranteed.

---

## 14. R20.5 — Live Intelligence Feed / Decision Proof

User concept name: **Proof-of-Thought**.
Engineering/product name: **Live Intelligence Feed / Decision Proof**.

The implementation must **not** expose or pretend to expose private chain-of-thought.
What is persisted is the externally auditable evidence, state transition, rule outcome
and concise rationale that legitimately explains the decision.

This becomes the product's anti-black-box layer.

### 14.1 Immutable Decision Event

Every meaningful decision window may emit an immutable event:

- TRADE;
- WATCH;
- ABSTAIN;
- EVENT_BLOCK;
- CONFLICT;
- INSUFFICIENT_EVIDENCE;
- FORECAST_ISSUED;
- FORECAST_UPDATED only through append-only transition semantics;
- FORECAST_RESOLVED;
- PAPER_FILL;
- PAPER_EXIT.

Each event carries:

- event identity/hash;
- event time;
- market as-of time;
- asset/provider/timeframe;
- policy/model versions;
- source evidence identities;
- freshness;
- decision state;
- supporting evidence;
- contradicting evidence;
- missing/stale evidence;
- trigger;
- target/invalidation when applicable;
- uncertainty;
- canonical vs shadow authority;
- links to frozen chart/microstructure snapshots.

### 14.2 Frozen Evidence Bundle

At forecast issuance or canonical paper action, freeze the evidence actually available
then:

- canonical candle window;
- PA/Harmonic/Elliott evidence;
- confluence object;
- regime;
- Market Tape references;
- order-book snapshot;
- relevant trade-flow window;
- derivatives observations;
- later liquidity/CVD/absorption features;
- event-risk context;
- on-chain/context references when present.

The archive must answer months later:

**“What exactly did the system have available when it made this statement?”**

Later market data cannot rewrite this bundle.

### 14.3 Dual-Layer Explanation

Every feed card has two user-selectable explanation layers.

**Simple / beginner layer**

Explains market mechanics without jargon where possible, for example:

“Alıcılar son dakikalarda satış likiditesini daha agresif tüketiyor; ancak üstteki
direnç henüz kapanışla aşılmadığı için sistem işlem yerine kırılım teyidi bekliyor.”

**Technical layer**

Shows explicit evidence, for example:

- CVD divergence;
- taker imbalance;
- absorption candidate;
- sweep;
- OI/funding/basis;
- geometry;
- regime;
- contradictions;
- exact evidence IDs and timestamps.

The simple layer must be generated from the same structured evidence as the technical
layer. It may simplify wording, never strengthen certainty.

### 14.4 NLG / explanation renderer

Use a deterministic/template-first explanation layer before considering free-form LLM
generation.

Input example:

- order_flow = BUY_DOMINANT;
- book_pressure = BID_HEAVY;
- breakout = CONFIRMED;
- event_risk = CLEAR;
- contradictions = none.

Outputs:

- technical structured sentence;
- simple Turkish sentence;
- evidence references.

Rules:

- no invented numbers;
- no “institution bought” unless source proves attribution;
- avoid “very high probability” unless calibrated probability exists;
- if evidence conflicts, simple language must mention the conflict;
- if data is stale, explanation must say so.

LLM may later polish wording under strict structured-input/structured-output constraints,
but deterministic evidence remains the source of truth.

### 14.5 Intelligence Timeline UI

The Intelligence workspace should behave like a timestamped market-intelligence feed.

Each card shows at minimum:

- timestamp;
- asset/timeframe;
- state badge;
- conditional expectation;
- trigger;
- target/invalidation if valid;
- simple explanation;
- expandable technical evidence;
- calibrated probability or NOT CALIBRATED;
- freshness;
- canonical/shadow/research label;
- “Kanıtı Gör” action.

Opening proof shows:

- frozen chart;
- source candles;
- relevant order book/depth;
- trade flow/CVD once available;
- liquidity evidence;
- derivatives context;
- methodology agreement/contradictions;
- immutable IDs.

### 14.6 Outcome closure

When the forecast horizon closes, append an immutable resolution:

- target hit;
- invalidated;
- expired;
- ambiguous;
- not evaluable.

The original text is not edited.
UI shows **original forecast vs later outcome side-by-side**.

This is central to honest self-evaluation and educational value.

---

## 15. R21 — Canonical 100 USDT Paper Fund

The canonical fund is the official customer-visible simulated track record.

Rules:

- starting capital 100 USDT;
- REAL_CAPITAL=0;
- accepted policy only;
- spot/long-only under current accepted policy unless a later separately-tested policy
  explicitly changes it;
- no leverage;
- no borrowing;
- no martingale;
- no forced BUY;
- cash is valid;
- realistic fee/spread/slippage;
- explicit invalidation;
- immutable capital mutations.

Initial proposed risk envelope remains subject to acceptance:

- max single-position notional 25% NAV;
- max gross exposure 70%;
- minimum cash 30%;
- max 3 concurrent positions;
- no averaging down by default.

Every mutation records:

- timestamp;
- side/action;
- symbol;
- quantity;
- reference price;
- simulated fill;
- fee;
- spread/slippage;
- cash before/after;
- position before/after;
- realized/unrealized PnL where defined;
- forecast/signal/decision IDs;
- policy version;
- reason;
- immutable record identity.

Examples in design documents that contain shorts or arbitrary larger balances are
illustrations only; they do not override the accepted canonical policy.

---

## 16. R21.5 — Shadow Lab

Exploration never mutates canonical performance.

Shadow Lab may evaluate:

- 1h/lower-confidence lanes;
- WATCH-to-ACTIVE alternatives;
- threshold alternatives;
- with/without liquidity confirmation;
- with/without order-flow confirmation;
- event-filter alternatives;
- entry timing;
- holding horizons;
- counterfactual exits;
- fixed-prior alternatives.

Shadow records remain immutable and outcome-scored, but never enter canonical:

- NAV;
- PnL;
- win rate;
- profit factor;
- drawdown.

Promotion requires:

1. chronological sample sufficiency;
2. no future leakage;
3. cost realism;
4. walk-forward/untouched-forward evidence;
5. measurable advantage over current accepted policy;
6. regime stability;
7. explicit versioned promotion review.

The unfinished `v1.1-paper-active-learning-v1` branch must therefore not be merged
into canonical paper semantics as-is. Reuse useful ideas only by moving them into a
separate Shadow Lab architecture.

---

## 17. R22 — Transaction Tape and Live Ledger Audit

The Paper Portfolio workspace exposes a human-auditable ledger.

Two views:

### Event timeline

Every cash/position mutation in sequence.

### Round-trip trade view

Groups entry/reductions/exit into one realized trade while retaining links to the
underlying atomic events.

Customer-visible fields include:

- execution time;
- asset/action;
- entry/fill;
- exit;
- closure time;
- net PnL;
- resulting balance/NAV;
- close reason;
- forecast/decision proof link.

No history is rewritten to make performance look better.

---

## 18. R23 — Explainable Intelligence

Do not expose private chain-of-thought.

Expose:

- accepted engine observations;
- supporting observations;
- contradictory observations;
- stale/missing observations;
- regime;
- key levels;
- uncertainty;
- what would change the decision;
- research vs production/shadow authority;
- exact evidence identities.

Default is concise beginner-friendly Turkish.
Advanced drill-down exposes technical proof.

---

## 19. R24 — Performance, calibration and trust surfaces

Customer metrics:

- Total Equity;
- Net PnL absolute/%;
- max drawdown;
- exposure;
- turnover;
- cost drag;
- win rate only with valid denominator/sample;
- profit factor only when meaningful;
- benchmark-relative return;
- forecast score/calibration metrics;
- evidence class;
- sample size.

Any growth projection UI is explicitly **what-if**, never presented as realized or
guaranteed performance.

Performance must keep separate:

- RETROSPECTIVE;
- WALK_FORWARD;
- LIVE_UNTOUCHED_FORWARD;
- SHADOW;
- CANONICAL PAPER.

---

## 20. R25 — Customer-grade integrated acceptance

Before v1.1.0:

- full pytest;
- Ruff;
- mypy;
- JS syntax/tests;
- hosted gate;
- UID504 gate;
- exact deployment SHA;
- rollback proof;
- responsive/desktop review;
- keyboard/accessibility;
- reduced motion;
- route/state persistence;
- stale-data simulation;
- SSD detach/remount;
- runner hang/progress recovery;
- Market Tape SQLite integrity;
- Market Tape reconnect/gap semantics;
- forecast archive determinism;
- frozen proof replay;
- NLG/evidence consistency;
- canonical paper reconstruction;
- Shadow/Canonical isolation;
- calibration truth checks;
- REAL_CAPITAL=0;
- no exchange order/credential endpoint.

---

## 21. Deferred v2 frontier

These are explicitly preserved but do not delay v1.1.

### V2-A Cross-Asset / Correlation

Candidate context:

- stablecoin dominance;
- BTC dominance;
- NDX / broad risk assets;
- DXY;
- US Treasury yields;
- regime-conditioned rolling relationships.

No universal rule such as “DXY up => reject BTC long”. Correlation may weaken,
invert or disappear and therefore requires forward evidence.

### V2-B Execution & Market Impact

Upgrade beyond static slippage:

- executable depth;
- size-dependent slippage;
- shallow-book rejection;
- partial fills;
- latency sensitivity;
- implementation shortfall;
- impact-aware viability.

A high-confluence idea may become **NO_TRADE_LIQUIDITY** when implementation cost
destroys the edge.

### V2-C Adaptive Regime-Switching Weights

Reuse the existing Regime engine.
Do not build a disconnected second classifier.

Potential states:

- trend;
- range/auction;
- high-volatility/panic;
- compression;
- transition/uncertain.

Adaptive weighting may be promoted only if chronological walk-forward evaluation
beats the fixed-prior baseline without leakage and remains interpretable.

---

## 22. Release sequencing

Recommended progression:

- **v1.1-alpha.1** — R15 runtime recovery + R16 shell; M1 Market Tape starts.
- **v1.1-alpha.2** — R17/R18 chart/visual proof while M2–M4 data features accumulate.
- **v1.1-beta.1** — R19 calibrated probability + R20 Forecast Stream +
  R20.5 Live Intelligence Feed foundation.
- **v1.1-beta.2** — R21 Canonical Fund + R21.5 Shadow Lab + R22 Transaction Tape.
- **v1.1-rc.1** — M5 Event Risk + R23/R24 explainability/performance/trust.
- **v1.1.0** — only exact merged-main + UID504 + physical/runtime acceptance.
- **v2 research** — Cross-Asset, Market Impact, adaptive regime weighting after enough
  v1.1 forward evidence.

UI and Market Tape remain parallel throughout.

---

## 23. Current mechanical development map — 2026-09-22

Baseline:

- v1.0.0 immutable release accepted/frozen.

Open development:

- **PR #715** — R15 SSD hot-plug recovery; hosted PASS; live physical/runtime
  acceptance still incomplete.
- **PR #722** — world-class workspace shell + truthful freshness; draft.
- **PR #723** — untouched-forward calibrated probability foundation; hosted PASS; draft.
- **PR #726** — append-only Market Tape foundation; hosted full gate PASS
  run `35718669274`; draft.

Experimental:

- `v1.1-paper-active-learning-v1` contains unfinished/unaccepted work.
- Do not merge it into canonical fund behavior.
- Reframe useful exploration concepts under Shadow Lab.

Runtime blocker:

- UID504 SSD runner has shown long-running near-100% CPU listener behavior.
- Dashboard/supervisor process existence does not prove data freshness.
- Exact post-04:00 signal/candle advancement must be mechanically verified once UID501
  tree permission or UID504 diagnostic access is available.

---

## 24. Agent handoff rules

A new agent must:

- preserve v1.0.0;
- inspect current Git/PR/workflow/runtime state before acting;
- avoid re-implementing already-present intelligence engines;
- prefer feeding existing accepted engines with better persistent evidence;
- keep UI and data work parallel;
- keep Canonical Fund and Shadow Lab physically/logically separate;
- keep confluence and probability separate;
- store Decision Proof, not private reasoning;
- preserve original forecasts and append later outcomes;
- do not delete losses;
- do not invent performance;
- do not use illustrative examples as production policy;
- do not weaken tests to make a gate pass;
- do not deploy v1.1 before R15 live acceptance;
- never enable REAL_CAPITAL.

When uncertain, choose the bounded action that preserves evidence and reversibility.
