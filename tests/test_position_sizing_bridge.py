from __future__ import annotations

from decimal import Decimal

import pytest
from test_immutable_forecast_stream import (
    _calibrated_probability,
    _event_context,
)
from test_position_sizing_intelligence import _policy
from test_unified_decision_runtime import _issue

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.capital_science_bridge import assess_unified_decision_capital
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_bridge import (
    SizingBridgeState,
    assess_capital_position_sizing,
    build_accepted_sizing_risk_inputs,
)
from crypto_signal.paper.position_sizing_intelligence import (
    SizingMethod,
    SizingMethodStatus,
)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _capital(tmp_path, *, calibrated: bool = False):
    _, issuance = _issue(tmp_path, calibrated=calibrated)
    capital = assess_unified_decision_capital(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 1,
    )
    return issuance, capital


def _core_risk(issuance, **overrides):
    values = {
        "expected_win_r": Decimal("2.00"),
        "expected_loss_r": Decimal("1.00"),
        "transaction_cost_r": Decimal("0.10"),
        "absolute_correlation_0_1": Decimal("0.20"),
        "current_drawdown_fraction": Decimal("0.05"),
        "volatility_fraction": Decimal("0.10"),
        "liquidity_score_0_1": Decimal("0.90"),
    }
    values.update(overrides)
    return build_accepted_sizing_risk_inputs(
        vault_id=PaperVaultId.CORE,
        asset="BTCUSDT",
        measured_at_ms=issuance.forecast.issued_at_ms + 2,
        source_evidence_identities=(
            _sha("correlation"),
            _sha("drawdown"),
            _sha("liquidity"),
            _sha("payoff"),
            _sha("transaction-cost"),
            _sha("volatility"),
        ),
        **values,
    )


def _vault_result(result, vault_id):
    return next(item for item in result.vault_results if item.vault_id is vault_id)


def _by_method(assessment):
    assert assessment is not None
    return {item.method: item for item in assessment.results}


def test_only_allocator_eligible_vault_with_explicit_risk_inputs_is_sized(
    tmp_path,
) -> None:
    issuance, capital = _capital(tmp_path)
    risk = _core_risk(issuance)

    result = assess_capital_position_sizing(
        issuance,
        capital,
        policy=_policy(),
        sized_at_ms=issuance.forecast.issued_at_ms + 3,
        risk_inputs=(risk,),
    )

    core = _vault_result(result, PaperVaultId.CORE)
    tactical = _vault_result(result, PaperVaultId.TACTICAL)
    reserve = _vault_result(result, PaperVaultId.OPPORTUNITY_RESERVE)

    assert core.state is SizingBridgeState.ASSESSED_SHADOW
    assert core.risk_identity == risk.risk_identity
    assert core.context is not None
    assert core.context.allocator_assessment_identity == (
        capital.allocation.assessment_identity
    )
    assert core.context.allocator_candidate_identity == (
        capital.candidate.candidate_identity
    )
    assert risk.risk_identity in core.context.source_evidence_identities
    assert capital.bridge_identity in core.context.source_evidence_identities
    assert issuance.proof.proof_identity in core.context.source_evidence_identities

    methods = _by_method(core.assessment)
    assert (
        methods[SizingMethod.FIXED_FRACTIONAL].status
        is SizingMethodStatus.AVAILABLE_SHADOW
    )
    assert (
        methods[SizingMethod.FIXED_FRACTIONAL].hypothetical_notional_usdt
        == Decimal("12.0000")
    )
    for method in (
        SizingMethod.KELLY_FULL,
        SizingMethod.KELLY_HALF,
        SizingMethod.KELLY_QUARTER,
    ):
        assert (
            methods[method].status
            is SizingMethodStatus.DISABLED_NO_CALIBRATED_PROBABILITY
        )

    assert tactical.state is SizingBridgeState.HOLD_ALLOCATOR
    assert reserve.state is SizingBridgeState.HOLD_ALLOCATOR
    assert tactical.context is None and tactical.assessment is None
    assert reserve.context is None and reserve.assessment is None
    assert result.selected_method is None
    assert result.canonical_notional_usdt is None
    assert result.automatic_method_selection is False
    assert result.production_authority is False
    assert result.real_capital == 0


def test_eligible_vault_without_explicit_risk_truth_remains_unsized(tmp_path) -> None:
    issuance, capital = _capital(tmp_path)
    result = assess_capital_position_sizing(
        issuance,
        capital,
        policy=_policy(),
        sized_at_ms=issuance.forecast.issued_at_ms + 2,
    )
    core = _vault_result(result, PaperVaultId.CORE)
    assert core.state is SizingBridgeState.MISSING_RISK_INPUTS
    assert core.reason_codes == ("accepted_sizing_risk_inputs_missing",)
    assert core.context is None
    assert core.assessment is None


def test_allocator_hold_vault_rejects_supplied_sizing_numbers(tmp_path) -> None:
    issuance, capital = _capital(tmp_path)
    tactical_risk = build_accepted_sizing_risk_inputs(
        vault_id=PaperVaultId.TACTICAL,
        asset="BTCUSDT",
        measured_at_ms=issuance.forecast.issued_at_ms + 2,
        expected_win_r=Decimal(2),
        expected_loss_r=Decimal(1),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=Decimal("0.20"),
        current_drawdown_fraction=Decimal("0.05"),
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=(_sha("tactical-risk"),),
    )
    with pytest.raises(
        ValueError,
        match="HOLD_CASH vault cannot accept sizing risk inputs",
    ):
        assess_capital_position_sizing(
            issuance,
            capital,
            policy=_policy(),
            sized_at_ms=issuance.forecast.issued_at_ms + 3,
            risk_inputs=(tactical_risk,),
        )


def test_explicit_risk_gate_breach_blocks_every_sizing_method(tmp_path) -> None:
    issuance, capital = _capital(tmp_path)
    risk = _core_risk(
        issuance,
        absolute_correlation_0_1=Decimal("0.95"),
    )
    result = assess_capital_position_sizing(
        issuance,
        capital,
        policy=_policy(),
        sized_at_ms=issuance.forecast.issued_at_ms + 3,
        risk_inputs=(risk,),
    )
    methods = _by_method(
        _vault_result(result, PaperVaultId.CORE).assessment
    )
    assert all(
        item.status is SizingMethodStatus.HOLD_RISK_GATE
        for item in methods.values()
    )
    assert all(
        "correlation_limit_breached" in item.reason_codes
        for item in methods.values()
    )


def test_exact_r19_probability_enables_shadow_kelly_without_selecting_winner(
    tmp_path,
) -> None:
    issuance, capital = _capital(tmp_path, calibrated=True)
    probability = _calibrated_probability()
    risk = _core_risk(issuance)
    result = assess_capital_position_sizing(
        issuance,
        capital,
        policy=_policy(),
        sized_at_ms=issuance.forecast.issued_at_ms + 3,
        risk_inputs=(risk,),
        calibrated_probability=probability,
    )
    core = _vault_result(result, PaperVaultId.CORE)
    methods = _by_method(core.assessment)
    assert (
        methods[SizingMethod.KELLY_FULL].status
        is SizingMethodStatus.AVAILABLE_SHADOW
    )
    assert (
        methods[SizingMethod.KELLY_HALF].status
        is SizingMethodStatus.AVAILABLE_SHADOW
    )
    assert (
        methods[SizingMethod.KELLY_QUARTER].status
        is SizingMethodStatus.AVAILABLE_SHADOW
    )
    assert core.assessment is not None
    assert core.assessment.selected_method is None
    assert core.assessment.canonical_notional_usdt is None
    assert result.selected_method is None


def test_probability_not_bound_to_exact_forecast_is_rejected(tmp_path) -> None:
    issuance, capital = _capital(tmp_path, calibrated=True)
    wrong_probability = _calibrated_probability(probability=Decimal("0.61"))
    with pytest.raises(
        ValueError,
        match="authorization does not match forecast",
    ):
        assess_capital_position_sizing(
            issuance,
            capital,
            policy=_policy(),
            sized_at_ms=issuance.forecast.issued_at_ms + 3,
            risk_inputs=(_core_risk(issuance),),
            calibrated_probability=wrong_probability,
        )


def test_risk_snapshot_cannot_arrive_before_forecast_or_after_sizing(tmp_path) -> None:
    issuance, capital = _capital(tmp_path)
    too_early = build_accepted_sizing_risk_inputs(
        vault_id=PaperVaultId.CORE,
        asset="BTCUSDT",
        measured_at_ms=issuance.forecast.issued_at_ms - 1,
        expected_win_r=Decimal(2),
        expected_loss_r=Decimal(1),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=Decimal("0.20"),
        current_drawdown_fraction=Decimal("0.05"),
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=(_sha("early-risk"),),
    )
    with pytest.raises(ValueError, match="outside decision-to-sizing window"):
        assess_capital_position_sizing(
            issuance,
            capital,
            policy=_policy(),
            sized_at_ms=issuance.forecast.issued_at_ms + 3,
            risk_inputs=(too_early,),
        )
