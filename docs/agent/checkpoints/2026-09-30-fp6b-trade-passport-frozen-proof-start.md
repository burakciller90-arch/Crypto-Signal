# Crypto Signal — FP6-B Live Checkpoint

Status: **ACTIVE / EXACT-HEAD ACCEPTANCE RUNNING**
Date: 2026-09-30
Repository: `burakciller90-arch/Crypto-Signal`
Canonical roadmap: `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
Active pointer: `ACTIVE_ROADMAP.md`
Task-start main: `38d757071a50566379715f3074b4b74b668a6aa6`
Active branch: `fp6b/trade-passport-frozen-proof`
Draft PR: `#1737`
Latest code fix before this checkpoint write: `a6b9047562454550e89d1e04188ef263ab5d4e8e`
Safety: `REAL_CAPITAL=0`

## Current program state

- FP0 / RDP11 remains mechanically **ACTIVE / NOT PASS** on the isolated R2 soak. Do not mutate the frozen Product/Development soak target, observer contract, or historical/frozen evidence.
- FP1–FP5 accepted work is reuse authority; do not rebuild it.
- FP6-A merged as PR #1705 / main `38d757071a50566379715f3074b4b74b668a6aa6` after exact-head FP6-A + WC6 + RDP11 Pre-Soak + F10 acceptance.
- FP6 is the current parallel product frontier while FP0 remains time/evidence gated.

## Duplicate / drift audit

Live GitHub recheck found:
- current `main` remained `38d757071a50566379715f3074b4b74b668a6aa6` during this continuation;
- draft PR #1737 is open and was `mergeable=true` after the latest code/test push;
- PR base remains exact FP6-A main SHA;
- no parallel `main` drift was present at the last recheck.

Classification:
- **REUSE** R22/R21 immutable transaction/accounting lineage and FP6-A lifecycle reconstruction;
- **REUSE** FP1-E immutable Trade Passport read model;
- **REUSE** S10 `IntelligenceStreamVisualProofReadModel` for frozen historical chart/annotation proof;
- **REUSE** RDP10 `IntelligenceStreamExactEvidenceReadModel` for exact persisted family/source proof;
- **EXTEND** read-only Trade Passport proof projection;
- **BUILD: NO** new canonical ledger/store/schema/writer/evidence engine.

## Canonical FP6 master clauses being enforced

From `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`:
- passport identity must expose asset/action/vault/policy/open-close time/size/result;
- “What did the system see?” must expose frozen Market Story, exact five-family states, source/provider/time, Event Risk and exact trigger/invalidation/targets;
- execution must expose signal/reference price, simulated fill, fill status, fee/spread/slippage plus funding/latency/partial-fill/queue status where applicable;
- lifecycle is append-only and includes OPEN / SCALE_IN / STOP_UPDATE / PARTIAL_TAKE_PROFIT / REDUCE / CLOSE / CORRECTION-SUPERSEDED when required;
- PASS requires reconstruction solely from accepted immutable records, every lifecycle event opening the exact proof that existed then, losses being equally inspectable, and later model versions being unable to alter historical content.

## FP6-B implementation state

Initial commits:
- `8b5ab765a74c0daafd664e4b3a78ee312b51b1d7`: added `src/crypto_signal/product/trade_passport_frozen_proof.py`; reuses existing Trade Passport audit lineage + S10 + RDP10; no new truth writer/store.
- `ecb949dcce578de60d2a7848b6f310afa0b130d5`: initial focused proof tests.
- `1cd1ae0753800c98067ecedb0d3b2bc32c08a2eb`: exact triple + lifecycle event-time resolver.
- `0cad8a5e0876bb4230bb97db27559876828ba8a1`: event-time/story-revision/lifecycle tests.
- `12ad17efcecbd98a5217b3c4e0b8ee5d8a6991d7`: dedicated exact-head UID504 FP6-B workflow.

Dedicated run #1 on exact head `12ad17efcecbd98a5217b3c4e0b8ee5d8a6991d7`:
- workflow run: `36708501018`;
- exact source assertion: **PASS**;
- UID504 + frozen RDP11 Product/Development target assertion: **PASS**;
- focused FP6-B test: **FAIL**;
- post-run Product/Development non-mutation: **PASS**;
- failure cause was local to this slice, not runner/soak/runtime mutation.

Failure root causes found from decoded job log:
1. resolver incorrectly read `read_message_detail()` event time at `detail["event_at_ms"]`; canonical contract exposes it at `detail["narrative"]["event_at_ms"]`;
2. the synthetic later-story fixture changed only the narrative row, violating canonical Stream detail lineage because narrative / analytical / fact / message event identities and event time must remain mutually consistent.

Fixes:
- `877018421e21e1b0bb9db3d69a363a3f7b2921b9`: resolver now reads event time from the verified canonical narrative payload. Canonical Stream verification was **not weakened**.
- `7852fc6869b85da3130b39815f9ce81324651731`: test fixture now creates a complete canonical full-lineage later Stream event: new fact bundle, message input, analytical view, plan and narrative identities/digests, all with consistent event/source/stream lineage. This preserves the real production contract instead of weakening tests.

Dedicated run #2 on exact head `7852fc6869b85da3130b39815f9ce81324651731`:
- FP6-B run `36709219791`: **FAIL**, but only at focused static typing;
- focused FP6-B frozen-proof tests: **8 passed**;
- FP6-A lifecycle regression: **PASS**;
- S10 frozen visual-proof regression: **PASS**;
- RDP10 exact-evidence regression: **PASS**;
- Final Product read-model regression: **PASS**;
- R22 / FP3 regression: **PASS**;
- Ruff: **PASS**;
- mypy: **FAIL** with five assignment/member errors caused by local variable shadowing in `_resolve_exact_narrative`;
- Product/Development frozen-target non-mutation proof: **PASS**;
- F10 run `36709219776`: **SUCCESS** on the same head;
- RDP11 Pre-Soak run `36709219892`: **SUCCESS** on the same head.

Static failure root cause:
- local mapping variable `narrative` shadowed/conflicted with `_ResolvedNarrative` inference in mypy;
- no runtime, proof-selection, lineage, or acceptance-test behavior failed.

Static fix:
- `a6b9047562454550e89d1e04188ef263ab5d4e8e`: renamed the verified detail mapping to `narrative_payload`; canonical behavior and selection contract are unchanged.

Acceptance graph fix:
- FP6-B workflow now watches the live checkpoint and WC6 workflow so documentation/acceptance-graph changes cannot silently leave FP6-B green on an older head.
- WC6 workflow now watches FP6-B source/test/checkpoint/workflow paths so the final candidate obtains WC6 on the exact same SHA instead of inheriting a stale paper gate.
- F10 and RDP11 Pre-Soak already trigger on PR-head changes.

Draft PR `#1737` remains an acceptance vehicle only. It must not merge before all required mechanical gates pass on one final candidate SHA.

## Historical-proof selection contract

The safe selection key is:
1. exact Trade Passport `forecast_identity`;
2. exact Trade Passport `proof_identity`;
3. exact Trade Passport `signal_freeze_identity` resolved through S10 proof lineage;
4. for a lifecycle event, candidate narrative `event_at_ms <= passport.filled_at_ms` / lifecycle event time;
5. among exact-lineage candidates already existing by the event cutoff, select the latest event time deterministically;
6. distinct exact candidates at the same latest event timestamp remain fail-closed because accepted history provides no safe ordering basis.

This prevents a later Stream event/story from being substituted into an earlier lifecycle event and does not invent ordering when persisted truth is ambiguous.

## FP4 reuse audit — important whole-project finding

Do **not** build a second execution realism engine for FP6. Accepted FP4 work already owns the required hard execution truth:

- FP4-A / PR #1688 → `src/crypto_signal/paper/execution_depth_v2.py`: deterministic depth-aware FULL / PARTIAL / NOT_FILLED / FILL_NOT_PROVEN outcomes.
- FP4-B / PR #1692 → `src/crypto_signal/paper/execution_limit_v2.py`: passive-limit latency, effective arrival, queue-ahead/queue-consumed proof, timeout/cancel terminal states, partial fills and FILL_NOT_PROVEN.
- FP4-C / PR #1693 → `src/crypto_signal/paper/funding_cost_v2.py` plus settled funding evidence: PROVEN / NOT_PROVEN exact settlement cash-flow projection; future/missing evidence fails closed.
- FP4-D / PR #1695 → `src/crypto_signal/paper/instrument_fees_v2.py`: exact instrument fee schedule/projection.
- FP4-E / PR #1696 → `src/crypto_signal/paper/execution_receipt_v2.py`: canonical execution receipt binding authoritative pretrade/venue truth to depth/passive outcome + fee evidence; funding intentionally accounted separately.

`ExecutionReceiptV2` already exposes exact status, mode, requested/filled/unfilled quantity, reference price, average fill price, fill notional, fee, adverse price impact, immediate execution cost, market evidence identities and all receipt/outcome/pretrade/venue identities.

`PassiveLimitExecutionOutcome` already exposes latency, queue proof, timeout/cancel, terminal state and partial-fill state.

`PaperFundingCostProjection` already exposes PROVEN/NOT_PROVEN status, exact settlement/mark identities/timestamps and funding cash flow.

Current `TradePassportView` on main still exposes only older summary execution fields (`reference_price`, `simulated_fill_price`, `fee_usdt`, `spread_usdt`, `slippage_usdt`, etc.) and does not expose the accepted FP4 receipt status/mode/partial-fill/queue/latency/funding truth. Therefore the likely next still-open FP6 bounded slice after FP6-B is **FP6-C: read-only binding/projection of accepted FP4 execution receipt + funding truth into Trade Passport**, not new simulation logic. Re-audit before starting because another agent may advance main.

## Acceptance requirements

Generic F10 green is **not** FP6-B PASS by itself. Dedicated exact-head workflow is required.

Dedicated gate checks:
- exact PR head checkout and explicit SHA assertion;
- frozen RDP11 Product/Development target assertion (`3d9f33db3f1189571d40566125fbeabd00c04930`);
- focused FP6-B proof tests;
- FP6-A lifecycle regression;
- S10 visual-proof regression;
- RDP10 exact-evidence regression;
- Final Product read-model regression;
- R22/FP3 regressions where relevant;
- Ruff + mypy;
- whole-repository regression;
- post-run Product/Development non-mutation proof.

Before merge, one final candidate SHA must satisfy the project acceptance set used for FP6-A: FP6-B + WC6 + RDP11 Pre-Soak + F10. Do not count a workflow as PASS only from its top-level conclusion; inspect the relevant acceptance steps/markers.

## Explicit non-goals / forbidden work

- no second Trade Passport ledger;
- no second evidence database;
- no second execution simulator or funding truth engine;
- no historical backfill;
- no current-data substitution;
- no Product/Development deployment;
- no RDP11 observer/soak mutation;
- no real-money/exchange authority;
- no changes to Durdurulmaz or Quantum Capital.

## Other active project risks retained for handoff

- `CURRENT_FRONTIER.md` and `HANDOFF_LOG.md` are large and must never be overwritten from truncated connector reads. Reconcile losslessly before final handoff/merge; this live checkpoint remains the authoritative in-flight FP6-B continuation record until that reconciliation.
- UID504 runner startup was repaired for the immediate FP6-A blocker, but daily sleep/shutdown/network-loss resilience has not all been mechanically exercised as durable operational acceptance.
- FP0/RDP11 remains independently open until its real accumulated evidence audit passes; elapsed time alone is not PASS.
- After FP6-B, audit FP6-C execution projection and then immutable archive/later-model immutability clauses before FP7. Do not skip remaining FP6 clauses merely because FP6-B passes.

## Exact next action

1. Treat the commit created by this checkpoint update as the new final-candidate head; obtain FP6-B + WC6 + RDP11 Pre-Soak + F10 on that exact SHA.
2. Inspect FP6-B step-level output; specifically prove focused tests, mypy/Ruff, whole-repository regression and Product/Development non-mutation all pass after `a6b9047562454550e89d1e04188ef263ab5d4e8e`.
3. Inspect WC6 step-level output rather than relying only on top-level success.
4. Recheck latest `main` and PR mergeability immediately before merge; reconcile any parallel-agent drift.
5. Only after one final SHA passes all four gates and acceptance outputs are inspected, reconcile `CURRENT_FRONTIER.md` + `HANDOFF_LOG.md` losslessly and consider merge.
6. After FP6-B merge, re-audit main; if no parallel agent already closed it, continue with FP6-C by **reusing** FP4-A→E canonical truth and projecting execution/funding status into Trade Passport.
