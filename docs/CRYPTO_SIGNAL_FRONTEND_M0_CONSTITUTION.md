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
