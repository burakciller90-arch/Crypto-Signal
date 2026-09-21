from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import bounded_ml
from research.alpha_factory.bounded_ml import (
    MLConfig,
    MLEvaluationSemantic,
    MLSelectionStatus,
    evaluate_ml,
    fit_ml_baseline,
    predict_ml,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.symbolic_rules import (
    build_symbolic_feature,
    build_symbolic_research_observation,
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


def _partition(role: PartitionRole, *, start_ms: int, prefix: str, count: int):
    return build_research_partition(
        dataset_identity=_sha("bounded-ml-dataset-v1"),
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


def _observations(partition, rows, *, start_ms: int):
    return tuple(
        build_symbolic_research_observation(
            partition_identity=partition.partition_identity,
            source_evidence_identity=source,
            decision_as_of_ms=start_ms + index * 100,
            feature_available_at_ms=start_ms + index * 100 - 1,
            outcome_available_at_ms=start_ms + index * 100 + 10,
            feature_values=(
                ("trend_state", trend),
                ("volatility_state", volatility),
            ),
            gross_outcome_r=Decimal(gross),
            explicit_cost_r=Decimal("0.1"),
        )
        for index, (source, (trend, volatility, gross)) in enumerate(
            zip(partition.evidence_identities, rows, strict=True)
        )
    )


def _train_observations():
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
    return _observations(_parts()[0], rows, start_ms=100)


def _validation_observations():
    rows = (
        ("falling", "expanded", "-0.3"),
        ("falling", "normal", "-0.2"),
        ("rising", "expanded", "0.3"),
        ("rising", "normal", "0.8"),
    )
    return _observations(_parts()[1], rows, start_ms=1100)


def _oos_observations():
    rows = (
        ("falling", "expanded", "-0.1"),
        ("falling", "normal", "-0.1"),
        ("rising", "expanded", "0.2"),
        ("rising", "normal", "0.4"),
    )
    return _observations(_parts()[2], rows, start_ms=2100)


def test_ml_fit_is_deterministic_and_research_only() -> None:
    first = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    second = fit_ml_baseline(_features(), _parts()[0], _train_observations())

    assert first == second
    assert first.selection_status is (
        MLSelectionStatus.SINGLE_PREDECLARED_BASELINE_NO_AUTOMATIC_SELECTION
    )
    assert first.automatic_model_selection is False
    assert first.validation_used_in_fit is False
    assert first.out_of_sample_used_in_fit is False
    assert first.untouched_forward_used is False
    assert first.calibrated_probability is False


def test_ml_fit_uses_net_outcomes_after_explicit_costs() -> None:
    model = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    observations = _train_observations()
    expected = sum(
        (item.gross_outcome_r - item.explicit_cost_r for item in observations),
        start=Decimal(0),
    )
    assert model.training_net_r_total == expected


def test_ml_config_is_hard_bounded() -> None:
    with pytest.raises(ValueError, match="min_cell_support"):
        MLConfig(min_cell_support=0)
    with pytest.raises(ValueError, match="max_features"):
        MLConfig(max_features=0)
    with pytest.raises(ValueError, match="max_features"):
        MLConfig(max_features=5)


def test_ml_fit_requires_train_partition() -> None:
    with pytest.raises(ValueError, match="requires the train partition"):
        fit_ml_baseline(
            _features(),
            _parts()[1],
            _validation_observations(),
        )


def test_ml_fit_requires_exact_partition_coverage() -> None:
    with pytest.raises(ValueError, match="cover the partition exactly"):
        fit_ml_baseline(
            _features(),
            _parts()[0],
            _train_observations()[:-1],
        )


def test_ml_prediction_is_descriptive_not_probability() -> None:
    model = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    prediction = predict_ml(model, _validation_observations()[0])
    assert prediction.semantic == "descriptive_net_r_score_not_probability"
    assert prediction.model_identity == model.model_identity


def test_ml_validation_and_oos_evaluation_are_descriptive_and_cost_aware() -> None:
    model = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    validation = evaluate_ml(
        model,
        _parts()[1],
        _validation_observations(),
    )
    oos = evaluate_ml(model, _parts()[2], _oos_observations())

    assert validation.semantic is (
        MLEvaluationSemantic.DESCRIPTIVE_NET_R_ERROR_NOT_PROBABILITY
    )
    assert validation.partition_role is PartitionRole.VALIDATION
    assert oos.partition_role is PartitionRole.OUT_OF_SAMPLE
    assert validation.net_r_total == (
        validation.gross_r_total - validation.explicit_cost_r_total
    )
    assert validation.mean_absolute_error_r >= 0


def test_ml_train_and_untouched_forward_evaluation_are_closed() -> None:
    model = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    train, _, _, forward = _parts()
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_ml(model, train, _train_observations())

    rows = tuple(("rising", "normal", "0.2") for _ in range(4))
    with pytest.raises(ValueError, match="validation or out-of-sample"):
        evaluate_ml(
            model,
            forward,
            _observations(forward, rows, start_ms=3100),
        )


def test_ml_rejects_feature_contract_mismatch() -> None:
    model = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    feature = build_symbolic_feature(
        feature_id="trend_state",
        feature_version="trend-v1",
        allowed_values=("falling", "rising"),
    )
    bad = build_symbolic_research_observation(
        partition_identity=_parts()[1].partition_identity,
        source_evidence_identity=_parts()[1].evidence_identities[0],
        decision_as_of_ms=1100,
        feature_available_at_ms=1099,
        outcome_available_at_ms=1110,
        feature_values=(("trend_state", "rising"),),
        gross_outcome_r=Decimal("0.2"),
        explicit_cost_r=Decimal("0.1"),
    )
    assert feature.feature_id == "trend_state"
    with pytest.raises(ValueError, match="feature set mismatch"):
        predict_ml(model, bad)


def test_ml_model_identity_tampering_fails_closed() -> None:
    model = fit_ml_baseline(_features(), _parts()[0], _train_observations())
    with pytest.raises(ValueError, match="global mean mismatch"):
        replace(model, global_mean_net_r=model.global_mean_net_r + Decimal(1))


def test_ml_source_has_no_production_or_execution_surface() -> None:
    source = inspect.getsource(bounded_ml).lower()
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
        "promotion",
        "promoted",
        "deploy",
        "reinforcement",
        " q_learning",
    )
    assert all(token not in source for token in forbidden)