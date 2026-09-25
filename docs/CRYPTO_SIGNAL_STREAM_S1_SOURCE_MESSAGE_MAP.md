# Crypto Signal — Stream S1 Source-to-Message Map & Engine Classification

Status: **S1 CLOSEOUT EVIDENCE**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
Observed main baseline: `2a61ad47e1f09640f3b36e4ccf09f6ed46dde7ef`

Purpose: decide which accepted backend capabilities may become Stream messages, which remain contextual/evidence-only, and which are research/internal only.

---

## 1. Stream classification vocabulary

- **STREAM_PRIMARY** — may create a customer message when a versioned materiality rule fires and exact source/evidence lineage exists.
- **STREAM_CONTEXT** — may enrich a primary message or create a message only for a material contextual change.
- **EVIDENCE_WINDOW_ONLY** — available for drill-down but should not independently spam the main stream.
- **RESEARCH_ONLY** — visible only in clearly labelled research contexts if later requested.
- **INTERNAL_ONLY** — not part of customer Stream V1.

Classification does not imply that a current message projector already exists.

---

## 2. Core Stream message families

### MARKET / GEOMETRY

Primary sources:
- immutable SignalDecision freeze;
- closed-candle/geometry bundle;
- Forecast trigger/target/invalidation.

Classification:
- STREAM_PRIMARY at issuance/meaningful state transition;
- EVIDENCE_WINDOW_ONLY for detailed chart geometry.

Current source status:
- live/persisted signal truth exists;
- rich geometry-change projector does not yet exist.

### LIQUIDITY

Primary sources:
- Market Tape order book;
- liquidity dynamics/structure;
- sweep engine;
- accepted liquidation evidence when exact evidence exists.

Classification:
- STREAM_PRIMARY for material sweep/liquidity-state changes;
- EVIDENCE_WINDOW_ONLY for full book/heatmap detail.

Current source status:
- order-book path is live/persisted;
- liquidation production WebSocket is explicitly disabled;
- historical/bounded liquidation evidence may be used only when exact persisted coverage exists.

Do not publish “live liquidation feed” messages until a continuous source is explicitly activated/accepted.

### ORDER FLOW / ABSORPTION

Primary sources:
- Market Tape public trades + order book;
- temporal delta/CVD;
- divergence;
- absorption;
- breakout/failure interaction.

Classification:
- STREAM_PRIMARY for material evidence changes;
- EVIDENCE_WINDOW_ONLY for series/measurement detail.

Current source status:
- trade/order-book source path exists;
- message projector absent.

### DERIVATIVES

Primary sources:
- Bybit derivatives snapshot path;
- OI/funding/basis/crowding/dynamics.

Classification:
- STREAM_PRIMARY when derivatives materially alter the decision context;
- EVIDENCE_WINDOW_ONLY for raw metric detail.

Current source status:
- live snapshot/persistence path established;
- customer message projector absent.

### ON-CHAIN / SMART MONEY

This family must be split by sub-source.

#### Bitcoin network activity

Source:
- Blockstream Esplora public Bitcoin mainnet adapter.

Accepted status:
- real public source-quality gate passed;
- deterministic on-chain/network freeze exists;
- engine remains observation-only;
- no Product deployment/always-on Stream collector is established.

Classification:
- STREAM_CONTEXT **once** a current persisted runtime collection path is added;
- EVIDENCE_WINDOW_ONLY before that.

#### Exchange Flow

Accepted status:
- provider-neutral engine/observation contract exists;
- no live provider/API/credential collector activated.

Classification:
- RESEARCH_ONLY / EVIDENCE_WINDOW_ONLY from explicitly supplied persisted evidence;
- not a current live Stream source.

#### Wallet Cohorts

Accepted status:
- PIT admission + forward measurement contract exists;
- no live wallet provider activated.

Classification:
- RESEARCH_ONLY.

#### Large Transfer Clusters

Accepted status:
- provider-neutral bounded transfer clustering exists;
- no live provider activated.

Classification:
- RESEARCH_ONLY / EVIDENCE_WINDOW_ONLY if exact externally supplied evidence exists.

### EVENT RISK

Sources:
- accepted event calendar/news sources;
- Event Source runtime/persistence;
- Event Risk circuit breaker.

Classification:
- STREAM_PRIMARY for material approach/block/recovery;
- STREAM_CONTEXT for non-material background.

Current source status:
- current source/persistence path exists;
- projector absent.

### DECISION

Sources:
- M6 snapshot;
- Forecast;
- Decision Proof;
- actionability state.

Classification:
- STREAM_PRIMARY.

Material examples:
- new forecast;
- stance changed;
- score band changed;
- conflict appeared/disappeared;
- trigger met;
- invalidation occurred.

Current source status:
- issuance/resolution feed exists;
- rich story/change/score-breakdown persistence/projector absent.

### CAPITAL

Sources:
- Smart Capital Allocator;
- Position Sizing;
- R22 intent/fill;
- R21 accounting.

Classification:
- STREAM_PRIMARY.

Material examples:
- HOLD reason changed materially;
- ELIGIBLE;
- sizing available/blocked;
- simulated execution;
- reduce;
- exit;
- accounting/outcome update.

Current source status:
- component contracts/persistence exist;
- one canonical three-vault forward runtime and customer projector do not yet exist.

### OUTCOME

Sources:
- Forecast Resolution;
- R22 fill/accounting outcome evidence.

Classification:
- STREAM_PRIMARY.

Current source status:
- Forecast resolution is already persisted/projected in the old feed;
- capital outcome Stream projection absent.

### SYSTEM / DATA QUALITY

Sources:
- Market Tape runtime status;
- Provider Divergence;
- Event Source runtime status;
- Cold Archive status;
- operational truth.

Classification:
- STREAM_PRIMARY only for decision-relevant degradation/recovery;
- INTERNAL_ONLY for routine low-level operational chatter.

---

## 3. Secondary accepted intelligence engines

Current Product Intelligence Center catalog marks all entries `accepted_research_only` and `not_exposed_as_live_feed`.

Stream V1 classification:

| Engine ID | Stream classification | Rationale |
|---|---|---|
| regime | STREAM_CONTEXT | useful for explaining why the same setup is treated differently across regimes |
| trend_momentum | STREAM_CONTEXT | supports/contradicts directional context but should not create constant standalone chatter |
| mean_reversion | STREAM_CONTEXT | useful contradiction/overextension context |
| breakout_volatility | STREAM_CONTEXT | useful around trigger/breakout material events |
| derivatives | STREAM_PRIMARY / EVIDENCE_WINDOW_ONLY | part of five-family decision evidence |
| order_flow | STREAM_PRIMARY / EVIDENCE_WINDOW_ONLY | part of five-family decision evidence |
| onchain | STREAM_CONTEXT / EVIDENCE_WINDOW_ONLY until runtime collection exists | accepted network engine but no always-on customer source |
| sentiment_attention | STREAM_CONTEXT | context only; public-source engine is observation-only |
| cross_market | STREAM_CONTEXT | macro/cross-market context, not primary signal spam |
| meta_intelligence_shadow | EVIDENCE_WINDOW_ONLY | useful analytical research context; zero production contribution |
| alpha_symbolic | RESEARCH_ONLY | Alpha Factory research |
| alpha_tree | RESEARCH_ONLY | Alpha Factory research |
| alpha_cluster | RESEARCH_ONLY | Alpha Factory research |
| alpha_interactions | RESEARCH_ONLY | Alpha Factory research |
| alpha_evolution | RESEARCH_ONLY | Alpha Factory research |
| ml_baseline | RESEARCH_ONLY | bounded ML research |
| ml_walk_forward | RESEARCH_ONLY | bounded ML research |
| ml_family_cost_stress | RESEARCH_ONLY | bounded ML research |
| ml_family_robustness | RESEARCH_ONLY | bounded ML research |
| ml_untouched_forward | RESEARCH_ONLY | bounded ML research |
| ml_promotion_dossier | RESEARCH_ONLY | promotion dossier is research governance, not customer live chatter |
| learning_memory | INTERNAL_ONLY for V1 | research memory store should not become a customer message source in Stream V1 |

This table is a product-surface classification only. It does not change any backend authority or scientific semantics.

---

## 4. Existing source-to-message mapping

| Stream category | Current canonical source | Current persisted? | Current message projector? | S2/S11 action |
|---|---|---:|---:|---|
| Forecast issued | Decision Ledger R20/R20.5 | YES | YES, old feed | adapt into rich Stream source event |
| Forecast resolved | Decision Ledger resolution/feed | YES | YES, old feed | adapt into OUTCOME story event |
| Geometry/trigger | Signal freeze + Forecast | YES | PARTIAL | add material-change/expanded projection |
| M6 score aggregate | Forecast/Proof | YES | PARTIAL | persist full decision context for family details |
| M6 family breakdown | UnifiedDecisionIssuance.confluence | NO in Decision Ledger | NO | add immutable decision-context persistence |
| Liquidity/order book | Market Tape + family evidence | YES/PARTIAL | NO | identity lookup + material projector |
| Liquidation | bounded persisted evidence only | PARTIAL; no continuous prod collector | NO | remain availability-gated |
| Order flow/CVD | Market Tape + accepted engines | YES/PARTIAL | NO | evidence lookup + material projector |
| Derivatives | Market Tape derivatives | YES | NO | evidence lookup + material projector |
| Bitcoin network | Blockstream adapter/engine | not established as always-on Stream store | NO | add runtime persistence before live messages |
| Exchange Flow | provider-neutral contract | no live provider | NO | research/evidence only until provider activation |
| Wallet Cohort | provider-neutral registry | no live provider | NO | research only |
| Large Transfer | provider-neutral contract | no live provider | NO | research/evidence only |
| Event Risk | Event Source + circuit breaker | YES | NO | projector for approach/block/recovery |
| Provider degradation | status runtimes | YES | NO | material SYSTEM projector |
| Epoch2 current state | R21 ledger | YES | NO | capital state projector/read model |
| R22 intents/fills/bundles | R22 atomic tape | YES when canonical writer used | NO | capital detail read model/projector |
| Capital Science assessment | runtime object | not fully persisted | NO | persist decision-capital context |
| Position Sizing assessment | runtime object | not fully persisted | NO | persist sizing context |
| Shadow R22 preview | shadow intent journal | YES | NO | optional research lineage; canonical capital message must not confuse shadow with Epoch2 mutation |

---

## 5. Materiality principles for S2/S4

Stream V1 should not publish one message per market tick.

Candidate material events:

- decision/stance transition;
- score crosses a configured message band;
- a family changes support/oppose/abstain/evidence state;
- material independent conflict appears/disappears;
- trigger becomes satisfied;
- invalidation occurs;
- Event Risk changes to/from a blocking state;
- major data-quality degradation/recovery;
- vault changes HOLD/BLOCK/ELIGIBLE/SIZED/EXECUTED/REDUCED/EXITED;
- forecast/trade outcome matures.

Routine source updates remain silent state unless a versioned summary policy chooses to publish them.

Exact numeric thresholds/bands belong to S2/S4 contracts and must be versioned.

---

## 6. S1 resolved discovery results

### Liquidation
Resolved:
- collector implementation exists;
- production continuous collector is explicitly disabled;
- no production WebSocket activation occurred;
- Stream must not claim continuous liquidation truth today.

### On-chain / Smart Money
Resolved:
- Bitcoin network has a real accepted public Blockstream source and deterministic engine;
- it is observation-only and not established as an always-on Product/Stream runtime;
- Exchange Flow, Wallet Cohort and Large Transfer are provider-neutral research contracts with no live provider activation.

### Secondary engines
Resolved:
- table in section 3 defines Stream vs context vs research/internal scope.

### Source-to-message plan
Resolved at discovery level:
- section 4 identifies canonical source and missing projection for each required Stream category.

These items are no longer open DISCOVER questions. Their implementation gaps remain tracked separately.
