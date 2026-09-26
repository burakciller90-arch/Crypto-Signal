# Crypto Signal — Final F1 WC2 Forward-Liveness Acceptance

Status: **PASS — CORRECT SILENCE PROVEN**  
Roadmap: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Phase: **F1 — WC2 Forward-Liveness Truth**  
Date: 2026-09-26  
Safety: **REAL_CAPITAL=0**

---

## 1. Question

Why did new WC2 forecasts stop advancing while fresh signal freezes continued?

F1 had only two acceptable conclusions:

1. **Correct silence** — no post-forecast freeze satisfied the preregistered issuance contract.
2. **Correctness defect** — at least one eligible freeze should have progressed but failed because of a reproducible implementation/runtime defect.

F1 was not allowed to loosen WC2 rules merely to make the Stream busy.

---

## 2. Exact production issuance contract audited

The audit is bound to the current code path:

`ops/run_live_evidence_clock.py`
→ `process_wc2_prepared_live_freeze()`
→ `build_wc2_prepared_cycle_receipt()`
→ `complete_wc2_prepared_cycle()`
→ accepted R20/R20.5 issuance
→ optional Stream issuance hook.

A fresh source can reach prepared issuance only when the real current code establishes all of the following:

- source freeze is at/after collection start;
- source freeze is at/after Epoch 2 activation;
- coverage context is authorized by the preregistered protocol;
- signal state is WATCH or ACTIVE;
- direction is not NONE;
- exact frozen geometry exists;
- exact frozen geometry contains at least one target;
- source/issuance delay remains inside the preregistered maximum.

The audit also checks exact prepared-receipt and forecast lineage.

The following were verified **not** to be current pre-receipt issuance gates in this code path:

- dual-provider consensus/pairing;
- real Event Risk source state;
- provider-divergence state.

Current `adapt_same_cycle_legacy_bundle()` instead supplies an explicit fail-closed `DEGRADED_DATA` missing-PIT Event Risk context. That is scientific debt for later source integration, but it did not cause the observed forecast silence.

---

## 3. Read-only audit implementation

Canonical diagnostic:

- `ops/audit_wc2_forward_liveness.py`

Regression coverage:

- `tests/test_wc2_forward_liveness_audit.py`
- existing `tests/test_wc2_live_clock_wiring.py`

Safety properties:

- production runtime SQLite files are never initialized or mutated;
- WC2 sidecars are first copied into stable temporary snapshots;
- the multi-GB signal ledger is opened query-only;
- the signal scan anchors on the exact latest forecast source `signal_freeze_identity` and inspects only later append-only rows;
- no historical market replay is performed;
- no forecast is created;
- no prepared receipt is created;
- no canonical paper state is mutated;
- no historical backfill authority exists;
- `REAL_CAPITAL=0`.

Synthetic regressions prove both decision branches:

- all post-forecast sources ineligible → correct silence;
- WATCH/ACTIVE + directional + frozen geometry + no prepared receipt → correctness candidate.

---

## 4. Exact live acceptance evidence

UID504 exact-source run:

- run: `36251560197`
- workflow result: **SUCCESS**
- artifact: `stream-final-f1-wc2-liveness-36251560197`
- artifact id: `10909311908`
- artifact digest: `sha256:bd42e8baca06e34ae938a9b00668fd45cbd58b4da39eaf4383e21a78330177a1`

Accepted markers:

- `F1_EXACT_SOURCE_PASS=YES`
- `F1_AUDIT_TEST_PASS=YES`
- `WC2_FORWARD_LIVENESS_CORRECT_SILENCE_PRE_RECEIPT=YES`
- `F1_NON_MUTATING_PASS=YES`
- `REAL_CAPITAL=0`

---

## 5. Observed production truth

Latest accepted forecast at the audit instant:

- forecast identity: `014d479a69196f890754229378b321f6134c39622d6ff73926e96868e459e50f`
- signal freeze identity: `38d162576e218d6b363dd8e852d6dcf93d548f25c40b69d35362e5b1a28c20b5`
- asset/symbol: ETH / ETHUSDT
- timeframe: 15m
- issued at ms: `1790295411622`

Post-latest-forecast freezes:

- total: **686**
- 15m: **523**
- 1h: **115**
- 4h: **48**
- Binance: **355**
- Bybit: **331**

Signal states:

- WATCH: **525**
- NEUTRAL: **161**

Directions:

- bullish: **259**
- bearish: **266**
- none: **161**

Exact reason classification:

- `source_missing_geometry`: **525**
- `source_neutral`: **161**

4h-only reason classification:

- `source_missing_geometry`: **36**
- `source_neutral`: **12**

Critical defect checks:

- prepared-required candidates: **0**
- eligible-without-prepared-receipt: **0**
- prepared-receipt-without-forecast: **0**
- receipt issuance-delay violations: **0**
- integrity errors: **0**

Therefore every post-forecast freeze was ineligible **before** prepared issuance.

---

## 6. Conclusion

**F1 conclusion = A — Correct silence.**

The forecast/Stream decision path is not proven broken.

The system remained silent because:

- 161 freezes were NEUTRAL; and
- 525 WATCH freezes did not contain frozen geometry.

No post-forecast source met the actual current issuance contract.

Therefore F1 explicitly rejects the following incorrect actions:

- lowering signal thresholds just to create messages;
- creating geometry after the fact;
- backfilling forecasts;
- treating dual-provider pairing as the missing gate when current code does not;
- inventing Event Risk truth;
- synthesizing Stream activity.

---

## 7. Observability closure

The live evidence clock now has deterministic per-cycle WC2 liveness summary output:

- status counts;
- exact reason-code counts;
- per-context reason codes;
- `POLICY_UNCHANGED=YES`;
- `HISTORICAL_BACKFILL=NO`;
- `REAL_CAPITAL=0`.

This does not change the issuance policy. It makes future quiet cycles mechanically explainable from runtime truth.

Product-facing “why quiet?” presentation remains a later Stream projection/UI concern and must consume this deterministic truth rather than infer or fabricate a reason.

---

## 8. F1 PASS

F1 passes because:

- every relevant post-forecast freeze was classified against actual current code;
- no eligible freeze was lost;
- no prepared/forecast lineage defect was found;
- no integrity error was found;
- the diagnosis used the real production ledger read-only;
- the policy was not relaxed;
- no backfill occurred;
- deterministic liveness observability was added;
- `REAL_CAPITAL=0` remained binding.

**F1 = PASS — CORRECT SILENCE PROVEN.**

Next exact frontier:

**F2 — Production Source-to-Message Backbone**
