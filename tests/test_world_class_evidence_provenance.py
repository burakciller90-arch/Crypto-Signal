"""WC7 typed evidence-provenance acceptance."""

from __future__ import annotations

import hashlib
import inspect

import pytest

from research import world_class_evidence_provenance
from research.world_class_evidence_provenance import (
    WC7EvidenceSourceKind,
    build_wc7_evidence_packet,
    build_wc7_evidence_provenance,
)
from research.world_class_evidence_review import (
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    WC7MachineReadiness,
    WC7ReviewConclusion,
    build_wc7_evidence_claim,
    build_wc7_evidence_review,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _claim(
    dimension: WC7EvidenceDimension,
    status: WC7EvidenceStatus,
    *,
    tag: str,
):
    if status in {
        WC7EvidenceStatus.MISSING,
        WC7EvidenceStatus.NOT_MEASURED,
        WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
    }:
        evidence_identity = None
    else:
        evidence_identity = _sha(f"{tag}:{dimension.value}")
    return build_wc7_evidence_claim(
        dimension=dimension,
        status=status,
        evidence_note=f"{tag}: {dimension.value}",
        evidence_identity=evidence_identity,
    )


def _current_frontier():
    claims = (
        _claim(
            WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY,
            WC7EvidenceStatus.SATISFIED,
            tag="runtime",
        ),
        _claim(
            WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
            WC7EvidenceStatus.MISSING,
            tag="wc2-open",
        ),
        _claim(
            WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED,
            WC7EvidenceStatus.NOT_APPLICABLE,
            tag="probability-not-used",
        ),
        _claim(
            WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
            WC7EvidenceStatus.MISSING,
            tag="economics-open",
        ),
        _claim(
            WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
            WC7EvidenceStatus.MISSING,
            tag="drawdown-open",
        ),
        _claim(
            WC7EvidenceDimension.REGIME_ROBUSTNESS,
            WC7EvidenceStatus.MISSING,
            tag="regime-open",
        ),
        _claim(
            WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY,
            WC7EvidenceStatus.SATISFIED,
            tag="fail-closed",
        ),
        _claim(
            WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
            WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
            tag="wc6-external",
        ),
        _claim(
            WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
            WC7EvidenceStatus.NOT_MEASURED,
            tag="human-usability",
        ),
    )
    review = build_wc7_evidence_review(
        claims=claims,
        probability_claims_used=False,
    )
    by_dimension = {item.dimension: item for item in review.claims}
    provenances = (
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY],
            source_kind=WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE,
            source_artifact_identity=by_dimension[
                WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY
            ].evidence_identity,
            source_reference="WC0/WC1 accepted runtime rails",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="WC2 preregistered sufficiency remains open",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[
                WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
            ],
            source_kind=WC7EvidenceSourceKind.PROBABILITY_NOT_USED_BOUNDARY,
            source_artifact_identity=by_dimension[
                WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
            ].evidence_identity,
            source_reference="no probability claim is used by current review",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="WC2/WC3 cost-adjusted conclusion not available",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.CONTROLLED_DRAWDOWN],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="WC3 drawdown conclusion not available",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.REGIME_ROBUSTNESS],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="durable regime-level edge not established",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[
                WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY
            ],
            source_kind=WC7EvidenceSourceKind.FAIL_CLOSED_TRANSPARENCY,
            source_artifact_identity=by_dimension[
                WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY
            ].evidence_identity,
            source_reference="accepted fail-closed Product/research semantics",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE],
            source_kind=WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY,
            source_reference="WC6 external sandbox/testnet evidence unavailable",
            observed_at_ms=1,
        ),
        build_wc7_evidence_provenance(
            by_dimension[
                WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY
            ],
            source_kind=WC7EvidenceSourceKind.NOT_MEASURED_BOUNDARY,
            source_reference="human <=10-second usability remains not measured",
            observed_at_ms=1,
        ),
    )
    return review, provenances


def test_wc7_current_frontier_packet_is_deterministic_and_insufficient() -> None:
    review, provenances = _current_frontier()
    first = build_wc7_evidence_packet(
        review,
        provenances=provenances,
    )
    second = build_wc7_evidence_packet(
        review,
        provenances=tuple(reversed(provenances)),
    )

    assert first == second
    assert first.review_identity == review.review_identity
    assert review.machine_readiness is WC7MachineReadiness.INSUFFICIENT_EVIDENCE
    assert review.machine_conclusion is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    assert first.human_review_required is True
    assert first.automatic_edge_verdict is False
    assert first.production_authority is False
    assert first.real_capital == 0


def test_wc7_usability_satisfied_cannot_use_runtime_or_freeform_source() -> None:
    claim = _claim(
        WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
        WC7EvidenceStatus.SATISFIED,
        tag="usability",
    )

    with pytest.raises(ValueError, match="dimension/source kind"):
        build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE,
            source_artifact_identity=claim.evidence_identity,
            source_reference="runtime acceptance is not a human usability study",
            observed_at_ms=2,
        )


def test_wc7_capital_lineage_satisfied_requires_sandbox_testnet_dossier() -> None:
    claim = _claim(
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        WC7EvidenceStatus.SATISFIED,
        tag="capital",
    )

    with pytest.raises(ValueError, match="dimension/source kind"):
        build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.FAIL_CLOSED_TRANSPARENCY,
            source_artifact_identity=claim.evidence_identity,
            source_reference="paper/lab transparency is not venue evidence",
            observed_at_ms=2,
        )

    provenance = build_wc7_evidence_provenance(
        claim,
        source_kind=WC7EvidenceSourceKind.WC6_SANDBOX_TESTNET_DOSSIER,
        source_artifact_identity=claim.evidence_identity,
        source_reference="accepted sandbox/testnet execution dossier",
        observed_at_ms=2,
    )
    assert provenance.source_kind is (
        WC7EvidenceSourceKind.WC6_SANDBOX_TESTNET_DOSSIER
    )


def test_wc7_blocker_status_cannot_invent_artifact_identity() -> None:
    claim = build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
        status=WC7EvidenceStatus.MISSING,
        evidence_note="drawdown evidence is genuinely missing",
        evidence_identity=_sha("invented-blocker-artifact"),
    )

    with pytest.raises(ValueError, match="blocker provenance cannot invent"):
        build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_artifact_identity=claim.evidence_identity,
            source_reference="must remain missing",
            observed_at_ms=3,
        )


def test_wc7_probability_not_applicable_requires_explicit_not_used_boundary() -> None:
    claim = _claim(
        WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED,
        WC7EvidenceStatus.NOT_APPLICABLE,
        tag="probability",
    )

    with pytest.raises(ValueError, match="requires probability-use boundary"):
        build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.PROBABILITY_CALIBRATION,
            source_artifact_identity=claim.evidence_identity,
            source_reference="wrong source class",
            observed_at_ms=4,
        )


def test_wc7_packet_rejects_provenance_from_different_claim() -> None:
    review, provenances = _current_frontier()
    runtime = next(
        item
        for item in review.claims
        if item.dimension
        is WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY
    )
    replacement_claim = _claim(
        WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY,
        WC7EvidenceStatus.SATISFIED,
        tag="different-runtime",
    )
    replacement = build_wc7_evidence_provenance(
        replacement_claim,
        source_kind=WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE,
        source_artifact_identity=replacement_claim.evidence_identity,
        source_reference="different runtime artifact",
        observed_at_ms=5,
    )
    assert replacement.claim_identity != runtime.claim_identity
    replaced = tuple(
        replacement
        if item.dimension
        is WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY
        else item
        for item in provenances
    )

    with pytest.raises(ValueError, match="claim/provenance identity mismatch"):
        build_wc7_evidence_packet(review, provenances=replaced)


def test_wc7_provenance_source_has_no_runtime_order_or_verdict_surface() -> None:
    source = inspect.getsource(world_class_evidence_provenance).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "subprocess",
        "launchctl",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "private_key",
        "edge_supported =",
        "automatic_edge_verdict: bool = true",
        "production_authority: bool = true",
    )
    assert all(token not in source for token in forbidden)
    assert "human_usability_study" in source
    assert "wc6_sandbox_testnet_dossier" in source
    assert "missing_required_evidence" in source
    assert world_class_evidence_provenance.REAL_CAPITAL == 0
