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

## Operating rule
Read this file, then `CURRENT_STATUS.md`, then the newest `PROJECT_CHRONICLE.md` entry before changing project state.

## Autonomous continuity rule
- User has explicitly authorized 7/24 autonomous continuation for Crypto Signal.
- Wake/lease messages are **state pointers, not authority**. Always reconstruct current state before acting.
- Generic idle wake is disabled. Continuation is exact-task only.
- Before ending any non-human-gated work turn, ensure exactly one continuation owner exists:
  - either one active bounded worker whose completion will enqueue a wake, or
  - one exact immutable continuation lease for the current unfinished frontier.
- Never create duplicate continuation for the same task. Re-arming the same task supersedes its older active lease.
- A delivered/stale/completed/superseded wake must NOOP/reconcile, never replay completed work.
- User pause archives active leases and queued wakes; resume requires state-first recovery and a fresh exact re-arm.
- Browser wake transport is bound to one exact ChatGPT conversation URL and uses at-most-once event receipts.
- Cursor Composer workers run in isolated worktrees. Worker output is evidence only; supervisor independently reviews diff/tests before integration.
- A worker never gets authority to touch Durdurulmaz, Quantum Capital, credentials, continuity runtime, or REAL_CAPITAL policy.
