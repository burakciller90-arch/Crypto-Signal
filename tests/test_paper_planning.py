"""Focused tests for conservative paper-fund virtual planning."""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper import planning as paper_planning
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    ExecutionCostAssumptions,
    FundCreationRecord,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.planning import (
    DEFAULT_MAX_GROSS_EXPOSURE_FRACTION,
    DEFAULT_MAX_POSITION_CONCENTRATION,
    DEFAULT_MIN_CASH_RESERVE_USDT,
    PaperPlanRejectedError,
    PaperRiskPolicy,
    PaperTradePlan,
    default_conservative_risk_policy,
    plan_hold_cash,
    plan_or_hold_on_missing_evidence,
    plan_paper_trade,
)
from crypto_signal.paper.state import PaperFundState, reconstruct_paper_fund_state


def _pristine_state(tmp_path: Path) -> tuple[PaperFundState, FundCreationRecord]:
    ledger = PaperFundLedger(tmp_path / "plan_fund.sqlite3")
    fund = build_fund_creation(created_at_ms=100)
    ledger.append_fund_creation(fund)
    return reconstruct_paper_fund_state(ledger), fund


def test_hold_cash_valid(tmp_path: Path) -> None:
    state, fund = _pristine_state(tmp_path)
    plan = plan_hold_cash(
        state=state,
        planned_at_ms=200,
        reason="cash is a valid professional allocation",
        invalidation_context="remain in cash until evidence improves",
    )
    assert isinstance(plan, PaperTradePlan)
    assert plan.action is PaperAction.HOLD_CASH
    assert plan.fund_identity == fund.record_identity
    assert plan.symbol is None
    assert plan.quantity is None
    assert plan.virtual_notional_usdt == Decimal(0)
    assert plan.cost_budget_usdt == Decimal(0)
    assert plan.projected_cash_usdt == Decimal("100.00")
    assert plan.projected_positions == ()
    assert plan.risk_policy_version == PAPER_RISK_POLICY_VERSION
    assert plan.real_capital == 0


def test_deterministic_plan_identity(tmp_path: Path) -> None:
    state, _fund = _pristine_state(tmp_path)
    first = plan_paper_trade(
        state=state,
        planned_at_ms=300,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0002"),
        reference_price=Decimal(50000),
        cost_budget_usdt=Decimal("0.10"),
        reason="bounded virtual buy",
        invalidation_context="close below structure",
        mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
    )
    second = plan_paper_trade(
        state=state,
        planned_at_ms=300,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0002"),
        reference_price=Decimal(50000),
        cost_budget_usdt=Decimal("0.10"),
        reason="bounded virtual buy",
        invalidation_context="close below structure",
        mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
    )
    assert first.plan_identity == second.plan_identity
    assert len(first.plan_identity) == 64

    third = plan_paper_trade(
        state=state,
        planned_at_ms=301,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0002"),
        reference_price=Decimal(50000),
        cost_budget_usdt=Decimal("0.10"),
        reason="bounded virtual buy",
        invalidation_context="close below structure",
        mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
    )
    assert third.plan_identity != first.plan_identity


def test_reject_buy_above_available_cash_or_cost_budget(tmp_path: Path) -> None:
    state, _fund = _pristine_state(tmp_path)
    with pytest.raises(PaperPlanRejectedError, match="available cash"):
        plan_paper_trade(
            state=state,
            planned_at_ms=1,
            action=PaperAction.BUY,
            symbol=PaperSymbol.BTCUSDT,
            quantity=Decimal("0.003"),
            reference_price=Decimal(50000),
            cost_budget_usdt=Decimal("1.00"),
            reason="too large",
            invalidation_context="n/a",
            mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
        )

    # 90 notional + 1 cost leaves 9 cash, below 20 reserve — but first check may
    # also be cash; use a buy that fits cash but fails reserve separately below.
    with pytest.raises(PaperPlanRejectedError, match="cost budget|available cash"):
        plan_paper_trade(
            state=state,
            planned_at_ms=2,
            action=PaperAction.BUY,
            symbol=PaperSymbol.ETHUSDT,
            quantity=Decimal("0.04"),
            reference_price=Decimal(3000),
            cost_budget_usdt=Decimal("20.00"),
            reason="costs push over cash",
            invalidation_context="n/a",
            mark_prices={PaperSymbol.ETHUSDT: Decimal(3000)},
        )


def test_reject_reduce_exit_above_holdings(tmp_path: Path) -> None:
    # Seed a virtual holding via ledger mutation, then reconstruct.
    ledger = PaperFundLedger(tmp_path / "held.sqlite3")
    fund = build_fund_creation(created_at_ms=1)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        reason="seed",
        invalidation_context="n/a",
    )
    fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        simulated_fill_price=Decimal(50000),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal(0),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
        ),
        venue_reference="simulated:spot:reference",
    )
    mutation = build_position_cash_mutation(
        fund_identity=fund.record_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=4,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("50.00"),
        positions_before=(),
        positions_after={PaperSymbol.BTCUSDT: Decimal("0.001")},
    )
    ledger.append_fund_creation(fund)
    ledger.append_decision_intent(decision)
    ledger.append_simulated_fill(fill)
    ledger.append_position_cash_mutation(mutation)
    held = reconstruct_paper_fund_state(ledger)

    with pytest.raises(PaperPlanRejectedError, match="exceeds virtual holdings"):
        plan_paper_trade(
            state=held,
            planned_at_ms=5,
            action=PaperAction.REDUCE,
            symbol=PaperSymbol.BTCUSDT,
            quantity=Decimal("0.002"),
            reference_price=Decimal(50000),
            cost_budget_usdt=Decimal("0.01"),
            reason="over-reduce",
            invalidation_context="n/a",
        )

    with pytest.raises(PaperPlanRejectedError, match="exceeds virtual holdings"):
        plan_paper_trade(
            state=held,
            planned_at_ms=6,
            action=PaperAction.EXIT,
            symbol=PaperSymbol.BTCUSDT,
            quantity=Decimal("0.002"),
            reference_price=Decimal(50000),
            cost_budget_usdt=Decimal("0.01"),
            reason="over-exit",
            invalidation_context="n/a",
        )

    exit_plan = plan_paper_trade(
        state=held,
        planned_at_ms=7,
        action=PaperAction.EXIT,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        cost_budget_usdt=Decimal("0.05"),
        reason="full exit",
        invalidation_context="invalidation hit",
    )
    assert exit_plan.projected_quantity is None
    assert exit_plan.projected_positions == ()
    assert exit_plan.projected_cash_usdt == Decimal("99.95")


def test_conservative_concentration_and_cash_reserve_enforced(
    tmp_path: Path,
) -> None:
    state, _fund = _pristine_state(tmp_path)
    policy = default_conservative_risk_policy()
    assert policy.version == PAPER_RISK_POLICY_VERSION
    assert policy.max_position_concentration == DEFAULT_MAX_POSITION_CONCENTRATION
    assert policy.min_cash_reserve_usdt == DEFAULT_MIN_CASH_RESERVE_USDT
    assert policy.max_gross_exposure_fraction == DEFAULT_MAX_GROSS_EXPOSURE_FRACTION
    assert policy.allow_leverage is False
    assert policy.allow_martingale is False

    # 40 USDT buy leaves 60 cash (>= 20 reserve) but 40% concentration > 25%.
    with pytest.raises(PaperPlanRejectedError, match="concentration"):
        plan_paper_trade(
            state=state,
            planned_at_ms=1,
            action=PaperAction.BUY,
            symbol=PaperSymbol.BTCUSDT,
            quantity=Decimal("0.0008"),
            reference_price=Decimal(50000),
            cost_budget_usdt=Decimal(0),
            reason="concentration breach",
            invalidation_context="n/a",
            mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
            risk_policy=policy,
        )

    # 85 USDT buy fits concentration if we used a looser policy, but breaches reserve.
    loose = PaperRiskPolicy(
        version=PAPER_RISK_POLICY_VERSION,
        max_position_concentration=Decimal("0.95"),
        min_cash_reserve_usdt=DEFAULT_MIN_CASH_RESERVE_USDT,
        max_gross_exposure_fraction=Decimal("0.95"),
    )
    with pytest.raises(PaperPlanRejectedError, match="cash reserve"):
        plan_paper_trade(
            state=state,
            planned_at_ms=2,
            action=PaperAction.BUY,
            symbol=PaperSymbol.ETHUSDT,
            quantity=Decimal("0.03"),
            reference_price=Decimal(3000),
            cost_budget_usdt=Decimal(0),
            reason="reserve breach",
            invalidation_context="n/a",
            mark_prices={PaperSymbol.ETHUSDT: Decimal(3000)},
            risk_policy=loose,
        )

    # Valid conservative buy: 20 USDT notional + 0.5 costs => cash 79.5, conc 20%.
    ok = plan_paper_trade(
        state=state,
        planned_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.SOLUSDT,
        quantity=Decimal("0.2"),
        reference_price=Decimal(100),
        cost_budget_usdt=Decimal("0.50"),
        reason="within conservative limits",
        invalidation_context="invalidate above range",
        mark_prices={PaperSymbol.SOLUSDT: Decimal(100)},
        risk_policy=policy,
    )
    assert ok.action is PaperAction.BUY
    assert ok.projected_cash_usdt == Decimal("79.50")
    assert ok.projected_quantity == Decimal("0.2")
    assert ok.virtual_notional_usdt == Decimal("20.0")
    assert ok.cost_budget_usdt == Decimal("0.50")
    assert ok.risk_policy_version == PAPER_RISK_POLICY_VERSION


def test_buy_concentration_uses_projected_nav_after_costs(tmp_path: Path) -> None:
    state, _fund = _pristine_state(tmp_path)
    policy = PaperRiskPolicy(
        version="paper_risk_policy.cost-aware-test",
        max_position_concentration=Decimal("0.25"),
        min_cash_reserve_usdt=Decimal(0),
        max_gross_exposure_fraction=Decimal(1),
    )
    with pytest.raises(PaperPlanRejectedError, match="concentration"):
        plan_paper_trade(
            state=state,
            planned_at_ms=10,
            action=PaperAction.BUY,
            symbol=PaperSymbol.BTCUSDT,
            quantity=Decimal("0.00125"),
            reference_price=Decimal(20000),
            cost_budget_usdt=Decimal(1),
            reason="boundary concentration",
            invalidation_context="test boundary",
            mark_prices={},
            risk_policy=policy,
        )


def test_missing_evidence_holds_cash(tmp_path: Path) -> None:
    state, _fund = _pristine_state(tmp_path)
    hold = plan_or_hold_on_missing_evidence(
        state=state,
        planned_at_ms=1,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0001"),
        reference_price=None,
        reason="would buy if priced",
        invalidation_context="n/a",
    )
    assert hold.action is PaperAction.HOLD_CASH
    assert hold.projected_cash_usdt == state.cash_usdt

    hold2 = plan_or_hold_on_missing_evidence(
        state=state,
        planned_at_ms=2,
        action=None,
        reason="no decision",
        invalidation_context="insufficient evidence",
    )
    assert hold2.action is PaperAction.HOLD_CASH


def test_plan_does_not_mutate_ledger(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "immutable_plan.sqlite3")
    fund = build_fund_creation(created_at_ms=50)
    ledger.append_fund_creation(fund)
    state = reconstruct_paper_fund_state(ledger)
    before = ledger.replay()

    plan_paper_trade(
        state=state,
        planned_at_ms=51,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0002"),
        reference_price=Decimal(50000),
        cost_budget_usdt=Decimal("0.05"),
        reason="intent only",
        invalidation_context="n/a",
        mark_prices={PaperSymbol.BTCUSDT: Decimal(50000)},
    )
    after = ledger.replay()
    assert len(before) == len(after) == 1
    assert before[0].record_identity == after[0].record_identity


def test_no_real_order_network_credential_surface() -> None:
    assert REAL_CAPITAL == 0
    assert paper_planning.REAL_CAPITAL == 0

    forbidden = {
        "place_order",
        "submit_order",
        "cancel_order",
        "exchange_order",
        "live_order",
        "broker",
        "api_key",
        "api_secret",
        "credentials",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "append_fund_creation",
        "append_decision_intent",
        "append_simulated_fill",
        "append_position_cash_mutation",
    }
    names = set(dir(paper_planning))
    for name in forbidden:
        assert name not in names

    source = inspect.getsource(paper_planning)
    for token in (
        "requests.",
        "httpx.",
        "urllib",
        "socket.",
        "api_key",
        "api_secret",
        "place_order",
        "submit_order",
    ):
        assert token not in source

    policy = default_conservative_risk_policy()
    assert isinstance(policy, PaperRiskPolicy)
    assert policy.max_position_concentration == Decimal("0.25")
    assert policy.min_cash_reserve_usdt == Decimal("20.00")
