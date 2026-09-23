# R25 Slice 13 — Shadow Cycle Manifest Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice exposes the accepted immutable shadow cycle manifest through a
dedicated read-only Product API and GALACTECH truth surface.

## Product API

`GET /api/shadow-cycle-manifest/status` reads only an explicitly configured
manifest path or `CRYPTO_SIGNAL_SHADOW_CYCLE_MANIFEST_PATH`.

There is no implicit runtime file creation.

If the manifest is absent:
- status remains unavailable;
- Capital Science lineage = NOT_PERSISTED;
- Sizing lineage = NOT_PERSISTED;
- restart/replay observation = NOT_PERSISTED.

If present:
- SQLite quick_check must pass;
- manifest metadata and every payload hash must verify;
- per-vault predecessor chains must verify;
- latest immutable cycle lineage is exposed read-only;
- Capital Science and Position Sizing lineage may be labelled PERSISTED because
  their exact identities are now inside the manifest.

## Important replay boundary

A cycle manifest is **not** a persisted observation that the deployed runtime
was restarted and replayed.

Therefore this slice always reports:

`restart_replay_observation = NOT_PERSISTED`

until a separate accepted replay-observation artefact exists.

## GALACTECH

Capital Center Shadow Decision Rail now distinguishes:
- preview-journal integrity;
- cycle-manifest integrity;
- persisted Capital Science lineage;
- persisted Sizing lineage;
- restart/replay observation status;
- canonical Epoch 2 authority.

System Truth gets a dedicated SHADOW CYCLE MANIFEST card.

## Authority

Read-only projection only. No:
- canonical Epoch 2 mutation;
- paper fill/cash/position mutation;
- exchange/network/credential authority;
- order authority;
- leverage/borrowing;
- production activation.

REAL_CAPITAL=0.

## Next frontier

Persist a separate append-only replay-observation ledger. An observation must
bind one accepted cycle-manifest identity and prove that an exact replay
produced the same cycle/preview/journal lineage. Only then may Product Truth
show restart/replay as observed for that runtime cycle.