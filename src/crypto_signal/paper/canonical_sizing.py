"""S11 canonical paper-sizing promotion.

This module does not create real-money or exchange authority. It promotes only the
already-computed fixed-fractional sizing result into a versioned Epoch 2 paper
notional, bounded by the exact current vault cash. Kelly variants remain research
unless a later separately accepted calibrated promotion policy exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import Epoch2VaultAccountingSnapshot
from crypto_signal.paper.epochs import PaperVaultId
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
        if self.policy_version != S11_CANONICAL_SIZING_POLICY_VERSION:
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
        for value, label in (
            (self.canonical_notional_usdt, "canonical notional"),
            (self.current_cash_usdt, "current cash"),
            (self.current_nav_usdt, "current NAV"),
        ):
            if (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or value < 0
            ):
                raise ValueError(f"S11 {label} must be finite and non-negative")
        if self.canonical_notional_usdt <= 0:
            raise ValueError("S11 canonical notional must be positive")
        if self.canonical_notional_usdt > self.current_cash_usdt:
            raise ValueError("S11 canonical notional cannot exceed current vault cash")
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
    return {
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


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
