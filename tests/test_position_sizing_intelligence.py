from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper import position_sizing_intelligence
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import (
    POSITION_SIZING_ENGINE_VERSION,
    POSITION_SIZING_SCHEMA_VERSION,
    SizingMethod,
    SizingMethodStatus,
    build_position_sizing_policy,
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.smart_capital_allocator import (
    VaultCapitalEnvelope,
    VaultEligibilityState,
)
from research.alpha_factory.probability_calibration_gate import (
    R19_CALIBRATION_ENGINE_VERSION,
    R19_CALIBRATION_SCHEMA_VERSION,
    R19_PROBABILITY_SEMANTIC,
    CalibratedProbabilityEvidence,
    R19ProbabilityStatus,
)

AS_OF = 1_000_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _policy():
    return build_position_sizing_policy(
        policy_version="position-sizing-research-policy-v1/1",
        fixed_fraction_of_vault=Decimal("0.02"),
        maximum_fraction_of_vault=Decimal("0.25"),
        maximum_absolute_correlation=Decimal("0.70"),
        maximum_drawdown_fraction=Decimal("0.20"),
        maximum_volatility_fraction=Decimal("0.25"),
        minimum_liquidity_score_0_1=Decimal("0.60"),
        maximum_transaction_cost_r=Decimal("0.20"),
    )


def _vault(
    *,
    eligible: bool = True,
    vault_id: PaperVaultId = PaperVaultId.CORE,
):
    budget = {
        PaperVaultId.CORE: Decimal("600.00"),
        PaperVaultId.TACTICAL: Decimal("300.00"),
        PaperVaultId.OPPORTUNITY_RESERVE: Decimal("100.00"),
    }[vault_id]
    return VaultCapitalEnvelope(
        vault_id=vault_id,
        starting_budget_usdt=budget,
        eligibility_state=(
            VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
            if eligible
            else VaultEligibilityState.HOLD_CASH
        ),
        reason_codes=(
            ("eligible",)
            if eligible
            else ("allocator_evidence_not_sufficient",)
        ),
        candidate_identity=_sha("candidate"),
        event_risk_identity=_sha("event-risk"),
        confluence_identity=_sha("confluence"),
        tactical_evidence_identity=_sha("tactical"),
        recovery_evidence_identity=_sha("recovery"),
        sizing_required_before_any_trade=eligible,
    )


def _context(
    *,
    vault_id: PaperVaultId = PaperVaultId.CORE,
    correlation: str = "0.20",
    drawdown: str = "0.05",
    volatility: str = "0.10",
    liquidity: str = "0.90",
    cost: str = "0.10",
    win_r: str = "2.00",
    loss_r: str = "1.00",
):
    return build_position_sizing_risk_context(
        vault_id=vault_id,
        asset="BTCUSDT",
        as_of_ms=AS_OF,
        allocator_assessment_identity=_sha("allocator-assessment"),
        allocator_candidate_identity=_sha("candidate"),
        expected_win_r=Decimal(win_r),
        expected_loss_r=Decimal(loss_r),
        transaction_cost_r=Decimal(cost),
        absolute_correlation_0_1=Decimal(correlation),
        current_drawdown_fraction=Decimal(drawdown),
        volatility_fraction=Decimal(volatility),
        liquidity_score_0_1=Decimal(liquidity),
        source_evidence_identities=(
            _sha("correlation"),
            _sha("drawdown"),
            _sha("liquidity"),
            _sha("payoff"),
            _sha("volatility"),
        ),
    )


def _calibrated_probability(
    probability: Decimal = Decimal("0.60"),
    *,
    issued_at_ms: int = AS_OF - 1,
):
    scope_identity = _sha("scope")
    model_version = "probability-model-v1"
    calibrator_version = "calibrator-v1"
    walk_forward_fit_identity = _sha("walk-forward-fit")
    source_forecast_identity = _sha(f"forecast-{issued_at_ms}-{probability}")
    prediction_payload = {
        "calibrator_version": calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "issued_at_ms": issued_at_ms,
        "model_version": model_version,
        "predicted_probability_0_1": probability,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": scope_identity,
        "source_forecast_identity": source_forecast_identity,
        "walk_forward_fit_identity": walk_forward_fit_identity,
    }
    source_prediction_identity = canonical_sha256(prediction_payload)
    payload = {
        "calibration_evidence_identity": _sha("calibration-report"),
        "calibrator_version": calibrator_version,
        "engine_version": R19_CALIBRATION_ENGINE_VERSION,
        "issued_at_ms": issued_at_ms,
        "model_version": model_version,
        "probability_0_1": probability,
        "probability_semantic": R19_PROBABILITY_SEMANTIC,
        "probability_status": R19ProbabilityStatus.CALIBRATED,
        "production_authority": False,
        "real_capital": 0,
        "schema_version": R19_CALIBRATION_SCHEMA_VERSION,
        "scope_identity": scope_identity,
        "source_forecast_identity": source_forecast_identity,
        "source_prediction_identity": source_prediction_identity,
        "walk_forward_fit_identity": walk_forward_fit_identity,
    }
    return CalibratedProbabilityEvidence(
        authorization_identity=canonical_sha256(payload),
        schema_version=R19_CALIBRATION_SCHEMA_VERSION,
        engine_version=R19_CALIBRATION_ENGINE_VERSION,
        calibration_evidence_identity=_sha("calibration-report"),
        scope_identity=scope_identity,
        model_version=model_version,
        calibrator_version=calibrator_version,
        walk_forward_fit_identity=walk_forward_fit_identity,
        source_prediction_identity=source_prediction_identity,
        source_forecast_identity=source_forecast_identity,
        issued_at_ms=issued_at_ms,
        probability_0_1=probability,
        probability_status=R19ProbabilityStatus.CALIBRATED,
        probability_semantic=R19_PROBABILITY_SEMANTIC,
    )


def _by_method(assessment):
    return {item.method: item for item in assessment.results}


def test_policy_is_explicit_research_only_and_forbids_martingale() -> None:
    policy = _policy()

    assert policy.engine_version == POSITION_SIZING_ENGINE_VERSION
    assert policy.schema_version == POSITION_SIZING_SCHEMA_VERSION
    assert policy.fixed_fraction_of_vault == Decimal("0.02")
    assert policy.maximum_fraction_of_vault == Decimal("0.25")
    assert policy.martingale_allowed is False
    assert policy.automatic_method_selection is False
    assert policy.canonical_notional_authority is False
    assert policy.production_authority is False
    assert policy.real_capital == 0

    with pytest.raises(ValueError, match="martingale"):
        replace(policy, martingale_allowed=True)


def test_without_r19_calibration_only_fixed_fractional_shadow_baseline_is_available() -> None:
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=_vault(),
        context=_context(),
    )
    results = _by_method(assessment)

    fixed = results[SizingMethod.FIXED_FRACTIONAL]
    assert fixed.status is SizingMethodStatus.AVAILABLE_SHADOW
    assert fixed.fraction_of_vault == Decimal("0.020000")
    assert fixed.hypothetical_notional_usdt == Decimal("12.0000")
    assert fixed.canonical_notional_usdt is None
    assert fixed.uses_calibrated_probability is False

    for method in (
        SizingMethod.KELLY_FULL,
        SizingMethod.KELLY_HALF,
        SizingMethod.KELLY_QUARTER,
    ):
        result = results[method]
        assert (
            result.status
            is SizingMethodStatus.DISABLED_NO_CALIBRATED_PROBABILITY
        )
        assert result.fraction_of_vault is None
        assert result.hypothetical_notional_usdt is None
        assert result.probability_0_1 is None

    assert assessment.selected_method is None
    assert assessment.selected_fraction_of_vault is None
    assert assessment.canonical_notional_usdt is None
    assert assessment.automatic_method_selection is False
    assert assessment.production_authority is False


def test_calibrated_probability_enables_full_half_quarter_kelly_shadow_comparison() -> None:
    probability = _calibrated_probability(Decimal("0.60"))
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=_vault(),
        context=_context(),
        calibrated_probability=probability,
    )
    results = _by_method(assessment)

    assert assessment.calibrated_probability_available is True

    fixed = results[SizingMethod.FIXED_FRACTIONAL]
    assert fixed.status is SizingMethodStatus.AVAILABLE_SHADOW
    assert fixed.fraction_of_vault == Decimal("0.020000")
    assert fixed.uses_calibrated_probability is False

    full = results[SizingMethod.KELLY_FULL]
    half = results[SizingMethod.KELLY_HALF]
    quarter = results[SizingMethod.KELLY_QUARTER]

    for item in (full, half, quarter):
        assert item.status is SizingMethodStatus.AVAILABLE_SHADOW
        assert item.uses_calibrated_probability is True
        assert item.probability_0_1 == Decimal("0.60")
        assert item.expected_edge_r == Decimal("0.700000")
        assert item.kelly_raw_fraction == Decimal("0.368421")
        assert (
            item.calibration_authorization_identity
            == probability.authorization_identity
        )
        assert item.canonical_notional_usdt is None

    assert full.fraction_of_vault == Decimal("0.250000")
    assert full.hypothetical_notional_usdt == Decimal("150.0000")
    assert half.fraction_of_vault == Decimal("0.184210")
    assert half.hypothetical_notional_usdt == Decimal("110.5260")
    assert quarter.fraction_of_vault == Decimal("0.092105")
    assert quarter.hypothetical_notional_usdt == Decimal("55.2630")
    assert assessment.selected_method is None


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("correlation", "0.80", "correlation_limit_breached"),
        ("drawdown", "0.30", "drawdown_limit_breached"),
        ("volatility", "0.30", "volatility_limit_breached"),
        ("liquidity", "0.50", "liquidity_floor_breached"),
        ("cost", "0.30", "transaction_cost_limit_breached"),
    ),
)
def test_risk_context_gates_block_all_methods(field, value, reason) -> None:
    kwargs = {field: value}
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=_vault(),
        context=_context(**kwargs),
        calibrated_probability=_calibrated_probability(),
    )

    assert all(
        item.status is SizingMethodStatus.HOLD_RISK_GATE
        for item in assessment.results
    )
    assert all(reason in item.reason_codes for item in assessment.results)
    assert all(item.fraction_of_vault is None for item in assessment.results)


def test_allocator_hold_cash_blocks_all_sizing_even_if_probability_exists() -> None:
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=_vault(eligible=False),
        context=_context(),
        calibrated_probability=_calibrated_probability(),
    )

    assert all(
        item.status is SizingMethodStatus.HOLD_ALLOCATOR_NOT_ELIGIBLE
        for item in assessment.results
    )
    assert all(item.fraction_of_vault is None for item in assessment.results)


def test_non_positive_calibrated_edge_blocks_fixed_and_kelly_methods() -> None:
    assessment = evaluate_position_sizing_intelligence(
        policy=_policy(),
        vault=_vault(),
        context=_context(win_r="1.00", loss_r="2.00", cost="0.10"),
        calibrated_probability=_calibrated_probability(Decimal("0.30")),
    )

    assert all(
        item.status
        is SizingMethodStatus.HOLD_NON_POSITIVE_CALIBRATED_EDGE
        for item in assessment.results
    )
    assert all(item.expected_edge_r is not None for item in assessment.results)
    assert all(item.fraction_of_vault is None for item in assessment.results)


def test_kelly_probability_must_not_come_from_future() -> None:
    with pytest.raises(ValueError, match="from the future"):
        evaluate_position_sizing_intelligence(
            policy=_policy(),
            vault=_vault(),
            context=_context(),
            calibrated_probability=_calibrated_probability(
                Decimal("0.60"),
                issued_at_ms=AS_OF + 1,
            ),
        )


def test_vault_and_candidate_lineage_fail_closed() -> None:
    with pytest.raises(ValueError, match="vault/context id mismatch"):
        evaluate_position_sizing_intelligence(
            policy=_policy(),
            vault=_vault(vault_id=PaperVaultId.CORE),
            context=_context(vault_id=PaperVaultId.TACTICAL),
        )

    bad_context = replace(
        _context(),
        allocator_candidate_identity=_sha("other-candidate"),
    )
    bad_context = replace(
        bad_context,
        context_identity=canonical_sha256(
            {
                "absolute_correlation_0_1": bad_context.absolute_correlation_0_1,
                "allocator_assessment_identity": bad_context.allocator_assessment_identity,
                "allocator_candidate_identity": bad_context.allocator_candidate_identity,
                "as_of_ms": bad_context.as_of_ms,
                "asset": bad_context.asset,
                "current_drawdown_fraction": bad_context.current_drawdown_fraction,
                "engine_version": bad_context.engine_version,
                "expected_loss_r": bad_context.expected_loss_r,
                "expected_win_r": bad_context.expected_win_r,
                "liquidity_score_0_1": bad_context.liquidity_score_0_1,
                "real_capital": bad_context.real_capital,
                "schema_version": bad_context.schema_version,
                "source_evidence_identities": bad_context.source_evidence_identities,
                "transaction_cost_r": bad_context.transaction_cost_r,
                "vault_id": bad_context.vault_id,
                "volatility_fraction": bad_context.volatility_fraction,
            }
        ),
    )
    with pytest.raises(ValueError, match="allocator candidate lineage mismatch"):
        evaluate_position_sizing_intelligence(
            policy=_policy(),
            vault=_vault(),
            context=bad_context,
        )


def test_policy_context_result_and_assessment_identity_tampering_fail_closed() -> None:
    policy = _policy()
    context = _context()
    assessment = evaluate_position_sizing_intelligence(
        policy=policy,
        vault=_vault(),
        context=context,
        calibrated_probability=_calibrated_probability(),
    )

    with pytest.raises(ValueError, match="sizing policy identity mismatch"):
        replace(policy, maximum_fraction_of_vault=Decimal("0.24"))
    with pytest.raises(ValueError, match="sizing context identity mismatch"):
        replace(context, volatility_fraction=Decimal("0.11"))
    with pytest.raises(ValueError, match="sizing method result identity mismatch"):
        replace(
            assessment.results[0],
            reason_codes=("tampered",),
        )
    with pytest.raises(ValueError, match="sizing assessment identity mismatch"):
        replace(
            assessment,
            allocator_vault_starting_budget_usdt=Decimal("599.00"),
        )


def test_position_sizing_intelligence_has_no_execution_ledger_or_selection_surface() -> None:
    source = inspect.getsource(position_sizing_intelligence).lower()
    forbidden = (
        "sqlite3",
        "paperfundledger",
        "append_",
        "write_text",
        "write_bytes",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "simulate_paper_fill",
        "commit_orchestration_bundle",
        "def select_winner",
        "def promote",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert position_sizing_intelligence.REAL_CAPITAL == 0
