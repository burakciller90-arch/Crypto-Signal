from __future__ import annotations

import sqlite3
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import pytest
from test_autopilot_forward_runtime import _paths
from test_autopilot_forward_sizing import (
    _current_vault,
    _front,
    _policy,
    _risk,
    _selected_at_ms,
    _sha,
)
from test_canonical_capital_runtime import _execution_snapshot
from test_immutable_forecast_stream import _event_context

from crypto_signal.paper.autopilot_forward_runtime import (
    CanonicalPaperAutopilotForwardRuntime,
)
from crypto_signal.paper.autopilot_forward_actions import (
    FP3ActionProcessDisposition,
    FP3ActionReason,
    FP3ActionStageStatus,
    FP3ActionStageStore,
    FP3PreregisteredActionBridge,
    build_fp3_action_intent,
)
from crypto_signal.paper.autopilot_forward_sizing import (
    FP3EligibleFixedFractionalSizingBridge,
)
from crypto_signal.paper.canonical_capital_runtime import commit_canonical_paper_buy
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.canonical_vault_eligibility import promote_vault_eligibility
from crypto_signal.paper.capital_science_bridge import assess_unified_decision_capital
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol
from crypto_signal.paper.position_sizing_intelligence import (
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital_forward_evidence import (
    build_capital_forward_auxiliary_evidence,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)


def _sized_chain(tmp_path: Path):
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    IntelligenceStreamForwardRuntime(stream_path).project_issuance(issuance)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    front_runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    front_runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms,
    )
    front_result = front_runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 5,
    )
    assert front_result.receipt is not None
    front = front_result.receipt
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    sizing_bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    sized = sizing_bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
    )
    assert sized.receipt is not None
    assert sized.receipt.selection_identity is not None
    assert sized.receipt.sizing_event_identity is not None

    auxiliary = build_capital_forward_auxiliary_evidence(
        issuance,
        event_context=_event_context(),
    )
    capital = assess_unified_decision_capital(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=front.assessed_at_ms,
        tactical_microstructure=auxiliary.tactical,
        opportunity_recovery=auxiliary.opportunity,
    )
    eligibility = promote_vault_eligibility(
        capital.candidate,
        capital.allocation,
        vault_id=PaperVaultId.CORE,
    )
    envelope = next(
        item
        for item in capital.allocation.vaults
        if item.vault_id is PaperVaultId.CORE
    )
    current = _current_vault(epoch2_path, PaperVaultId.CORE)
    sources = tuple(
        sorted(
            {
                *risk.source_evidence_identities,
                risk.risk_input_identity,
                eligibility.proof_identity,
                current.snapshot_identity,
            }
        )
    )
    context = build_position_sizing_risk_context(
        vault_id=PaperVaultId.CORE,
        asset=risk.asset,
        as_of_ms=risk.as_of_ms,
        allocator_assessment_identity=front.allocator_assessment_identity,
        allocator_candidate_identity=front.allocator_candidate_identity,
        expected_win_r=risk.expected_win_r,
        expected_loss_r=risk.expected_loss_r,
        transaction_cost_r=risk.transaction_cost_r,
        absolute_correlation_0_1=risk.absolute_correlation_0_1,
        current_drawdown_fraction=risk.current_drawdown_fraction,
        volatility_fraction=risk.volatility_fraction,
        liquidity_score_0_1=risk.liquidity_score_0_1,
        source_evidence_identities=sources,
    )
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=envelope,
        context=context,
    )
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=current,
        selected_at_ms=selected_at_ms,
    )
    assert assessment.assessment_identity == sized.receipt.sizing_assessment_identity
    assert selection.selection_identity == sized.receipt.selection_identity
    assert selection.sizing_result_identity == sized.receipt.fixed_fractional_result_identity

    return (
        epoch2_path,
        stream_path,
        autopilot_path,
        issuance,
        front,
        risk,
        sized.receipt,
        assessment,
        selection,
        eligibility,
    )


def _action_bridge(
    *,
    epoch2_path: Path,
    stream_path: Path,
    autopilot_path: Path,
) -> FP3PreregisteredActionBridge:
    return FP3PreregisteredActionBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )


def _open_intent(front, sizing, issuance, *, requested_at_ms: int):
    assert sizing.sizing_event_identity is not None
    return build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=sizing.receipt_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.OPEN,
        action_evidence_identity=sizing.sizing_event_identity,
        requested_at_ms=requested_at_ms,
    )


def _half_quantity(epoch2_path: Path) -> Decimal:
    current = _current_vault(epoch2_path, PaperVaultId.CORE)
    position = next(
        item for item in current.positions if item.symbol is PaperSymbol.BTCUSDT
    )
    step = Decimal("0.0001")
    steps = (position.quantity / step).to_integral_value(rounding=ROUND_DOWN)
    half_steps = int(steps) // 2
    if half_steps <= 0:
        raise AssertionError("FP3-C test position is too small to reduce")
    return Decimal(half_steps) * step


def test_fp3_c_open_buy_commits_canonical_bundle_and_replays(
    tmp_path: Path,
) -> None:
    (
        epoch2_path,
        stream_path,
        autopilot_path,
        issuance,
        front,
        _,
        sizing,
        assessment,
        selection,
        eligibility,
    ) = _sized_chain(tmp_path)
    requested_at_ms = selection.selected_at_ms + 10
    intent = _open_intent(
        front,
        sizing,
        issuance,
        requested_at_ms=requested_at_ms,
    )
    bridge = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    first = bridge.process_buy(
        intent,
        issuance,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("fp3c-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp3c-open-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=requested_at_ms + 10,
        mutated_at_ms=requested_at_ms + 11,
        snapshot_at_ms=requested_at_ms + 20,
        processed_at_ms=requested_at_ms + 30,
    )
    epoch_after = epoch2_path.read_bytes()
    stream_after = stream_path.read_bytes()

    replay = bridge.process_buy(
        intent,
        issuance,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("fp3c-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp3c-open-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=requested_at_ms + 10,
        mutated_at_ms=requested_at_ms + 11,
        snapshot_at_ms=requested_at_ms + 20,
        processed_at_ms=requested_at_ms + 100,
    )

    assert first.disposition is FP3ActionProcessDisposition.INSERTED
    assert first.receipt.stage_status is FP3ActionStageStatus.COMMITTED
    assert first.receipt.canonical_action is PaperAction.BUY
    assert first.receipt.r22_bundle_identity is not None
    assert first.receipt.outcome_identity is None
    assert first.receipt.real_capital == 0
    assert replay.disposition is FP3ActionProcessDisposition.REPLAYED
    assert replay.receipt == first.receipt
    assert epoch2_path.read_bytes() == epoch_after
    assert stream_path.read_bytes() == stream_after
    assert R22Epoch2AtomicTape(epoch2_path).audit_bundle_read_only(
        first.receipt.r22_bundle_identity
    )["bundle_identity"] == first.receipt.r22_bundle_identity


def test_fp3_c_recovers_buy_after_canonical_commit_before_action_receipt(
    tmp_path: Path,
) -> None:
    (
        epoch2_path,
        stream_path,
        autopilot_path,
        issuance,
        front,
        _,
        sizing,
        assessment,
        selection,
        eligibility,
    ) = _sized_chain(tmp_path)
    requested_at_ms = selection.selected_at_ms + 10
    intent = _open_intent(
        front,
        sizing,
        issuance,
        requested_at_ms=requested_at_ms,
    )
    committed = commit_canonical_paper_buy(
        epoch2_path=epoch2_path,
        forecast=issuance.forecast,
        proof=issuance.proof,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        symbol=PaperSymbol.BTCUSDT,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("fp3c-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp3c-open-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=requested_at_ms,
        filled_at_ms=requested_at_ms + 10,
        mutated_at_ms=requested_at_ms + 11,
        snapshot_at_ms=requested_at_ms + 20,
    )
    assert committed.inserted is True
    assert FP3ActionStageStore(autopilot_path).read(intent.action_intent_identity) is None

    recovered = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    ).process_buy(
        intent,
        issuance,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("fp3c-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp3c-open-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=requested_at_ms + 10,
        mutated_at_ms=requested_at_ms + 11,
        snapshot_at_ms=requested_at_ms + 20,
        processed_at_ms=requested_at_ms + 30,
    )

    assert recovered.disposition is FP3ActionProcessDisposition.RECOVERED
    assert recovered.receipt.r22_bundle_identity == committed.accounting_bundle_identity
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only()[1:] == (1, 1)


def test_fp3_c_wait_and_stop_update_never_mutate_r21_r22(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    bridge = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    before_epoch = epoch2_path.read_bytes()

    wait = build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=None,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.WAIT,
        action_evidence_identity=_sha("fp3c-wait-evidence"),
        requested_at_ms=front.processed_at_ms + 1,
    )
    wait_result = bridge.process_no_trade(
        wait,
        processed_at_ms=wait.requested_at_ms + 1,
    )

    stop_update = build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=None,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.STOP_UPDATE,
        action_evidence_identity=_sha("fp3c-stop-update-evidence"),
        requested_at_ms=front.processed_at_ms + 2,
    )
    unavailable = bridge.process_no_trade(
        stop_update,
        processed_at_ms=stop_update.requested_at_ms + 1,
    )

    assert wait_result.disposition is FP3ActionProcessDisposition.WAITED
    assert wait_result.receipt.stage_status is FP3ActionStageStatus.NO_TRADE
    assert unavailable.disposition is FP3ActionProcessDisposition.UNAVAILABLE
    assert unavailable.receipt.stage_status is FP3ActionStageStatus.UNAVAILABLE
    assert epoch2_path.read_bytes() == before_epoch


def test_fp3_c_scale_in_is_explicitly_unavailable_in_c1(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    bridge = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    before = epoch2_path.read_bytes()
    intent = build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=None,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.SCALE_IN,
        action_evidence_identity=_sha("fp3c-scale-in-unavailable"),
        requested_at_ms=front.processed_at_ms + 1,
    )

    result = bridge.process_no_trade(
        intent,
        processed_at_ms=intent.requested_at_ms + 1,
    )

    assert result.disposition is FP3ActionProcessDisposition.UNAVAILABLE
    assert result.receipt.stage_status is FP3ActionStageStatus.UNAVAILABLE
    assert result.receipt.canonical_action is None
    assert epoch2_path.read_bytes() == before


def test_fp3_c_partial_take_profit_then_close_uses_canonical_sell_lineage(
    tmp_path: Path,
) -> None:
    (
        epoch2_path,
        stream_path,
        autopilot_path,
        issuance,
        front,
        _,
        sizing,
        assessment,
        selection,
        eligibility,
    ) = _sized_chain(tmp_path)
    bridge = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    open_at = selection.selected_at_ms + 10
    opened = bridge.process_buy(
        _open_intent(front, sizing, issuance, requested_at_ms=open_at),
        issuance,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("fp3c-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp3c-open-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=open_at + 10,
        mutated_at_ms=open_at + 11,
        snapshot_at_ms=open_at + 20,
        processed_at_ms=open_at + 30,
    )
    assert opened.receipt.r22_bundle_identity is not None

    reduce_at = open_at + 40
    reduce_intent = build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=sizing.receipt_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.PARTIAL_TAKE_PROFIT,
        action_evidence_identity=_sha("fp3c-partial-tp-evidence"),
        requested_at_ms=reduce_at,
        quantity=_half_quantity(epoch2_path),
    )
    reduced = bridge.process_sell(
        reduce_intent,
        issuance,
        sizing_assessment=assessment,
        reference_price=Decimal(110),
        reference_price_evidence_identity=_sha("fp3c-reduce-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(110)},
        mark_evidence_identity=_sha("fp3c-reduce-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=reduce_at + 10,
        mutated_at_ms=reduce_at + 11,
        snapshot_at_ms=reduce_at + 20,
        processed_at_ms=reduce_at + 30,
    )
    assert reduced.disposition is FP3ActionProcessDisposition.INSERTED
    assert reduced.receipt.canonical_action is PaperAction.REDUCE
    assert reduced.receipt.outcome_identity is not None

    close_at = reduce_at + 40
    close_intent = build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=sizing.receipt_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.CLOSE,
        action_evidence_identity=_sha("fp3c-close-evidence"),
        requested_at_ms=close_at,
    )
    closed = bridge.process_sell(
        close_intent,
        issuance,
        sizing_assessment=assessment,
        reference_price=Decimal(108),
        reference_price_evidence_identity=_sha("fp3c-close-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(108)},
        mark_evidence_identity=_sha("fp3c-close-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=close_at + 10,
        mutated_at_ms=close_at + 11,
        snapshot_at_ms=close_at + 20,
        processed_at_ms=close_at + 30,
    )
    assert closed.disposition is FP3ActionProcessDisposition.INSERTED
    assert closed.receipt.canonical_action is PaperAction.EXIT
    assert closed.receipt.outcome_identity is not None

    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item for item in state.vault_snapshots if item.vault_id is PaperVaultId.CORE
    )
    assert not any(item.symbol is PaperSymbol.BTCUSDT for item in core.positions)


def test_fp3_c_action_receipts_are_physically_immutable(tmp_path: Path) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    intent = build_fp3_action_intent(
        front_receipt_identity=front.receipt_identity,
        sizing_receipt_identity=None,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.WAIT,
        action_evidence_identity=_sha("fp3c-immutable-wait"),
        requested_at_ms=front.processed_at_ms + 1,
    )
    result = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    ).process_no_trade(intent, processed_at_ms=intent.requested_at_ms + 1)

    with sqlite3.connect(autopilot_path) as connection, pytest.raises(
        sqlite3.IntegrityError,
        match="immutable FP3 action stage truth",
    ):
        connection.execute(
            """
            DELETE FROM fp3_paper_autopilot_action_receipts
            WHERE receipt_identity = ?
            """,
            (result.receipt.receipt_identity,),
        )
