from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_autopilot_forward_actions import (
    _action_bridge,
    _sized_chain,
)
from test_autopilot_forward_sizing import (
    _current_vault,
    _policy,
    _risk,
    _selected_at_ms,
    _sha,
)
from test_canonical_capital_runtime import _execution_snapshot
from test_immutable_forecast_stream import AS_OF, HORIZON, ISSUED_AT, _event_context, _signal
from test_unified_decision_runtime import _family_evidence, _preflight

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.intelligence.confluence_matrix_v2 import build_confluence_family_evidence
from crypto_signal.paper.autopilot_forward_actions import (
    FP3ActionProcessDisposition,
    FP3ActionReason,
    build_fp3_action_intent,
)
from crypto_signal.paper.autopilot_forward_runtime import (
    CanonicalPaperAutopilotForwardRuntime,
)
from crypto_signal.paper.autopilot_forward_sizing import (
    FP3EligibleFixedFractionalSizingBridge,
)
from crypto_signal.paper.canonical_capital_outcomes import reconstruct_open_cost_basis
from crypto_signal.paper.canonical_capital_runtime import (
    read_canonical_active_buy_entries,
)
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
from crypto_signal.unified_decision_runtime import issue_unified_decision


def _second_family_evidence(*, as_of_ms: int):
    return tuple(
        build_confluence_family_evidence(
            family=item.family,
            asset=item.asset,
            timeframe=item.timeframe,
            regime=item.regime,
            as_of_ms=as_of_ms,
            state=item.state,
            direction=item.direction,
            directional_strength_0_1=item.directional_strength_0_1,
            evidence_quality_0_1=item.evidence_quality_0_1,
            freshness_0_1=item.freshness_0_1,
            market_available_at_ms=as_of_ms - 20,
            observed_at_ms=as_of_ms - 10,
            source_engine_ids=item.source_engine_ids,
            source_evidence_identities=(
                _sha(f"fp3c2-second-{item.family.value}-source"),
            ),
            material_conflict_identities=item.material_conflict_identities,
            uncertainty_flags=item.uncertainty_flags,
        )
        for item in _family_evidence()
    )


def _second_issuance(tmp_path: Path):
    second_as_of_ms = AS_OF + 10_000
    family = _second_family_evidence(as_of_ms=second_as_of_ms)
    event = _event_context(as_of_ms=second_as_of_ms)
    signal = _signal(as_of_ms=second_as_of_ms)
    return issue_unified_decision(
        signal=signal,
        base_asset="BTC",
        regime="trend_up",
        family_evidence=family,
        event_context=event,
        preflight_proof_slices=_preflight(family, event),
        issued_at_ms=ISSUED_AT + 10_000,
        horizon_bars=HORIZON,
        target_label="target_1",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision-scale-in.sqlite3"),
    )


def _size_existing_issuance(
    *,
    epoch2_path: Path,
    stream_path: Path,
    autopilot_path: Path,
    issuance,
):
    IntelligenceStreamForwardRuntime(stream_path).project_issuance(issuance)
    event_context = _event_context(as_of_ms=issuance.forecast.source_as_of_ms)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    front_runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    front_result = front_runtime.process_issuance(
        issuance,
        event_context=event_context,
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
        event_context=event_context,
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
        event_context=event_context,
    )
    capital = assess_unified_decision_capital(
        issuance,
        event_context=event_context,
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
    assert (
        selection.sizing_result_identity
        == sized.receipt.fixed_fractional_result_identity
    )
    return front, sized.receipt, assessment, selection, eligibility


def test_fp3_c2_scale_in_then_exit_preserves_multi_entry_lineage_and_replays(
    tmp_path: Path,
) -> None:
    (
        epoch2_path,
        stream_path,
        autopilot_path,
        first_issuance,
        first_front,
        _,
        first_sizing,
        first_assessment,
        first_selection,
        first_eligibility,
    ) = _sized_chain(tmp_path)
    bridge = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    open_at = first_selection.selected_at_ms + 10
    assert first_sizing.sizing_event_identity is not None
    opened = bridge.process_buy(
        build_fp3_action_intent(
            front_receipt_identity=first_front.receipt_identity,
            sizing_receipt_identity=first_sizing.receipt_identity,
            forecast_identity=first_issuance.forecast.forecast_identity,
            proof_identity=first_issuance.proof.proof_identity,
            vault_id=PaperVaultId.CORE,
            symbol=PaperSymbol.BTCUSDT,
            reason=FP3ActionReason.OPEN,
            action_evidence_identity=first_sizing.sizing_event_identity,
            requested_at_ms=open_at,
        ),
        first_issuance,
        sizing_assessment=first_assessment,
        sizing_selection=first_selection,
        eligibility_proof=first_eligibility,
        reference_price=Decimal("101"),
        reference_price_evidence_identity=_sha("fp3c2-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal("101")},
        mark_evidence_identity=_sha("fp3c2-open-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=open_at + 10,
        mutated_at_ms=open_at + 11,
        snapshot_at_ms=open_at + 20,
        processed_at_ms=open_at + 30,
    )
    assert opened.receipt.r22_bundle_identity is not None

    second_issuance = _second_issuance(tmp_path)
    (
        second_front,
        second_sizing,
        second_assessment,
        second_selection,
        second_eligibility,
    ) = _size_existing_issuance(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
        issuance=second_issuance,
    )
    assert second_sizing.sizing_event_identity is not None
    scale_at = second_selection.selected_at_ms + 10
    scale_intent = build_fp3_action_intent(
        front_receipt_identity=second_front.receipt_identity,
        sizing_receipt_identity=second_sizing.receipt_identity,
        forecast_identity=second_issuance.forecast.forecast_identity,
        proof_identity=second_issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.SCALE_IN,
        action_evidence_identity=second_sizing.sizing_event_identity,
        requested_at_ms=scale_at,
    )
    scaled = bridge.process_buy(
        scale_intent,
        second_issuance,
        sizing_assessment=second_assessment,
        sizing_selection=second_selection,
        eligibility_proof=second_eligibility,
        reference_price=Decimal("102"),
        reference_price_evidence_identity=_sha("fp3c2-scale-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal("102")},
        mark_evidence_identity=_sha("fp3c2-scale-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=scale_at + 10,
        mutated_at_ms=scale_at + 11,
        snapshot_at_ms=scale_at + 20,
        processed_at_ms=scale_at + 30,
    )
    assert scaled.disposition is FP3ActionProcessDisposition.INSERTED
    assert scaled.receipt.canonical_action is PaperAction.BUY
    assert scaled.receipt.r22_bundle_identity is not None

    active_entries = read_canonical_active_buy_entries(
        epoch2_path=epoch2_path,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
    )
    assert len(active_entries) == 2
    assert active_entries[0].forecast_identity == first_issuance.forecast.forecast_identity
    assert active_entries[1].forecast_identity == second_issuance.forecast.forecast_identity
    assert (
        active_entries[0].sizing_assessment_identity
        != active_entries[1].sizing_assessment_identity
    )
    assert (
        active_entries[0].sizing_decision_identity
        == active_entries[1].sizing_decision_identity
    )

    history = R22Epoch2AtomicTape(epoch2_path).read_trade_history(
        PaperVaultId.CORE,
        PaperSymbol.BTCUSDT,
    )
    basis = reconstruct_open_cost_basis(
        history,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
    )
    current = _current_vault(epoch2_path, PaperVaultId.CORE)
    held = next(
        item.quantity
        for item in current.positions
        if item.symbol is PaperSymbol.BTCUSDT
    )
    assert basis.open_quantity == held
    assert len(basis.prior_fill_identities) == 2

    duplicate_scale = build_fp3_action_intent(
        front_receipt_identity=second_front.receipt_identity,
        sizing_receipt_identity=second_sizing.receipt_identity,
        forecast_identity=second_issuance.forecast.forecast_identity,
        proof_identity=second_issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.SCALE_IN,
        action_evidence_identity=second_sizing.sizing_event_identity,
        requested_at_ms=scale_at + 40,
    )
    with pytest.raises(ValueError, match="distinct forecast/proof/sizing lineage"):
        bridge.process_buy(
            duplicate_scale,
            second_issuance,
            sizing_assessment=second_assessment,
            sizing_selection=second_selection,
            eligibility_proof=second_eligibility,
            reference_price=Decimal("104"),
            reference_price_evidence_identity=_sha("fp3c2-duplicate-scale-reference"),
            mark_prices={PaperSymbol.BTCUSDT: Decimal("104")},
            mark_evidence_identity=_sha("fp3c2-duplicate-scale-mark"),
            execution_snapshot=_execution_snapshot(),
            filled_at_ms=scale_at + 50,
            mutated_at_ms=scale_at + 51,
            snapshot_at_ms=scale_at + 60,
            processed_at_ms=scale_at + 70,
        )

    exit_at = scale_at + 80
    exit_intent = build_fp3_action_intent(
        front_receipt_identity=second_front.receipt_identity,
        sizing_receipt_identity=second_sizing.receipt_identity,
        forecast_identity=second_issuance.forecast.forecast_identity,
        proof_identity=second_issuance.proof.proof_identity,
        vault_id=PaperVaultId.CORE,
        symbol=PaperSymbol.BTCUSDT,
        reason=FP3ActionReason.CLOSE,
        action_evidence_identity=_sha("fp3c2-close-evidence"),
        requested_at_ms=exit_at,
    )
    closed = bridge.process_sell(
        exit_intent,
        second_issuance,
        sizing_assessment=second_assessment,
        reference_price=Decimal("108"),
        reference_price_evidence_identity=_sha("fp3c2-close-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal("108")},
        mark_evidence_identity=_sha("fp3c2-close-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=exit_at + 10,
        mutated_at_ms=exit_at + 11,
        snapshot_at_ms=exit_at + 20,
        processed_at_ms=exit_at + 30,
    )
    epoch_after = epoch2_path.read_bytes()
    stream_after = stream_path.read_bytes()
    replay = bridge.process_sell(
        exit_intent,
        second_issuance,
        sizing_assessment=second_assessment,
        reference_price=Decimal("108"),
        reference_price_evidence_identity=_sha("fp3c2-close-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal("108")},
        mark_evidence_identity=_sha("fp3c2-close-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=exit_at + 10,
        mutated_at_ms=exit_at + 11,
        snapshot_at_ms=exit_at + 20,
        processed_at_ms=exit_at + 100,
    )

    assert closed.disposition is FP3ActionProcessDisposition.INSERTED
    assert closed.receipt.canonical_action is PaperAction.EXIT
    assert closed.receipt.outcome_identity is not None
    assert replay.disposition is FP3ActionProcessDisposition.REPLAYED
    assert replay.receipt == closed.receipt
    assert epoch2_path.read_bytes() == epoch_after
    assert stream_path.read_bytes() == stream_after
    assert (
        read_canonical_active_buy_entries(
            epoch2_path=epoch2_path,
            vault_id=PaperVaultId.CORE,
            symbol=PaperSymbol.BTCUSDT,
        )
        == ()
    )
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item for item in state.vault_snapshots if item.vault_id is PaperVaultId.CORE
    )
    assert not any(item.symbol is PaperSymbol.BTCUSDT for item in core.positions)

    trade_history = R22Epoch2AtomicTape(epoch2_path).read_trade_history(
        PaperVaultId.CORE,
        PaperSymbol.BTCUSDT,
    )
    assert [item["fill"]["action"] for item in trade_history] == [
        PaperAction.BUY.value,
        PaperAction.BUY.value,
        PaperAction.EXIT.value,
    ]
