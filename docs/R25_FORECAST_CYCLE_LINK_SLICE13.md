# R25 Slice 13 — Exact Forecast → Capital Cycle Product Link

Status: development candidate. REAL_CAPITAL=0.

This slice links one immutable R20 forecast to its persisted R25 shadow capital cycle using exact SHA256 identity only.

## Source of truth

The lookup source is the accepted immutable Shadow Cycle Manifest, not symbol/time proximity and not the preview journal alone.

The exact lineage exposed is:

R20 forecast
→ R20.5 Decision Proof
→ Capital Science
→ Position Sizing
→ optional explicit review
→ R22 preview
→ referenced shadow-intent journal record
→ Shadow Cycle Manifest.

## No heuristic matching

The system never links cycles by:
- asset symbol;
- timeframe;
- direction;
- close timestamp proximity;
- matching setup labels;
- similar evidence.

Only exact lower-case 64-character `forecast_identity` is accepted.

## Product API

`GET /api/shadow-decision-rail/forecast/{forecast_identity}`

States:
- `ready`: an exact persisted cycle manifest exists;
- `empty`: manifest runtime exists but no exact identity match exists;
- `unavailable`: manifest runtime is unconfigured or the evidence file is absent.

Malformed non-SHA lookup returns HTTP 400 before runtime access.

The endpoint is read-only and byte-stability is an acceptance requirement.

A manifest references the exact shadow journal record identity but does not by itself prove that the journal file is currently mounted. Therefore the API explicitly returns `journal_runtime_verified_here=false`; current journal runtime truth remains the responsibility of the separate shadow-rail status endpoint.

## GALACTECH Evidence Room

After the exact R20.5 Decision Proof is loaded, GALACTECH reads its immutable `forecast_identity` and requests the exact cycle endpoint.

When present, Evidence Room shows:
- forecast;
- Decision Proof;
- Capital Science;
- Position Sizing;
- explicit review identity;
- reviewed sizing method;
- R22 preview;
- referenced shadow journal record;
- cycle manifest identity.

When absent, the UI explicitly says no exact cycle was persisted and refuses heuristic matching.

The surface does not claim a fill, canonical Epoch 2 NAV mutation, exchange order or live trade.

## Authority

No writer is activated. No canonical paper capital is mutated. No order/network/credential authority exists. REAL_CAPITAL=0.

## Next frontier

After exact-head + whole-repository acceptance, add a separately persisted runtime replay observation that can prove a particular deployed/runtime cycle was replayed idempotently after restart. CI acceptance alone must never be displayed as deployed-runtime replay proof.