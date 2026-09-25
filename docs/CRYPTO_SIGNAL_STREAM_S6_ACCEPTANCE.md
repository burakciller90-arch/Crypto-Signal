# Crypto Signal — Stream S6 Real-time Stream Backend Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S6 closes the backend delivery layer required before the final one-panel Stream UI.

## Accepted implementation

### Slice 1 — immutable cursor/read model

Merged PR #1274 / main commit `ef5d435b2523946baea2a98b13cb2ea890a8c1ef`.

Accepted:
- append-only read model over immutable S5 narrative persistence;
- stable keyset cursor ordered by `event_at_ms + narrative_identity`;
- upward history pagination with `before`;
- reconnect/polling catch-up with `after`;
- exact narrative lookup;
- symbol, timeframe, story, source-kind, stance, category, importance, evidence-domain, time-window and full-text filters;
- polling fallback through `/api/stream/messages`;
- fail-closed behavior when Stream persistence is unavailable;
- no offset-pagination drift;
- read-only verification of narrative identity, digest, schema, engine version and REAL_CAPITAL boundary.

Exact acceptance:
- tested head `021e1cfcfa706e792cbb189626bde45709e2b263`;
- UID504 run `36165298510`;
- exact-source isolation PASS;
- focused pytest PASS;
- Ruff PASS;
- strict mypy PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

### Slice 2 — live SSE delivery and reconnect

Merged PR #1275 / main commit `c2a9deca8d36c191a0a05594e20710c438febf0c`.

Accepted:
- server-sent event delivery through `/api/stream/live`;
- deterministic SSE message event ids derived from exact Stream cursors;
- first connection tails from the current immutable head instead of replaying old history;
- an initially empty Stream remains anchored at an origin cursor and receives the first later message;
- browser reconnect uses `Last-Event-ID` without replaying the already delivered message;
- when an original `after` query cursor coexists with a reconnect header, the newer exact boundary wins and an older header cannot regress the session;
- catch-up is strict `>` cursor semantics and therefore de-duplicates replay;
- bounded live batches preserve chronological order;
- retry framing and heartbeat comments keep the transport reconnect-friendly;
- SSE filters reuse the same query contract as polling;
- missing runtime fails closed with HTTP 503;
- polling remains an accepted fallback rather than a second source of truth.

Exact acceptance:
- tested head `4e87a4e53299f7054224ebe93d9a9be44c2ca77a`;
- UID504 run `36167138486`;
- exact-source isolation PASS;
- focused pytest/Ruff/strict mypy PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

## Accepted S6 delivery model

```
immutable S5 narrative ledger
  -> S6 keyset read model
  -> /api/stream/messages polling/history/search
  -> /api/stream/live SSE tail
  -> cursor / Last-Event-ID reconnect
  -> exact catch-up without duplicate replay
  -> S7 browser Stream shell
```

Neither transport is allowed to mutate canonical Stream truth.

## S6 PASS criteria

Roadmap criterion: live message arrives without refresh.  
**PASS** — the SSE endpoint tails immutable persistence and emits new records without a page refresh.

Roadmap criterion: reconnect loses no messages.  
**PASS** — exact cursor / `Last-Event-ID` catch-up resumes strictly after the newest delivered boundary.

Roadmap criterion: replay produces no duplicates.  
**PASS** — live catch-up is strict keyset `after` pagination and regression tests cover reconnect precedence.

Roadmap criterion: old history loads upward.  
**PASS** — stable `before` keyset pagination is accepted and does not drift when newer messages arrive.

Roadmap criterion: message remains after browser refresh.  
**PASS** — the Product APIs read immutable backend persistence; browser state is not the source of message existence.

## Boundaries retained for later phases

S6 PASS does not claim:
- final one-panel visual shell or collapsed-message interaction — S7;
- expanded SIMPLE/PRO/INTELLIGENCE/DECISION/CAPITAL experience — S8;
- floating evidence windows — S9;
- frozen visual proof expansion — S10;
- canonical three-vault forward paper execution runtime — S11;
- final search/history interaction polish — S12;
- sound/browser notification behavior — S13;
- long-session/accessibility acceptance — S14;
- end-to-end product acceptance or production cutover — S15/S16;
- real-money trading authority.

## Active frontier

**S6 = PASS. S7 One-Panel UI Shell is the sole active Stream implementation frontier.**
