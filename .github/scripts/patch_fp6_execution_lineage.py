from pathlib import Path

frontier = Path("docs/agent/CURRENT_FRONTIER.md")
handoff = Path("docs/agent/HANDOFF_LOG.md")
marker = "## FP6 EXECUTION LINEAGE — IMPLEMENTATION -> ACCEPTANCE CHECKPOINT — 2026-10-01"
checkpoint = """## FP6 EXECUTION LINEAGE — IMPLEMENTATION -> ACCEPTANCE CHECKPOINT — 2026-10-01

status: FP6_EXECUTION_LINEAGE_ACCEPTANCE_START
verifiedMain: 523b1727cf369737abac4884e06c81b3402a1322
activeBranch: fp6/execution-funding-r22-passport-lineage-20261001
implementationHeadBeforeCheckpoint: b212cdc8d9ace08f525b46384e8cc62207604877
sessionLocalWorktree: NONE (GitHub connector + UID504 runner)
mechanicalGate: FP0 / RDP11 R2 ACTIVE / NOT PASS; frozen Product/Development target unchanged
finalProductSlice: FP6 immutable execution/funding lineage completion
classification: BRIDGE — REUSE accepted FP4 ExecutionReceiptV2/funding truth + R22 + FP6-B; persist/project only missing immutable lineage
realCapital: 0
historicalBackfill: NO
RDP11RuntimeMutation: NO
ProductDevelopmentDeploy: NO
DurdurulmazTouched: NO
QuantumCapitalTouched: NO

Implementation evidence now present:
- `src/crypto_signal/paper/r22_execution_lineage.py` adds append-only execution/funding companion records beside accepted R22 without rewriting historical R22 rows;
- `FinalProductReadModel.trade_passport()` projects only persisted execution-lineage truth and returns `None` for legacy bundles without lineage instead of recomputing/current-data substitution;
- passive-limit latency/queue fields are read only from immutable passive-limit outcomes; depth outcomes do not invent them;
- funding projections remain exact separate settlement evidence and are not folded into immediate execution cost;
- identical append is idempotent; conflicting immutable rebinding is rejected; `REAL_CAPITAL=0` is verified at write/read boundaries.

Acceptance scope locked by user / roadmap:
1. canonical R22 fixture focused execution-lineage tests;
2. partial fill;
3. passive-limit latency + visible queue ahead + queue consumed;
4. exact funding projection identities;
5. mismatch/conflicting rewrite rejection;
6. historical point-in-time immutability / later V2 truth cannot alter older Passport;
7. clean final candidate must not contain temporary `.github/scripts/patch_fp6_execution_lineage.py` or `.github/workflows/fp6-execution-lineage-patch.yml`;
8. SAME final SHA must pass focused lineage + FP6-B + WC6 + whole-repository + RDP11 Pre-Soak + F10 + Product/Development/frozen-runtime non-mutation with `REAL_CAPITAL=0`.

Current blocker:
- focused canonical fixture tests have not yet been added/run;
- temporary branch-only patch helper artifacts remain and must be removed before final candidate acceptance.

Exact nextAction:
Add canonical R22 execution-lineage focused tests using existing production constructors/fixtures, then remove the temporary helper artifacts before defining the final candidate SHA.

"""
frontier_text = frontier.read_text()
if marker not in frontier_text:
    frontier.write_text("# Crypto Signal Current Frontier\n\n" + checkpoint + frontier_text.removeprefix("# Crypto Signal Current Frontier\n\n"))

handoff_marker = "FP6 execution lineage implementation -> acceptance checkpoint"
handoff_entry = """

## 2026-10-01 — FP6 execution lineage implementation -> acceptance checkpoint

- exact main: `523b1727cf369737abac4884e06c81b3402a1322`
- branch: `fp6/execution-funding-r22-passport-lineage-20261001`
- implementation head entering acceptance: `b212cdc8d9ace08f525b46384e8cc62207604877`
- worktree: none in connector session; UID504 runner is execution plane
- slice: FP6 `ExecutionReceiptV2 -> funding/queue/latency/partial-fill -> R22 immutable tape -> Trade Passport`
- classification: BRIDGE only; accepted FP4/R22/FP6-B owners reused
- implementation: append-only R22 execution/funding companion lineage + read-only Trade Passport projection present
- acceptance pending: canonical fixture focused tests, helper cleanup, then same-final-SHA FP6-B + WC6 + whole-repo + RDP11 Pre-Soak + F10/non-mutation
- RDP11 global R2 soak remains independently ACTIVE / NOT PASS; this branch must not re-anchor or mutate the frozen runtime
- `REAL_CAPITAL=0`; `HISTORICAL_BACKFILL=NO`
- Product/Development deploy: NO
- Durdurulmaz touched: NO
- Quantum Capital touched: NO
- exact nextAction: add canonical R22 execution-lineage focused tests, then remove temporary helper artifacts before defining the final candidate SHA.
"""
handoff_text = handoff.read_text()
if handoff_marker not in handoff_text:
    handoff.write_text(handoff_text.rstrip() + handoff_entry + "\n")
