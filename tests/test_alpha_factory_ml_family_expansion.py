from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_family_expansion
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.ml_family_expansion import (
    FIXED_FAMILY_SET,
    MLExpandedFamily,
    MLFamilyExpansionSemantic,
    MLFamilyMultipleTestingStatus,
    build_ml_family_expansion_config,
    evaluate_ml_sign_vote_model,
    fit_ml_sign_vote_model,
    run_ml_family_expansion,
)
from research.alpha_factory.ml_walk_forward import (
    build_ml_walk_forward_fold,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


DATASET_IDENTITY = _sha("ml-family-expansion-dataset-v1")


def _features():
    return (
        build_symbolic_feature(
            feature_id="regime_state",
            feature_version="regime-v1",
            allowed_values=("risk_off", "risk_on"),
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
        gross = Decimal("0.8") if trend == "rising" else Decimal("-0.2")
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


def _reference_artifacts():
    folds = _folds()
    artifacts, _, _ = run_ml_walk_forward(_features(), folds)
    return folds, artifacts


def test_family_expansion_is_deterministic_and_bounded_to_two_families() -> None:
    folds, references = _reference_artifacts()
    first = run_ml_family_expansion(_features(), folds, references)
    second = run_ml_family_expansion(_features(), folds, references)

    assert first == second
    challengers, comparisons, manifest = first
    assert len(challengers) == len(folds)
    assert len(comparisons) == len(folds)
    assert manifest.family_set == FIXED_FAMILY_SET
    assert manifest.semantic is (
        MLFamilyExpansionSemantic.DESCRIPTIVE_MULTI_FAMILY_NOT_SELECTION
    )
    assert manifest.multiple_testing_status is (
        MLFamilyMultipleTestingStatus
        .BOUNDED_TWO_FAMILIES_NO_AUTOMATIC_SELECTION
    )
    assert manifest.automatic_family_selection is False
    assert manifest.automatic_hyperparameter_selection is False
    assert manifest.aggregate_winner_selection is False
    assert manifest.calibrated_probability_claim is False
    assert manifest.untouched_forward_used is False
    assert manifest.production_authority is False
    assert manifest.real_capital == 0


def test_sign_vote_challenger_is_train_only_and_oos_descriptive() -> None:
    folds, references = _reference_artifacts()
    challengers, _, _ = run_ml_family_expansion(
        _features(),
        folds,
        references,
    )

    for fold, (model, training, evaluation) in zip(
        folds,
        challengers,
        strict=True,
    ):
        assert model.family is MLExpandedFamily.CATEGORICAL_SIGN_VOTE
        assert model.training_partition_identity == (
            fold.training_partition.partition_identity
        )
        assert training.validation_used_in_fit is False
        assert training.out_of_sample_used_in_fit is False
        assert training.untouched_forward_used is False
        assert evaluation.partition_role is PartitionRole.OUT_OF_SAMPLE
        assert evaluation.family is MLExpandedFamily.CATEGORICAL_SIGN_VOTE


def test_reference_family_is_rebound_exactly_not_refit_or_replaced() -> None:
    folds, references = _reference_artifacts()
    _, comparisons, _ = run_ml_family_expansion(
        _features(),
        folds,
        references,
    )

    for reference, comparison in zip(references, comparisons, strict=True):
        assert comparison.reference_family is (
            MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE
        )
        assert comparison.reference_model_identity == reference[0].model_identity
        assert comparison.reference_evaluation_identity == (
            reference[2].evaluation_identity
        )
        assert comparison.challenger_family is (
            MLExpandedFamily.CATEGORICAL_SIGN_VOTE
        )
        assert comparison.automatic_winner_selection is False


def test_sign_vote_evaluation_preserves_explicit_cost_accounting() -> None:
    folds, _ = _reference_artifacts()
    config = build_ml_family_expansion_config()
    for fold in folds:
        model, _ = fit_ml_sign_vote_model(
            _features(),
            fold.training_partition,
            fold.training_observations,
            config=config,
        )
        _, evaluation = evaluate_ml_sign_vote_model(
            model,
            fold.evaluation_partition,
            fold.evaluation_observations,
            _features(),
        )
        if evaluation.positive_prediction_count:
            assert evaluation.gross_r_total is not None
            assert evaluation.explicit_cost_r_total is not None
            assert evaluation.net_r_total is not None
            assert (
                evaluation.gross_r_total - evaluation.explicit_cost_r_total
                == evaluation.net_r_total
            )


def test_family_config_is_fixed_and_fail_closed() -> None:
    config = build_ml_family_expansion_config()
    assert config.family_set == FIXED_FAMILY_SET
    assert config.automatic_family_selection is False
    assert config.automatic_hyperparameter_selection is False
    assert config.uncontrolled_model_search is False

    with pytest.raises(ValueError, match="family set is fixed"):
        replace(
            config,
            family_set=(MLExpandedFamily.CATEGORICAL_SIGN_VOTE,),
        )
    with pytest.raises(ValueError, match="automatic family selection"):
        replace(config, automatic_family_selection=True)


def test_family_expansion_requires_exact_reference_evaluation() -> None:
    folds, references = _reference_artifacts()
    bad_references = (
        (references[0][0], references[0][1], references[1][2]),
        references[1],
    )
    with pytest.raises(ValueError):
        run_ml_family_expansion(_features(), folds, bad_references)


def test_family_comparison_identity_tampering_fails_closed() -> None:
    folds, references = _reference_artifacts()
    _, comparisons, _ = run_ml_family_expansion(
        _features(),
        folds,
        references,
    )
    with pytest.raises(ValueError, match="comparison identity mismatch"):
        replace(comparisons[0], fold_index=comparisons[0].fold_index + 1)


def test_family_source_has_no_execution_or_production_write_surface() -> None:
    source = inspect.getsource(ml_family_expansion).lower()
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
    assert ml_family_expansion.REAL_CAPITAL == 0


def test_family_v1_has_no_winner_promotion_deploy_or_rl_api() -> None:
    source = inspect.getsource(ml_family_expansion).lower()
    assert "aggregate_winner_selection" in source
    assert "automatic_family_selection" in source
    assert "automatic_hyperparameter_selection" in source
    assert "def select" not in source
    assert "winner_identity" not in source
    assert "def promote" not in source
    assert "champion_mutation" not in source
    assert "def deploy" not in source
    assert "reinforcement" not in source
