# Crypto Signal — ACTIVE ROADMAP POINTER

Status: **ACTIVE / CANONICAL**
Updated: 2026-09-30
Repository: `burakciller90-arch/Crypto-Signal`
Safety: **REAL_CAPITAL=0**

## 1. Canonical final-product roadmap

Every agent must treat this as the current product-program authority:

**`docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`**

Do not infer the active product roadmap from old chat memory, old roadmap filenames, or historical acceptance records.

### Roadmap authority lock / anti-drift rule

This pointer is the **only file allowed to select the active product-program roadmap**.

- The sole active product-program roadmap is `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`.
- If any older roadmap, status file, handoff entry, branch name, commit message or historical document says that a different roadmap is "active", treat that statement as **STALE / HISTORICAL** unless this `ACTIVE_ROADMAP.md` file on current `main` has been explicitly changed to point elsewhere.
- Phase-specific authorities may define acceptance mechanics for the phase selected by this roadmap; they do **not** replace the umbrella roadmap.
- `CURRENT_FRONTIER.md` and `HANDOFF_LOG.md` record execution state only; they cannot redefine roadmap authority.
- Never choose a roadmap because its file timestamp is newer, its filename looks more specific, or a previous agent mentioned it.
- A roadmap-authority change must be an explicit, dedicated repository change that updates this pointer and the agent bootstrap contract together. Otherwise NOOP the conflicting claim.


## 2. First mechanically unclosed gate

**FP0 / RDP11 — Continuous soak + final Evidence PASS**

Mechanical gate authority while FP0 is open:

**`docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md`**

Current RDP11 soak state:
- frozen Product/Development runtime target remains: `3d9f33db3f1189571d40566125fbeabd00c04930`;
- previous epoch `rdp11-3d9f33db-20260929`: **INVALIDATED / IMMUTABLE HISTORICAL EVIDENCE**;
- first mechanical invalidation proof: run/job `36622461578/109591020809`, observer `/api/intelligence-center` read raised `ConnectionResetError:[Errno 54] Connection reset by peer`;
- previous `2026-10-02T09:13:21.134000Z` eligibility timestamp is **VOID FOR PASS**;
- active replacement epoch: `rdp11-3d9f33db-20260930-r2`;
- re-anchor PR/merge: `#1699` / `62540a3746c101530cd843353507a6746579bf15`;
- merged-main observer run: `36637452090`;
- attempt 1 / job `109641453750`: failed **before observer invocation and before anchor creation** on finite SSE `curl: (18) transfer closed with outstanding read data remaining`; preserved as pre-anchor continuity evidence;
- one controlled rerun only, attempt 2 / job `109642444475`: **SUCCESS**;
- `RDP11_SOAK_ANCHOR_CREATED=YES`;
- R2 soak start UTC: `2026-09-29T22:10:09.650000Z`;
- earliest R2 72h eligibility UTC: `2026-10-02T22:10:09.650000Z`;
- earliest R2 72h eligibility Europe/Istanbul: `2026-10-03T01:10:09.650000+03:00`;
- `RDP11_SOAK_72H_ELIGIBLE=NO`;
- `RDP11_SOAK_SIDE_CAR_ONLY=YES`;
- `RDP11_CANONICAL_RUNTIME_MUTATED=NO`;
- `HISTORICAL_BACKFILL=NO`;
- `REAL_CAPITAL=0`;
- RDP0-RDP10: PASS;
- RDP11: ACTIVE / NOT PASS.

Do not delete, rewrite, backfill or reinterpret either the invalidated epoch or its failure evidence. Elapsed time alone never closes FP0; R2 must remain non-invalidated for its own full 72-hour minimum and then pass the final accumulated RDP11 evidence audit mechanically.

## 3. Locked post-FP0 sequence

FP1+ implementation may proceed **in isolated parallel branches/worktrees during FP0** when it cannot mutate the soaked runtime, observer contract or frozen/historical evidence.

After FP0 PASS, final integrated runtime acceptance/cutover may proceed from the first mechanically unclosed phase in:

`docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`

High-level order:

```text
FP0  RDP11 Evidence Soak
 ↓
FP1  Final Product Human Read Models
 ↓
FP2–FP7  Paper Vault / Autopilot / Execution / Risk / Passport / Trust
 ↓
FP8–FP15 Final Command Center / Market Story / Family Visuals /
          Markets / Events / Watchlist+Alerts+Search / Portfolio / History
 ↓
FP16 UX + Accessibility + Long-Session Acceptance
 ↓
FP17 Real End-to-End Final Product Acceptance
 ↓
FP18 Controlled Cutover + Release Freeze
```

## 4. Accepted work that must NOT be rebuilt

Treat these as REUSE unless contrary mechanical evidence exists:
- Intelligence Stream V1 S0-S16;
- Stream final deficiency closure F0-F10;
- Message Intelligence MI1-MI6;
- RDP0-RDP10 accepted evidence/data/proof work;
- R21 canonical Epoch 2 accounting;
- R22 Transaction & Decision Tape;
- R24 Performance & Trust;
- Smart Capital Allocator / accepted fixed-fractional sizing;
- S11 three-vault Capital Story lifecycle;
- accepted GALACTECH Command/Markets/Capital/Archive/Performance product adapters;
- Stream SSE/history/search/filter/deep-link/sound;
- alert/outbox foundation;
- shared UID504 Chromium visual-audit infrastructure.

Historical implementation may be redesigned at the presentation layer without rebuilding its accepted canonical truth.

## 5. Known final-product gaps

Examples that remain real work after FP0:
- natural forward canonical Paper Capital liveness/productization;
- new immutable Paper Vault/policy versioning without rewriting Epoch 1/2;
- execution realism beyond current full-fill fee/spread/slippage v1;
- order-book/queue/latency/partial-fill/funding semantics where accepted;
- Trade Passport customer read model;
- world-class non-Geometry deterministic family visualizations;
- final 10-second Command Center composition;
- Asset Intelligence / Screener;
- Event Center;
- Watchlist;
- semantic alerts;
- global command search;
- unified Portfolio/History product UX.

Always run a duplicate audit before implementing any item.

## 6. Mandatory read order for every new agent/session

1. `AGENTS.md`
2. **`ACTIVE_ROADMAP.md`**
3. `docs/agent/CURRENT_FRONTIER.md`
4. tail of `docs/agent/HANDOFF_LOG.md`
5. `READ_FIRST_CRYPTO_SIGNAL.md`
6. `CURRENT_STATUS.md`
7. newest `PROJECT_CHRONICLE.md` entry
8. `ENVIRONMENT_REGISTRY.md`
9. `docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md`
10. the mechanically active phase authority (currently RDP11 roadmap)
11. relevant accepted contracts/acceptance records for the exact slice.

Then verify current Git/GitHub, Workbench and relevant runtime evidence. Conversation memory is not authority.

## 7. Duplicate-work rule

Before any implementation:
- search current main, recent merged PRs, open PRs/branches and relevant workflows;
- inspect actual code/contracts, not only filenames;
- classify the requested capability as `REUSE`, `EXTEND`, `BUILD` or `EXPLICITLY_UNAVAILABLE`;
- record that classification in `docs/agent/CURRENT_FRONTIER.md` before coding;
- never reopen a PASS phase merely because a newer UI is desired.

## 8. Active-soak protection

Until FP0/RDP11 closes:
- do not mutate the frozen soak Product/Development target;
- do not change the observer contract while pretending the same epoch remains valid;
- do not backfill or rewrite frozen/historical evidence;
- FP1+ may be implemented/tested in isolated branches/worktrees with fixtures, temporary DBs and read-only canonical inputs;
- do not deploy or merge a change that alters soaked runtime behavior unless the epoch consequence is explicitly handled;
- final integrated Product acceptance/cutover waits for FP0 PASS.

## 9. Project isolation

Do not touch:
- Durdurulmaz;
- Quantum Capital;
- their repos, runtimes, data, credentials or roadmaps.

**REAL_CAPITAL=0.**
