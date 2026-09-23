# WC0 Runtime Wiring and Deployment Acceptance

Status: development candidate. REAL_CAPITAL=0.

This slice closes a production integration gap discovered after the GALACTECH root cutover merge.

## Problem

The accepted Product API supports Decision Evidence, canonical Epoch 2, Shadow Intent Journal, Shadow Cycle Manifest, Runtime Replay Observation, Market Tape and Cold Archive.

However the production dashboard launcher previously passed only the legacy ledger/paper/candle paths. With an explicit signal-ledger path, unpassed R25 sources correctly stayed unconfigured.

The allowlisted UID504 product deployment command also retained legacy root-page acceptance strings and did not explicitly fetch the target commit into the Product clone before detached checkout.

## Fix

The production launcher now derives exact read-only runtime paths from the supplied signal ledger's runtime root:

- runtime/decision/decision_evidence.sqlite3
- runtime/paper/paper_fund_epoch2.sqlite3
- runtime/r25/r25.shadow-intent.sqlite3
- runtime/r25/r25.shadow-cycle.sqlite3
- runtime/r25/r25.shadow-replay.sqlite3
- runtime/market_tape/market_tape.sqlite3
- runtime/market_tape/cold

Explicit CLI overrides remain authoritative.

Missing files remain missing evidence; the launcher does not create them.

The UID504 productdeploy command now:
- fetches current main into both Development and Product clones;
- requires target == origin/main;
- fast-forwards Development to the exact target;
- checks out Product at the exact target;
- retains rollback to the previous Product head on any failure;
- validates current GALACTECH root == /galactech;
- validates /legacy rollback surface;
- validates read-only R25 Operational Truth;
- runs SSD topology/SQLite acceptance;
- verifies continuity pause remains preserved.

## Authority

This slice does not deploy by itself.

No order/credential authority, no real capital, no wake resume and no canonical paper mutation are introduced.
