# M5 Smart Money / On-chain 2.0 — Slice 3: Bounded Large-Transfer Clusters

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Represent provider-attributed large transfers as point-in-time context without turning one
large transaction into a whale/insider/institution claim.

This slice uses repeated relationships, temporal clustering, exact provider attribution and
size normalization inside the consumed PIT window.

## Observation contract

Each transfer freezes:

- asset and network;
- provider transfer identity;
- source and destination provider cluster IDs;
- provider-declared source/destination role: unknown, exchange or provider-known;
- amount;
- event/source/ingestion timestamps;
- provider and attribution-method identity;
- deterministic transfer identity.

An `EXCHANGE` role means only that the source provider attributed that cluster as an
exchange under the stated methodology.

## Size normalization and repeated relationships

Within one exact asset/network/provider/attribution context and a bounded lookback:

- each transfer amount receives an exact consumed-window percentile rank;
- large-event status is defined by a versioned percentile threshold;
- source→destination relationships are grouped deterministically;
- a repeated relationship candidate requires both a minimum event count and minimum
  share of observed transfer amount;
- candidate evidence retains count, total amount, amount share, mean size percentile and
  first/last event time.

## Context labels

- `REPEATED_RELATIONSHIP_CLUSTER`: at least one repeated relationship passes bounded
  count/share thresholds.
- `ISOLATED_LARGE_TRANSFER`: large normalized evidence exists but no repeated
  relationship satisfies the candidate rule.
- `UNRESOLVED`: too little PIT-safe history to characterize activity.

No directional price label is produced.

## Scientific boundaries

- Cluster IDs are provider attribution, not person/legal-entity identity.
- Provider-known or exchange-attributed does not prove a specific actor's intent.
- A large transfer is not automatically accumulation, distribution, buy or sell.
- Repetition does not prove coordination.
- Missing transfer coverage is not interpreted as zero activity.
- Future or late-ingested transfers cannot rewrite a historical freeze.
- No wallet is labeled insider/institutional/smart by this engine.
- No probability, capital allocation, sizing or trading command is produced.
- No live provider/API/credential/collector is activated.

## Acceptance checklist

1. Deterministic transfer and evidence identities.
2. Repeated source→destination clustering under explicit count/share thresholds.
3. Exact consumed-window size percentile normalization.
4. Provider exchange-role evidence retained without actor-intent inference.
5. Isolated large-transfer context remains distinct from repeated relationship evidence.
6. Insufficient history fails closed.
7. Future/late evidence cannot rewrite historical freezes.
8. Context mismatch, duplicate provider IDs, invalid thresholds and identity tampering
   fail closed.
9. Focused pytest/Ruff/mypy and full repository Python/JavaScript/freshness regression.
10. Temporary hosted workflow removed after PASS.

After this slice, the locked M5 evidence families are present: existing network activity,
exchange-flow context, PIT wallet cohort registry/forward measurement, and bounded
large-transfer clustering. Production data-source activation remains a separate gate.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
