from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import ClusterResearchObservation
from research.alpha_factory.ml_baseline import (
    MLBaselineModel,
    MLEvaluation,
    MLPrediction,
    evaluate_ml_baseline,
)
from research.alpha_factory.ml_walk_forward import MLWalkForwardFold
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_COST_STRESS_ENGINE_VERSION = "alpha-factory-ml-cost-stress-v1/1"
ML_COST_STRESS_SCHEMA_VERSION = "alpha-factory-ml-cost-stress-schema-v1/1"
DEFAULT_COST_MULTIPLIERS = (
    Decimal("1.0"),
    Decimal("1.5"),
    Decimal("2.0"),
)
REAL_CAPITAL = 0


class MLCostStressSemantic(StrEnum):
    DESCRIPTIVE_COST_STRESS_NOT_SELECTION = (
        "descriptive_cost_stress_not_selection"
    )


@dataclass(frozen=True, slots=True)
class MLCostStressConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    multipliers: tuple[Decimal, ...]
    automatic_scenario_selection: bool = False
    model_refit_allowed: bool = False
    prediction_change_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "cost-stress config identity")
        if self.schema_version != ML_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported cost-stress config schema")
        if self.engine_version != ML_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported cost-stress config engine")
        if self.multipliers != DEFAULT_COST_MULTIPLIERS:
            raise ValueError("cost-stress v1 multiplier grid is fixed")
        if any(item < Decimal(1) for item in self.multipliers):
            raise ValueError("cost-stress multipliers cannot reduce costs")
        if self.automatic_scenario_selection:
            raise ValueError("automatic stress scenario selection is closed")
        if self.model_refit_allowed:
            raise ValueError("cost stress cannot refit models")
        if self.prediction_change_allowed:
            raise ValueError("cost stress cannot change predictions")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("cost-stress config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLCostStressScenario:
    scenario_identity: str
    schema_version: str
    engine_version: str
    config_identity: str
    evaluation_identity: str
    model_identity: str
    multiplier: Decimal
    selected_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    original_cost_r_total: Decimal | None
    stressed_cost_r_total: Decimal | None
    original_net_r_total: Decimal | None
    stressed_net_r_total: Decimal | None
    prediction_set_changed: bool = False
    model_refit_performed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.scenario_identity, "cost-stress scenario identity")
        _require_sha256(self.config_identity, "cost-stress config identity")
        _require_sha256(self.evaluation_identity, "cost-stress evaluation identity")
        _require_sha256(self.model_identity, "cost-stress model identity")
        if self.schema_version != ML_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported cost-stress scenario schema")
        if self.engine_version != ML_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported cost-stress scenario engine")
        if self.multiplier not in DEFAULT_COST_MULTIPLIERS:
            raise ValueError("cost-stress scenario multiplier is outside grid")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "cost-stress selected observation identities must be "
                "sorted and unique"
            )
        if self.prediction_set_changed:
            raise ValueError("cost stress cannot change prediction set")
        if self.model_refit_performed:
            raise ValueError("cost stress cannot refit model")

        metrics = (
            self.gross_r_total,
            self.original_cost_r_total,
            self.stressed_cost_r_total,
            self.original_net_r_total,
            self.stressed_net_r_total,
        )
        if not self.selected_observation_identities:
            if any(value is not None for value in metrics):
                raise ValueError(
                    "empty cost-stress selection must not fabricate R metrics"
                )
        else:
            if any(value is None for value in metrics):
                raise ValueError(
                    "cost-stress selection requires complete R metrics"
                )
            assert self.original_cost_r_total is not None
            assert self.stressed_cost_r_total is not None
            assert self.gross_r_total is not None
            assert self.original_net_r_total is not None
            assert self.stressed_net_r_total is not None
            if self.original_cost_r_total < 0:
                raise ValueError("original cost cannot be negative")
            if self.stressed_cost_r_total != (
                self.original_cost_r_total * self.multiplier
            ):
                raise ValueError("stressed cost calculation mismatch")
            if self.original_net_r_total != (
                self.gross_r_total - self.original_cost_r_total
            ):
                raise ValueError("original net-R calculation mismatch")
            if self.stressed_net_r_total != (
                self.gross_r_total - self.stressed_cost_r_total
            ):
                raise ValueError("stressed net-R calculation mismatch")
            if self.stressed_cost_r_total < self.original_cost_r_total:
                raise ValueError("cost stress cannot improve cost")
        if self.scenario_identity != canonical_sha256(
            _scenario_payload(self)
        ):
            raise ValueError("cost-stress scenario identity mismatch")


@dataclass(frozen=True, slots=True)
class MLCostStressFoldResult:
    fold_result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    prediction_identities: tuple[str, ...]
    scenario_identities: tuple[str, ...]
    automatic_scenario_selection: bool = False
    model_refit_performed: bool = False
    prediction_set_changed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(
            self.fold_result_identity,
            "cost-stress fold result identity",
        )
        _require_sha256(self.fold_identity, "cost-stress fold identity")
        _require_sha256(self.model_identity, "cost-stress model identity")
        _require_sha256(
            self.evaluation_identity,
            "cost-stress evaluation identity",
        )
        if self.schema_version != ML_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported cost-stress fold schema")
        if self.engine_version != ML_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported cost-stress fold engine")
        if self.fold_index < 0:
            raise ValueError("cost-stress fold index must be non-negative")
        if not self.prediction_identities:
            raise ValueError("cost-stress fold requires predictions")
        if tuple(sorted(set(self.prediction_identities))) != (
            self.prediction_identities
        ):
            raise ValueError(
                "cost-stress prediction identities must be sorted and unique"
            )
        if len(self.scenario_identities) != len(DEFAULT_COST_MULTIPLIERS):
            raise ValueError("cost-stress fold must contain fixed scenario grid")
        if len(set(self.scenario_identities)) != len(
            self.scenario_identities
        ):
            raise ValueError("cost-stress scenario identities must be unique")
        if (
            self.automatic_scenario_selection
            or self.model_refit_performed
            or self.prediction_set_changed
        ):
            raise ValueError(
                "cost-stress fold cannot select, refit or change predictions"
            )
        if self.fold_result_identity != canonical_sha256(
            _fold_result_payload(self)
        ):
            raise ValueError("cost-stress fold result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLCostStressManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLCostStressSemantic
    config_identity: str
    walk_forward_fold_identities: tuple[str, ...]
    fold_result_identities: tuple[str, ...]
    automatic_scenario_selection: bool = False
    aggregate_winner_selection: bool = False
    model_refit_performed: bool = False
    prediction_set_changed: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.run_identity, "cost-stress run identity")
        _require_sha256(self.config_identity, "cost-stress config identity")
        if self.schema_version != ML_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported cost-stress manifest schema")
        if self.engine_version != ML_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported cost-stress manifest engine")
        if self.semantic is not (
            MLCostStressSemantic.DESCRIPTIVE_COST_STRESS_NOT_SELECTION
        ):
            raise ValueError("unsupported cost-stress semantic")
        if not self.walk_forward_fold_identities:
            raise ValueError("cost-stress run requires walk-forward folds")
        if len(self.walk_forward_fold_identities) != len(
            self.fold_result_identities
        ):
            raise ValueError("cost-stress fold/result count mismatch")
        if len(set(self.walk_forward_fold_identities)) != len(
            self.walk_forward_fold_identities
        ):
            raise ValueError("cost-stress walk-forward folds must be unique")
        if len(set(self.fold_result_identities)) != len(
            self.fold_result_identities
        ):
            raise ValueError("cost-stress fold results must be unique")
        if (
            self.automatic_scenario_selection
            or self.aggregate_winner_selection
            or self.model_refit_performed
            or self.prediction_set_changed
            or self.calibrated_probability_claim
        ):
            raise ValueError(
                "cost-stress manifest cannot select, refit, alter "
                "predictions or claim calibration"
            )
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("cost-stress research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("cost-stress run identity mismatch")


def build_ml_cost_stress_config() -> MLCostStressConfig:
    payload = {
        "automatic_scenario_selection": False,
        "engine_version": ML_COST_STRESS_ENGINE_VERSION,
        "model_refit_allowed": False,
        "multipliers": DEFAULT_COST_MULTIPLIERS,
        "prediction_change_allowed": False,
        "schema_version": ML_COST_STRESS_SCHEMA_VERSION,
    }
    return MLCostStressConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_COST_STRESS_SCHEMA_VERSION,
        engine_version=ML_COST_STRESS_ENGINE_VERSION,
        multipliers=DEFAULT_COST_MULTIPLIERS,
    )


def stress_ml_evaluation(
    *,
    model: MLBaselineModel,
    evaluation: MLEvaluation,
    predictions: Sequence[MLPrediction],
    observations: Sequence[ClusterResearchObservation],
    config: MLCostStressConfig | None = None,
) -> tuple[MLCostStressScenario, ...]:
    effective_config = config or build_ml_cost_stress_config()
    ordered_predictions = tuple(
        sorted(predictions, key=lambda item: item.prediction_identity)
    )
    if tuple(item.prediction_identity for item in ordered_predictions) != (
        evaluation.prediction_identities
    ):
        raise ValueError(
            "cost stress requires the exact accepted evaluation predictions"
        )
    if model.model_identity != evaluation.model_identity:
        raise ValueError("cost-stress model/evaluation identity mismatch")

    observation_by_identity = {
        item.observation_identity: item for item in observations
    }
    if len(observation_by_identity) != len(tuple(observations)):
        raise ValueError("cost-stress observations must be unique")
    selected_ids = evaluation.selected_observation_identities
    if any(item not in observation_by_identity for item in selected_ids):
        raise ValueError(
            "cost-stress observations must cover selected evaluation rows"
        )
    selected = tuple(observation_by_identity[item] for item in selected_ids)

    if selected:
        gross_total = sum(
            (item.gross_outcome_r for item in selected),
            start=Decimal(0),
        )
        original_cost_total = sum(
            (item.explicit_cost_r for item in selected),
            start=Decimal(0),
        )
        original_net_total = sum(
            (item.net_outcome_r for item in selected),
            start=Decimal(0),
        )
        if gross_total != evaluation.gross_r_total:
            raise ValueError("cost-stress gross-R evidence mismatch")
        if original_cost_total != evaluation.explicit_cost_r_total:
            raise ValueError("cost-stress cost evidence mismatch")
        if original_net_total != evaluation.net_r_total:
            raise ValueError("cost-stress net-R evidence mismatch")
    else:
        gross_total = None
        original_cost_total = None
        original_net_total = None

    scenarios: list[MLCostStressScenario] = []
    for multiplier in effective_config.multipliers:
        if selected:
            assert gross_total is not None
            assert original_cost_total is not None
            assert original_net_total is not None
            stressed_cost = original_cost_total * multiplier
            stressed_net = gross_total - stressed_cost
        else:
            stressed_cost = None
            stressed_net = None

        payload = {
            "config_identity": effective_config.config_identity,
            "engine_version": ML_COST_STRESS_ENGINE_VERSION,
            "evaluation_identity": evaluation.evaluation_identity,
            "gross_r_total": gross_total,
            "model_identity": model.model_identity,
            "model_refit_performed": False,
            "multiplier": multiplier,
            "original_cost_r_total": original_cost_total,
            "original_net_r_total": original_net_total,
            "prediction_set_changed": False,
            "schema_version": ML_COST_STRESS_SCHEMA_VERSION,
            "selected_observation_identities": selected_ids,
            "stressed_cost_r_total": stressed_cost,
            "stressed_net_r_total": stressed_net,
        }
        scenarios.append(
            MLCostStressScenario(
                scenario_identity=canonical_sha256(payload),
                schema_version=ML_COST_STRESS_SCHEMA_VERSION,
                engine_version=ML_COST_STRESS_ENGINE_VERSION,
                config_identity=effective_config.config_identity,
                evaluation_identity=evaluation.evaluation_identity,
                model_identity=model.model_identity,
                multiplier=multiplier,
                selected_observation_identities=selected_ids,
                gross_r_total=gross_total,
                original_cost_r_total=original_cost_total,
                stressed_cost_r_total=stressed_cost,
                original_net_r_total=original_net_total,
                stressed_net_r_total=stressed_net,
            )
        )
    return tuple(scenarios)


def run_ml_walk_forward_cost_stress(
    features: Sequence[SymbolicFeatureSpec],
    folds: Sequence[MLWalkForwardFold],
    artifacts: Sequence[
        tuple[MLBaselineModel, object, MLEvaluation]
    ],
    *,
    config: MLCostStressConfig | None = None,
) -> tuple[
    tuple[tuple[MLCostStressScenario, ...], ...],
    tuple[MLCostStressFoldResult, ...],
    MLCostStressManifest,
]:
    effective_config = config or build_ml_cost_stress_config()
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    artifact_rows = tuple(artifacts)
    if len(ordered_folds) != len(artifact_rows):
        raise ValueError("cost-stress walk-forward artifact count mismatch")
    if not ordered_folds:
        raise ValueError("cost-stress run requires walk-forward folds")

    scenario_groups: list[tuple[MLCostStressScenario, ...]] = []
    fold_results: list[MLCostStressFoldResult] = []

    for fold, artifact in zip(ordered_folds, artifact_rows, strict=True):
        model, _, accepted_evaluation = artifact
        predictions, rebuilt_evaluation = evaluate_ml_baseline(
            model,
            fold.evaluation_partition,
            fold.evaluation_observations,
            features,
        )
        if rebuilt_evaluation.evaluation_identity != (
            accepted_evaluation.evaluation_identity
        ):
            raise ValueError(
                "cost stress requires accepted walk-forward evaluation identity"
            )
        scenarios = stress_ml_evaluation(
            model=model,
            evaluation=accepted_evaluation,
            predictions=predictions,
            observations=fold.evaluation_observations,
            config=effective_config,
        )
        prediction_ids = tuple(
            sorted(item.prediction_identity for item in predictions)
        )
        scenario_ids = tuple(item.scenario_identity for item in scenarios)
        payload = {
            "automatic_scenario_selection": False,
            "engine_version": ML_COST_STRESS_ENGINE_VERSION,
            "evaluation_identity": accepted_evaluation.evaluation_identity,
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "model_identity": model.model_identity,
            "model_refit_performed": False,
            "prediction_identities": prediction_ids,
            "prediction_set_changed": False,
            "scenario_identities": scenario_ids,
            "schema_version": ML_COST_STRESS_SCHEMA_VERSION,
        }
        fold_result = MLCostStressFoldResult(
            fold_result_identity=canonical_sha256(payload),
            schema_version=ML_COST_STRESS_SCHEMA_VERSION,
            engine_version=ML_COST_STRESS_ENGINE_VERSION,
            fold_identity=fold.fold_identity,
            fold_index=fold.fold_index,
            model_identity=model.model_identity,
            evaluation_identity=accepted_evaluation.evaluation_identity,
            prediction_identities=prediction_ids,
            scenario_identities=scenario_ids,
        )
        scenario_groups.append(scenarios)
        fold_results.append(fold_result)

    walk_forward_fold_ids = tuple(item.fold_identity for item in ordered_folds)
    fold_result_ids = tuple(item.fold_result_identity for item in fold_results)
    manifest_payload = {
        "aggregate_winner_selection": False,
        "automatic_scenario_selection": False,
        "calibrated_probability_claim": False,
        "config_identity": effective_config.config_identity,
        "engine_version": ML_COST_STRESS_ENGINE_VERSION,
        "fold_result_identities": fold_result_ids,
        "model_refit_performed": False,
        "prediction_set_changed": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_COST_STRESS_SCHEMA_VERSION,
        "semantic": MLCostStressSemantic.DESCRIPTIVE_COST_STRESS_NOT_SELECTION,
        "untouched_forward_used": False,
        "walk_forward_fold_identities": walk_forward_fold_ids,
    }
    manifest = MLCostStressManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_COST_STRESS_SCHEMA_VERSION,
        engine_version=ML_COST_STRESS_ENGINE_VERSION,
        semantic=MLCostStressSemantic.DESCRIPTIVE_COST_STRESS_NOT_SELECTION,
        config_identity=effective_config.config_identity,
        walk_forward_fold_identities=walk_forward_fold_ids,
        fold_result_identities=fold_result_ids,
    )
    return tuple(scenario_groups), tuple(fold_results), manifest


def _config_payload(config: MLCostStressConfig) -> dict[str, object]:
    return {
        "automatic_scenario_selection": config.automatic_scenario_selection,
        "engine_version": config.engine_version,
        "model_refit_allowed": config.model_refit_allowed,
        "multipliers": config.multipliers,
        "prediction_change_allowed": config.prediction_change_allowed,
        "schema_version": config.schema_version,
    }


def _scenario_payload(scenario: MLCostStressScenario) -> dict[str, object]:
    return {
        "config_identity": scenario.config_identity,
        "engine_version": scenario.engine_version,
        "evaluation_identity": scenario.evaluation_identity,
        "gross_r_total": scenario.gross_r_total,
        "model_identity": scenario.model_identity,
        "model_refit_performed": scenario.model_refit_performed,
        "multiplier": scenario.multiplier,
        "original_cost_r_total": scenario.original_cost_r_total,
        "original_net_r_total": scenario.original_net_r_total,
        "prediction_set_changed": scenario.prediction_set_changed,
        "schema_version": scenario.schema_version,
        "selected_observation_identities": (
            scenario.selected_observation_identities
        ),
        "stressed_cost_r_total": scenario.stressed_cost_r_total,
        "stressed_net_r_total": scenario.stressed_net_r_total,
    }


def _fold_result_payload(
    result: MLCostStressFoldResult,
) -> dict[str, object]:
    return {
        "automatic_scenario_selection": result.automatic_scenario_selection,
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "model_identity": result.model_identity,
        "model_refit_performed": result.model_refit_performed,
        "prediction_identities": result.prediction_identities,
        "prediction_set_changed": result.prediction_set_changed,
        "scenario_identities": result.scenario_identities,
        "schema_version": result.schema_version,
    }


def _manifest_payload(manifest: MLCostStressManifest) -> dict[str, object]:
    return {
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_scenario_selection": manifest.automatic_scenario_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "fold_result_identities": manifest.fold_result_identities,
        "model_refit_performed": manifest.model_refit_performed,
        "prediction_set_changed": manifest.prediction_set_changed,
        "production_authority": manifest.production_authority,
        "real_capital": manifest.real_capital,
        "schema_version": manifest.schema_version,
        "semantic": manifest.semantic,
        "untouched_forward_used": manifest.untouched_forward_used,
        "walk_forward_fold_identities": manifest.walk_forward_fold_identities,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256 hex") from exc
