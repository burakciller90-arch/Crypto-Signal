from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace

import pytest

import research.alpha_factory.foundation as foundation
from research.alpha_factory.foundation import (
    REAL_CAPITAL,
    LeakageAuditStatus,
    PartitionRole,
    PromotionGateStatus,
    assess_promotion_gate,
    build_challenger_definition,
    build_leakage_audit,
    build_promotion_gate_evidence,
    build_research_experiment,
    build_research_partition,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _challenger():
    return build_challenger_definition(
        name="bounded trend confirmation",
        version="v1",
        hypothesis="trend evidence may remain useful after costs",
        rule_definition="trend_state == rising and volatility != expanded",
        feature_ids=("trend_state", "volatility_state"),
    )


def _partitions(
    *,
    dataset_identity: str | None = None,
    duplicate_evidence: bool = False,
):
    dataset = dataset_identity or _sha("dataset-v1")
    shared = _sha("shared") if duplicate_evidence else None
    return (
        build_research_partition(
            dataset_identity=dataset,
            role=PartitionRole.TRAIN,
            start_ms=0,
            end_ms=100,
            row_count=10,
            evidence_identities=(
                shared or _sha("train-a"),
                _sha("train-b"),
            ),
        ),
        build_research_partition(
            dataset_identity=dataset,
            role=PartitionRole.VALIDATION,
            start_ms=100,
            end_ms=200,
            row_count=10,
            evidence_identities=(
                shared or _sha("validation-a"),
                _sha("validation-b"),
            ),
        ),
        build_research_partition(
            dataset_identity=dataset,
            role=PartitionRole.OUT_OF_SAMPLE,
            start_ms=200,
            end_ms=300,
            row_count=10,
            evidence_identities=(
                _sha("oos-a"),
                _sha("oos-b"),
            ),
        ),
        build_research_partition(
            dataset_identity=dataset,
            role=PartitionRole.UNTOUCHED_FORWARD,
            start_ms=300,
            end_ms=400,
            row_count=10,
            evidence_identities=(
                _sha("forward-a"),
                _sha("forward-b"),
            ),
        ),
    )


def _experiment():
    parts = _partitions()
    return build_research_experiment(
        challenger=_challenger(),
        partitions=(parts[2], parts[0], parts[3], parts[1]),
        evaluation_policy_version="alpha-eval-v1",
        cost_stress_profile_identity=_sha("cost-stress"),
        reproducibility_seed=7,
    )


def _complete_gate_evidence(experiment_identity: str, *, supervisor: bool):
    return build_promotion_gate_evidence(
        experiment_identity=experiment_identity,
        data_contract_audit_identity=_sha("data-contract"),
        reproducibility_identity=_sha("reproducibility"),
        transaction_cost_stress_identity=_sha("cost-stress-result"),
        in_sample_sanity_identity=_sha("in-sample"),
        out_of_sample_identity=_sha("oos"),
        walk_forward_identity=_sha("walk-forward"),
        untouched_forward_identity=_sha("untouched-forward"),
        robustness_ablation_identity=_sha("ablation"),
        supervisor_acceptance_identity=(
            _sha("supervisor") if supervisor else None
        ),
    )


def test_foundation_identities_are_deterministic_and_research_only() -> None:
    first = _experiment()
    second = _experiment()

    assert first == second
    assert first.experiment_identity == second.experiment_identity
    assert tuple(item.role for item in first.partitions) == (
        PartitionRole.TRAIN,
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
        PartitionRole.UNTOUCHED_FORWARD,
    )
    assert first.authority == "research_only_no_deploy"
    assert first.can_self_promote is False
    assert first.champion_write_authority is False
    assert first.real_capital == REAL_CAPITAL == 0


def test_partition_overlap_and_cross_partition_evidence_fail_closed() -> None:
    parts = list(_partitions())
    overlapping = build_research_partition(
        dataset_identity=parts[1].dataset_identity,
        role=PartitionRole.OUT_OF_SAMPLE,
        start_ms=150,
        end_ms=300,
        row_count=10,
        evidence_identities=(_sha("overlap"),),
    )
    with pytest.raises(ValueError, match="must not overlap"):
        build_research_experiment(
            challenger=_challenger(),
            partitions=(parts[0], parts[1], overlapping, parts[3]),
            evaluation_policy_version="alpha-eval-v1",
            cost_stress_profile_identity=_sha("cost"),
            reproducibility_seed=1,
        )

    with pytest.raises(ValueError, match="cannot cross research partitions"):
        build_research_experiment(
            challenger=_challenger(),
            partitions=_partitions(duplicate_evidence=True),
            evaluation_policy_version="alpha-eval-v1",
            cost_stress_profile_identity=_sha("cost"),
            reproducibility_seed=1,
        )


def test_partition_dataset_mismatch_and_missing_role_fail_closed() -> None:
    parts = list(_partitions())
    parts[3] = build_research_partition(
        dataset_identity=_sha("different-dataset"),
        role=PartitionRole.UNTOUCHED_FORWARD,
        start_ms=300,
        end_ms=400,
        row_count=10,
        evidence_identities=(_sha("different-forward"),),
    )
    with pytest.raises(ValueError, match="share dataset identity"):
        build_research_experiment(
            challenger=_challenger(),
            partitions=tuple(parts),
            evaluation_policy_version="alpha-eval-v1",
            cost_stress_profile_identity=_sha("cost"),
            reproducibility_seed=1,
        )

    with pytest.raises(ValueError, match="exactly one partition"):
        build_research_experiment(
            challenger=_challenger(),
            partitions=_partitions()[:3],
            evaluation_policy_version="alpha-eval-v1",
            cost_stress_profile_identity=_sha("cost"),
            reproducibility_seed=1,
        )


def test_identity_tampering_fails_closed() -> None:
    partition = _partitions()[0]
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(partition, row_count=partition.row_count + 1)

    challenger = _challenger()
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(challenger, rule_definition="different rule")

    experiment = _experiment()
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(experiment, reproducibility_seed=99)


def test_leakage_audit_semantics_are_explicit() -> None:
    experiment = _experiment()
    passed = build_leakage_audit(
        experiment_identity=experiment.experiment_identity,
        audited_at_ms=500,
        status=LeakageAuditStatus.PASSED,
        auditor_version="leakage-audit-v1",
    )
    assert passed.status is LeakageAuditStatus.PASSED
    assert passed.findings == ()

    failed = build_leakage_audit(
        experiment_identity=experiment.experiment_identity,
        audited_at_ms=500,
        status=LeakageAuditStatus.FAILED,
        findings=("future row entered train partition",),
        auditor_version="leakage-audit-v1",
    )
    assert failed.status is LeakageAuditStatus.FAILED

    with pytest.raises(ValueError, match="failed leakage audit requires"):
        build_leakage_audit(
            experiment_identity=experiment.experiment_identity,
            audited_at_ms=500,
            status=LeakageAuditStatus.FAILED,
            auditor_version="leakage-audit-v1",
        )


def test_promotion_gate_cannot_skip_required_evidence() -> None:
    experiment = _experiment()
    audit = build_leakage_audit(
        experiment_identity=experiment.experiment_identity,
        audited_at_ms=500,
        status=LeakageAuditStatus.PASSED,
        auditor_version="leakage-audit-v1",
    )
    evidence = build_promotion_gate_evidence(
        experiment_identity=experiment.experiment_identity,
    )

    assessment = assess_promotion_gate(
        experiment=experiment,
        leakage_audit=audit,
        evidence=evidence,
    )

    assert assessment.status is PromotionGateStatus.BLOCKED
    assert "missing_data_contract_audit" in assessment.blocking_reasons
    assert "missing_walk_forward" in assessment.blocking_reasons
    assert "missing_untouched_forward" in assessment.blocking_reasons


def test_failed_leakage_audit_blocks_even_complete_metrics() -> None:
    experiment = _experiment()
    audit = build_leakage_audit(
        experiment_identity=experiment.experiment_identity,
        audited_at_ms=500,
        status=LeakageAuditStatus.FAILED,
        findings=("partition contamination",),
        auditor_version="leakage-audit-v1",
    )
    evidence = _complete_gate_evidence(
        experiment.experiment_identity,
        supervisor=True,
    )

    assessment = assess_promotion_gate(
        experiment=experiment,
        leakage_audit=audit,
        evidence=evidence,
    )

    assert assessment.status is PromotionGateStatus.BLOCKED
    assert assessment.blocking_reasons == ("leakage_audit_not_passed",)


def test_complete_gate_stops_at_supervisor_boundary() -> None:
    experiment = _experiment()
    audit = build_leakage_audit(
        experiment_identity=experiment.experiment_identity,
        audited_at_ms=500,
        status=LeakageAuditStatus.PASSED,
        auditor_version="leakage-audit-v1",
    )

    ready = assess_promotion_gate(
        experiment=experiment,
        leakage_audit=audit,
        evidence=_complete_gate_evidence(
            experiment.experiment_identity,
            supervisor=False,
        ),
    )
    assert ready.status is PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW

    accepted = assess_promotion_gate(
        experiment=experiment,
        leakage_audit=audit,
        evidence=_complete_gate_evidence(
            experiment.experiment_identity,
            supervisor=True,
        ),
    )
    assert accepted.status is (
        PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION
    )
    assert "promoted" not in {status.value for status in PromotionGateStatus}


def test_gate_rejects_cross_experiment_evidence() -> None:
    experiment = _experiment()
    audit = build_leakage_audit(
        experiment_identity=_sha("other-experiment"),
        audited_at_ms=500,
        status=LeakageAuditStatus.PASSED,
        auditor_version="leakage-audit-v1",
    )
    evidence = build_promotion_gate_evidence(
        experiment_identity=experiment.experiment_identity,
    )
    with pytest.raises(ValueError, match="leakage audit does not belong"):
        assess_promotion_gate(
            experiment=experiment,
            leakage_audit=audit,
            evidence=evidence,
        )


def test_foundation_has_no_network_execution_or_production_write_surface() -> None:
    source = inspect.getsource(foundation).lower()
    forbidden = (
        "crypto_signal.paper",
        "crypto_signal.product",
        "crypto_signal.confluence",
        "crypto_signal.signals",
        "import httpx",
        "import requests",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "launchctl",
        "subprocess.run",
    )
    assert all(token not in source for token in forbidden)
    assert REAL_CAPITAL == 0
