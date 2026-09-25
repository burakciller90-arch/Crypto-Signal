"""S11 promotion of Smart Capital Allocator eligibility into paper execution proof.

The allocator remains the owner of vault eligibility. This module does not
re-evaluate or loosen its policy; it cryptographically binds the exact accepted
candidate, assessment and vault envelope so later S11 sizing/execution can prove
why a vault was allowed to participate.

Simulation only. REAL_CAPITAL remains 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.smart_capital_allocator import (
    SmartCapitalAllocationAssessment,
    SmartCapitalCandidate,
    VaultEligibilityState,
)

S11_VAULT_ELIGIBILITY_VERSION = "stream-s11-vault-eligibility-v1/1"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class CanonicalVaultEligibilityProof:
    proof_identity: str
    proof_version: str
    allocator_assessment_identity: str
    allocator_candidate_identity: str
    vault_id: PaperVaultId
    asset: str
    candidate_as_of_ms: int
    assessed_at_ms: int
    starting_budget_usdt: Decimal
    eligibility_reason_codes: tuple[str, ...]
    event_risk_identity: str
    confluence_identity: str | None
    tactical_evidence_identity: str | None
    tactical_timeframe: str | None
    recovery_evidence_identity: str | None
    candidate_source_evidence_identities: tuple[str, ...]
    canonical_paper_execution_eligible: bool = True
    cross_vault_borrowing_allowed: bool = False
    forced_deployment: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.proof_identity, "S11 vault eligibility proof"),
            (self.allocator_assessment_identity, "S11 allocator assessment"),
            (self.allocator_candidate_identity, "S11 allocator candidate"),
            (self.event_risk_identity, "S11 allocator Event Risk"),
        ):
            _require_sha256(identity, label)
        for identity, label in (
            (self.confluence_identity, "S11 allocator confluence"),
            (self.tactical_evidence_identity, "S11 tactical evidence"),
            (self.recovery_evidence_identity, "S11 recovery evidence"),
        ):
            if identity is not None:
                _require_sha256(identity, label)
        if self.proof_version != S11_VAULT_ELIGIBILITY_VERSION:
            raise ValueError("unsupported S11 vault eligibility proof version")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 vault eligibility proof requires canonical vault")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("S11 vault eligibility asset must be uppercase")
        if min(self.candidate_as_of_ms, self.assessed_at_ms) < 0:
            raise ValueError("S11 vault eligibility timestamps must be non-negative")
        if self.assessed_at_ms < self.candidate_as_of_ms:
            raise ValueError("S11 allocator assessment cannot predate candidate")
        if (
            not isinstance(self.starting_budget_usdt, Decimal)
            or not self.starting_budget_usdt.is_finite()
            or self.starting_budget_usdt <= 0
        ):
            raise ValueError("S11 vault eligibility budget must be finite and positive")
        if (
            not self.eligibility_reason_codes
            or self.eligibility_reason_codes
            != tuple(sorted(set(self.eligibility_reason_codes)))
        ):
            raise ValueError("S11 vault eligibility reasons must be sorted unique")
        _identity_tuple(
            self.candidate_source_evidence_identities,
            "S11 allocator candidate source evidence",
        )
        if self.event_risk_identity not in self.candidate_source_evidence_identities:
            raise ValueError("S11 eligibility lost exact Event Risk lineage")
        optional_candidate_evidence = (
            self.confluence_identity,
            self.tactical_evidence_identity,
            self.recovery_evidence_identity,
        )
        if any(
            identity is not None
            and identity not in self.candidate_source_evidence_identities
            for identity in optional_candidate_evidence
        ):
            raise ValueError("S11 eligibility lost candidate evidence lineage")
        if self.vault_id is PaperVaultId.TACTICAL:
            if self.tactical_evidence_identity is None:
                raise ValueError("S11 Tactical eligibility requires tactical evidence")
            if self.tactical_timeframe not in {"1m", "5m"}:
                raise ValueError("S11 Tactical eligibility requires 1m/5m timeframe")
        elif self.tactical_timeframe is not None:
            raise ValueError("S11 non-Tactical eligibility cannot carry tactical timeframe")
        if self.vault_id is PaperVaultId.OPPORTUNITY_RESERVE:
            if self.recovery_evidence_identity is None:
                raise ValueError("S11 Opportunity eligibility requires recovery evidence")
        if (
            not self.canonical_paper_execution_eligible
            or self.cross_vault_borrowing_allowed
            or self.forced_deployment
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("S11 vault eligibility authority boundary mismatch")
        if self.proof_identity != canonical_sha256(_proof_payload(self)):
            raise ValueError("S11 vault eligibility proof identity mismatch")


def promote_vault_eligibility(
    candidate: SmartCapitalCandidate,
    assessment: SmartCapitalAllocationAssessment,
    *,
    vault_id: PaperVaultId,
) -> CanonicalVaultEligibilityProof:
    """Promote one exact eligible allocator envelope into paper-only execution proof."""
    if assessment.candidate_identity != candidate.candidate_identity:
        raise ValueError("S11 allocator assessment/candidate identity mismatch")
    if assessment.assessed_at_ms < candidate.as_of_ms:
        raise ValueError("S11 allocator assessment predates candidate")
    if assessment.production_authority or assessment.real_capital != REAL_CAPITAL:
        raise ValueError("S11 allocator assessment authority boundary mismatch")
    if (
        assessment.automatic_trade_authority
        or assessment.automatic_sizing_authority
        or assessment.cross_vault_transfer_authority
    ):
        raise ValueError("S11 cannot promote allocator automatic authority")

    envelopes = tuple(
        envelope for envelope in assessment.vaults if envelope.vault_id is vault_id
    )
    if len(envelopes) != 1:
        raise ValueError("S11 allocator assessment lacks exact target vault")
    envelope = envelopes[0]
    if envelope.candidate_identity != candidate.candidate_identity:
        raise ValueError("S11 allocator envelope candidate mismatch")
    if envelope.eligibility_state is not VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE:
        raise ValueError("S11 cannot promote HOLD_CASH vault into execution")
    if not envelope.sizing_required_before_any_trade:
        raise ValueError("S11 eligible vault must require sizing")
    if (
        envelope.cross_vault_borrowing_allowed
        or envelope.forced_deployment
        or envelope.production_authority
        or envelope.real_capital != REAL_CAPITAL
    ):
        raise ValueError("S11 allocator envelope authority boundary mismatch")

    expected = {
        "event_risk": candidate.event_risk.evidence_identity,
        "confluence": (
            None if candidate.confluence is None else candidate.confluence.snapshot_identity
        ),
        "tactical": (
            None
            if candidate.tactical_microstructure is None
            else candidate.tactical_microstructure.evidence_identity
        ),
        "recovery": (
            None
            if candidate.opportunity_recovery is None
            else candidate.opportunity_recovery.evidence_identity
        ),
    }
    if envelope.event_risk_identity != expected["event_risk"]:
        raise ValueError("S11 allocator envelope Event Risk mismatch")
    if envelope.confluence_identity != expected["confluence"]:
        raise ValueError("S11 allocator envelope confluence mismatch")
    if envelope.tactical_evidence_identity != expected["tactical"]:
        raise ValueError("S11 allocator envelope tactical evidence mismatch")
    if envelope.recovery_evidence_identity != expected["recovery"]:
        raise ValueError("S11 allocator envelope recovery evidence mismatch")

    tactical_timeframe = (
        candidate.tactical_microstructure.timeframe
        if vault_id is PaperVaultId.TACTICAL
        and candidate.tactical_microstructure is not None
        else None
    )
    payload = {
        "allocator_assessment_identity": assessment.assessment_identity,
        "allocator_candidate_identity": candidate.candidate_identity,
        "asset": candidate.asset,
        "assessed_at_ms": assessment.assessed_at_ms,
        "candidate_as_of_ms": candidate.as_of_ms,
        "candidate_source_evidence_identities": candidate.source_evidence_identities,
        "canonical_paper_execution_eligible": True,
        "confluence_identity": envelope.confluence_identity,
        "cross_vault_borrowing_allowed": False,
        "eligibility_reason_codes": envelope.reason_codes,
        "event_risk_identity": envelope.event_risk_identity,
        "forced_deployment": False,
        "production_authority": False,
        "proof_version": S11_VAULT_ELIGIBILITY_VERSION,
        "real_capital": REAL_CAPITAL,
        "recovery_evidence_identity": envelope.recovery_evidence_identity,
        "starting_budget_usdt": envelope.starting_budget_usdt,
        "tactical_evidence_identity": envelope.tactical_evidence_identity,
        "tactical_timeframe": tactical_timeframe,
        "vault_id": vault_id,
    }
    return CanonicalVaultEligibilityProof(
        proof_identity=canonical_sha256(payload),
        proof_version=S11_VAULT_ELIGIBILITY_VERSION,
        allocator_assessment_identity=assessment.assessment_identity,
        allocator_candidate_identity=candidate.candidate_identity,
        vault_id=vault_id,
        asset=candidate.asset,
        candidate_as_of_ms=candidate.as_of_ms,
        assessed_at_ms=assessment.assessed_at_ms,
        starting_budget_usdt=envelope.starting_budget_usdt,
        eligibility_reason_codes=envelope.reason_codes,
        event_risk_identity=envelope.event_risk_identity,
        confluence_identity=envelope.confluence_identity,
        tactical_evidence_identity=envelope.tactical_evidence_identity,
        tactical_timeframe=tactical_timeframe,
        recovery_evidence_identity=envelope.recovery_evidence_identity,
        candidate_source_evidence_identities=candidate.source_evidence_identities,
    )


def _proof_payload(value: CanonicalVaultEligibilityProof) -> dict[str, object]:
    return {
        "allocator_assessment_identity": value.allocator_assessment_identity,
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "asset": value.asset,
        "assessed_at_ms": value.assessed_at_ms,
        "candidate_as_of_ms": value.candidate_as_of_ms,
        "candidate_source_evidence_identities": (
            value.candidate_source_evidence_identities
        ),
        "canonical_paper_execution_eligible": value.canonical_paper_execution_eligible,
        "confluence_identity": value.confluence_identity,
        "cross_vault_borrowing_allowed": value.cross_vault_borrowing_allowed,
        "eligibility_reason_codes": value.eligibility_reason_codes,
        "event_risk_identity": value.event_risk_identity,
        "forced_deployment": value.forced_deployment,
        "production_authority": value.production_authority,
        "proof_version": value.proof_version,
        "real_capital": value.real_capital,
        "recovery_evidence_identity": value.recovery_evidence_identity,
        "starting_budget_usdt": value.starting_budget_usdt,
        "tactical_evidence_identity": value.tactical_evidence_identity,
        "tactical_timeframe": value.tactical_timeframe,
        "vault_id": value.vault_id,
    }


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be non-empty sorted unique")
    for identity in values:
        _require_sha256(identity, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
