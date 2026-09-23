# R25 Slice 11 — Shadow Decision Rail Product Truth

Status: development candidate. REAL_CAPITAL=0.

This slice exposes the accepted shadow decision journal through the read-only Product API and GALACTECH without upgrading shadow evidence into canonical paper activity.

## Product API

New endpoint:

`GET /api/shadow-decision-rail/status`

The runtime path is configured only by:
- explicit `create_app(..., shadow_intent_journal_path=...)`; or
- `CRYPTO_SIGNAL_SHADOW_INTENT_JOURNAL_PATH`.

There is no implicit default path. If the runtime is not explicitly bound, the endpoint returns `unavailable` rather than inventing shadow activity.

When a journal is present the endpoint calls only `R25ShadowIntentJournal.verify_read_only()`, which opens SQLite in read-only mode and exposes:
- journaled preview count;
- per-vault latest journal record identities;
- SQLite quick-check truth;
- read-only replay verification;
- authority boundaries.

The endpoint always states:
- semantic = SHADOW_RESEARCH_ONLY;
- canonical_epoch2_mutation = false;
- production_authority = false;
- read_only = true;
- REAL_CAPITAL=0.

## GALACTECH

Capital Center gains a separate Shadow Decision Rail panel next to — never merged into — canonical Epoch 2 accounting.

System Truth gains a SHADOW DECISION RAIL health card.

If no shadow journal runtime is configured or the file is absent, the UI shows NOT EXPOSED / unavailable truth. It does not infer zero activity and does not label the rail LIVE or TRADING.

If verified evidence exists, GALACTECH may show:
- preview record count;
- read-only replay VERIFIED;
- quick_check PASS;
- per-vault latest journal-record identity;
- canonical write DISABLED;
- production authority DISABLED;
- real capital DISABLED.

## Boundary

A shadow intent preview is not:
- a simulated fill;
- an R21 canonical NAV mutation;
- an exchange order;
- a live-trading event.

No production cutover, canonical writer activation, credentials, leverage, wake/lease change or real capital is authorized here.

Next frontier after acceptance: update the Command Center to link an immutable forecast/proof to its latest available shadow-rail lineage only when exact persisted cross-ledger identity evidence exists. If that cross-reference is not persisted, the UI must keep the two rails separate rather than infer a match.