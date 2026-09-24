"""WC7 canonical subsystem blocker-adapter acceptance."""

from __future__ import annotations

import hashlib
import inspect

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_lab_sandbox import (
    WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
    WC6_SANDBOX_BOUNDARY_SCHEMA_VERSION,
    WC6SandboxBoundaryEvidence,
    WC6SandboxDispatchStatus,
    WC6SandboxEvidenceSemantic,
)
from research import world_class_evidence_adapters
from research.alpha_factory.champion_challenger_cycle import (
    WC4_CHAMPION_CHALLENGER_ENGINE_VERSION,
    WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION,
    WC4ChampionChallengerCycle,
    WC4CycleSemantic,
    WC4CycleStatus,
)
from research.world_class_evidence_adapters import (
    WC7BoundarySourceKind,
    adapt_wc4_cycle_to_regime_blocker,
    adapt_wc6_boundary_to_execution_blocker,
)
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


def _wc4_cycle() -> WC4ChampionChallengerCycle:
    values = {
        "dataset_identity": _sha("dataset"),
        "champion_reference_model_identity": _sha("reference"),
        "challenger_model_identity": _sha("challenger"),
        "frozen_snapshot_identity": _sha("snapshot"),
        "machine_evidence_identity": _sha("machine"),
        "dossier_identity": _sha("dossier"),
        "data_contract_identity": _sha("data-contract"),
        "leakage_audit_identity": _sha("leakage"),
        "reproducibility_identity": _sha("reproducibility"),
        "transaction_cost_stress_identity": _sha("cost-stress"),
        "in_sample_sanity_identity": _sha("in-sample"),
        "out_of_sample_identity": _sha("oos"),
        "walk_forward_identity": _sha("walk-forward"),
        "robustness_ablation_identity": _sha("robustness"),
        "untouched_forward_identity": _sha("untouched"),
    }
    payload = {
        "automatic_promotion": False,
        "champion_reference_model_identity": values[
            "champion_reference_model_identity"
        ],
        "champion_state_mutation_performed": False,
        "challenger_model_identity": values["challenger_model_identity"],
        "data_contract_identity": values["data_contract_identity"],
        "dataset_identity": values["dataset_identity"],
        "deploy_authority": False,
        "dossier_identity": values["dossier_identity"],
        "engine_version": WC4_CHAMPION_CHALLENGER_ENGINE_VERSION,
        "frozen_snapshot_identity": values["frozen_snapshot_identity"],
        "human_supervisor_required": True,
        "in_sample_sanity_identity": values["in_sample_sanity_identity"],
        "leakage_audit_identity": values["leakage_audit_identity"],
        "machine_evidence_identity": values["machine_evidence_identity"],
        "out_of_sample_identity": values["out_of_sample_identity"],
        "performance_winner_declared": False,
        "production_authority": False,
        "real_capital": 0,
        "reproducibility_identity": values["reproducibility_identity"],
        "robustness_ablation_identity": values["robustness_ablation_identity"],
        "schema_version": WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION,
        "semantic": (
            WC4CycleSemantic.FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION
        ),
        "status": WC4CycleStatus.REVIEW_READY_NOT_PROMOTED,
        "supervisor_acceptance_identity": None,
        "transaction_cost_stress_identity": values[
            "transaction_cost_stress_identity"
        ],
        "untouched_forward_identity": values["untouched_forward_identity"],
        "untouched_forward_used": True,
        "walk_forward_identity": values["walk_forward_identity"],
    }
    return WC4ChampionChallengerCycle(
        cycle_identity=canonical_sha256(payload),
        schema_version=WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION,
        engine_version=WC4_CHAMPION_CHALLENGER_ENGINE_VERSION,
        semantic=(
            WC4CycleSemantic.FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION
        ),
        status=WC4CycleStatus.REVIEW_READY_NOT_PROMOTED,
        supervisor_acceptance_identity=None,
        untouched_forward_used=True,
        human_supervisor_required=True,
        performance_winner_declared=False,
        champion_state_mutation_performed=False,
        automatic_promotion=False,
        deploy_authority=False,
        production_authority=False,
        real_capital=0,
        **values,
    )


def _wc6_boundary() -> WC6SandboxBoundaryEvidence:
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


def _generic_claim(
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
        else _sha(f"{tag}:{dimension.value}")
    )
    return build_wc7_evidence_claim(
        dimension=dimension,
        status=status,
        evidence_note=f"{tag}: {dimension.value}",
        evidence_identity=evidence_identity,
    )


def test_wc7_wc4_cycle_adapter_preserves_missing_regime_blocker() -> None:
    cycle = _wc4_cycle()
    adapted = adapt_wc4_cycle_to_regime_blocker(
        cycle,
        observed_at_ms=10,
    )

    assert adapted.source_boundary_kind is (
        WC7BoundarySourceKind.WC4_CHAMPION_CHALLENGER_CYCLE
    )
    assert adapted.source_boundary_identity == cycle.cycle_identity
    assert adapted.claim.dimension is WC7EvidenceDimension.REGIME_ROBUSTNESS
    assert adapted.claim.status is WC7EvidenceStatus.MISSING
    assert adapted.claim.evidence_identity is None
    assert adapted.provenance.source_kind is (
        WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE
    )
    assert adapted.provenance.source_artifact_identity is None
    assert cycle.cycle_identity in adapted.provenance.source_reference
    assert adapted.real_capital == 0


def test_wc7_wc6_boundary_adapter_preserves_external_dependency() -> None:
    boundary = _wc6_boundary()
    adapted = adapt_wc6_boundary_to_execution_blocker(
        boundary,
        observed_at_ms=11,
    )

    assert adapted.source_boundary_kind is (
        WC7BoundarySourceKind.WC6_SANDBOX_NOT_CONFIGURED_BOUNDARY
    )
    assert adapted.source_boundary_identity == boundary.evidence_identity
    assert adapted.claim.dimension is (
        WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE
    )
    assert adapted.claim.status is WC7EvidenceStatus.EXTERNAL_DEPENDENCY
    assert adapted.claim.evidence_identity is None
    assert adapted.provenance.source_kind is (
        WC7EvidenceSourceKind.EXTERNAL_DEPENDENCY_BOUNDARY
    )
    assert adapted.provenance.source_artifact_identity is None
    assert boundary.evidence_identity in adapted.provenance.source_reference
    assert adapted.real_capital == 0


def test_wc7_adapted_blockers_integrate_without_changing_review_readiness() -> None:
    wc4 = adapt_wc4_cycle_to_regime_blocker(_wc4_cycle(), observed_at_ms=12)
    wc6 = adapt_wc6_boundary_to_execution_blocker(
        _wc6_boundary(),
        observed_at_ms=12,
    )

    claims = (
        _generic_claim(
            WC7EvidenceDimension.PRODUCTION_RUNTIME_RELIABILITY,
            WC7EvidenceStatus.SATISFIED,
            tag="runtime",
        ),
        _generic_claim(
            WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY,
            WC7EvidenceStatus.MISSING,
            tag="wc2-open",
        ),
        _generic_claim(
            WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED,
            WC7EvidenceStatus.NOT_APPLICABLE,
            tag="probability-not-used",
        ),
        _generic_claim(
            WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY,
            WC7EvidenceStatus.MISSING,
            tag="economics-open",
        ),
        _generic_claim(
            WC7EvidenceDimension.CONTROLLED_DRAWDOWN,
            WC7EvidenceStatus.MISSING,
            tag="drawdown-open",
        ),
        wc4.claim,
        _generic_claim(
            WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY,
            WC7EvidenceStatus.SATISFIED,
            tag="fail-closed",
        ),
        wc6.claim,
        _generic_claim(
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
            source_reference="accepted runtime evidence",
            observed_at_ms=12,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.UNTOUCHED_FORWARD_HISTORY],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="WC2 sufficiency remains open",
            observed_at_ms=12,
        ),
        build_wc7_evidence_provenance(
            by_dimension[
                WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
            ],
            source_kind=WC7EvidenceSourceKind.PROBABILITY_NOT_USED_BOUNDARY,
            source_artifact_identity=by_dimension[
                WC7EvidenceDimension.PROBABILITY_CALIBRATION_WHERE_USED
            ].evidence_identity,
            source_reference="current review makes no probability claim",
            observed_at_ms=12,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.COST_ADJUSTED_EXPECTANCY],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="cost-adjusted conclusion unavailable",
            observed_at_ms=12,
        ),
        build_wc7_evidence_provenance(
            by_dimension[WC7EvidenceDimension.CONTROLLED_DRAWDOWN],
            source_kind=WC7EvidenceSourceKind.MISSING_REQUIRED_EVIDENCE,
            source_reference="drawdown conclusion unavailable",
            observed_at_ms=12,
        ),
        wc4.provenance,
        build_wc7_evidence_provenance(
            by_dimension[
                WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY
            ],
            source_kind=WC7EvidenceSourceKind.FAIL_CLOSED_TRANSPARENCY,
            source_artifact_identity=by_dimension[
                WC7EvidenceDimension.ABSTENTION_FAILURE_TRANSPARENCY
            ].evidence_identity,
            source_reference="accepted fail-closed transparency evidence",
            observed_at_ms=12,
        ),
        wc6.provenance,
        build_wc7_evidence_provenance(
            by_dimension[
                WC7EvidenceDimension.USABILITY_WITHOUT_HIDDEN_UNCERTAINTY
            ],
            source_kind=WC7EvidenceSourceKind.NOT_MEASURED_BOUNDARY,
            source_reference="human usability remains not measured",
            observed_at_ms=12,
        ),
    )
    packet = build_wc7_evidence_packet(review, provenances=provenances)

    assert review.machine_readiness is WC7MachineReadiness.INSUFFICIENT_EVIDENCE
    assert review.machine_conclusion is WC7ReviewConclusion.INSUFFICIENT_EVIDENCE
    assert packet.review_identity == review.review_identity
    assert packet.automatic_edge_verdict is False
    assert packet.production_authority is False
    assert packet.real_capital == 0


def test_wc7_blocker_adapters_are_deterministic_and_non_promoting() -> None:
    assert adapt_wc4_cycle_to_regime_blocker(
        _wc4_cycle(),
        observed_at_ms=20,
    ) == adapt_wc4_cycle_to_regime_blocker(
        _wc4_cycle(),
        observed_at_ms=20,
    )
    assert adapt_wc6_boundary_to_execution_blocker(
        _wc6_boundary(),
        observed_at_ms=20,
    ) == adapt_wc6_boundary_to_execution_blocker(
        _wc6_boundary(),
        observed_at_ms=20,
    )

    source = inspect.getsource(world_class_evidence_adapters).lower()
    assert "wc7evidencestatus.satisfied" not in source
    assert "wc7evidencestatus.missing" in source
    assert "wc7evidencestatus.external_dependency" in source
    assert "source_artifact_identity" not in source.split(
        "def adapt_wc4_cycle_to_regime_blocker", 1
    )[1].split("def adapt_wc6_boundary_to_execution_blocker", 1)[0]
    assert world_class_evidence_adapters.REAL_CAPITAL == 0
