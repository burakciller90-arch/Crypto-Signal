# Crypto Signal Frontend M0 — Canonical Product Constitution

Status: CANONICAL M0 — PASS / CLOSED  
Company: GALACTECH  
Product/project: Crypto Signal  
Authority: frontend/product decisions only; scientific and safety boundaries remain governed by repository-wide contracts.

## Locked user decisions

- GALACTECH is the company.
- Crypto Signal is the product/project.
- Turkish-first.
- Light-first.
- Futuristic advanced-technology / command-center character.
- Calm, legible, low-noise surface.
- Approximately ten-second comprehension is a core UX target.
- Technical detail is progressive disclosure.
- **Intelligence Feed is the primary product pillar**: the user should see the machine's accepted market observations, decisions, evidence changes and capital consequences as a live, evidence-bound timeline rather than a thin forecast list.
- **Virtual Capital / Smart Capital is the second primary product pillar**: canonical Epoch 2 (1,000 USDT; Core 600 / Tactical 300 / Opportunity Reserve 100) must be visible as an active simulated capital system, not a decorative balance card.
- Intelligence and Decision Proof are core product values.
- Evidence must be truthful and frozen when the claim depends on point-in-time state.
- Visual technical claims should be shown on-chart only when exact evidence coordinates exist.
- Archive is persistent.
- Losses and invalidations remain visible.
- Missing evidence is not invented.
- REAL_CAPITAL=0.

## Decision rights

User locks:
- information architecture;
- screen purpose;
- hierarchy;
- terminology;
- visual direction;
- density;
- primary interactions;
- which information deserves attention.

Engineering owns:
- data structures;
- state implementation;
- rendering;
- caching;
- request orchestration;
- pagination mechanics;
- resilience;
- test architecture;
- accessibility mechanics;
- performance mechanics.

## Truth axes

### Availability
READY / EMPTY / PARTIAL / UNAVAILABLE

### Freshness
CURRENT / STALE / UNKNOWN

### Quality
HEALTHY / DEGRADED / UNKNOWN

### Evidence/measurement
SUFFICIENT / INSUFFICIENT_EVIDENCE / NOT_MEASURED / NOT_APPLICABLE / UNKNOWN

No axis may silently overwrite another.

## Temporal integrity

- Preserve canonical source/event/availability/observation/issuance/freeze/resolution timestamps where available.
- THEN uses only issuance-time/frozen evidence.
- NOW may contain later outcomes but cannot mutate THEN.
- Time proximity is never identity or causality.
- Timezone/local formatting is presentation only.
- Unknown temporal semantics must remain unknown.

## Identity and lineage

Exact canonical immutable identities are required for joins.

UI must never join decisions by symbol/time/direction heuristics.

Prefer explicit:
signal_freeze_identity -> forecast_identity -> proof_identity -> evidence identities -> capital/paper cycle -> outcome identity, with exact source snapshot identities where available.

## Frontend authority boundary

Frontend is read-only.

It cannot carry:
- exchange credentials;
- real order dispatch;
- withdrawal authority;
- leverage/borrowing authority;
- REAL_CAPITAL authority.

REAL_CAPITAL=0.

## Backend capability surfacing invariant

Accepted backend capability must not disappear merely because a product adapter or UI component has not yet been written.

For every accepted backend capability relevant to the user, M1 must classify it as one of:
- SURFACE_DIRECT — already safely consumable;
- SURFACE_ADAPTER — canonical truth exists; build a read-only product projection;
- ADVANCED_ONLY — expose through progressive disclosure;
- RESEARCH_ONLY — visible only as clearly labelled research evidence where useful;
- INTERNAL_ONLY — intentionally not a user-facing product concept;
- NOT_AVAILABLE — the underlying canonical evidence truly does not exist.

**SURFACE_ADAPTER is not NOT_AVAILABLE.** Frontend copy must never say "data does not exist" merely because the current API does not project an existing backend capability.

## Virtual-capital activity invariant

Epoch 2 is a simulation/research capital system, not a decorative wallet.

- Core, Tactical and Opportunity Reserve remain independent canonical vaults.
- Tactical is intended for short-horizon 1m/5m microstructure research.
- The product must not intentionally leave Tactical disconnected when canonical evidence, allocation, sizing and paper-accounting primitives exist.
- A missing canonical Tactical execution bridge is an implementation GAP, not a reason to hide Tactical.
- The system must continuously evaluate eligible simulated opportunities and explain every HOLD / BLOCK / EXECUTE outcome.
- **No forced trade is permitted solely to make the UI look active.** Activity means the decision engine is genuinely processing opportunities; capital is deployed only when canonical gates pass.
- REAL_CAPITAL remains 0; there is no real-order authority.

## Scientific UI invariants

- confluence != probability;
- historical win rate != calibrated probability;
- backtest != untouched-forward;
- missing != neutral;
- not measured != zero;
- stale != healthy;
- losses are not hidden;
- issuance truth is immutable;
- narrative/LLM is non-authoritative;
- UI certainty cannot exceed backend certainty.

## Layout invariant

Desktop primary surfaces target bounded application workspaces. Dense content uses controlled local scrolling or stable pagination rather than unbounded page scroll where practical.

## Execution invariant

Every screen:
truth discovery -> user decisions -> wireframe -> approval -> visual -> approval -> just-in-time adapter -> real data -> acceptance -> formative test -> close.

## M0 acceptance

M0 is PASS because:
- brand hierarchy is explicit;
- known user decisions are recorded;
- decision rights are explicit;
- truth states are multi-axis;
- temporal integrity is explicit;
- immutable lineage is explicit;
- authority boundary is explicit;
- scientific UI invariants are explicit;
- screen-by-screen execution rule is explicit.

Next frontier: **M1 ACTIVE** — complete the canonical cross-surface identity graph and frontend temporal-field map, resolve only the remaining open product decisions, and obtain user-approved final information architecture before M2 routes are frozen.
