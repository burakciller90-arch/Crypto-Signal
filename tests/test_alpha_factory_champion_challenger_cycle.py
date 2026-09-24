from __future__ import annotations

import hashlib
import inspect
from decimal import Decimal

import pytest

from research.alpha_factory import champion_challenger_cycle
from research.alpha_factory.champion_challenger_cycle import (
    WC4CycleSemantic,
    WC4CycleStatus,
    build_wc4_champion_challenger_cycle,
)
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
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


def _partition(
    *,
    dataset_identity: str,
    role: PartitionRole,
    start_ms: int,
    end_ms: int,
    prefix: str,
):
    return build_research_partition(
        dataset_identity=dataset_identity,
        role=role,
        start_ms=start_ms,
        end_ms=end_ms,
        row_count=4,
        evidence_identities=tuple(
            sorted(_sha(f"{prefix}-{index}") for index in range(4))
        ),
    )


def _observations(partition, *, cost: Decimal = Decimal("0.1")):
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


def _fold(
    *,
    dataset_identity: str,
    index: int,
    train_start: int,
    train_end: int,
    eval_start: int,
    eval_end: int,
    prefix: str,
):
    train = _partition(
        dataset_identity=dataset_identity,
        role=PartitionRole.TRAIN,
        start_ms=train_start,
        end_ms=train_end,
        prefix=f"{prefix}-train",
    )
    evaluation = _partition(
        dataset_identity=dataset_identity,
        role=PartitionRole.OUT_OF_SAMPLE,
        start_ms=eval_start,
        end_ms=eval_end,
        prefix=f"{prefix}-eval",
    )
    return build_ml_walk_forward_fold(
        fold_index=index,
        training_partition=train,
        evaluation_partition=evaluation,
        training_observations=_observations(train),
        evaluation_observations=_observations(evaluation),
    )


def _artifacts(tag: str = "a", *, supervisor: bool = False):
    dataset_identity = _sha(f"wc4-cycle-dataset-{tag}")
    folds = (
        _fold(
            dataset_identity=dataset_identity,
            index=0,
            train_start=0,
            train_end=1000,
            eval_start=1000,
            eval_end=2000,
            prefix=f"{tag}-fold0",
        ),
        _fold(
            dataset_identity=dataset_identity,
            index=1,
            train_start=500,
            train_end=2000,
            eval_start=2000,
            eval_end=3000,
            prefix=f"{tag}-fold1",
        ),
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
        dataset_identity=dataset_identity,
        role=PartitionRole.UNTOUCHED_FORWARD,
        start_ms=3000,
        end_ms=4000,
        prefix=f"{tag}-forward",
    )
    forward_observations = _observations(forward_partition)
    frozen = build_ml_family_untouched_forward_freeze(
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
    evaluated = evaluate_ml_family_untouched_forward_paper(
        frozen,
        _features(),
        references[-1][0],
        expansion[0][-1][0],
        as_of_ms=4000,
        untouched_partition=forward_partition,
        untouched_observations=forward_observations,
    )
    forward = (
        evaluated[0],
        evaluated[1],
        evaluated[2],
        evaluated[3],
        frozen,
        evaluated[4],
    )
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
    if supervisor:
        _, dossier = record_ml_supervisor_acceptance(
            dossier,
            reviewer_role="crypto-signal-supervisor",
            review_version="wc4-cycle-review-v1",
            acceptance_note="manual review boundary only; no promotion authority",
        )
    return machine, dossier, frozen, evaluated[4]


def test_wc4_cycle_is_deterministic_review_ready_and_not_promoted() -> None:
    first = _artifacts()
    second = _artifacts()
    first_cycle = build_wc4_champion_challenger_cycle(*first)
    second_cycle = build_wc4_champion_challenger_cycle(*second)

    assert first_cycle == second_cycle
    assert first_cycle.status is WC4CycleStatus.REVIEW_READY_NOT_PROMOTED
    assert first_cycle.semantic is (
        WC4CycleSemantic.FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION
    )
    assert (
        first_cycle.champion_reference_model_identity
        == first[2].reference_model_identity
    )
    assert first_cycle.challenger_model_identity == first[2].challenger_model_identity
    assert first_cycle.untouched_forward_used is True
    assert first_cycle.human_supervisor_required is True
    assert first_cycle.performance_winner_declared is False
    assert first_cycle.champion_state_mutation_performed is False
    assert first_cycle.automatic_promotion is False
    assert first_cycle.deploy_authority is False
    assert first_cycle.production_authority is False
    assert first_cycle.real_capital == 0


def test_wc4_supervisor_acceptance_still_does_not_promote_or_deploy() -> None:
    artifacts = _artifacts(supervisor=True)
    cycle = build_wc4_champion_challenger_cycle(*artifacts)

    assert cycle.status is (
        WC4CycleStatus.SUPERVISOR_ACCEPTED_MANUAL_REVIEW_NOT_PROMOTED
    )
    assert cycle.supervisor_acceptance_identity is not None
    assert cycle.human_supervisor_required is True
    assert cycle.performance_winner_declared is False
    assert cycle.champion_state_mutation_performed is False
    assert cycle.automatic_promotion is False
    assert cycle.deploy_authority is False
    assert cycle.production_authority is False
    assert cycle.real_capital == 0


def test_wc4_cycle_rejects_cross_cycle_untouched_forward_evidence() -> None:
    first = _artifacts("a")
    second = _artifacts("b")

    with pytest.raises(ValueError, match="machine/untouched-forward"):
        build_wc4_champion_challenger_cycle(
            first[0],
            first[1],
            second[2],
            second[3],
        )


def test_wc4_cycle_source_has_no_execution_or_production_write_surface() -> None:
    source = inspect.getsource(champion_challenger_cycle).lower()
    forbidden = (
        "crypto_signal.paper",
        "crypto_signal.product",
        "crypto_signal.confluence",
        "crypto_signal.signals",
        "import httpx",
        "import requests",
        "import urllib",
        "import socket",
        "subprocess",
        "place_order",
        "submit_order",
        "write_text(",
        "write_bytes(",
        "unlink(",
        "def promote",
        "def deploy",
    )
    assert all(token not in source for token in forbidden)
    assert "performance_winner_declared" in source
    assert "champion_state_mutation_performed" in source
    assert "winner_identity" not in source
    assert champion_challenger_cycle.REAL_CAPITAL == 0
