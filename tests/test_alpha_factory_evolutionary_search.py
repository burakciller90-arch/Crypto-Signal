from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import evolutionary_search
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.evolutionary_search import (
    LCG_MODULUS,
    MAX_GENERATIONS,
    MAX_POPULATION_SIZE,
    MIN_POPULATION_SIZE,
    EvolutionEvaluationSemantic,
    EvolutionSearchConfig,
    MultipleTestingControlStatus,
    evaluate_evolution_genome,
    run_evolutionary_search,
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
        dataset_identity=_sha("evolution-dataset-v1"),
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
        ("rising", "normal", "0.8"),
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


def _run(
    config: EvolutionSearchConfig | None = None,
    *,
    reverse_outcomes: bool = False,
):
    return run_evolutionary_search(
        _features(),
        _parts()[0],
        _train_observations(reverse_outcomes=reverse_outcomes),
        config=config or EvolutionSearchConfig(),
    )


def test_evolution_search_is_deterministic_and_has_no_winner_selection() -> None:
    first = _run()
    second = _run()

    assert first == second
    population, generations, metrics, manifest = first
    assert len(population) == manifest.final_genome_identities.__len__()
    assert len(generations) == EvolutionSearchConfig().generations
    assert metrics
    assert manifest.fitness_used_for_reproduction is False
    assert manifest.automatic_winner_selection is False
    assert manifest.validation_used_in_search is False
    assert manifest.out_of_sample_used_in_search is False
    assert manifest.untouched_forward_used is False
    assert manifest.multiple_testing_status is (
        MultipleTestingControlStatus.BOUNDED_EVOLUTION_NO_AUTOMATIC_WINNER
    )


def test_evolution_seed_changes_structural_trajectory() -> None:
    first = _run(EvolutionSearchConfig(seed=1))
    second = _run(EvolutionSearchConfig(seed=2))

    first_generations = tuple(
        item.genome_identities for item in first[1]
    )
    second_generations = tuple(
        item.genome_identities for item in second[1]
    )
    assert first_generations != second_generations


def test_train_outcomes_do_not_drive_reproduction_trajectory() -> None:
    first = _run(reverse_outcomes=False)
    second = _run(reverse_outcomes=True)

    assert tuple(item.genome_identities for item in first[1]) == tuple(
        item.genome_identities for item in second[1]
    )
    assert first[3].final_genome_identities == second[3].final_genome_identities
    assert first[3].fitness_used_for_reproduction is False
    assert first[2] != second[2]


def test_evolution_config_is_hard_bounded() -> None:
    with pytest.raises(ValueError, match="population_size"):
        EvolutionSearchConfig(population_size=MIN_POPULATION_SIZE - 1)
    with pytest.raises(ValueError, match="population_size"):
        EvolutionSearchConfig(population_size=MAX_POPULATION_SIZE + 1)
    with pytest.raises(ValueError, match="generations"):
        EvolutionSearchConfig(generations=MAX_GENERATIONS + 1)
    with pytest.raises(ValueError, match="min_train_support"):
        EvolutionSearchConfig(min_train_support=0)
    with pytest.raises(ValueError, match="seed"):
        EvolutionSearchConfig(seed=LCG_MODULUS)


def test_evolution_search_requires_train_partition() -> None:
    with pytest.raises(ValueError, match="requires the train partition"):
        run_evolutionary_search(
            _features(),
            _parts()[1],
            _validation_observations(),
        )


def test_evolution_search_requires_exact_train_evidence_coverage() -> None:
    with pytest.raises(ValueError, match="cover the partition exactly"):
        run_evolutionary_search(
            _features(),
            _parts()[0],
            _train_observations()[:-1],
        )


def test_evolution_insufficient_supported_population_fails_closed() -> None:
    with pytest.raises(ValueError, match="insufficient supported genomes"):
        _run(
            EvolutionSearchConfig(
                population_size=4,
                generations=2,
                min_train_support=3,
            )
        )


def test_evolution_feature_contract_mismatch_fails_closed() -> None:
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
        run_evolutionary_search(features, train, observations)


def test_training_metrics_include_explicit_costs() -> None:
    _, _, metrics, _ = _run()
    assert metrics
    metric = metrics[0]
    assert metric.gross_r_total - metric.explicit_cost_r_total == (
        metric.net_r_total
    )
    assert metric.explicit_cost_r_total > 0


def test_training_metric_identity_tampering_fails_closed() -> None:
    metric = _run()[2][0]
    with pytest.raises(ValueError, match="training metric identity mismatch"):
        replace(
            metric,
            training_partition_identity=_sha("other-training-partition"),
        )


def test_validation_evaluation_is_descriptive_and_cost_aware() -> None:
    genome = _run()[0][0]
    evaluation = evaluate_evolution_genome(
        genome,
        _parts()[1],
        _validation_observations(),
        _features(),
    )

    assert evaluation.partition_role is PartitionRole.VALIDATION
    assert evaluation.semantic is (
        EvolutionEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
    )
    if evaluation.matched_count:
        assert evaluation.gross_r_total is not None
        assert evaluation.explicit_cost_r_total is not None
        assert evaluation.net_r_total is not None
        assert (
            evaluation.gross_r_total - evaluation.explicit_cost_r_total
            == evaluation.net_r_total
        )


def test_out_of_sample_is_evaluation_only_and_allowed() -> None:
    genome = _run()[0][0]
    evaluation = evaluate_evolution_genome(
        genome,
        _parts()[2],
        _oos_observations(),
        _features(),
    )
    assert evaluation.partition_role is PartitionRole.OUT_OF_SAMPLE


def test_train_and_untouched_forward_evaluation_are_closed() -> None:
    genome = _run()[0][0]
    train, _, _, forward = _parts()

    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_evolution_genome(
            genome,
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
        evaluate_evolution_genome(
            genome,
            forward,
            forward_observations,
            _features(),
        )


def test_evolution_evaluation_rejects_incomplete_holdout_evidence() -> None:
    with pytest.raises(ValueError, match="cover the partition exactly"):
        evaluate_evolution_genome(
            _run()[0][0],
            _parts()[1],
            _validation_observations()[:-1],
            _features(),
        )


def test_evolution_evaluation_rejects_missing_genome_feature() -> None:
    with pytest.raises(ValueError, match="missing feature"):
        evaluate_evolution_genome(
            _run()[0][0],
            _parts()[1],
            _validation_observations(),
            (_features()[0],),
        )


def test_evolution_evaluation_identity_tampering_fails_closed() -> None:
    evaluation = evaluate_evolution_genome(
        _run()[0][0],
        _parts()[1],
        _validation_observations(),
        _features(),
    )
    if evaluation.matched_count:
        assert evaluation.average_net_r is not None
        with pytest.raises(
            ValueError,
            match="evolution evaluation identity mismatch",
        ):
            replace(
                evaluation,
                average_net_r=evaluation.average_net_r + Decimal("0.1"),
            )


def test_evolution_source_has_no_network_execution_or_production_write_surface() -> None:
    source = inspect.getsource(evolutionary_search).lower()
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


def test_evolution_v1_contains_no_winner_promotion_or_deploy_api() -> None:
    source = inspect.getsource(evolutionary_search).lower()
    assert "fitness_used_for_reproduction" in source
    assert "automatic_winner_selection" in source
    assert "def select_evolution_winner" not in source
    assert "winner_identity" not in source
    assert "promotion" not in source
    assert "promoted" not in source
    assert "deploy" not in source
