# Crypto Signal — Project Completion Execution Roadmap

Status: authoritative execution roadmap for completing the Full Version while preserving existing accepted evidence.

Date established: 2026-09-21

Hard invariants:
- REAL_CAPITAL=0.
- No real exchange order authority, real credentials, autonomous real-money trading, or implicit PAPER/STABLE write activation.
- Historical Stage 10 accepted evidence remains immutable and is not rewritten by later research/control work.
- Completed/stale/superseded slices are reconciled and never replayed.
- Research code remains isolated under `research/alpha_factory` until an explicitly accepted integration policy exists.

## M0 — Stabilized SSD/runtime baseline

Current baseline after SSD recovery:
- UID504 canonical development repo lives at `/Volumes/Crypto-504/Crypto-Signal/Development`.
- Product runtime remains the accepted Stage 10 product checkout.
- SSD supervisor owns dashboard/live/alert/paper runtime continuity.
- Dashboard binds signal ledger, alert outbox, paper ledger and candle cache from SSD runtime paths.
- Continuity paths are SSD-safe and fail closed when chat binding is absent.
- Full local gate passed after the repair.

This milestone is operationally complete. Reopen only on contradictory mechanical evidence.

## M1 — Stage 8.5 Alpha Factory scientific closure

### R1 — Bounded ML transaction-cost/slippage stress — ACCEPTED
Accepted main: `97af8105a8c5408bfbe2b19bd64d97bbbf384e17`.
Canonical evidence chain: branch research PASS → merged-main research PASS → Stage10 regression PASS → UID504 sync/fulltest PASS.

Requirements:
- operate only on accepted deterministic ML OOS/walk-forward evidence;
- use a small immutable deterministic multiplier grid;
- preserve gross R, original cost, original net R and derive stressed cost/net R exactly;
- immutable config/scenario/fold/run identities;
- no model refit;
- no prediction changes;
- no automatic scenario/model winner selection;
- no calibrated-probability claim;
- untouched-forward remains closed;
- no production/paper/confluence/signal import or deploy authority.

Acceptance:
- research tests/gate PASS;
- production Stage 10 regression PASS;
- merged-main research + production gates PASS;
- UID504 sync + fulltest PASS;
- authoritative docs/frontier closure.

### R2 — ML robustness / ablation evidence — ACCEPTED
Accepted main: `a385d7789af11aa7b124e5c52eb4731c868df615`.
- feature ablation and sensitivity checks;
- fold/regime/asset/timeframe stability evidence where supported;
- redundancy/correlation checks;
- failure cases retained explicitly;
- deterministic identities and reproducibility;
- no automatic winner selection or promotion.

### R3 — Carefully bounded broader ML research — CURRENT FRONTIER
Canonical task: `stage8.5-bounded-ml-model-family-expansion-v1`.
Only after R1/R2 close:
- predeclared finite hypothesis/model family;
- multiple-testing/backtest-overfitting controls;
- deterministic train/validation/OOS semantics;
- no uncontrolled hyperparameter search;
- no production authority.

### R4 — RL architecture decision / optional bounded RL research
RL remains closed until separately justified and accepted.
If opened, it must be research-only, deterministic/bounded where possible, with no order/broker authority.

### R5 — Untouched-forward paper evidence
- open untouched-forward only after prior scientific gates close;
- no retrospective refit on forward observations;
- preserve both favorable and unfavorable outcomes;
- immutable evidence identities and chronology;
- descriptive evaluation only.

### R6 — Robustness / promotion dossier closure
Each challenger must close the full promotion evidence boundary:
1. data-contract/leakage audit;
2. deterministic/reproducible generation;
3. transaction-cost/slippage stress;
4. in-sample sanity;
5. out-of-sample evaluation;
6. walk-forward evaluation;
7. untouched-forward paper evaluation;
8. robustness/ablation;
9. explicit supervisor acceptance.

Machine evidence may reach `READY_FOR_SUPERVISOR_REVIEW`.
Recorded supervisor acceptance may reach `SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION`.
There is no self-promotion, champion-write or deploy API.

## M2 — Stage 8.75 Learning Memory + product visibility

### R7 — Versioned Learning Memory
Persist success and failure equally by:
- method;
- asset;
- timeframe;
- regime;
- version;
- uncertainty;
- redundancy/overlap;
- before-vs-after policy/model changes.

Learning Memory is evidence, not authority.
Any production weighting effect requires a separately tested and accepted policy.

### R8 — Intelligence Center / Research Lab dashboard
Expose existing accepted Stage 8 and Stage 8.5 evidence read-only:
- regime;
- trend/momentum;
- mean reversion;
- breakout/volatility;
- derivatives;
- order flow/microstructure;
- on-chain;
- sentiment/attention;
- cross-market;
- Alpha Factory experiments;
- walk-forward;
- cost stress;
- robustness;
- Learning Memory.

Each surface should answer:
- what does it say?
- why does it matter?
- freshness/source/evidence?
- what is missing or contradictory?
- is production contribution zero or active?

Research-only surfaces must never imply production authority.

### R9 — Meta-intelligence / weighting policy
- prevent double-counting correlated evidence;
- contradiction and abstention are first-class;
- regime-aware weighting only through accepted versioned policy;
- no probability label without accepted calibration evidence;
- shadow/read-only validation before any production contribution change.

### R10 — Gift Edition final polish
Keep the first screen simple and beginner-friendly.
Integrate the new intelligence/research visibility through progressive disclosure rather than adding dashboard clutter.

## M3 — Operational hardening and Full Version final acceptance

### R11 — SSD/runtime recovery hardening
Test:
- Mac reboot;
- logout/login;
- SSD reconnect/remount;
- supervisor crash/restart;
- dashboard crash/restart;
- runner watchdog recovery;
- stale PID cleanup;
- DB integrity/WAL recovery;
- disk-space/log-rotation behavior;
- backup/restore;
- fail-closed behavior when SSD/runtime sources are missing.

No fallback to removed internal Macintosh project paths is allowed.

### R12 — Continuity hardening
- explicit current-chat binding;
- pause/resume semantics;
- empty/stale queue handling;
- duplicate/stale wake NOOP behavior;
- no cross-project relay contamination.

### R13 — Full Version Integrated Acceptance v2
Before calling the project complete:
- full repository gate PASS;
- stable runtime deployment;
- restart/recovery PASS;
- auto-refresh endurance PASS;
- stale-data semantics PASS;
- paper-ledger reconstruction PASS;
- fee/spread/slippage determinism PASS;
- leakage/PIT checks PASS;
- beginner usability PASS;
- explanation/evidence consistency PASS;
- benchmark correctness PASS;
- Research Lab isolation PASS;
- SSD path/freshness PASS;
- REAL_CAPITAL=0 verified;
- no exchange order endpoint/credential authority exposed.

### R14 — Final release/documentation package
Freeze:
- final accepted commit/tag;
- READ_FIRST;
- CURRENT_STATUS;
- PROJECT_CHRONICLE;
- completeness audit;
- architecture/roadmap;
- operator runbook;
- dashboard open/recovery guide;
- SSD recovery/backup guide;
- known intentional authority gates.

## Definition of Done

Crypto Signal Full Version is complete when M1, M2 and M3 are accepted with mechanical evidence and authoritative documentation, while REAL_CAPITAL remains 0 and all real-money/order authority stays closed.

Immediate next execution target:
`stage8.5-bounded-ml-model-family-expansion-v1`.
