# FP6-A Acceptance Continuation Checkpoint — 2026-09-30

status: FP6A_REPAIR_APPLIED_FRESH_ACCEPTANCE_REQUIRED
canonicalMain: c1263bc073f78caea12b088e95447c3cae91bf50
activeBranch: fp6a/trade-passport-lifecycle-audit
branchHeadAtTaskStart: 2bec4e0990e2ff07f42c43b06acf51b53c27a781
acceptedReadyHead: a1d44d8973979c382a7fd76475c7c9554341ed39
pr: 1705
sessionLocalVolumesWorktree: NONE
canonicalWorkbench: /Volumes/Crypto-504/Crypto-Signal-Workbench/repo
postFP5CloseoutWorkbenchRun: 36645069501 / SUCCESS / exact c1263bc073f78caea12b088e95447c3cae91bf50
realCapital: 0
historicalBackfill: NO
ProductDevelopmentDeploy: NO
RDP11RuntimeMutation: NO
DurdurulmazTouched: NO
QuantumCapitalTouched: NO

Accepted owner contract:
- REUSE FP1-E single-bundle Trade Passport projection;
- REUSE immutable R22/R21/S11/Decision Proof truth;
- reconstruct one trade episode read-only from exact R22 quantity transitions and bundle chronology;
- OPEN/SCALE_IN/REDUCE/CLOSE exact only when supported by canonical action/reason truth;
- STOP_UPDATE remains UNAVAILABLE_EXPLICIT because no exact persisted lifecycle-root binding exists;
- CORRECTION/SUPERSEDED remains UNAVAILABLE_EXPLICIT because no accepted canonical lifecycle owner exists;
- no new canonical ledger, schema, writer, historical backfill or current-data substitution.

Implementation:
- read-only `FinalProductReadModel.trade_lifecycle(bundle_identity, include_audit=False)`;
- deterministic episode grouping over verified R22 trade history;
- exact OPEN / SCALE_IN / PARTIAL_TAKE_PROFIT / REDUCE / CLOSE classification from canonical action, reason codes and before/after position quantity;
- nested existing Trade Passport view for every lifecycle event;
- immutable audit lineage for bundle/intent/fill/forecast/proof identities;
- explicit unavailable capability labels for STOP_UPDATE and CORRECTION/SUPERSEDED.

Acceptance work:
- initial focused test commit `353814fc78fde06526288a1ac3e8862590242447`;
- dedicated workflow commit `c8067093061384498bd7af465aa5ebd0f570f873`;
- focused coverage includes missing DB non-creation, single OPEN episode, real OPEN→PARTIAL_TAKE_PROFIT→CLOSE reconstruction, deterministic replay from different bundle keys, SCALE_IN/REDUCE classification, explicit unavailable capabilities, source-byte immutability, and winning/losing closed-trade inspectability;
- dedicated workflow also runs legacy `test_final_product_read_model.py`, `test_transaction_tape_atomic.py`, `test_autopilot_forward_actions.py`, Ruff, strict mypy, whole-repo regression and frozen Product/Development non-mutation.

Acceptance attempt 1:
- tested head `a1d44d8973979c382a7fd76475c7c9554341ed39`;
- dedicated run/job `36674626349/109756808558`;
- exact source and frozen RDP11 boundary: PASS;
- Product/Development non-mutation: PASS;
- focused pytest: 60 PASS / 2 FAIL;
- whole-repo step skipped because focused step stopped;
- no production-source behavior failure observed.

Exact blockers from attempt 1:
1. new single-OPEN test incorrectly required `${epoch2_path}-wal` absent after read; accepted writer fixture already leaves WAL before projection while canonical main DB bytes remained unchanged;
2. new lifecycle label test expected `Pozisyon kapandı`; accepted implementation/customer label is `Pozisyon kapanışı`.

Test-only repair:
- repair commit `f59dcc142071ce01c4735033fa3bee739913a0e9`;
- no source implementation file changed in the repair;
- SQLite sidecar acceptance now snapshots pre-existing `-wal` / `-shm` state and requires byte-identical state after lifecycle projection, catching both creation and mutation instead of assuming absence;
- CLOSE label expectation aligned to exact accepted label `Pozisyon kapanışı`;
- same sidecar byte-immutability assertion added to open, multi-event and winning/losing focused paths.

Acceptance rule:
- all runs on `a1d44d897397...` are stale for merge after the repair;
- this checkpoint commit is the final intended branch mutation before fresh acceptance, unless a new mechanical blocker is proven;
- require dedicated FP6-A + WC6 + RDP11 Pre-Soak + F10 SUCCESS on one exact final head.

Exact nextAction:
1. read PR #1705 new exact head after this checkpoint commit;
2. inspect fresh dedicated FP6-A focused/full/nonmutation results;
3. inspect fresh WC6/RDP11/F10 on the same head;
4. if all mechanical outputs PASS, recheck main drift/duplicate/PR head and merge with expected head SHA;
5. after merge, prove exact-main Workbench + regression and audit master FP6 PASS clauses; do not claim whole FP6 PASS if frozen visual proof/event linkage remains mechanically unresolved.
