# GALACTECH Root Cutover — Latest-Main R25 Candidate

Status: CANDIDATE ONLY  
Base main: `d80042a89196a35132e971a74a874316d9973773`  
REAL_CAPITAL=0

## Purpose

Prepare the production-root routing candidate from the latest accepted R25 main without
deploying or activating production.

This candidate includes the accepted Decision/Capital/Replay rail plus Slice 16
Market Tape / Cold Archive Product Truth.

## Routing

- `GET /` -> current GALACTECH;
- `GET /galactech` -> the same current GALACTECH HTML;
- `GET /legacy` -> previous accepted legacy UI for rollback/audit;
- `/galactech-static/*` and `/static/*` remain isolated;
- Product APIs remain read-only.

There is no redirect and no database/state migration.

## Truth invariants

The root cutover must preserve:
- exact immutable Decision Proof / Forecast-to-Capital-Cycle lineage;
- Runtime Replay Observation truth;
- component-wise R25 Operational Truth;
- canonical Epoch 2 read-only state;
- exact R20.5 LIQ/FLOW/DERIV/ONCHAIN Decision Proof surfaces;
- Hot Market Tape persisted/integrity truth;
- Cold Archive partition/file integrity truth;
- Market Tape ONLINE remains NOT ASSERTED without process evidence;
- Market/Archive process liveness remains NOT MEASURED;
- Event Source Runtime remains NOT EXPOSED without an exact persisted runtime adapter;
- missing probability/performance evidence stays missing;
- REAL_CAPITAL=0 and no order/credential authority.

## Hosted acceptance

Two independent hosted gates are required on the exact candidate head:

1. GALACTECH cutover candidate gate
   - root / alias / legacy routing;
   - all current GALACTECH product regressions;
   - R25 replay/operational/market-data truth;
   - full repository regression.

2. v1.1 integrated release-candidate gate
   - deterministic evidence and capital;
   - R25 unified decision / shadow cycle / replay;
   - Market Tape Hot/Cold contracts + Product Truth;
   - frontend cutover/accessibility;
   - full repository regression.

Hosted PASS is development evidence only.

## Authority boundary

This branch/PR may be prepared and tested without production authority.

The following remain separately gated:
- merging the production-root cutover into main;
- deploying/restarting UID504 production;
- dispatching manual live release acceptance;
- changing wake/lease state;
- enabling exchange credentials/orders;
- changing REAL_CAPITAL.

No such action is performed by candidate preparation.
