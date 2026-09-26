# Crypto Signal — Intelligence Stream Final F7 Preparation

Status: **PREPARED_NOT_ACTIVATED**  
Phase: **F7 — Guarded Local LLM / Ollama Activation**  
Preparation branch: `stream/final-f7-local-llm-prep`  
Preparation base main: `5bea11a40a8fe66d7327006ff50617e5169cdafa`  
Safety: **REAL_CAPITAL=0**

## Purpose

This branch prepares F7 without advancing canonical roadmap authority while F5 and F6 are being implemented by separate agents.

It intentionally does **not**:
- merge to `main`;
- mutate Development/Product/live databases;
- edit `CURRENT_STATUS.md`, `PROJECT_CHRONICLE.md`, the final roadmap, or the SSD supervisor;
- claim F5, F6, or F7 PASS;
- require a model to be installed or running;
- create synthetic Stream activity or historical backfill.

## Reused accepted S5 guardrails

F7 reuses the already accepted local rewrite boundary rather than creating a second LLM system:

- OpenAI-compatible local adapter;
- Ollama-compatible default endpoint `http://127.0.0.1:11434/v1`;
- loopback-only endpoint validation;
- redirects disabled;
- proxy environment ignored;
- bounded timeout and token budget;
- low runtime temperature;
- immutable rewriter configuration identity/version;
- only collapsed + SIMPLE prose is rewriteable;
- TECHNICAL / INTELLIGENCE / DECISION / CAPITAL sections remain protected;
- numeric/fact/semantic/repetition validation remains authoritative;
- any adapter/model/validation failure falls back to deterministic narrative.

The model remains a language-polish component only. It never becomes market, score, risk, vault, timestamp, evidence, or execution authority.

## F7 preparation wiring

The preparation branch injects one optional `StreamNarrativeRewriter` into:

1. `IntelligenceStreamForwardRuntime` for genuine forward Decision issuance/resolution narratives.
2. `IntelligenceStreamProductionProjector` for the canonical generic production Story → Analytical → Narrative backbone.

The existing F3/F4 family-specific deterministic narrative schema is deliberately not redesigned in this preparation branch. F7 activates the already-designed S5 safe rewrite port; it does not expand the phase into a second family-narrative migration.

## Runtime opt-in

Local rewrite is disabled by default. Runtime activation is environment-only and explicit:

- `CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_ENABLED=1`
- `CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_MODEL=<local model name>`
- optional `CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_BASE_URL` (default `http://127.0.0.1:11434/v1`)
- optional `CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_TIMEOUT_SECONDS` (default `8.0`)
- optional `CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_TEMPERATURE` (default `0.25`, production runtime rejects values above `0.3`)
- optional `CRYPTO_SIGNAL_STREAM_LOCAL_REWRITE_MAX_TOKENS` (default `1400`)

No model name is committed as product truth.

When enabled, startup observability emits the immutable rewriter identity/version and confirms loopback transport plus deterministic fallback. It does not log prompts or introduce credentials.

## Prepared acceptance coverage

The F7 prep gate must prove:

- deterministic mode remains the default;
- unsafe/non-loopback endpoints fail closed before model use;
- enabled mode requires an explicit model;
- production temperature remains low;
- forward Decision publication records `source_kind=local_rewrite` and exact rewrite provenance;
- the generic production backbone records the same provenance;
- a simulated local-model outage still publishes `deterministic_fallback`;
- existing semantic, numeric, protected-section and repetition guards remain green;
- whole-repository regression remains green;
- Development checkout remains untouched;
- `REAL_CAPITAL=0`.

No real Ollama invocation is required for **preparation** acceptance because F7 physical activation must occur only after F5 and F6 are canonically accepted.

## Mandatory handoff after F5 + F6

Before F7 can become active or PASS:

1. Fetch the exact accepted F5/F6 `main`.
2. Rebase this branch onto that exact `main`; resolve overlaps by preserving F5/F6 canonical behavior.
3. Re-run the F7 prep gate on the rebased exact source.
4. Audit any new F5 narrative writer introduced after this branch base; it must either enter the canonical S5-safe rewrite path or remain explicitly deterministic. Do not guess.
5. Verify a real local Ollama-compatible service/model on loopback only.
6. Activate the environment configuration through the canonical runtime owner without hard-coding model truth into product code.
7. Observe a genuine forward live message; do not synthesize one merely to satisfy F7.
8. Verify persisted provenance, semantic equivalence, protected sections and the deterministic original/replay path.
9. Verify model outage/failure cannot prevent genuine message publication.
10. Only then write F7 acceptance evidence and advance the roadmap to F8.

Until those steps are complete, this document remains **PREPARED_NOT_ACTIVATED** and canonical authority remains with the currently accepted roadmap frontier.

**REAL_CAPITAL=0.**
