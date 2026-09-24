"""WC7 conservative typed evidence-adapter acceptance."""

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
    build_wc7_execution_claim_from_wc6_boundary,
    build_wc7_regime_claim_from_wc4_cycle,
)
from research.world_class_evidence_review import (
    WC7EvidenceDimension,
    WC7EvidenceStatus,
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
    payload = {
        "config_identity": _sha("wc6-config"),
        "credential_bound": False,
        "dispatch_attempted": False,
        "dispatch_status": WC6SandboxDispatchStatus.BLOCKED_NOT_CONFIGURED,
        "endpoint_bound": False,
        "engine_version": WC6_SANDBOX_BOUNDARY_ENGINE_VERSION,
        "live_order_authority": False,
        "network_authority": False,
        "production_authority": False,
        "real_capital": 0,
        "request_identity": _sha("wc6-request"),
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
        config_identity=payload["config_identity"],
        request_identity=payload["request_identity"],
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


def test_wc7_wc4_adapter_preserves_regime_blocker_with_exact_provenance() -> None:
    cycle = _wc4_cycle()
    claim = build_wc7_regime_claim_from_wc4_cycle(cycle)

    assert claim.dimension is WC7EvidenceDimension.REGIME_ROBUSTNESS
    assert claim.status is WC7EvidenceStatus.MISSING
    assert claim.evidence_identity == cycle.cycle_identity
    assert "does not establish durable regime-specific edge" in claim.evidence_note
    assert claim.real_capital == 0


def test_wc7_wc6_adapter_preserves_external_execution_blocker() -> None:
    boundary = _wc6_boundary()
    claim = build_wc7_execution_claim_from_wc6_boundary(boundary)

    assert claim.dimension is WC7EvidenceDimension.CAPITAL_EXECUTION_LINEAGE
    assert claim.status is WC7EvidenceStatus.EXTERNAL_DEPENDENCY
    assert claim.evidence_identity == boundary.evidence_identity
    assert "no configured transport" in claim.evidence_note
    assert claim.real_capital == 0


def test_wc7_typed_adapters_are_deterministic() -> None:
    assert build_wc7_regime_claim_from_wc4_cycle(
        _wc4_cycle()
    ) == build_wc7_regime_claim_from_wc4_cycle(_wc4_cycle())
    assert build_wc7_execution_claim_from_wc6_boundary(
        _wc6_boundary()
    ) == build_wc7_execution_claim_from_wc6_boundary(_wc6_boundary())


def test_wc7_adapter_source_cannot_upgrade_blockers_or_open_authority() -> None:
    source = inspect.getsource(world_class_evidence_adapters).lower()

    assert "status=wc7evidencestatus.missing" in source
    assert "status=wc7evidencestatus.external_dependency" in source
    assert "status=wc7evidencestatus.satisfied" not in source
    assert "network_authority" in source
    assert "production_authority" in source
    assert "real_capital" in source
