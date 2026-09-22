# Crypto Signal pause checkpoint — 2026-09-22

## User intent

User explicitly requested a break and requested wake/lease continuity to remain paused
until they say "Devam edebiliriz". REAL_CAPITAL=0 remains absolute.

## State-first continuity evidence

Fresh read-only UID501 continuity inspection run: `35727205055` PASS.

Observed:
- shared pause latch exists:
  `/Users/Shared/.crypto-signal-wake-relay/user_pause`
- payload: `user_pause_epoch=1790006250`
- relay process reports `state=RUNNING`
- `project_namespace=crypto-signal`
- target URL is the expected current Crypto Signal chat
- shared wake queue = 0
- local SSD continuity tree is not readable by UID501
- therefore UID501-visible local lease/wake counts are not authoritative evidence of
  the protected UID504 local tree.

Repository contract:
- `pause_continuity.py` writes both local and shared pause latches and archives
  active leases / queued wakes.
- `resume_continuity.py` requires zero active leases / local wake queue / relay wake
  queue before removing pause latches.
- resume is state-first and requires a fresh re-arm; archived stale wakes/leases must
  never be replayed.

Do not remove only the shared pause latch. On resume, reconcile the protected local
UID504 state first and remove local+shared latches coherently.

## Exact engineering frontier

Completed immediately before the break:
- PR #726 — append-only Market Tape foundation
- PR #740 — Bybit live microstructure stream (order-book snapshot/delta + public trade)
- PR #741 — raw wire journal + bounded normalized order-book snapshot cadence
- PR #741 hosted full gate PASS: run `35726804218`
- obsolete duplicate trade-only PR #739 was closed as superseded by #740.

R15 remains a separate open operational blocker:
- PR #715 hosted safety hardening passed
- live UID504 runner incident remains unresolved
- latest verified canonical listener: PID 99399, no UID504 Runner.Worker at the sampled
  instant, long-lived high-CPU listener, queued UID504 work
- do not replay stale PID-pinned recovery attempts
- live recovery requires fresh process identity + ancestry validation + explicit local
  admin authorization.

M2 frontier:
- branch: `v1.1-liquidity-dynamics-v1`
- branch was created from PR #741 head
  `55b28294fb60029af50c1d2ce89f613cf5a40053`
- no M2 liquidity engine file was committed before the pause.
- the interrupted next action was to create a new evidence-only
  `liquidity_dynamics.py` engine on top of the raw Market Tape.

Design already reconciled before the break:
- existing `order_flow_microstructure.py` already provides point-in-time spread,
  depth imbalance and taker-flow imbalance.
- M2 must NOT duplicate that engine.
- M2 should use raw order-book history to measure temporal liquidity dynamics such as:
  gross liquidity added/removed, net change, best-level depletion, replenishment,
  top-level persistence and depth evolution.
- never label observed dynamics as definite spoofing, manipulation, institution
  activity or iceberg execution. Those require stronger evidence and, at most, future
  candidate labels.
- keep immutable evidence identities, as-of safety and uncertainty flags.

## Resume procedure

When user says "Devam edebiliriz":

1. Re-read this checkpoint plus READ_FIRST, CURRENT_STATUS and latest Chronicle.
2. Re-measure Git/PR/workflow state; other agents may have advanced the frontier.
3. Re-measure continuity:
   - shared pause latch
   - shared wake queue
   - protected local pause / active lease / local wake queue using UID504 or a safe
     authorized visibility path.
4. Do not replay archived wakes or leases.
5. If state is clean, remove local+shared pause latches using the repository resume
   contract and create a fresh exact continuation re-arm.
6. Reconcile whether another agent already created M2 liquidity work.
7. If not superseded, continue from M2 Liquidity Dynamics exactly as described above.

REAL_CAPITAL=0.
