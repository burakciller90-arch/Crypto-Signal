# Crypto Signal Agent Operating Contract

This file is mandatory context for every agent working on Crypto Signal.

**Conversation memory is non-authoritative.** The current repository, the current Workbench/runtime evidence, and the active canonical roadmap define truth.

## Project identity

Repository:

`burakciller90-arch/Crypto-Signal`

Canonical development workbench:

`/Volumes/Crypto-504/Crypto-Signal-Workbench`

Canonical stable repository copy:

`/Volumes/Crypto-504/Crypto-Signal-Workbench/repo`

Canonical runtime root:

`/Volumes/Crypto-504/Crypto-Signal`

Canonical Development runtime:

`/Volumes/Crypto-504/Crypto-Signal/Development`

Runtime owner:

- macOS account: `crypto-signal-agent`
- UID: `504`

## Non-negotiable safety

- `REAL_CAPITAL=0`.
- No real-money trading authority.
- No exchange/broker write authority may be introduced.
- Existing immutable/frozen historical evidence is never rewritten to improve acceptance.
- Missing/stale/unsupported evidence remains explicit; never fabricate a replacement.
- Confluence is evidence support/opposition, not calibrated probability.
- Do not claim 80%+ accuracy without real forward evidence.
- Do not touch Durdurulmaz or Quantum Capital.

## Canonical authority

Read these as current project authority before implementation:

1. **`ACTIVE_ROADMAP.md`** — canonical active-program pointer and mandatory read order.
2. `READ_FIRST_CRYPTO_SIGNAL.md`
3. `CURRENT_STATUS.md`
4. newest `PROJECT_CHRONICLE.md` entry
5. `ENVIRONMENT_REGISTRY.md`
6. **`docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`** — canonical final-product umbrella roadmap.
7. the mechanically active phase authority — currently `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md` for FP0/RDP11.
8. relevant accepted contracts/acceptance records for the exact slice.
9. `docs/CRYPTO_SIGNAL_SSD504_WORKBENCH.md` when work touches the SSD504 workbench/runtime.

Historical roadmaps/acceptance documents remain useful evidence, but they do not override the current active frontier.

When documents conflict:

1. current machine-readable/live evidence wins for current runtime state;
2. current Git/GitHub state wins for current code/merge state;
3. `ACTIVE_ROADMAP.md` + `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md` define product-program priority;
4. the current mechanically active phase authority defines the acceptance gate inside that program;
5. historical acceptance/roadmap files are context only.

## Mandatory bootstrap on every new prompt/session

Before changing code or telling the user where the project is:

1. Read this `AGENTS.md`.
2. Read **`ACTIVE_ROADMAP.md`**.
3. Read `docs/agent/CURRENT_FRONTIER.md`.
4. Read the tail of `docs/agent/HANDOFF_LOG.md`.
5. If working on the Mac/runner, read `/Volumes/Crypto-504/Crypto-Signal-Workbench/WORKSPACE_READ_FIRST.md`.
6. Read the canonical authority files above.
6. Verify actual Git/GitHub state:
   - current `main` SHA;
   - recent relevant commits;
   - open PRs/branches;
   - latest relevant GitHub Actions runs;
   - Workbench `repo/` branch, HEAD and dirty state.
7. Verify the relevant Development/runtime state read-only before promoting a live/runtime gate.
8. Compare actual evidence with `CURRENT_FRONTIER.md`.
9. Continue from the **first mechanically unclosed roadmap gate**.
10. Never ask the user to reconstruct where the project was left if the repository can answer it.

## Mandatory durable start checkpoint

Before implementing any new roadmap slice, sub-slice, bugfix, runtime gate, or other task that can outlive the current turn:

1. Update `docs/agent/CURRENT_FRONTIER.md` on the active task branch **before code changes**.
2. Append a start entry to `docs/agent/HANDOFF_LOG.md`.
3. Record at minimum:
   - exact task-start `main` SHA;
   - active branch and worktree path, or explicitly state that no session-local worktree exists;
   - active roadmap gate/slice;
   - duplicate/stale-work check result;
   - safety state (`REAL_CAPITAL=0`, historical backfill policy, Durdurulmaz/Quantum untouched);
   - the exact bounded goal;
   - current blocker;
   - exactly one concrete `nextAction`.
4. If implementation already began before this checkpoint was written, stop and repair the checkpoint immediately before continuing.
5. Treat this start checkpoint as the minimum resumable state: another agent must be able to continue from repository evidence without reading chat history.

For longer slices, add another durable checkpoint before a materially different phase (for example implementation -> acceptance, acceptance -> merge) when losing the current turn would otherwise make the next action ambiguous.

## Duplicate-work guard

Before implementing:

- search recent commits/PRs/workflows for the same roadmap slice;
- do not recreate work already merged by another agent;
- do not reopen a PASS phase without contrary mechanical evidence;
- a commit title is not sufficient to close a roadmap phase;
- a green generic workflow is not sufficient to close a roadmap phase;
- inspect the exact acceptance output required by the active roadmap.

If another agent advanced `main` after your task began, refresh/rebase/reconcile before merge. Never overwrite concurrent work.

## Worktree / branch discipline

- Never develop directly on `main`.
- One agent/task = one branch.
- For parallel agents, prefer a dedicated worktree under:
  `/Volumes/Crypto-504/Crypto-Signal-Workbench/worktrees/<task-slug>`
- Never allow two agents to mutate the same branch/worktree.
- Keep `/Volumes/Crypto-504/Crypto-Signal-Workbench/repo` as the clean canonical `main` inspection/sync point whenever possible.
- Before PR/merge, compare against the latest current `main`.

## Final Product program discipline

The active product program must be read from `ACTIVE_ROADMAP.md`, never remembered from chat.

Current mechanically unclosed gate at the time this authority was opened:

- RDP0–RDP10: PASS;
- **FP0 / RDP11: ACTIVE — real continuous soak**;
- earliest 72-hour eligibility: `2026-10-02T09:13:21.134000Z`.

RDP11 closes only when its roadmap PASS conditions are mechanically demonstrated. Elapsed time alone is never sufficient.

After FP0/RDP11 PASS, continue through the first mechanically unclosed phase of `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`.

Before every FP phase/sub-slice, classify the target as:
- `REUSE`;
- `EXTEND`;
- `BUILD`;
- `EXPLICITLY_UNAVAILABLE`.

Record that classification in CURRENT_FRONTIER before coding. Intelligence Stream S0-S16/F0-F10/MI1-MI6, R21, R22, R24 and other accepted foundations must not be rebuilt merely because their presentation is being redesigned.

While the RDP11 soak is active, do not mutate the frozen soaked runtime/observer contract or historical/frozen evidence merely to advance a later final-product phase.

## End-of-turn handoff is mandatory

Before ending a productive turn:

1. Update `docs/agent/CURRENT_FRONTIER.md` with the newest verified checkpoint.
2. Append a new entry to `docs/agent/HANDOFF_LOG.md`.

Every handoff must include:

- verified timestamp;
- exact current `main` SHA;
- active roadmap gate;
- PASS/FAIL/WAITING evidence;
- branch/worktree used;
- PR number and merge SHA if applicable;
- workflow/run IDs;
- files changed;
- remaining blocker;
- exactly one next concrete action;
- `REAL_CAPITAL=0` confirmation;
- explicit confirmation that Durdurulmaz and Quantum Capital were untouched.

Do not claim PASS or advance the frontier without the corresponding mechanical evidence.

## User shorthand

When the user says only:

`Kaldığın yerden devam et`

interpret it as:

- run this bootstrap protocol;
- distrust conversation memory;
- verify real Git/GitHub + Workbench + runtime truth;
- avoid stale/duplicate work;
- continue from the first mechanically unclosed gate;
- leave a durable handoff before stopping.
