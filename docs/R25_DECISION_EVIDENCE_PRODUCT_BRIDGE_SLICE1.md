# R25 — Immutable Decision Evidence Product Bridge / Slice 1

Status: development candidate  
Parent: v1.1 world-class completion program  
Safety invariant: REAL_CAPITAL=0

## Why this slice exists

R20 Immutable Forecast Stream and R20.5 Decision Proof / Live Intelligence Feed were
accepted as deterministic in-memory contracts. GALACTECH intentionally did not pretend
that the legacy signal-freeze endpoint was the new Decision Proof contract. As a result,
accepted M2-M6 / Event / probability evidence could exist in code without a persistent,
customer-readable R20/R20.5 lineage.

This slice closes the persistence and read-only product-adapter gap. It does **not** claim
that the complete 7/24 production decision orchestrator exists yet.

## Immutable decision evidence ledger

New append-only SQLite authority:

- `r20_forecasts`;
- `r20_resolutions`;
- `r20_5_decision_proofs`;
- `r20_5_live_feed_events`.

Every stored payload is canonical JSON plus SHA-256 digest. UPDATE and DELETE fail closed.
Forecast chronology, one-proof-per-forecast binding, one-resolution-per-forecast binding
and issuance/resolution feed ordering are enforced.

The ledger cannot grant:

- exchange/broker/network authority;
- credential authority;
- leverage or borrowing;
- production authority;
- real capital.

`REAL_CAPITAL=0` remains mandatory.

## Read-only Product API

New customer-readable surfaces:

- `GET /api/decision-evidence/status`;
- `GET /api/decision-proof/{signal_freeze_identity}`;
- `GET /api/intelligence-feed`.

Reads use SQLite `mode=ro` + `PRAGMA query_only=ON`. A missing decision ledger is never
initialized by a Product GET. Missing evidence remains UNAVAILABLE / EMPTY.

## GALACTECH binding

The existing Markets layer discipline changes from a blanket hard-coded NOT EXPOSED state
to exact proof-bound visibility:

- LIQ -> `liquidity_map` + `liquidation_map`;
- FLOW -> `order_book` + `order_flow_cvd`;
- DERIV -> `derivatives`;
- ONCHAIN -> `onchain`.

If the exact selected immutable signal has no persisted R20.5 Decision Proof, the layer
remains NOT PERSISTED. It is never synthesized from unrelated fields.

Evidence Room can append the exact persisted R20.5 cross-domain proof beside the legacy
frozen signal evidence without relabelling one as the other.

Intelligence and System Truth can now expose persisted feed/proof availability. This does
not mean Market Tape, event-source providers, latency or universal freshness are measured.

## Cross-regression hardening

Full-repository acceptance exposed a pre-existing SQLite connection-lifecycle sensitivity in
the R21 Epoch 2 read-only byte-preservation test. The accounting semantics were unchanged;
the fix makes writer/read-only connections close explicitly so committed WAL state is
settled before byte-preservation assertions. This is now part of the focused gate rather
than being left as order-dependent test behavior.

## Explicit non-goals

This slice does not:

- activate a live production writer;
- compose M2-M6/Event/R19 automatically for every market tick;
- enable the Bybit liquidation collector;
- activate on-chain/news provider credentials;
- cut over GALACTECH to production root;
- merge or deploy PR #932;
- activate real money.

The next architectural frontier after hosted acceptance is the **R25 decision runtime
orchestrator**: exact point-in-time evidence composition -> M6/Event -> optional R19
authorization -> R20 forecast -> R20.5 proof/feed -> bounded paper decision lineage.
That runtime must be proven in development/replay before any production activation.
