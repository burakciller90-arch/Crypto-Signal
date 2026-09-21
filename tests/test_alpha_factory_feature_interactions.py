from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import feature_interactions
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.feature_interactions import (
    MAX_INTERACTION_HYPOTHESES,
    InteractionEvaluationSemantic,
    InteractionSearchConfig,
    MultipleTestingControlStatus,
    evaluate_interaction_hypothesis,
    generate_interaction_hypotheses,
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
        dataset_identity=_sha("interaction-dataset-v1"),
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


def _validation_observations(*, remove_rising_normal: bool = False):
    validation = _parts()[1]
    sources = validation.evidence_identities
    rows = (
        ("falling", "expanded", "-0.3"),
        ("falling", "normal", "-0.2"),
        ("rising", "expanded", "0.3"),
        (
            "rising",
            "expanded" if remove_rising_normal else "normal",
            "0.8",
        ),
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


def _generated(config: InteractionSearchConfig | None = None):
    return generate_interaction_hypotheses(
        _features(),
        _parts()[0],
        _train_observations(),
        config=config or InteractionSearchConfig(),
    )


def _rising_normal_hypothesis():
    hypotheses, _ = _generated()
    for hypothesis in hypotheses:
        values = {
            item.feature_id: item.expected_value
            for item in hypothesis.predicates
        }
        if values == {
            "trend_state": "rising",
            "volatility_state": "normal",
        }:
            return hypothesis
    raise AssertionError("expected rising+normal interaction hypothesis")


def test_interaction_search_is_deterministic_and_no_auto_selection() -> None:
    first_hypotheses, first_manifest = _generated()
    second_hypotheses, second_manifest = _generated()

    assert first_hypotheses
    assert first_hypotheses == second_hypotheses
    assert first_manifest == second_manifest
    assert first_manifest.automatic_selection is False
    assert first_manifest.outcome_used_in_generation is False
    assert first_manifest.out_of_sample_used_in_generation is False
    assert first_manifest.untouched_forward_used is False
    assert first_manifest.multiple_testing_status is (
        MultipleTestingControlStatus
        .BOUNDED_INTERACTION_SET_NO_AUTOMATIC_SELECTION
    )
    assert first_manifest.hypothesis_identities == tuple(
        item.hypothesis_identity for item in first_hypotheses
    )


def test_interaction_generation_is_outcome_independent() -> None:
    train = _parts()[0]
    first = generate_interaction_hypotheses(
        _features(),
        train,
        _train_observations(),
    )
    second = generate_interaction_hypotheses(
        _features(),
        train,
        _train_observations(reverse_outcomes=True),
    )
    assert first == second


def test_interaction_config_is_bounded() -> None:
    with pytest.raises(ValueError, match="min_train_support"):
        InteractionSearchConfig(min_train_support=0)
    with pytest.raises(ValueError, match="max_hypotheses"):
        InteractionSearchConfig(
            max_hypotheses=MAX_INTERACTION_HYPOTHESES + 1
        )


def test_interaction_generation_requires_train_partition() -> None:
    with pytest.raises(ValueError, match="requires the train partition"):
        generate_interaction_hypotheses(
            _features(),
            _parts()[1],
            _validation_observations(),
        )


def test_interaction_support_filter_and_budget_are_explicit() -> None:
    hypotheses, manifest = _generated(
        InteractionSearchConfig(
            min_train_support=2,
            max_hypotheses=2,
        )
    )
    assert len(hypotheses) == 2
    assert len(manifest.hypothesis_identities) == 2
    assert manifest.candidates_considered >= 2
    assert all(item.training_support_count >= 2 for item in hypotheses)


def test_interaction_generation_can_return_no_supported_hypotheses() -> None:
    hypotheses, manifest = _generated(
        InteractionSearchConfig(min_train_support=3)
    )
    assert hypotheses == ()
    assert manifest.hypothesis_identities == ()
    assert manifest.candidates_considered == 4


def test_interaction_requires_at_least_two_features() -> None:
    with pytest.raises(ValueError, match="2..6"):
        generate_interaction_hypotheses(
            (_features()[0],),
            _parts()[0],
            _train_observations(),
        )


def test_interaction_generation_requires_exact_partition_coverage() -> None:
    with pytest.raises(ValueError, match="cover the partition exactly"):
        generate_interaction_hypotheses(
            _features(),
            _parts()[0],
            _train_observations()[:-1],
        )


def test_interaction_feature_contract_mismatch_fails_closed() -> None:
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
        generate_interaction_hypotheses(features, train, observations)


def test_hypothesis_identity_tampering_fails_closed() -> None:
    hypothesis = _rising_normal_hypothesis()
    with pytest.raises(ValueError, match="interaction hypothesis identity mismatch"):
        replace(
            hypothesis,
            training_support_count=hypothesis.training_support_count + 1,
        )


def test_validation_evaluation_measures_increment_vs_marginals() -> None:
    hypothesis = _rising_normal_hypothesis()
    evaluation = evaluate_interaction_hypothesis(
        hypothesis,
        _parts()[1],
        _validation_observations(),
        _features(),
    )

    assert evaluation.partition_role is PartitionRole.VALIDATION
    assert evaluation.semantic is (
        InteractionEvaluationSemantic
        .DESCRIPTIVE_INCREMENT_NOT_CAUSAL_OR_PROBABILITY
    )
    assert evaluation.interaction_metric.observation_count == 1
    assert evaluation.interaction_metric.average_net_r == Decimal("0.7")
    assert evaluation.first_marginal_metric.average_net_r == Decimal("0.45")
    assert evaluation.second_marginal_metric.average_net_r == Decimal("0.2")
    assert evaluation.incremental_vs_best_marginal_r == Decimal("0.25")


def test_interaction_evaluation_preserves_explicit_costs() -> None:
    evaluation = evaluate_interaction_hypothesis(
        _rising_normal_hypothesis(),
        _parts()[1],
        _validation_observations(),
        _features(),
    )
    assert evaluation.interaction_metric.gross_r_total == Decimal("0.8")
    assert evaluation.interaction_metric.explicit_cost_r_total == Decimal("0.1")
    assert evaluation.interaction_metric.net_r_total == Decimal("0.7")


def test_empty_holdout_interaction_has_no_increment_metric() -> None:
    evaluation = evaluate_interaction_hypothesis(
        _rising_normal_hypothesis(),
        _parts()[1],
        _validation_observations(remove_rising_normal=True),
        _features(),
    )
    assert evaluation.interaction_metric.observation_count == 0
    assert evaluation.interaction_metric.average_net_r is None
    assert evaluation.incremental_vs_best_marginal_r is None


def test_out_of_sample_is_evaluation_only_and_allowed() -> None:
    hypothesis = _rising_normal_hypothesis()
    evaluation = evaluate_interaction_hypothesis(
        hypothesis,
        _parts()[2],
        _oos_observations(),
        _features(),
    )
    assert evaluation.partition_role is PartitionRole.OUT_OF_SAMPLE
    assert hypothesis.training_partition_identity == _parts()[0].partition_identity


def test_train_and_untouched_forward_evaluation_are_closed() -> None:
    hypothesis = _rising_normal_hypothesis()
    train, _, _, forward = _parts()

    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_interaction_hypothesis(
            hypothesis,
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
            gross="0.2",
        )
        for index, source in enumerate(forward.evidence_identities)
    )
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_interaction_hypothesis(
            hypothesis,
            forward,
            forward_observations,
            _features(),
        )


def test_interaction_evaluation_rejects_incomplete_evidence() -> None:
    with pytest.raises(ValueError, match="cover the partition exactly"):
        evaluate_interaction_hypothesis(
            _rising_normal_hypothesis(),
            _parts()[1],
            _validation_observations()[:-1],
            _features(),
        )


def test_interaction_evaluation_rejects_missing_hypothesis_feature() -> None:
    with pytest.raises(ValueError, match="missing feature"):
        evaluate_interaction_hypothesis(
            _rising_normal_hypothesis(),
            _parts()[1],
            _validation_observations(),
            (_features()[0],),
        )


def test_interaction_metric_identity_tampering_fails_closed() -> None:
    evaluation = evaluate_interaction_hypothesis(
        _rising_normal_hypothesis(),
        _parts()[1],
        _validation_observations(),
        _features(),
    )
    metric = evaluation.interaction_metric
    assert metric.average_net_r is not None
    with pytest.raises(ValueError, match="interaction metric identity mismatch"):
        replace(metric, average_net_r=metric.average_net_r + Decimal("0.1"))


def test_interaction_source_has_no_network_execution_or_production_write_surface() -> None:
    source = inspect.getsource(feature_interactions).lower()
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


def test_interaction_v1_contains_no_winner_promotion_or_deploy_api() -> None:
    source = inspect.getsource(feature_interactions).lower()
    assert "automatic_selection" in source
    assert "def select_interaction" not in source
    assert "winner_identity" not in source
    assert "promotion" not in source
    assert "promoted" not in source
    assert "deploy" not in source
