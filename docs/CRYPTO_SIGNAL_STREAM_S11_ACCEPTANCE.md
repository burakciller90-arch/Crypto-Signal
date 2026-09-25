# Crypto Signal — Stream S11 Capital Story Integration Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S11 closes the canonical three-vault forward paper-capital lifecycle required before discovery/history UX.

## Accepted implementation

Merged PR #1290 / main `32375dbb89dd158d5d30b85db696ed640e4b8a4b`.

Accepted runtime:
- Core / Tactical / Opportunity participation only under exact Smart Capital Allocator eligibility;
- Tactical 1m/5m microstructure gating;
- Opportunity recovery gating;
- immutable candidate / eligible / hold / blocked decisions;
- fixed-fractional canonical paper sizing promotion;
- Kelly remains research-only and is not automatically promoted;
- restart-safe R22 predecessor chains;
- simulated BUY, reduction and exit;
- R22 intent/fill + R21 Epoch 2 atomic accounting;
- accounting update and outcome persistence;
- exact Decision Proof/evidence lineage for simulated fills;
- Epoch 1 history remains immutable and separate from Epoch 2;
- no real exchange or credential authority.

Accepted Stream lifecycle:
- `capital_candidate`;
- `capital_eligible`;
- `capital_hold`;
- `capital_blocked`;
- `capital_sized`;
- `capital_executed`;
- `capital_reduced`;
- `capital_exited`;
- `capital_accounting_updated`;
- `capital_outcome`.

All lifecycle records remain in the same mixed Intelligence Stream. No standalone Capital screen was introduced.

## Exact-head acceptance

Accepted implementation head:
- `4575ab564871c3a333bac4614cd483b6e8295217`.

UID504 run:
- `36197140443` — **PASS**.

The accepted run proved:
- exact source checkout;
- focused S11 capital runtime/projector/read-model/UI acceptance;
- project-level Ruff + strict mypy;
- whole-repository regression;
- real Chromium desktop Capital Story lifecycle;
- exact 430x860 mobile Capital Story lifecycle;
- zero whole-page horizontal overflow;
- all ten lifecycle states present;
- CORE / TACTICAL / OPPORTUNITY_RESERVE coverage;
- exact 64-hex message identities;
- outcome expansion with realized PnL and immutable lineage;
- REAL_CAPITAL=0 visible in deep detail;
- Stream remains usable/visible;
- Development checkout non-mutation.

Visual artifact:
- `stream-s11-visual-snapshot-36197140443`;
- artifact id `10890468821`;
- digest `sha256:1b79ac1c108785ee5ab41cd25e7ea9c97182ee866ea56057b8d431ceb4359114`.

## S11 PASS criteria

Roadmap criterion: all three vaults can participate under their own rules.  
**PASS** — canonical execution requires exact allocator eligibility proof; Tactical preserves its 1m/5m evidence rule and Opportunity preserves recovery evidence. Chromium acceptance displays all three vaults in one lifecycle.

Roadmap criterion: Stream explains why capital acted or did not act.  
**PASS** — candidate, eligible, hold, blocked, sized, executed, reduced, exited, accounting and outcome records are immutable first-class Stream messages with exact reason/lineage fields.

Roadmap criterion: no separate Capital screen required.  
**PASS** — all lifecycle states render inside the same Intelligence Stream and expand inline.

Roadmap criterion: every simulated fill links to exact decision/proof.  
**PASS** — R22 intent/fill, R21 accounting and Stream Capital Story preserve exact Decision Proof/evidence identities; stale/mismatched lineage fails closed.

## Boundaries retained

S11 does not authorize:
- real exchange orders;
- trading credentials;
- leverage, borrowing or martingale;
- historical paper backfill;
- Epoch 1 / Epoch 2 rescaling or merged track records;
- automatic Kelly promotion;
- S13 notifications/sound;
- production-root cutover.

The active frontier after closeout is S12 Search, Filters and History UX.
