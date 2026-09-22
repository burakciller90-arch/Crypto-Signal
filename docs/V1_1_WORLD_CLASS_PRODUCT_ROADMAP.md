# Crypto Signal v1.1 — World-Class Product & Active Learning Roadmap

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

## 8. R21 — Paper Active Learning Mode

The existing write/audit stack is retained. The objective is to produce more
decision/outcome evidence without turning weak evidence into fake certainty.

### Modes

- **Conservative** — accepted v1.0 behavior.
- **Active Learning** — higher paper participation within bounded simulation risk.
- **Stress Lab** — synthetic/replay only; never mixed with live-paper PnL.

### Active Learning principles

- REAL_CAPITAL=0 always;
- no leverage, shorting, borrowing or martingale;
- no forced unconditional BUY merely to spend cash;
- a bounded exploration lane may deliberately test uncertain but eligible setups;
- exploration trades are explicitly tagged `EXPLORATION`;
- exploitation trades are tagged `POLICY`;
- every action carries the exact policy version and evidence identity.

Initial bounded target for review:

- starting capital: 100 USDT;
- max single-position notional: 25% NAV;
- max gross exposure: 70% NAV;
- minimum cash reserve: 30% NAV;
- max concurrent positions: 3;
- explicit invalidation required for risk-sized entries;
- no averaging down by default;
- fee/spread/slippage simulation remains mandatory.

These values are a proposed v1.1 research policy and require tests before
acceptance.

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

- v1.1-alpha.1 — R15/R16 recovery + shell;
- v1.1-alpha.2 — R17/R18 visual/chart system;
- v1.1-beta.1 — R19/R20 probability + forecast stream;
- v1.1-beta.2 — R21/R22 active paper + transaction tape;
- v1.1-rc.1 — R23/R24 explainability + customer acceptance;
- v1.1.0 — only after exact merged-main + UID504 + live acceptance.

