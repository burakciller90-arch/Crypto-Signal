# Crypto Signal — Final F8 Real Production Multi-Category E2E Preparation

Status: **PREPARED IN PARALLEL — NOT ACCEPTED / NOT MERGEABLE AS FINAL F8 YET**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Target phase: **F8 — Real Production Multi-Category E2E Acceptance**  
Preparation date: 2026-09-26  
Safety: **REAL_CAPITAL=0**

---

## 1. Parallel-work boundary

This branch prepares F8 while F5, F6 and F7 are being developed by separate agents.

The branch intentionally does **not** modify:

- F5 capital runtime/projector/audit files;
- F6 evidence contract/resolver implementation;
- F7 local-model adapter/runtime configuration;
- shared production supervisor wiring;
- Product deployment state;
- canonical Stream history;
- R21/R22 paper-capital truth.

Only additive F8 acceptance tooling is introduced.

Before final F8 acceptance, this branch must be rebased onto the accepted post-F7 `main` and rerun against the actual live Product/runtime.

---

## 2. F8 authority

F8 does not create product truth.

Its job is to replace fixture confidence with genuine production proof for every message class currently claimed live:

1. MARKET or INTELLIGENCE;
2. DECISION issuance;
3. OUTCOME/resolution;
4. RISK or SYSTEM;
5. CAPITAL only when canonical R21/R22 forward activity genuinely exists.

Rare categories are never fabricated merely to make the gate pass.

If a required real forward event has not happened, F8 remains open.

---

## 3. Reused accepted infrastructure

F8 reuses the already accepted Stream and browser stack:

- `/api/stream/messages`;
- exact message lookup;
- exact message detail;
- `/api/stream/live` SSE;
- visual-proof API;
- Stream search/filter API;
- exact message deep links;
- S15/S16 real Chromium/CDP utility in `ops/capture_chromium_viewport.py`;
- live Product root at `http://127.0.0.1:48700` on UID504.

F8 does not introduce a second UI fixture system or a second screenshot stack.

---

## 4. Added preparation tooling

### `ops/audit_stream_f8_production_e2e.py`

Read-only production API auditor.

It:

- verifies Product health, read-only mode and `REAL_CAPITAL=0`;
- inventories every required category from the live Stream API;
- selects only already-persisted genuine messages;
- verifies exact lookup stability across repeated reads;
- verifies detail lineage and authority boundaries;
- verifies category filter/search visibility;
- checks visual proof is exact or explicitly unavailable rather than fabricated;
- checks one-shot SSE replay for duplicate identities;
- reports missing classes as `OPEN` rather than manufacturing activity;
- can require full completion only when final F8 closure is actually attempted.

### `ops/probe_stream_f8_browser.py`

Read-only real-browser probe.

It reuses the accepted Chromium/CDP primitives and verifies against an actual persisted production message:

- no fixture query mode;
- exact deep-link selection;
- real message expansion;
- evidence launcher/window behavior when available;
- search/filter retention of the exact persisted message;
- no horizontal overflow at the requested viewport;
- historical/deep-link load remains silent;
- immutable refresh returns the same persisted message text/identity.

The browser probe never appends a Stream event.

### `.github/workflows/crypto-stream-final-f8-production-e2e-prep.yml`

Two-level gate:

- push on the F8 prep branch runs only lightweight hosted contract checks;
- the production read-only UID504 audit is **manual dispatch only** while F5/F6/F7 are active, preventing unnecessary contention with parallel agents.

The production job records artifacts but does not deploy or mutate Development/Product.

---

## 5. Final F8 event evidence contract

For each accepted real event F8 must retain:

- category/group;
- narrative identity;
- story identity;
- source-event identity when present;
- source kind/subtype when present;
- event time;
- exact message response;
- exact detail response;
- proof status;
- search/filter result;
- SSE duplicate audit;
- browser deep-link result;
- browser expansion result;
- browser evidence-window result;
- refresh immutability result;
- read-only / production-authority / `REAL_CAPITAL=0` assertions.

The acceptance artifact is evidence, not a source of truth.

---

## 6. Negative acceptance

F8 final closure must prove all of the following without synthetic activity:

- repeated persisted identities do not appear as duplicate bubbles;
- one-shot SSE replay contains no duplicate event identity;
- historical/deep-link page load does not chime;
- refresh preserves exact persisted message identity/text;
- missing visual proof remains explicit and does not become an illustrative fake;
- API/UI remains read-only and `REAL_CAPITAL=0`.

A naturally occurring reconnect can be recorded as additional direct evidence. The preparation tooling does not deliberately break the production network merely to force a reconnect event.

---

## 7. Dependency gates before final F8 PASS

F8 cannot be declared PASS until:

- F5 is accepted and any claimed live CAPITAL class is based on canonical R21/R22 truth;
- F6 is accepted and proof states are exact/fail-closed;
- F7 is accepted if local rewrite is enabled, including deterministic fallback;
- the F8 branch is rebased onto that accepted main;
- required genuine forward production classes are present or explicitly classified unavailable/deferred by product authority;
- the final read-only audit is run against the real Product/runtime;
- the real Chromium probe passes on a genuine persisted production message;
- no historical backfill, synthetic event, policy loosening or real-money authority was used.

---

## 8. Current preparation conclusion

F8 is **prepared, not accepted**.

The correct next action is to let F5/F6/F7 finish independently, then rebase this additive acceptance layer and execute the final production proof.

`REAL_CAPITAL=0`.
