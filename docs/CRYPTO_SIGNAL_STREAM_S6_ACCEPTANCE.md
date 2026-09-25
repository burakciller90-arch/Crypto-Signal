# Crypto Signal — Stream S6 Real-time Stream Backend Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S6 closes the read/delivery layer required before the one-panel messaging UI.

## Accepted implementation

### Slice 1 — append-only Stream read model

Merged PR #1274 / main commit `ef5d435b2523946baea2a98b13cb2ea890a8c1ef`.

Accepted:
- stable keyset cursor based on exact `event_at_ms + narrative_identity`;
- opaque versioned cursor encode/decode;
- newest-history read;
- older-history `before` pagination;
- reconnect/catch-up `after` pagination;
- exact narrative lookup;
- deterministic de-duplication through exclusive cursor semantics;
- search/filter contract for symbol, timeframe, story, source kind, effective stance, category, importance, evidence domain, date range and full text;
- polling fallback via `/api/stream/messages`;
- read-only missing-runtime behavior;
- no offset-pagination drift;
- immutable S5 narrative payload verification on read.

Exact acceptance:
- tested head `021e1cfcfa706e792cbb189626bde45709e2b263`;
- UID504 run `36165298510`;
- exact-source isolation PASS;
- focused pytest/Ruff/strict mypy PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

### Slice 2 — live SSE transport

Merged PR #1275 / main commit `c2a9deca8d36c191a0a05594e20710c438febf0c`.

Accepted:
- `/api/stream/live` Server-Sent Events transport;
- every delivered message carries an exact opaque Stream cursor as SSE `id`;
- browser `Last-Event-ID` reconnect support;
- explicit `after` cursor support;
- reconnect chooses the furthest safe resume boundary and never moves backwards;
- catch-up is exclusive of the already-delivered message;
- default first connection tails from current latest message rather than replaying history;
- empty-stream sessions anchor at a deterministic origin cursor so the first arriving messages are not lost or reversed;
- heartbeat and retry framing;
- same search/filter semantics as polling transport;
- finite `follow=false` diagnostic/acceptance mode without changing default live behavior;
- polling fallback remains available if SSE is unavailable;
- missing runtime fails closed;
- request disconnect stops the async live generator;
- no duplicate parallel live-session implementation remains.

Exact acceptance:
- tested head `4e87a4e53299f7054224ebe93d9a9be44c2ca77a`;
- UID504 run `36167138486`;
- exact-source isolation PASS;
- focused pytest/Ruff/strict mypy PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

A duplicate later PR #1276 was closed without merge because PR #1275 had already merged the same accepted implementation head.

## Accepted S6 pipeline

```
immutable S5 Narrative Ledger
  -> S6 verified read model
  -> stable keyset cursor
  -> history / exact lookup / search-filter
  -> polling fallback
  -> SSE live transport
  -> Last-Event-ID reconnect/catch-up
  -> S7 one-panel UI
```

S6 transports persisted narrative truth. It does not rerender historical messages and it does not create new market facts.

## S6 PASS criteria

Roadmap criterion: live message arrives without refresh.  
**PASS** — SSE tail transport polls the immutable ledger and emits newly appended accepted narratives without page refresh.

Roadmap criterion: reconnect loses no messages.  
**PASS** — exact message cursor is emitted as SSE `id`; `Last-Event-ID` / `after` resume uses exclusive keyset catch-up.

Roadmap criterion: replay produces no duplicates.  
**PASS** — cursor boundary is exclusive and accepted reconnect tests prove delivered identities are not replayed.

Roadmap criterion: old history loads upward.  
**PASS** — stable `before` keyset pagination is accepted and remains stable when newer messages arrive.

Roadmap criterion: message remains after browser refresh.  
**PASS** — Product transport reads append-only persisted S5 Narrative Ledger records; browser state is not the source of message history.

## Activation / authority boundary

S6 does not create or backfill Stream truth. It exposes only narratives already accepted through the S2→S5 immutable lineage. The S2 forward activation boundary therefore remains upstream authority; S6 has no write/backfill path that can manufacture pre-activation rich history.

## Boundaries retained for later phases

S6 PASS does **not** claim:
- final messaging UI — S7+;
- compact expandable message experience — S8;
- floating/detachable evidence windows — S9;
- expanded frozen visual proof — S10;
- canonical three-vault forward paper execution integration — S11;
- advanced search UI / saved views — S12;
- notification sound/settings — S13;
- long-session virtualization/performance acceptance — S14;
- accessibility/human usability acceptance — S15;
- production Stream cutover — S16;
- real-money authority.

## Active frontier

**S6 = PASS. S7 One-Panel UI Shell is the sole active Stream implementation frontier.**
