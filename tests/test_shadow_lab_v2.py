from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory import shadow_lab_v2
from research.alpha_factory.foundation import (
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
from research.alpha_factory.shadow_lab_v2 import (
    ShadowMetric,
    ShadowResearchFamily,
    ShadowReviewState,
    build_shadow_lab_comparison,
    build_shadow_variant,
)

FAMILIES = tuple(ShadowResearchFamily)


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _experiment(seed: str = "base"):
    dataset = _sha(f"dataset-{seed}")
    roles = (
        PartitionRole.TRAIN,
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
        PartitionRole.UNTOUCHED_FORWARD,
    )
    partitions = tuple(
        build_research_partition(
            dataset_identity=dataset,
            role=role,
            start_ms=index * 100 + 1,
            end_ms=(index + 1) * 100,
            row_count=1,
            evidence_identities=(_sha(f"{seed}-{role.value}-row"),),
        )
        for index, role in enumerate(roles)
    )
    challenger = build_challenger_definition(
        name=f"shadow-{seed}",
        version="v1",
        hypothesis="bounded challenger hypothesis",
        rule_definition="feature_a > 0",
        feature_ids=("feature_a",),
    )
    return build_research_experiment(
        challenger=challenger,
        partitions=partitions,
        evaluation_policy_version="shadow-eval-v1",
        cost_stress_profile_identity=_sha(f"cost-profile-{seed}"),
        reproducibility_seed=7,
    )


def _assessment(experiment, *, ready: bool):
    audit = build_leakage_audit(
        experiment_identity=experiment.experiment_identity,
        audited_at_ms=1_000,
        status=LeakageAuditStatus.PASSED,
        auditor_version="shadow-audit-v1",
    )
    kwargs = dict(
        experiment_identity=experiment.experiment_identity,
        data_contract_audit_identity=_sha("data"),
        reproducibility_identity=_sha("repro"),
        transaction_cost_stress_identity=_sha("cost"),
        in_sample_sanity_identity=_sha("in"),
        out_of_sample_identity=_sha("oos"),
        walk_forward_identity=_sha("wf"),
        untouched_forward_identity=_sha("forward"),
        robustness_ablation_identity=_sha("robust"),
    )
    if not ready:
        kwargs["untouched_forward_identity"] = None
    evidence = build_promotion_gate_evidence(**kwargs)
    assessment = assess_promotion_gate(
        experiment=experiment,
        leakage_audit=audit,
        evidence=evidence,
    )
    if ready:
        assert assessment.status is PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW
    else:
        assert assessment.status is PromotionGateStatus.BLOCKED
    return assessment


def _variant(
    family: ShadowResearchFamily,
    *,
    ready: bool = True,
    seed: str | None = None,
):
    effective_seed = seed or family.value
    experiment = _experiment(effective_seed)
    assessment = _assessment(experiment, ready=ready)
    return build_shadow_variant(
        family=family,
        name=f"{family.value}-challenger",
        policy_version="shadow-policy-v1",
        hypothesis=f"test {family.value} without canonical mutation",
        experiment=experiment,
        parameter_identity=_sha(f"params-{effective_seed}"),
        untouched_forward_identity=_sha(f"forward-{effective_seed}"),
        robustness_identity=_sha(f"robust-{effective_seed}"),
        cost_stress_identity=_sha(f"stress-{effective_seed}"),
        promotion_assessment=assessment,
        metrics=(
            ShadowMetric(
                name="max_drawdown_fraction",
                value=Decimal("0.10"),
                unit="fraction",
                evidence_identity=_sha(f"dd-{effective_seed}"),
            ),
            ShadowMetric(
                name="net_r",
                value=Decimal("0.50"),
                unit="R",
                evidence_identity=_sha(f"net-{effective_seed}"),
            ),
        ),
    )


def test_all_locked_shadow_research_families_are_representable() -> None:
    variants = tuple(_variant(family) for family in FAMILIES)
    comparison = build_shadow_lab_comparison(
        champion_policy_identity=_sha("champion"),
        created_at_ms=2_000,
        variants=variants,
    )

    assert comparison.represented_families == tuple(
        sorted(set(FAMILIES), key=lambda item: item.value)
    )
    assert set(comparison.review_ready_variant_identities) == {
        item.variant_identity for item in variants
    }
    assert comparison.blocked_variant_identities == ()
    assert comparison.winner_identity is None
    assert comparison.automatic_winner_selection is False
    assert comparison.automatic_promotion is False
    assert comparison.champion_write_authority is False
    assert comparison.canonical_capital_write_authority is False
    assert comparison.production_authority is False
    assert comparison.real_capital == 0


def test_missing_forward_promotion_evidence_remains_blocked() -> None:
    blocked = _variant(
        ShadowResearchFamily.FRACTIONAL_KELLY,
        ready=False,
    )
    assert blocked.review_state is ShadowReviewState.BLOCKED

    comparison = build_shadow_lab_comparison(
        champion_policy_identity=_sha("champion"),
        created_at_ms=2_000,
        variants=(blocked,),
    )
    assert comparison.review_ready_variant_identities == ()
    assert comparison.blocked_variant_identities == (blocked.variant_identity,)
    assert comparison.winner_identity is None


def test_review_ready_is_not_promotion_or_winner_selection() -> None:
    variant = _variant(ShadowResearchFamily.CONFLUENCE_THRESHOLD)
    assert variant.review_state is ShadowReviewState.READY_FOR_EXPLICIT_REVIEW
    assert variant.can_self_promote is False
    assert variant.champion_write_authority is False
    assert variant.canonical_capital_write_authority is False

    comparison = build_shadow_lab_comparison(
        champion_policy_identity=_sha("champion"),
        created_at_ms=2_000,
        variants=(variant,),
    )
    with pytest.raises(ValueError, match="cannot select a winner"):
        replace(comparison, winner_identity=variant.variant_identity)


def test_metrics_are_descriptive_and_require_exact_evidence_identity() -> None:
    metric = ShadowMetric(
        name="net_r",
        value=Decimal("-0.25"),
        unit="R",
        evidence_identity=_sha("metric"),
    )
    assert metric.value == Decimal("-0.25")

    with pytest.raises(ValueError, match="SHA256"):
        replace(metric, evidence_identity="not-a-hash")


def test_duplicate_variant_identity_fails_closed() -> None:
    variant = _variant(ShadowResearchFamily.EVENT_WINDOW)
    with pytest.raises(ValueError, match="must be unique"):
        build_shadow_lab_comparison(
            champion_policy_identity=_sha("champion"),
            created_at_ms=2_000,
            variants=(variant, variant),
        )


def test_shadow_variant_identity_tampering_fails_closed() -> None:
    variant = _variant(ShadowResearchFamily.WALLET_FILTER)
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(variant, policy_version="tampered")


def test_shadow_lab_has_no_canonical_execution_or_self_promotion_surface() -> None:
    source = inspect.getsource(shadow_lab_v2).lower()
    forbidden = (
        "place_order",
        "submit_order",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "paperfundledger",
        "epoch2canonicalledger",
        "def promote",
        "def deploy",
    )
    assert all(token not in source for token in forbidden)
    assert shadow_lab_v2.REAL_CAPITAL == 0
