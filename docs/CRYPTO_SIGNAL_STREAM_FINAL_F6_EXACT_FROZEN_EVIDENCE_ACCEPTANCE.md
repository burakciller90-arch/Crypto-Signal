# Crypto Signal — Final F6 Exact Frozen Evidence Acceptance

Status: **PASS — PHYSICALLY LIVE**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F6 — Exact Frozen Evidence Closure**  
Date: 2026-09-27  
Safety: **REAL_CAPITAL=0**

---

## 1. Accepted production scope

F6 closes the exact-evidence path for real Stream messages.

Accepted customer-facing resolver model:

**message evidence identity**  
→ **exact persisted evidence object or exact bound identity**  
→ **frozen timestamped customer projection**

Historical proof is never reconstructed from current market state.

Every visible proof state is constrained to exactly one of:

- `READY_EXACT`;
- `IDENTITY_ONLY_EXACT`;
- `UNAVAILABLE_EXPLICIT`.

No ambiguous “looks plausible” proof state is accepted.

---

## 2. Implementation acceptance

F6 implementation merged through PR **#1372**.

Accepted merged main:

`115aaf9c97eca012503224c3a64a97526c1bf4dd`

Final exact-head preparation gate:

**36273257337 — SUCCESS**

Exact branch head:

`c830a47f32890ecde5a9138d384661c0202eac00`

The gate proved:

- focused F6 pytest coverage passed;
- Ruff passed;
- strict mypy passed;
- JavaScript syntax checks passed;
- all live evidence sources were readable without mutation:
  - Signal Ledger;
  - Decision Evidence;
  - Stream;
  - Market Tape;
  - Event Source;
  - Provider Divergence;
- Development and Product remained unmodified during the preparation audit;
- no historical rich-message backfill;
- `REAL_CAPITAL=0`.

Preparation artifact:

- name: `stream-final-f6-exact-evidence-prep-36273257337`;
- artifact ID: `10915519501`;
- SHA256: `94c5a9f55c8d297ff23244fdcabe5d680c58d0a2ea85a0d6aeee1056f06f912e`.

---

## 3. Genuine live evidence audit

The preparation gate scanned the latest **240 genuine persisted family messages** and selected the newest real message for every currently present required projector family.

Real messages resolved:

- `market_geometry_change`;
- `liquidity_change`;
- `order_flow_change`;
- `derivatives_change`;
- `provider_quality_change`.

Observed domain coverage included:

- frozen chart / geometry;
- liquidity;
- order flow;
- public trades;
- order book;
- derivatives;
- data quality;
- provider divergence.

Observed exact proof states:

- resolution states:
  - `READY_EXACT`: 6;
  - `IDENTITY_ONLY_EXACT`: 4;
- reference states:
  - `READY_EXACT`: 20;
  - `IDENTITY_ONLY_EXACT`: 6.

No ambiguous state was observed.

No current-data substitution was used.

Marker:

`F6_REAL_F3_F4_EVIDENCE_AUDIT_PASS=YES`

---

## 4. Physical Product deployment and live acceptance

Final UID504 physical acceptance run:

**36273664348 — SUCCESS**

Workflow-only acceptance head:

`2e4257ebfb24def7e643d4fbaf80aca91f526087`

The run proved:

- Development exact main:
  `115aaf9c97eca012503224c3a64a97526c1bf4dd`;
- Product exact main:
  `115aaf9c97eca012503224c3a64a97526c1bf4dd`;
- both checkouts clean;
- canonical supervisor restarted:
  - old PID `59679`;
  - new PID `60553`;
- customer dashboard process restarted on the new Product code:
  - old PID `59687`;
  - new PID `60561`;
- health remained:
  - `status=ok`;
  - read-only;
  - Stream product root;
  - `REAL_CAPITAL=0`.

The physical run then queried the **real loopback Product HTTP API** for persisted Stream messages and verified exact evidence on these genuine narrative identities:

- derivatives:
  `d10b0173cae69436dae900a569a44b98ba16763c02f86d283c4781d26401b011`;
- liquidity:
  `f39ce20e95d07924c0d393a91f5da59a1f920cdd682a5692ca1a6220f0f364e0`;
- geometry:
  `292fff32aef2df8a30eea66069f2a36c9c8ccfcd8042d1518f0b7e7526271d74`;
- order flow:
  `3246450aaeccb1c45f9e1ba8bd830503cd0304e4c32ea614e4219a665664d80e`;
- provider quality:
  `d1a5b938479608764146086869ccd6c0fe772b27b48a92eaedc91cd966e3b62f`.

Physical API resolution counts:

- derivatives:
  - `READY_EXACT=1`;
- liquidity:
  - `IDENTITY_ONLY_EXACT=2`;
- geometry:
  - `READY_EXACT=1`;
  - `IDENTITY_ONLY_EXACT=1`;
- order flow:
  - `READY_EXACT=2`;
  - `IDENTITY_ONLY_EXACT=1`;
- provider quality:
  - `READY_EXACT=2`.

The same run also proved:

- `/stream-evidence` detached evidence UI is served by the deployed Product;
- the deployed `/stream-static/evidence.js` knows only the accepted exact proof states;
- evidence requests do not substitute current market data;
- historical backfill remains disabled;
- production authority remains false;
- `REAL_CAPITAL=0`.

Final marker:

`F6_PHYSICAL_LIVE_ACCEPTANCE_PASS=YES`

Physical acceptance artifact:

- name: `stream-final-f6-live-acceptance-36273664348`;
- artifact ID: `10916074210`;
- SHA256: `c737c3b113bb169858c531182ff59a885334ca5e47c772b537de1ffd52aeba87`.

---

## 5. Fail-closed behavior

F6 explicitly preserves these rules:

- if exact visual coordinates exist, frozen proof may render them;
- if exact visual coordinates do not exist, the UI must not draw an illustrative line as fact;
- exact numeric/text evidence may still be shown;
- an exact bound identity may be shown as `IDENTITY_ONLY_EXACT`;
- missing evidence is explicit as `UNAVAILABLE_EXPLICIT`;
- current market state is never used to fabricate historical proof;
- old Stream chronology is not rewritten.

Event Risk and Capital are not fabricated merely to populate acceptance.

If a real Event Risk or Capital message exists, the same exact/fail-closed resolver contract applies. Under the revised frontend scope, the still-deferred Portfolio/Capital live behavior is not falsely claimed as tested here.

---

## 6. Safety boundary

F6 grants no execution authority.

- no real exchange orders;
- no production-capital authority;
- no synthetic Capital candidate;
- no fake sizing;
- no fake fill;
- no historical rich-message backfill;
- **REAL_CAPITAL=0**.

---

## 7. F6 closure

F6 is fully closed and physically live.

Next roadmap phase:

**F7 — Guarded Local LLM / Ollama Activation**
