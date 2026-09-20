"""Focused tests for deterministic virtual execution."""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper import execution as paper_execution
from crypto_signal.paper.execution import (
    PaperExecutionRejectedError,
    build_frozen_execution_snapshot,
    simulate_paper_fill,
)
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
from crypto_signal.paper.planning import plan_hold_cash, plan_paper_trade
from crypto_signal.paper.state import PaperFundState, reconstruct_paper_fund_state


def _pristine_state(tmp_path: Path) -> PaperFundState:
    ledger = PaperFundLedger(tmp_path / "execution_pristine.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return reconstruct_paper_fund_state(ledger)


def _held_state(tmp_path: Path) -> PaperFundState:
    ledger = PaperFundLedger(tmp_path / "execution_held.sqlite3")
    fund = build_fund_creation(created_at_ms=1)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal("20000"),
        reason="seed holding",
        invalidation_context="seed only",
    )
    fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal("20000"),
        simulated_fill_price=Decimal("20000"),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal(0),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
        ),
        venue_reference="seed:virtual",
    )
    mutation = build_position_cash_mutation(
        fund_identity=fund.record_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=4,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("80.00"),
        positions_before=(),
        positions_after={PaperSymbol.BTCUSDT: Decimal("0.001")},
    )
    ledger.append_fund_creation(fund)
    ledger.append_decision_intent(decision)
    ledger.append_simulated_fill(fill)
    ledger.append_position_cash_mutation(mutation)
    return reconstruct_paper_fund_state(ledger)


def _snapshot(
    *,
    min_quantity: str = "0.0001",
    quantity_step: str = "0.0001",
    min_notional: str = "5",
    policy_version: str = "paper_execution_policy.v1",
):
    return build_frozen_execution_snapshot(
        venue_reference="frozen:test-venue",
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal(quantity_step),
        min_quantity=Decimal(min_quantity),
        min_notional_usdt=Decimal(min_notional),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
        policy_version=policy_version,
    )


def _buy_plan(state: PaperFundState, *, budget: str = "0.05"):
    return plan_paper_trade(
        state=state,
        planned_at_ms=10,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal(budget),
        reason="bounded buy",
        invalidation_context="close below frozen structure",
        mark_prices={PaperSymbol.BTCUSDT: Decimal("20000")},
    )


def test_frozen_snapshot_identity_is_deterministic_and_rule_sensitive() -> None:
    first = _snapshot(min_notional="5")
    same = _snapshot(min_notional="5")
    changed = _snapshot(min_notional="10")

    assert first.snapshot_identity == same.snapshot_identity
    assert first.snapshot_identity != changed.snapshot_identity
    assert first.execution_reference.endswith(first.snapshot_identity)
    assert first.real_capital == REAL_CAPITAL == 0


def test_reject_minimum_quantity_step_and_notional(tmp_path: Path) -> None:
    state = _pristine_state(tmp_path)

    below_min = plan_paper_trade(
        state=state,
        planned_at_ms=11,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0001"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal("0.10"),
        reason="min probe",
        invalidation_context="probe",
        mark_prices={PaperSymbol.BTCUSDT: Decimal("20000")},
    )
    with pytest.raises(PaperExecutionRejectedError, match="minimum quantity"):
        simulate_paper_fill(
            plan=below_min,
            snapshot=_snapshot(min_quantity="0.0002"),
            decision_identity="a" * 64,
            filled_at_ms=11,
        )

    bad_step = plan_paper_trade(
        state=state,
        planned_at_ms=12,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.00015"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal("0.10"),
        reason="step probe",
        invalidation_context="probe",
        mark_prices={PaperSymbol.BTCUSDT: Decimal("20000")},
    )
    with pytest.raises(PaperExecutionRejectedError, match="quantity_step"):
        simulate_paper_fill(
            plan=bad_step,
            snapshot=_snapshot(quantity_step="0.0001", min_notional="1"),
            decision_identity="b" * 64,
            filled_at_ms=12,
        )

    below_notional = plan_paper_trade(
        state=state,
        planned_at_ms=13,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0002"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal("0.10"),
        reason="notional probe",
        invalidation_context="probe",
        mark_prices={PaperSymbol.BTCUSDT: Decimal("20000")},
    )
    with pytest.raises(PaperExecutionRejectedError, match="minimum notional"):
        simulate_paper_fill(
            plan=below_notional,
            snapshot=_snapshot(min_notional="5"),
            decision_identity="c" * 64,
            filled_at_ms=13,
        )


def test_adverse_pricing_and_explicit_cost_accounting(tmp_path: Path) -> None:
    state = _pristine_state(tmp_path)
    buy = simulate_paper_fill(
        plan=_buy_plan(state),
        snapshot=_snapshot(),
        decision_identity="d" * 64,
        filled_at_ms=10,
    )
    assert buy.fill is not None
    assert buy.costs is not None
    assert buy.fill.simulated_fill_price == Decimal("20020.0000")
    assert buy.reference_notional_usdt == Decimal("20.000")
    assert buy.fill_notional_usdt == Decimal("20.0200000")
    assert buy.costs.spread_usdt == Decimal("0.0100000")
    assert buy.costs.slippage_usdt == Decimal("0.0100000")
    assert buy.costs.fee_usdt == Decimal("0.0200200000")
    assert buy.total_cost_usdt == Decimal("0.0400200000")

    held = _held_state(tmp_path)
    reduce_plan = plan_paper_trade(
        state=held,
        planned_at_ms=20,
        action=PaperAction.REDUCE,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0004"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal("0.05"),
        reason="bounded reduce",
        invalidation_context="reduce exposure",
    )
    sell = simulate_paper_fill(
        plan=reduce_plan,
        snapshot=_snapshot(),
        decision_identity="e" * 64,
        filled_at_ms=20,
    )
    assert sell.fill is not None
    assert sell.fill.simulated_fill_price == Decimal("19980.0000")
    assert sell.fill.simulated_fill_price < reduce_plan.reference_price


def test_insufficient_cost_budget_rejected(tmp_path: Path) -> None:
    state = _pristine_state(tmp_path)
    with pytest.raises(PaperExecutionRejectedError, match="cost budget"):
        simulate_paper_fill(
            plan=_buy_plan(state, budget="0.01"),
            snapshot=_snapshot(),
            decision_identity="f" * 64,
            filled_at_ms=10,
        )


def test_snapshot_provenance_changes_fill_identity_even_same_fill_math(
    tmp_path: Path,
) -> None:
    state = _pristine_state(tmp_path)
    plan = _buy_plan(state)
    first_snapshot = _snapshot(min_notional="5")
    second_snapshot = _snapshot(min_notional="10")

    first = simulate_paper_fill(
        plan=plan,
        snapshot=first_snapshot,
        decision_identity="1" * 64,
        filled_at_ms=10,
    )
    second = simulate_paper_fill(
        plan=plan,
        snapshot=second_snapshot,
        decision_identity="1" * 64,
        filled_at_ms=10,
    )
    assert first.fill is not None and second.fill is not None
    assert first.fill.simulated_fill_price == second.fill.simulated_fill_price
    assert first_snapshot.snapshot_identity != second_snapshot.snapshot_identity
    assert first.fill.venue_reference != second.fill.venue_reference
    assert first.fill.record_identity != second.fill.record_identity


def test_hold_cash_has_no_execution_snapshot_or_fill(tmp_path: Path) -> None:
    state = _pristine_state(tmp_path)
    plan = plan_hold_cash(
        state=state,
        planned_at_ms=30,
        reason="cash is valid",
        invalidation_context="wait for evidence",
    )
    result = simulate_paper_fill(
        plan=plan,
        snapshot=None,
        decision_identity="2" * 64,
        filled_at_ms=30,
    )
    assert result.fill is None
    assert result.costs is None
    assert result.snapshot_identity is None
    assert result.total_cost_usdt == Decimal(0)


def test_same_inputs_are_deterministic(tmp_path: Path) -> None:
    state = _pristine_state(tmp_path)
    plan = _buy_plan(state)
    snapshot = _snapshot()
    first = simulate_paper_fill(
        plan=plan,
        snapshot=snapshot,
        decision_identity="3" * 64,
        filled_at_ms=10,
    )
    second = simulate_paper_fill(
        plan=plan,
        snapshot=snapshot,
        decision_identity="3" * 64,
        filled_at_ms=10,
    )
    assert first == second


def test_no_network_exchange_credential_order_surface() -> None:
    source = inspect.getsource(paper_execution).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
    )
    assert REAL_CAPITAL == 0
    assert all(token not in source for token in forbidden)
