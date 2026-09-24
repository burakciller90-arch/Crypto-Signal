"""Read-only canonical subsystem adapters for WC7 evidence review.

Adapters translate accepted subsystem artifacts into WC7 claim + provenance
pairs. They do not mutate subsystem state, do not infer missing evidence, and do
not select a final edge verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2ReviewReadiness,
    WC2ReviewStatus,
)
from crypto_signal.paper.execution_lab_sandbox import (
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
    WC6SandboxEvidenceSemantic,
)
from research.world_class_evidence_provenance import (
    WC7EvidenceProvenance,
    WC7EvidenceSourceKind,
    build_wc7_evidence_provenance,
)
from research.world_class_evidence_review import (
    REAL_CAPITAL,
    WC7EvidenceClaim,
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    build_wc7_evidence_claim,
)


@dataclass(frozen=True, slots=True)
class WC7AdaptedEvidence:
    claim: WC7EvidenceClaim
    provenance: WC7EvidenceProvenance
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.claim.dimension is not self.provenance.dimension:
            raise ValueError("WC7 adapted claim/provenance dimension mismatch")
        if self.claim.claim_identity != self.provenance.claim_identity:
            raise ValueError("WC7 adapted claim/provenance identity mismatch")
        if self.claim.status is not self.provenance.claim_status:
            raise ValueError("WC7 adapted claim/provenance status mismatch")
        if self.claim.evidence_identity != self.provenance.source_artifact_identity:
            raise ValueError("WC7 adapted claim/source artifact mismatch")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")


def adapt_wc2_untouched_forward_readiness(
    readiness: WC2ReviewReadiness,
    *,
    observed_at_ms: int,
) -> WC7AdaptedEvidence:
    """Map preregistered WC2 review sufficiency into WC7 history evidence."""

    if readiness.real_capital != REAL_CAPITAL or readiness.production_authority:
        raise ValueError("WC2 readiness cannot carry production authority")
    if observed_at_ms < 0:
        raise ValueError("WC7 adapter observation time must be non-negative")

    if readiness.status is WC2ReviewStatus.REVIEW_ELIGIBLE:
        claim = build_wc7_evidence_claim(
            dimension=WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
            status=WC7EvidenceStatus.SATISFIED,
            evidence_identity=readiness.readiness_identity,
            evidence_note=(
                "WC2 preregistered evidence sufficiency is REVIEW_ELIGIBLE; "
                "this satisfies history sufficiency only and is not an edge/"
                "profitability claim"
            ),
        )
        provenance = build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.WC2_PREREGISTERED_FORWARD,
            source_artifact_identity=readiness.readiness_identity,
            source_reference=(
                "WC2ReviewReadiness:"
                f"{readiness.readiness_identity}:REVIEW_ELIGIBLE"
            ),
            observed_at_ms=observed_at_ms,
        )
    elif readiness.status is WC2ReviewStatus.INSUFFICIENT_EVIDENCE:
        reasons = ",".join(readiness.reason_codes)
        claim = build_wc7_evidence_claim(
            dimension=WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
            status=WC7EvidenceStatus.MISSING,
            evidence_note=(
                "WC2 preregistered evidence sufficiency is incomplete; "
                f"blockers={reasons}"
            ),
        )
        provenance = build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            blocker_boundary_identity=readiness.readiness_identity,
            source_reference=(
                "WC2ReviewReadiness:"
                f"{readiness.readiness_identity}:INSUFFICIENT_EVIDENCE:"
                f"{reasons}"
            ),
            observed_at_ms=observed_at_ms,
        )
    else:
        raise ValueError("unsupported WC2 review readiness status")

    return WC7AdaptedEvidence(
        claim=claim,
        provenance=provenance,
        real_capital=REAL_CAPITAL,
    )


def adapt_wc6_sandbox_boundary(
    evidence: WC6SandboxBoundaryEvidence,
    *,
    observed_at_ms: int,
) -> WC7AdaptedEvidence:
    """Map the accepted NOT_CONFIGURED WC6 boundary into an external blocker."""

    if observed_at_ms < 0:
        raise ValueError("WC7 adapter observation time must be non-negative")
    if evidence.real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")
    if (
        evidence.semantic
        is not WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
    ):
        raise ValueError("unsupported WC6 sandbox evidence semantic")
    if evidence.dispatch_status is not (
        WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED
    ):
        raise ValueError("WC6 adapter only accepts blocked NOT_CONFIGURED evidence")
    if (
        evidence.dispatch_attempted
        or evidence.venue_acknowledgement_identity is not None
        or evidence.venue_fill_identities
        or evidence.endpoint_bound
        or evidence.credential_bound
        or evidence.transport_bound
        or evidence.network_authority
        or evidence.live_order_authority
        or evidence.production_authority
    ):
        raise ValueError("WC6 sandbox boundary cannot be upgraded by adapter")

    claim = build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        status=WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
        evidence_note=(
            "WC6 sandbox/testnet boundary is accepted but NOT_CONFIGURED; "
            "no venue acknowledgement/fill/recovery evidence exists"
        ),
    )
    provenance = build_wc7_evidence_provenance(
        claim,
        source_kind=WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY,
        blocker_boundary_identity=evidence.evidence_identity,
        source_reference=(
            "WC6SandboxBoundaryEvidence:"
            f"{evidence.evidence_identity}:BLOCKED_NOT_CONFIGURED"
        ),
        observed_at_ms=observed_at_ms,
    )
    return WC7AdaptedEvidence(
        claim=claim,
        provenance=provenance,
        real_capital=REAL_CAPITAL,
    )
