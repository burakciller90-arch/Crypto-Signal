from __future__ import annotations

import sqlite3
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import pytest
from test_canonical_capital_runtime import (
    _capital_inputs,
    _execution_snapshot,
    _sha,
)
from test_decision_proof_live_feed import ISSUED_AT, _forecast, _slices
from test_transaction_tape_atomic import _initial_state

from crypto_signal.paper.canonical_capital_outcomes import (
    CanonicalCapitalFinancialOutcome,
    reconstruct_open_cost_basis,
)
from crypto_signal.paper.canonical_capital_runtime import (
    commit_canonical_paper_buy,
    commit_canonical_paper_sell,
)
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.decision_proof import build_decision_proof_snapshot


def _open_core_position(tmp_path: Path):
    epoch2_path, state = _initial_state(tmp_path)
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    core = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, eligibility = _capital_inputs(PaperVaultId.CORE)
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=core,
        selected_at_ms=ISSUED_AT + 10,
    )
    buy = commit_canonical_paper_buy(
        epoch2_path=epoch2_path,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        symbol=PaperSymbol.BTCUSDT,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("sell-entry-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("sell-entry-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 20,
        filled_at_ms=ISSUED_AT + 30,
        mutated_at_ms=ISSUED_AT + 31,
        snapshot_at_ms=ISSUED_AT + 40,
    )
    return epoch2_path, forecast, proof, assessment, buy


def _half_step_quantity(quantity: Decimal) -> Decimal:
    step = Decimal("0.0001")
    steps = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    half_steps = int(steps) // 2
    if half_steps <= 0:
        raise AssertionError("test position is too small to reduce")
    result = Decimal(half_steps) * step
    if result >= quantity:
        raise AssertionError("test reduction must leave a position")
    return result


def test_s11_buy_reduce_exit_reconstructs_cost_basis_and_closes_flat(
    tmp_path: Path,
) -> None:
    epoch2_path, forecast, proof, assessment, buy = _open_core_position(tmp_path)
    after_buy = Epoch2CanonicalLedger(epoch2_path).read_state()
    core_buy = next(
        item for item in after_buy.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    open_quantity = core_buy.positions[0].quantity
    reduce_quantity = _half_step_quantity(open_quantity)

    reduced = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.REDUCE,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=reduce_quantity,
        reference_price=Decimal(105),
        reference_price_evidence_identity=_sha("reduce-reference"),
        exit_evidence_identity=_sha("reduce-exit-evidence"),
        exit_reason_codes=("partial_risk_reduction",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(105)},
        mark_evidence_identity=_sha("reduce-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 120,
        filled_at_ms=ISSUED_AT + 130,
        mutated_at_ms=ISSUED_AT + 131,
        snapshot_at_ms=ISSUED_AT + 140,
    )

    assert reduced.action is PaperAction.REDUCE
    assert (
        reduced.financial_outcome
        is CanonicalCapitalFinancialOutcome.PARTIAL_REDUCTION
    )
    assert reduced.realized_pnl_delta_usdt > 0
    state_after_reduce = Epoch2CanonicalLedger(epoch2_path).read_state()
    core_reduce = next(
        item for item in state_after_reduce.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assert core_reduce.positions[0].quantity == open_quantity - reduce_quantity
    assert core_reduce.closed_trade_count == 1
    assert core_reduce.win_count == 1
    assert core_reduce.realized_pnl_usdt == reduced.realized_pnl_delta_usdt
    assert reduced.outcome_identity in core_reduce.source_record_identities

    exited = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.EXIT,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=None,
        reference_price=Decimal(110),
        reference_price_evidence_identity=_sha("exit-reference"),
        exit_evidence_identity=_sha("exit-outcome-evidence"),
        exit_reason_codes=("forecast_lifecycle_exit",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(110)},
        mark_evidence_identity=_sha("exit-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 220,
        filled_at_ms=ISSUED_AT + 230,
        mutated_at_ms=ISSUED_AT + 231,
        snapshot_at_ms=ISSUED_AT + 240,
    )

    assert exited.action is PaperAction.EXIT
    assert exited.financial_outcome is CanonicalCapitalFinancialOutcome.CLOSED_WIN
    assert exited.realized_pnl_delta_usdt > 0

    final = Epoch2CanonicalLedger(epoch2_path).read_state()
    core_final = next(
        item for item in final.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assert core_final.positions == ()
    assert core_final.closed_trade_count == 2
    assert core_final.win_count == 2
    assert core_final.loss_count == 0
    assert core_final.breakeven_count == 0
    assert core_final.outcome_distribution == (("WIN", 2),)
    assert core_final.realized_pnl_usdt == (
        reduced.realized_pnl_delta_usdt + exited.realized_pnl_delta_usdt
    )
    assert core_final.unrealized_pnl_usdt == 0

    tape = R22Epoch2AtomicTape(epoch2_path)
    assert tape.audit_all_read_only() == (3, 3, 3)
    exit_context = tape.read_bundle_story_context(
        exited.accounting_bundle_identity
    )
    assert exit_context["outcome"]["outcome_identity"] == exited.outcome_identity
    assert exit_context["fill"]["financial_outcome"] == "CLOSED_WIN"
    assert buy.fill_identity in exit_context["outcome"]["prior_fill_identities"]
    assert reduced.fill_identity in exit_context["outcome"]["prior_fill_identities"]

    with sqlite3.connect(epoch2_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM s11_capital_outcome_evidence"
        ).fetchone() == (2,)



def test_s11_multi_buy_weighted_average_reduce_exit_has_no_decimal_residual(
    tmp_path: Path,
) -> None:
    epoch2_path, forecast, proof, assessment, _ = _open_core_position(tmp_path)
    after_first = Epoch2CanonicalLedger(epoch2_path).read_state()
    core_after_first = next(
        item for item in after_first.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    second_assessment, second_eligibility = _capital_inputs(PaperVaultId.CORE)
    assert second_assessment.assessment_identity == assessment.assessment_identity
    second_selection = promote_fixed_fractional_sizing(
        second_assessment,
        current_vault=core_after_first,
        selected_at_ms=ISSUED_AT + 60,
    )
    second_buy = commit_canonical_paper_buy(
        epoch2_path=epoch2_path,
        forecast=forecast,
        proof=proof,
        sizing_assessment=second_assessment,
        sizing_selection=second_selection,
        eligibility_proof=second_eligibility,
        symbol=PaperSymbol.BTCUSDT,
        reference_price=Decimal(102),
        reference_price_evidence_identity=_sha("multi-buy-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(102)},
        mark_evidence_identity=_sha("multi-buy-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 70,
        filled_at_ms=ISSUED_AT + 80,
        mutated_at_ms=ISSUED_AT + 81,
        snapshot_at_ms=ISSUED_AT + 90,
    )
    assert second_buy.inserted is True

    history = R22Epoch2AtomicTape(epoch2_path).read_trade_history(
        PaperVaultId.CORE,
        PaperSymbol.BTCUSDT,
    )
    basis = reconstruct_open_cost_basis(
        history,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
    )
    assert len(basis.prior_fill_identities) == 2
    assert (
        basis.average_cost_per_unit_usdt
        == basis.remaining_cost_basis_usdt / basis.open_quantity
    )

    reduce_quantity = _half_step_quantity(basis.open_quantity)
    reduced = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.REDUCE,
        forecast=forecast,
        proof=proof,
        sizing_assessment=second_assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=reduce_quantity,
        reference_price=Decimal(106),
        reference_price_evidence_identity=_sha("multi-reduce-reference"),
        exit_evidence_identity=_sha("multi-reduce-evidence"),
        exit_reason_codes=("multi_entry_partial_reduce",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(106)},
        mark_evidence_identity=_sha("multi-reduce-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 120,
        filled_at_ms=ISSUED_AT + 130,
        mutated_at_ms=ISSUED_AT + 131,
        snapshot_at_ms=ISSUED_AT + 140,
    )
    assert reduced.action is PaperAction.REDUCE

    history_after_reduce = R22Epoch2AtomicTape(epoch2_path).read_trade_history(
        PaperVaultId.CORE,
        PaperSymbol.BTCUSDT,
    )
    remaining = reconstruct_open_cost_basis(
        history_after_reduce,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
    )
    assert remaining.open_quantity == basis.open_quantity - reduce_quantity
    assert (
        remaining.average_cost_per_unit_usdt
        == remaining.remaining_cost_basis_usdt / remaining.open_quantity
    )

    exited = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.EXIT,
        forecast=forecast,
        proof=proof,
        sizing_assessment=second_assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=None,
        reference_price=Decimal(108),
        reference_price_evidence_identity=_sha("multi-exit-reference"),
        exit_evidence_identity=_sha("multi-exit-evidence"),
        exit_reason_codes=("multi_entry_close",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(108)},
        mark_evidence_identity=_sha("multi-exit-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 220,
        filled_at_ms=ISSUED_AT + 230,
        mutated_at_ms=ISSUED_AT + 231,
        snapshot_at_ms=ISSUED_AT + 240,
    )
    assert exited.action is PaperAction.EXIT

    final = Epoch2CanonicalLedger(epoch2_path).read_state()
    core_final = next(
        item for item in final.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assert core_final.positions == ()
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == (4, 4, 4)


def test_s11_reduce_cannot_flatten_and_exit_cannot_be_partial(tmp_path: Path) -> None:
    epoch2_path, forecast, proof, assessment, _ = _open_core_position(tmp_path)
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    quantity = core.positions[0].quantity

    base = {
        "epoch2_path": epoch2_path,
        "forecast": forecast,
        "proof": proof,
        "sizing_assessment": assessment,
        "symbol": PaperSymbol.BTCUSDT,
        "reference_price": Decimal(105),
        "reference_price_evidence_identity": _sha("sell-guard-reference"),
        "exit_evidence_identity": _sha("sell-guard-exit"),
        "exit_reason_codes": ("guard_test",),
        "mark_prices": {PaperSymbol.BTCUSDT: Decimal(105)},
        "mark_evidence_identity": _sha("sell-guard-mark"),
        "execution_snapshot": _execution_snapshot(),
        "decided_at_ms": ISSUED_AT + 120,
        "filled_at_ms": ISSUED_AT + 130,
        "mutated_at_ms": ISSUED_AT + 131,
        "snapshot_at_ms": ISSUED_AT + 140,
    }

    with pytest.raises(ValueError, match="REDUCE must leave"):
        commit_canonical_paper_sell(
            action=PaperAction.REDUCE,
            quantity=quantity,
            **base,
        )

    with pytest.raises(ValueError, match="EXIT quantity"):
        commit_canonical_paper_sell(
            action=PaperAction.EXIT,
            quantity=_half_step_quantity(quantity),
            **base,
        )


def test_s11_sell_outcome_table_is_physically_immutable(tmp_path: Path) -> None:
    epoch2_path, forecast, proof, assessment, _ = _open_core_position(tmp_path)
    commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.EXIT,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=None,
        reference_price=Decimal(105),
        reference_price_evidence_identity=_sha("immutable-exit-reference"),
        exit_evidence_identity=_sha("immutable-exit-evidence"),
        exit_reason_codes=("immutable_exit",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(105)},
        mark_evidence_identity=_sha("immutable-exit-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 120,
        filled_at_ms=ISSUED_AT + 130,
        mutated_at_ms=ISSUED_AT + 131,
        snapshot_at_ms=ISSUED_AT + 140,
    )

    with (
        sqlite3.connect(epoch2_path) as connection,
        pytest.raises(
            sqlite3.DatabaseError,
            match="immutable R22 Epoch2 audit tape",
        ),
    ):
        connection.execute(
            "UPDATE s11_capital_outcome_evidence SET vault_id = 'TACTICAL'"
        )
