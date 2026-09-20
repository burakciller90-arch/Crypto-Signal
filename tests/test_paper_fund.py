"""Focused tests for the Stage 6C immutable 100 USDT paper fund foundation."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal import paper
from crypto_signal.paper import (
    BENCHMARK_IDS,
    INITIAL_CASH_USDT,
    PARTIAL_FILLS_SUPPORTED,
    PERMITTED_ACTIONS,
    PERMITTED_SYMBOLS,
    REAL_CAPITAL,
    BenchmarkId,
    ExecutionCostAssumptions,
    PaperAction,
    PaperFundLedger,
    PaperLedgerConflictError,
    PaperLedgerWriteDisposition,
    PaperPosition,
    PaperRecordKind,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
    build_nav_snapshot,
    build_position_cash_mutation,
    build_simulated_fill,
    initial_account_state,
)

FORBIDDEN_SURFACE_NAMES = {
    "place_order",
    "submit_order",
    "cancel_order",
    "exchange_order",
    "live_order",
    "broker",
    "api_key",
    "api_secret",
    "credentials",
    "leverage",
    "margin",
    "short",
    "borrow",
    "martingale",
    "derivative",
    "futures",
    "update",
    "delete",
}


def test_real_capital_remains_zero() -> None:
    assert REAL_CAPITAL == 0
    assert paper.REAL_CAPITAL == 0
    cash, positions = initial_account_state()
    assert cash == Decimal("100.00")
    assert cash == INITIAL_CASH_USDT
    assert positions == ()


def test_exact_100_usdt_initialization() -> None:
    fund = build_fund_creation(created_at_ms=1_700_000_000_000)
    assert fund.initial_cash_usdt == Decimal("100.00")
    assert fund.real_capital == 0
    assert fund.positions == ()
    assert fund.schema_version.startswith("paper_fund.schema.")
    assert fund.execution_policy_version.startswith("paper_execution_policy.")
    assert fund.risk_policy_version.startswith("paper_risk_policy.")


def test_permitted_symbols_and_actions() -> None:
    assert PERMITTED_SYMBOLS == frozenset(
        {
            PaperSymbol.BTCUSDT,
            PaperSymbol.ETHUSDT,
            PaperSymbol.SOLUSDT,
        }
    )
    assert PERMITTED_ACTIONS == frozenset(
        {
            PaperAction.HOLD_CASH,
            PaperAction.BUY,
            PaperAction.REDUCE,
            PaperAction.EXIT,
        }
    )
    fund = build_fund_creation(created_at_ms=1)
    hold = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.HOLD_CASH,
        reason="cash is a valid professional allocation",
        invalidation_context="none — remaining in cash",
    )
    assert hold.action is PaperAction.HOLD_CASH
    assert hold.symbol is None


def test_benchmark_ids() -> None:
    assert BENCHMARK_IDS == frozenset(
        {
            BenchmarkId.CASH_100,
            BenchmarkId.BTC_BUY_HOLD_100,
            BenchmarkId.BTC_ETH_SOL_EQUAL_WEIGHT_100,
        }
    )
    fund = build_fund_creation(created_at_ms=10)
    assert set(fund.benchmark_ids) == set(BENCHMARK_IDS)


def test_deterministic_identities() -> None:
    first = build_fund_creation(created_at_ms=42)
    second = build_fund_creation(created_at_ms=42)
    third = build_fund_creation(created_at_ms=43)
    assert first.record_identity == second.record_identity
    assert first.record_identity != third.record_identity
    assert len(first.record_identity) == 64

    decision_a = build_decision_intent(
        fund_identity=first.record_identity,
        decided_at_ms=100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal("60000.00"),
        reason="confluence watch upgrade",
        invalidation_context="close below structure",
    )
    decision_b = build_decision_intent(
        fund_identity=first.record_identity,
        decided_at_ms=100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal("60000.00"),
        reason="confluence watch upgrade",
        invalidation_context="close below structure",
    )
    assert decision_a.record_identity == decision_b.record_identity


def test_invalid_negative_cash_and_quantity_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        PaperPosition(symbol=PaperSymbol.BTCUSDT, quantity=Decimal(-1))

    fund = build_fund_creation(created_at_ms=1)
    with pytest.raises(ValueError, match="cannot be negative"):
        build_position_cash_mutation(
            fund_identity=fund.record_identity,
            source_identity=fund.record_identity,
            mutated_at_ms=2,
            cash_before_usdt=Decimal("100.00"),
            cash_after_usdt=Decimal("-0.01"),
            positions_before=(),
            positions_after=(),
        )

    with pytest.raises(ValueError, match="cannot be negative"):
        ExecutionCostAssumptions(
            fee_usdt=Decimal(-1),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
        )


def test_fees_spread_slippage_represented() -> None:
    fund = build_fund_creation(created_at_ms=1)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.BUY,
        symbol=PaperSymbol.ETHUSDT,
        quantity=Decimal("0.01"),
        reference_price=Decimal("3000.00"),
        reason="simulated allocation",
        invalidation_context="invalidation level breached",
    )
    costs = ExecutionCostAssumptions(
        fee_usdt=Decimal("0.10"),
        spread_usdt=Decimal("0.05"),
        slippage_usdt=Decimal("0.02"),
    )
    assert costs.partial_fills_supported is False
    assert PARTIAL_FILLS_SUPPORTED is False
    fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.ETHUSDT,
        quantity=Decimal("0.01"),
        reference_price=Decimal("3000.00"),
        simulated_fill_price=Decimal("3001.50"),
        costs=costs,
        venue_reference="simulated:spot:reference",
    )
    assert fill.costs.fee_usdt == Decimal("0.10")
    assert fill.costs.spread_usdt == Decimal("0.05")
    assert fill.costs.slippage_usdt == Decimal("0.02")
    assert fill.simulated_fill_price != fill.reference_price


def test_nav_snapshot_rejects_inconsistent_or_unmarked_state() -> None:
    fund = build_fund_creation(created_at_ms=1)
    with pytest.raises(ValueError, match="cash plus marked position value"):
        build_nav_snapshot(
            fund_identity=fund.record_identity,
            snapshot_at_ms=2,
            cash_usdt=Decimal("50.00"),
            positions={PaperSymbol.BTCUSDT: Decimal("0.001")},
            mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
            nav_usdt=Decimal("99.99"),
        )

    with pytest.raises(ValueError, match="requires a mark price"):
        build_nav_snapshot(
            fund_identity=fund.record_identity,
            snapshot_at_ms=3,
            cash_usdt=Decimal("50.00"),
            positions={PaperSymbol.BTCUSDT: Decimal("0.001")},
            mark_prices={},
            nav_usdt=Decimal("50.00"),
        )


def test_append_replay_ordering_and_idempotency(tmp_path: Path) -> None:
    path = tmp_path / "paper_fund.sqlite3"
    ledger = PaperFundLedger(path)

    fund = build_fund_creation(created_at_ms=1_000)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=1_100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        reason="enter small virtual size",
        invalidation_context="structure break",
    )
    costs = ExecutionCostAssumptions(
        fee_usdt=Decimal("0.05"),
        spread_usdt=Decimal("0.01"),
        slippage_usdt=Decimal("0.01"),
    )
    fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=1_200,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        simulated_fill_price=Decimal(50010),
        costs=costs,
        venue_reference="simulated:spot:reference",
    )
    mutation = build_position_cash_mutation(
        fund_identity=fund.record_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=1_300,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("49.93"),
        positions_before=(),
        positions_after={PaperSymbol.BTCUSDT: Decimal("0.001")},
    )
    snapshot = build_nav_snapshot(
        fund_identity=fund.record_identity,
        snapshot_at_ms=1_400,
        cash_usdt=Decimal("49.93"),
        positions={PaperSymbol.BTCUSDT: Decimal("0.001")},
        mark_prices={PaperSymbol.BTCUSDT: Decimal(50010)},
        nav_usdt=Decimal("99.94"),
    )

    assert (
        ledger.append_fund_creation(fund)
        is PaperLedgerWriteDisposition.INSERTED
    )
    assert (
        ledger.append_decision_intent(decision)
        is PaperLedgerWriteDisposition.INSERTED
    )
    assert (
        ledger.append_simulated_fill(fill)
        is PaperLedgerWriteDisposition.INSERTED
    )
    assert (
        ledger.append_position_cash_mutation(mutation)
        is PaperLedgerWriteDisposition.INSERTED
    )
    assert (
        ledger.append_nav_snapshot(snapshot)
        is PaperLedgerWriteDisposition.INSERTED
    )

    # Exact duplicate is idempotent.
    assert (
        ledger.append_fund_creation(fund)
        is PaperLedgerWriteDisposition.UNCHANGED
    )
    assert (
        ledger.append_decision_intent(decision)
        is PaperLedgerWriteDisposition.UNCHANGED
    )

    replayed = ledger.replay()
    assert [entry.record_kind for entry in replayed] == [
        PaperRecordKind.FUND_CREATION,
        PaperRecordKind.DECISION_INTENT,
        PaperRecordKind.SIMULATED_FILL,
        PaperRecordKind.POSITION_CASH_MUTATION,
        PaperRecordKind.NAV_SNAPSHOT,
    ]
    assert [entry.sequence_id for entry in replayed] == [1, 2, 3, 4, 5]
    assert replayed[0].record == fund
    assert replayed[1].record == decision
    assert replayed[2].record == fill
    assert replayed[3].record == mutation
    assert replayed[4].record == snapshot

    # Restart reconstructs the same append order.
    restarted = PaperFundLedger(path)
    assert [entry.record_identity for entry in restarted.replay()] == [
        entry.record_identity for entry in replayed
    ]


def test_conflicting_duplicate_fails(tmp_path: Path) -> None:
    path = tmp_path / "paper_conflict.sqlite3"
    ledger = PaperFundLedger(path)
    fund = build_fund_creation(created_at_ms=99)
    ledger.initialize()

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO paper_fund_creations (
                record_identity,
                payload_json,
                appended_at_ms
            ) VALUES (?, ?, ?)
            """,
            (fund.record_identity, '{"conflicting":"payload"}', 1),
        )
        connection.execute(
            """
            INSERT INTO paper_replay_index (
                record_kind,
                record_identity,
                appended_at_ms
            ) VALUES (?, ?, ?)
            """,
            (PaperRecordKind.FUND_CREATION.value, fund.record_identity, 1),
        )

    with pytest.raises(PaperLedgerConflictError, match="conflict"):
        ledger.append_fund_creation(fund)


def test_sql_update_and_delete_rejected(tmp_path: Path) -> None:
    path = tmp_path / "paper_immutable.sqlite3"
    ledger = PaperFundLedger(path)
    fund = build_fund_creation(created_at_ms=7)
    ledger.append_fund_creation(fund)

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper ledger"):
            connection.execute(
                "UPDATE paper_fund_creations SET appended_at_ms = 0"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper ledger"):
            connection.execute("DELETE FROM paper_fund_creations")


def test_no_real_capital_or_order_execution_surface() -> None:
    module_names = set(dir(paper))
    for name in FORBIDDEN_SURFACE_NAMES:
        assert name not in module_names

    ledger_members = {
        name for name, _ in inspect.getmembers(PaperFundLedger)
    }
    for name in (
        "place_order",
        "submit_order",
        "cancel_order",
        "update",
        "delete",
        "execute_real",
    ):
        assert name not in ledger_members

    public_methods = [
        name
        for name, member in inspect.getmembers(
            PaperFundLedger, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    ]
    assert all(
        name.startswith("append_")
        or name in {"initialize", "replay", "list_fund_creations", "get_by_identity"}
        for name in public_methods
    )
    assert REAL_CAPITAL == 0
