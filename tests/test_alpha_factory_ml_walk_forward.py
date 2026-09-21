from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_walk_forward
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.ml_walk_forward import (
    MLWalkForwardSemantic,
    build_ml_walk_forward_fold,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


DATASET_IDENTITY = _sha("ml-walk-forward-dataset-v1")


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
    count: int = 4,
):
    return build_research_partition(
        dataset_identity=DATASET_IDENTITY,
        role=role,
        start_ms=start_ms,
        end_ms=end_ms,
        row_count=count,
        evidence_identities=tuple(
            sorted(_sha(f"{prefix}-{index}") for index in range(count))
        ),
    )


def _observations(
    partition,
    *,
    positive: bool,
    late_outcome: bool = False,
):
    features = _features()
    by_id = {item.feature_id: item for item in features}
    values = (
        ("falling", "expanded"),
        ("falling", "normal"),
        ("rising", "expanded"),
        ("rising", "normal"),
    )
    rows = []
    width = partition.end_ms - partition.start_ms
    for index, (source, (trend, volatility)) in enumerate(
        zip(partition.evidence_identities, values, strict=True)
    ):
        decision_as_of_ms = partition.start_ms + (
            (index + 1) * width // (len(values) + 1)
        )
        gross = (
            Decimal("0.7")
            if positive and trend == "rising"
            else Decimal("-0.2")
        )
        outcome_available_at_ms = decision_as_of_ms + 10
        if late_outcome and index == 0:
            outcome_available_at_ms = partition.end_ms + 1
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
        rows.append(
            build_cluster_research_observation(
                partition_identity=partition.partition_identity,
                source_evidence_identity=source,
                decision_as_of_ms=decision_as_of_ms,
                outcome_available_at_ms=outcome_available_at_ms,
                feature_readings=readings,
                gross_outcome_r=gross,
                explicit_cost_r=Decimal("0.1"),
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
    train_prefix: str,
    eval_prefix: str,
    late_train_outcome: bool = False,
):
    train = _partition(
        PartitionRole.TRAIN,
        start_ms=train_start,
        end_ms=train_end,
        prefix=train_prefix,
    )
    evaluation = _partition(
        PartitionRole.OUT_OF_SAMPLE,
        start_ms=eval_start,
        end_ms=eval_end,
        prefix=eval_prefix,
    )
    return build_ml_walk_forward_fold(
        fold_index=index,
        training_partition=train,
        evaluation_partition=evaluation,
        training_observations=_observations(
            train,
            positive=True,
            late_outcome=late_train_outcome,
        ),
        evaluation_observations=_observations(
            evaluation,
            positive=True,
        ),
    )


def _folds():
    return (
        _fold(
            0,
            train_start=0,
            train_end=1000,
            eval_start=1000,
            eval_end=2000,
            train_prefix="fold0-train",
            eval_prefix="fold0-eval",
        ),
        _fold(
            1,
            train_start=500,
            train_end=2000,
            eval_start=2000,
            eval_end=3000,
            train_prefix="fold1-train",
            eval_prefix="fold1-eval",
        ),
    )


def test_walk_forward_is_deterministic_and_descriptive_only() -> None:
    first = run_ml_walk_forward(_features(), _folds())
    second = run_ml_walk_forward(_features(), _folds())

    assert first == second
    artifacts, results, manifest = first
    assert len(artifacts) == 2
    assert len(results) == 2
    assert manifest.semantic is (
        MLWalkForwardSemantic.DESCRIPTIVE_WALK_FORWARD_NOT_PROMOTION
    )
    assert manifest.automatic_model_selection is False
    assert manifest.aggregate_winner_selection is False
    assert manifest.calibrated_probability_claim is False
    assert manifest.untouched_forward_used is False
    assert manifest.production_authority is False
    assert manifest.real_capital == 0


def test_each_fold_refits_before_oos_evaluation() -> None:
    artifacts, results, manifest = run_ml_walk_forward(
        _features(),
        _folds(),
    )

    assert len({item[0].model_identity for item in artifacts}) == 2
    assert tuple(item.fold_identity for item in _folds()) == (
        manifest.fold_identities
    )
    assert tuple(item.result_identity for item in results) == (
        manifest.result_identities
    )
    assert all(
        item[2].partition_role is PartitionRole.OUT_OF_SAMPLE
        for item in artifacts
    )


def test_fold_requires_train_then_out_of_sample() -> None:
    train = _partition(
        PartitionRole.TRAIN,
        start_ms=0,
        end_ms=1000,
        prefix="role-train",
    )
    validation = _partition(
        PartitionRole.VALIDATION,
        start_ms=1000,
        end_ms=2000,
        prefix="role-validation",
    )
    with pytest.raises(ValueError, match="must be OUT_OF_SAMPLE"):
        build_ml_walk_forward_fold(
            fold_index=0,
            training_partition=train,
            evaluation_partition=validation,
            training_observations=_observations(train, positive=True),
            evaluation_observations=_observations(
                validation,
                positive=True,
            ),
        )


def test_fold_rejects_training_that_reaches_into_evaluation() -> None:
    train = _partition(
        PartitionRole.TRAIN,
        start_ms=0,
        end_ms=1500,
        prefix="overlap-train",
    )
    evaluation = _partition(
        PartitionRole.OUT_OF_SAMPLE,
        start_ms=1000,
        end_ms=2000,
        prefix="overlap-eval",
    )
    with pytest.raises(ValueError, match="training must end before"):
        build_ml_walk_forward_fold(
            fold_index=0,
            training_partition=train,
            evaluation_partition=evaluation,
            training_observations=_observations(train, positive=True),
            evaluation_observations=_observations(
                evaluation,
                positive=True,
            ),
        )


def test_walk_forward_requires_bounded_fold_count() -> None:
    with pytest.raises(ValueError, match="requires 2..6 folds"):
        run_ml_walk_forward(_features(), (_folds()[0],))


def test_walk_forward_indexes_must_be_contiguous() -> None:
    first, second = _folds()
    shifted = build_ml_walk_forward_fold(
        fold_index=2,
        training_partition=second.training_partition,
        evaluation_partition=second.evaluation_partition,
        training_observations=second.training_observations,
        evaluation_observations=second.evaluation_observations,
    )
    with pytest.raises(ValueError, match="contiguous from zero"):
        run_ml_walk_forward(_features(), (first, shifted))


def test_walk_forward_evaluation_windows_cannot_overlap() -> None:
    first = _folds()[0]
    second = _fold(
        1,
        train_start=400,
        train_end=1500,
        eval_start=1500,
        eval_end=2500,
        train_prefix="overlap-seq-train",
        eval_prefix="overlap-seq-eval",
    )
    with pytest.raises(ValueError, match="chronological and non-overlapping"):
        run_ml_walk_forward(_features(), (first, second))


def test_walk_forward_training_cutoff_cannot_move_backward() -> None:
    first = _fold(
        0,
        train_start=0,
        train_end=1200,
        eval_start=1200,
        eval_end=2000,
        train_prefix="cutoff0-train",
        eval_prefix="cutoff0-eval",
    )
    second = _fold(
        1,
        train_start=0,
        train_end=1000,
        eval_start=2000,
        eval_end=3000,
        train_prefix="cutoff1-train",
        eval_prefix="cutoff1-eval",
    )
    with pytest.raises(ValueError, match="cutoff must not move backward"):
        run_ml_walk_forward(_features(), (first, second))


def test_walk_forward_rejects_late_training_outcome() -> None:
    bad_first = _fold(
        0,
        train_start=0,
        train_end=1000,
        eval_start=1000,
        eval_end=2000,
        train_prefix="late-train",
        eval_prefix="late-eval",
        late_train_outcome=True,
    )
    second = _folds()[1]
    with pytest.raises(ValueError, match="available by train partition end"):
        run_ml_walk_forward(_features(), (bad_first, second))


def test_walk_forward_fold_config_identity_is_immutable() -> None:
    first, _ = _folds()
    with pytest.raises(ValueError, match="fold identity mismatch"):
        replace(first, config_identity=_sha("other-config"))


def test_walk_forward_preserves_explicit_cost_accounting_per_fold() -> None:
    artifacts, _, _ = run_ml_walk_forward(_features(), _folds())

    for _, _, evaluation in artifacts:
        if evaluation.positive_prediction_count:
            assert evaluation.gross_r_total is not None
            assert evaluation.explicit_cost_r_total is not None
            assert evaluation.net_r_total is not None
            assert (
                evaluation.gross_r_total
                - evaluation.explicit_cost_r_total
                == evaluation.net_r_total
            )


def test_walk_forward_result_identity_tampering_fails_closed() -> None:
    _, results, _ = run_ml_walk_forward(_features(), _folds())
    with pytest.raises(ValueError, match="result identity mismatch"):
        replace(results[0], fold_index=results[0].fold_index + 1)


def test_walk_forward_source_has_no_execution_or_production_write_surface() -> None:
    source = inspect.getsource(ml_walk_forward).lower()
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
    assert ml_walk_forward.REAL_CAPITAL == 0


def test_walk_forward_v1_has_no_winner_promotion_deploy_or_rl_api() -> None:
    source = inspect.getsource(ml_walk_forward).lower()
    assert "aggregate_winner_selection" in source
    assert "automatic_model_selection" in source
    assert "def select" not in source
    assert "winner_identity" not in source
    assert "def promote" not in source
    assert "champion_mutation" not in source
    assert "def deploy" not in source
    assert "reinforcement" not in source