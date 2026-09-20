# ADR 0021 — Immutable Live Ledger and Forward Evidence Clock

Status: Accepted for implementation
Date: 2026-09-20
REAL_CAPITAL: 0

## Purpose
The Immutable Live Ledger is the boundary between analysis and untouched-forward evidence.

A ledger freeze records what the system knew and decided at one real observation time.
Later market outcomes and lifecycle events append new records.
They never rewrite the original decision.

## Two identities

### Signal freeze identity
SignalDecision.freeze_identity identifies the canonical decision object.

### Decision bundle identity
DecisionFreezeBundle.bundle_identity is SHA256 over the complete canonical audit payload:
- schema version
- SignalDecision
- ConfluenceAnalysisResult
- selected neutral MethodologyEvidence
- raw Price Action result
- raw Harmonic result
- raw Elliott result
- every closed/observed candle consumed by the decision run

The bundle identity is broader than the signal identity.

A signal freeze identity may never be rebound to a different bundle.

## Canonical source cutoff
Every bundle stores source_cutoff_open_time_ms:
the open time of the newest closed candle consumed by the run.

V1 allows at most one immutable decision freeze for:
exchange + market type + symbol + timeframe + source_cutoff_open_time_ms.

This prevents a recurring watcher from writing duplicate decisions for the same
market boundary with a later REST ingestion timestamp.

The first successful freeze owns that market boundary.

## Decision-time candle snapshot
The ledger freezes complete candle values, not only identities:
- OHLCV
- quote volume / trade count when available
- open / close time
- source type
- source timestamp
- local ingestion timestamp
- adapter version
- closed status

Only candles that are:
- closed
- market-closed by decision as-of
- locally observed by decision as-of
- exact context matches

may enter the bundle.

Missing data is not filled.

## Raw methodology state
The bundle freezes raw PA, Harmonic and Elliott outputs in addition to neutral
selected evidence.

This preserves:
- alternatives that did not win selection
- ambiguity
- source-methodology metrics
- original as-of and methodology versions

A future explanation or evaluator must not reconstruct decision-time state from
newer methodology code and pretend it is the original evidence.

## Serialization
Canonical JSON rules:
- dataclass fields retain declared names
- StrEnum values serialize as strings
- Decimal values serialize as exact decimal strings
- tuples/lists preserve order
- dictionaries sort by key
- JSON uses deterministic sorted keys and compact separators

Wall-clock database insertion time is not included in bundle identity.
This keeps bundle identity deterministic under idempotent retry.

## SQLite
V1 uses project-local SQLite under /runtime/ledger.

Required database behavior:
- WAL mode
- synchronous NORMAL
- foreign keys ON
- immutable signal_freezes table
- immutable lifecycle_evaluations table
- immutable outcome_evaluations table
- SQL triggers reject UPDATE and DELETE on ledger tables
- idempotent equivalent insertion returns UNCHANGED
- identity/context collision with different payload raises explicit conflict

Do not use INSERT OR REPLACE.

## Signal freeze table
Each immutable row stores at least:
- bundle identity
- signal freeze identity
- market identity
- decision as-of
- source cutoff open time
- initial signal state/direction
- canonical bundle JSON
- insertion time

Unique constraints:
- bundle_identity
- signal_freeze_identity
- market context + source_cutoff_open_time_ms

## Lifecycle evaluation table
Lifecycle evaluations append by deterministic evaluation identity.
They may represent:
- no new evidence
- complete coverage with no transition
- incomplete coverage
- invalidation transition

Equivalent re-delivery is idempotent.
Conflicting reuse of an evaluation identity is rejected.

## Outcome evaluation table
Outcome snapshots append with:
- deterministic outcome identity
- parent signal freeze identity
- explicit evidence class
- evaluated as-of
- resolution status and optional outcome state
- max holding-bars policy
- canonical outcome JSON
- insertion time

The unique decision point is:
signal freeze + evidence class + evaluated as-of + max holding bars.

Equivalent retry is UNCHANGED.
Different content at the same decision point is an immutable conflict.

## Forward evidence rule
A record is untouched-forward only when it is frozen during real operation
before its later lifecycle/outcome is known.

Historical REST backfill can be used as decision input at the real freeze time,
but it cannot be relabeled as historically untouched-forward evidence.

The forward evidence clock begins at the first successfully frozen live bundle.

## V1 initial live clock
Initial production-safe pilot:
- BTCUSDT
- 15m
- Bybit Spot
- Binance Spot
- 500-candle live decision window
- one freeze per newly observed closed candle per provider

This is an evidence-clock pilot, not a limitation on final product markets.

Expansion to additional symbols/timeframes follows after the ledger and runner
are mechanically accepted.

No exchange order API is used.
REAL_CAPITAL remains 0.
