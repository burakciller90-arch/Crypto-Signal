# Crypto Signal — Stream S6 Real-time Backend Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S6 closes the backend delivery layer required before the one-panel UI.

## Accepted implementation

### Slice 1 — immutable read model

Merged PR #1274 / main `ef5d435b2523946baea2a98b13cb2ea890a8c1ef`.

Accepted:

- read-only query model over immutable S5 narrative persistence;
- stable keyset cursor using `event_at_ms + narrative_identity`;
- `before` cursor for upward/older-history pagination;
- `after` cursor for reconnect catch-up / polling;
- exact narrative lookup by identity;
- symbol/timeframe/story/source-kind/stance/category/importance/evidence/date/text filters;
- refresh-safe history from backend persistence;
- no offset-pagination drift;
- fail-closed invalid cursor/runtime behavior.

Exact Slice 1 acceptance:
- head `021e1cfcfa706e792cbb189626bde45709e2b263`;
- UID504 run `36165298510`;
- focused pytest/Ruff/strict mypy: PASS;
- whole-repository regression: PASS;
- Development checkout non-mutation: PASS.

### Slice 2 — live SSE transport

Merged PR #1275 / main `c2a9deca8d36c191a0a05594e20710c438febf0c`.

Accepted:

- `/api/stream/live` Server-Sent Events transport;
- first connection tails from current latest persisted message rather than replaying old history;
- empty stream remains able to receive its first future message;
- reconnect/catch-up by exact cursor;
- browser `Last-Event-ID` support;
- cursor-safe EventSource reconnect precedence;
- no duplicate delivery after an already delivered cursor;
- deterministic event id / payload framing;
- heartbeat + retry framing;
- the same search/filter contract as polling;
- `/api/stream/messages?after=<cursor>` remains the polling fallback;
- missing runtime fails closed.

Exact Slice 2 acceptance:
- head `4e87a4e53299f7054224ebe93d9a9be44c2ca77a`;
- UID504 run `36167138486`;
- focused live acceptance: PASS;
- whole-repository regression: PASS;
- Development checkout non-mutation: PASS.

## S2 activation-boundary preservation

S6 does not create or import rich historical messages.

The accepted Stream write chain remains:

```
S2 activation-bound source truth
  -> S2 Fact / Message Input
  -> S3 Story State
  -> S4 Analytical View
  -> S5 immutable Narrative
  -> S6 read / live transport
```

S2 rejects pre-activation rich source-event backfill. S5 narratives are identity-bound to that accepted upstream chain. S6 only reads and transports already-persisted S5 narratives and introduces no write/backfill or current-data reconstruction path. Therefore reconnect/history cannot bypass the S2 activation authority.

## S6 PASS criteria

Roadmap criterion: live message arrives without refresh.  
**PASS** — SSE transport is live and empty-stream first-future-message behavior is accepted.

Roadmap criterion: reconnect loses no messages.  
**PASS** — exact after/Last-Event-ID catch-up is keyset-cursor based.

Roadmap criterion: replay produces no duplicates.  
**PASS** — cursor semantics resume strictly after the delivered message identity/time pair.

Roadmap criterion: old history loads upward.  
**PASS** — stable `before` keyset pagination is accepted.

Roadmap criterion: message remains after browser refresh.  
**PASS at backend persistence contract** — UI refresh reads the same immutable S5 narrative ledger; browser-local storage is not canonical.

## Boundaries retained for later phases

S6 PASS does **not** claim:

- final one-panel messaging UI — S7;
- inline expanded sections — S8;
- floating/detachable evidence windows — S9;
- frozen visual proof completion — S10;
- canonical three-vault paper runtime / capital event projection — S11;
- final search/history interaction UX — S12;
- sound/desktop notifications — S13;
- 10k-message browser performance/accessibility — S14;
- end-to-end product acceptance — S15;
- production cutover — S16.

## Active frontier

**S6 = PASS. S7 One-Panel UI Shell is the sole active Stream implementation frontier.**
