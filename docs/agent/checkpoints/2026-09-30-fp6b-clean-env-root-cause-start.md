# FP6-B clean-environment root-cause checkpoint — 2026-09-30

status: ROOT_CAUSE_EVIDENCE_CAPTURED / FIX_NEXT

taskStartMain: 38d757071a50566379715f3074b4b74b668a6aa6
activeBranch: fp6b/trade-passport-frozen-proof
candidateHeadAtStart: c8887be0625e096e5a0caba8afbc196888543094
evidenceCandidate: 826b38287a120116ff6ab38bc33b00cafee90438
sessionLocalWorktree: NONE (GitHub connector execution)
programFrontier: FP0 / RDP11 ACTIVE / NOT PASS; preserve soak target and observer contract
finalProductFrontier: FP6-B Trade Passport frozen-proof -> immutable execution/funding lineage
classification: EXTEND existing FP6-B implementation; do not rebuild accepted FP6-A / R22 / FP4 foundations

duplicateCheck:
- existing open PR #1737 is the active FP6-B implementation; continue it rather than creating duplicate work
- c8887be changed acceptance isolation only; product implementation remained from earlier FP6-B commits

## Exact clean-environment evidence

FP6-B diagnostic hardening commit:
- 826b38287a120116ff6ab38bc33b00cafee90438
- acceptance coverage was not reduced; focused pytest output is only tee'd and uploaded for diagnosis

FP6-B run:
- run 36740832734
- job 109974481985
- exact source/frozen target step: PASS
- isolated acceptance environment: PASS
- focused FP6-B pytest: FAIL
- diagnostic artifact: 11109848374 / fp6b-focused-diagnostics-36740832734
- frozen Product/Development non-mutation proof: PASS

Focused pytest exact result:
- 8 collected
- 6 passed, 2 failed
- failed: test_fp6b_stream_rewrite_is_selected_point_in_time_without_rewriting_history
- failed: test_fp6b_passport_fill_time_binds_each_lifecycle_event_to_then_current_story
- first failure is tests/test_fp6b_trade_passport_frozen_proof.py:329
- second failure is tests/test_fp6b_trade_passport_frozen_proof.py:403
- both assertion lines are signal_path.read_bytes() == before[signal_path]
- the diff shows physical SQLite bytes changed after read-only Trade Passport proof resolution
- stream_path, decision_path and epoch2 are not the reported failing byte invariants

Cross-gate evidence on the same 826b3828 candidate:
- WC6 run 36740832812 / job 109974480685: SUCCESS; focused + paper subsystem + whole repo + non-mutation PASS
- F10 run 36740832807: SUCCESS
- RDP11 run 36740832753 / job 109974482458: FAIL at Exact full-suite integration repair acceptance; exact-source boundary PASS and canonical Development non-mutation PASS
- RDP11 workflow still executes through shared Development .venv and requires separate acceptance-environment hardening; this does not explain the isolated FP6-B focused failure

## Proven implementation boundary

- IntelligenceStreamVisualProofReadModel resolves the signal freeze through ImmutableSignalLedger.read_freeze_by_signal().
- ImmutableSignalLedger.read_freeze_by_signal() opens the frozen signal SQLite database using mode=ro and PRAGMA query_only=ON.
- IntelligenceStreamExactEvidenceReadModel also resolves signal objects through a mode=ro + PRAGMA query_only connection.
- neither frozen signal read path marks the SQLite URI immutable=1.
- the accepted product rule requires frozen/history evidence to remain physically non-mutating during Trade Passport reads.

## Root-cause hypothesis to verify mechanically

The clean Python/SQLite environment exposes WAL/read-open side effects on the frozen signal SQLite file across repeated point-in-time proof reads. mode=ro + query_only prevents SQL writes but does not establish SQLite's immutable-file contract. Mark the frozen signal DB URI immutable=1 on the true read-only paths, preserving fail-closed behavior and leaving all write/initialize paths unchanged.

This remains a hypothesis until the unchanged FP6-B byte-invariance tests pass in the clean environment.

## Bounded fix

1. add immutable=1 only to frozen signal-ledger read-only SQLite URIs used by visual/exact proof resolution;
2. do not change tests or weaken byte-invariance assertions;
3. do not change signal-ledger write/initialize semantics;
4. preserve REAL_CAPITAL=0 and frozen/history immutability;
5. separately harden RDP11 Pre-Soak acceptance to an isolated runner-temp environment without changing its coverage;
6. run FP6-B + WC6 + RDP11 + F10 on the eventual exact final candidate SHA;
7. after FP6-B PASS, verify ExecutionReceiptV2 -> R22 immutable tape -> Trade Passport execution/funding lineage before declaring FP6 PASS.

currentBlocker:
- immutable SQLite URI repair has not yet been applied/proven

nextAction:
- patch the two frozen signal read-only URI constructors to mode=ro&immutable=1, then run the unchanged FP6-B focused test in isolated acceptance

safety:
- REAL_CAPITAL=0
- historical/frozen evidence mutation: NO intended; current test proves an unwanted read-side physical mutation that this repair must eliminate
- historical backfill: NO
- Product/Development deploy: NO
- Durdurulmaz touched: NO
- Quantum Capital touched: NO
