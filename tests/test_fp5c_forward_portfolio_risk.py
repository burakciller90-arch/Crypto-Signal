from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_autopilot_forward_runtime import _paths
from test_autopilot_forward_sizing import (
    _risk,
    _selected_at_ms,
    _sha,
)
from test_canonical_capital_runtime import _execution_snapshot
from test_immutable_forecast_stream import _event_context
from test_position_sizing_intelligence import _policy

from crypto_signal.paper.autopilot_forward_actions import (
    FP3ActionProcessDisposition,
    FP3ActionReason,
    FP3ActionStageStatus,
    FP3PreregisteredActionBridge,
    build_fp3_action_intent,
)
from crypto_signal.paper.autopilot_forward_runtime import (
    CanonicalPaperAutopilotForwardRuntime,
)
from crypto_signal.paper.autopilot_forward_sizing import (
    FP3EligibleFixedFractionalSizingBridge,
    FP3SizingProcessDisposition,
    FP3SizingStageStatus,
    FP3SizingStageStore,
    build_fp3_sizing_risk_inputs,
)
from crypto_signal.paper.canonical_sizing import (
    promote_portfolio_risk_bounded_sizing,
)
from crypto_signal.paper.canonical_sizing_events import CanonicalSizingEventLedger
from crypto_signal.paper.canonical_vault_eligibility import promote_vault_eligibility
from crypto_signal.paper.capital_science_bridge import assess_unified_decision_capital
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperSymbol
from crypto_signal.paper.portfolio_risk_v2 import (
    CorrelationCluster,
    PortfolioRiskStatus,
    assess_portfolio_allocation,
    build_portfolio_risk_policy,
    build_portfolio_risk_snapshot,
)
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingPolicy,
    build_position_sizing_policy,
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


def _portfolio_policy(
    *,
    cash_reserve: str = "0.10",
    new_trade_loss: str = "0.0005",
):
    return build_portfolio_risk_policy(
        maximum_gross_exposure_fraction_of_nav=Decimal("0.80"),
        minimum_cash_reserve_fraction_of_nav=Decimal(cash_reserve),
        maximum_new_trade_loss_fraction_of_nav=Decimal(new_trade_loss),
        clusters=(
            CorrelationCluster(
                cluster_id="CRYPTO_BETA",
                members=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
                max_gross_exposure_fraction=Decimal("0.50"),
            ),
        ),
    )


def _alternate_sizing_policy() -> PositionSizingPolicy:
    return build_position_sizing_policy(
        policy_version="fp5c-alternate-sizing-policy-v1/1",
        fixed_fraction_of_vault=Decimal("0.03"),
        maximum_fraction_of_vault=Decimal("0.25"),
        maximum_absolute_correlation=Decimal("0.70"),
        maximum_drawdown_fraction=Decimal("0.20"),
        maximum_volatility_fraction=Decimal("0.25"),
        minimum_liquidity_score_0_1=Decimal("0.60"),
        maximum_transaction_cost_r=Decimal("0.20"),
    )


def _front(
    tmp_path: Path,
    *,
    project_stream: bool = False,
):
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    if project_stream:
        IntelligenceStreamForwardRuntime(stream_path).project_issuance(issuance)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    runtime.ensure_activated(activated_at_ms=issuance.forecast.issued_at_ms)
    result = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 5,
    )
    assert result.receipt is not None
    return epoch2_path, stream_path, autopilot_path, issuance, result.receipt


def _portfolio_assessment(
    epoch2_path: Path,
    issuance,
    *,
    cash_reserve: str = "0.10",
    new_trade_loss: str = "0.0005",
    snapshot_proven: bool = True,
    source_identity: str | None = None,
    sizing_policy: PositionSizingPolicy | None = None,
):
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    current = next(
        item
        for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    source_as_of_ms = issuance.confluence.as_of_ms
    fp5_risk = build_fp3_sizing_risk_inputs(
        vault_id=PaperVaultId.CORE,
        asset=issuance.forecast.symbol,
        as_of_ms=source_as_of_ms,
        expected_win_r=Decimal("2.00"),
        expected_loss_r=Decimal("1.00"),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=Decimal("0.20"),
        current_drawdown_fraction=current.drawdown_fraction,
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=tuple(
            sorted(
                {
                    _sha("fp5c-correlation"),
                    _sha("fp5c-drawdown"),
                    _sha("fp5c-liquidity"),
                    _sha("fp5c-payoff"),
                    _sha("fp5c-transaction-cost"),
                    _sha("fp5c-volatility"),
                }
            )
        ),
    )
    portfolio_policy = _portfolio_policy(
        cash_reserve=cash_reserve,
        new_trade_loss=new_trade_loss,
    )
    snapshot = None
    if snapshot_proven:
        snapshot = build_portfolio_risk_snapshot(
            policy=portfolio_policy,
            source_portfolio_identity=(
                state.consolidated_snapshot.snapshot_identity
                if source_identity is None
                else source_identity
            ),
            as_of_ms=source_as_of_ms,
            cash_usdt=state.consolidated_snapshot.cash_usdt,
            nav_usdt=state.consolidated_snapshot.nav_usdt,
            asset_exposures=(),
        )
    selected_sizing_policy = _policy() if sizing_policy is None else sizing_policy
    assessment = assess_portfolio_allocation(
        policy=portfolio_policy,
        sizing_policy=selected_sizing_policy,
        snapshot=snapshot,
        risk_inputs=fp5_risk,
        event_context=_event_context(),
        confluence=issuance.confluence,
        base_asset="BTC",
        stop_invalidation_fraction=Decimal("0.05"),
    )
    return assessment, fp5_risk


def _forward_inputs(
    *,
    epoch2_path: Path,
    issuance,
    front,
    risk,
    selected_at_ms: int,
    portfolio_assessment,
):
    event_context = _event_context()
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
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    current = next(
        item
        for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
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
    sizing_assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=envelope,
        context=context,
    )
    selection = promote_portfolio_risk_bounded_sizing(
        sizing_assessment,
        current_vault=current,
        current_portfolio=state.consolidated_snapshot,
        portfolio_assessment=portfolio_assessment,
        candidate_asset=risk.asset,
        risk_input_identity=portfolio_assessment.risk_input_identity,
        selected_at_ms=selected_at_ms,
    )
    assert selection is not None
    return sizing_assessment, selection, eligibility


def test_fp5c_forward_deployable_caps_sizing_and_replays_exact_lineage(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    portfolio_assessment, fp5_risk = _portfolio_assessment(
        epoch2_path,
        issuance,
    )
    assert portfolio_assessment.status is PortfolioRiskStatus.DEPLOYABLE
    assert portfolio_assessment.max_deployable_notional_usdt < Decimal(12)
    assert portfolio_assessment.risk_input_identity != risk.risk_input_identity

    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    before_r22 = R22Epoch2AtomicTape(epoch2_path).audit_all_read_only()
    first = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
        portfolio_assessment=portfolio_assessment,
    )
    replay = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 100,
        portfolio_assessment=portfolio_assessment,
    )

    assert first.disposition is FP3SizingProcessDisposition.INSERTED
    assert first.receipt is not None
    assert first.receipt.stage_status is FP3SizingStageStatus.SIZED
    assert first.receipt.selection_identity is not None
    assert first.receipt.sizing_event_identity is not None
    assert (
        f"fp5_portfolio_assessment:{portfolio_assessment.assessment_identity}"
        in first.receipt.reason_codes
    )
    assert (
        f"fp5_portfolio_risk_input:{fp5_risk.risk_input_identity}"
        in first.receipt.reason_codes
    )
    assert "fp5_portfolio_status:deployable" in first.receipt.reason_codes
    assert "portfolio_risk_v2_bound" in first.receipt.reason_codes
    assert replay.disposition is FP3SizingProcessDisposition.REPLAYED
    assert replay.receipt == first.receipt
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == before_r22

    event = CanonicalSizingEventLedger(epoch2_path).read(
        first.receipt.sizing_event_identity
    )
    assert event is not None
    assert Decimal(str(event["canonical_notional_usdt"])) == (
        portfolio_assessment.max_deployable_notional_usdt
    )
    evidence = set(event["source_evidence_identities"])
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    assert portfolio_assessment.assessment_identity in evidence
    assert fp5_risk.risk_input_identity in evidence
    assert state.consolidated_snapshot.snapshot_identity in evidence


def test_fp5c_hold_cash_persists_explicit_portfolio_hold_without_event(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    hold_assessment, _ = _portfolio_assessment(
        epoch2_path,
        issuance,
        cash_reserve="1.00",
        new_trade_loss="0.01",
    )
    assert hold_assessment.status is PortfolioRiskStatus.HOLD_CASH
    before_r22 = R22Epoch2AtomicTape(epoch2_path).audit_all_read_only()
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    held = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
        portfolio_assessment=hold_assessment,
    )
    replay = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 10,
        portfolio_assessment=hold_assessment,
    )

    assert held.disposition is FP3SizingProcessDisposition.HELD_PORTFOLIO_RISK
    assert held.receipt is not None
    assert held.receipt.stage_status is FP3SizingStageStatus.HELD_PORTFOLIO_RISK
    assert held.receipt.fixed_fractional_status == "available_shadow"
    assert held.receipt.selection_identity is None
    assert held.receipt.sizing_event_identity is None
    assert "portfolio_risk_v2_hold" in held.receipt.reason_codes
    assert "fp5_portfolio_status:hold_cash" in held.receipt.reason_codes
    assert replay.disposition is FP3SizingProcessDisposition.REPLAYED
    assert replay.receipt == held.receipt
    assert FP3SizingStageStore(autopilot_path).read(
        forecast_identity=issuance.forecast.forecast_identity,
        vault_id=PaperVaultId.CORE,
    ) == held.receipt
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == before_r22


def test_fp5c_not_proven_persists_without_inventing_portfolio_source(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    assessment, _ = _portfolio_assessment(
        epoch2_path,
        issuance,
        snapshot_proven=False,
        new_trade_loss="0.01",
    )
    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN

    result = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    ).process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
        portfolio_assessment=assessment,
    )

    assert result.disposition is FP3SizingProcessDisposition.HELD_PORTFOLIO_RISK
    assert result.receipt is not None
    assert "fp5_portfolio_status:not_proven" in result.receipt.reason_codes
    assert "fp5_portfolio_snapshot:not_proven" in result.receipt.reason_codes
    assert "fp5_portfolio_source:not_proven" in result.receipt.reason_codes
    assert result.receipt.selection_identity is None
    assert result.receipt.sizing_event_identity is None


def test_fp5c_rejects_stale_portfolio_source_and_sizing_policy_mismatch(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    stale, _ = _portfolio_assessment(
        epoch2_path,
        issuance,
        source_identity=_sha("fp5c-stale-portfolio"),
    )
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    with pytest.raises(ValueError, match="portfolio source is stale or mismatched"):
        bridge.process(
            issuance,
            event_context=_event_context(),
            base_asset="BTC",
            vault_id=PaperVaultId.CORE,
            policy=_policy(),
            risk_inputs=risk,
            selected_at_ms=selected_at_ms,
            processed_at_ms=selected_at_ms + 1,
            portfolio_assessment=stale,
        )

    wrong_policy, _ = _portfolio_assessment(
        epoch2_path,
        issuance,
        sizing_policy=_alternate_sizing_policy(),
    )
    with pytest.raises(ValueError, match="FP5 sizing policy mismatch"):
        bridge.process(
            issuance,
            event_context=_event_context(),
            base_asset="BTC",
            vault_id=PaperVaultId.CORE,
            policy=_policy(),
            risk_inputs=risk,
            selected_at_ms=selected_at_ms,
            processed_at_ms=selected_at_ms + 1,
            portfolio_assessment=wrong_policy,
        )


def test_fp5c_replay_rejects_changed_portfolio_hold_truth(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(tmp_path)
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    hold_assessment, _ = _portfolio_assessment(
        epoch2_path,
        issuance,
        cash_reserve="1.00",
        new_trade_loss="0.01",
    )
    not_proven, _ = _portfolio_assessment(
        epoch2_path,
        issuance,
        snapshot_proven=False,
        new_trade_loss="0.01",
    )
    bridge = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    first = bridge.process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
        portfolio_assessment=hold_assessment,
    )
    assert first.receipt is not None

    with pytest.raises(ValueError, match="replay inputs conflict with portfolio-risk hold"):
        bridge.process(
            issuance,
            event_context=_event_context(),
            base_asset="BTC",
            vault_id=PaperVaultId.CORE,
            policy=_policy(),
            risk_inputs=risk,
            selected_at_ms=selected_at_ms,
            processed_at_ms=selected_at_ms + 10,
            portfolio_assessment=not_proven,
        )


def test_fp5c_v2_selection_reaches_fp3c_buy_and_r22_via_exact_sizing_event(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance, front = _front(
        tmp_path,
        project_stream=True,
    )
    risk = _risk(
        epoch2_path=epoch2_path,
        front_assessed_at_ms=front.assessed_at_ms,
    )
    selected_at_ms = _selected_at_ms(
        epoch2_path=epoch2_path,
        front=front,
        risk=risk,
    )
    portfolio_assessment, _ = _portfolio_assessment(epoch2_path, issuance)
    sizing_result = FP3EligibleFixedFractionalSizingBridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    ).process(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        vault_id=PaperVaultId.CORE,
        policy=_policy(),
        risk_inputs=risk,
        selected_at_ms=selected_at_ms,
        processed_at_ms=selected_at_ms + 1,
        portfolio_assessment=portfolio_assessment,
    )
    assert sizing_result.receipt is not None
    sizing = sizing_result.receipt
    assert sizing.selection_identity is not None
    assert sizing.sizing_event_identity is not None

    assessment, selection, eligibility = _forward_inputs(
        epoch2_path=epoch2_path,
        issuance=issuance,
        front=front,
        risk=risk,
        selected_at_ms=selected_at_ms,
        portfolio_assessment=portfolio_assessment,
    )
    assert selection.selection_identity == sizing.selection_identity

    requested_at_ms = selected_at_ms + 10
    intent = build_fp3_action_intent(
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
    committed = FP3PreregisteredActionBridge(
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
        reference_price_evidence_identity=_sha("fp5c-buy-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp5c-buy-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=requested_at_ms + 10,
        mutated_at_ms=requested_at_ms + 11,
        snapshot_at_ms=requested_at_ms + 20,
        processed_at_ms=requested_at_ms + 30,
    )

    assert committed.disposition is FP3ActionProcessDisposition.INSERTED
    assert committed.receipt.stage_status is FP3ActionStageStatus.COMMITTED
    assert committed.receipt.r22_bundle_identity is not None
    story = R22Epoch2AtomicTape(epoch2_path).read_bundle_story_context(
        committed.receipt.r22_bundle_identity
    )
    assert sizing.sizing_event_identity in story["intent"]["source_evidence_identities"]

    event = CanonicalSizingEventLedger(epoch2_path).read(
        sizing.sizing_event_identity
    )
    assert event is not None
    assert portfolio_assessment.assessment_identity in set(
        event["source_evidence_identities"]
    )
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item
        for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assert sizing.sizing_event_identity in core.source_record_identities
    assert selection.selection_identity in core.source_record_identities
    assert state.consolidated_snapshot.real_capital == 0
