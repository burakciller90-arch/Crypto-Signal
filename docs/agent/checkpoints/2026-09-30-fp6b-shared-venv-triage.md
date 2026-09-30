# FP6-B Shared Development Venv Triage Checkpoint

Status: ACTIVE / HANDOFF-SAFE
Date: 2026-09-30
Safety: `REAL_CAPITAL=0`

## Canonical live state at triage

- canonical repo: `burakciller90-arch/Crypto-Signal`
- canonical product roadmap: `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
- umbrella mechanical gate: FP0 / RDP11 remains ACTIVE / NOT PASS; this checkpoint does not claim 72h soak PASS.
- main/base re-verified: `38d757071a50566379715f3074b4b74b668a6aa6`
- PR: #1737, `FP6-B: bind Trade Passport lifecycle to frozen proof`
- branch: `fp6b/trade-passport-frozen-proof`
- exact candidate before acceptance-environment hardening: `1ffb323fe4f248aad033185e32437dacade3ca52`
- Product/Development frozen target: `3d9f33db3f1189571d40566125fbeabd00c04930`
- no Product/Development deployment, no historical backfill, no current-data substitution.
- Durdurulmaz and Quantum Capital are out of scope and untouched.

## Exact-head evidence on `1ffb323f...`

### FP6-B

Run `36710166209`, original job `109869788658`:

- exact source / UID504 / frozen RDP11 target: PASS
- Gitleaks: PASS
- focused FP6-B frozen-proof tests: PASS
- FP6-A lifecycle regression: PASS
- S10 frozen visual proof regression: PASS
- RDP10 exact-evidence regression: PASS
- Final Product read-model regression: PASS
- R22 + FP3 regression: PASS
- focused Ruff + mypy: PASS
- **Whole repository regression: FAIL**
- Product/Development non-mutation proof: PASS

A single controlled same-head rerun was performed on the same `1ffb323f...` candidate. Rerun job `109884076487` again failed at **Whole repository regression** while all earlier focused/static/non-mutation steps passed again. Therefore this is no longer treated as a one-off transient.

### WC6 cross-check

Run `36710166293` on the exact same `1ffb323f...` SHA: SUCCESS.

Critically, WC6 creates an isolated `$RUNNER_TEMP` venv from the Development Python, installs the checked-out repository plus acceptance tools, and its **Whole-repository regression passes** on the same candidate. Development remains untouched.

### RDP11 Pre-Soak cross-check

Run `36710166220` on the same candidate:

- exact source and canonical Development clean check: PASS
- **Exact full-suite integration repair acceptance: FAIL**
- Development non-mutation after the attempt: PASS

The RDP11 Pre-Soak workflow, like FP6-B before this hardening, executes acceptance through the shared `/Volumes/Crypto-504/Crypto-Signal/Development/.venv/bin/python`.

### F10 cross-check

Run `36710166163` on the same candidate: SUCCESS.

## Diagnosis and decision

The product/read-model-specific FP6-B coverage is green. A behavior-preserving commit immediately before this candidate only renamed a local mapping variable (`narrative` -> `narrative_payload`) to remove a mypy shadowing error. A prior candidate already passed the full repository tests and failed only that mypy issue.

The strongest current evidence is therefore an acceptance-environment isolation defect or contamination risk in workflows that execute the repository suite directly through the long-lived shared Development venv. This is **not** a license to waive the failing full-suite gate.

Decision:

1. Keep exact-source checks, frozen target checks, all focused tests, whole-repo pytest/Ruff/mypy/Node coverage, and final non-mutation proof intact.
2. Change FP6-B acceptance to create an isolated runner-temporary venv using the same proven WC6 pattern: base interpreter from Development, checked-out repository installed editable, explicit pytest/pytest-asyncio/Ruff/mypy acceptance dependencies.
3. Do not mutate Product/Development or the RDP11 R2 soak target/observer/evidence.
4. Re-run acceptance on the new exact head; previous exact-head PASS results cannot be carried forward after the workflow commit.
5. If FP6-B becomes green in the isolated environment, apply the same acceptance-environment hardening to RDP11 Pre-Soak rather than hiding the failure. RDP11 72h soak still remains independently ACTIVE / NOT PASS.
6. Merge nothing until FP6-B + WC6 + RDP11 Pre-Soak + F10 mechanically pass on one exact candidate SHA and `main` is rechecked for parallel drift.

## Whole-project FP6 follow-on finding

Do not build a second execution simulator. FP4 already owns depth-aware execution, passive queue/latency/cancel behavior, funding evidence/settlement, instrument fees and `ExecutionReceiptV2`.

Before deriving an FP6-C slice, verify whether accepted immutable R22 events actually persist/bind the FP4 receipt and funding identities/payloads. If they do, reuse them directly. If they do not, the next genuine FP6 blocker is the immutable persistence bridge first, followed by read-only Trade Passport projection. Do not create projection-only fields from current/recomputed truth.

## Immediate next action for a replacement agent

1. Inspect this checkpoint and PR #1737 body before changing code.
2. Harden `.github/workflows/fp6b-trade-passport-frozen-proof-uid504.yml` to use an isolated `$RUNNER_TEMP` venv without reducing acceptance coverage.
3. Validate the automatically triggered exact-head run step-by-step, including non-mutation markers.
4. If green, harden/re-run RDP11 Pre-Soak on the same isolation principle and then obtain FP6-B + WC6 + RDP11 + F10 evidence on one exact head.
5. Recheck `main` immediately before any merge.
