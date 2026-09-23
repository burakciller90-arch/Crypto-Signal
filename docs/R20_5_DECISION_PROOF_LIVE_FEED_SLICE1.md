# R20.5 Decision Proof / Live Intelligence Feed — Slice 1

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Bridge the accepted R20 immutable forecast stream into a product-safe, read-only Decision
Proof and Live Intelligence Feed contract.

This slice does not create a second dashboard, execute research engines, mutate ledgers,
or expose private chain-of-thought. It produces structured issuance-time truth that the
GALACTECH product rail can consume later.

## Decision Proof card truth

Each `DecisionProofSnapshot` is bound to one immutable R20 forecast and exposes:

- state;
- asset / symbol / timeframe;
- issuance and source-as-of time;
- one deterministic conditional thesis;
- trigger zone;
- target zone;
- invalidation;
- horizon;
- M6 support and opposition;
- probability or NOT_CALIBRATED;
- Event Risk state;
- authority;
- freshness;
- uncertainty;
- exact forecast source evidence identities.

The conditional thesis is derived only from structured forecast fields. No hidden model
reasoning or private chain-of-thought is stored.

## Evidence Room domain contract

Exactly one canonical slice exists for every locked Phase 14 proof domain:

1. frozen chart;
2. consumed candles;
3. order book;
4. liquidity map;
5. liquidation map;
6. order flow / CVD;
7. derivatives (OI / funding / basis);
8. on-chain;
9. event context;
10. methodology support/conflict;
11. probability calibration.

Every domain is explicit as:

- `AVAILABLE`;
- `INSUFFICIENT`;
- `UNSUPPORTED`.

Missing evidence is never silently omitted.

Available evidence freezes:

- exact evidence identities;
- market-available timestamp;
- observed timestamp;
- freshness;
- source quality;
- bounded verdict: SUPPORT / CONTRADICT / NEUTRAL.

Unavailable or unsupported evidence must use INSUFFICIENT verdict and may not carry hidden
identities, timestamps or freshness.

## Point-in-time boundary

Decision Proof is an issuance-time view.

Any evidence marked AVAILABLE must have been observed no later than the R20 forecast
`source_as_of_ms`. Future evidence cannot be inserted into the proof.

The union of proof evidence identities must cover every R20
`source_evidence_identity`.

## Domain-specific lineage

Proof evidence cannot merely appear somewhere in the bundle.

- EVENT_CONTEXT must contain the exact R20 Event Risk identity.
- METHODOLOGY must contain the exact signal freeze identity and M6 Confluence identity.
- If R19 probability is calibrated, PROBABILITY_CALIBRATION must contain the exact
  authorization and calibration-evidence identities, and all remaining R20 probability
  lineage identities must still be covered by the proof evidence union.
- If probability is NOT_CALIBRATED, the probability domain cannot claim AVAILABLE
  evidence.

This prevents correct-looking evidence IDs from being mislabeled into the wrong proof
domain.

## Evidence summary

Decision Proof exposes counts for:

- SUPPORT;
- CONTRADICT;
- NEUTRAL;
- INSUFFICIENT;
- AVAILABLE;
- total proof domains.

The summary is derived from the same evidence slices. It is not a probability and does not
increase certainty.

## Live Intelligence Feed

The feed is append-only and read-only.

Slice 1 emits only meaningful state transitions:

- `FORECAST_ISSUED`;
- `FORECAST_RESOLVED`.

Issuance carries the R20 forecast state. Resolution carries the accepted append-only R20
resolution state.

A resolution feed event:

- must reference the exact forecast and Decision Proof;
- must reference an exact R20 resolution identity;
- cannot predate forecast issuance;
- cannot be appended before that forecast's issuance event.

At most one issuance and one resolution event exist per forecast in this slice.

## Product boundary

This module is a structured truth bridge only.

It does not:

- write SQLite or any ledger;
- create paper fills;
- size positions;
- submit exchange orders;
- access network providers;
- control launchd/runtime;
- alter forecast history;
- expose private chain-of-thought.

The existing read-only product APIs and the future GALACTECH frontend may project these
objects, but presentation cannot add certainty or evidence that the proof does not contain.

## Scientific boundaries

- Proof is not prediction probability.
- Evidence summary counts are not probability.
- Simple explanation may reduce jargon but cannot increase certainty.
- Unsupported liquidation data remains UNSUPPORTED.
- Missing order-book/CVD/on-chain evidence remains INSUFFICIENT.
- Outcome information never enters issuance-time proof.
- R20 forecast identity remains unchanged after later resolution.
- REAL_CAPITAL=0.

## Acceptance checklist

1. All locked Phase 14 evidence domains exist exactly once.
2. AVAILABLE / INSUFFICIENT / UNSUPPORTED semantics fail closed.
3. Every R20 source evidence identity is covered.
4. Event Risk identity is in EVENT_CONTEXT.
5. Signal + M6 identities are in METHODOLOGY.
6. R19 calibrated identities are in PROBABILITY_CALIBRATION.
7. NOT_CALIBRATED cannot claim probability evidence.
8. Future evidence is rejected.
9. Conditional thesis is deterministic and structured.
10. Feed issuance/resolution state transitions preserve exact lineage.
11. Resolution requires prior issuance.
12. Feed is append-only and chronologically ordered.
13. Identity tampering fails closed.
14. No private reasoning, ledger write, network, sizing, execution or production authority.
15. REAL_CAPITAL=0.
16. Focused pytest/Ruff/mypy and full repository Python/JS/freshness regression.
17. Temporary hosted workflow removed after PASS.

After acceptance, Phase 14 infrastructure exit is satisfied. The next locked frontier is
Phase 15 — R21 Canonical 1,000 USDT Paper Fund, which remains a separate activation and
accounting gate.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
