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

1. `READ_FIRST_CRYPTO_SIGNAL.md`
2. `CURRENT_STATUS.md`
3. `PROJECT_CHRONICLE.md`
4. `ENVIRONMENT_REGISTRY.md`
5. `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md`
6. `docs/CRYPTO_SIGNAL_EVIDENCE_DEPTH_VISUAL_PROOF_FRONTIER_V1.md`
7. `docs/CRYPTO_SIGNAL_SSD504_WORKBENCH.md`

Historical roadmaps/acceptance documents remain useful evidence, but they do not override the current active frontier.

When documents conflict:

1. current machine-readable/live evidence wins for current runtime state;
2. current Git/GitHub state wins for current code/merge state;
3. `CURRENT_STATUS.md` + active RDP roadmap define execution priority;
4. historical acceptance/roadmap files are context only.

## Mandatory bootstrap on every new prompt/session

Before changing code or telling the user where the project is:

1. Read this `AGENTS.md`.
2. Read `docs/agent/CURRENT_FRONTIER.md`.
3. Read the tail of `docs/agent/HANDOFF_LOG.md`.
4. If working on the Mac/runner, read `/Volumes/Crypto-504/Crypto-Signal-Workbench/WORKSPACE_READ_FIRST.md`.
5. Read the canonical authority files above.
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

## Active Evidence Data Plane closure discipline

Current phase must be read from the active roadmap, not remembered.

At the baseline that created this contract, RDP0–RDP8 were PASS and RDP9 was ACTIVE.

RDP9 only closes when its roadmap PASS conditions are mechanically demonstrated:

- the same raw truth cannot silently create duplicate confidence;
- material venue disagreement is visible to the decision layer.

Do not skip to RDP10 simply because RDP9 implementation commits exist. First verify exact-main acceptance and update canonical status/roadmap evidence.

RDP10 only closes when every family exposes the strongest exact frozen customer-proof actually available, with stale/unavailable truth preserved and no current-data substitution.

RDP11 requires its real continuous soak; elapsed acceptance evidence must never be fabricated.

Portfolio/frontend integration must not treat an evidence rail as trusted before its RDP gate is actually closed.

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
