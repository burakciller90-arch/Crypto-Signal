# Crypto Signal — Final F7 Guarded Local LLM / Ollama Acceptance

Status: **PASS — PHYSICALLY LIVE**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F7 — Guarded Local LLM / Ollama Activation**  
Date: 2026-09-27  
Safety: **REAL_CAPITAL=0**

---

## 1. Accepted product boundary

F7 activates a local-language polish layer only after deterministic Stream narrative truth exists.

The local model is not an analyst and has no authority to:

- choose market direction;
- invent facts, prices, targets, scores or probabilities;
- change Decision truth;
- change Capital truth;
- change timestamps;
- create unsupported causal claims;
- create execution authority.

The final accepted rewrite boundary is intentionally narrow:

- the local model receives and returns only:
  - `collapsed_text`;
  - `simple_text`;
- `technical_text`, `intelligence_text`, `decision_text` and `capital_text` are rebound directly from deterministic truth in code;
- a byte-identical no-op rewrite is rejected;
- malformed or additional fields are rejected;
- unsupported additions remain validator-rejected;
- any model/transport/validation failure falls back to the deterministic narrative.

Accepted provenance version:

`crypto-signal-local-rewriter-v1/5`

---

## 2. Implementation lineage

F7 guarded local rewrite wiring was first merged through PR **#1366**.

Subsequent physical-acceptance hardening closed concrete real-model issues without weakening truth constraints:

- PR **#1377** — structured-output hardening;
- PR **#1380** — strict six-field schema/provenance hardening;
- PR **#1381** — require genuine guarded style rewrite;
- PR **#1382** — isolate the local model to the two polishable fields and rebind protected sections deterministically;
- PR **#1383** — add bounded, direction-neutral Turkish few-shot guidance and explicit safe rewrite task.

Exact accepted implementation main:

`3cf79749b580598fe16a6dd0879beaca869f9cfe`

Final PREP gate for the accepted prompt/contract:

**36304644827 — SUCCESS**

It passed:

- focused F7 guarded rewrite tests;
- whole-repository regression;
- Development non-mutation;
- loopback / bounded transport contract;
- strict response schema;
- no-op rejection;
- deterministic fallback coverage;
- `REAL_CAPITAL=0`.

---

## 3. Local runtime

UID504 now has a user-local Ollama runtime under the Crypto Signal tools root.

Final accepted operational model for this activation:

`qwen2.5:3b-instruct`

This model choice is **operational configuration, not product truth**.

The product contract remains model-independent provided a replacement model satisfies all F7 guardrails.

The final physical acceptance proved:

- Ollama reachable only through the configured loopback endpoint;
- no cloud model dependency required;
- bounded token budget;
- low temperature;
- bounded timeout;
- no proxy/redirect transport;
- immutable rewrite config identity;
- deterministic fallback on error.

---

## 4. Genuine local rewrite proof

Final physical acceptance run:

**36304946764 — SUCCESS**

Acceptance workflow head:

`3f1e861c1c13714e64348085108fb155cc44361a`

The run exercised the real OpenAI-compatible Ollama adapter without mutating production Stream state.

Accepted real rewrite sample:

Deterministic collapsed baseline:

`BTCUSDT 4h görünüm yukarı yön tarafı; destek puanı 82, ek teyit takip.`

Local collapsed result:

`BTCUSDT 4h yukarı yönü; destek puanı 82. Ek teyit takip.`

Deterministic simple baseline:

`BTCUSDT 4h yukarı yön görünüm var. Destek puanı 82. Ek teyit takip sürüyor.`

Local simple result:

`BTCUSDT 4h yukarı yönü. Destek puanı 82. Ek teyit takip sürüyor.`

Mechanical acceptance facts:

- `candidate_differs_from_baseline=true`;
- protected sections unchanged;
- no production mutation;
- no invented accepted numeric value;
- `REAL_CAPITAL=0`;
- local adapter marker:
  `F7_REAL_OLLAMA_ADAPTER_PASS=YES`.

The smoke-test config used a longer acceptance-only timeout to remove cold-start noise while preserving the same bounded product contract.

Acceptance smoke rewriter identity:

`50eb27007a35502c9fb0a857ea2bca8fd990c2f36e7021f4c0848840c9c82275`

---

## 5. Physical Product activation

The same run fast-forwarded both physical checkouts to exact accepted main:

- Development:
  `3cf79749b580598fe16a6dd0879beaca869f9cfe`;
- Product:
  `3cf79749b580598fe16a6dd0879beaca869f9cfe`.

Both remained clean.

The canonical supervisor was restarted with guarded local rewrite enabled and emitted:

`stream_rewrite status=ENABLED transport=loopback rewriter_identity=bb3cc91b32035df91b14de3c9974fde79a6ceb2ad90ce397b7812b5474dd04ab rewriter_version=crypto-signal-local-rewriter-v1/5 DETERMINISTIC_FALLBACK=YES REAL_CAPITAL=0`

Runtime activation marker:

`F7_PHYSICAL_ACTIVATION_PASS=YES`

Supervisor transition:

- old supervisor PID: `81112`;
- new supervisor PID: `91777`.

Production runtime uses the stricter bounded timeout configured for live delivery; if the local model is cold, slow, malformed or unavailable, publication falls back deterministically rather than waiting indefinitely.

No historical message was rewritten or backfilled.

`HISTORICAL_BACKFILL=NO`

---

## 6. Outage / rejection behavior

Final physical acceptance also proved the negative path:

`F7_OUTAGE_FALLBACK_PASS=YES`

Therefore:

- local-model outage does not prevent message publication;
- malformed model output does not become product truth;
- no-op output is rejected;
- unsupported additions are rejected by the existing narrative validation path;
- the deterministic baseline remains valid and publishable;
- original deterministic text/provenance remains auditable.

This is the binding F7 authority rule:

**LLM polish may improve presentation; deterministic truth remains authoritative.**

---

## 7. Artifact

Final acceptance artifact:

- name: `stream-final-f7-live-acceptance-36304946764`;
- artifact ID: `10926568887`;
- SHA256: `4c05aa1398eaed5aed229e552963bbf804d5e27a559d67291e1be167dfa239b1`.

---

## 8. Safety boundary

F7 grants no execution authority.

- no real exchange orders;
- no Capital sizing authority;
- no fill authority;
- no production-capital authority;
- no historical rich-message backfill;
- no cloud LLM dependency required;
- **REAL_CAPITAL=0**.

---

## 9. F7 closure

F7 is **PASS — PHYSICALLY LIVE**.

Next roadmap phase:

**F8 — Real Production Multi-Category E2E Acceptance**
