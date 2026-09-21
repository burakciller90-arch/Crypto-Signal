from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_baseline
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.ml_baseline import (
    MAX_ML_FEATURES,
    MLEvaluationSemantic,
    MLModelFamily,
    build_ml_training_config,
    evaluate_ml_baseline,
    fit_ml_baseline,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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
    prefix: str,
    count: int,
):
    return build_research_partition(
        dataset_identity=_sha("ml-dataset-v1"),
        role=role,
        start_ms=start_ms,
        end_ms=start_ms + 1000,
        row_count=count,
        evidence_identities=tuple(
            sorted(_sha(f"{prefix}-{index}") for index in range(count))
        ),
    )


def _parts():
    return (
        _partition(PartitionRole.TRAIN, start_ms=0, prefix="train", count=8),
        _partition(
            PartitionRole.VALIDATION,
            start_ms=1000,
            prefix="validation",
            count=4,
        ),
        _partition(
            PartitionRole.OUT_OF_SAMPLE,
            start_ms=2000,
            prefix="oos",
            count=4,
        ),
        _partition(
            PartitionRole.UNTOUCHED_FORWARD,
            start_ms=3000,
            prefix="forward",
            count=4,
        ),
    )


def _observation(
    *,
    partition,
    source_identity: str,
    decision_as_of_ms: int,
    trend: str,
    volatility: str,
    gross: str,
    cost: str = "0.1",
    outcome_available_at_ms: int | None = None,
    features=None,
):
    specs = features or _features()
    by_id = {item.feature_id: item for item in specs}
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
    return build_cluster_research_observation(
        partition_identity=partition.partition_identity,
        source_evidence_identity=source_identity,
        decision_as_of_ms=decision_as_of_ms,
        outcome_available_at_ms=(
            outcome_available_at_ms
            if outcome_available_at_ms is not None
            else decision_as_of_ms + 10
        ),
        feature_readings=readings,
        gross_outcome_r=Decimal(gross),
        explicit_cost_r=Decimal(cost),
    )


def _training_observations(*, reverse_outcomes: bool = False):
    train = _parts()[0]
    rows = (
        ("falling", "expanded", "-0.4"),
        ("falling", "expanded", "-0.3"),
        ("falling", "normal", "-0.2"),
        ("falling", "normal", "-0.1"),
        ("rising", "expanded", "0.3"),
        ("rising", "expanded", "0.4"),
        ("rising", "normal", "0.8"),
        ("rising", "normal", "1.0"),
    )
    if reverse_outcomes:
        rows = tuple(
            (trend, volatility, str(-Decimal(gross)))
            for trend, volatility, gross in rows
        )
    return tuple(
        _observation(
            partition=train,
            source_identity=source,
            decision_as_of_ms=100 + index * 80,
            trend=trend,
            volatility=volatility,
            gross=gross,
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(train.evidence_identities, rows, strict=True)
        )
    )


def _validation_observations():
    validation = _parts()[1]
    rows = (
        ("falling", "expanded", "-0.2"),
        ("falling", "normal", "-0.1"),
        ("rising", "expanded", "0.4"),
        ("rising", "normal", "0.7"),
    )
    return tuple(
        _observation(
            partition=validation,
            source_identity=source,
            decision_as_of_ms=1100 + index * 150,
            trend=trend,
            volatility=volatility,
            gross=gross,
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(validation.evidence_identities, rows, strict=True)
        )
    )


def _oos_observations():
    oos = _parts()[2]
    rows = (
        ("falling", "expanded", "-0.1"),
        ("falling", "normal", "-0.2"),
        ("rising", "expanded", "0.2"),
        ("rising", "normal", "0.5"),
    )
    return tuple(
        _observation(
            partition=oos,
            source_identity=source,
            decision_as_of_ms=2100 + index * 150,
            trend=trend,
            volatility=volatility,
            gross=gross,
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(oos.evidence_identities, rows, strict=True)
        )
    )


def _fit(*, reverse_outcomes: bool = False):
    return fit_ml_baseline(
        _features(),
        _parts()[0],
        _training_observations(reverse_outcomes=reverse_outcomes),
    )


def test_ml_training_is_deterministic_single_family_and_train_only() -> None:
    first = _fit()
    second = _fit()

    assert first == second
    model, manifest = first
    assert model.model_family is MLModelFamily.CATEGORICAL_COUNT_BASELINE
    assert manifest.validation_used_in_fit is False
    assert manifest.out_of_sample_used_in_fit is False
    assert manifest.untouched_forward_used is False
    assert manifest.automatic_hyperparameter_selection is False
    assert manifest.model_search_performed is False
    assert manifest.production_authority is False
    assert manifest.real_capital == 0


def test_ml_config_is_immutable_single_baseline_without_probability_claim() -> None:
    config = build_ml_training_config()
    assert config.max_features == MAX_ML_FEATURES
    assert config.model_family is MLModelFamily.CATEGORICAL_COUNT_BASELINE
    assert config.automatic_hyperparameter_selection is False
    assert config.model_search_performed is False
    assert config.calibrated_probability_claim is False

    with pytest.raises(ValueError, match="max_features is fixed"):
        replace(config, max_features=MAX_ML_FEATURES - 1)
    with pytest.raises(ValueError, match="probability claim"):
        replace(config, calibrated_probability_claim=True)


def test_ml_fitting_requires_train_partition() -> None:
    with pytest.raises(ValueError, match="requires the train partition"):
        fit_ml_baseline(
            _features(),
            _parts()[1],
            _validation_observations(),
        )


def test_ml_fitting_requires_exact_train_evidence_coverage() -> None:
    with pytest.raises(ValueError, match="cover the partition exactly"):
        fit_ml_baseline(
            _features(),
            _parts()[0],
            _training_observations()[:-1],
        )


def test_ml_training_rejects_outcome_not_available_by_train_end() -> None:
    train = _parts()[0]
    observations = list(_training_observations())
    first = observations[0]
    observations[0] = _observation(
        partition=train,
        source_identity=first.source_evidence_identity,
        decision_as_of_ms=100,
        trend="falling",
        volatility="expanded",
        gross="-0.4",
        outcome_available_at_ms=train.end_ms + 1,
    )
    with pytest.raises(ValueError, match="available by train partition end"):
        fit_ml_baseline(_features(), train, tuple(observations))


def test_ml_training_uses_train_outcomes_but_no_model_search() -> None:
    normal_model, normal_manifest = _fit(reverse_outcomes=False)
    reversed_model, reversed_manifest = _fit(reverse_outcomes=True)

    assert normal_model.model_identity != reversed_model.model_identity
    assert normal_model.positive_count == reversed_model.non_positive_count
    assert normal_manifest.model_search_performed is False
    assert reversed_manifest.model_search_performed is False


def test_ml_feature_contract_mismatch_fails_closed() -> None:
    train = _parts()[0]
    features = _features()
    changed = build_symbolic_feature(
        feature_id="trend_state",
        feature_version="trend-v2",
        allowed_values=("falling", "rising"),
    )
    changed_features = (changed, features[1])
    bad_first = _observation(
        partition=train,
        source_identity=train.evidence_identities[0],
        decision_as_of_ms=100,
        trend="falling",
        volatility="expanded",
        gross="-0.4",
        features=changed_features,
    )
    observations = (bad_first, *_training_observations()[1:])
    with pytest.raises(ValueError, match="feature identity mismatch"):
        fit_ml_baseline(features, train, observations)


def test_ml_model_identity_tampering_fails_closed() -> None:
    model, _ = _fit()
    with pytest.raises(ValueError, match="ML model identity mismatch"):
        replace(model, positive_count=model.positive_count + 1)


def test_validation_evaluation_is_descriptive_cost_aware_not_probability() -> None:
    model, _ = _fit()
    predictions, evaluation = evaluate_ml_baseline(
        model,
        _parts()[1],
        _validation_observations(),
        _features(),
    )

    assert len(predictions) == evaluation.observation_count
    assert evaluation.partition_role is PartitionRole.VALIDATION
    assert evaluation.semantic is (
        MLEvaluationSemantic.DESCRIPTIVE_CLASSIFICATION_NET_R_NOT_PROBABILITY
    )
    assert evaluation.correct_direction_count == evaluation.observation_count
    assert evaluation.positive_prediction_count > 0
    assert evaluation.gross_r_total is not None
    assert evaluation.explicit_cost_r_total is not None
    assert evaluation.net_r_total is not None
    assert (
        evaluation.gross_r_total - evaluation.explicit_cost_r_total
        == evaluation.net_r_total
    )


def test_oos_is_evaluation_only_and_allowed() -> None:
    model, manifest = _fit()
    _, evaluation = evaluate_ml_baseline(
        model,
        _parts()[2],
        _oos_observations(),
        _features(),
    )
    assert evaluation.partition_role is PartitionRole.OUT_OF_SAMPLE
    assert manifest.out_of_sample_used_in_fit is False


def test_train_and_untouched_forward_evaluation_are_closed() -> None:
    model, _ = _fit()
    train, _, _, forward = _parts()

    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_ml_baseline(
            model,
            train,
            _training_observations(),
            _features(),
        )

    forward_observations = tuple(
        _observation(
            partition=forward,
            source_identity=source,
            decision_as_of_ms=3100 + index * 150,
            trend="rising",
            volatility="normal",
            gross="0.2",
        )
        for index, source in enumerate(forward.evidence_identities)
    )
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_ml_baseline(
            model,
            forward,
            forward_observations,
            _features(),
        )


def test_ml_evaluation_rejects_incomplete_holdout_evidence() -> None:
    model, _ = _fit()
    with pytest.raises(ValueError, match="cover the partition exactly"):
        evaluate_ml_baseline(
            model,
            _parts()[1],
            _validation_observations()[:-1],
            _features(),
        )


def test_ml_prediction_and_evaluation_identities_fail_closed_on_tamper() -> None:
    model, _ = _fit()
    predictions, evaluation = evaluate_ml_baseline(
        model,
        _parts()[1],
        _validation_observations(),
        _features(),
    )

    with pytest.raises(ValueError, match="prediction label"):
        replace(
            predictions[0],
            predicted_positive=not predictions[0].predicted_positive,
        )

    with pytest.raises(ValueError, match="ML evaluation identity mismatch"):
        replace(
            evaluation,
            correct_direction_count=evaluation.correct_direction_count - 1,
        )


def test_ml_source_has_no_network_execution_or_production_write_surface() -> None:
    source = inspect.getsource(ml_baseline).lower()
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
    assert ml_baseline.REAL_CAPITAL == 0


def test_ml_v1_has_no_winner_promotion_deploy_or_rl_surface() -> None:
    source = inspect.getsource(ml_baseline).lower()
    assert "automatic_hyperparameter_selection" in source
    assert "model_search_performed" in source
    assert "calibrated_probability_claim" in source
    assert "def select_ml_winner" not in source
    assert "winner_identity" not in source
    assert "promotion" not in source
    assert "promoted" not in source
    assert "deploy" not in source
    assert "reinforcement" not in source
