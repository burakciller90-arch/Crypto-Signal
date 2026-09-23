"""R25 Slice 7: exact Capital Science -> Position Sizing bridge.

Risk numbers are never inferred from a forecast or Decision Proof. An eligible
vault is sized only when explicit source-bound risk inputs are supplied.
Results remain shadow-only and no method winner/canonical notional is selected.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.capital_science_bridge import CapitalScienceBridgeResult
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingAssessment,
    PositionSizingPolicy,
    PositionSizingRiskContext,
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.smart_capital_allocator import VaultEligibilityState
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance
if TYPE_CHECKING:
    from research.alpha_factory.probability_calibration_gate import (
        CalibratedProbabilityEvidence,
    )

POSITION_SIZING_BRIDGE_VERSION = "r25-position-sizing-bridge-v1/1"
REAL_CAPITAL = 0


class SizingBridgeState(StrEnum):
    ASSESSED_SHADOW = "assessed_shadow"
    HOLD_ALLOCATOR = "hold_allocator"
    MISSING_RISK_INPUTS = "missing_risk_inputs"


@dataclass(frozen=True, slots=True)
class AcceptedSizingRiskInputs:
    risk_identity: str
    vault_id: PaperVaultId
    asset: str
    measured_at_ms: int
    expected_win_r: Decimal
    expected_loss_r: Decimal
    transaction_cost_r: Decimal
    absolute_correlation_0_1: Decimal
    current_drawdown_fraction: Decimal
    volatility_fraction: Decimal
    liquidity_score_0_1: Decimal
    source_evidence_identities: tuple[str, ...]
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.risk_identity, "sizing risk identity")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("sizing risk inputs require canonical vault")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("sizing risk asset must be uppercase")
        if self.measured_at_ms < 0:
            raise ValueError("sizing risk measurement time must be non-negative")
        for value, label in (
            (self.expected_win_r, "expected win R"),
            (self.expected_loss_r, "expected loss R"),
        ):
            if value.is_nan() or value.is_infinite() or value <= 0:
                raise ValueError(f"{label} must be finite and positive")
        if (
            self.transaction_cost_r.is_nan()
            or self.transaction_cost_r.is_infinite()
            or self.transaction_cost_r < 0
        ):
            raise ValueError("transaction cost R must be finite and non-negative")
        for value, label in (
            (self.absolute_correlation_0_1, "absolute correlation"),
            (self.current_drawdown_fraction, "drawdown"),
            (self.volatility_fraction, "volatility"),
            (self.liquidity_score_0_1, "liquidity score"),
        ):
            _unit(value, label)
        if not self.source_evidence_identities:
            raise ValueError("sizing risk inputs require exact source evidence")
        if (
            self.source_evidence_identities
            != tuple(sorted(set(self.source_evidence_identities)))
        ):
            raise ValueError("sizing risk evidence identities must be sorted unique")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "sizing risk evidence identity")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("sizing risk inputs cannot grant execution authority")
        if self.risk_identity != canonical_sha256(_risk_payload(self)):
            raise ValueError("sizing risk input identity mismatch")


@dataclass(frozen=True, slots=True)
class SizingBridgeVaultResult:
    result_identity: str
    vault_id: PaperVaultId
    state: SizingBridgeState
    reason_codes: tuple[str, ...]
    risk_identity: str | None
    context: PositionSizingRiskContext | None
    assessment: PositionSizingAssessment | None
    automatic_method_selection: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "sizing bridge vault result")
        if (
            not self.reason_codes
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
        ):
            raise ValueError("sizing bridge reasons must be non-empty sorted unique")
        if self.state is SizingBridgeState.ASSESSED_SHADOW:
            if self.risk_identity is None or self.context is None or self.assessment is None:
                raise ValueError("assessed sizing requires risk/context/assessment")
            _require_sha256(self.risk_identity, "assessed sizing risk identity")
            if self.context.vault_id is not self.vault_id:
                raise ValueError("sizing bridge context vault mismatch")
            if self.assessment.vault_id is not self.vault_id:
                raise ValueError("sizing bridge assessment vault mismatch")
            if self.assessment.context_identity != self.context.context_identity:
                raise ValueError("sizing bridge assessment/context mismatch")
        else:
            if (
                self.risk_identity is not None
                or self.context is not None
                or self.assessment is not None
            ):
                raise ValueError("non-assessed sizing cannot carry fabricated context")
        if self.automatic_method_selection or self.production_authority:
            raise ValueError("sizing bridge cannot auto-select or gain production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.result_identity != canonical_sha256(_vault_result_payload(self)):
            raise ValueError("sizing bridge vault result identity mismatch")


@dataclass(frozen=True, slots=True)
class PositionSizingBridgeResult:
    bridge_identity: str
    capital_bridge_identity: str
    forecast_identity: str
    proof_identity: str
    policy_identity: str
    sized_at_ms: int
    vault_results: tuple[SizingBridgeVaultResult, ...]
    bridge_version: str = POSITION_SIZING_BRIDGE_VERSION
    selected_method: None = None
    canonical_notional_usdt: None = None
    automatic_method_selection: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.bridge_identity, "position sizing bridge"),
            (self.capital_bridge_identity, "capital bridge"),
            (self.forecast_identity, "sizing forecast"),
            (self.proof_identity, "sizing proof"),
            (self.policy_identity, "sizing policy"),
        ):
            _require_sha256(identity, label)
        expected_vaults = tuple(sorted(PaperVaultId, key=lambda item: item.value))
        if tuple(item.vault_id for item in self.vault_results) != expected_vaults:
            raise ValueError("sizing bridge requires canonical three-vault order")
        if (
            self.selected_method is not None
            or self.canonical_notional_usdt is not None
            or self.automatic_method_selection
            or self.production_authority
        ):
            raise ValueError("sizing bridge cannot select/canonicalize sizing")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.bridge_identity != canonical_sha256(_bridge_payload(self)):
            raise ValueError("position sizing bridge identity mismatch")


def build_accepted_sizing_risk_inputs(
    *,
    vault_id: PaperVaultId,
    asset: str,
    measured_at_ms: int,
    expected_win_r: Decimal,
    expected_loss_r: Decimal,
    transaction_cost_r: Decimal,
    absolute_correlation_0_1: Decimal,
    current_drawdown_fraction: Decimal,
    volatility_fraction: Decimal,
    liquidity_score_0_1: Decimal,
    source_evidence_identities: tuple[str, ...],
) -> AcceptedSizingRiskInputs:
    sources = tuple(sorted(set(source_evidence_identities)))
    payload = {
        "absolute_correlation_0_1": absolute_correlation_0_1,
        "asset": asset,
        "current_drawdown_fraction": current_drawdown_fraction,
        "expected_loss_r": expected_loss_r,
        "expected_win_r": expected_win_r,
        "liquidity_score_0_1": liquidity_score_0_1,
        "measured_at_ms": measured_at_ms,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "source_evidence_identities": sources,
        "transaction_cost_r": transaction_cost_r,
        "vault_id": vault_id,
        "volatility_fraction": volatility_fraction,
    }
    return AcceptedSizingRiskInputs(
        risk_identity=canonical_sha256(payload),
        vault_id=vault_id,
        asset=asset,
        measured_at_ms=measured_at_ms,
        expected_win_r=expected_win_r,
        expected_loss_r=expected_loss_r,
        transaction_cost_r=transaction_cost_r,
        absolute_correlation_0_1=absolute_correlation_0_1,
        current_drawdown_fraction=current_drawdown_fraction,
        volatility_fraction=volatility_fraction,
        liquidity_score_0_1=liquidity_score_0_1,
        source_evidence_identities=sources,
    )


def assess_capital_position_sizing(
    issuance: UnifiedDecisionIssuance,
    capital: CapitalScienceBridgeResult,
    *,
    policy: PositionSizingPolicy,
    sized_at_ms: int,
    risk_inputs: tuple[AcceptedSizingRiskInputs, ...] = (),
    calibrated_probability: CalibratedProbabilityEvidence | None = None,
) -> PositionSizingBridgeResult:
    """Run accepted sizing only where allocator + explicit risk evidence permit it."""
    if capital.forecast_identity != issuance.forecast.forecast_identity:
        raise ValueError("sizing bridge capital/forecast lineage mismatch")
    if capital.proof_identity != issuance.proof.proof_identity:
        raise ValueError("sizing bridge capital/proof lineage mismatch")
    if capital.confluence_identity != issuance.confluence.snapshot_identity:
        raise ValueError("sizing bridge capital/M6 lineage mismatch")
    if sized_at_ms < max(capital.assessed_at_ms, issuance.forecast.issued_at_ms):
        raise ValueError("sizing bridge cannot predate forecast/capital assessment")

    if calibrated_probability is not None:
        if (
            issuance.forecast.probability_authorization_identity
            != calibrated_probability.authorization_identity
        ):
            raise ValueError("sizing probability authorization does not match forecast")
        if (
            issuance.forecast.calibrated_probability_0_1
            != calibrated_probability.probability_0_1
        ):
            raise ValueError("sizing probability value does not match forecast")
        if calibrated_probability.issued_at_ms > issuance.forecast.source_as_of_ms:
            raise ValueError("sizing probability was not available at forecast PIT cutoff")

    by_vault: dict[PaperVaultId, AcceptedSizingRiskInputs] = {}
    for risk_input in risk_inputs:
        if risk_input.vault_id in by_vault:
            raise ValueError("duplicate sizing risk input for vault")
        by_vault[risk_input.vault_id] = risk_input

    results: list[SizingBridgeVaultResult] = []
    for vault in capital.allocation.vaults:
        selected_risk = by_vault.get(vault.vault_id)

        if vault.eligibility_state is VaultEligibilityState.HOLD_CASH:
            if selected_risk is not None:
                raise ValueError(
                    "allocator HOLD_CASH vault cannot accept sizing risk inputs"
                )
            results.append(
                _vault_result(
                    vault_id=vault.vault_id,
                    state=SizingBridgeState.HOLD_ALLOCATOR,
                    reason_codes=vault.reason_codes,
                )
            )
            continue

        if selected_risk is None:
            results.append(
                _vault_result(
                    vault_id=vault.vault_id,
                    state=SizingBridgeState.MISSING_RISK_INPUTS,
                    reason_codes=("accepted_sizing_risk_inputs_missing",),
                )
            )
            continue

        if selected_risk.asset != issuance.forecast.symbol:
            raise ValueError("sizing risk input market mismatch")
        if not issuance.forecast.issued_at_ms <= selected_risk.measured_at_ms <= sized_at_ms:
            raise ValueError("sizing risk input time outside decision-to-sizing window")

        context = build_position_sizing_risk_context(
            vault_id=vault.vault_id,
            asset=issuance.forecast.symbol,
            as_of_ms=selected_risk.measured_at_ms,
            allocator_assessment_identity=capital.allocation.assessment_identity,
            allocator_candidate_identity=capital.candidate.candidate_identity,
            expected_win_r=selected_risk.expected_win_r,
            expected_loss_r=selected_risk.expected_loss_r,
            transaction_cost_r=selected_risk.transaction_cost_r,
            absolute_correlation_0_1=selected_risk.absolute_correlation_0_1,
            current_drawdown_fraction=selected_risk.current_drawdown_fraction,
            volatility_fraction=selected_risk.volatility_fraction,
            liquidity_score_0_1=selected_risk.liquidity_score_0_1,
            source_evidence_identities=tuple(
                sorted(
                    {
                        *selected_risk.source_evidence_identities,
                        selected_risk.risk_identity,
                        capital.bridge_identity,
                        issuance.proof.proof_identity,
                    }
                )
            ),
        )
        assessment = evaluate_position_sizing_intelligence(
            policy=policy,
            vault=vault,
            context=context,
            calibrated_probability=calibrated_probability,
        )
        results.append(
            _vault_result(
                vault_id=vault.vault_id,
                state=SizingBridgeState.ASSESSED_SHADOW,
                reason_codes=("position_sizing_assessed_shadow_only",),
                risk_identity=selected_risk.risk_identity,
                context=context,
                assessment=assessment,
            )
        )

    ordered = tuple(sorted(results, key=lambda item: item.vault_id.value))
    payload = {
        "automatic_method_selection": False,
        "bridge_version": POSITION_SIZING_BRIDGE_VERSION,
        "canonical_notional_usdt": None,
        "capital_bridge_identity": capital.bridge_identity,
        "forecast_identity": issuance.forecast.forecast_identity,
        "policy_identity": policy.policy_identity,
        "production_authority": False,
        "proof_identity": issuance.proof.proof_identity,
        "real_capital": REAL_CAPITAL,
        "selected_method": None,
        "sized_at_ms": sized_at_ms,
        "vault_result_identities": tuple(item.result_identity for item in ordered),
    }
    return PositionSizingBridgeResult(
        bridge_identity=canonical_sha256(payload),
        capital_bridge_identity=capital.bridge_identity,
        forecast_identity=issuance.forecast.forecast_identity,
        proof_identity=issuance.proof.proof_identity,
        policy_identity=policy.policy_identity,
        sized_at_ms=sized_at_ms,
        vault_results=ordered,
    )


def _vault_result(
    *,
    vault_id: PaperVaultId,
    state: SizingBridgeState,
    reason_codes: tuple[str, ...],
    risk_identity: str | None = None,
    context: PositionSizingRiskContext | None = None,
    assessment: PositionSizingAssessment | None = None,
) -> SizingBridgeVaultResult:
    reasons = tuple(sorted(set(reason_codes)))
    payload = {
        "assessment_identity": (
            None if assessment is None else assessment.assessment_identity
        ),
        "automatic_method_selection": False,
        "context_identity": None if context is None else context.context_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": reasons,
        "risk_identity": risk_identity,
        "state": state,
        "vault_id": vault_id,
    }
    return SizingBridgeVaultResult(
        result_identity=canonical_sha256(payload),
        vault_id=vault_id,
        state=state,
        reason_codes=reasons,
        risk_identity=risk_identity,
        context=context,
        assessment=assessment,
    )


def _risk_payload(risk: AcceptedSizingRiskInputs) -> dict[str, object]:
    return {
        "absolute_correlation_0_1": risk.absolute_correlation_0_1,
        "asset": risk.asset,
        "current_drawdown_fraction": risk.current_drawdown_fraction,
        "expected_loss_r": risk.expected_loss_r,
        "expected_win_r": risk.expected_win_r,
        "liquidity_score_0_1": risk.liquidity_score_0_1,
        "measured_at_ms": risk.measured_at_ms,
        "production_authority": risk.production_authority,
        "real_capital": risk.real_capital,
        "source_evidence_identities": risk.source_evidence_identities,
        "transaction_cost_r": risk.transaction_cost_r,
        "vault_id": risk.vault_id,
        "volatility_fraction": risk.volatility_fraction,
    }


def _vault_result_payload(result: SizingBridgeVaultResult) -> dict[str, object]:
    return {
        "assessment_identity": (
            None if result.assessment is None else result.assessment.assessment_identity
        ),
        "automatic_method_selection": result.automatic_method_selection,
        "context_identity": (
            None if result.context is None else result.context.context_identity
        ),
        "production_authority": result.production_authority,
        "real_capital": result.real_capital,
        "reason_codes": result.reason_codes,
        "risk_identity": result.risk_identity,
        "state": result.state,
        "vault_id": result.vault_id,
    }


def _bridge_payload(result: PositionSizingBridgeResult) -> dict[str, object]:
    return {
        "automatic_method_selection": result.automatic_method_selection,
        "bridge_version": result.bridge_version,
        "canonical_notional_usdt": result.canonical_notional_usdt,
        "capital_bridge_identity": result.capital_bridge_identity,
        "forecast_identity": result.forecast_identity,
        "policy_identity": result.policy_identity,
        "production_authority": result.production_authority,
        "proof_identity": result.proof_identity,
        "real_capital": result.real_capital,
        "selected_method": result.selected_method,
        "sized_at_ms": result.sized_at_ms,
        "vault_result_identities": tuple(
            item.result_identity for item in result.vault_results
        ),
    }


def _unit(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value < 0 or value > 1:
        raise ValueError(f"{label} must be inside [0,1]")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
