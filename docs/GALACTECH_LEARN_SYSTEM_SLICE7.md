# GALACTECH Product Rail — Learn / System Slice 7

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
Predecessor: accepted GALACTECH Performance & Trust PR #929.
REAL_CAPITAL=0.

## Learn

Learn is bound to the deterministic Turkish-first education catalog exposed by
`GET /api/education`.

It renders the accepted fields:

- canonical concept id;
- beginner explanation;
- why it matters;
- optional advanced explanation.

Search is local over those exact fields. An empty search result does not generate new
content.

Quick links use exact canonical concept ids. Evidence Room may offer deterministic
contextual lesson links only when the frozen detail contains an explicit cue such as:

- NO_SIGNAL / NEUTRAL -> ABSTAIN;
- frozen geometry / invalidated state -> INVALIDATION + RISK_REWARD;
- explicit CVD/delta text -> CVD;
- explicit absorption text -> ABSORPTION;
- explicit liquidity/sweep text -> LIQUIDITY_SWEEP;
- harmonic setup text -> HARMONIC_PRZ;
- Elliott/wave text -> ELLIOTT_WAVE.

Agreement-vs-probability is always available because the evidence surface itself exposes
a confluence agreement score. This mapping teaches concepts; it does not generate a
market conclusion.

## System

System Truth is a fail-closed customer observability surface.

It may report from accepted loaded APIs:

- Product API status;
- signal ledger presence;
- canonical Epoch 2 customer state;
- Proof Wall/outcome-schema availability;
- Market Radar customer-evidence availability and observed item count;
- Intelligence API projection;
- Performance API projection;
- deterministic education catalog size;
- alert-outbox presence;
- REAL_CAPITAL=0 and read-only authority.

It deliberately does **not** infer runtime health for systems that the current customer
API does not expose.

Therefore:

- Market Tape runtime = NOT EXPOSED;
- Cold Archive = NOT EXPOSED;
- Event Feed runtime = NOT EXPOSED;
- latency = NOT MEASURED;
- universal freshness = NOT MEASURED.

A healthy Product API is not evidence that Market Tape is ONLINE.

## Authority

- no order submission;
- no broker/exchange credentials;
- no ledger mutation;
- no fabricated health;
- no generated probability;
- REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
