# R25 Slice 12 — Exact Forecast → Shadow Preview Link

Status: development candidate. REAL_CAPITAL=0.

This slice lets the Product API and GALACTECH connect an immutable R20 forecast to shadow decision-rail evidence only when the isolated shadow journal contains that exact `forecast_identity`.

## No heuristic matching

The system does not link by:
- symbol;
- timeframe;
- timestamp proximity;
- direction;
- similar proof content.

The lookup key is the lowercase 64-character immutable forecast SHA256 only.

## Journal lookup

`R25ShadowIntentJournal.read_latest_for_forecast(forecast_identity)`:
1. validates the lookup identity;
2. runs the full read-only journal verifier;
3. opens the journal again in SQLite `mode=ro`;
4. re-hashes persisted preview payloads;
5. finds only an exact `forecast_identity` payload match;
6. returns the latest matching journal record and its persisted identities.

Returned lineage includes:
- journal record;
- R22 preview;
- forecast;
- Decision Proof;
- Position Sizing bridge;
- sizing vault result;
- explicit review selection when present;
- market reference when present;
- paper decision preview identity when present;
- R22 intent identity.

Authority remains read-only/shadow-only.

## Product API

New endpoint:

`GET /api/shadow-decision-rail/forecast/{forecast_identity}`

States:
- `ready`: exact persisted identity match exists;
- `empty`: journal exists but no exact match;
- `unavailable`: journal runtime is not configured or evidence file is absent.

Invalid non-SHA lookups return HTTP 400.

## GALACTECH Evidence Room

After loading the exact R20.5 Decision Proof, GALACTECH uses its persisted `forecast_identity` to query the shadow endpoint.

If an exact match exists, the Evidence Room shows the immutable shadow lineage. If not, it explicitly says exact linkage is unavailable and that it will not infer a match heuristically.

The UI does not claim that the linked preview is:
- a fill;
- a canonical Epoch 2 NAV mutation;
- an exchange order;
- a live trade.

## Next frontier

After acceptance, add a read-only R25 operational acceptance summary that reconciles:
- decision evidence ledger;
- shadow journal replay truth;
- canonical Epoch 2 state;
- GALACTECH product exposure;

without activating canonical paper writers or production cutover.