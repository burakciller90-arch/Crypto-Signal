"""Focused tests for pure paper-fund execution orchestration."""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper import orchestration as paper_orchestration
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    ExecutionCostAssumptions,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.orchestration import (
    PaperOrchestrationRejectedError,
    orchestrate_paper_plan,
)
from crypto_signal.paper.planning import (
    PaperRiskPolicy,
    plan_hold_cash,
    plan_paper_trade,
)
from crypto_signal.paper.state import PaperFundState, reconstruct_paper_fund_state


def _pristine_state(
    tmp_path: Path,
    *,
    name: str = "orchestration_pristine.sqlite3",
    created_at_ms: int = 1,
) -> tuple[PaperFundState, PaperFundLedger]:
    ledger = PaperFundLedger(tmp_path / name)
    ledger.append_fund_creation(build_fund_creation(created_at_ms=created_at_ms))
    return reconstruct_paper_fund_state(ledger), ledger


def _held_state(tmp_path: Path) -> PaperFundState:
    ledger = PaperFundLedger(tmp_path / "orchestration_held.sqlite3")
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
    symbol: PaperSymbol = PaperSymbol.BTCUSDT,
    policy_version: str = PAPER_EXECUTION_POLICY_VERSION,
    min_notional: str = "5",
):
    return build_frozen_execution_snapshot(
        venue_reference="frozen:test-venue",
        symbol=symbol,
        quantity_step=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        min_notional_usdt=Decimal(min_notional),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
        policy_version=policy_version,
    )


def _buy_plan(
    state: PaperFundState,
    *,
    risk_policy: PaperRiskPolicy | None = None,
    budget: str = "0.05",
):
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
        risk_policy=risk_policy,
    )


def test_valid_buy_chain_is_policy_bound_and_reconciled(tmp_path: Path) -> None:
    state, _ledger = _pristine_state(tmp_path)
    plan = _buy_plan(state)
    snapshot = _snapshot()

    bundle = orchestrate_paper_plan(
        state=state,
        plan=plan,
        snapshot=snapshot,
    )

    assert bundle.decision.action is PaperAction.BUY
    assert bundle.decision.reason == plan.reason
    assert bundle.decision.invalidation_context == plan.invalidation_context
    assert bundle.decision.risk_policy_version == PAPER_RISK_POLICY_VERSION
    assert bundle.fill is not None
    assert bundle.mutation is not None
    assert bundle.fill.decision_identity == bundle.decision.record_identity
    assert bundle.fill.venue_reference == snapshot.execution_reference
    assert bundle.execution_snapshot_identity == snapshot.snapshot_identity
    assert bundle.fill.costs.execution_policy_version == PAPER_EXECUTION_POLICY_VERSION
    assert bundle.mutation.source_identity == bundle.fill.record_identity
    assert bundle.mutation.cash_before_usdt == Decimal("100.00")
    assert bundle.mutation.cash_after_usdt == Decimal("79.9599800000")
    assert bundle.mutation.cash_after_usdt > plan.projected_cash_usdt
    assert bundle.mutation.positions_after == plan.projected_positions
    assert bundle.real_capital == REAL_CAPITAL == 0


def test_valid_reduce_and_exit_chains(tmp_path: Path) -> None:
    state = _held_state(tmp_path)
    snapshot = _snapshot()

    reduce_plan = plan_paper_trade(
        state=state,
        planned_at_ms=20,
        action=PaperAction.REDUCE,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.0004"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal("0.05"),
        reason="reduce exposure",
        invalidation_context="risk reduction",
    )
    reduced = orchestrate_paper_plan(
        state=state,
        plan=reduce_plan,
        snapshot=snapshot,
    )
    assert reduced.fill is not None
    assert reduced.mutation is not None
    assert reduced.mutation.cash_after_usdt == Decimal("87.9840080000")
    assert reduced.mutation.positions_after[0].quantity == Decimal("0.0006")

    exit_plan = plan_paper_trade(
        state=state,
        planned_at_ms=21,
        action=PaperAction.EXIT,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal("20000"),
        cost_budget_usdt=Decimal("0.05"),
        reason="close position",
        invalidation_context="exit condition met",
    )
    exited = orchestrate_paper_plan(
        state=state,
        plan=exit_plan,
        snapshot=snapshot,
    )
    assert exited.fill is not None
    assert exited.mutation is not None
    assert exited.mutation.cash_after_usdt == Decimal("99.9600200000")
    assert exited.mutation.positions_after == ()


def test_hold_cash_emits_decision_only(tmp_path: Path) -> None:
    state, _ledger = _pristine_state(tmp_path)
    plan = plan_hold_cash(
        state=state,
        planned_at_ms=30,
        reason="cash remains valid",
        invalidation_context="wait for better evidence",
    )
    bundle = orchestrate_paper_plan(state=state, plan=plan, snapshot=None)

    assert bundle.decision.action is PaperAction.HOLD_CASH
    assert bundle.fill is None
    assert bundle.mutation is None
    assert bundle.execution_snapshot_identity is None
    assert bundle.execution.total_cost_usdt == Decimal(0)


def test_risk_policy_mismatch_is_rejected(tmp_path: Path) -> None:
    state, _ledger = _pristine_state(tmp_path)
    other_policy = PaperRiskPolicy(
        version="paper_risk_policy.probe-other",
        max_position_concentration=Decimal("0.25"),
        min_cash_reserve_usdt=Decimal("20"),
        max_gross_exposure_fraction=Decimal("0.50"),
    )
    plan = _buy_plan(state, risk_policy=other_policy)

    with pytest.raises(PaperOrchestrationRejectedError, match="risk policy"):
        orchestrate_paper_plan(
            state=state,
            plan=plan,
            snapshot=_snapshot(),
        )


def test_execution_policy_mismatch_is_rejected(tmp_path: Path) -> None:
    state, _ledger = _pristine_state(tmp_path)
    plan = _buy_plan(state)

    with pytest.raises(PaperOrchestrationRejectedError, match="execution snapshot policy"):
        orchestrate_paper_plan(
            state=state,
            plan=plan,
            snapshot=_snapshot(policy_version="paper_execution_policy.probe-other"),
        )


def test_fund_or_symbol_mismatch_is_rejected(tmp_path: Path) -> None:
    state_a, _ledger_a = _pristine_state(
        tmp_path,
        name="fund_a.sqlite3",
        created_at_ms=1,
    )
    state_b, _ledger_b = _pristine_state(
        tmp_path,
        name="fund_b.sqlite3",
        created_at_ms=2,
    )
    plan_b = _buy_plan(state_b)
    with pytest.raises(PaperOrchestrationRejectedError, match="fund identity"):
        orchestrate_paper_plan(
            state=state_a,
            plan=plan_b,
            snapshot=_snapshot(),
        )

    plan_a = _buy_plan(state_a)
    with pytest.raises(PaperOrchestrationRejectedError, match="symbol"):
        orchestrate_paper_plan(
            state=state_a,
            plan=plan_a,
            snapshot=_snapshot(symbol=PaperSymbol.ETHUSDT),
        )


def test_snapshot_provenance_is_visible_in_bundle_and_fill(tmp_path: Path) -> None:
    state, _ledger = _pristine_state(tmp_path)
    plan = _buy_plan(state)
    first = orchestrate_paper_plan(
        state=state,
        plan=plan,
        snapshot=_snapshot(min_notional="5"),
    )
    second = orchestrate_paper_plan(
        state=state,
        plan=plan,
        snapshot=_snapshot(min_notional="10"),
    )
    assert first.fill is not None and second.fill is not None
    assert first.execution_snapshot_identity != second.execution_snapshot_identity
    assert first.fill.record_identity != second.fill.record_identity


def test_orchestration_is_deterministic_and_does_not_write_ledger(
    tmp_path: Path,
) -> None:
    state, ledger = _pristine_state(tmp_path)
    plan = _buy_plan(state)
    snapshot = _snapshot()
    before = ledger.replay()

    first = orchestrate_paper_plan(
        state=state,
        plan=plan,
        snapshot=snapshot,
    )
    second = orchestrate_paper_plan(
        state=state,
        plan=plan,
        snapshot=snapshot,
    )

    assert first == second
    assert ledger.replay() == before


def test_insufficient_execution_cost_budget_rejected(tmp_path: Path) -> None:
    state, _ledger = _pristine_state(tmp_path)
    plan = _buy_plan(state, budget="0.01")
    with pytest.raises(PaperOrchestrationRejectedError, match="cost budget"):
        orchestrate_paper_plan(
            state=state,
            plan=plan,
            snapshot=_snapshot(),
        )


def test_no_network_exchange_credential_or_ledger_write_surface() -> None:
    source = inspect.getsource(paper_orchestration).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "paperfundledger",
        ".append_",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
    )
    assert REAL_CAPITAL == 0
    assert all(token not in source for token in forbidden)
