# FP6-B + RDP11 Live Recovery Checkpoint — 2026-09-30

Status: ACTIVE / HANDOFF-SAFE
Recorded at: 2026-09-30 18:16+03:00 session window

## Canonical state verified from GitHub

- Repository: `burakciller90-arch/Crypto-Signal`
- Canonical `main`: `38d757071a50566379715f3074b4b74b668a6aa6`
- Active engineering branch: `fp6b/trade-passport-frozen-proof`
- Candidate observed before this checkpoint commit: `c8887be0625e096e5a0caba8afbc196888543094`
- Existing PR: `#1737` — OPEN, DRAFT, mergeable; do not open a duplicate PR.
- Mechanical roadmap frontier remains FP0 / RDP11 soak.
- Final Product engineering is allowed to continue in the isolated branch while the soak remains open.

## Exact candidate acceptance state at c8887be0625e096e5a0caba8afbc196888543094

- FP6-B Trade Passport Frozen Proof UID504: FAIL
  - run: `36715303232`
  - job: `109887220067`
  - failing step: focused FP6-B frozen-proof pytest step
  - exact assertion/trace is still being extracted; do not guess it.
  - type/static portions are not the current diagnosed root cause.
- RDP11 Pre-Soak Fulltest UID504: FAIL
  - run: `36715303285`
  - failed job: `109886647811`
  - observed failure class: server / active-observer startup path; exact stderr still being extracted; do not guess it.
- F10 Final Closeout: PASS on same candidate
  - run: `36715303165`
- WC6 Paper Recovery Reconciliation: PASS on same candidate
  - run: `36715303173`

Important correction: run `36715303285` is RDP11 Pre-Soak Fulltest and is FAIL; it must not be described as a passing full test matrix.

## What was proven in this recovery session

1. `AGENTS.md`, `ACTIVE_ROADMAP.md`, `READ_FIRST_CRYPTO_SIGNAL.md`, `CURRENT_STATUS.md`, `PROJECT_CHRONICLE.md`, `ENVIRONMENT_REGISTRY.md`, `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`, `docs/agent/CURRENT_FRONTIER.md`, and `docs/agent/HANDOFF_LOG.md` were re-read from canonical GitHub state.
2. FP0/RDP11 is the mechanical active gate, but the roadmap explicitly allows later FP engineering on an isolated branch while soak remains open.
3. PR #1737 is the existing FP6-B PR and already points at the active branch; do not create another PR.
4. Candidate `c8887be0…` commit message is `ci: isolate FP6-B acceptance environment` and it changes only the FP6-B workflow. It does not change FP6-B product/test code.
5. Parent candidate is `3ffe9e8ff2c359ee6f0ae5b5e946632b4d28e2ab`; its FP6-B/RDP11/WC6 runs were cancelled when the newer head arrived, so they do not provide acceptance.
6. Failed-run artifact lists for FP6-B run `36715303232` and RDP11 run `36715303285` are empty. Do not depend on artifacts for the missing trace/stderr.
7. FP6-B workflow runs the focused file `tests/test_fp6b_trade_passport_frozen_proof.py` in a fresh isolated venv using the exact PR head. The old shared-venv contamination hypothesis is therefore not accepted as the current root cause.

## Non-negotiable acceptance rules

- `REAL_CAPITAL=0`.
- Frozen/historical evidence is immutable. No current-data substitution or historical backfill.
- Do not touch Durdurulmaz or Quantum Capital.
- A green workflow or commit is not by itself a gate PASS; inspect acceptance output/evidence.
- Any source/checkpoint change creates a new candidate SHA. Before merge, FP6-B + WC6 + RDP11 + F10 must all be validated on the exact same new SHA.
- Re-check live `main` immediately before merge because parallel/external changes may advance it.
- FP6 is not complete merely when FP6-B is green. Separately prove the immutable execution/funding lineage `ExecutionReceiptV2 → R22 immutable tape → Trade Passport` before declaring FP6 complete.

## Immediate next actions

1. Extract the exact FP6-B failed assertion using workflow/source/test evidence without weakening the test contract.
2. Extract the exact RDP11 server/active-observer startup failure from its workflow/source path.
3. Fix only proven root causes on `fp6b/trade-passport-frozen-proof`.
4. Rerun the exact-head acceptance set and verify outputs on one SHA.
5. Update `docs/agent/CURRENT_FRONTIER.md`, `docs/agent/HANDOFF_LOG.md`, and PR #1737 with final exact SHA/run evidence before any merge decision.
6. After FP6-B, inspect/prove R22 execution/funding lineage and continue to the first mechanically unclosed Final Product gate; do not stop at a local green test.
