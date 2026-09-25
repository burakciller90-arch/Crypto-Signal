# Crypto Signal — Stream S4 Analytical Composer Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S4 closes the deterministic structured-opinion layer required before Turkish narrative generation.

## Accepted implementation

Merged PR #1268 / main commit `d8d53e26c8b552615d14697f614124d3f1e1ed00`.

Accepted:

- versioned immutable `StreamAnalyticalPolicy`;
- deterministic `StreamAnalyticalView`;
- exact Fact Bundle + current Story State + Change Set lineage;
- optional Message Input linkage so analytical composition can happen **before publication**;
- effective stance: bullish / bearish / watch / blocked / resolved;
- deterministic stance strength under a versioned policy;
- exact support/opposition/net-support points;
- deterministic dominant support / secondary support / main contradiction selection from persisted five-family M6 contributions;
- uncertainty derived from accepted evidence availability, conflicts, family states, Event Risk and probability status;
- canonical next-condition and invalidation objects bound to frozen forecast geometry;
- deterministic capital-reference consequence without inventing paper execution;
- deterministic analytical publication materiality from S3 Change Set;
- append-only Analytical View persistence keyed by exact Story State / Change Set identity;
- immutable Fact Bundle persistence before a Message Input exists;
- later Message Input attachment only when the exact frozen Fact Bundle matches;
- exact replay/idempotence;
- physical SQLite UPDATE/DELETE rejection.

## Pipeline now accepted

```
Canonical source truth
  -> immutable Fact Bundle
  -> S3 Story State + Change Set
  -> S4 Analytical View
  -> S5 Narrative Plan / Turkish renderer (next phase)
```

This ordering is intentional: the system first forms an identity-bound structured opinion, then a later phase turns that opinion into natural Turkish.

## Publication/materiality semantics

S4 materiality is versioned and deterministic.

A change may become analytically publishable when the accepted policy sees material state such as:

- story start;
- stance change;
- Event Risk change;
- trigger change;
- capital-reference change;
- outcome change;
- support/opposition movement above the versioned material threshold;
- material five-family evidence change.

A non-material state can remain `SILENT` with `no_material_analytical_change`.

This prevents the future Stream from emitting a message for every market tick while still allowing meaningful changes to become message candidates.

## Exact-head acceptance

Branch head accepted before merge:
`a425a0dac8065ca142da20ada14534d07adff198`

GitHub Actions:
- run `36158170886`;
- exact-source isolation: **PASS**;
- focused pytest: **PASS**;
- focused Ruff: **PASS**;
- focused strict mypy: **PASS**;
- whole-repository regression: **PASS**;
- Development checkout non-mutation: **PASS**.

## S4 PASS criteria

Roadmap criterion: same canonical facts produce the same analytical result.  
**PASS** — policy, facts, Story State and Change Set are identity-bound and deterministic.

Roadmap criterion: analytical result explains why a message deserves publication.  
**PASS** — analytical materiality carries deterministic PUBLISH/SILENT disposition plus reason codes.

Roadmap criterion: decision and capital state are identity-bound.  
**PASS** — current Story State / Change Set identities are required; capital consequences carry exact reference identities and never invent execution.

## Boundaries retained for later phases

S4 PASS does **not** claim:

- natural Turkish analyst prose — S5;
- local-LLM rewriting — S5;
- original published narrative persistence/versioning — S5;
- realtime SSE/WebSocket transport — S6;
- one-panel messaging UI — S7+;
- rich floating evidence windows — S9-S10;
- canonical three-vault forward execution runtime — S11;
- provider-specific/Event-Risk live projector completion where the source projector is still gated;
- trading edge, profitability or calibrated probability unless separately accepted.

## Active frontier

**S4 = PASS. S5 Narrative Engine is the sole active Stream implementation frontier.**
