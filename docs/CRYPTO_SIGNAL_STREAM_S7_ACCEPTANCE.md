# Crypto Signal — Stream S7 One-Panel UI Shell Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S7 closes the browser-rendered messaging shell required before inline message depth.

## Accepted implementation

Merged PR #1280 / main `f25ee7e3f6f81097b61f1f33136d3d71001d50f4`.

Accepted:

- isolated `/stream-preview` Stream V1 preview surface;
- deployed GALACTECH V2 remains the production root/fallback;
- Turkish-first light, low-noise, one-panel messaging shell;
- compact collapsed narrative bubbles from exact S5 persisted narrative payloads;
- S6 SSE live delivery with polling fallback;
- cursor catch-up and duplicate-safe append behavior;
- upward history loading without browser-local canonical history;
- bottom-anchor behavior plus buffered `N yeni mesaj` affordance when reading history;
- temporary search/filter drawer;
- settings/sound control surface without prematurely enabling S13 sound;
- floating-window layer placeholder without prematurely implementing S9;
- dashboard runtime binding to the canonical Stream ledger;
- deterministic browser fixtures explicitly labeled as non-live truth;
- existing UID504 Chromium visual-snapshot path reused and extended;
- exact CDP mobile viewport capture with horizontal-overflow rejection.

## Exact-head acceptance

Accepted implementation head:
- `65dc2e3dcf141940c8d93ba29d0b988e8d3dd3d3`.

UID504 run:
- `36170910074` — **PASS**.

The accepted run proved:
- exact source checkout;
- focused Stream/UI/runtime tests;
- whole-repository regression;
- rendered desktop mixed stream;
- rendered incoming-message state;
- rendered old-history + unread state;
- rendered search/filter drawer;
- rendered degraded/reconnect state;
- exact mobile viewport acceptance;
- Development checkout non-mutation.

Visual artifact:
- `stream-s7-visual-snapshot-36170910074`.

The mobile acceptance uses a real 430x860 emulated CSS viewport through Chromium CDP and rejects horizontal overflow. The accepted capture records `innerWidth=430` with document `scrollWidth=430`.

## S7 PASS criteria

Roadmap criterion: desktop feels like a premium messaging application.  
**PASS** — exact-head real-browser renders show the messaging-first shell without dashboard chrome.

Roadmap criterion: no unnecessary dashboard chrome.  
**PASS** — the Stream preview has no multi-screen sidebar or separate product sections.

Roadmap criterion: no separate product sections.  
**PASS** — one persistent stream is the primary content surface.

Roadmap criterion: new-message behavior matches messaging UX.  
**PASS** — new messages stay bottom-anchored only when the user is already near the bottom; otherwise unread count is buffered without forced scrolling.

Roadmap criterion: old-message scrolling remains stable.  
**PASS** — upward keyset history preserves viewport position and the rendered history fixture is accepted.

## Truth and safety boundaries

S7 does not mutate source truth. It reads exact immutable S5 narratives through the accepted S6 transport/read model.

Visual fixture messages are never presented as live market evidence: fixture mode is visibly labeled `GÖRSEL TEST FIXTURE · CANLI PİYASA GERÇEĞİ DEĞİL`.

S7 introduces no historical synthesis/backfill authority and no real-money/exchange authority.

## Boundaries retained for later phases

S7 PASS does **not** claim:

- final inline SIMPLE / PRO / INTELLIGENCE / DECISION / trade geometry / CAPITAL expansion — S8;
- evidence window manager / detach — S9;
- frozen visual proof completion — S10;
- canonical three-vault capital story completion — S11;
- complete search/filter/history interaction — S12;
- notification sound/browser notifications — S13;
- 10k-message long-session performance/accessibility completion — S14;
- end-to-end product acceptance — S15;
- product-root cutover — S16.

## Active frontier

**S7 = PASS. S8 Expandable Message Experience is the sole active Stream implementation frontier.**
