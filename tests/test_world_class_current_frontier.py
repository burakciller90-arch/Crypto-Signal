"""WC7 current-frontier packet composition acceptance."""

from __future__ import annotations

import inspect

import pytest

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2_MIN_CALENDAR_DAYS,
    WC2_MIN_TOTAL_DECISIVE_N,
    WC2ReviewStatus,
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
from research import world_class_current_frontier
from research.world_class_current_frontier import (
    WC7CurrentFrontierInputs,
    build_wc7_current_frontier_snapshot,
)
from research.world_class_evidence_provenance import WC7EvidenceSourceKind
from research.world_class_evidence_review import (
    WC7EvidenceDimension,
    WC7EvidenceStatus,
    WC7MachineReadiness,
    WC7ReviewConclusion,
)

DAY_MS = 86_400_000


def _policy():
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=1_000,
        collection_start_ms=2_000,
    )


def _eligible_readiness():
    policy = _policy()
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
    readiness = evaluate_wc2_review_readiness(policy, evidence)
    assert readiness.status is WC2ReviewStatus.REVIEW_ELIGIBLE
    return readiness


def _insufficient_readiness():
    policy = _policy()
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
    readiness = evaluate_wc2_review_readiness(policy, evidence)
    assert readiness.status is WC2ReviewStatus.INSUFFICIENT_EVIDENCE
    return readiness


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


def _inputs(*, eligible_wc2: bool) -> WC7CurrentFrontierInputs:
    return WC7CurrentFrontierInputs(
        runtime_acceptance_identity=canonical_sha256(
            {"accepted": "production-runtime"}
        ),
        abstention_transparency_identity=canonical_sha256(
            {"accepted": "fail-closed-transparency"}
        ),
        wc4_research_cycle_identity=canonical_sha256(
            {"accepted": "wc4-research-cycle-engineering"}
        ),
        wc2_readiness=(
            _eligible_readiness()
            if eligible_wc2
            else _insufficient_readiness()
        ),
        wc6_sandbox_boundary=_wc6_blocked_boundary(),
        observed_at_ms=999_999,
        real_capital=0,
    )


def _by_dimension(snapshot):
    return {item.dimension: item for item in snapshot.review.claims}


def _provenance_by_dimension(snapshot):
    return {item.dimension: item for item in snapshot.packet.provenances}


def test_wc7_current_frontier_with_current_blockers_is_deterministically_insufficient() -> None:
    inputs = _inputs(eligible_wc2=False)

    first = build_wc7_current_frontier_snapshot(inputs)
    second = build_wc7_current_frontier_snapshot(inputs)

    assert first == second
    assert first.review.machine_readiness is WC7MachineReadiness.INSUFFICIENT_EVIDENCE
    assert (
        first.review.machine_conclusion
        is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    )
    assert first.current_conclusion is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    assert first.review.blocking_dimensions == (
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
        WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
        WC7EvidenceDimension.REGIME_ROBUSTNESS,
        WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
        WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
    )
    assert first.packet.review_identity == first.review.review_identity
    assert first.packet.human_review_required is True
    assert first.packet.automatic_edge_verdict is False
    assert first.packet.production_authority is False
    assert first.real_capital == 0


def test_wc2_review_eligible_removes_only_history_blocker() -> None:
    snapshot = build_wc7_current_frontier_snapshot(
        _inputs(eligible_wc2=True)
    )
    claims = _by_dimension(snapshot)

    assert (
        claims[WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY].status
        is WC7EvidenceStatus.SATISFIED
    )
    assert snapshot.review.blocking_dimensions == (
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE,
        WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
        WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
        WC7EvidenceDimension.REGIME_ROBUSTNESS,
        WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY,
    )
    assert snapshot.review.machine_readiness is WC7MachineReadiness.INSUFFICIENT_EVIDENCE
    assert (
        snapshot.current_conclusion
        is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    )


def test_current_frontier_preserves_wc6_external_dependency_as_blocker_only() -> None:
    inputs = _inputs(eligible_wc2=False)
    snapshot = build_wc7_current_frontier_snapshot(inputs)
    claims = _by_dimension(snapshot)
    provenance = _provenance_by_dimension(snapshot)[
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE
    ]

    assert (
        claims[WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE].status
        is WC7EvidenceStatus.EXTERNAL_DEPENDENCY
    )
    assert (
        claims[WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE].evidence_identity
        is None
    )
    assert provenance.source_kind is (
        WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY
    )
    assert provenance.source_artifact_identity is None
    assert (
        provenance.blocker_boundary_identity
        == inputs.wc6_sandbox_boundary.evidence_identity
    )


def test_current_frontier_binds_runtime_abstention_and_probability_boundaries() -> None:
    inputs = _inputs(eligible_wc2=False)
    snapshot = build_wc7_current_frontier_snapshot(inputs)
    claims = _by_dimension(snapshot)
    provenance = _provenance_by_dimension(snapshot)

    runtime = claims[WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY]
    assert runtime.status is WC7EvidenceStatus.SATISFIED
    assert runtime.evidence_identity == inputs.runtime_acceptance_identity
    assert provenance[runtime.dimension].source_kind is (
        WC7EvidenceSourceKind.RUNTIME_ACCEPTANCE
    )

    abstention = claims[
        WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY
    ]
    assert abstention.status is WC7EvidenceStatus.SATISFIED
    assert (
        abstention.evidence_identity
        == inputs.abstention_transparency_identity
    )
    assert provenance[abstention.dimension].source_kind is (
        WC7EvidenceSourceKind.FAIL_CLOSED_TRANSPARENCY
    )

    probability = claims[
        WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
    ]
    assert probability.status is WC7EvidenceStatus.NOT_APPLICABLE
    assert probability.evidence_identity is not None
    assert provenance[probability.dimension].source_kind is (
        WC7EvidenceSourceKind.PROBABILITY_NOT_USED_BOUNDARY
    )
    assert provenance[probability.dimension].blocker_boundary_identity is None


def test_wc4_engineering_cycle_is_blocker_boundary_not_regime_edge_evidence() -> None:
    inputs = _inputs(eligible_wc2=False)
    snapshot = build_wc7_current_frontier_snapshot(inputs)
    claim = _by_dimension(snapshot)[
        WC7EvidenceDimension.REGIME_ROBUSTNESS
    ]
    provenance = _provenance_by_dimension(snapshot)[
        WC7EvidenceDimension.REGIME_ROBUSTNESS
    ]

    assert claim.status is WC7EvidenceStatus.MISSING
    assert claim.evidence_identity is None
    assert provenance.source_artifact_identity is None
    assert (
        provenance.blocker_boundary_identity
        == inputs.wc4_research_cycle_identity
    )
    assert "durable" in claim.evidence_note.lower()


def test_wc7_current_frontier_rejects_invalid_accepted_boundary_identity() -> None:
    with pytest.raises(ValueError, match="lowercase SHA256"):
        WC7CurrentFrontierInputs(
            runtime_acceptance_identity="not-a-sha",
            abstention_transparency_identity="a" * 64,
            wc4_research_cycle_identity="b" * 64,
            wc2_readiness=_insufficient_readiness(),
            wc6_sandbox_boundary=_wc6_blocked_boundary(),
            observed_at_ms=1,
        )


def test_wc7_current_frontier_source_has_no_write_network_or_edge_verdict_surface() -> None:
    source = inspect.getsource(world_class_current_frontier).lower()
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
    assert "insufficient_evidence" in source
    assert "wc7_machine_edge_verdict" not in source
    assert world_class_current_frontier.REAL_CAPITAL == 0
