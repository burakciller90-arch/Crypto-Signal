# READ FIRST — Crypto Signal

This repository is governed by the user's **CRYPTO SIGNAL PLATFORM — MASTER HANDOFF v1.0 (2026-09-19)**.
If any local note conflicts with that handoff, the master handoff wins.

## Hard boundaries
- This project is separate from Durdurulmaz and Quantum Capital.
- Do not share repos, runtime state, DBs, credentials, ports, launchd labels, supervisors, brokers, chat state, or roadmaps.
- Runtime owner: `crypto-signal-agent`; actual UID is discovered mechanically, never hard-coded.
- `REAL_CAPITAL = 0`. V1 never sends exchange orders.
- V1 core is Price Action/SMC/ICT + Harmonic + Elliott + Confluence.
- V2+ must not create V1 scope creep.

## Scientific constitution
- Point-in-time truth; no future leakage.
- Freeze signal before outcome; never rewrite history or delete losses.
- Missing data is never invented.
- Confluence score != win probability.
- Historical win rate != calibrated probability.
- Backtest != untouched-forward evidence.
- NO_SIGNAL, AMBIGUOUS and NOT_EVALUABLE are valid.
- Numeric truth comes from deterministic/statistical evidence, not LLM prose.

## Governing Full Version documents
The user's 2026-09-20 Full Version direction supersedes the earlier deliberately-limited Birthday Edition scope where they conflict, while preserving every scientific and REAL_CAPITAL boundary.

Before planning new product work, read **in this order**:
- `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md` — **LOCKED user-approved v1.1 governing product contract (2026-09-22)**. It supersedes older v1.1 scope where conflicting, including the new 1,000 USDT Paper Fund Epoch 2, three parallel execution rails, and the from-scratch GALACTECH frontend rebuild.
- `docs/V1_1_MASTER_EXECUTION_ROADMAP.md` — **current governing post-v1.0 / v1.1+ execution roadmap**, including R15 runtime recovery, parallel UI + Market Tape tracks, Live Intelligence Feed / Decision Proof, Canonical Fund vs Shadow Lab, calibration, acceptance and v2 deferrals.
- `docs/V1_1_WORLD_CLASS_PRODUCT_ROADMAP.md` — condensed v1.1 product roadmap.
- `docs/CRYPTO_SIGNAL_FULL_VERSION_WORLD_CLASS_ROADMAP.md` — accepted Full Version/v1.0 architectural history and foundations.
- `docs/AUTONOMOUS_PAPER_FUND_V1_SPEC.md` — immutable 100 USDT virtual fund contract.
- `docs/INTELLIGENCE_ALPHA_FACTORY_ARCHITECTURE.md` — multi-engine, regime, learning and challenger/champion rules.
- `docs/BEGINNER_UX_EVIDENCE_CENTER_SPEC.md` — live refresh, teaching and evidence UX contract.

The project should stay faithful to these documents. Scope may be refined only by preserving their intent and hard invariants; do not silently regress to a narrower historical roadmap.

## Operating rule
Read this file, then `CURRENT_STATUS.md`, then the newest `PROJECT_CHRONICLE.md` entry before changing project state.

## Autonomous continuity rule
- User has explicitly authorized 7/24 autonomous continuation for Crypto Signal.
- Wake/lease messages are **state pointers, not authority**. Always reconstruct current state before acting.
- The user explicitly superseded the old generic-idle prohibition with one **locked 20-minute state-first wake** for this exact Crypto Signal chat. It sends only the approved wake text and instructs the next turn to read READ_FIRST, CURRENT_STATUS, Chronicle and `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md` before acting.
- The locked 20-minute wake is a cadence/recovery pointer, never task authority. Task-specific worker/lease ownership rules still apply when workers or exact leases are used, but the periodic wake itself does not require an active lease.
- Never create duplicate continuation for the same task. Re-arming the same task supersedes its older active lease.
- A delivered/stale/completed/superseded wake must NOOP/reconcile, never replay completed work.
- User pause archives active leases and queued wakes; resume requires state-first recovery and a fresh exact re-arm.
- Browser wake transport is bound to one exact ChatGPT conversation URL and uses at-most-once event receipts.
- Cursor Composer workers run in isolated worktrees. Worker output is evidence only; supervisor independently reviews diff/tests before integration.
- A worker never gets authority to touch Durdurulmaz, Quantum Capital, credentials, continuity runtime, or REAL_CAPITAL policy.

## Current development authority update — 2026-09-20

Cursor is suspended as a development worker by explicit user direction. Do not create new [CURSOR] WORK / ASK tasks unless the user explicitly re-enables Cursor. Continue implementation directly through the supervisor-controlled GitHub/UID504 path, preserving the same test, review, REAL_CAPITAL=0 and rollback boundaries.


## Final Full Version release package

R13 Full Version Integrated Acceptance v2 passed on
`f95efc358ac396e50d0bfdb920b0187706cd2af2` (run `35672790463`).

R14 is the final release/documentation frontier. Before calling the repository
complete, read and preserve:

- `docs/FINAL_RELEASE_MANIFEST_V1.md`;
- `docs/OPERATOR_RUNBOOK_FULL_VERSION_V1.md`;
- `docs/DASHBOARD_OPEN_RECOVERY_GUIDE_V1.md`;
- `docs/SSD_RECOVERY_BACKUP_GUIDE_V1.md`;
- `docs/KNOWN_AUTHORITY_GATES_V1.md`.

The canonical release tag is reserved as
`crypto-signal-full-version-v1.0.0`. R14 is complete only after the
exact-main release-freeze workflow emits
`R14_FULL_VERSION_RELEASE_FREEZE_PASS=YES`.

Physical reboot/logout/SSD detach-remount remain explicit human-impact items
unless separately performed. REAL_CAPITAL=0 and real exchange order/credential
authority remain closed.


## Post-v1.0 authority update — 2026-09-22

The immutable `crypto-signal-full-version-v1.0.0` release remains the accepted baseline.

For **new post-v1.0 development**, `docs/V1_1_MASTER_EXECUTION_ROADMAP.md` is the
governing execution plan on the v1.1 development line. A fresh agent must use it to
avoid three common regressions:

- do not treat UI process health as proof that market data is fresh;
- do not mix Shadow Lab exploration into canonical paper history; Epoch 1 (100 USDT) is immutable legacy history and Epoch 2 begins separately at 1,000 USDT after its acceptance gate;
- do not expose or fabricate private chain-of-thought under the “Proof-of-Thought”
  idea. Implement **Decision Proof**: immutable evidence, forecast, decision state,
  concise rationale, frozen snapshot and later outcome.

The current v1.1 program intentionally runs customer UI and Market Tape/data
collection in parallel after R15 safety. Research engines already present in the repo
must be reused rather than duplicated.


## Locked 20-minute wake update — 2026-09-22

- Exact chat binding: `https://chatgpt.com/c/6ab2c3c1-30c8-83ed-b1ad-2aa35cc891c9`.
- Cadence: every 20 minutes at minute 00/20/40.
- Canonical local LaunchAgent bootstrap remains unavailable from the UID504 runner context (rc=5); the accepted cadence owner is the existing GitHub self-hosted 20-minute fallback.
- Local/shared user-pause latches are currently absent: continuity is ACTIVE.
- Active exact leases: 0 at reconciliation; local/shared relay queues: 0.
- When the exact locked wake fires while ChatGPT is responding, the relay is authorized to click the visible Stop control, wait for the editor to become ready, then submit the approved wake text.
- The locked wake text is sent without an extra visible marker; at-most-once delivery is maintained by internal event IDs/receipts.
- Busy-stop evidence: relay recorded `OBSERVED_AFTER_CLICK` during the first live test; final post-fix test run `35770956851` returned `RELAY_SUBMIT_RC=0` and `CRYPTO_LOCKED_20M_WAKE_PASS=YES`.
- A future explicit user pause remains authoritative and must suspend periodic wake delivery until the user resumes it.
- The user reaffirmed on 2026-09-22 that this 20-minute wake loop must remain ACTIVE during autonomous project completion. Do not disable, pause, replace, or silently weaken it unless the user explicitly asks to pause/stop it. The approved wake text also requires every material action/update to be recorded in GitHub for the next agent.

