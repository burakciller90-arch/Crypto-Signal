# GALACTECH Product Rail — Archive / Proof Wall Slice 5

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
Predecessor: accepted GALACTECH Markets workspace PR #927.
REAL_CAPITAL=0.

## Scope

This slice turns the existing read-only Proof Wall API into the locked immutable archive
experience.

The product binds:

- `GET /api/archive/proof-wall?limit=500&offset=0`;
- exact immutable issuance signal freeze;
- latest appended outcome snapshot when one exists;
- exact Evidence Room drill-down by `signal_freeze_identity`.

## Core invariant

The archive always presents:

**ISSUANCE SNAPSHOT ↔ LATER OUTCOME SNAPSHOT**

The later outcome never replaces or rewrites issuance-time state.

Every loaded card keeps the original:

- symbol / timeframe / provider / market type;
- signal state and direction;
- setup type;
- confluence agreement;
- probability status;
- freeze and source-cutoff timestamps;
- full signal freeze identity.

If a later outcome exists, it is shown alongside issuance with:

- exact outcome state;
- resolution status;
- evidence class;
- coverage status;
- evaluated timestamp;
- holding horizon;
- entry-observed truth;
- highest target index;
- ambiguity/not-evaluable reason when applicable;
- exact outcome identity.

## Filter semantics

The customer-visible categories are deterministic projections of the latest outcome:

- WINNERS = `success_tp1|2|3`;
- LOSERS = `fail_sl`;
- EXPIRED = `timeout`;
- INVALIDATED = `invalidated`;
- AMBIGUOUS = `ambiguous`;
- ABSTAIN / N-E = explicit `not_evaluable` / `cancelled`, plus issuance-time
  `no_signal` or `neutral` decisions when no later outcome exists;
- UNRESOLVED = an active/watch issuance with no later outcome snapshot yet.

Unresolved is not silently counted as failure or success.

## Counts

- TOTAL IMMUTABLE uses the server-reported archive total.
- Resolved / unresolved / filter counts are labelled as counts for the currently loaded
  page.
- The current product requests the API maximum page size (500) rather than pretending a
  60-row viewport is the complete archive.

## Scientific boundaries

- losses remain visible;
- expired/invalidated/ambiguous/not-evaluable remain visible;
- evidence class is never hidden;
- no historical hit-rate is relabelled as calibrated probability;
- confluence stays agreement evidence, not probability;
- missing later outcome remains missing;
- no archive mutation/delete/order authority;
- REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
