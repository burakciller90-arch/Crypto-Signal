from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import tree_models
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature
from research.alpha_factory.tree_models import (
    MAX_TREE_STRUCTURES,
    MultipleTestingControlStatus,
    TreeEvaluationSemantic,
    TreeLeafAction,
    TreeSearchConfig,
    build_tree_feature_reading,
    build_tree_research_observation,
    evaluate_tree_challenger,
    generate_tree_challengers,
)


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
        dataset_identity=_sha("tree-dataset-v1"),
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
        build_tree_feature_reading(
            feature=by_id["trend_state"],
            value=trend,
            available_at_ms=decision_as_of_ms - 1,
        ),
        build_tree_feature_reading(
            feature=by_id["volatility_state"],
            value=volatility,
            available_at_ms=decision_as_of_ms - 1,
        ),
    )
    return build_tree_research_observation(
        partition_identity=partition.partition_identity,
        source_evidence_identity=source_identity,
        decision_as_of_ms=decision_as_of_ms,
        outcome_available_at_ms=decision_as_of_ms + 10,
        feature_readings=readings,
        gross_outcome_r=Decimal(gross),
        explicit_cost_r=Decimal(cost),
    )


def _train_observations():
    train = _parts()[0]
    sources = train.evidence_identities
    rows = (
        ("rising", "normal", "1.0"),
        ("rising", "normal", "0.8"),
        ("rising", "expanded", "-0.5"),
        ("rising", "expanded", "-0.4"),
        ("falling", "normal", "-0.6"),
        ("falling", "normal", "-0.5"),
        ("falling", "expanded", "-0.2"),
        ("falling", "expanded", "-0.1"),
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


def _validation_observations(*, all_falling: bool = False):
    validation = _parts()[1]
    sources = validation.evidence_identities
    rows = (
        ("falling" if all_falling else "rising", "normal", "0.7"),
        ("falling" if all_falling else "rising", "normal", "0.5"),
        ("falling", "expanded", "-0.3"),
        ("falling", "normal", "-0.4"),
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
        ("rising", "normal", "0.4"),
        ("rising", "expanded", "-0.1"),
        ("falling", "normal", "-0.2"),
        ("falling", "expanded", "-0.2"),
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


def _generated(config: TreeSearchConfig | None = None):
    train = _parts()[0]
    return generate_tree_challengers(
        _features(),
        train,
        _train_observations(),
        config=config or TreeSearchConfig(),
    )


def _trend_candidate():
    candidates, _ = _generated()
    for candidate in candidates:
        if (
            len(candidate.splits) == 1
            and candidate.splits[0].feature_id == "trend_state"
            and candidate.splits[0].expected_value == "rising"
        ):
            return candidate
    raise AssertionError("expected rising trend tree candidate")


def test_tree_search_is_deterministic_and_has_no_automatic_selection() -> None:
    first_candidates, first_manifest = _generated()
    second_candidates, second_manifest = _generated()

    assert first_candidates
    assert first_candidates == second_candidates
    assert first_manifest == second_manifest
    assert first_manifest.automatic_selection is False
    assert first_manifest.out_of_sample_used_in_generation is False
    assert first_manifest.untouched_forward_used is False
    assert first_manifest.multiple_testing_status is (
        MultipleTestingControlStatus
        .BOUNDED_HYPOTHESIS_SET_NO_AUTOMATIC_SELECTION
    )
    assert first_manifest.structures_evaluated <= MAX_TREE_STRUCTURES
    assert tuple(item.generated_identity for item in first_candidates) == (
        first_manifest.candidate_identities
    )


def test_tree_config_is_bounded() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        TreeSearchConfig(max_depth=3)
    with pytest.raises(ValueError, match="max_structures"):
        TreeSearchConfig(max_structures=MAX_TREE_STRUCTURES + 1)
    with pytest.raises(ValueError, match="min_leaf_count"):
        TreeSearchConfig(min_leaf_count=0)


def test_tree_search_honors_structure_budget() -> None:
    candidates, manifest = _generated(
        TreeSearchConfig(max_depth=2, max_structures=3)
    )
    assert manifest.structures_evaluated == 3
    assert len(candidates) <= 3


def test_tree_generation_requires_train_partition() -> None:
    validation = _parts()[1]
    with pytest.raises(ValueError, match="requires the train partition"):
        generate_tree_challengers(
            _features(),
            validation,
            _validation_observations(),
        )


def test_tree_v1_limits_feature_count_and_value_count() -> None:
    train = _parts()[0]
    too_many = tuple(
        build_symbolic_feature(
            feature_id=f"feature_{index}",
            feature_version="v1",
            allowed_values=("a", "b"),
        )
        for index in range(5)
    )
    with pytest.raises(ValueError, match="1..4"):
        generate_tree_challengers(
            too_many,
            train,
            _train_observations(),
        )

    wide_feature = build_symbolic_feature(
        feature_id="trend_state",
        feature_version="wide-v1",
        allowed_values=("a", "b", "c", "d", "e"),
    )
    with pytest.raises(ValueError, match="at most 4 values"):
        generate_tree_challengers(
            (wide_feature,),
            train,
            _train_observations(),
        )


def test_tree_feature_reading_rejects_unknown_value() -> None:
    feature = _features()[0]
    with pytest.raises(ValueError, match="outside feature contract"):
        build_tree_feature_reading(
            feature=feature,
            value="sideways",
            available_at_ms=10,
        )


def test_tree_observation_rejects_future_feature_evidence() -> None:
    train = _parts()[0]
    features = _features()
    future = build_tree_feature_reading(
        feature=features[0],
        value="rising",
        available_at_ms=101,
    )
    current = build_tree_feature_reading(
        feature=features[1],
        value="normal",
        available_at_ms=99,
    )
    with pytest.raises(ValueError, match="unavailable at decision"):
        build_tree_research_observation(
            partition_identity=train.partition_identity,
            source_evidence_identity=train.evidence_identities[0],
            decision_as_of_ms=100,
            outcome_available_at_ms=110,
            feature_readings=(future, current),
            gross_outcome_r=Decimal(1),
            explicit_cost_r=Decimal("0.1"),
        )


def test_tree_observation_rejects_outcome_available_before_decision() -> None:
    train = _parts()[0]
    features = _features()
    readings = tuple(
        build_tree_feature_reading(
            feature=feature,
            value=feature.allowed_values[0],
            available_at_ms=99,
        )
        for feature in features
    )
    with pytest.raises(ValueError, match="cannot predate"):
        build_tree_research_observation(
            partition_identity=train.partition_identity,
            source_evidence_identity=train.evidence_identities[0],
            decision_as_of_ms=100,
            outcome_available_at_ms=99,
            feature_readings=readings,
            gross_outcome_r=Decimal(1),
            explicit_cost_r=Decimal("0.1"),
        )


def test_tree_generation_requires_exact_partition_evidence_coverage() -> None:
    train = _parts()[0]
    with pytest.raises(ValueError, match="cover the partition exactly"):
        generate_tree_challengers(
            _features(),
            train,
            _train_observations()[:-1],
        )


def test_tree_generation_rejects_feature_version_or_identity_mismatch() -> None:
    train = _parts()[0]
    features = _features()
    changed_trend = build_symbolic_feature(
        feature_id="trend_state",
        feature_version="trend-v2",
        allowed_values=("falling", "rising"),
    )
    changed_features = (changed_trend, features[1])
    bad_first = _observation(
        partition=train,
        source_identity=train.evidence_identities[0],
        decision_as_of_ms=100,
        trend="rising",
        volatility="normal",
        gross="1.0",
        features=changed_features,
    )
    observations = (bad_first, *_train_observations()[1:])
    with pytest.raises(ValueError, match="feature identity mismatch"):
        generate_tree_challengers(
            features,
            train,
            observations,
        )


def test_tree_candidate_is_selective_and_bound_to_train_identity() -> None:
    candidate = _trend_candidate()
    assert candidate.training_partition_identity == _parts()[0].partition_identity
    assert candidate.definition.feature_ids == ("trend_state",)
    assert candidate.leaf_actions == (
        TreeLeafAction.ABSTAIN,
        TreeLeafAction.TAKE,
    )
    assert candidate.definition.rule_definition.startswith(
        "tree[trend_state@trend-v1==rising]"
    )


def test_tree_candidate_identity_tampering_fails_closed() -> None:
    candidate = _trend_candidate()
    with pytest.raises(ValueError, match="generated tree identity mismatch"):
        replace(candidate, config_identity=_sha("other-config"))


def test_validation_evaluation_is_descriptive_and_cost_aware() -> None:
    candidate = _trend_candidate()
    validation = _parts()[1]
    evaluation = evaluate_tree_challenger(
        candidate,
        validation,
        _validation_observations(),
        _features(),
    )

    assert evaluation.partition_role is PartitionRole.VALIDATION
    assert evaluation.semantic is (
        TreeEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
    )
    assert evaluation.taken_count == 2
    assert evaluation.gross_r_total == Decimal("1.2")
    assert evaluation.explicit_cost_r_total == Decimal("0.2")
    assert evaluation.net_r_total == Decimal("1.0")
    assert evaluation.average_net_r == Decimal("0.5")


def test_out_of_sample_is_evaluation_only_and_allowed() -> None:
    candidate = _trend_candidate()
    oos = _parts()[2]
    evaluation = evaluate_tree_challenger(
        candidate,
        oos,
        _oos_observations(),
        _features(),
    )
    assert evaluation.partition_role is PartitionRole.OUT_OF_SAMPLE
    assert candidate.training_partition_identity == _parts()[0].partition_identity


def test_train_and_untouched_forward_evaluation_are_closed() -> None:
    candidate = _trend_candidate()
    train, _, _, forward = _parts()
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_tree_challenger(
            candidate,
            train,
            _train_observations(),
            _features(),
        )

    forward_sources = forward.evidence_identities
    forward_observations = tuple(
        _observation(
            partition=forward,
            source_identity=source,
            decision_as_of_ms=3100 + index * 100,
            trend="rising",
            volatility="normal",
            gross="0.2",
        )
        for index, source in enumerate(forward_sources)
    )
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_tree_challenger(
            candidate,
            forward,
            forward_observations,
            _features(),
        )


def test_tree_evaluation_can_abstain_on_every_holdout_row() -> None:
    candidate = _trend_candidate()
    validation = _parts()[1]
    evaluation = evaluate_tree_challenger(
        candidate,
        validation,
        _validation_observations(all_falling=True),
        _features(),
    )
    assert evaluation.taken_count == 0
    assert evaluation.net_r_total is None
    assert evaluation.average_net_r is None
    assert evaluation.max_drawdown_r is None


def test_tree_evaluation_requires_challenger_feature_contract() -> None:
    candidate = next(
        item
        for item in _generated()[0]
        if len(item.splits) == 2
    )
    validation = _parts()[1]
    with pytest.raises(ValueError, match="missing feature"):
        evaluate_tree_challenger(
            candidate,
            validation,
            _validation_observations(),
            (_features()[0],),
        )


def test_tree_evaluation_rejects_incomplete_holdout_evidence() -> None:
    candidate = _trend_candidate()
    validation = _parts()[1]
    with pytest.raises(ValueError, match="cover the partition exactly"):
        evaluate_tree_challenger(
            candidate,
            validation,
            _validation_observations()[:-1],
            _features(),
        )


def test_tree_evaluation_identity_tampering_fails_closed() -> None:
    candidate = _trend_candidate()
    evaluation = evaluate_tree_challenger(
        candidate,
        _parts()[1],
        _validation_observations(),
        _features(),
    )
    with pytest.raises(ValueError, match="tree evaluation identity mismatch"):
        replace(evaluation, taken_count=evaluation.taken_count + 1)


def test_tree_source_has_no_network_execution_or_production_write_surface() -> None:
    source = inspect.getsource(tree_models).lower()
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


def test_tree_v1_contains_no_winner_or_promotion_state() -> None:
    source = inspect.getsource(tree_models).lower()
    assert "automatic_selection" in source
    assert "winner" not in source
    assert "promoted" not in source
    assert "deploy" not in source
