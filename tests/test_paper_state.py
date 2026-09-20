"""Focused tests for paper-fund state reconstruction."""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper import state as paper_state
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    INITIAL_CASH_USDT,
    REAL_CAPITAL,
    ExecutionCostAssumptions,
    FundCreationRecord,
    NavSnapshotRecord,
    PaperAction,
    PaperSymbol,
    PositionCashMutationRecord,
    SimulatedFillRecord,
    build_decision_intent,
    build_fund_creation,
    build_nav_snapshot,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.state import (
    PaperFundState,
    PaperStateReconstructionError,
    reconstruct_paper_fund_state,
)


def _append_valid_buy_chain(
    ledger: PaperFundLedger,
) -> tuple[
    FundCreationRecord,
    object,
    SimulatedFillRecord,
    PositionCashMutationRecord,
    NavSnapshotRecord,
]:
    fund = build_fund_creation(created_at_ms=1_000)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=1_100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        reason="small virtual allocation",
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
    ledger.append_fund_creation(fund)
    ledger.append_decision_intent(decision)
    ledger.append_simulated_fill(fill)
    ledger.append_position_cash_mutation(mutation)
    ledger.append_nav_snapshot(snapshot)
    return fund, decision, fill, mutation, snapshot


def test_reconstruct_pristine_100_usdt_state(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "pristine.sqlite3")
    fund = build_fund_creation(created_at_ms=42)
    ledger.append_fund_creation(fund)

    state = reconstruct_paper_fund_state(ledger)

    assert isinstance(state, PaperFundState)
    assert state.fund_identity == fund.record_identity
    assert state.cash_usdt == Decimal("100.00")
    assert state.cash_usdt == INITIAL_CASH_USDT
    assert state.positions == ()
    assert state.real_capital == 0
    assert state.real_capital == REAL_CAPITAL
    assert state.last_mutation_identity is None
    assert state.latest_nav_snapshot is None
    assert state.replayed_record_count == 1


def test_replay_valid_buy_mutation(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "buy.sqlite3")
    fund, _decision, fill, mutation, snapshot = _append_valid_buy_chain(ledger)

    state = reconstruct_paper_fund_state(ledger)

    assert state.fund_identity == fund.record_identity
    assert state.cash_usdt == Decimal("49.93")
    assert len(state.positions) == 1
    assert state.positions[0].symbol is PaperSymbol.BTCUSDT
    assert state.positions[0].quantity == Decimal("0.001")
    assert state.last_mutation_identity == mutation.record_identity
    assert state.last_mutation_at_ms == mutation.mutated_at_ms
    assert state.latest_nav_snapshot == snapshot
    assert state.latest_nav_snapshot is not None
    assert state.latest_nav_snapshot.nav_usdt == Decimal("99.94")
    # Fill identity was a valid source; accounting state is independent of NAV marks.
    assert fill.record_identity == mutation.source_identity


def test_reject_discontinuous_cash_position_lineage(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "discontinuous.sqlite3")
    fund = build_fund_creation(created_at_ms=1)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.BUY,
        symbol=PaperSymbol.ETHUSDT,
        quantity=Decimal("0.01"),
        reference_price=Decimal(3000),
        reason="attempted buy",
        invalidation_context="invalidation",
    )
    fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.ETHUSDT,
        quantity=Decimal("0.01"),
        reference_price=Decimal(3000),
        simulated_fill_price=Decimal(3001),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.01"),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
        ),
        venue_reference="simulated:spot:reference",
    )
    bad_mutation = build_position_cash_mutation(
        fund_identity=fund.record_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=4,
        cash_before_usdt=Decimal("90.00"),  # not equal to pristine 100.00
        cash_after_usdt=Decimal("60.00"),
        positions_before=(),
        positions_after={PaperSymbol.ETHUSDT: Decimal("0.01")},
    )
    ledger.append_fund_creation(fund)
    ledger.append_decision_intent(decision)
    ledger.append_simulated_fill(fill)
    ledger.append_position_cash_mutation(bad_mutation)

    with pytest.raises(PaperStateReconstructionError, match="discontinuous cash"):
        reconstruct_paper_fund_state(ledger)

    ledger2 = PaperFundLedger(tmp_path / "discontinuous_pos.sqlite3")
    fund2 = build_fund_creation(created_at_ms=10)
    decision2 = build_decision_intent(
        fund_identity=fund2.record_identity,
        decided_at_ms=11,
        action=PaperAction.BUY,
        symbol=PaperSymbol.SOLUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        reason="attempted buy",
        invalidation_context="invalidation",
    )
    fill2 = build_simulated_fill(
        fund_identity=fund2.record_identity,
        decision_identity=decision2.record_identity,
        filled_at_ms=12,
        action=PaperAction.BUY,
        symbol=PaperSymbol.SOLUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        simulated_fill_price=Decimal(100),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal(0),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
        ),
        venue_reference="simulated:spot:reference",
    )
    bad_positions = build_position_cash_mutation(
        fund_identity=fund2.record_identity,
        source_identity=fill2.record_identity,
        mutated_at_ms=13,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("0.00"),
        positions_before={PaperSymbol.BTCUSDT: Decimal("0.001")},
        positions_after={PaperSymbol.SOLUSDT: Decimal(1)},
    )
    ledger2.append_fund_creation(fund2)
    ledger2.append_decision_intent(decision2)
    ledger2.append_simulated_fill(fill2)
    ledger2.append_position_cash_mutation(bad_positions)

    with pytest.raises(
        PaperStateReconstructionError, match="discontinuous position"
    ):
        reconstruct_paper_fund_state(ledger2)


def test_reject_fill_that_sources_another_fill_as_decision(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "fill_source_type.sqlite3")
    fund = build_fund_creation(created_at_ms=1)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(20000),
        reason="first decision",
        invalidation_context="first invalidation",
    )
    costs = ExecutionCostAssumptions(
        fee_usdt=Decimal("0.01"),
        spread_usdt=Decimal("0.01"),
        slippage_usdt=Decimal("0.01"),
    )
    first_fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(20000),
        simulated_fill_price=Decimal(20001),
        costs=costs,
        venue_reference="simulated:test",
    )
    bad_fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=first_fill.record_identity,
        filled_at_ms=4,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(20000),
        simulated_fill_price=Decimal(20001),
        costs=costs,
        venue_reference="simulated:test",
    )
    ledger.append_fund_creation(fund)
    ledger.append_decision_intent(decision)
    ledger.append_simulated_fill(first_fill)
    ledger.append_simulated_fill(bad_fill)
    with pytest.raises(PaperStateReconstructionError, match="wrong type"):
        reconstruct_paper_fund_state(ledger)


def test_reject_fill_semantically_divergent_from_source_decision(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "fill_mismatch.sqlite3")
    fund = build_fund_creation(created_at_ms=1)
    decision = build_decision_intent(
        fund_identity=fund.record_identity,
        decided_at_ms=2,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(20000),
        reason="decision",
        invalidation_context="invalidation",
    )
    fill = build_simulated_fill(
        fund_identity=fund.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=3,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.002"),
        reference_price=Decimal(20000),
        simulated_fill_price=Decimal(20001),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.01"),
            spread_usdt=Decimal("0.01"),
            slippage_usdt=Decimal("0.01"),
        ),
        venue_reference="simulated:test",
    )
    ledger.append_fund_creation(fund)
    ledger.append_decision_intent(decision)
    ledger.append_simulated_fill(fill)
    with pytest.raises(PaperStateReconstructionError, match="does not match"):
        reconstruct_paper_fund_state(ledger)


def test_reject_cross_fund_and_source_lineage(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "cross_fund.sqlite3")
    fund_a = build_fund_creation(created_at_ms=1)
    fund_b = build_fund_creation(created_at_ms=2)
    decision_b = build_decision_intent(
        fund_identity=fund_b.record_identity,
        decided_at_ms=3,
        action=PaperAction.HOLD_CASH,
        reason="other fund hold",
        invalidation_context="n/a",
    )
    ledger.append_fund_creation(fund_a)
    ledger.append_decision_intent(decision_b)

    with pytest.raises(PaperStateReconstructionError, match="cross-fund decision"):
        reconstruct_paper_fund_state(ledger)

    ledger2 = PaperFundLedger(tmp_path / "cross_source.sqlite3")
    fund = build_fund_creation(created_at_ms=5)
    foreign_decision = build_decision_intent(
        fund_identity=fund_b.record_identity,
        decided_at_ms=6,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(50000),
        reason="foreign",
        invalidation_context="n/a",
    )
    # Mutation claims fund A but sources an identity never recorded for this fund.
    orphan_mutation = build_position_cash_mutation(
        fund_identity=fund.record_identity,
        source_identity=foreign_decision.record_identity,
        mutated_at_ms=7,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("100.00"),
        positions_before=(),
        positions_after=(),
    )
    ledger2.append_fund_creation(fund)
    ledger2.append_position_cash_mutation(orphan_mutation)

    with pytest.raises(
        PaperStateReconstructionError, match="source identity is missing"
    ):
        reconstruct_paper_fund_state(ledger2)


def test_empty_ledger_and_second_creation_rejected(tmp_path: Path) -> None:
    empty = PaperFundLedger(tmp_path / "empty.sqlite3")
    empty.initialize()
    with pytest.raises(PaperStateReconstructionError, match="empty ledger"):
        reconstruct_paper_fund_state(empty)

    ledger = PaperFundLedger(tmp_path / "two_funds.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    ledger.append_fund_creation(build_fund_creation(created_at_ms=2))
    with pytest.raises(
        PaperStateReconstructionError, match="exactly one fund creation"
    ):
        reconstruct_paper_fund_state(ledger)


def test_reconstruction_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "readonly.sqlite3"
    ledger = PaperFundLedger(path)
    fund = build_fund_creation(created_at_ms=9)
    ledger.append_fund_creation(fund)
    before = ledger.replay()

    state = reconstruct_paper_fund_state(ledger)
    after = ledger.replay()

    assert state.cash_usdt == Decimal("100.00")
    assert [entry.record_identity for entry in before] == [
        entry.record_identity for entry in after
    ]
    assert len(after) == 1


def test_real_capital_and_no_order_surface() -> None:
    assert REAL_CAPITAL == 0
    assert paper_state.REAL_CAPITAL == 0

    forbidden = {
        "place_order",
        "submit_order",
        "cancel_order",
        "exchange_order",
        "api_key",
        "api_secret",
        "credentials",
        "append_fund_creation",
        "append_decision_intent",
    }
    names = set(dir(paper_state))
    for name in forbidden:
        assert name not in names

    public_fns = [
        name
        for name, member in inspect.getmembers(
            paper_state, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    ]
    assert "reconstruct_paper_fund_state" in public_fns
    assert all(
        "order" not in name and "exchange" not in name and "credential" not in name
        for name in public_fns
    )
