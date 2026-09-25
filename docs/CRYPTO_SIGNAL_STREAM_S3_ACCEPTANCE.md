# Crypto Signal — Stream S3 Story Engine & Change Detection Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S3 closes the deterministic continuity/change-detection layer required before Analytical Composer work.

## Accepted implementation

Merged PR #1265 / main commit `f0ec56b830d22679b9cdf489f7e2453635fafe20`.

Accepted:

- immutable `StreamStoryObservation`;
- immutable `StreamStoryState`;
- immutable `StreamChangeSet`;
- explicit `previous_state_identity` continuity;
- append-only Story Observation + State + Change Set persistence;
- deterministic stance changes;
- deterministic support/opposition score deltas;
- deterministic five-family evidence changes;
- deterministic Event Risk changes;
- deterministic trigger changes;
- deterministic capital-reference additions/removals;
- deterministic outcome changes;
- optional message linkage so pre-publication change detection does not depend on an already-published message;
- exact replay/idempotence;
- unrelated-story joins rejected;
- chronological backfill/forks rejected;
- physical SQLite UPDATE/DELETE rejection.

## Critical continuity rule

S3 does **not** infer story continuity from clock-time proximity.

A non-root observation must name the exact prior `state_identity`. The Story Engine then verifies:

- same explicit `story_identity`;
- same asset/symbol/timeframe context;
- exact latest previous state;
- forward chronological order.

This prevents two nearby but unrelated market events from being silently grouped into one narrative.

## Pre-publication change detection

S3 deliberately permits `message_identity=None` on a Story Observation.

Reason:

1. canonical source truth changes;
2. S3 determines what changed;
3. S4 decides the structured analytical meaning/materiality;
4. S5 later creates Turkish prose.

Therefore S3 does not require a message to exist before it can detect an Event Risk, evidence-family, trigger or capital-state transition.

## Deterministic Change Set fields

The accepted Change Set can represent:

- `story_started`;
- `stance_changed`;
- `score_changed`;
- `evidence_family_changed`;
- `risk_changed`;
- `trigger_changed`;
- `capital_changed`;
- `outcome_changed`;
- `no_story_state_change`.

Family-level change detail preserves:

- family;
- previous/current evidence state;
- previous/current direction;
- support delta;
- opposition delta;
- previous/current quality;
- previous/current freshness;
- previous/current material-conflict count.

## Exact-head acceptance

Branch head accepted before merge:
`debeefdab05c59f4c115b2fa45ee81f3fc020fad`

GitHub Actions:
- run `36155780247`;
- exact-source isolation: **PASS**;
- focused pytest: **PASS**;
- focused Ruff: **PASS**;
- focused strict mypy: **PASS**;
- whole-repository regression: **PASS**;
- Development checkout non-mutation: **PASS**.

## S3 PASS criteria

Roadmap criterion: system can answer “what changed?” deterministically.  
**PASS** — structured stance/score/family/risk/trigger/capital/outcome deltas are deterministic and identity-bound.

Roadmap criterion: message/story can reference previous state without heuristic time-only joins.  
**PASS** — explicit previous-state identity is required and persisted.

Roadmap criterion: unrelated events are not falsely grouped.  
**PASS** — story/market identity mismatch and non-latest previous-state joins fail closed.

## Boundaries retained for later phases

S3 PASS does **not** claim:

- analytical opinion / stance-strength composition — S4;
- dominant support / contradiction / next-condition policy — S4;
- final message publication thresholds for new event families — S4;
- Turkish narrative text — S5;
- narrative persistence/versioning — S5;
- realtime SSE/WebSocket delivery — S6;
- Stream UI — S7+;
- rich proof windows — S9-S10;
- canonical three-vault capital runtime/story — S11;
- trading edge/profitability evidence.

## Active frontier

**S3 = PASS. S4 Analytical Composer is the sole active Stream implementation frontier.**
