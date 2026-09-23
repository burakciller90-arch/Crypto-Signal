# R25 Slice 11 — Shadow Decision Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice exposes the accepted shadow decision rail to Product API and GALACTECH
without converting CI acceptance into fake runtime truth.

## Product API

`GET /api/shadow-decision/status` is read-only.

If no isolated shadow journal is configured/present:
- status = unavailable;
- journal integrity = NOT_PERSISTED;
- restart/replay runtime status = NOT_MEASURED;
- Capital Science runtime status = NOT_PERSISTED;
- canonical Epoch 2 mutation = NOT_AUTHORIZED.

If a shadow journal is present:
- it is opened through the accepted R25 journal verifier;
- SQLite quick_check, metadata, preview hashes, predecessor chains and authority
  boundaries are verified;
- latest preview summaries are exposed read-only;
- exact review and market-reference identities remain visible;
- sizing lineage is reported only when an exact persisted preview references it.

The endpoint never creates a missing journal and never upgrades missing stages.

## GALACTECH System Truth

System Truth gains:
- SHADOW DECISION JOURNAL;
- REVIEWED R22 PREVIEW;
- RESTART / REPLAY RUNTIME;
- a compact R25 decision rail:
  Decision Proof -> Capital Science -> Sizing -> Review -> R22 Preview ->
  Shadow Journal -> Restart/Replay -> Canonical Epoch 2.

The rail deliberately distinguishes:
- PERSISTED / VERIFIED runtime evidence;
- NOT PERSISTED;
- NOT MEASURED;
- NOT AUTHORIZED.

CI acceptance is not shown as proof that a particular deployed runtime replay
actually happened.

## Authority

This slice is a read-only product projection. It creates no:
- paper intent;
- journal write;
- canonical Epoch 2 mutation;
- simulated fill;
- position/cash mutation;
- exchange order;
- credential/network authority;
- leverage/borrowing;
- production deployment authority.

REAL_CAPITAL remains 0.

## Next frontier

After exact-head + whole-repository acceptance, the next safe product frontier is
to persist a dedicated immutable **shadow cycle manifest** that binds Capital
Science identity, Position Sizing identity, explicit review identity, R22 preview
identity and shadow journal record identity in one artefact. Only after that exists
may Product API truthfully mark Capital Science as persisted for a specific runtime
cycle.