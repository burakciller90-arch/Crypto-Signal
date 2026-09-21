from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_robustness_ablation
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.ml_cost_stress import (
    run_ml_walk_forward_cost_stress,
)
from research.alpha_factory.ml_robustness_ablation import (
    MLRegimeEvidenceStatus,
    MLRobustnessSemantic,
    build_ml_robustness_config,
    run_ml_robustness_ablation,
)
from research.alpha_factory.ml_walk_forward import (
    build_ml_walk_forward_fold,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


DATASET_IDENTITY = _sha("ml-robustness-dataset-v1")


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
    cost: Decimal = Decimal("0.1"),
):
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
    for index, (source, (regime, trend, volatility)) in enumerate(
        zip(partition.evidence_identities, values, strict=True)
    ):
        decision_as_of_ms = partition.start_ms + (
            (index + 1) * width // 5
        )
        readings = (
            build_cluster_feature_reading(
                feature=by_id["regime_state"],
                value=regime,
                available_at_ms=decision_as_of_ms - 1,
            ),
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
        gross = (
            Decimal("0.8")
            if trend == "rising"
            else Decimal("-0.2")
        )
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


def _accepted_evidence():
    folds = _folds()
    artifacts, _, _ = run_ml_walk_forward(_features(), folds)
    cost_stress = run_ml_walk_forward_cost_stress(
        _features(),
        folds,
        artifacts,
    )
    return folds, artifacts, cost_stress


def test_robustness_is_deterministic_and_binds_cost_stress() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    first = run_ml_robustness_ablation(
        _features(),
        folds,
        artifacts,
        cost_stress,
        regime_feature_id="regime_state",
    )
    second = run_ml_robustness_ablation(
        _features(),
        folds,
        artifacts,
        cost_stress,
        regime_feature_id="regime_state",
    )

    assert first == second
    ablations, regimes, fold_results, sensitivity, manifest = first
    assert len(ablations) == len(folds)
    assert len(regimes) == len(folds)
    assert len(fold_results) == len(folds)
    assert manifest.semantic is (
        MLRobustnessSemantic.DESCRIPTIVE_ROBUSTNESS_ABLATION_NOT_SELECTION
    )
    assert manifest.cost_stress_run_identity == cost_stress[2].run_identity
    assert manifest.fold_sensitivity_identity == sensitivity.summary_identity
    assert manifest.automatic_feature_selection is False
    assert manifest.automatic_regime_selection is False
    assert manifest.aggregate_winner_selection is False
    assert manifest.model_refit_performed is False
    assert manifest.accepted_prediction_set_mutated is False
    assert manifest.calibrated_probability_claim is False
    assert manifest.untouched_forward_used is False
    assert manifest.production_authority is False
    assert manifest.real_capital == 0


def test_feature_ablation_exposes_prediction_sensitivity_without_refit() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    ablations, _, _, _, _ = run_ml_robustness_ablation(
        _features(),
        folds,
        artifacts,
        cost_stress,
        regime_feature_id="regime_state",
    )

    for fold_results in ablations:
        trend = next(
            item
            for item in fold_results
            if item.omitted_feature_id == "trend_state"
        )
        volatility = next(
            item
            for item in fold_results
            if item.omitted_feature_id == "volatility_state"
        )
        assert trend.changed_prediction_count > 0
        assert trend.ablated_positive_prediction_count < (
            trend.baseline_positive_prediction_count
        )
        assert volatility.changed_prediction_count == 0
        assert all(item.model_refit_performed is False for item in fold_results)
        assert all(
            item.accepted_prediction_set_mutated is False
            for item in fold_results
        )


def test_regime_slices_keep_observed_and_no_evidence_states() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    _, regimes, _, _, _ = run_ml_robustness_ablation(
        _features(),
        folds,
        artifacts,
        cost_stress,
        regime_feature_id="regime_state",
    )

    for fold_results in regimes:
        transition = next(
            item for item in fold_results if item.regime_value == "transition"
        )
        assert transition.status is MLRegimeEvidenceStatus.NO_EVIDENCE
        assert transition.observation_identities == ()
        assert transition.positive_prediction_count == 0
        assert transition.net_r_total is None

        observed = tuple(
            item
            for item in fold_results
            if item.regime_value in {"risk_off", "risk_on"}
        )
        assert all(
            item.status is MLRegimeEvidenceStatus.OBSERVED
            for item in observed
        )
        assert all(item.observation_identities for item in observed)


def test_fold_sensitivity_is_descriptive_not_selection() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    ablations, _, _, sensitivity, manifest = run_ml_robustness_ablation(
        _features(),
        folds,
        artifacts,
        cost_stress,
        regime_feature_id="regime_state",
    )

    assert sensitivity.automatic_fold_selection is False
    assert sensitivity.baseline_net_r_by_fold == tuple(
        (index, artifact[2].net_r_total)
        for index, artifact in enumerate(artifacts)
    )
    assert sensitivity.max_cost_stress_net_r_by_fold == tuple(
        (index, scenarios[-1].stressed_net_r_total)
        for index, scenarios in enumerate(cost_stress[0])
    )
    assert sensitivity.ablation_changed_prediction_counts_by_fold == tuple(
        (
            index,
            sum(item.changed_prediction_count for item in fold_results),
        )
        for index, fold_results in enumerate(ablations)
    )
    assert manifest.aggregate_winner_selection is False


def test_robustness_requires_exact_accepted_cost_stress_evidence() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    bad_cost_stress = (
        tuple(reversed(cost_stress[0])),
        cost_stress[1],
        cost_stress[2],
    )
    with pytest.raises(
        ValueError,
        match="exact accepted cost-stress evidence",
    ):
        run_ml_robustness_ablation(
            _features(),
            folds,
            artifacts,
            bad_cost_stress,
            regime_feature_id="regime_state",
        )


def test_robustness_requires_exact_accepted_evaluation_identity() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    bad_artifacts = (
        (artifacts[0][0], artifacts[0][1], artifacts[1][2]),
        artifacts[1],
    )
    with pytest.raises(ValueError):
        run_ml_robustness_ablation(
            _features(),
            folds,
            bad_artifacts,
            cost_stress,
            regime_feature_id="regime_state",
        )


def test_robustness_config_is_explicit_and_fail_closed() -> None:
    config = build_ml_robustness_config(
        _features(),
        regime_feature_id="regime_state",
    )
    assert config.max_feature_ablations == 3
    assert config.automatic_feature_selection is False
    assert config.automatic_regime_selection is False
    assert config.model_refit_allowed is False

    with pytest.raises(ValueError, match="one explicit regime feature"):
        build_ml_robustness_config(
            _features(),
            regime_feature_id="missing_regime",
        )
    with pytest.raises(ValueError, match="automatic feature selection"):
        replace(config, automatic_feature_selection=True)


def test_ablation_identity_tampering_fails_closed() -> None:
    folds, artifacts, cost_stress = _accepted_evidence()
    ablations, _, _, _, _ = run_ml_robustness_ablation(
        _features(),
        folds,
        artifacts,
        cost_stress,
        regime_feature_id="regime_state",
    )
    stable = next(
        item
        for item in ablations[0]
        if item.omitted_feature_id == "volatility_state"
    )
    with pytest.raises(ValueError, match="ablation result identity mismatch"):
        replace(stable, changed_prediction_count=1)


def test_robustness_source_has_no_refit_execution_or_production_surface() -> None:
    source = inspect.getsource(ml_robustness_ablation).lower()
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
    assert ml_robustness_ablation.REAL_CAPITAL == 0


def test_robustness_v1_has_no_winner_promotion_deploy_or_rl_api() -> None:
    source = inspect.getsource(ml_robustness_ablation).lower()
    assert "aggregate_winner_selection" in source
    assert "automatic_feature_selection" in source
    assert "automatic_regime_selection" in source
    assert "def select" not in source
    assert "winner_identity" not in source
    assert "def promote" not in source
    assert "champion_mutation" not in source
    assert "def deploy" not in source
    assert "reinforcement" not in source
