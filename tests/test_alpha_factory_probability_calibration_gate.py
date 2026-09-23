from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass
from research.alpha_factory import probability_calibration_gate
from research.alpha_factory.foundation import PartitionRole, build_research_partition
from research.alpha_factory.probability_calibration_gate import (
    CalibrationGateStatus,
    R19ProbabilityStatus,
    authorize_calibrated_probability,
    build_calibration_scope,
    build_frozen_probability_prediction,
    build_probability_calibration_config,
    build_untouched_probability_observation,
    evaluate_probability_calibration,
)

WINDOW_START = 10_000
WINDOW_END = 20_000
EVALUATION_CUTOFF = 21_000
HORIZON_MS = 1_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _scope():
    return build_calibration_scope(
        asset="BTCUSDT",
        timeframe="4h",
        regime="trend_up",
        outcome_event_definition=(
            "frozen bullish forecast reaches target before invalidation within horizon"
        ),
        horizon_ms=HORIZON_MS,
    )


def _config(
    *,
    minimum_holdout_n: int = 8,
    minimum_holdout_class_n: int = 2,
    minimum_reliability_bin_n: int = 2,
    minimum_brier_skill: str = "0.10",
    maximum_expected_calibration_error: str = "0.21",
):
    return build_probability_calibration_config(
        policy_version="r19-gate-policy-v1/1",
        scope=_scope(),
        model_version="m6-probability-model-v1/1",
        calibrator_version="isotonic-shadow-v1/1",
        walk_forward_fit_identity=_sha("walk-forward-fit"),
        created_at_ms=WINDOW_START - 100,
        training_cutoff_ms=WINDOW_START - 200,
        training_sample_count=100,
        training_positive_count=50,
        decision_window_start_ms=WINDOW_START,
        decision_window_end_ms=WINDOW_END,
        evaluation_cutoff_ms=EVALUATION_CUTOFF,
        probability_bin_edges=(Decimal(0), Decimal("0.50"), Decimal(1)),
        minimum_training_n=60,
        minimum_training_class_n=10,
        minimum_holdout_n=minimum_holdout_n,
        minimum_holdout_class_n=minimum_holdout_class_n,
        minimum_reliability_bin_n=minimum_reliability_bin_n,
        minimum_brier_skill=Decimal(minimum_brier_skill),
        maximum_expected_calibration_error=Decimal(
            maximum_expected_calibration_error
        ),
    )


def _predictions(
    config,
    *,
    low_probability: str = "0.20",
    high_probability: str = "0.80",
    count: int = 8,
):
    values = []
    for index in range(count):
        probability = low_probability if index < count // 2 else high_probability
        values.append(
            build_frozen_probability_prediction(
                config,
                source_forecast_identity=_sha(f"forecast-{index}"),
                issued_at_ms=11_000 + index * 1_000,
                predicted_probability_0_1=Decimal(probability),
            )
        )
    return tuple(values)


def _partition(predictions, *, role: PartitionRole = PartitionRole.UNTOUCHED_FORWARD):
    return build_research_partition(
        dataset_identity=_sha("r19-untouched-forward-dataset"),
        role=role,
        start_ms=WINDOW_START,
        end_ms=WINDOW_END,
        row_count=len(predictions),
        evidence_identities=tuple(
            sorted(item.prediction_identity for item in predictions)
        ),
    )


def _observations(
    predictions,
    *,
    reverse: bool = False,
    all_positive: bool = False,
):
    rows = []
    midpoint = len(predictions) // 2
    for index, prediction in enumerate(predictions):
        if all_positive:
            positive = True
        else:
            positive = index >= midpoint
            if reverse:
                positive = not positive
        rows.append(
            build_untouched_probability_observation(
                prediction,
                source_outcome_identity=_sha(f"outcome-{index}"),
                outcome_available_at_ms=prediction.issued_at_ms + 500,
                observed_positive=positive,
            )
        )
    return tuple(rows)


def test_scope_and_config_freeze_exact_r19_context_before_holdout() -> None:
    scope = _scope()
    config = _config()

    assert scope.asset == "BTCUSDT"
    assert scope.timeframe == "4h"
    assert scope.regime == "trend_up"
    assert scope.horizon_ms == HORIZON_MS
    assert "target before invalidation" in scope.outcome_event_definition
    assert config.created_at_ms < config.decision_window_start_ms
    assert config.training_cutoff_ms < config.decision_window_start_ms
    assert config.training_sample_count == 100
    assert config.training_positive_count == 50
    assert config.training_base_rate == Decimal("0.5")
    assert config.walk_forward_fit_identity == _sha("walk-forward-fit")
    assert config.production_authority is False
    assert config.real_capital == 0


def test_training_support_thresholds_fail_before_probability_evaluation() -> None:
    with pytest.raises(ValueError, match="training sample support is below minimum"):
        build_probability_calibration_config(
            policy_version="r19-gate-policy-v1/1",
            scope=_scope(),
            model_version="m6-probability-model-v1/1",
            calibrator_version="isotonic-shadow-v1/1",
            walk_forward_fit_identity=_sha("walk-forward-fit"),
            created_at_ms=WINDOW_START - 100,
            training_cutoff_ms=WINDOW_START - 200,
            training_sample_count=20,
            training_positive_count=10,
            decision_window_start_ms=WINDOW_START,
            decision_window_end_ms=WINDOW_END,
            evaluation_cutoff_ms=EVALUATION_CUTOFF,
            probability_bin_edges=(Decimal(0), Decimal("0.50"), Decimal(1)),
            minimum_training_n=60,
            minimum_training_class_n=5,
            minimum_holdout_n=8,
            minimum_holdout_class_n=2,
            minimum_reliability_bin_n=2,
            minimum_brier_skill=Decimal("0.10"),
            maximum_expected_calibration_error=Decimal("0.21"),
        )

    with pytest.raises(ValueError, match="training class support is below minimum"):
        build_probability_calibration_config(
            policy_version="r19-gate-policy-v1/1",
            scope=_scope(),
            model_version="m6-probability-model-v1/1",
            calibrator_version="isotonic-shadow-v1/1",
            walk_forward_fit_identity=_sha("walk-forward-fit"),
            created_at_ms=WINDOW_START - 100,
            training_cutoff_ms=WINDOW_START - 200,
            training_sample_count=100,
            training_positive_count=2,
            decision_window_start_ms=WINDOW_START,
            decision_window_end_ms=WINDOW_END,
            evaluation_cutoff_ms=EVALUATION_CUTOFF,
            probability_bin_edges=(Decimal(0), Decimal("0.50"), Decimal(1)),
            minimum_training_n=60,
            minimum_training_class_n=10,
            minimum_holdout_n=8,
            minimum_holdout_class_n=2,
            minimum_reliability_bin_n=2,
            minimum_brier_skill=Decimal("0.10"),
            maximum_expected_calibration_error=Decimal("0.21"),
        )


def test_untouched_forward_gate_accepts_well_calibrated_predictions() -> None:
    config = _config()
    predictions = _predictions(config)
    partition = _partition(predictions)
    observations = _observations(predictions)

    report = evaluate_probability_calibration(
        config,
        partition,
        observations,
        as_of_ms=EVALUATION_CUTOFF,
    )

    assert report.status is CalibrationGateStatus.ACCEPTED
    assert report.probability_status is R19ProbabilityStatus.CALIBRATED
    assert report.training_sample_count == 100
    assert report.training_positive_count == 50
    assert report.training_negative_count == 50
    assert report.holdout_sample_count == 8
    assert report.holdout_positive_count == 4
    assert report.holdout_negative_count == 4
    assert report.brier_score == Decimal("0.04")
    assert report.baseline_brier_score == Decimal("0.25")
    assert report.brier_skill_score == Decimal("0.84")
    assert report.expected_calibration_error == Decimal("0.20")
    assert report.maximum_calibration_error == Decimal("0.20")
    assert len(report.reliability_bins) == 2
    assert {item.sample_count for item in report.reliability_bins} == {4}
    assert report.automatic_promotion is False
    assert report.production_authority is False
    assert report.real_capital == 0


def test_gate_is_permutation_invariant_but_partition_is_prediction_bound() -> None:
    config = _config()
    predictions = _predictions(config)
    partition = _partition(predictions)
    observations = _observations(predictions)

    first = evaluate_probability_calibration(
        config,
        partition,
        observations,
        as_of_ms=EVALUATION_CUTOFF,
    )
    second = evaluate_probability_calibration(
        config,
        partition,
        tuple(reversed(observations)),
        as_of_ms=EVALUATION_CUTOFF,
    )
    assert first == second

    wrong_partition = build_research_partition(
        dataset_identity=_sha("r19-untouched-forward-dataset"),
        role=PartitionRole.UNTOUCHED_FORWARD,
        start_ms=WINDOW_START,
        end_ms=WINDOW_END,
        row_count=len(predictions),
        evidence_identities=tuple(
            sorted(
                (
                    *(item.prediction_identity for item in predictions[:-1]),
                    _sha("future-outcome-selected-membership"),
                )
            )
        ),
    )
    with pytest.raises(ValueError, match="predictions do not match partition evidence"):
        evaluate_probability_calibration(
            config,
            wrong_partition,
            observations,
            as_of_ms=EVALUATION_CUTOFF,
        )


def test_prediction_identity_is_frozen_before_outcome_and_cannot_be_rewritten() -> None:
    config = _config()
    prediction = _predictions(config)[0]
    observation = build_untouched_probability_observation(
        prediction,
        source_outcome_identity=_sha("outcome-frozen"),
        outcome_available_at_ms=prediction.issued_at_ms + 500,
        observed_positive=False,
    )

    assert observation.source_prediction_identity == prediction.prediction_identity
    assert observation.predicted_probability_0_1 == prediction.predicted_probability_0_1
    assert prediction.issued_at_ms < observation.outcome_available_at_ms

    with pytest.raises(ValueError, match="source prediction identity mismatch"):
        replace(
            observation,
            predicted_probability_0_1=Decimal("0.33"),
        )


def test_reversed_predictions_fail_brier_skill_and_remain_not_calibrated() -> None:
    config = _config()
    predictions = _predictions(config)
    report = evaluate_probability_calibration(
        config,
        _partition(predictions),
        _observations(predictions, reverse=True),
        as_of_ms=EVALUATION_CUTOFF,
    )

    assert report.status is CalibrationGateStatus.FAILED_BRIER_SKILL
    assert report.probability_status is R19ProbabilityStatus.NOT_CALIBRATED
    assert report.brier_skill_score is not None
    assert report.brier_skill_score < 0


def test_calibration_error_gate_can_reject_otherwise_positive_brier_skill() -> None:
    config = _config(maximum_expected_calibration_error="0.30")
    predictions = _predictions(
        config,
        low_probability="0.40",
        high_probability="0.60",
    )
    report = evaluate_probability_calibration(
        config,
        _partition(predictions),
        _observations(predictions),
        as_of_ms=EVALUATION_CUTOFF,
    )

    assert report.brier_score == Decimal("0.16")
    assert report.brier_skill_score == Decimal("0.36")
    assert report.expected_calibration_error == Decimal("0.40")
    assert report.status is CalibrationGateStatus.FAILED_CALIBRATION_ERROR
    assert report.probability_status is R19ProbabilityStatus.NOT_CALIBRATED


def test_sample_class_and_bin_support_fail_closed() -> None:
    low_sample_config = _config(minimum_holdout_n=9)
    low_sample_predictions = _predictions(low_sample_config)
    low_sample_report = evaluate_probability_calibration(
        low_sample_config,
        _partition(low_sample_predictions),
        _observations(low_sample_predictions),
        as_of_ms=EVALUATION_CUTOFF,
    )
    assert low_sample_report.status is CalibrationGateStatus.INSUFFICIENT_SAMPLE

    class_config = _config()
    class_predictions = _predictions(class_config)
    class_report = evaluate_probability_calibration(
        class_config,
        _partition(class_predictions),
        _observations(class_predictions, all_positive=True),
        as_of_ms=EVALUATION_CUTOFF,
    )
    assert class_report.status is CalibrationGateStatus.INSUFFICIENT_CLASS_SUPPORT

    bin_config = _config(minimum_reliability_bin_n=5)
    bin_predictions = _predictions(bin_config)
    bin_report = evaluate_probability_calibration(
        bin_config,
        _partition(bin_predictions),
        _observations(bin_predictions),
        as_of_ms=EVALUATION_CUTOFF,
    )
    assert bin_report.status is CalibrationGateStatus.INSUFFICIENT_BIN_SUPPORT

    assert all(
        item.probability_status is R19ProbabilityStatus.NOT_CALIBRATED
        for item in (low_sample_report, class_report, bin_report)
    )


def test_maturity_and_missing_evidence_are_explicit() -> None:
    config = _config()
    predictions = _predictions(config)
    partition = _partition(predictions)

    early = evaluate_probability_calibration(
        config,
        partition,
        _observations(predictions),
        as_of_ms=EVALUATION_CUTOFF - 1,
    )
    assert early.status is CalibrationGateStatus.NOT_YET_EVALUABLE
    assert early.probability_status is R19ProbabilityStatus.NOT_CALIBRATED
    assert early.holdout_sample_count == 0

    missing = evaluate_probability_calibration(
        config,
        partition,
        (),
        as_of_ms=EVALUATION_CUTOFF,
    )
    assert missing.status is CalibrationGateStatus.NO_EVIDENCE
    assert missing.probability_status is R19ProbabilityStatus.NOT_CALIBRATED


def test_only_live_untouched_forward_evidence_is_admissible() -> None:
    config = _config()
    prediction = _predictions(config)[0]
    observation = build_untouched_probability_observation(
        prediction,
        source_outcome_identity=_sha("retrospective-outcome"),
        outcome_available_at_ms=prediction.issued_at_ms + 500,
        observed_positive=False,
    )

    with pytest.raises(ValueError, match="LIVE_UNTOUCHED_FORWARD only"):
        replace(observation, evidence_class=EvidenceClass.RETROSPECTIVE)


def test_holdout_outcome_must_obey_frozen_horizon_and_evaluation_cutoff() -> None:
    config = _config()
    predictions = _predictions(config)
    observations = list(_observations(predictions))

    observations[0] = build_untouched_probability_observation(
        predictions[0],
        source_outcome_identity=_sha("late-horizon-outcome"),
        outcome_available_at_ms=predictions[0].issued_at_ms + HORIZON_MS + 1,
        observed_positive=False,
    )
    with pytest.raises(ValueError, match="exceeds frozen horizon"):
        evaluate_probability_calibration(
            config,
            _partition(predictions),
            tuple(observations),
            as_of_ms=EVALUATION_CUTOFF,
        )


def test_probability_authorization_requires_accepted_gate_and_exact_frozen_prediction() -> None:
    config = _config()
    predictions = _predictions(config)
    accepted = evaluate_probability_calibration(
        config,
        _partition(predictions),
        _observations(predictions),
        as_of_ms=EVALUATION_CUTOFF,
    )
    future_prediction = build_frozen_probability_prediction(
        config,
        source_forecast_identity=_sha("post-acceptance-forecast"),
        issued_at_ms=EVALUATION_CUTOFF + 1_000,
        predicted_probability_0_1=Decimal("0.73"),
    )

    authorization = authorize_calibrated_probability(
        accepted,
        future_prediction,
    )
    assert authorization is not None
    assert authorization.probability_status is R19ProbabilityStatus.CALIBRATED
    assert authorization.probability_0_1 == Decimal("0.73")
    assert (
        authorization.source_prediction_identity
        == future_prediction.prediction_identity
    )
    assert authorization.calibration_evidence_identity == accepted.evidence_identity
    assert authorization.production_authority is False
    assert authorization.real_capital == 0

    failed_report = evaluate_probability_calibration(
        config,
        _partition(predictions),
        _observations(predictions, reverse=True),
        as_of_ms=EVALUATION_CUTOFF,
    )
    assert failed_report.status is CalibrationGateStatus.FAILED_BRIER_SKILL
    assert authorize_calibrated_probability(
        failed_report,
        future_prediction,
    ) is None


def test_future_authorization_cannot_change_frozen_numeric_prediction() -> None:
    config = _config()
    predictions = _predictions(config)
    report = evaluate_probability_calibration(
        config,
        _partition(predictions),
        _observations(predictions),
        as_of_ms=EVALUATION_CUTOFF,
    )
    future_prediction = build_frozen_probability_prediction(
        config,
        source_forecast_identity=_sha("numeric-truth-forecast"),
        issued_at_ms=EVALUATION_CUTOFF + 2_000,
        predicted_probability_0_1=Decimal("0.67"),
    )
    authorization = authorize_calibrated_probability(report, future_prediction)
    assert authorization is not None

    with pytest.raises(
        ValueError,
        match="authorization source prediction identity mismatch",
    ):
        replace(authorization, probability_0_1=Decimal("0.99"))


def test_config_prediction_report_and_authorization_identity_tampering_fail_closed() -> None:
    config = _config()
    prediction = _predictions(config)[0]
    predictions = _predictions(config)
    report = evaluate_probability_calibration(
        config,
        _partition(predictions),
        _observations(predictions),
        as_of_ms=EVALUATION_CUTOFF,
    )

    with pytest.raises(ValueError, match="config identity mismatch"):
        replace(config, training_sample_count=101)
    with pytest.raises(ValueError, match="frozen prediction identity mismatch"):
        replace(prediction, issued_at_ms=prediction.issued_at_ms + 1)
    with pytest.raises(ValueError, match="calibration evidence identity mismatch"):
        replace(report, brier_score=Decimal("0.05"))


def test_r19_gate_has_no_execution_or_self_promotion_surface() -> None:
    source = inspect.getsource(probability_calibration_gate).lower()
    forbidden = (
        "crypto_signal.paper",
        "crypto_signal.signals",
        "import httpx",
        "import requests",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "launchctl",
        "subprocess",
        "def promote",
        "def deploy",
    )
    assert all(token not in source for token in forbidden)
    assert probability_calibration_gate.REAL_CAPITAL == 0
