from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_promotion_dossier
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    PromotionGateStatus,
    build_research_partition,
)
from research.alpha_factory.ml_family_cost_stress import (
    run_ml_family_cost_stress,
)
from research.alpha_factory.ml_family_expansion import run_ml_family_expansion
from research.alpha_factory.ml_family_robustness_ablation import (
    run_ml_family_robustness_ablation,
)
from research.alpha_factory.ml_family_untouched_forward import (
    build_ml_family_untouched_forward_freeze,
    evaluate_ml_family_untouched_forward_paper,
)
from research.alpha_factory.ml_promotion_dossier import (
    MLSupervisorDecision,
    build_ml_promotion_dossier,
    record_ml_supervisor_acceptance,
)
from research.alpha_factory.ml_walk_forward import (
    build_ml_walk_forward_fold,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


DATASET_IDENTITY = _sha("ml-promotion-dossier-dataset-v1")


def _features():
    return (
        build_symbolic_feature(
            feature_id="regime_state",
            feature_version="regime-v1",
            allowed_values=("risk_off", "risk_on", "transition"),
        ),
        build_symbolic_feature(
            feature_id="trend_state",
            feature_version="trend-v1",
            allowed_values=("falling", "rising"),
        ),
        build_symbolic_feature(
            feature_id="volatility_state",
            feature_version="vol-v1",
            allowed_values=("expanded", "normal"),
        ),
    )


def _partition(role, start_ms, end_ms, prefix):
    return build_research_partition(
        dataset_identity=DATASET_IDENTITY,
        role=role,
        start_ms=start_ms,
        end_ms=end_ms,
        row_count=4,
        evidence_identities=tuple(
            sorted(_sha(f"{prefix}-{index}") for index in range(4))
        ),
    )


def _observations(partition, cost=Decimal("0.1")):
    features = _features()
    by_id = {item.feature_id: item for item in features}
    values = (
        ("risk_off", "falling", "expanded"),
        ("risk_on", "falling", "normal"),
        ("risk_on", "rising", "expanded"),
        ("risk_off", "rising", "normal"),
    )
    width = partition.end_ms - partition.start_ms
    rows = []
    for index, (source, values_row) in enumerate(
        zip(partition.evidence_identities, values, strict=True)
    ):
        regime, trend, volatility = values_row
        decision = partition.start_ms + ((index + 1) * width // 5)
        readings = (
            build_cluster_feature_reading(
                feature=by_id["regime_state"],
                value=regime,
                available_at_ms=decision - 1,
            ),
            build_cluster_feature_reading(
                feature=by_id["trend_state"],
                value=trend,
                available_at_ms=decision - 1,
            ),
            build_cluster_feature_reading(
                feature=by_id["volatility_state"],
                value=volatility,
                available_at_ms=decision - 1,
            ),
        )
        gross = Decimal("0.8") if trend == "rising" else Decimal("-0.2")
        rows.append(
            build_cluster_research_observation(
                partition_identity=partition.partition_identity,
                source_evidence_identity=source,
                decision_as_of_ms=decision,
                outcome_available_at_ms=decision + 10,
                feature_readings=readings,
                gross_outcome_r=gross,
                explicit_cost_r=cost,
            )
        )
    return tuple(rows)


def _fold(index, train_start, train_end, eval_start, eval_end, prefix):
    train = _partition(
        PartitionRole.TRAIN,
        train_start,
        train_end,
        f"{prefix}-train",
    )
    evaluation = _partition(
        PartitionRole.OUT_OF_SAMPLE,
        eval_start,
        eval_end,
        f"{prefix}-eval",
    )
    return build_ml_walk_forward_fold(
        fold_index=index,
        training_partition=train,
        evaluation_partition=evaluation,
        training_observations=_observations(train),
        evaluation_observations=_observations(evaluation),
    )


def _chain():
    folds = (
        _fold(0, 0, 1000, 1000, 2000, "fold0"),
        _fold(1, 500, 2000, 2000, 3000, "fold1"),
    )
    walk = run_ml_walk_forward(_features(), folds)
    references = walk[0]
    expansion = run_ml_family_expansion(_features(), folds, references)
    cost = run_ml_family_cost_stress(
        _features(),
        folds,
        references,
        expansion,
    )
    robustness = run_ml_family_robustness_ablation(
        _features(),
        folds,
        references,
        expansion,
        cost,
        regime_feature_id="regime_state",
    )
    forward_partition = _partition(
        PartitionRole.UNTOUCHED_FORWARD,
        3000,
        4000,
        "forward",
    )
    forward_observations = _observations(forward_partition)
    frozen_snapshot = build_ml_family_untouched_forward_freeze(
        _features(),
        folds,
        references,
        expansion,
        cost,
        robustness,
        regime_feature_id="regime_state",
        created_at_ms=2999,
        window_start_ms=3000,
        window_end_ms=4000,
    )
    evaluated_forward = evaluate_ml_family_untouched_forward_paper(
        frozen_snapshot,
        _features(),
        references[-1][0],
        expansion[0][-1][0],
        as_of_ms=4000,
        untouched_partition=forward_partition,
        untouched_observations=forward_observations,
    )
    forward = (
        evaluated_forward[0],
        evaluated_forward[1],
        evaluated_forward[2],
        evaluated_forward[3],
        frozen_snapshot,
        evaluated_forward[4],
    )
    return (
        folds,
        walk,
        expansion,
        cost,
        robustness,
        forward_partition,
        forward_observations,
        forward,
    )


def _build():
    (
        folds,
        walk,
        expansion,
        cost,
        robustness,
        forward_partition,
        forward_observations,
        forward,
    ) = _chain()
    machine, dossier = build_ml_promotion_dossier(
        _features(),
        folds,
        walk,
        expansion,
        cost,
        robustness,
        forward_partition,
        forward_observations,
        forward,
        regime_feature_id="regime_state",
    )
    return machine, dossier


def test_machine_dossier_is_deterministic_and_ready_only() -> None:
    first = _build()
    second = _build()
    assert first == second

    machine, dossier = first
    assert len(machine.data_contract_identity) == 64
    assert len(machine.leakage_audit_identity) == 64
    assert len(machine.reproducibility_identity) == 64
    assert len(machine.transaction_cost_stress_identity) == 64
    assert len(machine.in_sample_sanity_identity) == 64
    assert len(machine.out_of_sample_identity) == 64
    assert len(machine.walk_forward_identity) == 64
    assert len(machine.untouched_forward_identity) == 64
    assert len(machine.robustness_ablation_identity) == 64
    assert dossier.status is PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW
    assert dossier.supervisor_acceptance_identity is None
    assert dossier.automatic_promotion is False
    assert dossier.champion_write_authority is False
    assert dossier.deploy_authority is False
    assert dossier.production_authority is False
    assert dossier.real_capital == 0


def test_dossier_requires_exact_accepted_chain() -> None:
    (
        folds,
        walk,
        expansion,
        cost,
        robustness,
        forward_partition,
        forward_observations,
        forward,
    ) = _chain()
    bad_cost = (tuple(reversed(cost[0])), cost[1], cost[2])
    with pytest.raises(ValueError, match="exact cost-stress evidence"):
        build_ml_promotion_dossier(
            _features(),
            folds,
            walk,
            expansion,
            bad_cost,
            robustness,
            forward_partition,
            forward_observations,
            forward,
            regime_feature_id="regime_state",
        )


def test_forward_evidence_cannot_reuse_historical_source_identity() -> None:
    (
        folds,
        walk,
        expansion,
        cost,
        robustness,
        _,
        _,
        _,
    ) = _chain()
    reused = folds[-1].evaluation_partition.evidence_identities[0]
    ids = tuple(
        sorted(
            (reused,)
            + tuple(_sha(f"reused-forward-{i}") for i in range(3))
        )
    )
    forward_partition = build_research_partition(
        dataset_identity=DATASET_IDENTITY,
        role=PartitionRole.UNTOUCHED_FORWARD,
        start_ms=3000,
        end_ms=4000,
        row_count=4,
        evidence_identities=ids,
    )
    forward_observations = _observations(forward_partition)
    frozen_snapshot = build_ml_family_untouched_forward_freeze(
        _features(),
        folds,
        walk[0],
        expansion,
        cost,
        robustness,
        regime_feature_id="regime_state",
        created_at_ms=2999,
        window_start_ms=3000,
        window_end_ms=4000,
    )
    with pytest.raises(ValueError, match="overlaps prior research evidence"):
        evaluate_ml_family_untouched_forward_paper(
            frozen_snapshot,
            _features(),
            walk[0][-1][0],
            expansion[0][-1][0],
            as_of_ms=4000,
            untouched_partition=forward_partition,
            untouched_observations=forward_observations,
        )


def test_supervisor_acceptance_is_explicit_and_still_manual_only() -> None:
    _, dossier = _build()
    acceptance, accepted = record_ml_supervisor_acceptance(
        dossier,
        reviewer_role="crypto-signal-supervisor",
        review_version="supervisor-review-v1",
        acceptance_note="accepted evidence dossier for manual promotion review only",
    )

    assert acceptance.decision is (
        MLSupervisorDecision.ACCEPTED_FOR_MANUAL_PROMOTION_REVIEW_ONLY
    )
    assert acceptance.manual_promotion_required is True
    assert acceptance.champion_write_authority is False
    assert acceptance.deploy_authority is False
    assert acceptance.production_authority is False
    assert accepted.status is (
        PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION
    )
    assert accepted.supervisor_acceptance_identity == (
        acceptance.acceptance_identity
    )
    assert accepted.automatic_promotion is False
    assert accepted.champion_write_authority is False
    assert accepted.deploy_authority is False
    assert accepted.production_authority is False


def test_supervisor_acceptance_cannot_be_replayed() -> None:
    _, dossier = _build()
    _, accepted = record_ml_supervisor_acceptance(
        dossier,
        reviewer_role="crypto-signal-supervisor",
        review_version="supervisor-review-v1",
        acceptance_note="manual-review-only",
    )
    with pytest.raises(ValueError, match="requires ready machine dossier"):
        record_ml_supervisor_acceptance(
            accepted,
            reviewer_role="crypto-signal-supervisor",
            review_version="supervisor-review-v1",
            acceptance_note="duplicate",
        )


def test_identity_tampering_fails_closed() -> None:
    machine, dossier = _build()
    with pytest.raises(ValueError, match="machine-evidence identity mismatch"):
        replace(machine, walk_forward_identity=_sha("tampered"))
    with pytest.raises(ValueError, match="promotion dossier identity mismatch"):
        replace(dossier, machine_evidence_identity=_sha("tampered"))


def test_promotion_dossier_source_has_no_execution_or_production_surface() -> None:
    source = inspect.getsource(ml_promotion_dossier).lower()
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
        "subprocess",
        "write_text(",
        "write_bytes(",
        "unlink(",
    )
    assert all(token not in source for token in forbidden)
    assert ml_promotion_dossier.REAL_CAPITAL == 0


def test_dossier_has_no_promote_champion_write_deploy_or_rl_api() -> None:
    source = inspect.getsource(ml_promotion_dossier).lower()
    assert "promotiongatestatus.ready_for_supervisor_review" in source
    assert "automatic_promotion" in source
    assert "champion_write_authority" in source
    assert "manual_promotion_required" in source
    assert "def promote" not in source
    assert "def deploy" not in source
    assert "place_order" not in source
    assert "reinforcement" not in source
