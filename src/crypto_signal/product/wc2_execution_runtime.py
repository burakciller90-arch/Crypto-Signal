from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_execution_journal import (
    WC2PaperExecutionJournal,
)
from crypto_signal.evaluation.untouched_forward_execution_runtime import (
    WC2PaperExecutionRuntimeStore,
)

REAL_CAPITAL = 0


def read_wc2_execution_runtime_truth(
    *,
    runtime_activation_path: Path,
    execution_journal_path: Path,
    recent_limit: int = 50,
) -> dict[str, object]:
    """Project WC2 execution evidence strictly read-only for Product surfaces."""
    if recent_limit <= 0 or recent_limit > 500:
        raise ValueError("recent_limit must be inside [1,500]")

    activation = WC2PaperExecutionRuntimeStore(runtime_activation_path).latest()
    if activation is None:
        return {
            "status": "unavailable",
            "reason": "wc2_execution_runtime_not_activated",
            "runtime_activation_present": False,
            "execution_journal_present": execution_journal_path.is_file(),
            "online_status": "NOT_ASSERTED",
            "process_status": "NOT_MEASURED",
            "economic_evidence_status": "NOT_MEASURED",
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }

    if not execution_journal_path.is_file():
        return {
            "status": "ready",
            "activation": asdict(activation),
            "journal": {
                "status": "empty",
                "decision_n": 0,
                "hold_cash_n": 0,
                "rejected_n": 0,
                "trade_decision_n": 0,
                "simulated_execution_n": 0,
                "explicit_cost_evidence_trade_n": 0,
                "recent_records": [],
            },
            "runtime_activation_present": True,
            "execution_journal_present": False,
            "online_status": "NOT_ASSERTED",
            "process_status": "NOT_MEASURED",
            "economic_evidence_status": "NO_EXECUTED_TRADES_YET",
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }

    journal = WC2PaperExecutionJournal(execution_journal_path)
    snapshot = journal.verify_read_only()
    records = journal.read_records()
    recent = tuple(reversed(records[-recent_limit:]))
    if snapshot.trade_decision_n == 0:
        economic_status = "NO_EXECUTED_TRADES_YET"
    elif (
        snapshot.explicit_cost_evidence_trade_n
        == snapshot.trade_decision_n
        == snapshot.simulated_execution_n
    ):
        economic_status = "EXPLICIT_COST_EVIDENCE_COMPLETE_FOR_EXECUTED_TRADES"
    else:
        raise ValueError("WC2 execution journal economic evidence does not reconcile")

    return {
        "status": "ready",
        "activation": asdict(activation),
        "journal": {
            **asdict(snapshot),
            "status": "ready" if snapshot.decision_n else "empty",
            "recent_records": [asdict(item) for item in recent],
        },
        "runtime_activation_present": True,
        "execution_journal_present": True,
        "online_status": "NOT_ASSERTED",
        "process_status": "NOT_MEASURED",
        "economic_evidence_status": economic_status,
        "read_only": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
