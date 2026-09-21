from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import symbolic_rules
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.symbolic_rules import (
    ResearchEvaluationSemantic,
    SymbolicSearchConfig,
    build_symbolic_feature,
    build_symbolic_research_observation,
    evaluate_symbolic_challenger,
    generate_symbolic_challengers,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _features():
    return (
        build_symbolic_feature(
            feature_id="trend_state",
            feature_version="v1",
            allowed_values=("falling", "rising"),
        ),
        build_symbolic_feature(
            feature_id="volatility_state",
            feature_version="v1",
            allowed_values=("expanded", "normal"),
        ),
    )


def _generated():
    return generate_symbolic_challengers(
        _features(),
        config=SymbolicSearchConfig(
            max_predicates=2,
            max_challengers=8,
        ),
    )


def _target_challenger():
    expected = (
        "trend_state@v1==rising && "
        "volatility_state@v1==normal"
    )
    return next(
        item
        for item in _generated()
        if item.definition.rule_definition == expected
    )


def _partition(role: PartitionRole = PartitionRole.TRAIN):
    sources = tuple(sorted((_sha("row-a"), _sha("row-b"), _sha("row-c"))))
    return build_research_partition(
        dataset_identity=_sha("dataset"),
        role=role,
        start_ms=100,
        end_ms=400,
        row_count=3,
        evidence_identities=sources,
    )


def _observation(
    partition_identity: str,
    source_identity: str,
    *,
    decision_ms: int,
    trend: str,
    volatility: str,
    gross: str,
    cost: str = "0.1",
):
    return build_symbolic_research_observation(
        partition_identity=partition_identity,
        source_evidence_identity=source_identity,
        decision_as_of_ms=decision_ms,
        feature_available_at_ms=decision_ms,
        outcome_available_at_ms=decision_ms + 50,
        feature_values=(
            ("trend_state", trend),
            ("volatility_state", volatility),
        ),
        gross_outcome_r=Decimal(gross),
        explicit_cost_r=Decimal(cost),
    )


def _observations(partition):
    sources = partition.evidence_identities
    return (
        _observation(
            partition.partition_identity,
            sources[0],
            decision_ms=150,
            trend="rising",
            volatility="normal",
            gross="1.0",
        ),
        _observation(
            partition.partition_identity,
            sources[1],
            decision_ms=250,
            trend="falling",
            volatility="normal",
            gross="0.4",
        ),
        _observation(
            partition.partition_identity,
            sources[2],
            decision_ms=350,
            trend="rising",
            volatility="normal",
            gross="-0.5",
        ),
    )


def test_symbolic_generation_is_deterministic_bounded_and_data_free() -> None:
    first = _generated()
    second = generate_symbolic_challengers(
        tuple(reversed(_features())),
        config=SymbolicSearchConfig(
            max_predicates=2,
            max_challengers=8,
        ),
    )

    assert first == second
    assert len(first) == 8
    assert len({item.generated_identity for item in first}) == 8
    assert all(1 <= len(item.predicates) <= 2 for item in first)
    assert all(
        item.definition.version
        == symbolic_rules.SYMBOLIC_RULE_ENGINE_VERSION
        for item in first
    )

    parameters = inspect.signature(
        generate_symbolic_challengers
    ).parameters
    assert set(parameters) == {"features", "config"}
    assert "observation" not in inspect.getsource(
        generate_symbolic_challengers
    ).lower()


def test_generator_truncation_is_deterministic() -> None:
    generated = generate_symbolic_challengers(
        _features(),
        config=SymbolicSearchConfig(
            max_predicates=2,
            max_challengers=5,
        ),
    )
    assert len(generated) == 5
    assert tuple(
        item.definition.rule_definition for item in generated
    ) == (
        "trend_state@v1==falling",
        "trend_state@v1==rising",
        "volatility_state@v1==expanded",
        "volatility_state@v1==normal",
        "trend_state@v1==falling && volatility_state@v1==expanded",
    )


def test_feature_and_generated_identity_tampering_fail_closed() -> None:
    feature = _features()[0]
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(feature, feature_version="v2")

    challenger = _target_challenger()
    with pytest.raises(
        ValueError,
        match="unsupported symbolic-rule engine",
    ):
        replace(
            challenger,
            engine_version="alpha-factory-symbolic-rule-v1/999",
        )


def test_evaluation_uses_explicit_costs_and_is_order_invariant() -> None:
    partition = _partition()
    challenger = _target_challenger()
    observations = _observations(partition)

    first = evaluate_symbolic_challenger(
        challenger,
        partition,
        observations,
    )
    second = evaluate_symbolic_challenger(
        challenger,
        partition,
        tuple(reversed(observations)),
    )

    assert first == second
    assert first.semantic is (
        ResearchEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
    )
    assert first.observation_count == 3
    assert first.matched_count == 2
    assert first.gross_r_total == Decimal("0.5")
    assert first.explicit_cost_r_total == Decimal("0.2")
    assert first.net_r_total == Decimal("0.3")
    assert first.average_net_r == Decimal("0.15")
    assert first.median_net_r == Decimal("0.15")
    assert first.max_drawdown_r == Decimal("0.6")


def test_no_match_is_not_invented_as_zero_performance() -> None:
    partition = _partition()
    challenger = next(
        item
        for item in _generated()
        if item.definition.rule_definition
        == "volatility_state@v1==expanded"
    )
    evaluation = evaluate_symbolic_challenger(
        challenger,
        partition,
        _observations(partition),
    )

    assert evaluation.matched_count == 0
    assert evaluation.gross_r_total is None
    assert evaluation.explicit_cost_r_total is None
    assert evaluation.net_r_total is None
    assert evaluation.average_net_r is None
    assert evaluation.median_net_r is None
    assert evaluation.max_drawdown_r is None


def test_evaluation_requires_exact_partition_evidence_coverage() -> None:
    partition = _partition()
    observations = _observations(partition)
    challenger = _target_challenger()

    with pytest.raises(ValueError, match="cover every partition"):
        evaluate_symbolic_challenger(
            challenger,
            partition,
            observations[:2],
        )

    wrong_source = build_symbolic_research_observation(
        partition_identity=partition.partition_identity,
        source_evidence_identity=_sha("outside"),
        decision_as_of_ms=150,
        feature_available_at_ms=150,
        outcome_available_at_ms=200,
        feature_values=(
            ("trend_state", "rising"),
            ("volatility_state", "normal"),
        ),
        gross_outcome_r=Decimal("1"),
        explicit_cost_r=Decimal("0.1"),
    )
    with pytest.raises(ValueError, match="outside partition"):
        evaluate_symbolic_challenger(
            challenger,
            partition,
            (wrong_source, observations[1], observations[2]),
        )


def test_feature_availability_is_point_in_time_safe() -> None:
    partition = _partition()
    with pytest.raises(ValueError, match="unavailable at decision"):
        build_symbolic_research_observation(
            partition_identity=partition.partition_identity,
            source_evidence_identity=partition.evidence_identities[0],
            decision_as_of_ms=150,
            feature_available_at_ms=151,
            outcome_available_at_ms=200,
            feature_values=(("trend_state", "rising"),),
            gross_outcome_r=Decimal("1"),
            explicit_cost_r=Decimal("0.1"),
        )


def test_untouched_forward_evaluation_remains_closed() -> None:
    partition = _partition(PartitionRole.UNTOUCHED_FORWARD)
    with pytest.raises(ValueError, match="untouched-forward evaluation remains closed"):
        evaluate_symbolic_challenger(
            _target_challenger(),
            partition,
            _observations(partition),
        )


def test_observation_identity_tampering_fails_closed() -> None:
    partition = _partition()
    observation = _observations(partition)[0]
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(
            observation,
            explicit_cost_r=Decimal("0.2"),
            net_outcome_r=Decimal("0.8"),
        )


def test_symbolic_engine_has_no_dynamic_execution_or_production_write_surface() -> None:
    source = inspect.getsource(symbolic_rules).lower()
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
        "eval(",
        "exec(",
        "assess_promotion_gate",
    )
    assert all(token not in source for token in forbidden)
