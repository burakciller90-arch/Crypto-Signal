# Crypto Signal — Final F2 Production Source-to-Message Backbone Acceptance

Status: **PASS**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F2 — Production Source-to-Message Backbone**  
Date: 2026-09-26  
Safety: **REAL_CAPITAL=0**

---

## 1. Goal

F2 had one bounded goal:

> provide one reusable production projector boundary so every later source family must enter the already accepted Stream Source Event → Fact Bundle → Story → Analytical → materiality → Narrative → immutable ledger path instead of creating a parallel customer-message system.

F2 does **not** claim that Market/Geometry, Liquidity, Order Flow, Derivatives, Event Risk or Provider/System projection is already live. Those source-specific change detectors and runtime hooks remain F3/F4 work.

---

## 2. Accepted implementation

Added:

`src/crypto_signal/product/intelligence_stream_production_projector.py`

The module introduces:

- `StreamProductionProjectorContract`;
- `IntelligenceStreamProductionProjector`;
- `StreamProductionProjectionResult`;
- deterministic contract identity;
- exact registry binding;
- exact accepted materiality-decision binding;
- fail-closed rejection for source projectors that are not yet marked `IMPLEMENTED`.

The common contract carries:

- source event identity;
- normalized Stream event identity;
- category;
- subtype;
- importance;
- asset/symbol/market/timeframe;
- event time;
- source-as-of time;
- exact evidence identities;
- story identity;
- current fact reference;
- optional previous-state reference;
- accepted S4 materiality reason codes;
- exact materiality-decision identity;
- `production_authority=false`;
- `REAL_CAPITAL=0`.

---

## 3. Canonical chain ownership

Once a source-specific projector produces its canonical projected source/fact/message input, the F2 backbone owns the downstream path:

1. append exact source event;
2. append canonical fact/message bundle;
3. build Story Observation;
4. build Story State;
5. build Change Set;
6. compose Analytical View;
7. enforce accepted analytical materiality;
8. build Narrative Plan;
9. render deterministic Narrative;
10. append immutable narrative.

The backbone reuses the existing accepted ledgers and S3/S4/S5 logic. It does not create a second message ledger, second story engine, second materiality policy or second renderer.

Replay remains idempotent.

---

## 4. Fail-closed family activation

F2 deliberately does not mark later families live.

A registry entry must be `IMPLEMENTED` before the production backbone accepts it.

Therefore current F3/F4 families such as:

- `market_geometry_change`;
- `liquidity_change`;
- `order_flow_change`;
- `derivatives_change`;
- `event_risk_change`;
- `provider_quality_change`

remain rejected by the common production boundary until their exact change-detection/projector implementation is completed in the correct later phase.

This prevents a registry declaration from being mistaken for live production capability.

---

## 5. Accepted exact-source gate

UID504 workflow run:

**36253512588**

Exact head:

**`c63c17ef8fbd56a7663728e92edd94e049469571`**

Accepted evidence:

- `F2_EXACT_SOURCE_PASS=YES`;
- focused F2 backbone + existing forward-runtime tests PASS;
- ruff PASS;
- strict mypy PASS;
- broad repository regression excluding tests marked `asyncio` PASS;
- full `ruff check src tests` PASS;
- full strict `mypy src` PASS — 237 source files;
- JavaScript syntax/freshness regression PASS;
- `F2_FOCUSED_GATE_PASS=YES`;
- `F2_BROAD_REPOSITORY_REGRESSION_PASS=YES`;
- `HISTORICAL_BACKFILL=NO`;
- `REAL_CAPITAL=0`.

The repository's current dev dependency set does not include `pytest-asyncio`; tests carrying that marker were therefore excluded from this F2 regression rather than changing unrelated dependency authority. F2 changes do not touch those async collectors.

---

## 6. F2 closure

F2 is accepted because a reusable, identity-bound, fail-closed production projector interface now exists and forces later implemented families through the accepted Story / Analytical / materiality / Narrative chain.

F2 does **not** fabricate source-family activation.

Next exact frontier:

**F3 — Five-Family Live Intelligence Projection**

No historical rich backfill is authorized.  
No scientific threshold is relaxed to manufacture activity.  
No real-money authority is introduced.  
**REAL_CAPITAL=0.**
