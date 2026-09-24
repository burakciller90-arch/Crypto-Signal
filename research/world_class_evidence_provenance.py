"""Typed provenance for WC7 world-class evidence review packets.

This layer does not score evidence and does not choose an edge verdict. It binds
each WC7 claim to an allowed evidence source class, or to an explicit blocker
boundary, so a free-form note/hash cannot silently masquerade as satisfied
world-class evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.world_class_evidence_review import (
    REAL_CAPITAL,
    WC7EvidenceClaim,
    WC7EvidenceDimension,
    WC7EvidenceReview,
    WC7EvidenceStatus,
)

WC7_PROVENANCE_ENGINE_VERSION = "wc7-typed-evidence-provenance-v1/1"
WC7_PROVENANCE_SCHEMA_VERSION = "wc7-typed-evidence-provenance-schema-v1/1"


class WC7EvidenceSourceKind(StrEnum):
    RUNTIME_ACCEPTANCE = "runtime_acceptance"
    WC2_PREREGISTERED_FORWARD = "wc2_preregistered_forward"
    PROBABILITY_CALIBRATION = "probability_calibration"
    PROBABILITY_NOT_USED_BOUNDARY = "probability_not_used_boundary"
    WC2_COST_ADJUSTED_ECONOMICS = "wc2_cost_adjusted_economics"
    WC2_DRAWDOWN_EVIDENCE = "wc2_drawdown_evidence"
    WC4_REGIME_RESEARCH = "wc4_regime_research"
    FAIL_CLOSED_TRANSPARENCY = "fail_closed_transparency"
    WC6_SANDBOX_TESTNET_DOSSIER = "wc6_sandbox_testnet_dossier"
    HUMAN_USABILITY_STUDY = "human_usability_study"
    MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"
    NOT_MEASURED_BOUNDARY = "not_measured_boundary"
    EXTERNAL_DEPENDENCY_BOUNDARY = "external_dependency_boundary"


_EVIDENCE_SOURCE_BY_DIMENSION: dict[
    WC7EvidenceDimension,
    WC7EvidenceSourceKind,
] = {
    WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY: (
        WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE
    ),
    WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY: (
        WC7EvidenceSourceKind.WC2_PREREGISTERED_FORWARD
    ),
    WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED: (
        WC7EvidenceSourceKind.PROBABILITY_CALIBRATION
    ),
    WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY: (
        WC7EvidenceSourceKind.WC2_COST_ADJUSTED_ECONOMICS
    ),
    WC7EvidenceDimension.CONTROLLED_DRAWDOWN: (
        WC7EvidenceSourceKind.WC2_DRAWDOWN_EVIDENCE
    ),
    WC7EvidenceDimension.REGIME_ROBUSTNESS: (
        WC7EvidenceSourceKind.WC4_REGIME_RESEARCH
    ),
    WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY: (
        WC7EvidenceSourceKind.FAIL_CLOSED_TRANSPARENCY
    ),
    WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE: (
        WC7EvidenceSourceKind.WC6_SANDBOX_TESTNET_DOSSIER
    ),
    WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY: (
        WC7EvidenceSourceKind.HUMAN_USABILITY_STUDY
    ),
}


_BLOCKER_SOURCE_BY_STATUS: dict[WC7EvidenceStatus, WC7EvidenceSourceKind] = {
    WC7EvidenceStatus.MISSING: WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
    WC7EvidenceStatus.NOT_MEASURED: WC7EvidenceSourceKind.NOT_MEASURED_BOUNDARY,
    WC7EvidenceStatus.EXTERNAL_DEPENDENCY: (
        WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY
    ),
}


@dataclass(frozen=True, slots=True)
class WC7EvidenceProvenance:
    provenance_identity: str
    schema_version: str
    engine_version: str
    claim_identity: str
    dimension: WC7EvidenceDimension
    claim_status: WC7EvidenceStatus
    source_kind: WC7EvidenceSourceKind
    source_artifact_identity: str | None
    blocker_boundary_identity: str | None
    source_reference: str
    observed_at_ms: int
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(
            self.provenance_identity,
            "WC7 provenance identity",
        )
        _require_sha256(self.claim_identity, "WC7 claim identity")
        if self.schema_version != WC7_PROVENANCE_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 provenance schema")
        if self.engine_version != WC7_PROVENANCE_ENGINE_VERSION:
            raise ValueError("unsupported WC7 provenance engine")
        if not self.source_reference.strip():
            raise ValueError("WC7 provenance source reference must be non-empty")
        if self.observed_at_ms < 0:
            raise ValueError("WC7 provenance observation time must be non-negative")
        if self.source_artifact_identity is not None:
            _require_sha256(
                self.source_artifact_identity,
                "WC7 source artifact identity",
            )
        if self.blocker_boundary_identity is not None:
            _require_sha256(
                self.blocker_boundary_identity,
                "WC7 blocker boundary identity",
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _validate_source_semantics(
            dimension=self.dimension,
            status=self.claim_status,
            source_kind=self.source_kind,
            source_artifact_identity=self.source_artifact_identity,
            blocker_boundary_identity=self.blocker_boundary_identity,
        )
        if self.provenance_identity != canonical_sha256(
            _provenance_payload(self)
        ):
            raise ValueError("WC7 provenance identity mismatch")


@dataclass(frozen=True, slots=True)
class WC7EvidencePacket:
    packet_identity: str
    schema_version: str
    engine_version: str
    review_identity: str
    provenances: tuple[WC7EvidenceProvenance, ...]
    human_review_required: bool = True
    automatic_edge_verdict: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.packet_identity, "WC7 packet identity")
        _require_sha256(self.review_identity, "WC7 review identity")
        if self.schema_version != WC7_PROVENANCE_SCHEMA_VERSION:
            raise ValueError("unsupported WC7 packet schema")
        if self.engine_version != WC7_PROVENANCE_ENGINE_VERSION:
            raise ValueError("unsupported WC7 packet engine")
        dimensions = tuple(item.dimension for item in self.provenances)
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("WC7 packet cannot duplicate evidence dimensions")
        if set(dimensions) != set(WC7EvidenceDimension):
            raise ValueError("WC7 packet requires exact evidence dimension set")
        if tuple(sorted(dimensions, key=lambda item: item.value)) != dimensions:
            raise ValueError("WC7 packet provenances must be canonical-order")
        if not self.human_review_required:
            raise ValueError("WC7 packet must preserve human review boundary")
        if self.automatic_edge_verdict or self.production_authority:
            raise ValueError("WC7 packet grants no auto-verdict/production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.packet_identity != canonical_sha256(_packet_payload(self)):
            raise ValueError("WC7 evidence packet identity mismatch")


def build_wc7_evidence_provenance(
    claim: WC7EvidenceClaim,
    *,
    source_kind: WC7EvidenceSourceKind,
    source_reference: str,
    observed_at_ms: int,
    source_artifact_identity: str | None = None,
    blocker_boundary_identity: str | None = None,
) -> WC7EvidenceProvenance:
    """Bind one claim to an allowed typed evidence source or blocker."""

    if (
        source_artifact_identity is not None
        and claim.evidence_identity != source_artifact_identity
    ):
        raise ValueError("WC7 claim/source artifact identity mismatch")
    if source_artifact_identity is None and claim.evidence_identity is not None:
        raise ValueError(
            "WC7 claim evidence identity requires exact source artifact identity"
        )
    _validate_source_semantics(
        dimension=claim.dimension,
        status=claim.status,
        source_kind=source_kind,
        source_artifact_identity=source_artifact_identity,
        blocker_boundary_identity=blocker_boundary_identity,
    )
    payload = {
        "blocker_boundary_identity": blocker_boundary_identity,
        "claim_identity": claim.claim_identity,
        "claim_status": claim.status,
        "dimension": claim.dimension,
        "engine_version": WC7_PROVENANCE_ENGINE_VERSION,
        "observed_at_ms": observed_at_ms,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC7_PROVENANCE_SCHEMA_VERSION,
        "source_artifact_identity": source_artifact_identity,
        "source_kind": source_kind,
        "source_reference": source_reference,
    }
    return WC7EvidenceProvenance(
        provenance_identity=canonical_sha256(payload),
        schema_version=WC7_PROVENANCE_SCHEMA_VERSION,
        engine_version=WC7_PROVENANCE_ENGINE_VERSION,
        claim_identity=claim.claim_identity,
        dimension=claim.dimension,
        claim_status=claim.status,
        source_kind=source_kind,
        source_artifact_identity=source_artifact_identity,
        blocker_boundary_identity=blocker_boundary_identity,
        source_reference=source_reference,
        observed_at_ms=observed_at_ms,
        real_capital=REAL_CAPITAL,
    )


def build_wc7_evidence_packet(
    review: WC7EvidenceReview,
    *,
    provenances: tuple[WC7EvidenceProvenance, ...],
) -> WC7EvidencePacket:
    """Bind an existing fail-closed review to exact typed source provenance."""

    ordered = tuple(sorted(provenances, key=lambda item: item.dimension.value))
    by_dimension = {item.dimension: item for item in ordered}
    if len(by_dimension) != len(ordered):
        raise ValueError("WC7 packet cannot duplicate provenance dimensions")
    if set(by_dimension) != set(WC7EvidenceDimension):
        raise ValueError("WC7 packet requires exact evidence dimension set")

    for claim in review.claims:
        provenance = by_dimension[claim.dimension]
        if provenance.claim_identity != claim.claim_identity:
            raise ValueError("WC7 packet claim/provenance identity mismatch")
        if provenance.claim_status is not claim.status:
            raise ValueError("WC7 packet claim/provenance status mismatch")
        if provenance.source_artifact_identity != claim.evidence_identity:
            raise ValueError("WC7 packet claim/source artifact mismatch")

    payload = {
        "automatic_edge_verdict": False,
        "engine_version": WC7_PROVENANCE_ENGINE_VERSION,
        "human_review_required": True,
        "production_authority": False,
        "provenances": ordered,
        "real_capital": REAL_CAPITAL,
        "review_identity": review.review_identity,
        "schema_version": WC7_PROVENANCE_SCHEMA_VERSION,
    }
    return WC7EvidencePacket(
        packet_identity=canonical_sha256(payload),
        schema_version=WC7_PROVENANCE_SCHEMA_VERSION,
        engine_version=WC7_PROVENANCE_ENGINE_VERSION,
        review_identity=review.review_identity,
        provenances=ordered,
        human_review_required=True,
        automatic_edge_verdict=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


def _validate_source_semantics(
    *,
    dimension: WC7EvidenceDimension,
    status: WC7EvidenceStatus,
    source_kind: WC7EvidenceSourceKind,
    source_artifact_identity: str | None,
    blocker_boundary_identity: str | None,
) -> None:
    blocker_kind = _BLOCKER_SOURCE_BY_STATUS.get(status)
    if blocker_kind is not None:
        if source_kind is not blocker_kind:
            raise ValueError("WC7 blocker status/source kind mismatch")
        if source_artifact_identity is not None:
            raise ValueError("WC7 blocker provenance cannot invent artifact evidence")
        return

    if status is WC7EvidenceStatus.NOT_APPLICABLE:
        if dimension is not (
            WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
        ):
            raise ValueError("WC7 NOT_APPLICABLE is only valid for calibration")
        if source_kind is not (
            WC7EvidenceSourceKind.PROBABILITY_NOT_USED_BOUNDARY
        ):
            raise ValueError("WC7 calibration N/A requires probability-use boundary")
        if source_artifact_identity is None:
            raise ValueError("WC7 calibration N/A requires boundary artifact")
        if blocker_boundary_identity is not None:
            raise ValueError("WC7 calibration N/A cannot carry blocker boundary")
        return

    if status not in {
        WC7EvidenceStatus.SATISFIED,
        WC7EvidenceStatus.PARTIAL,
        WC7EvidenceStatus.NEGATIVE,
    }:
        raise ValueError("unsupported WC7 provenance status")

    expected_kind = _EVIDENCE_SOURCE_BY_DIMENSION[dimension]
    if source_kind is not expected_kind:
        raise ValueError("WC7 evidence dimension/source kind mismatch")
    if source_artifact_identity is None:
        raise ValueError("WC7 evidenced status requires source artifact identity")
    if blocker_boundary_identity is not None:
        raise ValueError("WC7 evidenced status cannot carry blocker boundary")


def _provenance_payload(
    provenance: WC7EvidenceProvenance,
) -> dict[str, object]:
    return {
        "blocker_boundary_identity": provenance.blocker_boundary_identity,
        "claim_identity": provenance.claim_identity,
        "claim_status": provenance.claim_status,
        "dimension": provenance.dimension,
        "engine_version": provenance.engine_version,
        "observed_at_ms": provenance.observed_at_ms,
        "real_capital": provenance.real_capital,
        "schema_version": provenance.schema_version,
        "source_artifact_identity": provenance.source_artifact_identity,
        "source_kind": provenance.source_kind,
        "source_reference": provenance.source_reference,
    }


def _packet_payload(packet: WC7EvidencePacket) -> dict[str, object]:
    return {
        "automatic_edge_verdict": packet.automatic_edge_verdict,
        "engine_version": packet.engine_version,
        "human_review_required": packet.human_review_required,
        "production_authority": packet.production_authority,
        "provenances": packet.provenances,
        "real_capital": packet.real_capital,
        "review_identity": packet.review_identity,
        "schema_version": packet.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
