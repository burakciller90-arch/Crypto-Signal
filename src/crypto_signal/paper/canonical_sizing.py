"""S11 canonical paper-sizing promotion.

This module does not create real-money or exchange authority. It promotes only the
already-computed fixed-fractional sizing result into a versioned Epoch 2 paper
notional, bounded by the exact current vault cash. Kelly variants remain research
unless a later separately accepted calibrated promotion policy exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    Epoch2ConsolidatedAccountingSnapshot,
    Epoch2VaultAccountingSnapshot,
)
from crypto_signal.paper.epochs import PaperVaultId

if TYPE_CHECKING:
    from crypto_signal.paper.portfolio_risk_v2 import PortfolioAllocationAssessmentV2
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingAssessment,
    SizingMethod,
    SizingMethodResult,
    SizingMethodStatus,
)

S11_CANONICAL_SIZING_VERSION = "stream-s11-canonical-sizing-v1/1"
S11_CANONICAL_SIZING_POLICY_VERSION = (
    "stream-s11-fixed-fractional-paper-promotion-v1/1"
)
S11_CANONICAL_SIZING_POLICY_V2 = (
    "stream-s11-fixed-fractional-portfolio-risk-promotion-v2/1"
)
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class CanonicalPaperSizingSelection:
    selection_identity: str
    selection_version: str
    policy_version: str
    vault_id: PaperVaultId
    sizing_assessment_identity: str
    sizing_result_identity: str
    sizing_policy_identity: str
    allocator_candidate_identity: str
    current_vault_snapshot_identity: str
    method: SizingMethod
    fraction_of_vault: Decimal
    canonical_notional_usdt: Decimal
    current_cash_usdt: Decimal
    current_nav_usdt: Decimal
    selected_at_ms: int
    reason_codes: tuple[str, ...]
    source_evidence_identities: tuple[str, ...]
    portfolio_risk_assessment_identity: str | None = None
    portfolio_source_identity: str | None = None
    portfolio_risk_cap_usdt: Decimal | None = None
    canonical_epoch2_paper_authority: bool = True
    automatic_method_selection: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.selection_identity, "S11 sizing selection"),
            (self.sizing_assessment_identity, "S11 sizing assessment"),
            (self.sizing_result_identity, "S11 sizing result"),
            (self.sizing_policy_identity, "S11 sizing policy"),
            (self.allocator_candidate_identity, "S11 allocator candidate"),
            (self.current_vault_snapshot_identity, "S11 vault snapshot"),
        ):
            _require_sha256(value, label)
        if self.selection_version != S11_CANONICAL_SIZING_VERSION:
            raise ValueError("unsupported S11 canonical sizing version")
        if self.policy_version not in {
            S11_CANONICAL_SIZING_POLICY_VERSION,
            S11_CANONICAL_SIZING_POLICY_V2,
        }:
            raise ValueError("unsupported S11 canonical sizing policy")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 canonical sizing requires canonical vault")
        if self.method is not SizingMethod.FIXED_FRACTIONAL:
            raise ValueError("S11 canonical sizing only promotes fixed fractional")
        if (
            not isinstance(self.fraction_of_vault, Decimal)
            or not self.fraction_of_vault.is_finite()
            or self.fraction_of_vault <= 0
            or self.fraction_of_vault > 1
        ):
            raise ValueError("S11 canonical sizing fraction must be inside (0,1]")
        for amount, amount_label in (
            (self.canonical_notional_usdt, "canonical notional"),
            (self.current_cash_usdt, "current cash"),
            (self.current_nav_usdt, "current NAV"),
        ):
            if not amount.is_finite() or amount < 0:
                raise ValueError(
                    f"S11 {amount_label} must be finite and non-negative"
                )
        if self.canonical_notional_usdt <= 0:
            raise ValueError("S11 canonical notional must be positive")
        if self.canonical_notional_usdt > self.current_cash_usdt:
            raise ValueError("S11 canonical notional cannot exceed current vault cash")
        if self.policy_version == S11_CANONICAL_SIZING_POLICY_VERSION:
            if (
                self.portfolio_risk_assessment_identity is not None
                or self.portfolio_source_identity is not None
                or self.portfolio_risk_cap_usdt is not None
            ):
                raise ValueError("S11 V1 sizing cannot carry FP5 portfolio-risk fields")
        else:
            portfolio_risk_identity = self.portfolio_risk_assessment_identity
            portfolio_source_identity = self.portfolio_source_identity
            portfolio_risk_cap = self.portfolio_risk_cap_usdt
            if (
                portfolio_risk_identity is None
                or portfolio_source_identity is None
                or portfolio_risk_cap is None
            ):
                raise ValueError("S11 V2 sizing requires exact FP5 portfolio-risk lineage")
            _require_sha256(
                portfolio_risk_identity,
                "S11 FP5 portfolio-risk assessment",
            )
            _require_sha256(
                portfolio_source_identity,
                "S11 FP5 portfolio source",
            )
            if not portfolio_risk_cap.is_finite() or portfolio_risk_cap <= 0:
                raise ValueError("S11 FP5 portfolio-risk cap must be positive finite")
            if self.canonical_notional_usdt > portfolio_risk_cap:
                raise ValueError("S11 V2 notional cannot exceed FP5 portfolio-risk cap")
            if "portfolio_risk_v2_bound" not in self.reason_codes:
                raise ValueError("S11 V2 sizing must declare portfolio-risk binding")
        if self.selected_at_ms < 0:
            raise ValueError("S11 sizing selection time must be non-negative")
        if (
            not self.reason_codes
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
        ):
            raise ValueError("S11 sizing reasons must be non-empty sorted unique")
        if (
            not self.source_evidence_identities
            or self.source_evidence_identities
            != tuple(sorted(set(self.source_evidence_identities)))
        ):
            raise ValueError("S11 sizing evidence must be non-empty sorted unique")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "S11 sizing source evidence")
        required = {
            self.sizing_assessment_identity,
            self.sizing_result_identity,
            self.sizing_policy_identity,
            self.allocator_candidate_identity,
            self.current_vault_snapshot_identity,
        }
        if self.policy_version == S11_CANONICAL_SIZING_POLICY_V2:
            assert self.portfolio_risk_assessment_identity is not None
            assert self.portfolio_source_identity is not None
            required.update(
                {
                    self.portfolio_risk_assessment_identity,
                    self.portfolio_source_identity,
                }
            )
        if not required.issubset(set(self.source_evidence_identities)):
            raise ValueError("S11 sizing selection lost exact source lineage")
        if (
            not self.canonical_epoch2_paper_authority
            or not self.automatic_method_selection
        ):
            raise ValueError("S11 selection must explicitly carry paper-only authority")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("S11 sizing cannot grant production/real-capital authority")
        if self.selection_identity != canonical_sha256(
            _selection_payload(self)
        ):
            raise ValueError("S11 canonical sizing selection identity mismatch")


def promote_fixed_fractional_sizing(
    assessment: PositionSizingAssessment,
    *,
    current_vault: Epoch2VaultAccountingSnapshot,
    selected_at_ms: int,
) -> CanonicalPaperSizingSelection:
    """Promote the exact fixed-fractional result into bounded Epoch 2 paper sizing."""
    if assessment.vault_id is not current_vault.vault_id:
        raise ValueError("S11 sizing assessment/current-vault mismatch")
    if selected_at_ms < current_vault.snapshot_at_ms:
        raise ValueError("S11 sizing selection cannot predate current vault state")

    result = _fixed_fractional_result(assessment)
    if result.status is not SizingMethodStatus.AVAILABLE_SHADOW:
        raise ValueError("S11 fixed fractional result is not available")
    if result.fraction_of_vault is None or result.hypothetical_notional_usdt is None:
        raise ValueError("S11 fixed fractional result lacks bounded sizing")
    if result.uses_calibrated_probability:
        raise ValueError("S11 fixed fractional promotion must not depend on probability")
    if result.calibration_authorization_identity is not None:
        raise ValueError("S11 fixed fractional promotion cannot borrow calibration authority")
    if current_vault.cash_usdt <= 0:
        raise ValueError("S11 cannot promote a trade from an empty-cash vault")

    canonical_notional = min(
        result.hypothetical_notional_usdt,
        current_vault.cash_usdt,
    )
    reasons = {
        "canonical_epoch2_paper_only",
        "fixed_fractional_only",
        "kelly_not_promoted",
        "real_capital_zero",
    }
    if canonical_notional < result.hypothetical_notional_usdt:
        reasons.add("capped_by_current_vault_cash")
    sources = tuple(
        sorted(
            {
                assessment.assessment_identity,
                result.result_identity,
                assessment.policy_identity,
                assessment.allocator_candidate_identity,
                current_vault.snapshot_identity,
            }
        )
    )
    payload = {
        "allocator_candidate_identity": assessment.allocator_candidate_identity,
        "automatic_method_selection": True,
        "canonical_epoch2_paper_authority": True,
        "canonical_notional_usdt": canonical_notional,
        "current_cash_usdt": current_vault.cash_usdt,
        "current_nav_usdt": current_vault.nav_usdt,
        "current_vault_snapshot_identity": current_vault.snapshot_identity,
        "fraction_of_vault": result.fraction_of_vault,
        "method": result.method,
        "policy_version": S11_CANONICAL_SIZING_POLICY_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": tuple(sorted(reasons)),
        "selected_at_ms": selected_at_ms,
        "selection_version": S11_CANONICAL_SIZING_VERSION,
        "sizing_assessment_identity": assessment.assessment_identity,
        "sizing_policy_identity": assessment.policy_identity,
        "sizing_result_identity": result.result_identity,
        "source_evidence_identities": sources,
        "vault_id": assessment.vault_id,
    }
    return CanonicalPaperSizingSelection(
        selection_identity=canonical_sha256(payload),
        selection_version=S11_CANONICAL_SIZING_VERSION,
        policy_version=S11_CANONICAL_SIZING_POLICY_VERSION,
        vault_id=assessment.vault_id,
        sizing_assessment_identity=assessment.assessment_identity,
        sizing_result_identity=result.result_identity,
        sizing_policy_identity=assessment.policy_identity,
        allocator_candidate_identity=assessment.allocator_candidate_identity,
        current_vault_snapshot_identity=current_vault.snapshot_identity,
        method=result.method,
        fraction_of_vault=result.fraction_of_vault,
        canonical_notional_usdt=canonical_notional,
        current_cash_usdt=current_vault.cash_usdt,
        current_nav_usdt=current_vault.nav_usdt,
        selected_at_ms=selected_at_ms,
        reason_codes=tuple(sorted(reasons)),
        source_evidence_identities=sources,
    )


def promote_portfolio_risk_bounded_sizing(
    assessment: PositionSizingAssessment,
    *,
    current_vault: Epoch2VaultAccountingSnapshot,
    current_portfolio: Epoch2ConsolidatedAccountingSnapshot,
    portfolio_assessment: PortfolioAllocationAssessmentV2,
    candidate_asset: str,
    risk_input_identity: str,
    selected_at_ms: int,
) -> CanonicalPaperSizingSelection | None:
    """Promote fixed-fractional sizing only when FP5 portfolio risk permits it."""
    if assessment.vault_id is not current_vault.vault_id:
        raise ValueError("S11 V2 sizing assessment/current-vault mismatch")
    if portfolio_assessment.vault_id is not assessment.vault_id:
        raise ValueError("S11 V2 FP5 assessment vault mismatch")
    if portfolio_assessment.sizing_policy_identity != assessment.policy_identity:
        raise ValueError("S11 V2 FP5/sizing policy identity mismatch")
    if portfolio_assessment.candidate_asset != candidate_asset:
        raise ValueError("S11 V2 FP5 candidate asset mismatch")
    _require_sha256(risk_input_identity, "S11 V2 FP5 risk input")
    if portfolio_assessment.risk_input_identity != risk_input_identity:
        raise ValueError("S11 V2 FP5 risk-input identity mismatch")
    if current_vault.snapshot_identity not in current_portfolio.vault_snapshot_identities:
        raise ValueError("S11 V2 current vault is not in consolidated R21 snapshot")
    if portfolio_assessment.source_portfolio_identity is not None and (
        portfolio_assessment.source_portfolio_identity
        != current_portfolio.snapshot_identity
    ):
        raise ValueError("S11 V2 FP5 portfolio source is stale or mismatched")
    if selected_at_ms < max(
        current_vault.snapshot_at_ms,
        current_portfolio.snapshot_at_ms,
        portfolio_assessment.as_of_ms,
    ):
        raise ValueError("S11 V2 sizing selection predates exact portfolio truth")

    portfolio_status = portfolio_assessment.status.value
    if portfolio_status == "not_proven":
        return None
    if portfolio_status == "hold_cash":
        if portfolio_assessment.source_portfolio_identity is None:
            raise ValueError("S11 V2 HOLD_CASH requires proven portfolio source")
        return None
    if portfolio_status != "deployable":
        raise ValueError("S11 V2 unsupported FP5 portfolio-risk status")

    portfolio_source_identity = portfolio_assessment.source_portfolio_identity
    portfolio_snapshot_identity = portfolio_assessment.snapshot_identity
    if portfolio_source_identity is None:
        raise ValueError("S11 V2 DEPLOYABLE requires proven portfolio source")
    if portfolio_snapshot_identity is None:
        raise ValueError("S11 V2 DEPLOYABLE requires FP5 portfolio snapshot")
    if portfolio_assessment.max_deployable_notional_usdt <= 0:
        raise ValueError("S11 V2 DEPLOYABLE requires positive FP5 capacity")
    if (
        portfolio_assessment.current_gross_exposure_usdt
        != current_portfolio.marked_exposure_usdt
    ):
        raise ValueError("S11 V2 FP5 gross exposure differs from canonical R21 portfolio")

    result = _fixed_fractional_result(assessment)
    if result.status is not SizingMethodStatus.AVAILABLE_SHADOW:
        raise ValueError("S11 V2 fixed fractional result is not available")
    if result.fraction_of_vault is None or result.hypothetical_notional_usdt is None:
        raise ValueError("S11 V2 fixed fractional result lacks bounded sizing")
    if result.uses_calibrated_probability:
        raise ValueError("S11 V2 fixed fractional promotion cannot depend on probability")
    if result.calibration_authorization_identity is not None:
        raise ValueError("S11 V2 fixed fractional promotion cannot borrow calibration")
    if current_vault.cash_usdt <= 0:
        raise ValueError("S11 V2 cannot promote from an empty-cash vault")

    expected_portfolio_baseline = (
        current_portfolio.nav_usdt * result.fraction_of_vault
    )
    if (
        portfolio_assessment.baseline_fixed_fractional_notional_usdt
        != expected_portfolio_baseline
    ):
        raise ValueError("S11 V2 FP5 fixed-fractional baseline mismatch")

    canonical_notional = min(
        result.hypothetical_notional_usdt,
        current_vault.cash_usdt,
        portfolio_assessment.max_deployable_notional_usdt,
    )
    if canonical_notional <= 0:
        return None

    reasons = {
        "canonical_epoch2_paper_only",
        "fixed_fractional_only",
        "kelly_not_promoted",
        "portfolio_risk_v2_bound",
        "real_capital_zero",
    }
    if canonical_notional < result.hypothetical_notional_usdt:
        if canonical_notional == current_vault.cash_usdt:
            reasons.add("capped_by_current_vault_cash")
        if canonical_notional == portfolio_assessment.max_deployable_notional_usdt:
            reasons.add("capped_by_portfolio_risk")
    sources = tuple(
        sorted(
            {
                assessment.assessment_identity,
                result.result_identity,
                assessment.policy_identity,
                assessment.allocator_candidate_identity,
                current_vault.snapshot_identity,
                current_portfolio.snapshot_identity,
                portfolio_assessment.assessment_identity,
                portfolio_snapshot_identity,
                risk_input_identity,
            }
        )
    )
    payload = {
        "allocator_candidate_identity": assessment.allocator_candidate_identity,
        "automatic_method_selection": True,
        "canonical_epoch2_paper_authority": True,
        "canonical_notional_usdt": canonical_notional,
        "current_cash_usdt": current_vault.cash_usdt,
        "current_nav_usdt": current_vault.nav_usdt,
        "current_vault_snapshot_identity": current_vault.snapshot_identity,
        "fraction_of_vault": result.fraction_of_vault,
        "method": result.method,
        "policy_version": S11_CANONICAL_SIZING_POLICY_V2,
        "portfolio_risk_assessment_identity": portfolio_assessment.assessment_identity,
        "portfolio_risk_cap_usdt": portfolio_assessment.max_deployable_notional_usdt,
        "portfolio_source_identity": current_portfolio.snapshot_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason_codes": tuple(sorted(reasons)),
        "selected_at_ms": selected_at_ms,
        "selection_version": S11_CANONICAL_SIZING_VERSION,
        "sizing_assessment_identity": assessment.assessment_identity,
        "sizing_policy_identity": assessment.policy_identity,
        "sizing_result_identity": result.result_identity,
        "source_evidence_identities": sources,
        "vault_id": assessment.vault_id,
    }
    return CanonicalPaperSizingSelection(
        selection_identity=canonical_sha256(payload),
        selection_version=S11_CANONICAL_SIZING_VERSION,
        policy_version=S11_CANONICAL_SIZING_POLICY_V2,
        vault_id=assessment.vault_id,
        sizing_assessment_identity=assessment.assessment_identity,
        sizing_result_identity=result.result_identity,
        sizing_policy_identity=assessment.policy_identity,
        allocator_candidate_identity=assessment.allocator_candidate_identity,
        current_vault_snapshot_identity=current_vault.snapshot_identity,
        method=result.method,
        fraction_of_vault=result.fraction_of_vault,
        canonical_notional_usdt=canonical_notional,
        current_cash_usdt=current_vault.cash_usdt,
        current_nav_usdt=current_vault.nav_usdt,
        selected_at_ms=selected_at_ms,
        reason_codes=tuple(sorted(reasons)),
        source_evidence_identities=sources,
        portfolio_risk_assessment_identity=portfolio_assessment.assessment_identity,
        portfolio_source_identity=current_portfolio.snapshot_identity,
        portfolio_risk_cap_usdt=portfolio_assessment.max_deployable_notional_usdt,
    )


def _fixed_fractional_result(
    assessment: PositionSizingAssessment,
) -> SizingMethodResult:
    matches = tuple(
        item
        for item in assessment.results
        if item.method is SizingMethod.FIXED_FRACTIONAL
    )
    if len(matches) != 1:
        raise ValueError("S11 sizing assessment must contain one fixed-fractional result")
    return matches[0]


def _selection_payload(
    selection: CanonicalPaperSizingSelection,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "allocator_candidate_identity": selection.allocator_candidate_identity,
        "automatic_method_selection": selection.automatic_method_selection,
        "canonical_epoch2_paper_authority": (
            selection.canonical_epoch2_paper_authority
        ),
        "canonical_notional_usdt": selection.canonical_notional_usdt,
        "current_cash_usdt": selection.current_cash_usdt,
        "current_nav_usdt": selection.current_nav_usdt,
        "current_vault_snapshot_identity": (
            selection.current_vault_snapshot_identity
        ),
        "fraction_of_vault": selection.fraction_of_vault,
        "method": selection.method,
        "policy_version": selection.policy_version,
        "production_authority": selection.production_authority,
        "real_capital": selection.real_capital,
        "reason_codes": selection.reason_codes,
        "selected_at_ms": selection.selected_at_ms,
        "selection_version": selection.selection_version,
        "sizing_assessment_identity": selection.sizing_assessment_identity,
        "sizing_policy_identity": selection.sizing_policy_identity,
        "sizing_result_identity": selection.sizing_result_identity,
        "source_evidence_identities": selection.source_evidence_identities,
        "vault_id": selection.vault_id,
    }
    if selection.policy_version == S11_CANONICAL_SIZING_POLICY_V2:
        payload.update(
            {
                "portfolio_risk_assessment_identity": (
                    selection.portfolio_risk_assessment_identity
                ),
                "portfolio_risk_cap_usdt": selection.portfolio_risk_cap_usdt,
                "portfolio_source_identity": selection.portfolio_source_identity,
            }
        )
    return payload


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
