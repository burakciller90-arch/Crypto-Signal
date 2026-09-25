# Crypto Signal — Stream S5 Narrative Engine Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S5 closes the customer-language layer required before realtime delivery.

## Accepted implementation

### Slice 1 — fact-safe Turkish narrative backbone

Merged PR #1270 / main commit `e9dcca413dd82da4d6a3702ae6e74bb6f1037e3b`.

Accepted:
- deterministic `StreamNarrativePlan` bound to the exact S4 Analytical View, Fact Bundle and S3 Change Set;
- Turkish-first Crypto Signal analyst voice;
- deterministic voice variants to avoid one robotic opening pattern;
- collapsed + SIMPLE + TECHNICAL + INTELLIGENCE + DECISION + CAPITAL narrative sections;
- story-aware wording only when exact S3 history supports it;
- numeric/certainty/probability validation;
- collapsed/expanded length budgets;
- repetition/similarity guard;
- optional rewriter contract;
- deterministic fallback on rewrite exception, invalid output or repetition;
- append-only Narrative Plan + original rendered-text persistence;
- immutable original narrative text/version lineage.

Exact acceptance:
- tested head `e252a2b42fbe4cdf38d2a09a0092ffa37b6370a9`;
- UID504 run `36160125242`;
- exact-source isolation PASS;
- focused pytest PASS;
- Ruff PASS;
- strict mypy PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

### Slice 2 — concrete local-only rewrite integration

Merged PR #1271 / main commit `4befb074d5b8843a2efb4a1eb09bc9e015f9202a`.

Accepted:
- loopback-only OpenAI-compatible local rewriter;
- default Ollama-compatible endpoint `127.0.0.1:11434/v1`;
- explicit local model configuration requirement;
- no proxy-environment use;
- no redirects;
- bounded timeout / temperature / token limits;
- immutable local-rewriter configuration identity/version in narrative provenance;
- local rewrite authority limited to collapsed + SIMPLE customer-facing prose;
- TECHNICAL / INTELLIGENCE / DECISION / CAPITAL sections remain protected;
- semantic guard rejects unsupported new qualitative market concepts;
- existing numeric/certainty validator remains authoritative;
- repetition guard remains authoritative;
- deterministic renderer remains the fallback path.

Exact acceptance:
- tested head `5a099345c602e09f6ec602dae716eaa6a7a53fd5`;
- UID504 run `36162999184`;
- exact-source isolation PASS;
- focused pytest PASS;
- Ruff PASS;
- strict mypy PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

## Accepted S5 pipeline

```
Canonical source truth
  -> Fact Bundle
  -> S3 Story State + Change Set
  -> S4 Analytical View
  -> S5 Narrative Plan
  -> deterministic Turkish renderer
  -> optional local-only rewrite
  -> validator / semantic guard / repetition guard
  -> immutable original narrative record
  -> S6 realtime delivery
```

The local model is never allowed to become the source of market truth.

## S5 PASS criteria

Roadmap criterion: no invented numeric fact in narrative fixtures.  
**PASS** — numeric/certainty/probability validation rejects unsupported additions and falls back deterministically.

Roadmap criterion: same facts may be expressed naturally without robotic repetition.  
**PASS** — deterministic voice variants, optional safe local rewrite and repetition/similarity guard are accepted.

Roadmap criterion: stylistic consistency.  
**PASS** — voice/version contracts and protected technical sections are identity-bound.

Roadmap criterion: LLM failure does not stop the Stream.  
**PASS** — exceptions, invalid output and repetitive output fall back to deterministic Turkish rendering.

Roadmap criterion: story-aware phrases work only when exact history supports them.  
**PASS** — acceptance now includes an exact same-story `ORDER_FLOW: NO_EVIDENCE -> OBSERVED` transition. The narrative plan emits `missing_confirmation_arrived` and the Turkish message says “Önce eksik olan teyitlerden biri geldi” only for that history-backed transition; a root message with no prior missing evidence does not emit the phrase. Outcome continuation wording is separately covered.

## Important operational boundary

S5 PASS does **not** claim that a particular local model has been downloaded, installed or is currently serving live inference on UID504.

What is accepted is the concrete **local-only adapter contract and guarded runtime path**. Deterministic Turkish rendering works without a model. A configured local model may rewrite only within the accepted safe surface and cannot stop the Stream if unavailable.

## Boundaries retained for later phases

S5 PASS does not claim:
- realtime SSE/WebSocket delivery — S6;
- browser reconnect/catch-up/history cursor/search API — S6;
- final one-panel Stream UI — S7+;
- evidence-window manager — S9;
- frozen visual proof expansion — S10;
- canonical three-vault execution runtime — S11;
- actual trading edge/profitability;
- calibrated probability unless separately accepted.

## Active frontier

**S5 = PASS. S6 Real-time Stream Backend is the sole active Stream implementation frontier.**
