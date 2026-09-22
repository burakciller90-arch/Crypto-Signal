# CRYPTO SIGNAL — FULL VERSION / WORLD-CLASS ROADMAP

> **Post-v1.0 notice (2026-09-22):** This document is retained as accepted historical/product context for v1.0. New v1.1+ execution is governed by `docs/V1_1_MASTER_EXECUTION_ROADMAP.md`. Do not use an older stage order here to override the current R15 -> parallel UI/Market Tape -> Decision Proof/Forecast -> Canonical Fund/Shadow Lab program.


Status: governing full-version execution roadmap.
Created: 2026-09-20.
Product goal: deliver a Turkish-first, explainable, evidence-driven crypto intelligence platform as a meaningful gift.
Hard invariant: REAL_CAPITAL=0. No real exchange order path is authorized by this roadmap.

## Governing product thesis

Crypto Signal is not a BUY/SELL toy and is not a promise of guaranteed profit.
The target is a professional quantitative intelligence platform that:
- observes the market continuously,
- explains what it sees in plain Turkish,
- shows chart evidence,
- manages a fully virtual paper portfolio,
- measures its own decisions honestly,
- learns which methods work in which regimes,
- researches new strategies in isolation,
- promotes new ideas only after strong out-of-sample and forward evidence.

"World-class" means scientific integrity, clarity, reliability, disciplined experimentation and a premium user experience — not feature count or unsupported certainty.

## Non-negotiable scientific rules

1. REAL_CAPITAL=0 until a separate future authority gate explicitly changes it.
2. No future leakage; point-in-time truth only.
3. Closed-candle truth for decisions. Live prices may animate UI but cannot rewrite decision history.
4. Frozen evidence is immutable. Losses are never deleted.
5. Missing data is never invented.
6. Agreement index is not probability.
7. Historical frequency is not calibrated probability.
8. Backtest is not untouched-forward evidence.
9. LLM prose may explain deterministic evidence but may not invent numeric market truth.
10. No newly discovered strategy can directly replace the champion. It must pass the Research Lab gate.

## Architecture destination

MARKET DATA
  -> independent analysis engines
  -> regime engine
  -> meta-decision engine
  -> risk engine
  -> $100 autonomous paper fund
  -> immutable execution/outcome ledger
  -> performance & calibration lab
  -> learning engine
  -> Alpha Factory / challenger research
  -> gated promotion to champion

The UI sits above this stack and must explain each step without exposing unnecessary engineering complexity.

## Independent analysis engine family

The full version may use multiple independent engines. They must remain separately testable and must not create fake agreement by repeating the same underlying signal.

### A. Price Action / Market Structure
Swings, trend structure, BOS, CHoCH, support/resistance, liquidity pools/sweeps, FVG/BPR and price interactions.

### B. SMC / ICT
Order blocks, displacement, imbalance, liquidity concepts, premium/discount and other bounded deterministic structures.

### C. Elliott Wave
Multiple competing structural counts, hard-rule validity, invalidation and ambiguity. Never claim one subjective count is certain.

### D. Harmonic
Algorithmic XABCD detection, Fibonacci-ratio validation, PRZ, invalidation and target geometry.

### E. Trend / Momentum
Trend persistence, rate-of-change and momentum evidence. Must be distinct from duplicated indicator voting.

### F. Mean Reversion
Tests whether price has moved unusually far from a regime-appropriate reference and whether reversion evidence exists.

### G. Breakout / Volatility Expansion
Compression, range escape, volatility expansion and follow-through conditions.

### H. Order Flow / Market Microstructure
Later bounded expansion: bid/ask spread, depth, imbalance, aggressor flow and liquidity quality where reliable data contracts exist.

### I. Derivatives / Leverage Context
Funding, open interest, basis and liquidation context when source quality is sufficient.

### J. On-chain / Network Context
Network activity and other blockchain-native factors only after source contracts are reliable and reproducible.

### K. Sentiment / Attention
Optional bounded context. Never allowed to dominate deterministic market truth by itself.

### L. Cross-market / Macro Context
Optional context such as broad risk regime where evidence quality is sufficient.

## Regime Engine

Before weighting methods, classify the market environment deterministically when possible:
- trending,
- ranging,
- high volatility,
- low volatility/compression,
- disorder/panic,
- liquidity-stressed,
- insufficient evidence.

The same methodology does not receive the same weight in every regime.

## Meta-Decision Engine

The meta engine combines independent evidence without pretending that vote count equals probability.
It must:
- detect correlated/duplicate evidence,
- preserve contradictions,
- preserve unresolved methodologies,
- expose which engines influenced the decision,
- expose which engines argued against it,
- allow "do nothing / stay in cash" as a valid outcome.

## Risk Engine

A correct direction with poor risk is still a bad trade.
The risk engine controls the virtual paper fund:
- maximum virtual exposure,
- position size,
- concentration,
- invalidation-based risk,
- cash reserve,
- spread/slippage/fee budget,
- cooldown / overtrading protection,
- no-trade conditions.

No martingale, loss-chasing or hidden leverage.

## Stage 6A — Live Mission Control + Auto Refresh

Goal: eliminate manual F5 and make the product feel alive without weakening closed-candle truth.

Deliver:
- automatic UI refresh using SSE/WebSocket or a safe bounded polling fallback,
- visible "Canlı / son güncelleme / bağlantı durumu",
- stale-data detection,
- no duplicated event listeners or UI state loss,
- preserve selected asset/timeframe/provider while refreshing,
- continue conservative ACTIVE / INVALIDATED alert semantics.

Exit:
- user can leave the page open and see new evidence appear automatically,
- stale connection is obvious,
- no manual F5 required.

## Stage 6B — Evidence Center + "Bana Öğret"

Goal: a person with zero crypto knowledge can understand each signal.

Deliver for each signal:
- plain-Turkish "Sistem ne görüyor?",
- "Neden önemli?",
- "Neden şimdi?",
- "Neden işlem yapmamalıyız?" counter-case,
- "Bu fikir ne zaman bozulur?" invalidation,
- methodology-by-methodology explanation,
- graph overlays tied only to frozen evidence,
- clickable mini-lessons for BOS, CHoCH, FVG, liquidity sweep, Elliott, Harmonic, risk/reward and other concepts,
- beginner vs advanced explanation depth.

Exit:
- every major decision is teachable and visually auditable.

## Stage 6C — $100 Autonomous Paper Fund

Initial virtual capital: exactly 100 USDT.
This is simulation only. REAL_CAPITAL remains 0.

The fund may allocate between:
- virtual cash,
- BTC,
- ETH,
- SOL,
with expansion only after evidence.

Every virtual action must record:
- decision identity,
- timestamp,
- venue/reference market,
- side,
- quantity,
- reference price,
- simulated fill price,
- fee,
- spread/slippage assumption,
- resulting cash,
- resulting holdings,
- reason,
- invalidation/risk context.

Valid actions:
- HOLD CASH,
- BUY,
- REDUCE,
- EXIT.

No forced trading. Cash is a valid professional position.

Execution realism:
- venue trading rules,
- minimum notional/step size,
- fees,
- spread,
- slippage,
- deterministic fill policy,
- partial-fill semantics if introduced,
must be explicit and versioned.

Benchmarks from the same start time:
- 100 USDT cash,
- 100 USDT BTC buy-and-hold,
- BTC/ETH/SOL equal-weight,
plus optional later benchmarks.

Exit:
- paper NAV can be reconstructed exactly from immutable records,
- every trade is explainable,
- net performance includes simulated costs.

## Stage 7 — Honest Performance & Calibration Lab

Report:
- net return,
- benchmark-relative return,
- max drawdown,
- turnover,
- fees/slippage cost,
- win rate only when meaningful,
- expectancy,
- profit factor,
- average/median R where valid,
- exposure,
- cash time,
- asset/timeframe/regime/method segmentation.

Never hide losing trades.
Never merge RETROSPECTIVE, WALK_FORWARD and LIVE_UNTOUCHED_FORWARD evidence.

Probability:
- do not display calibrated probabilities until sample size and calibration design are accepted,
- later evaluate reliability/Brier/calibration by evidence class and regime,
- until then show agreement/evidence strength, not probability.

## Stage 8 — Multi-Method Intelligence Expansion

Add new engines one at a time behind isolated acceptance gates:
1. deterministic regime labeling,
2. trend/momentum,
3. mean reversion,
4. breakout/volatility,
5. bounded derivatives context,
6. order-flow/microstructure if data quality supports it,
7. on-chain/network,
8. bounded sentiment/attention,
9. cross-market context.

Each engine needs:
- deterministic source contract,
- PIT safety,
- frozen evidence,
- independent tests,
- contribution/ablation evidence,
- explicit uncertainty.

Do not add an engine merely to increase feature count.

## Stage 8.5 — Alpha Factory / Strategy Evolution Lab

Purpose: allow the platform to discover strategies we did not manually encode while preventing uncontrolled self-modification.

Research candidates may use:
- symbolic rule discovery,
- tree-based models,
- clustering/regime discovery,
- feature interaction search,
- genetic/evolutionary search,
- later carefully bounded ML/RL research.

Champion/challenger model:
- production/paper champion remains stable,
- challengers live in isolated research worktrees/data partitions,
- challengers cannot deploy themselves,
- every challenger must pass leakage checks, transaction-cost stress, walk-forward, out-of-sample and untouched-forward paper evaluation,
- multiple-testing/backtest-overfitting controls are mandatory,
- promotion requires explicit recorded acceptance evidence.

The system may generate hypotheses. It may not declare itself correct.

## Stage 8.75 — Learning Memory

Maintain an interpretable knowledge layer:
- which method contributed value,
- under which asset/timeframe/regime,
- when it failed,
- whether an engine is redundant with another,
- what uncertainty preceded failures,
- what changed after model/version updates.

Learning must be versioned and reproducible. It may inform future weighting only through a tested policy.

## Stage 9 — Full Gift Edition UX

The friend should not need crypto knowledge.

Primary product surfaces:
- Piyasa Özeti,
- Piyasa Radarı,
- Varlık Merkezi,
- Sinyal Detayı,
- Grafik Kanıtları,
- Bana Öğret,
- Sanal Portföy,
- İşlem Planı,
- Performans Laboratuvarı,
- Uyarılar,
- Sinyal/İşlem Arşivi,
- Sistem Sağlığı.

A virtual purchase plan must explain:
- what the system wants to do,
- exact virtual amount,
- expected fee/spread/slippage,
- remaining cash,
- portfolio exposure,
- invalidation,
- why now,
- why not,
- what evidence could change the decision.

Complexity belongs behind progressive disclosure. The first screen must remain simple.

## Stage 10 — Full Integrated Acceptance

Before calling the gift complete:
- full repository gate PASS,
- stable runtime deployments,
- restart/recovery tests,
- auto-refresh endurance test,
- stale-data test,
- paper-ledger reconstruction test,
- fee/slippage determinism test,
- no-leakage checks,
- UI beginner usability pass,
- explanation/evidence consistency tests,
- benchmark comparison correctness,
- Research Lab isolation,
- REAL_CAPITAL=0 verification,
- no exchange order endpoint/credential authority exposed.

The result is tagged only after these gates pass.

## Parallel development policy

Cursor is an acceleration worker, not a dependency.
- Supervisor may develop directly while Cursor works on an isolated non-overlapping slice.
- Cursor work uses isolated worktrees.
- Worker output is evidence only.
- Supervisor reviews diff/tests/state before integration.
- A slow or failed worker must not block unrelated canonical work.
- No two workers edit the same bounded slice concurrently.
- Stale/duplicate completion wakes are NOOP and never replay old work.

## Scope discipline

We are building the full version, but not by adding uncontrolled breadth.
Every feature must improve at least one of:
- truth,
- decision quality,
- risk control,
- learning quality,
- monitoring burden,
- beginner clarity,
- gift-quality experience.

Anything else is deferred.

## Immediate canonical execution order

1. Stage 6A: automatic live refresh + connection/stale state.
2. Stage 6B: beginner Evidence Center / "Bana Öğret" foundation.
3. Stage 6C: immutable $100 paper-fund domain and ledger.
4. Stage 7: paper performance + benchmarks.
5. Stage 8: new analysis engines incrementally.
6. Stage 8.5/8.75: Alpha Factory + learning memory.
7. Stage 9/10: full gift UX and integrated acceptance.

Do not skip scientific gates to move faster. Move faster by parallelizing independent slices, not by weakening evidence.


## Full Version completion record — 2026-09-22

The implementation and integrated-acceptance roadmap is mechanically complete
through R13.

Canonical R13 accepted main:
`f95efc358ac396e50d0bfdb920b0187706cd2af2`.

Canonical R13 evidence:
issue #704 / run `35672790463`, result PASS.

The final release/documentation frontier is R14. Its reserved immutable release
identity is `crypto-signal-full-version-v1.0.0`. Full Version v1.0.0 becomes
final only when the R14 release-freeze workflow re-verifies exact UID504
Development state, Product-code parity, live read-only safety, paused continuity
and the release-documentation contract, then binds that tag to the exact current
main commit.

Intentional boundaries remain closed:
- REAL_CAPITAL=0;
- no exchange-order or credential authority;
- paper policy may remain NOT_ACTIVATED;
- research/meta production contribution remains 0;
- calibrated probability is not claimed;
- model/challenger promotion remains gated;
- physical reboot/logout/SSD detach-remount remain human-impact UNTESTED items.
