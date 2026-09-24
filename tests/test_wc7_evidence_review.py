"""WC7 fail-closed evidence-review readiness acceptance."""

from __future__ import annotations

import hashlib
import inspect

import pytest

from crypto_signal.evaluation import world_class_review
from crypto_signal.evaluation.untouched_forward_policy import (
    build_wc2_cohort_readiness_evidence,
    build_wc2_untouched_forward_policy,
    evaluate_wc2_review_readiness,
)
from crypto_signal.evaluation.world_class_review import (
    WC7EvidenceDomain,
    WC7EvidenceStatus,
    WC7ReviewReadinessStatus,
    build_wc7_evidence_reference,
    build_wc7_execution_lineage_reference,
    build_wc7_untouched_forward_reference,
    evaluate_wc7_review_readiness,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_sandbox import (
    WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
    WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
    WC6SandboxEvidenceSemantic,
)
from crypto_signal.paper.models import REAL_CAPITAL


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _accepted_reference(domain: WC7EvidenceDomain):
    return build_wc7_evidence_reference(
        domain=domain,
        status=WC7EvidenceStatus.ACCEPTED,
        source_semantic=f"accepted_{domain.value}_evidence",
        evidence_identity=_sha(f"wc7-{domain.value}"),
        blocker_detail=None,
    )


def _insufficient_wc2_reference():
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )
    evidence = build_wc2_cohort_readiness_evidence(
        policy=policy,
        observed_at_ms=86_402_000,
        collection_start_ms=2_000,
        collection_end_ms=86_402_000,
        total_forecast_n=0,
        resolved_forecast_n=0,
        decisive_n=0,
        paper_decision_n=0,
        trade_decision_n=0,
        simulated_execution_n=0,
        explicit_cost_evidence_trade_n=0,
        asset_decisive_counts=(),
        regime_decisive_counts=(),
        loss_retention_complete=True,
        abstain_retention_complete=True,
        invalidation_retention_complete=True,
        unresolved_retention_complete=True,
        source_evidence_identities=(_sha("wc2-source"),),
    )
    readiness = evaluate_wc2_review_readiness(policy, evidence)
    return build_wc7_untouched_forward_reference(readiness)


def _blocked_wc6_reference():
    config_identity = _sha("wc6-config")
    request_identity = _sha("wc6-request")
    payload = {
        "config_identity": config_identity,
        "credential_bound": False,
        "dispatch_attempted": False,
        "dispatch_status": WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED,
        "endpoint_bound": False,
        "engine_version": WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        "live_order_authority": False,
        "network_authority": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "request_identity": request_identity,
        "schema_version": WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        "semantic": (
            WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
        ),
        "transport_bound": False,
        "venue_acknowledgement_identity": None,
        "venue_fill_identities": (),
    }
    evidence = WC6SandboxBoundaryEvidence(
        evidence_identity=canonical_sha256(payload),
        schema_version=WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        engine_version=WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        semantic=(
            WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
        ),
        config_identity=config_identity,
        request_identity=request_identity,
        dispatch_status=WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED,
        dispatch_attempted=False,
        venue_acknowledgement_identity=None,
        venue_fill_identities=(),
        endpoint_bound=False,
        credential_bound=False,
        transport_bound=False,
        network_authority=False,
        live_order_authority=False,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return build_wc7_execution_lineage_reference(evidence)


def test_wc7_current_like_missing_evidence_forces_insufficient() -> None:
    references = [_accepted_reference(domain) for domain in WC7EvidenceDomain]
    by_domain = {item.domain: item for item in references}
    by_domain[WC7EvidenceDomain.UNTOUCHED_FORWARD] = (
        _insufficient_wc2_reference()
    )
    by_domain[WC7EvidenceDomain.EXECUTION_LINEAGE] = _blocked_wc6_reference()
    by_domain[WC7EvidenceDomain.USABILITY] = build_wc7_evidence_reference(
        domain=WC7EvidenceDomain.USABILITY,
        status=WC7EvidenceStatus.NOT_MEASURED,
        source_semantic="human_time_to_understand",
        evidence_identity=None,
        blocker_detail="WC5 human <=10-second comprehension is NOT_MEASURED",
    )

    readiness = evaluate_wc7_review_readiness(tuple(by_domain.values()))

    assert readiness.status is WC7ReviewReadinessStatus.INSUFFICIENT_EVIDENCE
    assert "untouched_forward:open" in readiness.blocker_codes
    assert "execution_lineage:open" in readiness.blocker_codes
    assert "usability:not_measured" in readiness.blocker_codes
    assert readiness.edge_supported_claim is False
    assert readiness.world_class_claim is False
    assert readiness.automatic_promotion is False
    assert readiness.production_authority is False
    assert readiness.real_capital == REAL_CAPITAL == 0


def test_wc7_all_domains_only_reach_review_ready_not_edge_conclusion() -> None:
    references = tuple(
        _accepted_reference(domain) for domain in reversed(tuple(WC7EvidenceDomain))
    )
    readiness = evaluate_wc7_review_readiness(references)

    assert readiness.status is (
        WC7ReviewReadinessStatus.READY_FOR_EVIDENCE_REVIEW_NOT_CONCLUSION
    )
    assert tuple(item.domain for item in readiness.references) == tuple(
        WC7EvidenceDomain
    )
    assert readiness.blocker_codes == ()
    assert readiness.semantic == "readiness_only_not_edge_or_world_class_conclusion"
    assert readiness.edge_supported_claim is False
    assert readiness.world_class_claim is False
    assert readiness.automatic_promotion is False
    assert readiness.production_authority is False
    assert readiness.real_capital == REAL_CAPITAL == 0


def test_wc7_accepted_reference_requires_exact_evidence_identity() -> None:
    with pytest.raises(ValueError, match="requires exact identity"):
        build_wc7_evidence_reference(
            domain=WC7EvidenceDomain.CALIBRATION,
            status=WC7EvidenceStatus.ACCEPTED,
            source_semantic="calibration evidence",
            evidence_identity=None,
            blocker_detail=None,
        )


def test_wc7_readiness_rejects_missing_domain_and_duplicate_domain() -> None:
    references = tuple(
        _accepted_reference(domain)
        for domain in WC7EvidenceDomain
        if domain is not WC7EvidenceDomain.USABILITY
    )
    with pytest.raises(ValueError, match="every domain"):
        evaluate_wc7_review_readiness(references)

    complete = tuple(_accepted_reference(domain) for domain in WC7EvidenceDomain)
    with pytest.raises(ValueError, match="duplicate WC7 evidence domain"):
        evaluate_wc7_review_readiness(complete + (complete[0],))


def test_wc7_source_has_no_scoring_promotion_order_or_network_surface() -> None:
    source = inspect.getsource(world_class_review).lower()
    forbidden = (
        "edge_score",
        "world_class_score",
        "winner_identity",
        "profitability_threshold",
        "place_order",
        "submit_order",
        "cancel_order",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "api_key",
        "api_secret",
        "ccxt",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert "ready_for_evidence_review_not_conclusion" in source
    assert "insufficient_evidence" in source
    assert world_class_review.REAL_CAPITAL == 0
