from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import Exchange
from crypto_signal.evaluation.untouched_forward_execution_journal import (
    WC2PaperExecutionDecisionStatus,
    WC2PaperExecutionJournal,
    build_wc2_paper_execution_decision,
    compute_wc2_cost_evidence_identity,
    compute_wc2_paper_execution_event_identity,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import PaperAction, PaperSymbol

START = 1_000_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _base() -> dict[str, object]:
    freezes = (_sha("binance-freeze"), _sha("bybit-freeze"))
    event = compute_wc2_paper_execution_event_identity(
        execution_protocol_identity=_sha("protocol"),
        symbol=PaperSymbol.BTCUSDT,
        source_cutoff_open_time_ms=START + 100,
        source_exchanges=(Exchange.BINANCE.value, Exchange.BYBIT.value),
        source_freeze_identities=freezes,
    )
    return {
        "event_identity": event,
        "execution_protocol_identity": _sha("protocol"),
        "execution_start_ms": START,
        "source_exchanges": (Exchange.BINANCE.value, Exchange.BYBIT.value),
        "source_freeze_identities": freezes,
        "source_forecast_identities": (
            _sha("binance-forecast"),
            _sha("bybit-forecast"),
        ),
        "source_cohort_forecast_identities": (
            _sha("binance-cohort"),
            _sha("bybit-cohort"),
        ),
        "source_signal_as_of_ms": (START + 100, START + 100),
        "source_frozen_at_ms": (START + 110, START + 111),
        "source_forecast_issued_at_ms": (START + 120, START + 121),
        "source_cutoff_open_time_ms": START + 100,
        "symbol": PaperSymbol.BTCUSDT,
        "epoch2_core_snapshot_identity": _sha("core-before"),
        "decided_at_ms": START + 200,
        "reason_code": "exact_dual_provider_hold",
        "autonomy_policy_version": "paper_autonomy_policy.v2",
    }


def _executed_values() -> dict[str, object]:
    values = _base()
    fill = _sha("fill")
    venue = "binance_spot_rules|snapshot:abc|paper-only"
    costs = {
        "fee_usdt": Decimal("0.10"),
        "spread_usdt": Decimal("0.05"),
        "slippage_usdt": Decimal("0.05"),
    }
    values.update(
        {
            "status": WC2PaperExecutionDecisionStatus.EXECUTED,
            "action": PaperAction.BUY,
            "reason_code": "paper_autonomy_trade_executed",
            "execution_input_identity": _sha("execution-input"),
            "sizing_identity": _sha("sizing"),
            "venue_rule_snapshot_identity": _sha("venue-rules"),
            "pretrade_identity": _sha("pretrade"),
            "plan_identity": _sha("plan"),
            "fill_identity": fill,
            "cost_evidence_identity": compute_wc2_cost_evidence_identity(
                fill_identity=fill,
                execution_policy_version="paper_execution_policy.v1",
                venue_reference=venue,
                **costs,
            ),
            "quantity": Decimal("1"),
            "reference_price": Decimal("100"),
            "simulated_fill_price": Decimal("100.10"),
            **costs,
            "venue_reference": venue,
        }
    )
    return values


def test_hold_cash_is_terminal_without_trade_or_cost_evidence() -> None:
    record = build_wc2_paper_execution_decision(
        **_base(),
        status=WC2PaperExecutionDecisionStatus.HOLD_CASH,
        action=PaperAction.HOLD_CASH,
    )

    assert record.trade_decision is False
    assert record.simulated_execution is False
    assert record.explicit_cost_evidence is False
    assert record.real_capital == 0
    assert record.historical_backfill_performed is False


def test_execution_requires_fill_and_explicit_cost_evidence() -> None:
    record = build_wc2_paper_execution_decision(**_executed_values())

    assert record.trade_decision is True
    assert record.simulated_execution is True
    assert record.explicit_cost_evidence is True
    assert record.fill_identity == _sha("fill")
    assert record.quantity == Decimal("1")
    assert record.reference_price == Decimal("100")
    assert record.simulated_fill_price == Decimal("100.10")
    assert record.fee_usdt == Decimal("0.10")
    assert record.spread_usdt == Decimal("0.05")
    assert record.slippage_usdt == Decimal("0.05")

    broken = _executed_values()
    broken["cost_evidence_identity"] = _sha("wrong-cost")
    with pytest.raises(ValueError, match="cost evidence identity mismatch"):
        build_wc2_paper_execution_decision(**broken)


def test_boundary_refuses_historical_source_or_backfill() -> None:
    values = _base()
    values["source_forecast_issued_at_ms"] = (START - 1, START + 121)
    with pytest.raises(ValueError, match="forecast predates execution boundary"):
        build_wc2_paper_execution_decision(
            **values,
            status=WC2PaperExecutionDecisionStatus.HOLD_CASH,
            action=PaperAction.HOLD_CASH,
        )

    with pytest.raises(ValueError, match="cannot backfill"):
        build_wc2_paper_execution_decision(
            **_base(),
            status=WC2PaperExecutionDecisionStatus.HOLD_CASH,
            action=PaperAction.HOLD_CASH,
            historical_backfill_performed=True,
        )


def test_rejection_retains_upstream_evidence_without_fabricating_fill() -> None:
    values = _base()
    values.update(
        {
            "status": WC2PaperExecutionDecisionStatus.SIZING_REJECTED,
            "action": PaperAction.BUY,
            "reason_code": "reference_outside_entry_zone",
            "execution_input_identity": _sha("execution-input"),
            "sizing_identity": _sha("sizing"),
            "venue_rule_snapshot_identity": _sha("venue-rules"),
        }
    )
    record = build_wc2_paper_execution_decision(**values)

    assert record.trade_decision is False
    assert record.fill_identity is None
    assert record.cost_evidence_identity is None


def test_journal_is_append_only_idempotent_and_counts_economic_truth(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2.wc2-paper-execution.sqlite3"
    journal = WC2PaperExecutionJournal(path)
    hold = build_wc2_paper_execution_decision(
        **_base(),
        status=WC2PaperExecutionDecisionStatus.HOLD_CASH,
        action=PaperAction.HOLD_CASH,
    )
    assert journal.append(hold) is True
    assert journal.append(hold) is False

    executed_values = _executed_values()
    executed_values["event_identity"] = compute_wc2_paper_execution_event_identity(
        execution_protocol_identity=_sha("protocol"),
        symbol=PaperSymbol.ETHUSDT,
        source_cutoff_open_time_ms=START + 200,
        source_exchanges=(Exchange.BINANCE.value, Exchange.BYBIT.value),
        source_freeze_identities=(_sha("eth-binance"), _sha("eth-bybit")),
    )
    executed_values["source_freeze_identities"] = (
        _sha("eth-binance"),
        _sha("eth-bybit"),
    )
    executed_values["source_forecast_identities"] = (
        _sha("eth-forecast-a"),
        _sha("eth-forecast-b"),
    )
    executed_values["source_cohort_forecast_identities"] = (
        _sha("eth-cohort-a"),
        _sha("eth-cohort-b"),
    )
    executed_values["source_cutoff_open_time_ms"] = START + 200
    executed_values["symbol"] = PaperSymbol.ETHUSDT
    executed = build_wc2_paper_execution_decision(**executed_values)
    assert journal.append(executed) is True

    records = journal.read_records()
    assert records == (hold, executed)

    status = journal.verify_read_only()
    assert status.decision_n == 2
    assert status.hold_cash_n == 1
    assert status.rejected_n == 0
    assert status.trade_decision_n == 1
    assert status.simulated_execution_n == 1
    assert status.explicit_cost_evidence_trade_n == 1
    assert status.real_capital == 0

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "UPDATE wc2_paper_execution_events SET status='HOLD_CASH'"
            )
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM wc2_paper_execution_events")
