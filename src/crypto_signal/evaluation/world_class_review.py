"""Fail-closed WC7 evidence-review readiness manifest.

This module does not decide whether Crypto Signal has an edge and does not score,
rank, promote, deploy, or trade. It only answers whether the preregistered
evidence domains required for a later human/scientific WC7 review are present.

Missing/open/not-measured evidence forces INSUFFICIENT_EVIDENCE. Even a complete
manifest stops at READY_FOR_EVIDENCE_REVIEW_NOT_CONCLUSION.
REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2ReviewReadiness,
    WC2ReviewStatus,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_sandbox import (
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
)
from crypto_signal.paper.models import REAL_CAPITAL

WC7_REVIEW_ENGINE_VERSION = "wc7-evidence-review-readiness-v1/1"
WC7_REVIEW_SCHEMA_VERSION = "wc7-evidence-review-readiness-schema-v1/1"


class WC7EvidenceDomain(StrEnum):
    RUNTIME_RELIABILITY = "runtime_reliability"
    UNTOUCHED_FORWARD = "untouched_forward"
    CALIBRATION = "calibration"
    COST_ADJUSTED_PERFORMANCE = "cost_adjusted_performance"
    RISK_CONTROL = "risk_control"
    ROBUSTNESS = "robustness"
    ABSTENTION_FAILURE_CASES = "abstention_failure_cases"
    EXECUTION_LINEAGE = "execution_lineage"
    USABILITY = "usability"


class WC7EvidenceStatus(StrEnum):
    ACCEPTED = "accepted"
    OPEN = "open"
    NOT_MEASURED = "not_measured"
    MISSING = "missing"


class WC7ReviewReadinessStatus(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    READY_FOR_EVIDENCE_REVIEW_NOT_CONCLUSION = (
        "ready_for_evidence_review_not_conclusion"
    )


@dataclass(frozen=True, slots=True)
class WC7EvidenceReference:
    reference_identity: str
    schema_version: str
    engine_version: str
    domain: WC7EvidenceDomain
    status: WC7EvidenceStatus
    source_semantic: str
    evidence_identity: str | None
    blocker_detail: str | None
    performance_threshold_applied: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.reference_identity, "WC7 reference identity")
        if self.schema_version != WC7_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 evidence-reference schema")
        if self.engine_version != WC7_REVIEW_ENGINE_VERSION:
            raise ValueError("unsupported WC7 evidence-reference engine")
        if not self.source_semantic.strip():
            raise ValueError("WC7 evidence source semantic must be non-empty")
        if self.evidence_identity is not None:
            _require_sha256(self.evidence_identity, "WC7 source evidence identity")
        if self.status is WC7EvidenceStatus.ACCEPTED:
            if self.evidence_identity is None:
                raise ValueError("accepted WC7 evidence requires exact identity")
            if self.blocker_detail is not None:
                raise ValueError("accepted WC7 evidence cannot retain blocker")
        else:
            if not self.blocker_detail or not self.blocker_detail.strip():
                raise ValueError("non-accepted WC7 evidence requires blocker detail")
        if self.performance_threshold_applied:
            raise ValueError(
                "WC7 readiness cannot invent or apply a performance winner threshold"
            )
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC7 evidence reference cannot grant authority")
        if self.reference_identity != canonical_sha256(_reference_payload(self)):
            raise ValueError("WC7 evidence-reference identity mismatch")


@dataclass(frozen=True, slots=True)
class WC7ReviewReadiness:
    readiness_identity: str
    schema_version: str
    engine_version: str
    status: WC7ReviewReadinessStatus
    references: tuple[WC7EvidenceReference, ...]
    blocker_codes: tuple[str, ...]
    semantic: str = "readiness_only_not_edge_or_world_class_conclusion"
    edge_supported_claim: bool = False
    world_class_claim: bool = False
    automatic_promotion: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.readiness_identity, "WC7 readiness identity")
        if self.schema_version != WC7_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 readiness schema")
        if self.engine_version != WC7_REVIEW_ENGINE_VERSION:
            raise ValueError("unsupported WC7 readiness engine")
        if self.semantic != "readiness_only_not_edge_or_world_class_conclusion":
            raise ValueError("unsupported WC7 readiness semantic")

        required_domains = tuple(WC7EvidenceDomain)
        actual_domains = tuple(item.domain for item in self.references)
        if actual_domains != required_domains:
            raise ValueError(
                "WC7 readiness requires every evidence domain in canonical order"
            )
        if self.blocker_codes != tuple(sorted(set(self.blocker_codes))):
            raise ValueError("WC7 blocker codes must be canonical")

        expected_blockers = tuple(
            sorted(
                f"{item.domain.value}:{item.status.value}"
                for item in self.references
                if item.status is not WC7EvidenceStatus.ACCEPTED
            )
        )
        if self.blocker_codes != expected_blockers:
            raise ValueError("WC7 blocker codes do not match evidence statuses")

        if self.status is WC7ReviewReadinessStatus.INSUFFICIENT_EVIDENCE:
            if not self.blocker_codes:
                raise ValueError(
                    "WC7 insufficient-evidence readiness requires blockers"
                )
        elif self.status is (
            WC7ReviewReadinessStatus.READY_FOR_EVIDENCE_REVIEW_NOT_CONCLUSION
        ):
            if self.blocker_codes:
                raise ValueError("WC7 review-ready state cannot retain blockers")
        else:
            raise ValueError("unsupported WC7 readiness status")

        if (
            self.edge_supported_claim
            or self.world_class_claim
            or self.automatic_promotion
            or self.production_authority
        ):
            raise ValueError(
                "WC7 readiness cannot claim edge/world-class or grant authority"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.readiness_identity != canonical_sha256(_readiness_payload(self)):
            raise ValueError("WC7 readiness identity mismatch")


def build_wc7_evidence_reference(
    *,
    domain: WC7EvidenceDomain,
    status: WC7EvidenceStatus,
    source_semantic: str,
    evidence_identity: str | None,
    blocker_detail: str | None,
) -> WC7EvidenceReference:
    """Build one exact evidence-domain reference without performance judgement."""

    payload = {
        "blocker_detail": blocker_detail,
        "domain": domain,
        "engine_version": WC7_REVIEW_ENGINE_VERSION,
        "evidence_identity": evidence_identity,
        "performance_threshold_applied": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC7_REVIEW_SCHEMA_VERSION,
        "source_semantic": source_semantic,
        "status": status,
    }
    return WC7EvidenceReference(
        reference_identity=canonical_sha256(payload),
        schema_version=WC7_REVIEW_SCHEMA_VERSION,
        engine_version=WC7_REVIEW_ENGINE_VERSION,
        domain=domain,
        status=status,
        source_semantic=source_semantic,
        evidence_identity=evidence_identity,
        blocker_detail=blocker_detail,
        performance_threshold_applied=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def build_wc7_untouched_forward_reference(
    readiness: WC2ReviewReadiness,
) -> WC7EvidenceReference:
    """Map the preregistered WC2 readiness gate into WC7 without reinterpretation."""

    if readiness.production_authority or readiness.real_capital != REAL_CAPITAL:
        raise ValueError("WC2 readiness carries forbidden authority")
    if readiness.status is WC2ReviewStatus.REVIEW_ELIGIBLE:
        status = WC7EvidenceStatus.ACCEPTED
        blocker_detail = None
    else:
        status = WC7EvidenceStatus.OPEN
        blocker_detail = (
            "WC2 untouched-forward review sufficiency not met: "
            + ",".join(readiness.reason_codes)
        )
    return build_wc7_evidence_reference(
        domain=WC7EvidenceDomain.UNTOUCHED_FORWARD,
        status=status,
        source_semantic=readiness.semantic,
        evidence_identity=readiness.readiness_identity,
        blocker_detail=blocker_detail,
    )


def build_wc7_execution_lineage_reference(
    evidence: WC6SandboxBoundaryEvidence,
) -> WC7EvidenceReference:
    """Map accepted WC6 fail-closed boundary truth without inventing venue evidence."""

    if evidence.production_authority or evidence.real_capital != REAL_CAPITAL:
        raise ValueError("WC6 sandbox evidence carries forbidden authority")
    if evidence.dispatch_status is WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED:
        return build_wc7_evidence_reference(
            domain=WC7EvidenceDomain.EXECUTION_LINEAGE,
            status=WC7EvidenceStatus.OPEN,
            source_semantic=evidence.semantic.value,
            evidence_identity=evidence.evidence_identity,
            blocker_detail=(
                "WC6 sandbox/testnet transport is NOT_CONFIGURED; "
                "no venue acknowledgement/fill/recovery evidence exists"
            ),
        )
    raise ValueError(
        "unsupported WC6 sandbox evidence state; explicit reviewed mapping required"
    )


def evaluate_wc7_review_readiness(
    references: tuple[WC7EvidenceReference, ...],
) -> WC7ReviewReadiness:
    """Evaluate only evidence availability/readiness, never edge performance."""

    by_domain: dict[WC7EvidenceDomain, WC7EvidenceReference] = {}
    for item in references:
        if item.domain in by_domain:
            raise ValueError(f"duplicate WC7 evidence domain: {item.domain.value}")
        by_domain[item.domain] = item

    required_domains = tuple(WC7EvidenceDomain)
    missing_domains = tuple(
        domain for domain in required_domains if domain not in by_domain
    )
    if missing_domains:
        raise ValueError(
            "WC7 readiness requires explicit references for every domain: "
            + ",".join(domain.value for domain in missing_domains)
        )

    canonical_references = tuple(by_domain[domain] for domain in required_domains)
    blockers = tuple(
        sorted(
            f"{item.domain.value}:{item.status.value}"
            for item in canonical_references
            if item.status is not WC7EvidenceStatus.ACCEPTED
        )
    )
    status = (
        WC7ReviewReadinessStatus.INSUFFICIENT_EVIDENCE
        if blockers
        else WC7ReviewReadinessStatus.READY_FOR_EVIDENCE_REVIEW_NOT_CONCLUSION
    )
    payload = {
        "automatic_promotion": False,
        "blocker_codes": blockers,
        "edge_supported_claim": False,
        "engine_version": WC7_REVIEW_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "references": canonical_references,
        "schema_version": WC7_REVIEW_SCHEMA_VERSION,
        "semantic": "readiness_only_not_edge_or_world_class_conclusion",
        "status": status,
        "world_class_claim": False,
    }
    return WC7ReviewReadiness(
        readiness_identity=canonical_sha256(payload),
        schema_version=WC7_REVIEW_SCHEMA_VERSION,
        engine_version=WC7_REVIEW_ENGINE_VERSION,
        status=status,
        references=canonical_references,
        blocker_codes=blockers,
        semantic="readiness_only_not_edge_or_world_class_conclusion",
        edge_supported_claim=False,
        world_class_claim=False,
        automatic_promotion=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _reference_payload(reference: WC7EvidenceReference) -> dict[str, object]:
    return {
        "blocker_detail": reference.blocker_detail,
        "domain": reference.domain,
        "engine_version": reference.engine_version,
        "evidence_identity": reference.evidence_identity,
        "performance_threshold_applied": reference.performance_threshold_applied,
        "production_authority": reference.production_authority,
        "real_capital": reference.real_capital,
        "schema_version": reference.schema_version,
        "source_semantic": reference.source_semantic,
        "status": reference.status,
    }


def _readiness_payload(readiness: WC7ReviewReadiness) -> dict[str, object]:
    return {
        "automatic_promotion": readiness.automatic_promotion,
        "blocker_codes": readiness.blocker_codes,
        "edge_supported_claim": readiness.edge_supported_claim,
        "engine_version": readiness.engine_version,
        "production_authority": readiness.production_authority,
        "real_capital": readiness.real_capital,
        "references": readiness.references,
        "schema_version": readiness.schema_version,
        "semantic": readiness.semantic,
        "status": readiness.status,
        "world_class_claim": readiness.world_class_claim,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
