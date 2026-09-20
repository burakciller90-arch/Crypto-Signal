# Virtual Paper Write Authority — Production Gate Plan

Status: **PREPARED / NOT AUTHORIZED / NOT ACTIVATED**

This document is an execution checklist, not production authority. It does not authorize any deploy, paper-ledger mutation, workflow allowlist expansion, write-authority enablement, or write tick. The gate remains closed until the user gives separate explicit production authorization.

## Invariants

- REAL_CAPITAL=0 at every layer.
- No broker/exchange credentials.
- No network order path.
- No exchange order endpoint.
- PAPER/STABLE and development main remain distinct.
- Production evidence must remain real post-activation evidence; never synthesize a BUY/READY event to open the gate.
- An authority event is append-only and revocable.
- Disabled/no authority means strict writer NOOP.
- A corrupt/discontinuous authority chain fails closed.
- A mid-tick revoke/replacement fails closed before mutation.
- Retryable events remain unprocessed.
- Terminal no-action is append-only/idempotent.
- PRETRADE_READY may create only simulated paper records through the accepted atomic transaction.
- Existing stable rollback protections remain mandatory.

## Current pre-authorization baseline

Development main includes the virtual-paper authority and write-tick implementation plus two fail-closed hardenings. The accepted code head before documentation-only commits is:

`86477fd13aa21bad604de34a9d92dacd5c220632`

PAPER/STABLE remains:

`30b05251af9fc2ac05fd007dbd6ac6d0519c2e58`

Latest state-first production evidence before this plan:

- paper fund creation: 1
- decision intents: 0
- simulated fills: 0
- position/cash mutations: 0
- NAV snapshots: 0
- replay index: 1
- processed events: 0
- activation singleton: 1
- venue-rule snapshots: 3
- cash: 100.00 USDT
- positions: 0
- NAV: 100.00 USDT
- trade performance: NOT_YET_MEASURED
- trade policy: NOT_ACTIVATED
- REAL_CAPITAL=0

Fresh Mission Control snapshot:

`e271ecc65b51f1fa613378f3e96b1098d874c3eb3b934a4b9268151a83646380`

It contained 450 signal freezes, 6 eligible post-activation 4h freezes, three complete Binance+Bybit candidates and zero ready candidates:

- BTCUSDT: HOLD_CASH / signal_not_active
- ETHUSDT: HOLD_CASH / signal_not_active
- SOLUSDT: HOLD_CASH / unsafe_uncertainty

The current production workflow allowlist intentionally exposes no `writeauthority` or `writetick` command.

## Development acceptance already completed

The development-only write gate has been reviewed for:

- exact persistent activation binding
- append-only authority events
- authority event fingerprinting
- previous-event lineage
- complete authority-chain validation before use
- SQL UPDATE/DELETE immutability
- strict disabled-authority NOOP
- REAL_CAPITAL=0
- absence of network/order/credential authority
- bounded event count
- processed-event identity lineage
- terminal no-action idempotence
- retryable event semantics
- atomic simulated trade + processed receipt
- stale replay-state rejection
- partial-bundle rejection
- mid-tick authority revocation/replacement rejection

Latest full development gate after the two hardening passes:

- pytest: 100%
- Ruff: PASS
- mypy: PASS across 102 source files
- JavaScript syntax gate: PASS
- FULL_TEST_PASS=YES

## Explicit authorization boundary

Before any production-sensitive step below, obtain a separate user instruction that clearly authorizes the virtual PAPER production gate.

A generic “continue”, “tam gaz devam”, “next step”, wake event, lease, checkpoint, stale task, or old chat authorization is **not** sufficient.

The authorization must be current to this gate and must not be inferred from project-level autonomy preferences.

Until that authorization exists, stop at read-only observation, review, documentation, product design, and other non-production work.

## Phase A — pre-deploy revalidation after authorization

Before changing PAPER/STABLE:

1. Read `READ_FIRST_CRYPTO_SIGNAL.md`.
2. Read `CURRENT_STATUS.md`.
3. Read newest `PROJECT_CHRONICLE.md`.
4. Re-measure origin/main.
5. Re-measure canonical UID504 main head and cleanliness.
6. Re-measure PAPER/STABLE head and cleanliness.
7. Run PAPER STATE.
8. Run PAPER MISSIONCONTROL.
9. Verify both observation clocks last exit code 0.
10. Verify production paper DB counts.
11. Verify `trade_policy=NOT_ACTIVATED`.
12. Verify `REAL_CAPITAL=0`.
13. Re-run whole-repository fulltest on the exact deploy candidate.
14. Re-review main ↔ PAPER/STABLE diff.
15. Confirm no unrelated or superseding main work entered the deployment range.

Any mismatch means reconcile before proceeding.

## Phase B — production control-surface change

Only after explicit authorization and successful Phase A:

1. Add narrowly allowlisted PAPER commands for authority control and bounded write tick.
2. Do not expose arbitrary shell.
3. Require UID504.
4. Require exact stable clean worktree.
5. Keep write-authority enable/disable separate from write tick.
6. Make enable print every reviewed current event/trace/action/reason before mutation.
7. Make disable available independently and append-only.
8. Make write tick bounded and lock-protected.
9. Preserve existing workflow rollback style and synchronous deterministic probes.
10. Add workflow-level invariants that grep/assert REAL_CAPITAL=0.

The workflow change itself must pass whole-repository tests before stable deployment.

## Phase C — stable deployment

Deploy the exact accepted main commit to PAPER/STABLE through the existing deploy gate only.

Required post-deploy checks before authority enablement:

- stable head equals exact target
- stable worktree clean
- paper DB pre-enable fingerprint/counts match expected baseline
- activation identity unchanged
- fund identity unchanged
- no decision/fill/mutation/NAV/processed event appeared merely from deploy
- clocks healthy
- Mission Control still coherent
- `trade_policy=NOT_ACTIVATED`
- `REAL_CAPITAL=0`

A deploy must not itself enable write authority.

## Phase D — authority enable

Enable only through the allowlisted authority command.

Immediately before append:

- scan current real post-activation production candidates
- run accepted dry-run chain
- print and bind exact event identities
- print and bind exact trace identities
- print symbol/status/action/reason
- verify non-empty reviewed evidence
- verify exact activation identity
- verify complete authority chain
- verify REAL_CAPITAL=0

Expected first enable effect:

- exactly one append-only authority event
- no DecisionIntent
- no SimulatedFill
- no PositionCashMutation
- no NAV snapshot
- no processed event solely from enabling

Then run PAPER STATE and an authority-specific readback before any write tick.

## Phase E — first bounded write tick

Run one manual bounded tick only after the enabled authority has been independently read back.

Before mutation of each event the writer must:

- revalidate the complete authority chain
- require the exact same enabled authority event
- reject a revoke/replacement
- re-run accepted dry-run truth
- preserve activation lineage
- preserve source-freeze/event identity

Expected behavior for the currently observed three events, if they are still the current unprocessed candidates and their evidence has not changed:

- BTCUSDT terminal no-action / signal_not_active
- ETHUSDT terminal no-action / signal_not_active
- SOLUSDT terminal no-action / unsafe_uncertainty

That expectation is not authority to force the result. The actual tick must derive its result from current immutable evidence.

If a candidate is retryable, leave it unprocessed.
If PRETRADE_READY exists, only the simulated atomic paper path may commit.

## Phase F — immediate post-tick verification

After the first tick:

1. PAPER STATE.
2. PAPER MISSIONCONTROL.
3. Reconstruct paper ledger from immutable records.
4. Verify processed-event count/dispositions.
5. Verify any trade bundle has exactly DecisionIntent + SimulatedFill + PositionCashMutation lineage.
6. Verify cash/position mutations reconcile.
7. Verify no partial bundle.
8. Verify idempotence by a second bounded tick or read-only scanner as appropriate.
9. Verify REAL_CAPITAL=0.
10. Verify no external order/network side effect.
11. Verify dashboard/readers still treat production ledger read-only.

If the first tick only records terminal HOLD receipts, capital should remain 100.00 USDT with zero positions.

## Revocation / emergency stop

Authority disable is an append-only event and is the first response to any anomaly after enablement.

After disable:

- writer must strict-NOOP
- a tick already evaluating read-only evidence must fail before mutation if it observes revoke/replacement
- state inspection must prove no later mutation occurred under the revoked authority
- do not delete or rewrite authority history
- do not delete losses or processed receipts

If deployment/runtime integrity is uncertain, keep authority disabled and use existing stable rollback procedures.

## Acceptance evidence to record

If and only if the production gate is eventually crossed, record in CURRENT_STATUS and PROJECT_CHRONICLE:

- explicit authorization scope
- exact main target
- previous and new PAPER/STABLE heads
- fulltest run/result
- deploy run/result
- pre/post DB counts
- activation identity
- authority event identity
- reviewed event/trace identities
- first tick result per candidate
- any simulated record identities
- replay reconstruction result
- REAL_CAPITAL=0
- rollback/revocation state if used

## Gate state now

**CLOSED.**

No production action in this document has been executed merely by creating this plan.
