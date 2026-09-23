# Event Risk + NLP — Slice 1: Structured Event Calendar & Safety Window

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Introduce a deterministic, point-in-time event-risk safety layer before any NLP/news
interpretation is allowed to influence downstream research.

This slice models structured calendar/event evidence only. It does not activate a live
calendar provider, does not infer market direction and does not create trading authority.

## Event contract

Each structured event freezes:

- provider event ID;
- title;
- category;
- scheduled event time;
- affected assets (empty means provider/global scope);
- source provider;
- source quality;
- source timestamp;
- ingestion timestamp;
- adapter version;
- deterministic event identity.

Supported event categories include inflation, central-bank/rate decisions, employment,
regulatory, exchange/security, listing, delisting and bounded OTHER.

## Coverage contract

A separate `EventCalendarCoverage` freezes what one provider actually covered at one
observation time:

- past/future coverage bounds;
- covered event categories;
- provider and source quality;
- observed-at time;
- adapter version.

A CLEAR state is valid only when calendar coverage is present, fresh and complete for the
required policy horizon/categories. Missing data is never interpreted as “no event”.

## Versioned safety-window policy

Default Slice 1 research policy:

- caution lead: 60 minutes;
- EVENT_BLOCK: 15 minutes before through 15 minutes after scheduled time;
- post-event stabilization: next 30 minutes;
- coverage freshness maximum: 6 hours.

These durations are versioned research parameters, not universal market laws.

Possible states in this slice:

- `CLEAR`;
- `PRE_EVENT_CAUTION`;
- `EVENT_BLOCK`;
- `POST_EVENT_STABILIZATION`;
- `DEGRADED_DATA`.

Downstream ABSTAIN policy is a later composition layer; this slice itself supplies bounded
event-risk evidence.

## PIT / causal boundaries

- Only event records whose source and ingestion timestamps are available by `as_of_ms`
  may be consumed.
- Only events relevant to the requested asset and active policy horizon are validated and
  frozen.
- Future/late or other-asset events cannot rewrite a historical freeze.
- A calendar coverage record observed after `as_of_ms` is not frozen into history.
  It is treated exactly like unavailable coverage, producing deterministic DEGRADED_DATA
  without leaking the future coverage identity.
- Stale, horizon-incomplete, category-incomplete or unverified coverage fails closed.
- A relevant unverified event inside the active horizon degrades the state.
- Relevant provider/category mismatch and duplicate provider event IDs fail closed.

## Scientific boundaries

- Event Risk is safety/context/veto evidence, not a directional price signal.
- EVENT_BLOCK means the configured research policy blocks ordinary activation near the
  event; it does not predict a positive or negative move.
- The ±15 minute block is an initial versioned research rule and must later be evaluated,
  not assumed optimal.
- No text sentiment/NLP claim is made in Slice 1.
- No live provider/API/credential collector is activated.
- No probability, confluence promotion, capital sizing or order authority is produced.
- REAL_CAPITAL=0.

## Acceptance checklist

1. Deterministic event, coverage, analysis and freeze identities.
2. CLEAR requires complete verified coverage.
3. Explicit PRE_EVENT_CAUTION / EVENT_BLOCK / POST_EVENT_STABILIZATION boundaries.
4. Missing/future calendar coverage yields deterministic DEGRADED_DATA without future
   identity leakage.
5. Stale/incomplete/unverified coverage fails closed.
6. Unverified relevant events degrade a verified calendar.
7. Future/late/other-asset events cannot rewrite historical freezes.
8. Out-of-horizon irrelevant wrong-context records cannot poison current PIT evidence.
9. Relevant context mismatch, duplicates, tampering and invalid policy fail closed.
10. Focused pytest/Ruff/mypy plus full repository Python/JavaScript/freshness regression.
11. Temporary hosted workflow removed after PASS.

Next Event Risk frontier after Slice 1: source-bounded News/NLP event evidence with
publication time, ingest time, affected assets, category and explicit source/confidence
quality, followed by circuit-breaker composition with market-data degradation signals.

The user-requested wake/lease pause remains authoritative and must not be re-armed.


## Canonical maintenance boundary

This file and `tests/test_event_risk.py` are the single canonical Slice 1 contract and
acceptance suite. Parallel duplicate calendar docs/tests/workflows were reconciled and
removed before acceptance so later agents have one source of truth.
