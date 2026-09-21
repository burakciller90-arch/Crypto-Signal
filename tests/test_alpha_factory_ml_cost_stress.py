from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_cost_stress
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.ml_cost_stress import (
    DEFAULT_COST_MULTIPLIERS,
    MLCostStressSemantic,
    build_ml_cost_stress_config,
    run_ml_walk_forward_cost_stress,
)
from research.alpha_factory.ml_walk_forward import (
    build_ml_walk_forward_fold,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


DATASET_IDENTITY = _sha("ml-cost-stress-dataset-v1")


def _features():
    return (
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
    role: PartitionRole,
    *,
    start_ms: int,
    end_ms: int,
    prefix: str,
):
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


def _observations(
    partition,
    *,
    rising_gross: Decimal = Decimal("0.8"),
    falling_gross: Decimal = Decimal("-0.2"),
    cost: Decimal = Decimal("0.1"),
):
    features = _features()
    by_id = {item.feature_id: item for item in features}
    values = (
        ("falling", "expanded"),
        ("falling", "normal"),
        ("rising", "expanded"),
        ("rising", "normal"),
    )
    width = partition.end_ms - partition.start_ms
    rows = []
    for index, (source, (trend, volatility)) in enumerate(
        zip(partition.evidence_identities, values, strict=True)
    ):
        decision_as_of_ms = partition.start_ms + (
            (index + 1) * width // 5
        )
        readings = (
            build_cluster_feature_reading(
                feature=by_id["trend_state"],
                value=trend,
                available_at_ms=decision_as_of_ms - 1,
            ),
            build_cluster_feature_reading(
                feature=by_id["volatility_state"],
                value=volatility,
                available_at_ms=decision_as_of_ms - 1,
            ),
        )
        gross = rising_gross if trend == "rising" else falling_gross
        rows.append(
            build_cluster_research_observation(
                partition_identity=partition.partition_identity,
                source_evidence_identity=source,
                decision_as_of_ms=decision_as_of_ms,
                outcome_available_at_ms=decision_as_of_ms + 10,
                feature_readings=readings,
                gross_outcome_r=gross,
                explicit_cost_r=cost,
            )
        )
    return tuple(rows)


def _fold(
    index: int,
    *,
    train_start: int,
    train_end: int,
    eval_start: int,
    eval_end: int,
    prefix: str,
):
    train = _partition(
        PartitionRole.TRAIN,
        start_ms=train_start,
        end_ms=train_end,
        prefix=f"{prefix}-train",
    )
    evaluation = _partition(
        PartitionRole.OUT_OF_SAMPLE,
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


def _folds():
    return (
        _fold(
            0,
            train_start=0,
            train_end=1000,
            eval_start=1000,
            eval_end=2000,
            prefix="fold0",
        ),
        _fold(
            1,
            train_start=500,
            train_end=2000,
            eval_start=2000,
            eval_end=3000,
            prefix="fold1",
        ),
    )


def _accepted_walk_forward():
    folds = _folds()
    artifacts, _, manifest = run_ml_walk_forward(_features(), folds)
    return folds, artifacts, manifest


def test_cost_stress_is_deterministic_and_uses_fixed_grid() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    first = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )
    second = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )

    assert first == second
    scenario_groups, fold_results, manifest = first
    assert len(scenario_groups) == len(folds)
    assert len(fold_results) == len(folds)
    assert manifest.semantic is (
        MLCostStressSemantic.DESCRIPTIVE_COST_STRESS_NOT_SELECTION
    )
    for scenarios in scenario_groups:
        assert tuple(item.multiplier for item in scenarios) == (
            DEFAULT_COST_MULTIPLIERS
        )


def test_baseline_multiplier_reproduces_accepted_net_r() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    scenario_groups, _, _ = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )

    for scenarios, (_, _, evaluation) in zip(
        scenario_groups,
        artifacts,
        strict=True,
    ):
        baseline = scenarios[0]
        assert baseline.multiplier == Decimal("1.0")
        assert baseline.gross_r_total == evaluation.gross_r_total
        assert (
            baseline.original_cost_r_total
            == evaluation.explicit_cost_r_total
        )
        assert baseline.original_net_r_total == evaluation.net_r_total
        assert baseline.stressed_net_r_total == evaluation.net_r_total


def test_higher_cost_multiplier_never_improves_selected_net_r() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    scenario_groups, _, _ = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )

    for scenarios in scenario_groups:
        baseline = scenarios[0]
        worst = scenarios[-1]
        if baseline.stressed_net_r_total is not None:
            assert worst.stressed_net_r_total is not None
            assert (
                worst.stressed_net_r_total
                <= baseline.stressed_net_r_total
            )
            assert (
                worst.stressed_cost_r_total
                >= baseline.stressed_cost_r_total
            )


def test_cost_stress_never_refits_or_changes_predictions() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    scenario_groups, fold_results, manifest = (
        run_ml_walk_forward_cost_stress(
            _features(),
            folds,
            artifacts,
        )
    )

    assert manifest.model_refit_performed is False
    assert manifest.prediction_set_changed is False
    assert manifest.automatic_scenario_selection is False
    assert manifest.aggregate_winner_selection is False
    assert manifest.calibrated_probability_claim is False
    assert manifest.untouched_forward_used is False
    assert manifest.production_authority is False
    assert manifest.real_capital == 0

    for scenarios, fold_result in zip(
        scenario_groups,
        fold_results,
        strict=True,
    ):
        assert all(item.model_refit_performed is False for item in scenarios)
        assert all(item.prediction_set_changed is False for item in scenarios)
        assert fold_result.model_refit_performed is False
        assert fold_result.prediction_set_changed is False


def test_cost_stress_config_is_fixed_and_fail_closed() -> None:
    config = build_ml_cost_stress_config()
    assert config.multipliers == DEFAULT_COST_MULTIPLIERS
    assert config.automatic_scenario_selection is False
    assert config.model_refit_allowed is False
    assert config.prediction_change_allowed is False

    with pytest.raises(ValueError, match="multiplier grid is fixed"):
        replace(
            config,
            multipliers=(Decimal("1.0"), Decimal("3.0")),
        )
    with pytest.raises(ValueError, match="cannot refit"):
        replace(config, model_refit_allowed=True)


def test_cost_stress_requires_exact_walk_forward_evaluation_identity() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    bad_artifacts = (
        (artifacts[0][0], artifacts[0][1], artifacts[1][2]),
        artifacts[1],
    )
    with pytest.raises(
        ValueError,
        match="accepted walk-forward evaluation identity",
    ):
        run_ml_walk_forward_cost_stress(
            _features(),
            folds,
            bad_artifacts,
        )


def test_cost_stress_requires_exact_artifact_count() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    with pytest.raises(ValueError, match="artifact count mismatch"):
        run_ml_walk_forward_cost_stress(
            _features(),
            folds,
            artifacts[:-1],
        )


def test_cost_stress_scenario_identity_tamper_fails_closed() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    scenario_groups, _, _ = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )
    scenario = scenario_groups[0][-1]
    assert scenario.stressed_net_r_total is not None
    with pytest.raises(ValueError, match="stressed net-R calculation mismatch"):
        replace(
            scenario,
            stressed_net_r_total=scenario.stressed_net_r_total
            + Decimal("0.01"),
        )


def test_cost_stress_manifest_identity_tamper_fails_closed() -> None:
    folds, artifacts, _ = _accepted_walk_forward()
    _, _, manifest = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )
    with pytest.raises(ValueError, match="run identity mismatch"):
        replace(manifest, fold_result_identities=tuple(reversed(
            manifest.fold_result_identities
        )))


def test_cost_stress_source_has_no_refit_execution_or_production_surface() -> None:
    source = inspect.getsource(ml_cost_stress).lower()
    forbidden = (
        "fit_ml_baseline",
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
    assert ml_cost_stress.REAL_CAPITAL == 0


def test_cost_stress_v1_has_no_scenario_winner_or_deploy_api() -> None:
    source = inspect.getsource(ml_cost_stress).lower()
    assert "automatic_scenario_selection" in source
    assert "aggregate_winner_selection" in source
    assert "model_refit_performed" in source
    assert "prediction_set_changed" in source
    assert "def select" not in source
    assert "winner_identity" not in source
    assert "def promote" not in source
    assert "champion_mutation" not in source
    assert "def deploy" not in source
    assert "reinforcement" not in source
