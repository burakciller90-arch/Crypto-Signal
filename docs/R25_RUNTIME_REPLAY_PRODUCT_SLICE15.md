# R25 Slice 15 — Runtime Replay Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice exposes the accepted immutable runtime restart/replay observation through read-only Product API and GALACTECH.

It also completes the previously partial Shadow Cycle Manifest product status surface on top of the current main lineage.

## Truth hierarchy

Three different runtime artefacts remain distinct:

1. Shadow intent journal
   - proves reviewed R22 preview evidence was persisted;
   - does not prove restart/replay.

2. Shadow cycle manifest
   - proves exact Forecast → Decision Proof → Capital Science → Position Sizing → Review → Preview → Journal lineage;
   - does not prove restart/replay.

3. Runtime replay observation
   - may say VERIFIED only when one complete persisted cycle was first INSERTED and then reproduced as exact IDEMPOTENT replay on the same immutable runtime-instance identity.

Hosted CI acceptance alone is never runtime replay evidence.

## Product API

### GET /api/shadow-cycle-manifest/status

Read-only manifest status. Capital Science and Sizing may be labelled PERSISTED only when the manifest exists and verifies.

The endpoint continues to report restart replay as NOT_PERSISTED because the manifest itself is not a replay observation.

### GET /api/runtime-replay-observation/status

States:
- ready: at least one verified runtime observation exists;
- empty: observation ledger exists and verifies but contains no observation;
- unavailable: path is unconfigured or evidence file is absent.

Only ready may expose:
`restart_replay_observation = VERIFIED`.

### GET /api/runtime-replay-observation/forecast/{forecast_identity}

Exact lower-case SHA256 lookup only.

No symbol, timeframe, direction, setup or timestamp-proximity matching is allowed.

A ready result returns the immutable observation carrying exact forecast/cycle/proof/capital/sizing/review/preview/journal/manifest identities.

## GALACTECH

Capital Center combines:
- preview-journal integrity;
- cycle-manifest integrity;
- persisted Capital Science lineage;
- persisted Position Sizing lineage;
- dedicated runtime replay observation.

The main replay badge becomes VERIFIED only from the replay-observation API, never from journal quick_check or generic read-only verification.

Evidence Room performs two exact lookups for the immutable forecast:
- exact shadow cycle;
- exact runtime replay observation.

It shows VERIFIED only when the observation matches that exact cycle identity, manifest identity and preview identity.

System Truth adds a dedicated RUNTIME REPLAY OBSERVATION card.

## Authority

Read-only projection only.

No:
- canonical Epoch 2 mutation;
- simulated fill;
- cash/position mutation;
- exchange/network/credential authority;
- order authority;
- leverage/borrowing;
- production activation.

REAL_CAPITAL=0.

## Next frontier

After exact-head and whole-repository acceptance, build an operational acceptance summary that reconciles Decision Evidence, Shadow Journal, Cycle Manifest, Runtime Replay Observation and canonical Epoch 2 runtime presence in one read-only health contract.

That summary may describe evidence availability and integrity only. It must not activate canonical writers or production execution.
