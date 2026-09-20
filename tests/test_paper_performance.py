"""Tests for immutable simulated closed-trade performance truth."""

from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    ExecutionCostAssumptions,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.performance import (
    PaperTradeOutcome,
    PaperTradePerformanceError,
    PaperTradePerformanceStatus,
    read_paper_trade_performance,
)


def _fund(tmp_path) -> tuple[PaperFundLedger, str]:
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    creation = build_fund_creation(created_at_ms=1)
    ledger.append_fund_creation(creation)
    return ledger, creation.record_identity


def _append_buy(
    ledger: PaperFundLedger,
    fund_identity: str,
    *,
    decided_at_ms: int = 100,
) -> tuple[Decimal, str]:
    quantity = Decimal("0.1")
    decision = build_decision_intent(
        fund_identity=fund_identity,
        decided_at_ms=decided_at_ms,
        action=PaperAction.BUY,
        reason="performance fixture buy",
        invalidation_context="fixture",
        symbol=PaperSymbol.BTCUSDT,
        quantity=quantity,
        reference_price=Decimal(100),
    )
    ledger.append_decision_intent(decision)
    fill = build_simulated_fill(
        fund_identity=fund_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=decided_at_ms + 1,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=quantity,
        reference_price=Decimal(100),
        simulated_fill_price=Decimal("100.1"),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.01001"),
            spread_usdt=Decimal("0.005"),
            slippage_usdt=Decimal("0.005"),
        ),
        venue_reference="fixture-buy",
    )
    ledger.append_simulated_fill(fill)
    cash_after = Decimal("89.97999")
    mutation = build_position_cash_mutation(
        fund_identity=fund_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=decided_at_ms + 1,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=cash_after,
        positions_before=(),
        positions_after={PaperSymbol.BTCUSDT: quantity},
    )
    ledger.append_position_cash_mutation(mutation)
    return cash_after, fill.record_identity


def _append_exit(
    ledger: PaperFundLedger,
    fund_identity: str,
    *,
    cash_before: Decimal,
    decided_at_ms: int = 200,
) -> tuple[Decimal, str]:
    quantity = Decimal("0.1")
    decision = build_decision_intent(
        fund_identity=fund_identity,
        decided_at_ms=decided_at_ms,
        action=PaperAction.EXIT,
        reason="performance fixture exit",
        invalidation_context="fixture",
        symbol=PaperSymbol.BTCUSDT,
        quantity=quantity,
        reference_price=Decimal(120),
    )
    ledger.append_decision_intent(decision)
    fill = build_simulated_fill(
        fund_identity=fund_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=decided_at_ms + 1,
        action=PaperAction.EXIT,
        symbol=PaperSymbol.BTCUSDT,
        quantity=quantity,
        reference_price=Decimal(120),
        simulated_fill_price=Decimal("119.88"),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.011988"),
            spread_usdt=Decimal("0.006"),
            slippage_usdt=Decimal("0.006"),
        ),
        venue_reference="fixture-exit",
    )
    ledger.append_simulated_fill(fill)
    cash_after = Decimal("101.956002")
    mutation = build_position_cash_mutation(
        fund_identity=fund_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=decided_at_ms + 1,
        cash_before_usdt=cash_before,
        cash_after_usdt=cash_after,
        positions_before={PaperSymbol.BTCUSDT: quantity},
        positions_after=(),
    )
    ledger.append_position_cash_mutation(mutation)
    return cash_after, fill.record_identity


def test_no_closed_trades_is_not_yet_measured_not_zero_win_rate(tmp_path) -> None:
    ledger, _ = _fund(tmp_path)

    snapshot = read_paper_trade_performance(
        paper_ledger_path=ledger.path,
        observed_at_ms=500,
    )

    assert snapshot.status is PaperTradePerformanceStatus.NOT_YET_MEASURED
    assert snapshot.closed_trade_count == 0
    assert snapshot.open_trade_count == 0
    assert snapshot.closed_trades == ()
    assert snapshot.win_rate_fraction is None
    assert snapshot.total_closed_trade_net_pnl_usdt is None
    assert snapshot.average_closed_trade_net_pnl_usdt is None
    assert snapshot.profit_factor is None
    assert snapshot.total_explicit_execution_cost_usdt is None
    assert snapshot.real_capital == REAL_CAPITAL == 0


def test_open_trade_does_not_invent_closed_trade_success(tmp_path) -> None:
    ledger, fund_identity = _fund(tmp_path)
    _append_buy(ledger, fund_identity)

    snapshot = read_paper_trade_performance(
        paper_ledger_path=ledger.path,
        observed_at_ms=500,
    )

    assert snapshot.status is PaperTradePerformanceStatus.NOT_YET_MEASURED
    assert snapshot.closed_trade_count == 0
    assert snapshot.open_trade_count == 1
    assert snapshot.open_trade_symbols == (PaperSymbol.BTCUSDT,)
    assert snapshot.win_rate_fraction is None
    assert snapshot.total_closed_trade_net_pnl_usdt is None


def test_closed_trade_performance_uses_accounting_cash_lineage(tmp_path) -> None:
    ledger, fund_identity = _fund(tmp_path)
    cash_after_buy, buy_fill_identity = _append_buy(ledger, fund_identity)
    final_cash, exit_fill_identity = _append_exit(
        ledger,
        fund_identity,
        cash_before=cash_after_buy,
    )

    snapshot = read_paper_trade_performance(
        paper_ledger_path=ledger.path,
        observed_at_ms=500,
    )

    expected_pnl = final_cash - Decimal("100.00")
    entry_outflow = Decimal("100.00") - cash_after_buy
    expected_return = expected_pnl / entry_outflow
    expected_cost = Decimal("0.043998")

    assert snapshot.status is PaperTradePerformanceStatus.AVAILABLE
    assert snapshot.closed_trade_count == 1
    assert snapshot.open_trade_count == 0
    assert snapshot.win_count == 1
    assert snapshot.loss_count == 0
    assert snapshot.breakeven_count == 0
    assert snapshot.win_rate_fraction == Decimal(1)
    assert snapshot.total_closed_trade_net_pnl_usdt == expected_pnl
    assert snapshot.average_closed_trade_net_pnl_usdt == expected_pnl
    assert snapshot.average_closed_trade_return_fraction == expected_return
    assert snapshot.gross_profit_usdt == expected_pnl
    assert snapshot.gross_loss_usdt == Decimal(0)
    assert snapshot.profit_factor is None
    assert snapshot.best_trade_pnl_usdt == expected_pnl
    assert snapshot.worst_trade_pnl_usdt == expected_pnl
    assert snapshot.total_explicit_execution_cost_usdt == expected_cost

    trade = snapshot.closed_trades[0]
    assert trade.entry_fill_identity == buy_fill_identity
    assert trade.exit_fill_identity == exit_fill_identity
    assert trade.entry_cash_outflow_usdt == entry_outflow
    assert trade.exit_cash_inflow_usdt == Decimal("11.976012")
    assert trade.net_pnl_usdt == expected_pnl
    assert trade.return_fraction == expected_return
    assert trade.explicit_execution_cost_usdt == expected_cost
    assert trade.outcome is PaperTradeOutcome.WIN
    assert trade.symbol is PaperSymbol.BTCUSDT
    assert trade.quantity == Decimal("0.1")
    assert snapshot.real_capital == REAL_CAPITAL == 0


def test_fill_without_accounting_mutation_fails_closed(tmp_path) -> None:
    ledger, fund_identity = _fund(tmp_path)
    decision = build_decision_intent(
        fund_identity=fund_identity,
        decided_at_ms=100,
        action=PaperAction.BUY,
        reason="missing mutation fixture",
        invalidation_context="fixture",
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.1"),
        reference_price=Decimal(100),
    )
    ledger.append_decision_intent(decision)
    fill = build_simulated_fill(
        fund_identity=fund_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=101,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.1"),
        reference_price=Decimal(100),
        simulated_fill_price=Decimal("100.1"),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.01001"),
            spread_usdt=Decimal("0.005"),
            slippage_usdt=Decimal("0.005"),
        ),
        venue_reference="missing-mutation",
    )
    ledger.append_simulated_fill(fill)

    with pytest.raises(
        PaperTradePerformanceError,
        match="missing its accounting mutation",
    ):
        read_paper_trade_performance(
            paper_ledger_path=ledger.path,
            observed_at_ms=500,
        )


def test_accounting_mutation_that_disagrees_with_fill_fails_closed(tmp_path) -> None:
    ledger, fund_identity = _fund(tmp_path)
    decision = build_decision_intent(
        fund_identity=fund_identity,
        decided_at_ms=100,
        action=PaperAction.BUY,
        reason="bad cash fixture",
        invalidation_context="fixture",
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.1"),
        reference_price=Decimal(100),
    )
    ledger.append_decision_intent(decision)
    fill = build_simulated_fill(
        fund_identity=fund_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=101,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.1"),
        reference_price=Decimal(100),
        simulated_fill_price=Decimal("100.1"),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.01001"),
            spread_usdt=Decimal("0.005"),
            slippage_usdt=Decimal("0.005"),
        ),
        venue_reference="bad-cash",
    )
    ledger.append_simulated_fill(fill)
    mutation = build_position_cash_mutation(
        fund_identity=fund_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=101,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("90.00"),
        positions_before=(),
        positions_after={PaperSymbol.BTCUSDT: Decimal("0.1")},
    )
    ledger.append_position_cash_mutation(mutation)

    with pytest.raises(
        PaperTradePerformanceError,
        match="BUY mutation cash does not match fill",
    ):
        read_paper_trade_performance(
            paper_ledger_path=ledger.path,
            observed_at_ms=500,
        )
