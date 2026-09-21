from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from research.alpha_factory import ml_family_untouched_forward
from research.alpha_factory.clustering_regime import (
    build_cluster_feature_reading,
    build_cluster_research_observation,
)
from research.alpha_factory.foundation import (
    PartitionRole,
    build_research_partition,
)
from research.alpha_factory.ml_family_cost_stress import (
    run_ml_family_cost_stress,
)
from research.alpha_factory.ml_family_expansion import (
    MLExpandedFamily,
    run_ml_family_expansion,
)
from research.alpha_factory.ml_family_robustness_ablation import (
    run_ml_family_robustness_ablation,
)
from research.alpha_factory.ml_family_untouched_forward import (
    MLFrozenModelPolicy,
    MLUntouchedForwardSemantic,
    MLUntouchedForwardStatus,
    build_ml_untouched_forward_config,
    run_ml_family_untouched_forward_paper,
)
from research.alpha_factory.ml_walk_forward import (
    build_ml_walk_forward_fold,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import build_symbolic_feature


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


DATASET_IDENTITY = _sha("ml-family-untouched-forward-dataset-v1")


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
    all_falling: bool = False,
):
    features = _features()
    by_id = {item.feature_id: item for item in features}
    if all_falling:
        values = (
            ("risk_off", "falling", "expanded"),
            ("risk_on", "falling", "normal"),
            ("transition", "falling", "expanded"),
            ("risk_off", "falling", "normal"),
        )
    else:
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


def _accepted_chain():
    folds = (
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
    references, _, _ = run_ml_walk_forward(_features(), folds)
    expansion = run_ml_family_expansion(_features(), folds, references)
    cost_stress = run_ml_family_cost_stress(
        _features(),
        folds,
        references,
        expansion,
    )
    robustness = run_ml_family_robustness_ablation(
        _features(),
        folds,
        references,
        expansion,
        cost_stress,
        regime_feature_id="regime_state",
    )
    return folds, references, expansion, cost_stress, robustness


def _forward_partition():
    return _partition(
        PartitionRole.UNTOUCHED_FORWARD,
        start_ms=3000,
        end_ms=4000,
        prefix="forward",
    )


def test_untouched_forward_is_deterministic_and_uses_frozen_latest_fold() -> None:
    folds, references, expansion, cost_stress, robustness = _accepted_chain()
    forward = _forward_partition()
    observations = _observations(forward)

    first = run_ml_family_untouched_forward_paper(
        _features(),
        folds,
        references,
        expansion,
        cost_stress,
        robustness,
        forward,
        observations,
        regime_feature_id="regime_state",
    )
    second = run_ml_family_untouched_forward_paper(
        _features(),
        folds,
        references,
        expansion,
        cost_stress,
        robustness,
        forward,
        observations,
        regime_feature_id="regime_state",
    )

    assert first == second
    (
        reference_predictions,
        challenger_predictions,
        reference_evaluation,
        challenger_evaluation,
        snapshot,
        manifest,
    ) = first

    assert snapshot.freeze_policy is (
        MLFrozenModelPolicy.LATEST_ACCEPTED_WALK_FORWARD_FOLD
    )
    assert snapshot.source_fold_identity == folds[-1].fold_identity
    assert snapshot.source_fold_index == folds[-1].fold_index
    assert snapshot.reference_model_identity == references[-1][0].model_identity
    assert snapshot.challenger_model_identity == expansion[0][-1][0].model_identity
    assert snapshot.model_refit_performed is False
    assert snapshot.family_selection_performed is False

    assert len(reference_predictions) == forward.row_count
    assert len(challenger_predictions) == forward.row_count
    assert reference_evaluation.partition_identity == forward.partition_identity
    assert challenger_evaluation.partition_identity == forward.partition_identity
    assert manifest.semantic is (
        MLUntouchedForwardSemantic.DESCRIPTIVE_FORWARD_PAPER_NOT_SELECTION
    )
    assert manifest.automatic_family_selection is False
    assert manifest.aggregate_winner_selection is False
    assert manifest.retrospective_optimization_performed is False
    assert manifest.model_refit_performed is False
    assert manifest.feature_change_performed is False
    assert manifest.calibrated_probability_claim is False
    assert manifest.untouched_forward_used is True
    assert manifest.production_authority is False
    assert manifest.real_capital == 0


def test_forward_evidence_preserves_both_families_and_explicit_costs() -> None:
    folds, references, expansion, cost_stress, robustness = _accepted_chain()
    forward = _forward_partition()
    observations = _observations(forward)
    result = run_ml_family_untouched_forward_paper(
        _features(),
        folds,
        references,
        expansion,
        cost_stress,
        robustness,
        forward,
        observations,
        regime_feature_id="regime_state",
    )
    reference_eval, challenger_eval = result[2], result[3]

    assert reference_eval.family is MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE
    assert challenger_eval.family is MLExpandedFamily.CATEGORICAL_SIGN_VOTE
    for evaluation in (reference_eval, challenger_eval):
        assert evaluation.status in {
            MLUntouchedForwardStatus.OBSERVED,
            MLUntouchedForwardStatus.OBSERVED_NO_SELECTION,
        }
        assert evaluation.model_refit_performed is False
        assert evaluation.feature_change_performed is False
        assert evaluation.threshold_change_performed is False
        if evaluation.positive_prediction_count:
            assert evaluation.gross_r_total is not None
            assert evaluation.explicit_cost_r_total is not None
            assert evaluation.net_r_total is not None
            assert evaluation.net_r_total == (
                evaluation.gross_r_total
                - evaluation.explicit_cost_r_total
            )


def test_forward_partition_must_start_after_last_oos_window() -> None:
    folds, references, expansion, cost_stress, robustness = _accepted_chain()
    overlapping = _partition(
        PartitionRole.UNTOUCHED_FORWARD,
        start_ms=2500,
        end_ms=3500,
        prefix="overlap-forward",
    )
    with pytest.raises(
        ValueError,
        match="after accepted OOS evidence closes",
    ):
        run_ml_family_untouched_forward_paper(
            _features(),
            folds,
            references,
            expansion,
            cost_stress,
            robustness,
            overlapping,
            _observations(overlapping),
            regime_feature_id="regime_state",
        )


def test_forward_requires_exact_accepted_robustness_evidence() -> None:
    folds, references, expansion, cost_stress, robustness = _accepted_chain()
    forward = _forward_partition()
    bad_robustness = (
        robustness[0],
        robustness[1],
        tuple(reversed(robustness[2])),
        robustness[3],
        robustness[4],
    )
    with pytest.raises(
        ValueError,
        match="exact accepted family robustness evidence",
    ):
        run_ml_family_untouched_forward_paper(
            _features(),
            folds,
            references,
            expansion,
            cost_stress,
            bad_robustness,
            forward,
            _observations(forward),
            regime_feature_id="regime_state",
        )


def test_forward_rejects_incomplete_outcome_availability() -> None:
    folds, references, expansion, cost_stress, robustness = _accepted_chain()
    forward = _forward_partition()
    observations = list(_observations(forward))
    original = observations[-1]
    observations[-1] = build_cluster_research_observation(
        partition_identity=original.partition_identity,
        source_evidence_identity=original.source_evidence_identity,
        decision_as_of_ms=original.decision_as_of_ms,
        outcome_available_at_ms=forward.end_ms + 1,
        feature_readings=original.feature_readings,
        gross_outcome_r=original.gross_outcome_r,
        explicit_cost_r=original.explicit_cost_r,
    )
    with pytest.raises(ValueError, match="not yet evaluable"):
        run_ml_family_untouched_forward_paper(
            _features(),
            folds,
            references,
            expansion,
            cost_stress,
            robustness,
            forward,
            tuple(observations),
            regime_feature_id="regime_state",
        )


def test_foundation_rejects_future_feature_evidence_before_forward_run() -> None:
    forward = _forward_partition()
    first = _observations(forward)[0]
    regime = _features()[0]
    late = build_cluster_feature_reading(
        feature=regime,
        value="risk_off",
        available_at_ms=first.decision_as_of_ms + 1,
    )
    readings = (late,) + first.feature_readings[1:]
    with pytest.raises(
        ValueError,
        match="feature evidence is unavailable at decision as-of",
    ):
        build_cluster_research_observation(
            partition_identity=first.partition_identity,
            source_evidence_identity=first.source_evidence_identity,
            decision_as_of_ms=first.decision_as_of_ms,
            outcome_available_at_ms=first.outcome_available_at_ms,
            feature_readings=readings,
            gross_outcome_r=first.gross_outcome_r,
            explicit_cost_r=first.explicit_cost_r,
        )


def test_forward_config_and_manifest_fail_closed_on_selection_or_refit() -> None:
    config = build_ml_untouched_forward_config()
    assert config.automatic_family_selection is False
    assert config.automatic_threshold_selection is False
    assert config.feature_change_allowed is False
    assert config.model_refit_allowed is False
    assert config.retrospective_optimization_allowed is False

    with pytest.raises(ValueError, match="cannot select, refit or optimize"):
        replace(config, model_refit_allowed=True)

    folds, references, expansion, cost_stress, robustness = _accepted_chain()
    forward = _forward_partition()
    result = run_ml_family_untouched_forward_paper(
        _features(),
        folds,
        references,
        expansion,
        cost_stress,
        robustness,
        forward,
        _observations(forward),
        regime_feature_id="regime_state",
    )
    with pytest.raises(ValueError, match="cannot select, optimize"):
        replace(result[-1], aggregate_winner_selection=True)


def test_forward_source_has_no_fit_execution_or_production_surface() -> None:
    source = inspect.getsource(ml_family_untouched_forward).lower()
    forbidden = (
        "fit_ml_baseline",
        "fit_ml_sign_vote_model",
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
    assert ml_family_untouched_forward.REAL_CAPITAL == 0


def test_forward_v1_has_no_winner_promotion_deploy_or_rl_api() -> None:
    source = inspect.getsource(ml_family_untouched_forward).lower()
    assert "aggregate_winner_selection" in source
    assert "automatic_family_selection" in source
    assert "retrospective_optimization" in source
    assert "def select" not in source
    assert "winner_identity" not in source
    assert "def promote" not in source
    assert "champion_mutation" not in source
    assert "def deploy" not in source
    assert "reinforcement" not in source
