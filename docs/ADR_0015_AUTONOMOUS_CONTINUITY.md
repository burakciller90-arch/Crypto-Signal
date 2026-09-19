# ADR 0015 — Autonomous Continuity and Cursor Worker Governance

Status: Accepted for infrastructure implementation
Date: 2026-09-20

## Authorization
The user explicitly authorized autonomous 7/24 continuation for Crypto Signal.

This authorization applies only to this project and does not relax:
- REAL_CAPITAL = 0
- project isolation from Durdurulmaz and Quantum Capital
- scientific point-in-time rules
- destructive-action caution
- credential and human-authentication boundaries

## Continuation ownership
Every active development turn must end with exactly one continuation owner:
1. an active bounded worker whose completion enqueues a wake, or
2. one exact continuation lease for the current unfinished task.

Generic idle wake is disabled.
## Exact lease
A lease contains:
- task identity
- due time
- immutable checkpoint path
- checkpoint SHA256
- creation time

Re-arming the same task supersedes the older active lease.
A lease is only a state pointer; it does not create authority or imply PASS.

On delivery, ChatGPT must reconstruct:
1. READ_FIRST_CRYPTO_SIGNAL.md
2. CURRENT_STATUS.md
3. latest relevant PROJECT_CHRONICLE.md
4. exact checkpoint
5. current Git / worker / wake / lease state

A completed, stale, duplicate or superseded task must be reconciled as NOOP.
## Wake transport
The transport is bound to one exact ChatGPT conversation URL.

Delivery rules:
- never send while ChatGPT is visibly busy
- never overwrite a non-empty user draft
- every event receives a deterministic marker
- event receipts enforce at-most-once submission intent
- the receipt is written before the single send-button click
- conflicting reuse of one event ID with different content is rejected

The bridge processes only:
- exact due leases
- bounded worker-completion queue items

No fallback or generic idle chatter is permitted in V1 continuity.
## Pause / resume
User pause:
- creates a pause latch
- archives active leases
- archives queued wakes
- does not kill an already-running bounded worker unless separately requested

Resume:
- removes the pause latch
- does not replay archived stale events
- requires state-first recovery and fresh exact re-arm

## Cursor worker
Cursor Agent / Composer is an optional bounded worker.

Worker rules:
- isolated Cursor worktree
- one explicit task ID and prompt
- no direct main-branch authority
- no continuity-runtime edits
- no other-project access
- run focused tests / quality gates
- commit valid worker changes in its worktree
- completion result is evidence, never automatic PASS
## Supervisor integration
After worker completion, ChatGPT supervisor must:
- inspect exact output and worktree
- inspect diff/commit mechanically
- run independent tests
- reject scope creep
- integrate only reviewed changes
- update project state
- choose the next bounded task

## Availability boundary
The local wake transport requires:
- the crypto-signal-agent GUI session to remain logged in
- Safari to keep the bound ChatGPT conversation available
- Terminal to Safari Automation permission
- Safari JavaScript-from-Apple-Events permission
- the continuity bridge process to remain running

If the GUI session is logged out, browser-based self-wake cannot operate.
This is an operational constraint, not a project-state loss.
