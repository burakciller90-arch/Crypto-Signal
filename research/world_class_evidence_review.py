"""Fail-closed WC7 world-class evidence review contract.

The machine layer only decides whether the required evidence set is complete
enough for review. It never auto-selects an edge-positive or edge-negative
verdict. Human review remains explicit, evidence-bound, and REAL_CAPITAL=0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256

WC7_REVIEW_ENGINE_VERSION = "wc7-world-class-evidence-review-v1/1"
WC7_REVIEW_SCHEMA_VERSION = "wc7-world-class-evidence-review-schema-v1/1"
REAL_CAPITAL = 0


class WC7EvidenceDimension(StrEnum):
    PRODUCTION_RUNTIME_RELIABILITY = "production_runtime_reliability"
    UNTOUCHED_FORWARD_HISTORY = "untouched_forward_history"
    PROBABILITY_CALIBRATION_WHERE_USED = "probability_calibration_where_used"
    COST_ADJUSTED_EXPECTANCY = "cost_adjusted_expectancy"
    CONTROLLED_DRAWDOWN = "controlled_drawdown"
    REGIME_ROBUSTNESS = "regime_robustness"
    ABSTENTION_FAILURE_TRANSPARENCY = "abstention_failure_transparency"
    CAPITAL_EXECUTION_LINEAGE = "capital_execution_lineage"
    USABILITY_WITHOUT_HIDDEN_UNCERTAINTY = (
        "usability_without_hidden_uncertainty"
    )


class WC7EvidenceStatus(StrEnum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    NEGATIVE = "negative"
    MISSING = "missing"
    NOT_MEASURED = "not_measured"
    EXTERNAL_DEPENDENCY = "external_dependency"
    NOT_APPLICABLE = "not_applicable"


class WC7MachineReadiness(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"


class WC7ReviewConclusion(StrEnum):
    EDGE_SUPPORTED = "EDGE_SUPPORTED"
    EDGE_PARTIAL_REGIME_SPECIFIC = "EDGE_PARTIAL / regime-specific"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    EDGE_NOT_SUPPORTED = "EDGE_NOT_SUPPORTED"


@dataclass(frozen=True, slots=True)
class WC7EvidenceClaim:
    claim_identity: str
    dimension: WC7EvidenceDimension
    status: WC7EvidenceStatus
    evidence_identity: str | None
    evidence_note: str
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.claim_identity, "WC7 evidence claim identity")
        if not self.evidence_note.strip():
            raise ValueError("WC7 evidence note must be non-empty")
        if self.status in {
            WC7EvidenceStatus.SATISFIED,
            WC7EvidenceStatus.PARTIAL,
            WC7EvidenceStatus.NEGATIVE,
            WC7EvidenceStatus.NOT_APPLICABLE,
        }:
            if self.evidence_identity is None:
                raise ValueError(
                    "WC7 evidenced status requires evidence identity"
                )
            _require_sha256(
                self.evidence_identity,
                "WC7 evidence identity",
            )
        elif self.evidence_identity is not None:
            _require_sha256(
                self.evidence_identity,
                "WC7 blocker evidence identity",
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.claim_identity != canonical_sha256(_claim_payload(self)):
            raise ValueError("WC7 evidence claim identity mismatch")


@dataclass(frozen=True, slots=True)
class WC7EvidenceReview:
    review_identity: str
    schema_version: str
    engine_version: str
    probability_claims_used: bool
    claims: tuple[WC7EvidenceClaim, ...]
    machine_readiness: WC7MachineReadiness
    machine_conclusion: WC7ReviewConclusion | None
    blocking_dimensions: tuple[WC7EvidenceDimension, ...]
    human_review_required: bool = True
    automatic_edge_verdict: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.review_identity, "WC7 review identity")
        if self.schema_version != WC7_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 review schema")
        if self.engine_version != WC7_REVIEW_ENGINE_VERSION:
            raise ValueError("unsupported WC7 review engine")
        _validate_claim_set(
            claims=self.claims,
            probability_claims_used=self.probability_claims_used,
        )
        expected_blockers = _blocking_dimensions(self.claims)
        if self.blocking_dimensions != expected_blockers:
            raise ValueError("WC7 blocking dimensions mismatch")
        if expected_blockers:
            if self.machine_readiness is not (
                WC7MachineReadiness.INSUFFICIENT_EVIDENCE
            ):
                raise ValueError("WC7 incomplete evidence must fail closed")
            if self.machine_conclusion is not (
                WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
            ):
                raise ValueError(
                    "WC7 incomplete evidence conclusion must be insufficient"
                )
        else:
            if self.machine_readiness is not (
                WC7MachineReadiness.READY_FOR_HUMAN_REVIEW
            ):
                raise ValueError(
                    "WC7 complete evidence must be ready for human review"
                )
            if self.machine_conclusion is not None:
                raise ValueError(
                    "WC7 machine cannot choose final edge verdict"
                )
        if not self.human_review_required:
            raise ValueError("WC7 final conclusion requires human review")
        if self.automatic_edge_verdict or self.production_authority:
            raise ValueError("WC7 review has no automatic/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.review_identity != canonical_sha256(_review_payload(self)):
            raise ValueError("WC7 review identity mismatch")


@dataclass(frozen=True, slots=True)
class WC7HumanReviewDecision:
    decision_identity: str
    schema_version: str
    engine_version: str
    review_identity: str
    conclusion: WC7ReviewConclusion
    reviewer_role: str
    review_version: str
    decision_note: str
    reviewed_at_ms: int
    automatic_edge_verdict: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.decision_identity, "WC7 human decision identity")
        _require_sha256(self.review_identity, "WC7 review identity")
        if self.schema_version != WC7_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 decision schema")
        if self.engine_version != WC7_REVIEW_ENGINE_VERSION:
            raise ValueError("unsupported WC7 decision engine")
        for value, label in (
            (self.reviewer_role, "WC7 reviewer role"),
            (self.review_version, "WC7 review version"),
            (self.decision_note, "WC7 decision note"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.reviewed_at_ms < 0:
            raise ValueError("WC7 review timestamp must be non-negative")
        if self.automatic_edge_verdict or self.production_authority:
            raise ValueError("WC7 decision has no automatic/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.decision_identity != canonical_sha256(
            _human_decision_payload(self)
        ):
            raise ValueError("WC7 human decision identity mismatch")


def build_wc7_evidence_claim(
    *,
    dimension: WC7EvidenceDimension,
    status: WC7EvidenceStatus,
    evidence_note: str,
    evidence_identity: str | None = None,
) -> WC7EvidenceClaim:
    payload = {
        "dimension": dimension,
        "evidence_identity": evidence_identity,
        "evidence_note": evidence_note,
        "real_capital": REAL_CAPITAL,
        "status": status,
    }
    return WC7EvidenceClaim(
        claim_identity=canonical_sha256(payload),
        dimension=dimension,
        status=status,
        evidence_identity=evidence_identity,
        evidence_note=evidence_note,
        real_capital=REAL_CAPITAL,
    )


def build_wc7_evidence_review(
    *,
    claims: tuple[WC7EvidenceClaim, ...],
    probability_claims_used: bool,
) -> WC7EvidenceReview:
    ordered = tuple(sorted(claims, key=lambda item: item.dimension.value))
    _validate_claim_set(
        claims=ordered,
        probability_claims_used=probability_claims_used,
    )
    blockers = _blocking_dimensions(ordered)
    if blockers:
        readiness = WC7MachineReadiness.INSUFFICIENT_EVIDENCE
        machine_conclusion: WC7ReviewConclusion | None = (
            WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
        )
    else:
        readiness = WC7MachineReadiness.READY_FOR_HUMAN_REVIEW
        machine_conclusion = None

    payload = {
        "automatic_edge_verdict": False,
        "blocking_dimensions": blockers,
        "claims": ordered,
        "engine_version": WC7_REVIEW_ENGINE_VERSION,
        "human_review_required": True,
        "machine_conclusion": machine_conclusion,
        "machine_readiness": readiness,
        "probability_claims_used": probability_claims_used,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC7_REVIEW_SCHEMA_VERSION,
    }
    return WC7EvidenceReview(
        review_identity=canonical_sha256(payload),
        schema_version=WC7_REVIEW_SCHEMA_VERSION,
        engine_version=WC7_REVIEW_ENGINE_VERSION,
        probability_claims_used=probability_claims_used,
        claims=ordered,
        machine_readiness=readiness,
        machine_conclusion=machine_conclusion,
        blocking_dimensions=blockers,
        human_review_required=True,
        automatic_edge_verdict=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def record_wc7_human_review(
    review: WC7EvidenceReview,
    *,
    conclusion: WC7ReviewConclusion,
    reviewer_role: str,
    review_version: str,
    decision_note: str,
    reviewed_at_ms: int,
) -> WC7HumanReviewDecision:
    """Record an explicit human verdict only when evidence semantics allow it."""

    if review.machine_readiness is WC7MachineReadiness.INSUFFICIENT_EVIDENCE:
        if conclusion is not WC7ReviewConclusion.INSUFFICIENT_EVIDENCE:
            raise ValueError(
                "WC7 incomplete evidence cannot receive edge-positive/negative verdict"
            )
    else:
        statuses = tuple(item.status for item in review.claims)
        if conclusion is WC7ReviewConclusion.EDGE_SUPPORTED:
            allowed = {
                WC7EvidenceStatus.SATISFIED,
                WC7EvidenceStatus.NOT_APPLICABLE,
            }
            if any(status not in allowed for status in statuses):
                raise ValueError(
                    "EDGE_SUPPORTED requires all applicable evidence satisfied"
                )
        elif conclusion is WC7ReviewConclusion.EDGE_PARTIAL_REGIME_SPECIFIC:
            if WC7EvidenceStatus.NEGATIVE in statuses:
                raise ValueError(
                    "EDGE_PARTIAL cannot override negative evidence"
                )
            if WC7EvidenceStatus.PARTIAL not in statuses:
                raise ValueError(
                    "EDGE_PARTIAL requires explicit partial evidence"
                )
        elif conclusion is WC7ReviewConclusion.EDGE_NOT_SUPPORTED:
            if WC7EvidenceStatus.NEGATIVE not in statuses:
                raise ValueError(
                    "EDGE_NOT_SUPPORTED requires explicit negative evidence"
                )
        elif conclusion is not WC7ReviewConclusion.INSUFFICIENT_EVIDENCE:
            raise ValueError("unsupported WC7 conclusion")

    payload = {
        "automatic_edge_verdict": False,
        "conclusion": conclusion,
        "decision_note": decision_note,
        "engine_version": WC7_REVIEW_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "review_identity": review.review_identity,
        "review_version": review_version,
        "reviewed_at_ms": reviewed_at_ms,
        "reviewer_role": reviewer_role,
        "schema_version": WC7_REVIEW_SCHEMA_VERSION,
    }
    return WC7HumanReviewDecision(
        decision_identity=canonical_sha256(payload),
        schema_version=WC7_REVIEW_SCHEMA_VERSION,
        engine_version=WC7_REVIEW_ENGINE_VERSION,
        review_identity=review.review_identity,
        conclusion=conclusion,
        reviewer_role=reviewer_role,
        review_version=review_version,
        decision_note=decision_note,
        reviewed_at_ms=reviewed_at_ms,
        automatic_edge_verdict=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _validate_claim_set(
    *,
    claims: tuple[WC7EvidenceClaim, ...],
    probability_claims_used: bool,
) -> None:
    expected = set(WC7EvidenceDimension)
    dimensions = tuple(item.dimension for item in claims)
    if len(dimensions) != len(set(dimensions)):
        raise ValueError("WC7 review cannot contain duplicate dimensions")
    if set(dimensions) != expected:
        missing = sorted(item.value for item in expected - set(dimensions))
        extra = sorted(item.value for item in set(dimensions) - expected)
        raise ValueError(
            f"WC7 review requires exact dimension set; missing={missing} extra={extra}"
        )

    calibration = next(
        item
        for item in claims
        if item.dimension
        is WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
    )
    if probability_claims_used:
        if calibration.status is WC7EvidenceStatus.NOT_APPLICABLE:
            raise ValueError(
                "probability use requires applicable calibration evidence"
            )
    elif calibration.status is not WC7EvidenceStatus.NOT_APPLICABLE:
        raise ValueError(
            "no probability claims requires calibration NOT_APPLICABLE"
        )


def _blocking_dimensions(
    claims: tuple[WC7EvidenceClaim, ...],
) -> tuple[WC7EvidenceDimension, ...]:
    blocking = {
        WC7EvidenceStatus.MISSING,
        WC7EvidenceStatus.NOT_MEASURED,
        WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
    }
    return tuple(
        sorted(
            (
                item.dimension
                for item in claims
                if item.status in blocking
            ),
            key=lambda item: item.value,
        )
    )


def _claim_payload(claim: WC7EvidenceClaim) -> dict[str, object]:
    return {
        "dimension": claim.dimension,
        "evidence_identity": claim.evidence_identity,
        "evidence_note": claim.evidence_note,
        "real_capital": claim.real_capital,
        "status": claim.status,
    }


def _review_payload(review: WC7EvidenceReview) -> dict[str, object]:
    return {
        "automatic_edge_verdict": review.automatic_edge_verdict,
        "blocking_dimensions": review.blocking_dimensions,
        "claims": review.claims,
        "engine_version": review.engine_version,
        "human_review_required": review.human_review_required,
        "machine_conclusion": review.machine_conclusion,
        "machine_readiness": review.machine_readiness,
        "probability_claims_used": review.probability_claims_used,
        "production_authority": review.production_authority,
        "real_capital": review.real_capital,
        "schema_version": review.schema_version,
    }


def _human_decision_payload(
    decision: WC7HumanReviewDecision,
) -> dict[str, object]:
    return {
        "automatic_edge_verdict": decision.automatic_edge_verdict,
        "conclusion": decision.conclusion,
        "decision_note": decision.decision_note,
        "engine_version": decision.engine_version,
        "production_authority": decision.production_authority,
        "real_capital": decision.real_capital,
        "review_identity": decision.review_identity,
        "review_version": decision.review_version,
        "reviewed_at_ms": decision.reviewed_at_ms,
        "reviewer_role": decision.reviewer_role,
        "schema_version": decision.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
