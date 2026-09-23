# Event Risk + NLP Intelligence — Slice 1: Structured Calendar Safety Layer

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Introduce a point-in-time Event Risk safety layer before news/NLP enrichment.

This slice answers only:

- is the structured event calendar coverage trustworthy enough at this PIT cutoff?;
- is a relevant scheduled event approaching, inside the bounded block window, or just past?;
- should the system remain clear, cautious, blocked, stabilizing, or degraded?

It does **not** predict event outcomes or price direction.

## Structured event contract

Every event freezes:

- provider event id;
- title;
- category;
- scheduled event timestamp;
- affected assets, or empty for market-wide/global context;
- source provider;
- source quality;
- source timestamp;
- ingestion timestamp;
- adapter version;
- deterministic event identity.

Initial categories include:

- inflation;
- central-bank/rate decisions;
- employment;
- regulatory;
- exchange/security incidents;
- listings;
- delistings.

## Coverage proof

Absence of an event is not enough to claim `CLEAR`.

The engine requires PIT-available `EventCalendarCoverage` that:

- spans the complete past stabilization horizon;
- spans the complete future caution horizon;
- covers all configured required categories;
- is fresh under a versioned maximum-age rule;
- comes from a non-unverified coverage source.

If coverage is absent, future-only, stale, horizon-incomplete, category-incomplete or
unverified, the engine resolves to `DEGRADED_DATA`.

Future coverage is not inserted into a historical freeze.

## Initial versioned timing policy

The defaults are research policy, not universal laws:

- caution lead: 60 minutes;
- event block begins: 15 minutes before scheduled time;
- event block ends: 15 minutes after scheduled time;
- post-event stabilization: 30 additional minutes.

States:

- `CLEAR`;
- `PRE_EVENT_CAUTION`;
- `EVENT_BLOCK`;
- `POST_EVENT_STABILIZATION`;
- `DEGRADED_DATA`.

When multiple relevant events overlap, the more restrictive state has precedence.

## Scientific and safety boundaries

- A scheduled event is not a prediction of its result.
- Event Risk is a veto/context layer, not a bullish/bearish signal.
- A ±15 minute block window is only the initial versioned research rule.
- A global event may affect all assets; asset-specific events apply only to declared assets.
- Unverified active-horizon event evidence degrades the state rather than becoming an event block.
- Future, late-ingested, out-of-horizon or other-asset evidence cannot rewrite the current PIT freeze.
- Eligible wrong-provider/category evidence fails closed.
- No live news/calendar provider, credential or collector is activated in this slice.
- No probability, capital sizing or trading authority is created.
- REAL_CAPITAL=0.

## Acceptance checklist

1. Deterministic structured-event and coverage identities.
2. Complete verified empty coverage produces `CLEAR`, not fabricated missing-data confidence.
3. Separate caution, block and post-event stabilization states.
4. Event-block precedence under overlapping events.
5. Global versus asset-specific event filtering.
6. Missing/future/stale/incomplete/unverified coverage fails closed to `DEGRADED_DATA`.
7. Future coverage is not consumed in a historical freeze.
8. Future/late/out-of-horizon wrong-context events cannot rewrite history.
9. Eligible provider mismatch and duplicate provider ids fail closed.
10. Identity tampering and invalid timing policy fail closed.
11. Focused pytest/Ruff/mypy, then full repository Python/JavaScript/freshness regression.
12. Remove temporary hosted workflow after PASS.

News/NLP evidence, provider disagreement, abnormal market-quality triggers and ABSTAIN policy
remain separate later Event Risk slices.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
