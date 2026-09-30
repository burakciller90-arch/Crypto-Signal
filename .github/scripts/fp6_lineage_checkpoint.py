from pathlib import Path

MARKER = "## FP6 EXECUTION / FUNDING -> R22 -> TRADE PASSPORT LINEAGE - TASK START - 2026-10-01"
ENTRY = """## FP6 EXECUTION / FUNDING -> R22 -> TRADE PASSPORT LINEAGE - TASK START - 2026-10-01

status: ACTIVE / DURABLE START CHECKPOINT
taskStartMain: 523b1727cf369737abac4884e06c81b3402a1322
activeBranch: fp6/execution-funding-r22-passport-lineage-20261001
sessionLocalWorktree: NONE (GitHub connector + UID504 runner)
canonicalWorkbench: /Volumes/Crypto-504/Crypto-Signal-Workbench/repo
activeRoadmap: docs/CRYPTO_SIGNAL_FINAL_PRODUCT_MASTER_ROADMAP_V1.md
mechanicalGate: FP0 / RDP11 ACTIVE / NOT PASS; soaked Product/Development target remains frozen
finalProductSlice: FP6 immutable execution/funding lineage completion
classification: REUSE FP4 ExecutionReceiptV2 + funding_cost_v2 + accepted R22 + FP6-B; EXTEND only the missing immutable bridge/read model
duplicateCheck: FP6-B PR #1737 is merged as main 523b1727; no open PR for this exact execution/funding lineage bridge
realCapital: 0
historicalFrozenMutation: NO
DurdurulmazTouched: NO
QuantumCapitalTouched: NO

Bounded goal:
- bind ExecutionReceiptV2 and, where applicable, PaperFundingCostProjection to an append-only immutable R22 record;
- preserve queue/latency/partial-fill/fill-not-proven semantics from accepted FP4 execution truth;
- expose those immutable values through Trade Passport without deriving them from mutable/current data;
- preserve accepted R21/R22 accounting and FP6-B frozen market-proof lineage;
- do not deploy or mutate the active RDP11 soaked runtime.

Current blocker:
- R22 currently stores only legacy intent/fill/accounting bundle/outcome evidence and has no ExecutionReceiptV2 or funding projection attachment;
- TradePassportView therefore has no funding/latency/queue/partial-fill immutable execution projection.

Exact nextAction:
- add one append-only R22 execution-lineage attachment contract/table, then project it read-only into Trade Passport and prove exact-SHA acceptance.
"""

frontier = Path("docs/agent/CURRENT_FRONTIER.md")
handoff = Path("docs/agent/HANDOFF_LOG.md")
frontier_text = frontier.read_text()
if MARKER not in frontier_text:
    lines = frontier_text.splitlines()
    frontier.write_text(lines[0] + "\n\n" + ENTRY + "\n\n" + "\n".join(lines[1:]) + "\n")
handoff_text = handoff.read_text()
if MARKER not in handoff_text:
    handoff.write_text(handoff_text.rstrip() + "\n\n" + ENTRY + "\n")
