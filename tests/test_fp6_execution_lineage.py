from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from test_decision_proof_live_feed import ISSUED_AT, _forecast, _slices
from test_fp4c_settled_funding import _settlement
from test_paper_execution_receipt_v2 import (
    _bound_pretrade,
    _fee,
    _fee_snapshot,
    _orderbook,
    _public_trade,
)
from test_transaction_tape import _sizing
from test_transaction_tape_atomic import _initial_state

from crypto_signal.paper.epoch2_accounting import (
    build_consolidated_epoch2_snapshot,
    build_epoch2_vault_accounting_snapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution_depth_v2 import simulate_depth_execution
from crypto_signal.paper.execution_limit_v2 import simulate_passive_limit_execution
from crypto_signal.paper.execution_receipt_v2 import (
    ExecutionReceiptV2,
    build_execution_receipt_v2,
)
from crypto_signal.paper.funding_cost_v2 import (
    PaperFundingSide,
    project_paper_funding_cost,
)
from crypto_signal.paper.instrument_fees_v2 import InstrumentFeeRole
from crypto_signal.paper.models import (
    ExecutionCostAssumptions,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    build_decision_intent,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.r22_execution_lineage import R22ExecutionLineageTape
from crypto_signal.paper.transaction_tape import build_tape_fill, build_tape_intent
from crypto_signal.paper.transaction_tape_atomic import (
    R22Epoch2AtomicTape,
    build_epoch2_accounting_bundle,
)
from crypto_signal.product.decision_proof import build_decision_proof_snapshot
from crypto_signal.product.final_product_read_model import FinalProductReadModel


def _sha(seed: str) -> str:
    from crypto_signal.ledger.serialization import canonical_sha256

    return canonical_sha256({"seed": seed})


def _case_dir(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def _depth_receipt(
    tmp_path: Path,
    *,
    ask_size: str,
) -> tuple[ExecutionReceiptV2, object]:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(ask_size=ask_size)
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    fee = _fee(role=InstrumentFeeRole.TAKER, notional=outcome.fill_notional)
    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
    )
    return receipt, outcome


def _passive_partial_receipt(
    tmp_path: Path,
) -> tuple[ExecutionReceiptV2, object]:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(
        bid_price="99",
        bid_size="0.05",
        ask_price="101",
        ask_size="1",
    )
    trades = (_public_trade(size="0.10"),)
    outcome = simulate_passive_limit_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        limit_price=Decimal(99),
        arrival_book=book,
        public_trades=trades,
        submitted_at_ms=20_100,
        latency_ms=10,
        timeout_ms=100,
        max_book_age_ms=0,
        partial_fills_enabled=True,
        queue_position_proven=True,
    )
    fee = _fee(role=InstrumentFeeRole.MAKER, notional=outcome.fill_notional)
    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
        public_trades=trades,
    )
    return receipt, outcome


def _canonical_r22_bundle_for_receipt(
    tmp_path: Path,
    receipt: ExecutionReceiptV2,
):
    assert receipt.average_fill_price is not None
    epoch2_path, before = _initial_state(tmp_path)
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    sizing_assessment, sizing_result = _sizing()

    # Legacy R22 accounts the quantity that actually changed capital. The V2
    # companion receipt remains the immutable source for requested/unfilled
    # quantity, which is how partial-fill truth is added without rewriting R22.
    decision = build_decision_intent(
        fund_identity=before.activation.activation_identity,
        decided_at_ms=ISSUED_AT + 100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=receipt.filled_quantity,
        reference_price=receipt.average_fill_price,
        reason="FP6 immutable execution-lineage acceptance",
        invalidation_context="exact V2 receipt lineage",
    )
    intent = build_tape_intent(
        before.activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.BUY,
        decided_at_ms=decision.decided_at_ms,
        reason_codes=("fp6_execution_lineage",),
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
    )
    source_fill = build_simulated_fill(
        fund_identity=before.activation.activation_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=ISSUED_AT + 200,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=receipt.filled_quantity,
        reference_price=receipt.average_fill_price,
        simulated_fill_price=receipt.average_fill_price,
        costs=ExecutionCostAssumptions(
            fee_usdt=receipt.fee_usdt,
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
        ),
        venue_reference="fp6-execution-lineage-fixture",
    )

    by_vault = {item.vault_id: item for item in before.vault_snapshots}
    core_before = by_vault[PaperVaultId.CORE]
    cash_after = (
        core_before.cash_usdt
        - receipt.fill_notional_usdt
        - receipt.fee_usdt
    )
    positions_after = (
        PaperPosition(PaperSymbol.BTCUSDT, receipt.filled_quantity),
    )
    mutation = build_position_cash_mutation(
        fund_identity=before.activation.activation_identity,
        source_identity=source_fill.record_identity,
        mutated_at_ms=ISSUED_AT + 210,
        cash_before_usdt=core_before.cash_usdt,
        cash_after_usdt=cash_after,
        positions_before=core_before.positions,
        positions_after=positions_after,
    )
    mark = _sha(f"fp6-lineage-mark-{receipt.receipt_identity}")
    snapshot_at = ISSUED_AT + 300
    core = build_epoch2_vault_accounting_snapshot(
        before.activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=snapshot_at,
        cash_usdt=cash_after,
        positions=positions_after,
        marked_exposure_usdt=receipt.fill_notional_usdt,
        realized_pnl_usdt=core_before.realized_pnl_usdt,
        unrealized_pnl_usdt=core_before.unrealized_pnl_usdt - receipt.fee_usdt,
        fee_usdt=core_before.fee_usdt + receipt.fee_usdt,
        spread_usdt=core_before.spread_usdt,
        slippage_usdt=core_before.slippage_usdt,
        turnover_notional_usdt=(
            core_before.turnover_notional_usdt + receipt.fill_notional_usdt
        ),
        closed_trade_count=core_before.closed_trade_count,
        win_count=core_before.win_count,
        loss_count=core_before.loss_count,
        breakeven_count=core_before.breakeven_count,
        outcome_distribution=core_before.outcome_distribution,
        source_record_identities=(
            intent.intent_identity,
            source_fill.record_identity,
            mutation.record_identity,
            mark,
        ),
        previous=core_before,
    )

    carry = []
    for vault_id in (PaperVaultId.TACTICAL, PaperVaultId.OPPORTUNITY_RESERVE):
        previous = by_vault[vault_id]
        carry.append(
            build_epoch2_vault_accounting_snapshot(
                before.activation,
                vault_id=vault_id,
                snapshot_at_ms=snapshot_at,
                cash_usdt=previous.cash_usdt,
                positions=previous.positions,
                marked_exposure_usdt=previous.marked_exposure_usdt,
                realized_pnl_usdt=previous.realized_pnl_usdt,
                unrealized_pnl_usdt=previous.unrealized_pnl_usdt,
                fee_usdt=previous.fee_usdt,
                spread_usdt=previous.spread_usdt,
                slippage_usdt=previous.slippage_usdt,
                turnover_notional_usdt=previous.turnover_notional_usdt,
                closed_trade_count=previous.closed_trade_count,
                win_count=previous.win_count,
                loss_count=previous.loss_count,
                breakeven_count=previous.breakeven_count,
                outcome_distribution=previous.outcome_distribution,
                source_record_identities=(previous.snapshot_identity,),
                previous=previous,
            )
        )

    after_vaults = (core, *carry)
    parent = build_consolidated_epoch2_snapshot(
        after_vaults,
        previous=before.consolidated_snapshot,
    )
    fill = build_tape_fill(
        intent,
        core_before,
        core,
        fill=source_fill,
        mutation=mutation,
        mark_evidence_identity=mark,
    )
    bundle = build_epoch2_accounting_bundle(
        before,
        intent=intent,
        fill=fill,
        after_vaults=after_vaults,
        after_consolidated=parent,
    )
    tape = R22Epoch2AtomicTape(epoch2_path)
    assert tape.append_accounting_bundle(
        before,
        intent=intent,
        fill=fill,
        after_vaults=after_vaults,
        after_consolidated=parent,
        bundle=bundle,
    )
    return epoch2_path, fill, bundle


def _passport(epoch2_path: Path, bundle_identity: str):
    return FinalProductReadModel(
        stream_ledger_path=epoch2_path.parent / "missing-stream.sqlite3",
        epoch2_path=epoch2_path,
    ).trade_passport(bundle_identity=bundle_identity, include_audit=True)


def test_partial_fill_is_bound_to_canonical_r22_and_projected_exactly(
    tmp_path: Path,
) -> None:
    receipt, outcome = _depth_receipt(
        _case_dir(tmp_path, "partial-receipt"),
        ask_size="0.05",
    )
    epoch2_path, fill, bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "partial-r22"),
        receipt,
    )
    lineage = R22ExecutionLineageTape(epoch2_path)

    assert receipt.requested_quantity == Decimal("0.10")
    assert receipt.filled_quantity == Decimal("0.05")
    assert receipt.unfilled_quantity == Decimal("0.05")
    assert fill.quantity == receipt.filled_quantity
    assert lineage.append_execution(
        bundle_identity=bundle.bundle_identity,
        receipt=receipt,
        outcome=outcome,
    )
    assert not lineage.append_execution(
        bundle_identity=bundle.bundle_identity,
        receipt=receipt,
        outcome=outcome,
    )

    view = _passport(epoch2_path, bundle.bundle_identity)
    assert view.execution_lineage is not None
    assert view.execution_lineage.execution_receipt_identity == receipt.receipt_identity
    assert view.execution_lineage.execution_outcome_identity == outcome.outcome_identity
    assert view.execution_lineage.requested_quantity == "0.1"
    assert view.execution_lineage.filled_quantity == "0.05"
    assert view.execution_lineage.unfilled_quantity == "0.05"
    assert view.execution_lineage.partial_fills_enabled is True
    assert view.execution_lineage.latency_ms is None
    assert view.execution_lineage.visible_queue_ahead_quantity is None
    assert view.execution_lineage.queue_consumed_quantity is None
    assert view.execution_lineage.real_capital == 0


def test_passive_limit_latency_and_queue_survive_r22_and_trade_passport(
    tmp_path: Path,
) -> None:
    receipt, outcome = _passive_partial_receipt(
        _case_dir(tmp_path, "passive-receipt")
    )
    epoch2_path, _, bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "passive-r22"),
        receipt,
    )
    lineage = R22ExecutionLineageTape(epoch2_path)
    assert lineage.append_execution(
        bundle_identity=bundle.bundle_identity,
        receipt=receipt,
        outcome=outcome,
    )

    view = _passport(epoch2_path, bundle.bundle_identity)
    assert view.execution_lineage is not None
    assert receipt.status.value == "partial"
    assert view.execution_lineage.mode == "passive_limit"
    assert view.execution_lineage.status == "partial"
    assert view.execution_lineage.latency_ms == 10
    assert view.execution_lineage.visible_queue_ahead_quantity == "0.05"
    assert view.execution_lineage.queue_consumed_quantity == "0.05"
    assert view.execution_lineage.filled_quantity == "0.05"
    assert view.execution_lineage.unfilled_quantity == "0.05"


def test_funding_projection_identities_survive_r22_and_trade_passport(
    tmp_path: Path,
) -> None:
    receipt, outcome = _depth_receipt(
        _case_dir(tmp_path, "funding-receipt"),
        ask_size="0.10",
    )
    epoch2_path, fill, bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "funding-r22"),
        receipt,
    )
    lineage = R22ExecutionLineageTape(epoch2_path)
    assert lineage.append_execution(
        bundle_identity=bundle.bundle_identity,
        receipt=receipt,
        outcome=outcome,
    )

    settlement_at = fill.snapshot_at_ms - 20
    settlement = _settlement(
        funding_rate="0.001",
        settlement_at_ms=settlement_at,
        source_timestamp_ms=settlement_at + 1,
        ingested_at_ms=settlement_at + 2,
    )
    mark_identity = _sha("fp6-funding-mark")
    projection = project_paper_funding_cost(
        side=PaperFundingSide.LONG,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=receipt.filled_quantity,
        settlement=settlement,
        mark_price=Decimal(100),
        mark_evidence_identity=mark_identity,
        mark_at_ms=settlement.settlement_at_ms,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )
    assert lineage.append_funding(
        bundle_identity=bundle.bundle_identity,
        projection=projection,
    )
    assert not lineage.append_funding(
        bundle_identity=bundle.bundle_identity,
        projection=projection,
    )

    view = _passport(epoch2_path, bundle.bundle_identity)
    assert view.execution_lineage is not None
    assert len(view.execution_lineage.funding_projections) == 1
    funding = view.execution_lineage.funding_projections[0]
    assert funding.projection_identity == projection.projection_identity
    assert funding.settlement_identity == settlement.settlement_identity
    assert funding.settlement_at_ms == settlement.settlement_at_ms
    assert funding.mark_evidence_identity == mark_identity
    assert funding.mark_price == "100"
    assert funding.cash_flow_usdt == "-0.005"


def test_execution_lineage_rejects_mismatch_and_sql_rewrite(
    tmp_path: Path,
) -> None:
    partial_receipt, partial_outcome = _depth_receipt(
        _case_dir(tmp_path, "mismatch-partial"),
        ask_size="0.05",
    )
    full_receipt, full_outcome = _depth_receipt(
        _case_dir(tmp_path, "mismatch-full"),
        ask_size="0.10",
    )
    epoch2_path, _, bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "mismatch-r22"),
        partial_receipt,
    )
    lineage = R22ExecutionLineageTape(epoch2_path)

    with pytest.raises(ValueError, match="fill quantity"):
        lineage.append_execution(
            bundle_identity=bundle.bundle_identity,
            receipt=full_receipt,
            outcome=full_outcome,
        )

    assert lineage.append_execution(
        bundle_identity=bundle.bundle_identity,
        receipt=partial_receipt,
        outcome=partial_outcome,
    )
    with sqlite3.connect(epoch2_path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="immutable R22 execution lineage"):
            connection.execute(
                "UPDATE r22_execution_lineage SET execution_receipt_identity = ?",
                (_sha("forged-receipt"),),
            )
        with pytest.raises(sqlite3.DatabaseError, match="immutable R22 execution lineage"):
            connection.execute("DELETE FROM r22_execution_lineage")


def test_historical_passport_does_not_change_when_later_execution_truth_exists(
    tmp_path: Path,
) -> None:
    old_receipt, old_outcome = _depth_receipt(
        _case_dir(tmp_path, "history-old-receipt"),
        ask_size="0.05",
    )
    old_epoch2, _, old_bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "history-old-r22"),
        old_receipt,
    )
    old_lineage = R22ExecutionLineageTape(old_epoch2)
    assert old_lineage.append_execution(
        bundle_identity=old_bundle.bundle_identity,
        receipt=old_receipt,
        outcome=old_outcome,
    )
    before = _passport(old_epoch2, old_bundle.bundle_identity)

    later_receipt, later_outcome = _passive_partial_receipt(
        _case_dir(tmp_path, "history-later-receipt")
    )
    later_epoch2, _, later_bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "history-later-r22"),
        later_receipt,
    )
    later_lineage = R22ExecutionLineageTape(later_epoch2)
    assert later_lineage.append_execution(
        bundle_identity=later_bundle.bundle_identity,
        receipt=later_receipt,
        outcome=later_outcome,
    )
    settlement = _settlement()
    later_funding = project_paper_funding_cost(
        side=PaperFundingSide.LONG,
        symbol=PaperSymbol.BTCUSDT,
        position_quantity=later_receipt.filled_quantity,
        settlement=settlement,
        mark_price=Decimal(100),
        mark_evidence_identity=_sha("history-later-funding-mark"),
        mark_at_ms=settlement.settlement_at_ms,
        evaluation_cutoff_ms=settlement.ingested_at_ms,
    )
    assert later_lineage.append_funding(
        bundle_identity=later_bundle.bundle_identity,
        projection=later_funding,
    )

    after = _passport(old_epoch2, old_bundle.bundle_identity)
    assert after == before
    assert after.execution_lineage is not None
    assert after.execution_lineage.execution_receipt_identity == old_receipt.receipt_identity
    assert after.execution_lineage.execution_outcome_identity == old_outcome.outcome_identity
    assert after.execution_lineage.funding_projections == ()


def test_legacy_r22_bundle_without_lineage_never_recomputes_current_v2_truth(
    tmp_path: Path,
) -> None:
    receipt, _ = _depth_receipt(
        _case_dir(tmp_path, "legacy-current-receipt"),
        ask_size="0.10",
    )
    epoch2_path, _, bundle = _canonical_r22_bundle_for_receipt(
        _case_dir(tmp_path, "legacy-r22"),
        receipt,
    )

    view = _passport(epoch2_path, bundle.bundle_identity)
    assert view.execution_lineage is None
    assert view.real_capital == 0
