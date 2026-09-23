# R25 Slice 12 — Immutable Shadow Cycle Manifest

Status: development candidate. REAL_CAPITAL=0.

This slice persists one immutable lineage record for the accepted shadow decision
cycle without touching canonical Epoch 2.

The manifest binds:
- immutable forecast identity;
- R20.5 Decision Proof identity;
- Capital Science bridge identity;
- Position Sizing bridge identity;
- explicit review selection identity when one exists;
- R22 preview identity;
- isolated shadow intent journal record identity;
- vault, reviewed method and event time.

## Isolation

The manifest uses a dedicated `*.shadow-cycle.sqlite3` database.

Initialization fails closed if the target database contains any non-manifest
application table. The manifest never imports or calls canonical Epoch 2
accounting writers.

## Append-only integrity

Every row has a manifest SHA256 identity over the exact lineage payload and the
previous per-vault manifest identity.

Exact cycle replay is idempotent. A different payload cannot reuse the same
cycle identity.

Per-vault event time is strictly increasing. Backfill and same-time forks fail
closed.

UPDATE and DELETE are blocked by SQLite triggers.

Read-only verification runs:
- SQLite `PRAGMA quick_check`;
- exact metadata validation;
- payload digest verification;
- record identity verification;
- per-vault predecessor-chain verification;
- authority-boundary verification.

## Product meaning

This manifest is the missing persisted bridge between:
Decision Proof -> Capital Science -> Position Sizing -> Review -> R22 Preview ->
Shadow Intent Journal.

It lets a later Product API truthfully say that Capital Science and Sizing
lineage were persisted for a specific runtime cycle instead of inferring them
from CI acceptance.

It still does **not** prove that a restart replay happened on the deployed
runtime. That requires a separate persisted replay observation.

## Authority

No:
- canonical Epoch 2 mutation;
- simulated fill;
- cash/position mutation;
- exchange/network/credential access;
- order authority;
- leverage/borrowing;
- production activation.

REAL_CAPITAL=0.