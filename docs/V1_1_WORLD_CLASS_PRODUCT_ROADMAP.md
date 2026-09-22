# Crypto Signal v1.1 — World-Class Product & Market Intelligence Roadmap

Status: **implementation roadmap**
Baseline: **Full Version v1.0.0 frozen**
Baseline tag: `crypto-signal-full-version-v1.0.0`
Safety invariant: **REAL_CAPITAL=0**

## 1. Product thesis

v1.1 turns the accepted v1.0.0 evidence platform into a premium, customer-ready
market intelligence product without weakening scientific truth.

The product must feel simple at first glance and deep on demand:

- first screen answers what matters now;
- each claim can be opened into evidence;
- advanced research remains available but never floods the default view;
- live freshness is explicit;
- paper activity is auditable to exact simulated fills;
- forecasts are timestamped before outcomes and later scored;
- percentages are shown only when they are genuinely calibrated.

No real-money, exchange-order, credential, leverage, borrowing, shorting or
martingale authority is added by this roadmap.

### Program execution model

v1.1 is intentionally developed as **two parallel product tracks** after the R15
runtime prerequisite is mechanically stable:

- **Track A — Customer Product:** R16–R18 shell, visual system, chart/proof UX,
  portfolio surfaces and customer-visible explainability.
- **Track B — Market Intelligence Data:** raw public-market capture, derived
  microstructure features, derivatives context, liquidity intelligence and event
  risk infrastructure.

Neither track waits for the other to be "finished". The product must keep becoming
visible and usable while the proprietary dataset begins accumulating immediately.
Backend research must not postpone customer-grade UI, and UI polish must not delay
collection of time-sensitive raw market data that cannot be recreated cheaply later.

## 2. R15 — SSD hot-plug recovery and runtime freshness

Critical prerequisite.

### Required behavior

- unplugged SSD => product/runtime becomes unavailable or stale, never falls back
  to an internal-Mac runtime;
- remounted SSD => canonical supervisor, dashboard, clocks and UID504 runner recover;
- SQLite quick-check happens before restart-sensitive recovery;
- stale PID files are not treated as proof of a live process;
- recovery is owned by a tiny internal bootstrap only; all market/runtime DBs stay
  on `/Volumes/Crypto-504/Crypto-Signal`;
- dashboard health exposes **data freshness**, not only HTTP/process health;
- UI must not label a successful HTTP refresh as “live” when the underlying
  signal evidence is old.

### Acceptance

- physical detach/remount test;
- runner reconnect test;
- supervisor/dashboard restart test;
- latest signal/candle evidence advances after remount;
- no internal runtime fallback;
- REAL_CAPITAL=0.

## 3. R16 — World-class application shell

Replace the one-long-page experience with a stable command-center shell.

### Primary navigation

1. Overview
2. Markets
3. Signals
4. Paper Portfolio
5. Intelligence
6. Performance
7. Archive
8. Learn
9. System

Only the active workspace is presented as the primary content surface. The
sidebar/navigation remains stable. Advanced information is progressively
disclosed.

### Overview

The Overview must be intentionally sparse:

- Market Pulse
- current BTC/ETH/SOL state
- strongest active/watch setup
- paper NAV / deployed capital
- latest forecast
- live-data freshness
- system status

No research-engine inventory dump on the first screen.

### Interaction standard

All interactive surfaces must have:

- hover, focus-visible and pressed states;
- 120–180 ms micro-interactions;
- reduced-motion support;
- clear keyboard focus;
- touch-friendly hit areas;
- no layout shift from changing numbers.

Cards that open evidence use a consistent detail drawer/dialog pattern.

## 4. R17 — Premium visual system

### Typography

- UI font stack optimized for dense financial reading;
- tabular numerals for prices, percentages, timestamps and PnL;
- minimum body/supporting text size suitable for long sessions;
- strong separation of display, body and numeric text.

### Semantic color

- bullish and profitable are not blindly conflated;
- bearish and loss are not blindly conflated;
- neutral/watch/waiting use separate muted/amber semantics;
- stale/error/recovery states have dedicated colors;
- research/shadow authority has a visually distinct neutral language.

### Depth

Use low-opacity borders, restrained layered surfaces and small shadows. Avoid
excess glow. A glow/pulse is reserved for a genuinely new live event.

## 5. R18 — Chart and proof experience

### Market surfaces

- compact 24h/selected-horizon sparklines where supported by real candle data;
- full candlestick views on asset detail;
- support/resistance, invalidation, target zones and selected methodology evidence;
- optional overlays for Price Action, Harmonic and Elliott evidence;
- tooltips with source and timestamp;
- no reconstructed or invented chart point.

### Frozen proof

Every historical forecast/signal opens the exact frozen evidence that existed at
issuance time. Later candles never rewrite the old claim.

## Parallel Track M1–M6 — Market Intelligence Foundation

This track begins in parallel with R16–R18 once R15 runtime safety is accepted.
It does not grant production signal authority by itself.

### M1 — Crypto Signal Market Tape

Persist timestamped raw/near-raw public market evidence on the canonical SSD:

- Binance/Bybit public trade flow / aggregated trades where available;
- order-book depth snapshots and deltas with deterministic sequence handling;
- open interest;
- funding / predicted funding where available;
- liquidation events where available;
- basis / spot-perpetual relationship inputs;
- venue/source timestamps, ingestion timestamps and adapter versions.

The objective is to build a proprietary historical dataset instead of depending on
future access to expensive or incomplete third-party microstructure history.

Raw capture and derived metrics must be separable. A derived feature may be rebuilt
from retained raw evidence when the source semantics permit it.

### M2 — Liquidity Intelligence

Research-only first:

- depth imbalance;
- persistent liquidity pools;
- liquidity sweeps;
- replenishment behavior;
- cancellation/appearance dynamics;
- spoofing/ghost-order **candidates**, never claims of proven manipulation;
- iceberg/hidden-liquidity **candidates**, never claims of direct observation.

No inferred hidden order may be presented as certainty.

### M3 — Order Flow & Absorption

Derive and freeze research evidence for:

- aggressive buy/sell flow;
- delta and cumulative volume delta;
- price/flow divergence;
- absorption candidates;
- breakout confirmation/failure;
- price response to executed aggressive flow.

This layer is designed to help distinguish a structurally supported move from a
possible fakeout; it is not an automatic trade command.

### M4 — Derivatives Intelligence

Integrate:

- price × open-interest state;
- funding extremes;
- basis;
- liquidation concentration;
- squeeze / crowding context;
- volatility and leverage-state transitions.

These are context/evidence features. Simple heuristics such as "funding high => short"
must not become unconditional triggers.

### M5 — Smart Money / On-chain & Event Risk

On-chain inputs are context, not deterministic order instructions:

- exchange inflow/outflow anomalies;
- stablecoin flow anomalies;
- large transfer clusters where attribution is supportable;
- wallet-cluster research with explicit attribution and survivorship caveats.

Event Risk is a separate veto/circuit-breaker layer:

- scheduled macro events;
- exchange/security/listing/delisting events where reliable public evidence exists;
- abnormal volatility/spread/depth degradation;
- dynamic WATCH / ABSTAIN / EVENT_BLOCK states.

A fixed ±15 minute window may be an initial research rule, but final blocking policy
should be evidence-driven rather than universally hard-coded.

### M6 — v1 Research Priors, then adaptive weights later

For v1.1 research, begin with an explicit fixed prior matrix inspired by the product
thesis:

- Geometry / Price Action / Elliott / Harmonic: **20%**
- Liquidity Intelligence: **25%**
- Order Flow / Absorption: **25%**
- Derivatives / OI / Funding: **15%**
- On-chain / Smart Money: **15%**

These weights are **research priors**, not probabilities, not promises, and not
automatic production authority. The Event Risk layer remains a veto/context layer
outside this 100-point matrix.

The fixed priors are used first so the system can collect interpretable forward
evidence without premature meta-model complexity. Adaptive weighting is a later
promotion target only after enough chronological live/shadow evidence exists and a
walk-forward meta-model beats the fixed-prior baseline without leakage.

Confluence and probability remain separate:

- **Confluence** = how strongly independent evidence agrees under the current matrix.
- **Calibrated probability** = forward-validated empirical probability for a precisely
  defined outcome event.

A confluence score must never be relabeled as probability.

## 6. R19 — Calibrated probability program

The current `confluence_score` is not a probability and must not be relabeled.

v1.1 adds a real probability pipeline.

### Probability object

A probability shown to the user must carry:

- `probability`;
- event definition;
- horizon;
- asset/timeframe/regime scope;
- calibration model/version;
- training/evaluation cutoff;
- sample size;
- Brier score;
- calibration error;
- reliability status;
- evidence identity.

### Scientific acceptance

- chronological / walk-forward fitting only;
- no future leakage;
- untouched-forward or equivalent held-out evaluation;
- minimum sample count;
- Brier and calibration diagnostics;
- reliability diagram;
- fallback to **not calibrated** if acceptance fails.

Until those gates pass, the UI may show evidence strength/confidence context but
must not fabricate a percent.

## 7. R20 — Forecast Stream and immutable forecast archive

Create a pre-outcome market forecast object.

Each forecast contains:

- immutable `forecast_identity`;
- `issued_at_ms`;
- symbol;
- source timeframe;
- forecast horizon;
- direction;
- expected target zone;
- invalidation level;
- conditional trigger, when relevant;
- ETA window where scientifically supported;
- calibrated probability only when R19 allows it;
- evidence snapshot identities;
- market/regime context;
- plain-language rationale;
- status: OPEN / HIT_TARGET / INVALIDATED / EXPIRED / UNRESOLVED;
- resolution timestamp and scoring metrics.

Examples of acceptable language:

- “BTC 1h: 67,420 üzerindeki kabul edilmiş kırılım korunursa 68,100–68,450
  bölgesi 1–3 saatlik ufukta izleniyor.”
- “67,050 altı kapanış bu tahmini geçersizleştirir.”

The system must never say an exact future path is guaranteed.

Archive must show the original forecast text, issuance time and later outcome
side by side.

## 8. R21 — Canonical Paper Fund + Shadow Lab

The existing immutable write/audit stack is retained, but official track record and
research exploration are intentionally separated.

### Canonical Paper Fund

The canonical 100 USDT fund is the customer-visible official paper track record.

Principles:

- REAL_CAPITAL=0 always;
- no leverage, shorting, borrowing or martingale in the accepted v1.1 canonical lane;
- no forced unconditional BUY merely to deploy cash;
- only the accepted production paper policy may mutate canonical capital;
- every fill retains exact policy, evidence, cost and execution identities;
- fee/spread/slippage simulation remains mandatory;
- cash is a valid position when evidence is insufficient, contradictory or event-blocked;
- canonical history is immutable and never rewritten to improve results.

Initial bounded risk envelope for review:

- starting capital: 100 USDT;
- max single-position notional: 25% NAV;
- max gross exposure: 70% NAV;
- minimum cash reserve: 30% NAV;
- max concurrent positions: 3;
- explicit invalidation required for risk-sized entries;
- no averaging down by default.

These values remain proposed until tested and accepted.

### Shadow Lab

The Shadow Lab learns aggressively **without mutating canonical fund performance**.

It may evaluate:

- 1h / lower-confidence candidate policies;
- WATCH-to-ACTIVE alternatives;
- counterfactual entries and exits;
- with/without liquidity confirmation;
- with/without order-flow confirmation;
- fixed-prior threshold alternatives;
- event-risk filter alternatives;
- timing / horizon variants.

Shadow records are immutable research evidence but are not mixed into canonical
NAV, PnL, win rate, profit factor or customer track record.

A shadow policy may be promoted toward canonical eligibility only after:

1. sufficient chronological sample size;
2. untouched-forward / walk-forward validation;
3. realistic fee/spread/slippage treatment;
4. no future leakage;
5. measurable improvement over the current accepted policy;
6. stability across relevant regimes;
7. explicit promotion review and versioned policy identity.

### Decision-learning contract

The system is required to learn from **every market decision**, not only fills.
Each eligible decision window should resolve to a recorded state such as:

- TRADE
- WATCH
- ABSTAIN
- EVENT_BLOCK
- CONFLICT
- INSUFFICIENT_EVIDENCE

These decision records may later be matched with outcomes so the system can learn
from both actions and deliberate non-actions.

## 9. R22 — Transaction Tape

Every virtual capital mutation must be visible to the user.

For each paper fill show:

- BUY / REDUCE / EXIT;
- exact simulated execution timestamp;
- symbol;
- quantity;
- reference price;
- simulated fill price;
- notional;
- fee;
- spread;
- slippage;
- cash before/after;
- position before/after;
- realized/unrealized PnL where defined;
- source forecast/signal IDs;
- policy version;
- reason;
- immutable record identities.

The UI exposes both an event timeline and a round-trip trade view.

## 10. R23 — Explainable Intelligence

Do not expose private chain-of-thought. Expose **decision evidence**.

For each decision show:

- what each accepted engine observed;
- which observations support or contradict the setup;
- which evidence is fresh/stale/missing;
- research vs production/shadow authority;
- regime/context;
- key levels;
- uncertainty;
- what would change the decision.

Default view is a short explanation. Advanced drill-down exposes engine evidence,
Learning Memory lineage and immutable identities.

## 11. R24 — Customer-grade acceptance

Acceptance includes:

- desktop and responsive UI review;
- keyboard/accessibility review;
- reduced-motion behavior;
- route/state persistence;
- no horizontal/vertical “everything at once” dashboard;
- stale-data simulation;
- SSD detach/remount recovery;
- full hosted tests;
- UID504 tests;
- live Product deployment with rollback;
- post-deploy health and freshness verification;
- paper transaction audit replay;
- forecast archive determinism;
- probability calibration truth checks;
- REAL_CAPITAL=0.

## 12. Release sequencing

v1.0.0 stays immutable.

Recommended progression:

- v1.1-alpha.1 — R15 recovery + R16 shell; begin M1 Market Tape capture in parallel;
- v1.1-alpha.2 — R17/R18 visual/chart system while M2–M4 research features accumulate;
- v1.1-beta.1 — R19/R20 probability + forecast stream; fixed M6 research priors remain explicit;
- v1.1-beta.2 — R21 canonical paper + Shadow Lab + R22 transaction tape;
- v1.1-rc.1 — M5 event-risk integration + R23/R24 explainability/customer acceptance;
- post-v1.1 research — adaptive meta-weighting only after fixed-prior forward evidence is sufficient;
- v1.1.0 — only after exact merged-main + UID504 + live acceptance.

