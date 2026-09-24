"""WC7 read-only canonical evidence-adapter acceptance."""

from __future__ import annotations

import inspect

import pytest

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2_MIN_CALENDAR_DAYS,
    WC2_MIN_TOTAL_DECISIVE_N,
    build_wc2_cohort_readiness_evidence,
    build_wc2_untouched_forward_policy,
    evaluate_wc2_review_readiness,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_sandbox import (
    WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
    WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
    WC6SandboxEvidenceSemantic,
)
from research import world_class_evidence_adapters
from research.world_class_evidence_adapters import (
    adapt_wc2_untouched_forward_readiness,
    adapt_wc6_sandbox_boundary,
)
from research.world_class_evidence_provenance import (
    WC7EvidenceSourceKind,
    build_wc7_evidence_provenance,
)
from research.world_class_evidence_review import (
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    build_wc7_evidence_claim,
)

DAY_MS = 86_400_000


def _eligible_wc2_readiness():
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )
    collection_end_ms = 2_000 + WC2_MIN_CALENDAR_DAYS * DAY_MS
    evidence = build_wc2_cohort_readiness_evidence(
        policy=policy,
        observed_at_ms=collection_end_ms + 1,
        collection_start_ms=2_000,
        collection_end_ms=collection_end_ms,
        total_forecast_n=420,
        resolved_forecast_n=360,
        decisive_n=WC2_MIN_TOTAL_DECISIVE_N,
        paper_decision_n=420,
        trade_decision_n=180,
        simulated_execution_n=180,
        explicit_cost_evidence_trade_n=180,
        asset_decisive_counts=(
            ("BTCUSDT", 100),
            ("ETHUSDT", 100),
            ("SOLUSDT", 100),
        ),
        regime_decisive_counts=(
            ("high_vol_trend", 100),
            ("low_vol_range", 100),
            ("transition", 100),
        ),
        loss_retention_complete=True,
        abstain_retention_complete=True,
        invalidation_retention_complete=True,
        unresolved_retention_complete=True,
        source_evidence_identities=("a" * 64, "b" * 64),
    )
    return evaluate_wc2_review_readiness(policy, evidence)


def _insufficient_wc2_readiness():
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )
    evidence = build_wc2_cohort_readiness_evidence(
        policy=policy,
        observed_at_ms=2_000 + DAY_MS,
        collection_start_ms=2_000,
        collection_end_ms=2_000 + DAY_MS,
        total_forecast_n=3,
        resolved_forecast_n=1,
        decisive_n=1,
        paper_decision_n=3,
        trade_decision_n=0,
        simulated_execution_n=0,
        explicit_cost_evidence_trade_n=0,
        asset_decisive_counts=(
            ("BTCUSDT", 1),
            ("ETHUSDT", 0),
            ("SOLUSDT", 0),
        ),
        regime_decisive_counts=(("transition", 1),),
        loss_retention_complete=True,
        abstain_retention_complete=True,
        invalidation_retention_complete=True,
        unresolved_retention_complete=True,
        source_evidence_identities=("c" * 64,),
    )
    return evaluate_wc2_review_readiness(policy, evidence)


def _wc6_blocked_boundary() -> WC6SandboxBoundaryEvidence:
    config_identity = canonical_sha256({"wc6": "not-configured-config"})
    request_identity = canonical_sha256({"wc6": "prepared-request"})
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
        "real_capital": 0,
        "request_identity": request_identity,
        "schema_version": WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
        "semantic": (
            WC6SandboxEvidenceSemantic.REQUEST_PREPARED_NO_DISPATCH_NO_VENUE_EVIDENCE
        ),
        "transport_bound": False,
        "venue_acknowledgement_identity": None,
        "venue_fill_identities": (),
    }
    return WC6SandboxBoundaryEvidence(
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
        real_capital=0,
    )


def test_wc2_review_eligible_only_satisfies_history_dimension() -> None:
    readiness = _eligible_wc2_readiness()

    adapted = adapt_wc2_untouched_forward_readiness(
        readiness,
        observed_at_ms=99,
    )

    assert adapted.claim.dimension is WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY
    assert adapted.claim.status is WC7EvidenceStatus.SATISFIED
    assert adapted.claim.evidence_identity == readiness.readiness_identity
    assert adapted.provenance.source_kind is (
        WC7EvidenceSourceKind.WC2_PREREGISTERED_FORWARD
    )
    assert (
        adapted.provenance.source_artifact_identity
        == readiness.readiness_identity
    )
    assert adapted.provenance.blocker_boundary_identity is None
    assert "not an edge/profitability claim" in adapted.claim.evidence_note
    assert adapted.real_capital == 0


def test_wc2_insufficient_readiness_stays_missing_with_boundary_identity() -> None:
    readiness = _insufficient_wc2_readiness()

    adapted = adapt_wc2_untouched_forward_readiness(
        readiness,
        observed_at_ms=100,
    )

    assert adapted.claim.status is WC7EvidenceStatus.MISSING
    assert adapted.claim.evidence_identity is None
    assert adapted.provenance.source_kind is (
        WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE
    )
    assert adapted.provenance.source_artifact_identity is None
    assert (
        adapted.provenance.blocker_boundary_identity
        == readiness.readiness_identity
    )
    assert "decisive_sample_below_minimum" in adapted.claim.evidence_note


def test_wc6_not_configured_boundary_stays_external_dependency() -> None:
    boundary = _wc6_blocked_boundary()

    adapted = adapt_wc6_sandbox_boundary(
        boundary,
        observed_at_ms=101,
    )

    assert adapted.claim.dimension is WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE
    assert adapted.claim.status is WC7EvidenceStatus.EXTERNAL_DEPENDENCY
    assert adapted.claim.evidence_identity is None
    assert adapted.provenance.source_kind is (
        WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY
    )
    assert adapted.provenance.source_artifact_identity is None
    assert (
        adapted.provenance.blocker_boundary_identity
        == boundary.evidence_identity
    )
    assert adapted.real_capital == 0


def test_wc7_satisfied_evidence_cannot_carry_blocker_boundary_identity() -> None:
    evidence_identity = canonical_sha256({"runtime": "accepted"})
    claim = build_wc7_evidence_claim(
        dimension=WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY,
        status=WC7EvidenceStatus.SATISFIED,
        evidence_note="accepted runtime",
        evidence_identity=evidence_identity,
    )

    with pytest.raises(ValueError, match="cannot carry blocker boundary"):
        build_wc7_evidence_provenance(
            claim,
            source_kind=WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE,
            source_artifact_identity=evidence_identity,
            blocker_boundary_identity=canonical_sha256({"blocker": "wrong"}),
            source_reference="runtime acceptance",
            observed_at_ms=102,
        )


def test_wc7_adapter_source_has_no_write_network_or_verdict_surface() -> None:
    source = inspect.getsource(world_class_evidence_adapters).lower()
    forbidden = (
        "sqlite3",
        "open(",
        "write_text",
        "write_bytes",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "subprocess",
        "launchctl",
        "place_order",
        "submit_order",
        "cancel_order",
        "edge_supported",
        "edge_not_supported",
        "production_authority=true",
    )
    assert all(token not in source for token in forbidden)
    assert "wc2reviewreadiness" in source
    assert "wc6sandboxboundaryevidence" in source
    assert world_class_evidence_adapters.REAL_CAPITAL == 0
