# R25 Slice 15 — Runtime Replay Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice upgrades the exact Forecast → Capital Cycle Product link with a second,
strictly independent runtime truth source: the immutable Runtime Replay
Observation ledger.

## Product rule

A persisted cycle manifest alone is not enough to display `REPLAY VERIFIED`.

The exact forecast endpoint returns `RESTART / REPLAY = VERIFIED` only when:

- an isolated runtime replay observation store is configured and present;
- an exact forecast SHA lookup returns an observation;
- the observation is itself read-only verified;
- cycle identity matches;
- Decision Proof identity matches;
- Capital Science identity matches;
- Position Sizing identity matches;
- optional explicit review identity matches;
- R22 preview identity matches;
- referenced shadow journal record identity matches;
- cycle manifest identity matches.

Any lineage mismatch is a server-integrity failure and fails closed.

## NOT MEASURED states

The product keeps restart/replay as `NOT_MEASURED` when:
- observation runtime is not configured;
- observation file is absent;
- observation store exists but no exact forecast observation exists.

Missing evidence is never promoted from CI acceptance.

## GALACTECH Evidence Room

The R25 Capital Decision Lineage panel now includes a `RESTART / REPLAY` row.

When exact runtime evidence exists:
- status = VERIFIED;
- runtime-instance identity is shown in shortened form;
- first observation time is shown;
- replay observation time is shown.

Otherwise the panel shows NOT MEASURED with the exact reason.

The existing boundaries remain explicit:
- shadow lineage is not a fill;
- not canonical Epoch 2 NAV mutation;
- not exchange order;
- not live trade.

## Read-only boundary

The exact Product GET must preserve both:
- shadow cycle manifest bytes;
- runtime replay observation bytes.

No missing file is created by GET.

## Authority

No writer is activated. No canonical Epoch 2 mutation, fill, order, network,
credential, leverage, production activation or real capital. REAL_CAPITAL=0.

## Next frontier

After exact-head + whole-repository acceptance, create a read-only operational
acceptance summary that reconciles Decision Evidence, cycle manifest, runtime
replay observation, shadow journal, canonical Epoch 2 state and GALACTECH
exposure without activating production writers.