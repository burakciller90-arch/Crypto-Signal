"""Deterministic research-only robustness and ablation evidence for bounded ML."""

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
    MLTrainingManifest,
    evaluate_ml_baseline,
)
from research.alpha_factory.ml_cost_stress import (
    DEFAULT_COST_MULTIPLIERS,
    MLCostStressFoldResult,
    MLCostStressManifest,
    MLCostStressScenario,
    run_ml_walk_forward_cost_stress,
)
from research.alpha_factory.ml_walk_forward import MLWalkForwardFold
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_ROBUSTNESS_ENGINE_VERSION = "alpha-factory-ml-robustness-ablation-v1/1"
ML_ROBUSTNESS_SCHEMA_VERSION = "alpha-factory-ml-robustness-schema-v1/1"
MIN_ROBUSTNESS_FEATURES = 2
MAX_ROBUSTNESS_FEATURES = 6
REAL_CAPITAL = 0


class MLRobustnessSemantic(StrEnum):
    DESCRIPTIVE_ROBUSTNESS_ABLATION_NOT_SELECTION = (
        "descriptive_robustness_ablation_not_selection"
    )


class MLRegimeEvidenceStatus(StrEnum):
    OBSERVED = "observed"
    NO_EVIDENCE = "no_evidence"


@dataclass(frozen=True, slots=True)
class MLRobustnessConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    feature_identities: tuple[str, ...]
    regime_feature_identity: str
    regime_feature_id: str
    regime_feature_version: str
    max_feature_ablations: int
    automatic_feature_selection: bool = False
    automatic_regime_selection: bool = False
    model_refit_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "robustness config identity")
        for identity in self.feature_identities:
            _require_sha256(identity, "robustness feature identity")
        _require_sha256(
            self.regime_feature_identity,
            "robustness regime feature identity",
        )
        _require_token(self.regime_feature_id, "robustness regime feature id")
        _require_token(
            self.regime_feature_version,
            "robustness regime feature version",
        )
        if self.schema_version != ML_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported robustness config schema")
        if self.engine_version != ML_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported robustness config engine")
        if not MIN_ROBUSTNESS_FEATURES <= len(self.feature_identities) <= (
            MAX_ROBUSTNESS_FEATURES
        ):
            raise ValueError("robustness v1 requires 2..6 features")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError(
                "robustness feature identities must be sorted and unique"
            )
        if self.regime_feature_identity not in self.feature_identities:
            raise ValueError("regime feature must belong to robustness features")
        if self.max_feature_ablations != len(self.feature_identities):
            raise ValueError("robustness v1 must ablate every feature exactly once")
        if self.automatic_feature_selection:
            raise ValueError("automatic feature selection is closed")
        if self.automatic_regime_selection:
            raise ValueError("automatic regime selection is closed")
        if self.model_refit_allowed:
            raise ValueError("robustness v1 cannot refit models")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("robustness config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFeatureAblationResult:
    result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    omitted_feature_identity: str
    omitted_feature_id: str
    omitted_feature_version: str
    baseline_prediction_identities: tuple[str, ...]
    ablated_prediction_rows: tuple[tuple[str, int, bool], ...]
    baseline_positive_prediction_count: int
    ablated_positive_prediction_count: int
    changed_prediction_count: int
    selected_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    model_refit_performed: bool = False
    accepted_prediction_set_mutated: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "ablation result identity")
        _require_sha256(self.fold_identity, "ablation fold identity")
        _require_sha256(self.model_identity, "ablation model identity")
        _require_sha256(self.evaluation_identity, "ablation evaluation identity")
        _require_sha256(
            self.omitted_feature_identity,
            "ablation omitted feature identity",
        )
        _require_token(self.omitted_feature_id, "ablation omitted feature id")
        _require_token(
            self.omitted_feature_version,
            "ablation omitted feature version",
        )
        if self.schema_version != ML_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported ablation result schema")
        if self.engine_version != ML_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported ablation result engine")
        if self.fold_index < 0:
            raise ValueError("ablation fold index must be non-negative")
        if not self.baseline_prediction_identities:
            raise ValueError("ablation requires baseline predictions")
        if tuple(sorted(set(self.baseline_prediction_identities))) != (
            self.baseline_prediction_identities
        ):
            raise ValueError(
                "ablation baseline prediction identities must be sorted and unique"
            )
        if not self.ablated_prediction_rows:
            raise ValueError("ablation requires prediction rows")
        row_ids = tuple(item[0] for item in self.ablated_prediction_rows)
        if row_ids != tuple(sorted(set(row_ids))):
            raise ValueError(
                "ablation prediction rows must be sorted by unique observation"
            )
        for observation_identity, score, predicted_positive in (
            self.ablated_prediction_rows
        ):
            _require_sha256(
                observation_identity,
                "ablation prediction observation identity",
            )
            if predicted_positive != (score > 0):
                raise ValueError(
                    "ablation predicted label must match deterministic score"
                )
        if not 0 <= self.baseline_positive_prediction_count <= len(
            self.ablated_prediction_rows
        ):
            raise ValueError("invalid baseline positive prediction count")
        if not 0 <= self.ablated_positive_prediction_count <= len(
            self.ablated_prediction_rows
        ):
            raise ValueError("invalid ablated positive prediction count")
        if not 0 <= self.changed_prediction_count <= len(
            self.ablated_prediction_rows
        ):
            raise ValueError("invalid changed prediction count")
        if len(self.selected_observation_identities) != (
            self.ablated_positive_prediction_count
        ):
            raise ValueError("ablation selected observation count mismatch")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "ablation selected observations must be sorted and unique"
            )
        _validate_metrics(
            selected_count=self.ablated_positive_prediction_count,
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
            average_net_r=self.average_net_r,
            label="ablation",
        )
        if self.model_refit_performed:
            raise ValueError("ablation cannot refit model")
        if self.accepted_prediction_set_mutated:
            raise ValueError("ablation cannot mutate accepted predictions")
        if self.result_identity != canonical_sha256(_ablation_payload(self)):
            raise ValueError("ablation result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLRegimeSliceResult:
    result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    regime_feature_identity: str
    regime_feature_id: str
    regime_feature_version: str
    regime_value: str
    status: MLRegimeEvidenceStatus
    observation_identities: tuple[str, ...]
    positive_prediction_count: int
    selected_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "regime result identity")
        _require_sha256(self.fold_identity, "regime fold identity")
        _require_sha256(self.model_identity, "regime model identity")
        _require_sha256(self.evaluation_identity, "regime evaluation identity")
        _require_sha256(
            self.regime_feature_identity,
            "regime feature identity",
        )
        _require_token(self.regime_feature_id, "regime feature id")
        _require_token(self.regime_feature_version, "regime feature version")
        _require_token(self.regime_value, "regime value")
        if self.schema_version != ML_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported regime result schema")
        if self.engine_version != ML_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported regime result engine")
        if self.fold_index < 0:
            raise ValueError("regime fold index must be non-negative")
        if tuple(sorted(set(self.observation_identities))) != (
            self.observation_identities
        ):
            raise ValueError("regime observations must be sorted and unique")
        if not 0 <= self.positive_prediction_count <= len(
            self.observation_identities
        ):
            raise ValueError("invalid regime positive prediction count")
        if len(self.selected_observation_identities) != (
            self.positive_prediction_count
        ):
            raise ValueError("regime selected observation count mismatch")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "regime selected observations must be sorted and unique"
            )
        if not self.observation_identities:
            if self.status is not MLRegimeEvidenceStatus.NO_EVIDENCE:
                raise ValueError("empty regime slice must be explicit no-evidence")
            if self.positive_prediction_count:
                raise ValueError("empty regime slice cannot have predictions")
        elif self.status is not MLRegimeEvidenceStatus.OBSERVED:
            raise ValueError("observed regime slice must use observed status")
        _validate_metrics(
            selected_count=self.positive_prediction_count,
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
            average_net_r=self.average_net_r,
            label="regime",
        )
        if self.result_identity != canonical_sha256(_regime_payload(self)):
            raise ValueError("regime result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLRobustnessFoldResult:
    result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    cost_stress_fold_result_identity: str
    cost_stress_scenario_identities: tuple[str, ...]
    feature_ablation_result_identities: tuple[str, ...]
    regime_result_identities: tuple[str, ...]
    automatic_selection: bool = False
    model_refit_performed: bool = False
    accepted_prediction_set_mutated: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "robustness fold result identity")
        _require_sha256(self.fold_identity, "robustness fold identity")
        _require_sha256(self.model_identity, "robustness model identity")
        _require_sha256(
            self.evaluation_identity,
            "robustness evaluation identity",
        )
        _require_sha256(
            self.cost_stress_fold_result_identity,
            "robustness cost-stress fold result identity",
        )
        if self.schema_version != ML_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported robustness fold schema")
        if self.engine_version != ML_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported robustness fold engine")
        if self.fold_index < 0:
            raise ValueError("robustness fold index must be non-negative")
        if len(self.cost_stress_scenario_identities) != len(
            DEFAULT_COST_MULTIPLIERS
        ):
            raise ValueError("robustness fold requires fixed cost-stress grid")
        for identity in self.cost_stress_scenario_identities:
            _require_sha256(identity, "robustness cost-stress scenario identity")
        if len(set(self.cost_stress_scenario_identities)) != len(
            self.cost_stress_scenario_identities
        ):
            raise ValueError("robustness cost-stress scenarios must be unique")
        for identities, label in (
            (self.feature_ablation_result_identities, "feature ablation"),
            (self.regime_result_identities, "regime"),
        ):
            if not identities:
                raise ValueError(f"robustness fold requires {label} results")
            for identity in identities:
                _require_sha256(identity, f"robustness {label} identity")
            if tuple(sorted(set(identities))) != identities:
                raise ValueError(
                    f"robustness {label} identities must be sorted and unique"
                )
        if (
            self.automatic_selection
            or self.model_refit_performed
            or self.accepted_prediction_set_mutated
        ):
            raise ValueError(
                "robustness fold cannot select, refit or mutate accepted predictions"
            )
        if self.result_identity != canonical_sha256(_fold_payload(self)):
            raise ValueError("robustness fold result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFoldSensitivitySummary:
    summary_identity: str
    schema_version: str
    engine_version: str
    fold_identities: tuple[str, ...]
    evaluation_identities: tuple[str, ...]
    baseline_net_r_by_fold: tuple[tuple[int, Decimal | None], ...]
    max_cost_stress_net_r_by_fold: tuple[tuple[int, Decimal | None], ...]
    ablation_changed_prediction_counts_by_fold: tuple[tuple[int, int], ...]
    automatic_fold_selection: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.summary_identity, "fold sensitivity identity")
        if self.schema_version != ML_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported fold sensitivity schema")
        if self.engine_version != ML_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported fold sensitivity engine")
        if not self.fold_identities:
            raise ValueError("fold sensitivity requires folds")
        if len(self.fold_identities) != len(self.evaluation_identities):
            raise ValueError("fold sensitivity fold/evaluation count mismatch")
        for identity in self.fold_identities:
            _require_sha256(identity, "fold sensitivity fold identity")
        for identity in self.evaluation_identities:
            _require_sha256(identity, "fold sensitivity evaluation identity")
        expected_indexes = tuple(range(len(self.fold_identities)))
        for rows, label in (
            (self.baseline_net_r_by_fold, "baseline"),
            (self.max_cost_stress_net_r_by_fold, "cost-stress"),
            (
                self.ablation_changed_prediction_counts_by_fold,
                "ablation",
            ),
        ):
            if tuple(item[0] for item in rows) != expected_indexes:
                raise ValueError(
                    f"fold sensitivity {label} indexes must be contiguous"
                )
        if any(
            item[1] < 0
            for item in self.ablation_changed_prediction_counts_by_fold
        ):
            raise ValueError("ablation change counts must be non-negative")
        if self.automatic_fold_selection:
            raise ValueError("automatic fold selection is closed")
        if self.summary_identity != canonical_sha256(
            _sensitivity_payload(self)
        ):
            raise ValueError("fold sensitivity identity mismatch")


@dataclass(frozen=True, slots=True)
class MLRobustnessManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLRobustnessSemantic
    config_identity: str
    cost_stress_run_identity: str
    fold_identities: tuple[str, ...]
    fold_result_identities: tuple[str, ...]
    fold_sensitivity_identity: str
    automatic_feature_selection: bool = False
    automatic_regime_selection: bool = False
    aggregate_winner_selection: bool = False
    model_refit_performed: bool = False
    accepted_prediction_set_mutated: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.run_identity, "robustness run identity")
        _require_sha256(self.config_identity, "robustness config identity")
        _require_sha256(
            self.cost_stress_run_identity,
            "robustness cost-stress run identity",
        )
        _require_sha256(
            self.fold_sensitivity_identity,
            "robustness fold sensitivity identity",
        )
        if self.schema_version != ML_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported robustness manifest schema")
        if self.engine_version != ML_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported robustness manifest engine")
        if self.semantic is not (
            MLRobustnessSemantic.DESCRIPTIVE_ROBUSTNESS_ABLATION_NOT_SELECTION
        ):
            raise ValueError("unsupported robustness semantic")
        if not self.fold_identities:
            raise ValueError("robustness manifest requires folds")
        if len(self.fold_identities) != len(self.fold_result_identities):
            raise ValueError("robustness fold/result count mismatch")
        for identities, label in (
            (self.fold_identities, "fold"),
            (self.fold_result_identities, "fold result"),
        ):
            for identity in identities:
                _require_sha256(identity, f"robustness {label} identity")
            if len(set(identities)) != len(identities):
                raise ValueError(f"robustness {label} identities must be unique")
        if (
            self.automatic_feature_selection
            or self.automatic_regime_selection
            or self.aggregate_winner_selection
            or self.model_refit_performed
            or self.accepted_prediction_set_mutated
            or self.calibrated_probability_claim
        ):
            raise ValueError(
                "robustness manifest cannot select, refit, mutate or calibrate"
            )
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("robustness research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("robustness run identity mismatch")


def build_ml_robustness_config(
    features: Sequence[SymbolicFeatureSpec],
    *,
    regime_feature_id: str,
) -> MLRobustnessConfig:
    ordered = tuple(sorted(features, key=lambda item: item.feature_id))
    if not MIN_ROBUSTNESS_FEATURES <= len(ordered) <= MAX_ROBUSTNESS_FEATURES:
        raise ValueError("robustness v1 requires 2..6 features")
    feature_ids = tuple(item.feature_id for item in ordered)
    if feature_ids != tuple(sorted(set(feature_ids))):
        raise ValueError("robustness features must have unique ids")
    feature_identities = tuple(sorted(item.feature_identity for item in ordered))
    regime_matches = tuple(
        item for item in ordered if item.feature_id == regime_feature_id
    )
    if len(regime_matches) != 1:
        raise ValueError("robustness requires one explicit regime feature")
    regime = regime_matches[0]
    payload = {
        "automatic_feature_selection": False,
        "automatic_regime_selection": False,
        "engine_version": ML_ROBUSTNESS_ENGINE_VERSION,
        "feature_identities": feature_identities,
        "max_feature_ablations": len(ordered),
        "model_refit_allowed": False,
        "regime_feature_id": regime.feature_id,
        "regime_feature_identity": regime.feature_identity,
        "regime_feature_version": regime.feature_version,
        "schema_version": ML_ROBUSTNESS_SCHEMA_VERSION,
    }
    return MLRobustnessConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_ROBUSTNESS_ENGINE_VERSION,
        feature_identities=feature_identities,
        regime_feature_identity=regime.feature_identity,
        regime_feature_id=regime.feature_id,
        regime_feature_version=regime.feature_version,
        max_feature_ablations=len(ordered),
    )


def run_ml_robustness_ablation(
    features: Sequence[SymbolicFeatureSpec],
    folds: Sequence[MLWalkForwardFold],
    artifacts: Sequence[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation]
    ],
    cost_stress_evidence: tuple[
        tuple[tuple[MLCostStressScenario, ...], ...],
        tuple[MLCostStressFoldResult, ...],
        MLCostStressManifest,
    ],
    *,
    regime_feature_id: str,
    config: MLRobustnessConfig | None = None,
) -> tuple[
    tuple[tuple[MLFeatureAblationResult, ...], ...],
    tuple[tuple[MLRegimeSliceResult, ...], ...],
    tuple[MLRobustnessFoldResult, ...],
    MLFoldSensitivitySummary,
    MLRobustnessManifest,
]:
    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    effective_config = config or build_ml_robustness_config(
        ordered_features,
        regime_feature_id=regime_feature_id,
    )
    _validate_config_features(
        effective_config,
        ordered_features,
        regime_feature_id=regime_feature_id,
    )
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    artifact_rows = tuple(artifacts)
    if not ordered_folds:
        raise ValueError("robustness requires walk-forward folds")
    if len(ordered_folds) != len(artifact_rows):
        raise ValueError("robustness walk-forward artifact count mismatch")

    expected_cost_stress = run_ml_walk_forward_cost_stress(
        ordered_features,
        ordered_folds,
        artifact_rows,
    )
    if expected_cost_stress != cost_stress_evidence:
        raise ValueError("robustness requires exact accepted cost-stress evidence")
    scenario_groups, cost_fold_results, cost_manifest = cost_stress_evidence

    regime_feature = next(
        item
        for item in ordered_features
        if item.feature_id == effective_config.regime_feature_id
    )

    ablation_groups: list[tuple[MLFeatureAblationResult, ...]] = []
    regime_groups: list[tuple[MLRegimeSliceResult, ...]] = []
    fold_results: list[MLRobustnessFoldResult] = []

    for fold, artifact, scenarios, cost_fold in zip(
        ordered_folds,
        artifact_rows,
        scenario_groups,
        cost_fold_results,
        strict=True,
    ):
        model, training_manifest, accepted_evaluation = artifact
        _validate_fold_artifact(
            fold,
            model,
            training_manifest,
            accepted_evaluation,
        )
        predictions, rebuilt_evaluation = evaluate_ml_baseline(
            model,
            fold.evaluation_partition,
            fold.evaluation_observations,
            ordered_features,
        )
        if rebuilt_evaluation != accepted_evaluation:
            raise ValueError(
                "robustness requires exact accepted evaluation identity"
            )
        baseline_by_observation = {
            item.observation_identity: item for item in predictions
        }
        baseline_prediction_ids = tuple(
            sorted(item.prediction_identity for item in predictions)
        )
        ordered_observations = tuple(
            sorted(
                fold.evaluation_observations,
                key=lambda item: item.observation_identity,
            )
        )

        fold_ablations = tuple(
            _build_feature_ablation(
                fold=fold,
                model=model,
                evaluation=accepted_evaluation,
                baseline_by_observation=baseline_by_observation,
                baseline_prediction_ids=baseline_prediction_ids,
                observations=ordered_observations,
                omitted_feature=feature,
            )
            for feature in ordered_features
        )
        fold_regimes = tuple(
            _build_regime_slice(
                fold=fold,
                model=model,
                evaluation=accepted_evaluation,
                baseline_by_observation=baseline_by_observation,
                observations=ordered_observations,
                regime_feature=regime_feature,
                regime_value=value,
            )
            for value in regime_feature.allowed_values
        )

        scenario_ids = tuple(item.scenario_identity for item in scenarios)
        ablation_ids = tuple(
            sorted(item.result_identity for item in fold_ablations)
        )
        regime_ids = tuple(sorted(item.result_identity for item in fold_regimes))
        fold_payload = {
            "accepted_prediction_set_mutated": False,
            "automatic_selection": False,
            "cost_stress_fold_result_identity": (
                cost_fold.fold_result_identity
            ),
            "cost_stress_scenario_identities": scenario_ids,
            "engine_version": ML_ROBUSTNESS_ENGINE_VERSION,
            "evaluation_identity": accepted_evaluation.evaluation_identity,
            "feature_ablation_result_identities": ablation_ids,
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "model_identity": model.model_identity,
            "model_refit_performed": False,
            "regime_result_identities": regime_ids,
            "schema_version": ML_ROBUSTNESS_SCHEMA_VERSION,
        }
        fold_result = MLRobustnessFoldResult(
            result_identity=canonical_sha256(fold_payload),
            schema_version=ML_ROBUSTNESS_SCHEMA_VERSION,
            engine_version=ML_ROBUSTNESS_ENGINE_VERSION,
            fold_identity=fold.fold_identity,
            fold_index=fold.fold_index,
            model_identity=model.model_identity,
            evaluation_identity=accepted_evaluation.evaluation_identity,
            cost_stress_fold_result_identity=cost_fold.fold_result_identity,
            cost_stress_scenario_identities=scenario_ids,
            feature_ablation_result_identities=ablation_ids,
            regime_result_identities=regime_ids,
        )
        ablation_groups.append(fold_ablations)
        regime_groups.append(fold_regimes)
        fold_results.append(fold_result)

    sensitivity = _build_fold_sensitivity(
        ordered_folds,
        artifact_rows,
        scenario_groups,
        tuple(ablation_groups),
    )
    fold_ids = tuple(item.fold_identity for item in ordered_folds)
    fold_result_ids = tuple(item.result_identity for item in fold_results)
    manifest_payload = {
        "accepted_prediction_set_mutated": False,
        "aggregate_winner_selection": False,
        "automatic_feature_selection": False,
        "automatic_regime_selection": False,
        "calibrated_probability_claim": False,
        "config_identity": effective_config.config_identity,
        "cost_stress_run_identity": cost_manifest.run_identity,
        "engine_version": ML_ROBUSTNESS_ENGINE_VERSION,
        "fold_identities": fold_ids,
        "fold_result_identities": fold_result_ids,
        "fold_sensitivity_identity": sensitivity.summary_identity,
        "model_refit_performed": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_ROBUSTNESS_SCHEMA_VERSION,
        "semantic": (
            MLRobustnessSemantic
            .DESCRIPTIVE_ROBUSTNESS_ABLATION_NOT_SELECTION
        ),
        "untouched_forward_used": False,
    }
    manifest = MLRobustnessManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_ROBUSTNESS_ENGINE_VERSION,
        semantic=(
            MLRobustnessSemantic
            .DESCRIPTIVE_ROBUSTNESS_ABLATION_NOT_SELECTION
        ),
        config_identity=effective_config.config_identity,
        cost_stress_run_identity=cost_manifest.run_identity,
        fold_identities=fold_ids,
        fold_result_identities=fold_result_ids,
        fold_sensitivity_identity=sensitivity.summary_identity,
    )
    return (
        tuple(ablation_groups),
        tuple(regime_groups),
        tuple(fold_results),
        sensitivity,
        manifest,
    )


def _build_feature_ablation(
    *,
    fold: MLWalkForwardFold,
    model: MLBaselineModel,
    evaluation: MLEvaluation,
    baseline_by_observation: dict[str, MLPrediction],
    baseline_prediction_ids: tuple[str, ...],
    observations: tuple[ClusterResearchObservation, ...],
    omitted_feature: SymbolicFeatureSpec,
) -> MLFeatureAblationResult:
    rows = tuple(
        (
            observation.observation_identity,
            _score_without_feature(
                model,
                observation,
                omitted_feature_identity=omitted_feature.feature_identity,
            ),
        )
        for observation in observations
    )
    ablated_rows = tuple(
        (
            observation_identity,
            score,
            score > 0,
        )
        for observation_identity, score in rows
    )
    selected_ids = tuple(
        sorted(
            observation_identity
            for observation_identity, _, predicted_positive in ablated_rows
            if predicted_positive
        )
    )
    selected_set = set(selected_ids)
    selected = tuple(
        item
        for item in observations
        if item.observation_identity in selected_set
    )
    gross, cost, net, average = _selected_metrics(selected)
    changed = sum(
        baseline_by_observation[observation_identity].predicted_positive
        != predicted_positive
        for observation_identity, _, predicted_positive in ablated_rows
    )
    payload = {
        "accepted_prediction_set_mutated": False,
        "ablated_positive_prediction_count": len(selected_ids),
        "ablated_prediction_rows": ablated_rows,
        "average_net_r": average,
        "baseline_positive_prediction_count": (
            evaluation.positive_prediction_count
        ),
        "baseline_prediction_identities": baseline_prediction_ids,
        "changed_prediction_count": changed,
        "engine_version": ML_ROBUSTNESS_ENGINE_VERSION,
        "evaluation_identity": evaluation.evaluation_identity,
        "explicit_cost_r_total": cost,
        "fold_identity": fold.fold_identity,
        "fold_index": fold.fold_index,
        "gross_r_total": gross,
        "model_identity": model.model_identity,
        "model_refit_performed": False,
        "net_r_total": net,
        "omitted_feature_id": omitted_feature.feature_id,
        "omitted_feature_identity": omitted_feature.feature_identity,
        "omitted_feature_version": omitted_feature.feature_version,
        "schema_version": ML_ROBUSTNESS_SCHEMA_VERSION,
        "selected_observation_identities": selected_ids,
    }
    return MLFeatureAblationResult(
        result_identity=canonical_sha256(payload),
        schema_version=ML_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_ROBUSTNESS_ENGINE_VERSION,
        fold_identity=fold.fold_identity,
        fold_index=fold.fold_index,
        model_identity=model.model_identity,
        evaluation_identity=evaluation.evaluation_identity,
        omitted_feature_identity=omitted_feature.feature_identity,
        omitted_feature_id=omitted_feature.feature_id,
        omitted_feature_version=omitted_feature.feature_version,
        baseline_prediction_identities=baseline_prediction_ids,
        ablated_prediction_rows=ablated_rows,
        baseline_positive_prediction_count=evaluation.positive_prediction_count,
        ablated_positive_prediction_count=len(selected_ids),
        changed_prediction_count=changed,
        selected_observation_identities=selected_ids,
        gross_r_total=gross,
        explicit_cost_r_total=cost,
        net_r_total=net,
        average_net_r=average,
    )


def _build_regime_slice(
    *,
    fold: MLWalkForwardFold,
    model: MLBaselineModel,
    evaluation: MLEvaluation,
    baseline_by_observation: dict[str, MLPrediction],
    observations: tuple[ClusterResearchObservation, ...],
    regime_feature: SymbolicFeatureSpec,
    regime_value: str,
) -> MLRegimeSliceResult:
    matching = tuple(
        item
        for item in observations
        if _reading_value(item, regime_feature.feature_id) == regime_value
    )
    observation_ids = tuple(
        sorted(item.observation_identity for item in matching)
    )
    selected = tuple(
        item
        for item in matching
        if baseline_by_observation[item.observation_identity].predicted_positive
    )
    selected_ids = tuple(
        sorted(item.observation_identity for item in selected)
    )
    gross, cost, net, average = _selected_metrics(selected)
    status = (
        MLRegimeEvidenceStatus.OBSERVED
        if matching
        else MLRegimeEvidenceStatus.NO_EVIDENCE
    )
    payload = {
        "average_net_r": average,
        "engine_version": ML_ROBUSTNESS_ENGINE_VERSION,
        "evaluation_identity": evaluation.evaluation_identity,
        "explicit_cost_r_total": cost,
        "fold_identity": fold.fold_identity,
        "fold_index": fold.fold_index,
        "gross_r_total": gross,
        "model_identity": model.model_identity,
        "net_r_total": net,
        "observation_identities": observation_ids,
        "positive_prediction_count": len(selected_ids),
        "regime_feature_id": regime_feature.feature_id,
        "regime_feature_identity": regime_feature.feature_identity,
        "regime_feature_version": regime_feature.feature_version,
        "regime_value": regime_value,
        "schema_version": ML_ROBUSTNESS_SCHEMA_VERSION,
        "selected_observation_identities": selected_ids,
        "status": status,
    }
    return MLRegimeSliceResult(
        result_identity=canonical_sha256(payload),
        schema_version=ML_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_ROBUSTNESS_ENGINE_VERSION,
        fold_identity=fold.fold_identity,
        fold_index=fold.fold_index,
        model_identity=model.model_identity,
        evaluation_identity=evaluation.evaluation_identity,
        regime_feature_identity=regime_feature.feature_identity,
        regime_feature_id=regime_feature.feature_id,
        regime_feature_version=regime_feature.feature_version,
        regime_value=regime_value,
        status=status,
        observation_identities=observation_ids,
        positive_prediction_count=len(selected_ids),
        selected_observation_identities=selected_ids,
        gross_r_total=gross,
        explicit_cost_r_total=cost,
        net_r_total=net,
        average_net_r=average,
    )


def _build_fold_sensitivity(
    folds: tuple[MLWalkForwardFold, ...],
    artifacts: tuple[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation],
        ...,
    ],
    scenario_groups: tuple[tuple[MLCostStressScenario, ...], ...],
    ablation_groups: tuple[tuple[MLFeatureAblationResult, ...], ...],
) -> MLFoldSensitivitySummary:
    fold_ids = tuple(item.fold_identity for item in folds)
    evaluation_ids = tuple(item[2].evaluation_identity for item in artifacts)
    baseline_rows = tuple(
        (index, artifact[2].net_r_total)
        for index, artifact in enumerate(artifacts)
    )
    max_stress_rows = tuple(
        (index, scenarios[-1].stressed_net_r_total)
        for index, scenarios in enumerate(scenario_groups)
    )
    ablation_rows = tuple(
        (
            index,
            sum(item.changed_prediction_count for item in ablations),
        )
        for index, ablations in enumerate(ablation_groups)
    )
    payload = {
        "ablation_changed_prediction_counts_by_fold": ablation_rows,
        "automatic_fold_selection": False,
        "baseline_net_r_by_fold": baseline_rows,
        "engine_version": ML_ROBUSTNESS_ENGINE_VERSION,
        "evaluation_identities": evaluation_ids,
        "fold_identities": fold_ids,
        "max_cost_stress_net_r_by_fold": max_stress_rows,
        "schema_version": ML_ROBUSTNESS_SCHEMA_VERSION,
    }
    return MLFoldSensitivitySummary(
        summary_identity=canonical_sha256(payload),
        schema_version=ML_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_ROBUSTNESS_ENGINE_VERSION,
        fold_identities=fold_ids,
        evaluation_identities=evaluation_ids,
        baseline_net_r_by_fold=baseline_rows,
        max_cost_stress_net_r_by_fold=max_stress_rows,
        ablation_changed_prediction_counts_by_fold=ablation_rows,
    )


def _validate_config_features(
    config: MLRobustnessConfig,
    features: tuple[SymbolicFeatureSpec, ...],
    *,
    regime_feature_id: str,
) -> None:
    identities = tuple(sorted(item.feature_identity for item in features))
    if identities != config.feature_identities:
        raise ValueError("robustness config feature identity mismatch")
    regime = tuple(
        item for item in features if item.feature_id == regime_feature_id
    )
    if len(regime) != 1:
        raise ValueError("robustness requires one explicit regime feature")
    feature = regime[0]
    if (
        feature.feature_identity != config.regime_feature_identity
        or feature.feature_version != config.regime_feature_version
        or feature.feature_id != config.regime_feature_id
    ):
        raise ValueError("robustness regime feature identity mismatch")


def _validate_fold_artifact(
    fold: MLWalkForwardFold,
    model: MLBaselineModel,
    training_manifest: MLTrainingManifest,
    evaluation: MLEvaluation,
) -> None:
    if model.config_identity != fold.config_identity:
        raise ValueError("robustness model/fold config identity mismatch")
    if model.training_partition_identity != (
        fold.training_partition.partition_identity
    ):
        raise ValueError("robustness model training partition mismatch")
    if training_manifest.model_identity != model.model_identity:
        raise ValueError("robustness training/model identity mismatch")
    if training_manifest.training_partition_identity != (
        fold.training_partition.partition_identity
    ):
        raise ValueError("robustness training partition identity mismatch")
    if evaluation.model_identity != model.model_identity:
        raise ValueError("robustness evaluation/model identity mismatch")
    if evaluation.partition_identity != (
        fold.evaluation_partition.partition_identity
    ):
        raise ValueError("robustness evaluation partition identity mismatch")


def _score_without_feature(
    model: MLBaselineModel,
    observation: ClusterResearchObservation,
    *,
    omitted_feature_identity: str,
) -> int:
    if omitted_feature_identity not in model.feature_identities:
        raise ValueError("ablation omitted feature is outside accepted model")
    score = model.positive_count - model.non_positive_count
    count_by_key = {
        (item.feature_id, item.feature_version, item.value): item
        for item in model.category_counts
    }
    for reading in observation.feature_readings:
        if reading.feature_identity == omitted_feature_identity:
            continue
        category = count_by_key.get(
            (reading.feature_id, reading.feature_version, reading.value)
        )
        if category is not None:
            score += category.positive_count - category.non_positive_count
    return score


def _reading_value(
    observation: ClusterResearchObservation,
    feature_id: str,
) -> str:
    matches = tuple(
        item.value
        for item in observation.feature_readings
        if item.feature_id == feature_id
    )
    if len(matches) != 1:
        raise ValueError("regime observation feature coverage mismatch")
    return matches[0]


def _selected_metrics(
    observations: Sequence[ClusterResearchObservation],
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    selected = tuple(observations)
    if not selected:
        return None, None, None, None
    gross = sum((item.gross_outcome_r for item in selected), start=Decimal(0))
    cost = sum((item.explicit_cost_r for item in selected), start=Decimal(0))
    net = sum((item.net_outcome_r for item in selected), start=Decimal(0))
    return gross, cost, net, net / Decimal(len(selected))


def _validate_metrics(
    *,
    selected_count: int,
    gross_r_total: Decimal | None,
    explicit_cost_r_total: Decimal | None,
    net_r_total: Decimal | None,
    average_net_r: Decimal | None,
    label: str,
) -> None:
    metrics = (
        gross_r_total,
        explicit_cost_r_total,
        net_r_total,
        average_net_r,
    )
    if selected_count == 0:
        if any(item is not None for item in metrics):
            raise ValueError(f"{label} with no selections cannot fabricate metrics")
        return
    if any(item is None for item in metrics):
        raise ValueError(f"{label} selections require complete metrics")
    assert gross_r_total is not None
    assert explicit_cost_r_total is not None
    assert net_r_total is not None
    assert average_net_r is not None
    if explicit_cost_r_total < 0:
        raise ValueError(f"{label} explicit cost cannot be negative")
    if net_r_total != gross_r_total - explicit_cost_r_total:
        raise ValueError(f"{label} net-R accounting mismatch")
    if average_net_r != net_r_total / Decimal(selected_count):
        raise ValueError(f"{label} average net-R mismatch")


def _config_payload(config: MLRobustnessConfig) -> dict[str, object]:
    return {
        "automatic_feature_selection": config.automatic_feature_selection,
        "automatic_regime_selection": config.automatic_regime_selection,
        "engine_version": config.engine_version,
        "feature_identities": config.feature_identities,
        "max_feature_ablations": config.max_feature_ablations,
        "model_refit_allowed": config.model_refit_allowed,
        "regime_feature_id": config.regime_feature_id,
        "regime_feature_identity": config.regime_feature_identity,
        "regime_feature_version": config.regime_feature_version,
        "schema_version": config.schema_version,
    }


def _ablation_payload(result: MLFeatureAblationResult) -> dict[str, object]:
    return {
        "accepted_prediction_set_mutated": result.accepted_prediction_set_mutated,
        "ablated_positive_prediction_count": (
            result.ablated_positive_prediction_count
        ),
        "ablated_prediction_rows": result.ablated_prediction_rows,
        "average_net_r": result.average_net_r,
        "baseline_positive_prediction_count": (
            result.baseline_positive_prediction_count
        ),
        "baseline_prediction_identities": result.baseline_prediction_identities,
        "changed_prediction_count": result.changed_prediction_count,
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "explicit_cost_r_total": result.explicit_cost_r_total,
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "gross_r_total": result.gross_r_total,
        "model_identity": result.model_identity,
        "model_refit_performed": result.model_refit_performed,
        "net_r_total": result.net_r_total,
        "omitted_feature_id": result.omitted_feature_id,
        "omitted_feature_identity": result.omitted_feature_identity,
        "omitted_feature_version": result.omitted_feature_version,
        "schema_version": result.schema_version,
        "selected_observation_identities": (
            result.selected_observation_identities
        ),
    }


def _regime_payload(result: MLRegimeSliceResult) -> dict[str, object]:
    return {
        "average_net_r": result.average_net_r,
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "explicit_cost_r_total": result.explicit_cost_r_total,
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "gross_r_total": result.gross_r_total,
        "model_identity": result.model_identity,
        "net_r_total": result.net_r_total,
        "observation_identities": result.observation_identities,
        "positive_prediction_count": result.positive_prediction_count,
        "regime_feature_id": result.regime_feature_id,
        "regime_feature_identity": result.regime_feature_identity,
        "regime_feature_version": result.regime_feature_version,
        "regime_value": result.regime_value,
        "schema_version": result.schema_version,
        "selected_observation_identities": result.selected_observation_identities,
        "status": result.status,
    }


def _fold_payload(result: MLRobustnessFoldResult) -> dict[str, object]:
    return {
        "accepted_prediction_set_mutated": (
            result.accepted_prediction_set_mutated
        ),
        "automatic_selection": result.automatic_selection,
        "cost_stress_fold_result_identity": (
            result.cost_stress_fold_result_identity
        ),
        "cost_stress_scenario_identities": (
            result.cost_stress_scenario_identities
        ),
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "feature_ablation_result_identities": (
            result.feature_ablation_result_identities
        ),
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "model_identity": result.model_identity,
        "model_refit_performed": result.model_refit_performed,
        "regime_result_identities": result.regime_result_identities,
        "schema_version": result.schema_version,
    }


def _sensitivity_payload(
    summary: MLFoldSensitivitySummary,
) -> dict[str, object]:
    return {
        "ablation_changed_prediction_counts_by_fold": (
            summary.ablation_changed_prediction_counts_by_fold
        ),
        "automatic_fold_selection": summary.automatic_fold_selection,
        "baseline_net_r_by_fold": summary.baseline_net_r_by_fold,
        "engine_version": summary.engine_version,
        "evaluation_identities": summary.evaluation_identities,
        "fold_identities": summary.fold_identities,
        "max_cost_stress_net_r_by_fold": (
            summary.max_cost_stress_net_r_by_fold
        ),
        "schema_version": summary.schema_version,
    }


def _manifest_payload(manifest: MLRobustnessManifest) -> dict[str, object]:
    return {
        "accepted_prediction_set_mutated": (
            manifest.accepted_prediction_set_mutated
        ),
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_feature_selection": manifest.automatic_feature_selection,
        "automatic_regime_selection": manifest.automatic_regime_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "config_identity": manifest.config_identity,
        "cost_stress_run_identity": manifest.cost_stress_run_identity,
        "engine_version": manifest.engine_version,
        "fold_identities": manifest.fold_identities,
        "fold_result_identities": manifest.fold_result_identities,
        "fold_sensitivity_identity": manifest.fold_sensitivity_identity,
        "model_refit_performed": manifest.model_refit_performed,
        "production_authority": manifest.production_authority,
        "real_capital": manifest.real_capital,
        "schema_version": manifest.schema_version,
        "semantic": manifest.semantic,
        "untouched_forward_used": manifest.untouched_forward_used,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256 hex") from exc


def _require_token(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty trimmed token")
