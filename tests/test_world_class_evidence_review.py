"""WC7 fail-closed world-class evidence-review acceptance."""

from __future__ import annotations

import hashlib
import inspect

import pytest

from research import world_class_evidence_review
from research.world_class_evidence_review import (
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    WC7MachineReadiness,
    WC7ReviewConclusion,
    build_wc7_evidence_claim,
    build_wc7_evidence_review,
    record_wc7_human_review,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _claim(
    dimension: WC7EvidenceDimension,
    status: WC7EvidenceStatus,
    *,
    tag: str,
):
    evidence_identity = (
        None
        if status
        in {
            WC7EvidenceStatus.MISSING,
            WC7EvidenceStatus.NOT_MEASURED,
            WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
        }
        else _sha(f"evidence-{tag}-{dimension.value}")
    )
    return build_wc7_evidence_claim(
        dimension=dimension,
        status=status,
        evidence_note=f"{tag}: {dimension.value}",
        evidence_identity=evidence_identity,
    )


def _current_frontier_claims():
    return (
        _claim(
            WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY,
            WC7EvidenceStatus.SATISFIED,
            tag="accepted-runtime",
        ),
        _claim(
            WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
            WC7EvidenceStatus.MISSING,
            tag="wc2-evidence-sufficiency-open",
        ),
        _claim(
            WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED,
            WC7EvidenceStatus.NOT_APPLICABLE,
            tag="no-probability-claim",
        ),
        _claim(
            WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
            WC7EvidenceStatus.MISSING,
            tag="economic-conclusion-blocked",
        ),
        _claim(
            WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
            WC7EvidenceStatus.MISSING,
            tag="economic-conclusion-blocked",
        ),
        _claim(
            WC7EvidenceDimension.REGIME_ROBUSTNESS,
            WC7EvidenceStatus.MISSING,
            tag="durable-regime-edge-not-established",
        ),
        _claim(
            WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY,
            WC7EvidenceStatus.SATISFIED,
            tag="fail-closed-product-semantics",
        ),
        _claim(
            WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
            WC7EvidenceStatus.EXTERNAL_DEPENDENCY,
            tag="wc6-real-venue-evidence-missing",
        ),
        _claim(
            WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
            WC7EvidenceStatus.NOT_MEASURED,
            tag="human-ten-second-usability-not-measured",
        ),
    )


def _complete_claims(
    *,
    override_dimension: WC7EvidenceDimension | None = None,
    override_status: WC7EvidenceStatus | None = None,
):
    claims = []
    for dimension in WC7EvidenceDimension:
        status = (
            WC7EvidenceStatus.NOT_APPLICABLE
            if dimension
            is WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
            else WC7EvidenceStatus.SATISFIED
        )
        if dimension is override_dimension:
            assert override_status is not None
            status = override_status
        claims.append(
            _claim(
                dimension,
                status,
                tag="complete-review",
            )
        )
    return tuple(claims)


def test_wc7_current_frontier_fails_closed_to_insufficient_evidence() -> None:
    first = build_wc7_evidence_review(
        claims=_current_frontier_claims(),
        probability_claims_used=False,
    )
    second = build_wc7_evidence_review(
        claims=tuple(reversed(_current_frontier_claims())),
        probability_claims_used=False,
    )

    assert first == second
    assert first.machine_readiness is WC7MachineReadiness.INSUFFICIENT_EVIDENCE
    assert first.machine_conclusion is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    assert first.blocking_dimensions == (
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
        WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
        WC7EvidenceDimension.REGIME_ROBUSTNESS,
        WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
        WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
    )
    assert first.human_review_required is True
    assert first.automatic_edge_verdict is False
    assert first.production_authority is False
    assert first.real_capital == 0


def test_wc7_incomplete_evidence_cannot_receive_edge_positive_or_negative_verdict() -> None:
    review = build_wc7_evidence_review(
        claims=_current_frontier_claims(),
        probability_claims_used=False,
    )

    for conclusion in (
        WC7ReviewConclusion.EDGE_SUPPORTED,
        WC7ReviewConclusion.EDGE_PARTIAL_REGIME_SPECIFIC,
        WC7ReviewConclusion.EDGE_NOT_SUPPORTED,
    ):
        with pytest.raises(ValueError, match="incomplete evidence"):
            record_wc7_human_review(
                review,
                conclusion=conclusion,
                reviewer_role="world-class-evidence-reviewer",
                review_version="wc7-test-v1",
                decision_note="must fail closed while required evidence is missing",
                reviewed_at_ms=1,
            )

    insufficient = record_wc7_human_review(
        review,
        conclusion=WC7ReviewConclusion.INSUFFICIENT_EVIDENCE,
        reviewer_role="world-class-evidence-reviewer",
        review_version="wc7-test-v1",
        decision_note="required evidence remains incomplete",
        reviewed_at_ms=1,
    )
    assert insufficient.conclusion is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    assert insufficient.automatic_edge_verdict is False
    assert insufficient.production_authority is False
    assert insufficient.real_capital == 0


def test_wc7_complete_satisfied_evidence_only_becomes_human_review_ready() -> None:
    review = build_wc7_evidence_review(
        claims=_complete_claims(),
        probability_claims_used=False,
    )

    assert review.machine_readiness is WC7MachineReadiness.READY_FOR_HUMAN_REVIEW
    assert review.machine_conclusion is None
    assert review.blocking_dimensions == ()

    decision = record_wc7_human_review(
        review,
        conclusion=WC7ReviewConclusion.EDGE_SUPPORTED,
        reviewer_role="world-class-evidence-reviewer",
        review_version="wc7-test-v1",
        decision_note="test-only complete supported evidence set",
        reviewed_at_ms=2,
    )
    assert decision.conclusion is WC7ReviewConclusion.EDGE_SUPPORTED
    assert decision.review_identity == review.review_identity
    assert decision.automatic_edge_verdict is False
    assert decision.production_authority is False


def test_wc7_partial_or_negative_conclusions_require_matching_evidence() -> None:
    partial = build_wc7_evidence_review(
        claims=_complete_claims(
            override_dimension=WC7EvidenceDimension.REGIME_ROBUSTNESS,
            override_status=WC7EvidenceStatus.PARTIAL,
        ),
        probability_claims_used=False,
    )
    with pytest.raises(ValueError, match="all applicable evidence satisfied"):
        record_wc7_human_review(
            partial,
            conclusion=WC7ReviewConclusion.EDGE_SUPPORTED,
            reviewer_role="reviewer",
            review_version="v1",
            decision_note="partial evidence cannot support full edge verdict",
            reviewed_at_ms=3,
        )
    partial_decision = record_wc7_human_review(
        partial,
        conclusion=WC7ReviewConclusion.EDGE_PARTIAL_REGIME_SPECIFIC,
        reviewer_role="reviewer",
        review_version="v1",
        decision_note="explicit partial regime evidence",
        reviewed_at_ms=3,
    )
    assert (
        partial_decision.conclusion
        is WC7ReviewConclusion.EDGE_PARTIAL_REGIME_SPECIFIC
    )

    negative = build_wc7_evidence_review(
        claims=_complete_claims(
            override_dimension=WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
            override_status=WC7EvidenceStatus.NEGATIVE,
        ),
        probability_claims_used=False,
    )
    negative_decision = record_wc7_human_review(
        negative,
        conclusion=WC7ReviewConclusion.EDGE_NOT_SUPPORTED,
        reviewer_role="reviewer",
        review_version="v1",
        decision_note="explicit negative cost-adjusted evidence",
        reviewed_at_ms=4,
    )
    assert negative_decision.conclusion is WC7ReviewConclusion.EDGE_NOT_SUPPORTED


def test_wc7_probability_use_cannot_hide_behind_not_applicable_calibration() -> None:
    with pytest.raises(ValueError, match="requires applicable calibration"):
        build_wc7_evidence_review(
            claims=_complete_claims(),
            probability_claims_used=True,
        )


def test_wc7_review_source_has_no_runtime_order_or_auto_verdict_surface() -> None:
    source = inspect.getsource(world_class_evidence_review).lower()
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
        "automatic_edge_verdict: bool = true",
        "production_authority: bool = true",
    )
    assert all(token not in source for token in forbidden)
    assert "ready_for_human_review" in source
    assert "insufficient_evidence" in source
    assert world_class_evidence_review.REAL_CAPITAL == 0
