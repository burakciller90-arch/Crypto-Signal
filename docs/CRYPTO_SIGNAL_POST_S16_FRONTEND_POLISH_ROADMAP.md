# Crypto Signal — Post-S16 Frontend Polish Roadmap

Updated: 2026-09-26  
Authority: user-approved post-S16 product polish scope  
Product: Crypto Signal by Galactech  
Safety: REAL_CAPITAL=0

## 1. Why this roadmap exists

Intelligence Stream V1 S0-S16 is complete and remains closed. This roadmap does **not** reopen those stages.

The live Stream is mechanically correct, but the accepted surface still reads visually like an acceptance build in several places. The goal of this scope is to turn the already-working Stream into the final premium product experience the user asked for:

- Turkish;
- light-first and low eye strain;
- futuristic cyber-command-center / advanced-technology feel;
- no dashboard clutter;
- one persistent Intelligence Stream;
- trader understands the situation in about 10 seconds;
- deeper proof remains exact, frozen and auditable;
- no synthetic market truth;
- no historical rich backfill;
- REAL_CAPITAL=0.

## 2. Locked product rules

The following are not negotiable during polish:

1. The Stream remains the single product root.
2. Search, filters, evidence and settings remain overlays/windows, not permanent product sections.
3. Canonical message text/history is not silently rewritten.
4. Frozen proof never substitutes current data.
5. Missing evidence remains explicit.
6. No new real-money authority.
7. Product polish must not reopen backend/runtime work unless an actual frontend-blocking truth defect is reproducible.
8. Existing S0-S16 behavioral guarantees stay intact: SSE/reconnect, history, deep-linking, windows, proof, notifications, long-session performance and accessibility.

## 3. P0 — Visual authority and scope freeze

Goal: establish one final visual direction before touching interaction semantics.

Work:
- keep light-first palette;
- reduce acceptance-test visual language;
- strengthen Galactech/Crypto Signal identity;
- replace weak Unicode controls with consistent vector controls;
- define message category accents without turning the Stream into a dashboard;
- preserve reduced-motion and contrast modes.

PASS:
- no new navigation rail or dashboard chrome;
- visual treatment stays calm and premium;
- mobile remains first-class;
- no semantics or backend contract change.

## 4. P1 — Ten-second message hierarchy

Goal: a trader should be able to scan a collapsed message and answer:

- what changed?
- which market/timeframe?
- what does the system currently think?
- is this important?
- where do I open the proof?

Work:
- stronger category/state hierarchy;
- restrained category accent system;
- clearer symbol/timeframe/time ordering;
- cleaner message chips;
- global paper-only safety replaces repetitive non-capital safety chips;
- “detail” language becomes proof/evidence-oriented;
- empty state explains deliberate silence instead of looking unfinished.

PASS:
- collapsed messages remain concise;
- category differences are visible without reading every chip;
- non-capital messages do not repeat global safety status;
- capital messages still state paper-only truth explicitly;
- no data is invented.

## 5. P2 — Evidence and decision presentation polish

Goal: make exact proof feel like the strongest part of the product.

Work:
- improve frozen chart legibility;
- strengthen provenance hierarchy;
- make support/opposition easier to compare;
- simplify identity presentation while preserving exact values;
- improve Evidence Window header/actions;
- make “why this matters” and “what changes the view” easier to locate.

PASS:
- proof lineage remains exact;
- chart annotations remain identity-backed only;
- no current-data substitution;
- dense technical information is progressively disclosed.

## 6. P3 — Mobile and interaction refinement

Goal: make the Stream feel intentional on small screens, not merely responsive.

Work:
- topbar control sizing;
- message density;
- expanded-depth sequencing;
- drawer ergonomics;
- evidence-window fallback behavior on narrow screens;
- keyboard/focus and reduced-motion re-check;
- touch targets and scroll anchoring.

PASS:
- exact 430px acceptance;
- no horizontal overflow;
- collapsed feed remains readable with one hand;
- expanded depth does not destroy scroll position;
- drawers/windows remain dismissible and focus-safe.

## 7. P4 — Final product acceptance

Goal: close the visual/product scope with real browser proof.

Acceptance matrix:
- desktop live-empty;
- mobile live-empty;
- multi-message fixture;
- expanded message;
- capital lifecycle;
- frozen proof window;
- discovery drawer;
- settings/notification drawer;
- 1k and 10k long-session smoke;
- reduced motion;
- no-overflow;
- current backend/API parity;
- REAL_CAPITAL=0.

PASS:
- whole-repository regression passes;
- real Chromium desktop/mobile capture passes;
- no S0-S16 guarantee regresses;
- live Product can be promoted only after exact-main visual acceptance.

## 8. Current execution frontier

Active now: **P0 + P1**.

First implementation packet:
- premium vector topbar controls;
- stronger but restrained brand/shell treatment;
- deliberate-silence empty state;
- category-aware message hierarchy;
- reduced chip noise;
- clearer “proof/evidence” expansion affordance;
- desktop/mobile fixture acceptance.

P2-P4 must follow only after P0/P1 acceptance is mechanically clean.
