# Crypto Signal — Stream S9 Evidence Window Manager Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S9 closes the reusable deep-evidence window framework required before frozen visual proof.

## Accepted implementation

Merged PR #1285 / main `9492d9347f3a0170f9da2a73c2e206998d3eb3f8`.

Accepted:
- reusable floating evidence-window framework over the Stream;
- draggable and resizable windows;
- minimize, close and pin controls;
- multiple simultaneous windows;
- explicit focus/z-order handling;
- session-local geometry/state persistence and restore;
- exact-identity detach/pop-out route at `/stream-evidence`;
- Liquidity, Order Flow, Derivatives, On-chain, Geometry, Decision, Capital, Event Risk and Proof window types;
- window content from the S8 verified persisted message-detail projection;
- exact source evidence identities shown when present;
- deterministic context education through the existing education API;
- message-specific “neden önemli?” derived only from the same persisted message detail;
- Stream remains visible/usable beneath windows;
- no S10 frozen visual coordinates/drawings are invented early.

## Exact-head acceptance

Accepted head:
- `8fdcc0a4ed7320db1b257fd3827656da3df75c76`.

UID504 run:
- `36175446260` — **PASS**.

The accepted run proved:
- exact source checkout;
- focused S9 acceptance;
- whole-repository regression;
- three simultaneous exact-message windows;
- drag movement under viewport-edge clamping;
- resize movement;
- pin and minimize state;
- session persistence for three windows;
- exact narrative/kind detach URL;
- Stream remains visible while windows are open;
- exact 430x860 mobile viewport with no horizontal overflow;
- Development checkout non-mutation.

Visual artifact:
- `stream-s9-visual-snapshot-36175446260`.

## S9 PASS criteria

Roadmap criterion: user can open several evidence windows and continue scrolling.  
**PASS** — multi-window Chromium fixture keeps the Stream viewport visible behind three simultaneous windows.

Roadmap criterion: detached chart/evidence remains tied to exact message identity.  
**PASS** — detach URL carries exact lower-SHA256 narrative identity plus explicit evidence kind and detached page re-reads that exact persisted detail.

Roadmap criterion: closing/reopening does not alter underlying evidence.  
**PASS** — window state is client-side only; evidence truth is re-read from immutable persisted detail. Local storage persists geometry/UI state, never evidence payload.

## Truth and safety boundaries

S9 does not create market facts, recompute historical evidence, or write to canonical ledgers. Missing evidence remains explicit.

The Proof window preserves exact forecast/proof identities but does not claim S10 frozen OHLC coordinates, annotations, order-book visuals or CVD plots.

## Active frontier

**S9 = PASS. S10 Frozen Visual Proof is the sole active Stream implementation frontier.**
