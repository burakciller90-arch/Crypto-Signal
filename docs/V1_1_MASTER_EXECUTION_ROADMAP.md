# Crypto Signal v1.1+ — MASTER EXECUTION ROADMAP

> ## LOCKED ROADMAP OVERRIDE — 2026-09-22
>
> The user-approved canonical post-v1.0 product contract is now
> **`docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`**.
> New agents must read that file before using the historical execution detail below.
> It supersedes conflicting older v1.1 scope, specifically:
> - Paper Fund Epoch 1 remains immutable at 100 USDT; **Epoch 2 starts separately at 1,000 USDT**;
> - execution is now **three parallel rails: Intelligence / Capital-Science / Product**;
> - the existing frontend is not the target; the Product rail is a **from-scratch GALACTECH // CRYPTO SIGNAL rebuild**;
> - M2–M5 are expanded with liquidation-map, bounded spoofing/iceberg candidates, deeper order-flow/derivatives, PIT wallet cohorts and Event/NLP risk;
> - Smart Capital Allocator begins as a 600/300/100 Core/Tactical/Reserve research policy;
> - R19 calibration remains mandatory before user-visible probability or Kelly-based sizing;
> - safe development may continue autonomously, but new production/human-impact mutations remain separately gated.
>
> Historical R15/M1/M2 evidence retained below is still valuable, but stale "current" statements must be reconciled against `CURRENT_STATUS.md` and live mechanical state.
>

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

### Current 2026-09-22 runtime evidence

The earlier “04:00 data cut” has now been mechanically rechecked **without relying on
process existence**.

At 2026-09-22 14:25:51 +0300, a temporary UID501 read-only localhost API diagnostic
reported:

- dashboard health: `status=ok`, `ledger_present=true`, `read_only=true`,
  `REAL_CAPITAL=0`;
- immutable signal freeze count: **294**;
- latest freeze: **2026-09-22 14:15:18 +0300**;
- Binance and Bybit BTC/ETH/SOL 15m contexts all had fresh ~14:15 freezes;
- 1h contexts had fresh ~14:01 freezes;
- therefore the market-data/freeze pipeline is **no longer stuck at 04:00**.

This closes the specific data-staleness incident.

A separate R15 blocker remains: the UID504 SSD GitHub runner
`Runner.Listener` was rechecked at 14:26:28 +0300 and remained at **100% CPU**,
state `RN`, with ~12 hours elapsed. Dashboard and SSD supervisor remained healthy.

Therefore R15 is still not fully accepted. The remaining work is runner hang detection
and safe recovery plus physical detach/remount acceptance. Do not restart or duplicate
the runner blindly; identify the exact listener and use an identity-checked recovery
path.

### Runner-hang recovery runbook

Never start a second UID504 runner merely because a GitHub job is queued.

Current live process ancestry was mechanically observed as:

`-zsh -> /bin/bash ./runsvc.sh -> ./externals/node20/bin/node ./bin/RunnerService.js -> /Volumes/Crypto-504/Crypto-Signal/Runner/bin/Runner.Listener`

This matters because the wrapper/service processes use **relative commands**. A recovery
implementation that searches only for `$RUNNER/` in process command lines can find the
Listener but miss `./runsvc.sh` and `RunnerService.js`. Killing only the Listener may
therefore allow the parent service to respawn it. Recovery must verify and stop the
exact ancestry tree before starting a new runner.

Preconditions:

1. Match the exact SSD listener command:
   `/Volumes/Crypto-504/Crypto-Signal/Runner/bin/Runner.Listener run --startuptype service`.
2. Require **exactly one** matching listener.
3. Require **zero** matching SSD `Runner.Worker` processes.
4. Require the listener to be at least **600 seconds old** so a newly starting runner is
   never classified as hung.
5. Sample the **same PID** for **6 consecutive watchdog cycles**.
6. Current bounded idle-spin threshold: each accepted sample is at or above **50% CPU**.
   With the 20-second watchdog cadence this requires roughly two minutes of sustained
   abnormal idle CPU after the minimum-age gate.
7. Verify the exact ancestry:
   `/bin/bash ./runsvc.sh -> RunnerService.js -> canonical SSD Runner.Listener`.
8. Abort immediately if a Worker appears, PID/command identity changes, CPU normalizes,
   ancestry is ambiguous, or multiple listeners are present.

Recovery sequence:

1. Stop the **verified parent service tree**, not merely the Listener:
   wrapper `./runsvc.sh`, then `RunnerService.js`, then the exact Listener.
2. Wait a bounded interval for graceful exit.
3. Before any forced kill, re-check identities and require Worker absence.
4. Force-kill only members of that already-verified old service tree if they remain.
5. Start exactly one SSD runner as `crypto-signal-agent`.
6. Require exactly one new listener and a different listener PID from the old tree.
7. Fail closed on duplicate listeners, changed ancestry or any Worker race.

Hosted proof for this current contract:
- runner-tree full gate: `35723794736` PASS;
- aged idle-spin full gate: `35724089582` PASS;
- full pytest, Ruff, mypy and product freshness contract all passed.

Post-recovery acceptance:

- exactly one SSD listener;
- queued UID504 jobs begin draining;
- dashboard remains healthy/read-only with REAL_CAPITAL=0;
- SQLite integrity checks pass;
- live signal/freeze timestamps continue advancing;
- no internal-Mac runtime fallback appears.

For the current incident, recovery ownership must remain single-owner. The earlier
PID-only attempts failed closed and did not mutate the runner. A newer recovery run
may exist while this document is being read; reconcile live GitHub Actions state before
starting anything. Do **not** launch a second recovery while any
`Crypto UID501 R15 Runner Recovery 20260922` run is queued or in progress. Only the
ancestry-aware hosted-PASS recovery contract above is acceptable for the next live
attempt.

UID501 filesystem access to the existing Crypto-504 tree is still useful for direct DB
and log forensics, but it is no longer required to prove that the 04:00 market-data
cut itself recovered because the live read-only API provided direct immutable-ledger
timestamps.

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

- **PR #715** — R15 SSD hot-plug + hung-runner recovery; hosted safety hardening PASS
  through exact-listener run `35724497074`; live runner recovery and physical
  detach/remount acceptance still incomplete.
- **PR #722** — world-class workspace shell + truthful freshness; draft.
- **PR #723** — untouched-forward calibrated probability foundation; hosted PASS; draft.
- **PR #726** — append-only Market Tape foundation; hosted full gate PASS
  run `35718669274`; draft.

Experimental:

- `v1.1-paper-active-learning-v1` contains unfinished/unaccepted work.
- Do not merge it into canonical fund behavior.
- Reframe useful exploration concepts under Shadow Lab.

Runtime status:

- The specific post-04:00 market-data/freeze interruption is mechanically **RECOVERED**
  by UID501 localhost diagnostic run `35721395160`.
- UID504 SSD runner is a separate open incident: latest read-only forensics showed one
  canonical listener PID `99399`, no Worker, exact service ancestry, ~97% CPU and
  ~12h40 elapsed while UID504 work remained queued.
- Process existence does not prove runner health.
- Hosted R15 safety hardening passed through exact-listener run `35724497074`
  (with aged idle-spin run `35724089582` also PASS).
- No live recovery workflow is currently active. Old one-shot attempts are stale and
  must not be replayed.
- Physical SSD detach/remount acceptance remains pending after runner recovery.
- Continuity transport is alive but user-pause latch remains present; shared wake queue
  is zero. Resume requires state-first removal of pause latches and a fresh exact
  continuation re-arm, never replay of archived wakes/leases.

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


### Continuity / wake / lease state — 2026-09-22

Read-only UID501 reconciliation run `35724768336` observed:

- shared relay RUNNING;
- protocol `crypto-relay-v2`;
- project namespace `crypto-signal`;
- exact expected target chat bound;
- shared wake queue = 0;
- shared `user_pause` PRESENT;
- UID504 `bridge_watchdog.py` alive;
- shared `relay_daemon.py` alive;
- UID501 cannot read the local SSD continuity directory.

Therefore local active-lease counts reported from UID501 are **not authoritative**.
The shared pause marker is authoritative enough to preserve pause-dominant behavior:
do not arm a lease, enqueue a wake or unpause continuity until a fresh explicit resume
action is authorized. Current-turn development may continue because the user supplied
a continuation message, but continuity transport state itself remains paused.
