from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import clustering_regime
from research.alpha_factory.clustering_regime import (
    MAX_CLUSTERS,
    MAX_ITERATIONS,
    ClusterEvaluationSemantic,
    ClusterFitStatus,
    ClusterSearchConfig,
    MultipleTestingControlStatus,
    build_cluster_feature_reading,
    build_cluster_research_observation,
    evaluate_cluster_model,
    fit_cluster_models,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
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
        dataset_identity=_sha("cluster-dataset-v1"),
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
    features=None,
):
    feature_specs = features or _features()
    by_id = {item.feature_id: item for item in feature_specs}
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
        outcome_available_at_ms=decision_as_of_ms + 10,
        feature_readings=readings,
        gross_outcome_r=Decimal(gross),
        explicit_cost_r=Decimal(cost),
    )


def _train_observations(*, reverse_outcomes: bool = False):
    train = _parts()[0]
    sources = train.evidence_identities
    rows = (
        ("falling", "expanded", "-0.2"),
        ("falling", "expanded", "-0.1"),
        ("falling", "normal", "-0.5"),
        ("falling", "normal", "-0.4"),
        ("rising", "expanded", "0.1"),
        ("rising", "expanded", "0.2"),
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
            decision_as_of_ms=100 + index * 50,
            trend=trend,
            volatility=volatility,
            gross=gross,
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(sources, rows, strict=True)
        )
    )


def _validation_observations():
    validation = _parts()[1]
    sources = validation.evidence_identities
    rows = (
        ("falling", "expanded", "-0.3"),
        ("falling", "normal", "-0.2"),
        ("rising", "expanded", "0.3"),
        ("rising", "normal", "0.7"),
    )
    return tuple(
        _observation(
            partition=validation,
            source_identity=source,
            decision_as_of_ms=1100 + index * 100,
            trend=trend,
            volatility=volatility,
            gross=gross,
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(sources, rows, strict=True)
        )
    )


def _oos_observations():
    oos = _parts()[2]
    sources = oos.evidence_identities
    rows = (
        ("falling", "expanded", "-0.1"),
        ("falling", "normal", "-0.1"),
        ("rising", "expanded", "0.2"),
        ("rising", "normal", "0.4"),
    )
    return tuple(
        _observation(
            partition=oos,
            source_identity=source,
            decision_as_of_ms=2100 + index * 100,
            trend=trend,
            volatility=volatility,
            gross=gross,
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(sources, rows, strict=True)
        )
    )


def _fit(config: ClusterSearchConfig | None = None):
    train = _parts()[0]
    return fit_cluster_models(
        _features(),
        train,
        _train_observations(),
        config=config or ClusterSearchConfig(),
    )


def test_cluster_fit_is_deterministic_and_has_no_automatic_selection() -> None:
    first_models, first_attempts, first_manifest = _fit()
    second_models, second_attempts, second_manifest = _fit()

    assert first_models
    assert first_models == second_models
    assert first_attempts == second_attempts
    assert first_manifest == second_manifest
    assert first_manifest.automatic_selection is False
    assert first_manifest.out_of_sample_used_in_fit is False
    assert first_manifest.untouched_forward_used is False
    assert first_manifest.multiple_testing_status is (
        MultipleTestingControlStatus
        .BOUNDED_CLUSTER_COUNT_NO_AUTOMATIC_SELECTION
    )
    assert first_manifest.model_identities == tuple(
        item.model_identity for item in first_models
    )


def test_cluster_fit_is_unsupervised_with_respect_to_outcomes() -> None:
    train = _parts()[0]
    first_models, first_attempts, first_manifest = fit_cluster_models(
        _features(),
        train,
        _train_observations(),
    )
    second_models, second_attempts, second_manifest = fit_cluster_models(
        _features(),
        train,
        _train_observations(reverse_outcomes=True),
    )

    assert first_models == second_models
    assert first_attempts == second_attempts
    assert first_manifest == second_manifest


def test_cluster_config_is_bounded() -> None:
    with pytest.raises(ValueError, match="min_clusters"):
        ClusterSearchConfig(min_clusters=1)
    with pytest.raises(ValueError, match="max_clusters"):
        ClusterSearchConfig(max_clusters=MAX_CLUSTERS + 1)
    with pytest.raises(ValueError, match="max_iterations"):
        ClusterSearchConfig(max_iterations=MAX_ITERATIONS + 1)
    with pytest.raises(ValueError, match="min_cluster_size"):
        ClusterSearchConfig(min_cluster_size=0)


def test_cluster_fit_requires_train_partition() -> None:
    validation = _parts()[1]
    with pytest.raises(ValueError, match="requires the train partition"):
        fit_cluster_models(
            _features(),
            validation,
            _validation_observations(),
        )


def test_cluster_feature_reading_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="outside feature contract"):
        build_cluster_feature_reading(
            feature=_features()[0],
            value="sideways",
            available_at_ms=1,
        )


def test_cluster_observation_rejects_future_feature() -> None:
    train = _parts()[0]
    features = _features()
    future = build_cluster_feature_reading(
        feature=features[0],
        value="rising",
        available_at_ms=101,
    )
    current = build_cluster_feature_reading(
        feature=features[1],
        value="normal",
        available_at_ms=99,
    )
    with pytest.raises(ValueError, match="unavailable at decision"):
        build_cluster_research_observation(
            partition_identity=train.partition_identity,
            source_evidence_identity=train.evidence_identities[0],
            decision_as_of_ms=100,
            outcome_available_at_ms=110,
            feature_readings=(future, current),
            gross_outcome_r=Decimal(1),
            explicit_cost_r=Decimal("0.1"),
        )


def test_cluster_observation_rejects_outcome_before_decision() -> None:
    train = _parts()[0]
    readings = tuple(
        build_cluster_feature_reading(
            feature=feature,
            value=feature.allowed_values[0],
            available_at_ms=99,
        )
        for feature in _features()
    )
    with pytest.raises(ValueError, match="cannot predate"):
        build_cluster_research_observation(
            partition_identity=train.partition_identity,
            source_evidence_identity=train.evidence_identities[0],
            decision_as_of_ms=100,
            outcome_available_at_ms=99,
            feature_readings=readings,
            gross_outcome_r=Decimal(1),
            explicit_cost_r=Decimal("0.1"),
        )


def test_cluster_fit_requires_exact_partition_coverage() -> None:
    train = _parts()[0]
    with pytest.raises(ValueError, match="cover the partition exactly"):
        fit_cluster_models(
            _features(),
            train,
            _train_observations()[:-1],
        )


def test_cluster_feature_contract_mismatch_fails_closed() -> None:
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
        gross="-0.2",
        features=changed_features,
    )
    observations = (bad_first, *_train_observations()[1:])
    with pytest.raises(ValueError, match="feature identity mismatch"):
        fit_cluster_models(features, train, observations)


def test_insufficient_unique_patterns_are_unresolved_not_forced() -> None:
    train = _parts()[0]
    observations = tuple(
        _observation(
            partition=train,
            source_identity=source,
            decision_as_of_ms=100 + index * 50,
            trend="rising",
            volatility="normal",
            gross="0.1",
        )
        for index, source in enumerate(train.evidence_identities)
    )
    models, attempts, manifest = fit_cluster_models(
        _features(),
        train,
        observations,
        config=ClusterSearchConfig(min_clusters=2, max_clusters=2),
    )
    assert models == ()
    assert attempts[0].status is (
        ClusterFitStatus.UNRESOLVED_INSUFFICIENT_UNIQUE_PATTERNS
    )
    assert manifest.model_identities == ()


def test_small_clusters_are_unresolved_not_force_merged() -> None:
    models, attempts, _ = _fit(
        ClusterSearchConfig(
            min_clusters=2,
            max_clusters=2,
            min_cluster_size=3,
        )
    )
    assert models == ()
    assert attempts[0].status is ClusterFitStatus.UNRESOLVED_SMALL_CLUSTER


def test_accepted_models_bind_only_feature_snapshot_set() -> None:
    models, attempts, manifest = _fit()
    assert models
    assert any(
        attempt.status is ClusterFitStatus.ACCEPTED
        for attempt in attempts
    )
    assert all(
        model.training_feature_set_identity
        == manifest.training_feature_set_identity
        for model in models
    )


def test_cluster_model_identity_tampering_fails_closed() -> None:
    model = _fit()[0][0]
    with pytest.raises(ValueError, match="cluster model identity mismatch"):
        replace(model, config_identity=_sha("other-config"))


def test_validation_evaluation_is_descriptive_and_cost_aware() -> None:
    model = _fit()[0][0]
    evaluation = evaluate_cluster_model(
        model,
        _parts()[1],
        _validation_observations(),
        _features(),
    )

    assert evaluation.partition_role is PartitionRole.VALIDATION
    assert evaluation.semantic is (
        ClusterEvaluationSemantic
        .DESCRIPTIVE_REGIME_NET_R_NOT_PROBABILITY
    )
    assert sum(
        bucket.observation_count for bucket in evaluation.buckets
    ) == 4
    gross = sum(
        (
            bucket.gross_r_total or Decimal(0)
            for bucket in evaluation.buckets
        ),
        start=Decimal(0),
    )
    costs = sum(
        (
            bucket.explicit_cost_r_total or Decimal(0)
            for bucket in evaluation.buckets
        ),
        start=Decimal(0),
    )
    net = sum(
        (
            bucket.net_r_total or Decimal(0)
            for bucket in evaluation.buckets
        ),
        start=Decimal(0),
    )
    assert gross == Decimal("0.5")
    assert costs == Decimal("0.4")
    assert net == Decimal("0.1")


def test_out_of_sample_is_evaluation_only_and_allowed() -> None:
    model = _fit()[0][0]
    evaluation = evaluate_cluster_model(
        model,
        _parts()[2],
        _oos_observations(),
        _features(),
    )
    assert evaluation.partition_role is PartitionRole.OUT_OF_SAMPLE
    assert model.training_partition_identity == _parts()[0].partition_identity


def test_train_and_untouched_forward_evaluation_are_closed() -> None:
    model = _fit()[0][0]
    train, _, _, forward = _parts()

    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_cluster_model(
            model,
            train,
            _train_observations(),
            _features(),
        )

    forward_observations = tuple(
        _observation(
            partition=forward,
            source_identity=source,
            decision_as_of_ms=3100 + index * 100,
            trend="rising",
            volatility="normal",
            gross="0.1",
        )
        for index, source in enumerate(forward.evidence_identities)
    )
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_cluster_model(
            model,
            forward,
            forward_observations,
            _features(),
        )


def test_cluster_evaluation_rejects_incomplete_holdout_evidence() -> None:
    model = _fit()[0][0]
    with pytest.raises(ValueError, match="cover the partition exactly"):
        evaluate_cluster_model(
            model,
            _parts()[1],
            _validation_observations()[:-1],
            _features(),
        )


def test_cluster_evaluation_rejects_model_feature_contract_mismatch() -> None:
    model = _fit()[0][0]
    with pytest.raises(ValueError, match="feature contract mismatch"):
        evaluate_cluster_model(
            model,
            _parts()[1],
            _validation_observations(),
            (_features()[0],),
        )


def test_cluster_bucket_identity_tampering_fails_closed() -> None:
    model = _fit()[0][0]
    evaluation = evaluate_cluster_model(
        model,
        _parts()[1],
        _validation_observations(),
        _features(),
    )
    non_empty = next(
        bucket for bucket in evaluation.buckets if bucket.observation_count
    )
    assert non_empty.average_net_r is not None
    with pytest.raises(ValueError, match="cluster bucket identity mismatch"):
        replace(
            non_empty,
            average_net_r=non_empty.average_net_r + Decimal("0.1"),
        )


def test_cluster_source_has_no_network_execution_or_production_write_surface() -> None:
    source = inspect.getsource(clustering_regime).lower()
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


def test_cluster_v1_contains_no_selection_promotion_or_deploy_api() -> None:
    source = inspect.getsource(clustering_regime).lower()
    assert "automatic_selection" in source
    assert "def select_cluster" not in source
    assert "winner_identity" not in source
    assert "promotion" not in source
    assert "promoted" not in source
    assert "deploy" not in source
