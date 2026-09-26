# Crypto Signal — Final F1 WC2 Forward-Liveness Acceptance

Status: **PASS — MECHANICAL TRUTH + LIVE OBSERVABILITY ACTIVATED**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F1 — WC2 Forward-Liveness Truth**  
Date: 2026-09-26  
Safety: **REAL_CAPITAL=0**

---

## 1. Question answered

F1 was opened to answer one narrow question:

> Why did fresh signal freezes continue after the latest WC2 forecast while the forecast count did not advance?

F1 was not allowed to loosen the collection/issuance policy merely to create activity.

The required outcomes were:

- **correct silence**, or
- one exact reproducible correctness defect.

The mechanical answer is:

## **CORRECT SILENCE**

No post-latest-forecast source freeze satisfied the current pre-receipt issuance eligibility contract.

---

## 2. Exact current issuance contract

The current production path in:

- `src/crypto_signal/evaluation/untouched_forward_prepared_runtime.py`;
- `src/crypto_signal/evaluation/untouched_forward_prepared.py`;
- `src/crypto_signal/evaluation/live_untouched_forward_operational.py`

requires a fresh source to be:

- after the accepted collection boundary;
- after the Epoch 2 activation boundary;
- in an authorized pilot coverage context;
- `WATCH` or `ACTIVE`;
- directional;
- bound to frozen geometry with at least one frozen target.

Only then is a prepared receipt written and canonical R20 issuance completed.

Current code does **not** use the following as pre-receipt issuance gates:

- dual-provider pairing/consensus;
- real Event Risk source state;
- provider-divergence state.

The current source adapter instead preserves missing exact PIT Event Risk/market-quality context as explicit `DEGRADED_DATA` truth. F1 therefore did not falsely attribute forecast silence to those non-gates.

---

## 3. Reusable read-only audit

Added:

`ops/audit_wc2_forward_liveness.py`

The audit:

- opens production truth query-only;
- takes stable temporary copies of small WAL-backed WC2 sidecars in the UID504 workflow;
- does not copy or integrity-scan the multi-GB signal ledger;
- holds one query-only signal-ledger snapshot;
- classifies post-latest-forecast freezes using the production pre-receipt conditions;
- reads full freeze bundles only for potential directional `WATCH/ACTIVE` candidates;
- joins exact prepared-receipt and forecast lineage;
- reports candidate defects separately;
- performs no market replay;
- creates no forecast;
- creates no historical message;
- performs no canonical capital mutation;
- grants no production or real-money authority.

Regression coverage:

`tests/test_wc2_forward_liveness_audit.py`

proves at minimum:

- all-ineligible post-forecast sources → correct silence;
- directional geometry without a prepared receipt → correctness candidate.

The accepted F1 gate also ran the existing WC2 live-clock wiring tests against the new observability code.

---

## 4. Accepted exact-source run

Workflow run:

**36251560197**

Exact head:

**`3ca8ce32dc3fc340f2b381f92e6cea4065a6ece0`**

Artifact:

- `stream-final-f1-wc2-liveness-36251560197`
- artifact id: `10909311908`
- digest: `sha256:bd42e8baca06e34ae938a9b00668fd45cbd58b4da39eaf4383e21a78330177a1`

Gate evidence:

- `F1_EXACT_SOURCE_PASS=YES`;
- focused audit tests PASS;
- WC2 live-clock wiring tests PASS;
- stable sidecar snapshots PASS;
- live production read-only audit PASS;
- `F1_NON_MUTATING_PASS=YES`;
- `REAL_CAPITAL=0`.

Physical checkout proof during the audit:

- Development: `f0349a70c11046893cbabd88ab56ca4ca8c44a99`;
- Product: `d343c4b2d10489a88f614bd58c9539be76029f80`.

Neither checkout was mutated by the audit.

---

## 5. Live result

At the accepted observation:

- post-latest-forecast freezes: **686**;
- post-latest-forecast 4h freezes: **48**;
- prepared-required sources: **0**;
- candidate defects: **0**;
- integrity errors: **0**.

State distribution:

- `WATCH`: **525**;
- `NEUTRAL`: **161**.

Primary reason distribution:

- `source_missing_geometry`: **525**;
- `source_neutral`: **161**.

4h reason distribution:

- `source_missing_geometry`: **36**;
- `source_neutral`: **12**.

Latest persisted forecast at the observation:

- forecast identity: `014d479a69196f890754229378b321f6134c39622d6ff73926e96868e459e50f`;
- symbol: `ETHUSDT`;
- timeframe: `15m`;
- issued at: `1790295411622`.

No post-forecast freeze had:

**WATCH/ACTIVE + directional + frozen geometry + frozen target**

and then failed to receive its prepared receipt.

Therefore no evidence supports a stalled eligible issuance.

---

## 6. Why WATCH did not mean forecast-eligible

The 525 `WATCH` rows were directional but lacked frozen trade geometry.

This is valid under the canonical SignalDecision contract:

- `ACTIVE` requires geometry;
- `WATCH` may remain directional without geometry.

WC2 forecast issuance is intentionally stricter than the generic `WATCH` label.

Therefore:

> “WATCH exists” does not mean “WC2 should issue a forecast.”

The Stream was quiet because the current forecast-only production bridge had no new eligible forecast to project.

This is exactly why later F2-F4 must complete material source-family messaging rather than weakening WC2 to make the feed busy.

---

## 7. Operability closure

F1 also adds deterministic live-clock liveness telemetry.

Each WC2 context now prints exact reason codes carried by `WC2PreparedLiveResult`.

Each cycle prints one bounded summary:

`wc2_liveness status=SUMMARY contexts=... status_counts=... reason_counts=... POLICY_UNCHANGED=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0`

Purpose:

- explain prolonged issuance silence without reconstructing policy from ad-hoc logs;
- preserve exact current reason semantics;
- expose liveness without altering forecast eligibility.

This telemetry changes no policy and no canonical scientific truth.

---

## 8. Live activation proof

The accepted observability/audit code merged through PR #1348 to main:

`71ff1ad4f2d1c9f58df65fab12a12c02754acfc6`

The physical Development checkout was then cleanly fast-forwarded from:

`f0349a70c11046893cbabd88ab56ca4ca8c44a99`

to exact merged main:

`71ff1ad4f2d1c9f58df65fab12a12c02754acfc6`.

UID504 live activation run:

**36252043820**

Artifact:

- `stream-final-f1-live-activation-36252043820`
- artifact id: `10909291747`
- digest: `sha256:3c435fe78bb048d6c9ebb4a2e06e40880971edfae00a1425ae42506cadfbf161`

A fresh real supervisor cycle produced:

`wc2_liveness status=SUMMARY contexts=17 status_counts=no_prepared_receipt:17 reason_counts=no_preoutcome_prepared_receipt_for_source_freeze:17 POLICY_UNCHANGED=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0`

The marker count advanced from **1 to 2** during the acceptance window.

The WC2 forward-policy and collection-protocol files were SHA256-identical before and after the live proof.

Product remained unchanged at:

`d343c4b2d10489a88f614bd58c9539be76029f80`.

No Product deployment, historical rich backfill, synthetic forecast/message activity, policy relaxation or real-money authority was used.

---

## 9. F1 closure boundary

F1 is fully closed.

The accepted conclusion is:

**WC2 forecast silence is currently correct, not a proven issuance bug.**

Production now exposes deterministic reason telemetry that explains the silence without changing the issuance contract.

The next exact frontier is:

**F2 — Production Source-to-Message Backbone**

No policy relaxation is authorized.  
No historical backfill is authorized.  
No real-money authority is introduced.  
**REAL_CAPITAL=0.**
