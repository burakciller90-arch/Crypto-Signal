# Crypto Signal — Final F0 Source-to-Message Closure Ledger

Status: **CANONICAL F0 MECHANICAL INVENTORY**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F0 — Authority + Gap Reconciliation**  
Date: 2026-09-26  
Safety: **REAL_CAPITAL=0**

---

## 1. Purpose

This ledger replaces vague words such as “supported”, “implemented” or “accepted” with one exact production question:

> Can this source family create a genuine forward customer Stream message on the current 24/7 production path?

Every family is traced through:

**ENGINE → LIVE SOURCE → PERSISTED EVIDENCE → PRODUCT PROJECTION → MESSAGE PROJECTOR → LIVE RUNTIME HOOK**

Allowed final status values:

- `LIVE_COMPLETE`
- `CODE_EXISTS_NOT_LIVE`
- `PERSISTED_SOURCE_ONLY`
- `NO_LIVE_SOURCE`
- `RESEARCH_ONLY`
- `EXTERNAL_DEPENDENCY`
- `BLOCKED_BY_CORRECTNESS_DEFECT`

Historical S0-S16 acceptance remains valid for the component/scenario it actually proved. It is not used as proof that a source family is live.

---

## 2. Runtime paths proven by current code/state

Current production SSD paths relevant to this ledger:

- Signal ledger:  
  `Development/runtime/ledger/live_signal_ledger.sqlite3`
- Market Tape:  
  `Development/runtime/market_tape/market_tape.sqlite3`
- Raw Market Tape:  
  `Development/runtime/market_tape/raw_market_tape.sqlite3`
- Provider divergence:  
  `Development/runtime/data/provider_divergence.sqlite3`
- Event Source:  
  `Development/runtime/events/event_source.sqlite3`
- Epoch 2 canonical paper state:  
  `Development/runtime/paper/paper_fund_epoch2.sqlite3`
- Stream ledger:  
  `Development/runtime/stream/intelligence_stream.sqlite3`
- WC2 prepared journal:  
  `Development/runtime/wc2/wc2.wc2-prepared.sqlite3`
- WC2 decision evidence: configured by the live evidence clock through `--wc2-decision-evidence`
- WC2 cohort: configured by the live evidence clock through `--wc2-cohort`
- WC2 execution runtime/journal: configured by the live evidence clock through the accepted WC2 execution arguments.

Current Stream production caller:

- `ops/run_live_evidence_clock.py`
- `IntelligenceStreamForwardRuntime.project_issuance`
- `IntelligenceStreamForwardRuntime.project_resolution`

No other source-family Stream caller is present in that live loop.

---

# 3. Final production matrix

| Family | Engine | Live source | Persisted evidence | Product projection | Message projector | Live runtime hook | F0 status |
|---|---|---|---|---|---|---|---|
| Market / Geometry | YES | YES | YES | PARTIAL/YES | registry intent only; no rich production projector | NO | **PERSISTED_SOURCE_ONLY** |
| Liquidity | YES | PARTIAL/YES | YES/PARTIAL | PARTIAL | no production material-change projector | NO | **PERSISTED_SOURCE_ONLY** |
| Order Flow / CVD / Absorption | YES | YES | YES/PARTIAL | PARTIAL | no production material-change projector | NO | **PERSISTED_SOURCE_ONLY** |
| Derivatives | YES | YES | YES | PARTIAL | no production material-change projector | NO | **PERSISTED_SOURCE_ONLY** |
| Bitcoin network | YES | real public source exists | no accepted always-on Stream runtime/persistence | PARTIAL/research context | deferred | NO | **NO_LIVE_SOURCE** |
| Exchange Flow / Wallet Cohort / Large Transfer | contracts/engines exist | NO accepted provider | NO live collection | research only | research only | NO | **RESEARCH_ONLY** |
| Liquidation context | YES | bounded collector exists; continuous production disabled | persisted when collected | PARTIAL | no live material projector | NO | **NO_LIVE_SOURCE** |
| Event Risk | YES | YES for accepted calendar/news sources | YES | PARTIAL | registry intent only; no live projector | NO | **PERSISTED_SOURCE_ONLY** |
| Decision issuance | YES | YES | YES | YES | YES | YES | **LIVE_COMPLETE** |
| Forecast outcome/resolution | YES | YES | YES | YES | YES | YES | **LIVE_COMPLETE** |
| Capital lifecycle | YES | canonical S11 runtime/projector code exists | YES when R21/R22 canonical mutation exists | YES in projector/read-model code | YES | no production caller proven | **CODE_EXISTS_NOT_LIVE** |
| Provider/Data Quality/System | YES | YES | YES | YES/PARTIAL | registry intent only; no live projector | NO | **PERSISTED_SOURCE_ONLY** |

---

# 4. Market / Geometry

## Engine

Canonical signal/geometry truth is frozen by the accepted signal pipeline.

Relevant source code:

- `src/crypto_signal/ledger/store.py`
- signal/geometry bundle creation used by the live freeze path.

## Live source

The live evidence clock continuously freezes configured Binance/Bybit contexts.

## Persisted evidence

Database:

`Development/runtime/ledger/live_signal_ledger.sqlite3`

Tables:

- `signal_freezes`
- `lifecycle_evaluations`
- `outcome_evaluations`

Primary source identities:

- `signal_freeze_identity`
- `bundle_identity`
- lifecycle `evaluation_identity`
- outcome `outcome_identity`

The immutable freeze bundle contains the consumed point-in-time candle/decision context.

## Product projection

Existing product proof can resolve exact forecast-bound frozen OHLC/geometry from immutable signal/Decision Proof lineage.

## Message projector

Registry entry:

- `market_geometry_change`
- category: `MARKET`
- intended subtypes:
  - `geometry_material_change`
  - `trigger_transition`

Current registry state:

`REQUIRES_CHANGE_DETECTION`

There is no production source-specific projector function equivalent to the implemented forecast projector.

## Live runtime hook

None in `ops/run_live_evidence_clock.py`.

## Final status

**PERSISTED_SOURCE_ONLY**

## Required closure

F2/F3 must add exact forward-only material geometry projection that enters the existing Story → Analytical → Narrative chain without creating one message per candle.

## Acceptance

A genuine forward geometry/trigger material transition produces one immutable MARKET message; replay produces no duplicate; non-material freezes remain silent.

---

# 5. Liquidity

## Engine / source

Accepted liquidity engines and Market Tape order-book evidence exist.

Relevant code/source:

- liquidity engines from the accepted intelligence layer;
- `src/crypto_signal/data/market_tape.py`
- Decision Proof liquidity/order-book domains.

## Persisted evidence

Database:

`Development/runtime/market_tape/market_tape.sqlite3`

Relevant tables:

- `market_tape_orderbooks`
- `market_tape_liquidations` when liquidation collection exists
- `market_tape_liquidation_coverage`

Key identities:

- `snapshot_identity`
- `liquidation_identity`
- `coverage_identity`

## Product projection

Current product layers expose decision-proof evidence status/identity and bounded frozen proof for supported geometry, but no universal exact customer resolver for all liquidity/order-book objects exists.

## Message projector

Registry entry:

- `liquidity_change`
- category: `INTELLIGENCE`
- subtype: `liquidity_material_change`

Current registry state:

`REQUIRES_CHANGE_DETECTION`

No source-specific production projector exists.

## Live runtime hook

None.

## Final status

**PERSISTED_SOURCE_ONLY**

Separate liquidation-live status:

**NO_LIVE_SOURCE** for continuous liquidation chatter because continuous production collection is explicitly disabled.

## Required closure

F3:
- exact material liquidity transition projector from persisted forward truth;
- no synthetic sweep semantics;
- liquidation messages only if a separately accepted live collector exists.

F6:
- exact order-book/liquidity evidence resolver by identity.

## Acceptance

One genuine material liquidity event reaches the Stream through the canonical pipeline and opens exact/fail-closed frozen evidence.

---

# 6. Order Flow / CVD / Absorption

## Engine / source

Accepted order-flow engines consume real Market Tape trades/order book.

## Persisted evidence

Market Tape tables:

- `market_tape_trades`
- `market_tape_orderbooks`

Key identities:

- `trade_identity`
- `snapshot_identity`

Decision Proof may bind accepted Order Flow evidence identities.

## Product projection

Partial: evidence identity/verdict exists in Decision/Proof context, but there is no universal frozen customer graph/series resolver for all CVD/divergence/absorption truth.

## Message projector

Registry entry:

- `order_flow_change`
- category: `INTELLIGENCE`
- subtype: `order_flow_material_change`
- state: `REQUIRES_CHANGE_DETECTION`

No live projector implementation/caller exists.

## Live runtime hook

None.

## Final status

**PERSISTED_SOURCE_ONLY**

## Required closure

F3:
- derive exact forward change truth from accepted persisted/runtime evidence;
- publish only material support/opposition/divergence/absorption transitions.

F6:
- exact frozen CVD/measurement/evidence projection.

## Acceptance

A real forward order-flow state change produces one story-aware message and exact/fail-closed proof.

---

# 7. Derivatives

## Engine / source

Accepted Bybit derivatives adapter and derivatives intelligence engines are present.

The Market Tape production stack stores derivatives observations.

## Persisted evidence

Database:

`Development/runtime/market_tape/market_tape.sqlite3`

Table:

- `market_tape_derivatives`

Identities:

- `observation_identity`
- `semantic_identity`

## Product projection

Partial: Decision Proof can bind derivatives evidence; dedicated rich historical metric resolver is incomplete.

## Message projector

Registry:

- `derivatives_change`
- category: `INTELLIGENCE`
- subtype: `derivatives_material_change`
- state: `REQUIRES_CHANGE_DETECTION`

No production implementation/caller exists.

## Live runtime hook

None.

## Final status

**PERSISTED_SOURCE_ONLY**

## Required closure

F3:
- material OI/funding/basis/crowding transition projection.

F6:
- exact persisted snapshot resolver.

## Acceptance

A genuine derivatives context transition produces an immutable Stream message and exact snapshot evidence.

---

# 8. On-chain / Smart Money

This family must remain split by actual source availability.

## 8.1 Bitcoin network

Engine and a real accepted Blockstream public source exist.

The S1 audit explicitly found no always-on Stream collection/persistence path.

Registry entry:

- `bitcoin_network_context`
- state: `DEFERRED_SOURCE`

### Final status

**NO_LIVE_SOURCE**

### Closure rule

Do not activate customer chatter until an accepted always-on forward persistence path exists.

Decision messages may expose an already frozen exact on-chain contribution if it exists in their immutable decision context.

## 8.2 Exchange Flow / Wallet Cohort / Large Transfer

Provider-neutral contracts/engines exist, but no accepted live provider activation exists.

Registry:

- `m5_smart_money_research`
- state: `RESEARCH_ONLY`

### Final status

**RESEARCH_ONLY**

### Closure rule

Do not invent live data and do not make F8 wait on a source that the product explicitly classifies unavailable.

A later provider activation would be new source work, not permission to fabricate current Stream events.

---

# 9. Liquidation context

The bounded liquidation collector and Market Tape persistence contracts exist.

Production continuous collection remains disabled by accepted authority.

Tables when evidence exists:

- `market_tape_liquidations`
- `market_tape_liquidation_coverage`

Identities:

- `liquidation_identity`
- `coverage_identity`

## Final status

**NO_LIVE_SOURCE**

## Closure rule

Exact persisted liquidation evidence may support a message/proof when already available.

Continuous liquidation Stream messages require a separately accepted live collector. They are not fabricated to complete F3.

---

# 10. Event Risk

## Engine / live source

Accepted calendar/news source runtime exists.

Default canonical runtime path:

`Development/runtime/events/event_source.sqlite3`

Collector:

- `ops/run_event_source_snapshot.py`

## Persisted evidence

Required Event Source tables:

- `event_source_runtime_meta`
- `event_source_raw_payloads`
- `event_calendar_coverages`
- `structured_event_observations`
- `news_event_observations`
- `event_source_fetches`

Primary identities:

- calendar `coverage_identity`
- structured event `event_identity`
- news `news_identity`
- fetch `fetch_identity`

Product Truth intentionally reports `PERSISTED_EVIDENCE_ONLY`; it does not claim process ONLINE from persisted evidence.

## Product projection

Event Risk identity/state already participates in accepted Decision/Analytical context.

## Message projector

Registry:

- `event_risk_change`
- category: `RISK`
- subtypes:
  - `event_risk_block`
  - `event_risk_change`
  - `event_risk_recovery`
- state: `REQUIRES_CHANGE_DETECTION`

No dedicated live source projector/caller exists.

## Live runtime hook

None in the Stream production loop.

## Final status

**PERSISTED_SOURCE_ONLY**

## Required closure

F4:
- exact persisted forward Event Risk transition projector;
- no synthetic news/event creation;
- use accepted S4 materiality.

## Acceptance

A real exact forward Event Risk transition can create one immutable RISK message and preserve source identity/time lineage.

---

# 11. Decision issuance

## Source / persistence

Accepted WC2/R20/R20.5 path.

Decision evidence includes:

- immutable forecast;
- Decision Proof;
- feed event;
- frozen five-family decision context.

## Projector

Implemented:

`project_forecast_issuance()`

Registry:

- `r20_5_forecast_issued`
- category: `DECISION`
- state: `IMPLEMENTED`

## Live caller

`process_wc2_prepared_live_freeze(... issuance_hook=stream_runtime.project_issuance)`

in:

`ops/run_live_evidence_clock.py`

## Production chain

WC2 completion validation  
→ `IntelligenceStreamForwardRuntime.project_issuance`  
→ source ledger  
→ message ledger  
→ story/change  
→ Analytical View/materiality  
→ deterministic Narrative  
→ narrative ledger  
→ SSE/read model.

## Final status

**LIVE_COMPLETE**

## Important current issue

The projector is live, but F1 must explain why WC2 forecast issuance stopped advancing while fresh freezes continued.

That is an upstream liveness/eligibility question, not an F0 projector gap.

---

# 12. Outcome / forecast resolution

## Projector

Implemented forward resolution path:

`IntelligenceStreamForwardRuntime.project_resolution`

Registry:

- `r20_5_forecast_resolved`
- category: `OUTCOME`
- state: `IMPLEMENTED`

## Live caller

`resolve_wc2_outcomes_once(... resolution_hook=stream_runtime.project_resolution)`

in the live evidence clock.

## Safety

Resolution is only projected when the original forward issuance context exists.

Pre-activation historical forecasts are not synthesized into rich Stream stories.

## Final status

**LIVE_COMPLETE**

---

# 13. Capital lifecycle

## Engine / persistence

Canonical three-vault S11 primitives exist for:

- Core;
- Tactical;
- Opportunity Reserve;
- eligibility;
- canonical sizing;
- simulated execution;
- R22 transaction tape;
- R21 Epoch 2 accounting;
- outcome evidence.

Canonical Epoch 2 path:

`Development/runtime/paper/paper_fund_epoch2.sqlite3`

Relevant R22/R21 tables include:

- `r22_epoch2_intents`
- `r22_epoch2_fills`
- `r22_epoch2_bundles`
- `s11_capital_outcome_evidence`
- `r21_vault_snapshots`
- `r21_consolidated_snapshots`
- Epoch 2 activation/state tables.

Key identities include:

- allocator candidate/assessment identities;
- eligibility proof identity;
- sizing assessment/selection identities;
- `intent_identity`;
- `fill_identity`;
- `bundle_identity`;
- vault/consolidated `snapshot_identity`;
- `outcome_identity`.

## Projector code

Implemented code exists:

- `src/crypto_signal/product/intelligence_stream_capital.py`
- `src/crypto_signal/product/intelligence_stream_capital_lifecycle.py`

Projectors include:

- candidate;
- hold;
- blocked;
- eligible;
- sized;
- executed;
- reduced;
- exited;
- accounting updated;
- outcome.

Registry:

- `paper_capital_transition`
- category: `CAPITAL`
- state: `IMPLEMENTED`

## Live production hook

No production Stream caller is proven in the current live evidence clock/supervisor path.

The current WC2 execution journal is a separate evidence rail and cannot be silently treated as canonical R21/R22 Epoch 2 mutation.

## Final status

**CODE_EXISTS_NOT_LIVE**

## Required closure

F5:
- identify/create the canonical forward caller that observes only committed R21/R22 truth;
- project lifecycle idempotently after canonical commit;
- preserve WC2 journal versus canonical Epoch 2 separation;
- add zero-activity diagnostics.

## Acceptance

A genuine canonical Core/Tactical/Opportunity state/action can create the corresponding CAPITAL message, and no CAPITAL action is claimed without exact R21/R22 lineage.

---

# 14. Provider / Data Quality / SYSTEM

## Engine / source

Provider divergence is actively persisted by the live evidence clock.

Runtime path:

`Development/runtime/data/provider_divergence.sqlite3`

Tables:

- `provider_divergence_meta`
- `provider_divergence_snapshots`

Primary identity:

- `snapshot_identity`

The Product read model verifies exact persisted provider-quality/divergence truth.

Market Tape and Event Source also expose source-quality/freshness evidence.

## Message projector

Registry:

- `provider_quality_change`
- category: `SYSTEM`
- subtypes:
  - `data_quality_degraded`
  - `data_quality_recovered`
- state: `REQUIRES_CHANGE_DETECTION`

No production customer-message projector/caller exists.

## Final status

**PERSISTED_SOURCE_ONLY**

## Required closure

F4:
- publish only decision-relevant degradation/recovery;
- bind exact provider-quality/divergence snapshot;
- state effect on decision trust/actionability;
- suppress routine operational noise.

## Acceptance

A real forward degradation/recovery transition enters the canonical Stream once, without converting ordinary logs into customer spam.

---

# 15. Generic Stream infrastructure status

The following infrastructure is already accepted and is not an F0 gap:

| Layer | Status |
|---|---|
| Stream activation boundary | live |
| source ledger | implemented |
| message/fact ledger | implemented |
| Story Observation/State/Change Set | implemented |
| Analytical View | implemented |
| materiality framework | implemented |
| deterministic Turkish Narrative | implemented |
| narrative ledger | implemented |
| SSE/read model | implemented |
| history/search/filter | implemented |
| evidence windows | implemented |
| frozen forecast-bound OHLC proof | implemented |
| notification/sound | implemented |
| mobile/desktop shell | implemented |

The missing work is source-specific production activation/closure, not rebuilding these generic layers.

---

# 16. F0 closure decisions

## LIVE_COMPLETE

- Decision issuance
- Forecast outcome/resolution

## CODE_EXISTS_NOT_LIVE

- canonical Capital lifecycle projection

## PERSISTED_SOURCE_ONLY

- Market / Geometry rich material messages
- Liquidity
- Order Flow / CVD / Absorption
- Derivatives
- Event Risk
- Provider/Data Quality/System

## NO_LIVE_SOURCE

- Bitcoin network always-on Stream source
- continuous liquidation Stream source

## RESEARCH_ONLY

- Exchange Flow
- Wallet Cohort
- Large Transfer / provider-neutral M5 smart-money live chatter

## BLOCKED_BY_CORRECTNESS_DEFECT

None is declared by F0.

The current WC2 forecast stall is deliberately **not** classified as a correctness defect until F1 proves one. F1 must distinguish correct silence from a reproducible failure.

---

# 17. F0 PASS criteria

F0 passes because every original Stream source family now has:

- an exact current source classification;
- known persistence boundary;
- known identity contract;
- exact current projector state;
- exact current live-hook state;
- explicit next closure phase;
- an acceptance condition.

There is no remaining “implemented therefore live” ambiguity.

**F0 = PASS.**

Next exact frontier:

**F1 — WC2 Forward-Liveness Truth**

No policy relaxation is authorized.  
No historical backfill is authorized.  
No real-money authority is introduced.  
**REAL_CAPITAL=0.**
