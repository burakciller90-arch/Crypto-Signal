from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import ClusterResearchObservation
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.ml_baseline import (
    MLBaselineModel,
    MLEvaluation,
    MLTrainingConfig,
    MLTrainingManifest,
    build_ml_training_config,
    evaluate_ml_baseline,
    fit_ml_baseline,
)
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_WALK_FORWARD_ENGINE_VERSION = "alpha-factory-ml-walk-forward-v1/1"
ML_WALK_FORWARD_SCHEMA_VERSION = "alpha-factory-ml-walk-forward-schema-v1/1"
MIN_WALK_FORWARD_FOLDS = 2
MAX_WALK_FORWARD_FOLDS = 6
REAL_CAPITAL = 0


class MLWalkForwardSemantic(StrEnum):
    DESCRIPTIVE_WALK_FORWARD_NOT_PROMOTION = (
        "descriptive_walk_forward_not_promotion"
    )


@dataclass(frozen=True, slots=True)
class MLWalkForwardFold:
    fold_identity: str
    schema_version: str
    engine_version: str
    fold_index: int
    dataset_identity: str
    config_identity: str
    training_partition: ResearchPartition
    evaluation_partition: ResearchPartition
    training_observations: tuple[ClusterResearchObservation, ...]
    evaluation_observations: tuple[ClusterResearchObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.fold_identity, "walk-forward fold identity")
        _require_sha256(self.dataset_identity, "walk-forward dataset identity")
        _require_sha256(self.config_identity, "walk-forward config identity")
        if self.schema_version != ML_WALK_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported walk-forward fold schema")
        if self.engine_version != ML_WALK_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported walk-forward fold engine")
        if self.fold_index < 0:
            raise ValueError("walk-forward fold index must be non-negative")
        if self.training_partition.role is not PartitionRole.TRAIN:
            raise ValueError("walk-forward training partition must be TRAIN")
        if self.evaluation_partition.role is not PartitionRole.OUT_OF_SAMPLE:
            raise ValueError(
                "walk-forward evaluation partition must be OUT_OF_SAMPLE"
            )
        if self.training_partition.dataset_identity != self.dataset_identity:
            raise ValueError("walk-forward training dataset identity mismatch")
        if self.evaluation_partition.dataset_identity != self.dataset_identity:
            raise ValueError("walk-forward evaluation dataset identity mismatch")
        if self.training_partition.end_ms > self.evaluation_partition.start_ms:
            raise ValueError(
                "walk-forward training must end before evaluation begins"
            )
        if not self.training_observations:
            raise ValueError("walk-forward fold requires training observations")
        if not self.evaluation_observations:
            raise ValueError("walk-forward fold requires evaluation observations")
        train_ids = tuple(
            sorted(item.observation_identity for item in self.training_observations)
        )
        eval_ids = tuple(
            sorted(item.observation_identity for item in self.evaluation_observations)
        )
        if len(set(train_ids)) != len(train_ids):
            raise ValueError("walk-forward training observations must be unique")
        if len(set(eval_ids)) != len(eval_ids):
            raise ValueError("walk-forward evaluation observations must be unique")
        if set(train_ids).intersection(eval_ids):
            raise ValueError(
                "walk-forward training and evaluation observations must not overlap"
            )
        if self.fold_identity != canonical_sha256(_fold_payload(self)):
            raise ValueError("walk-forward fold identity mismatch")


@dataclass(frozen=True, slots=True)
class MLWalkForwardFoldResult:
    result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    model_identity: str
    training_identity: str
    evaluation_identity: str
    automatic_model_selection: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "walk-forward result identity")
        _require_sha256(self.fold_identity, "walk-forward fold identity")
        _require_sha256(self.model_identity, "walk-forward model identity")
        _require_sha256(self.training_identity, "walk-forward training identity")
        _require_sha256(self.evaluation_identity, "walk-forward evaluation identity")
        if self.schema_version != ML_WALK_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported walk-forward result schema")
        if self.engine_version != ML_WALK_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported walk-forward result engine")
        if self.fold_index < 0:
            raise ValueError("walk-forward result index must be non-negative")
        if self.automatic_model_selection:
            raise ValueError("walk-forward cannot automatically select a model")
        if self.calibrated_probability_claim:
            raise ValueError("walk-forward makes no calibrated probability claim")
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("walk-forward research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.result_identity != canonical_sha256(_result_payload(self)):
            raise ValueError("walk-forward result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLWalkForwardManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLWalkForwardSemantic
    dataset_identity: str
    config_identity: str
    fold_identities: tuple[str, ...]
    result_identities: tuple[str, ...]
    automatic_model_selection: bool = False
    aggregate_winner_selection: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.run_identity, "walk-forward run identity")
        _require_sha256(self.dataset_identity, "walk-forward dataset identity")
        _require_sha256(self.config_identity, "walk-forward config identity")
        if self.schema_version != ML_WALK_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported walk-forward manifest schema")
        if self.engine_version != ML_WALK_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported walk-forward manifest engine")
        if self.semantic is not (
            MLWalkForwardSemantic.DESCRIPTIVE_WALK_FORWARD_NOT_PROMOTION
        ):
            raise ValueError("unsupported walk-forward semantic")
        if not MIN_WALK_FORWARD_FOLDS <= len(self.fold_identities) <= (
            MAX_WALK_FORWARD_FOLDS
        ):
            raise ValueError("walk-forward run requires 2..6 folds")
        if len(self.fold_identities) != len(self.result_identities):
            raise ValueError("walk-forward fold/result count mismatch")
        if len(set(self.fold_identities)) != len(self.fold_identities):
            raise ValueError("walk-forward fold identities must be unique")
        if len(set(self.result_identities)) != len(self.result_identities):
            raise ValueError("walk-forward result identities must be unique")
        if (
            self.automatic_model_selection
            or self.aggregate_winner_selection
            or self.calibrated_probability_claim
        ):
            raise ValueError("walk-forward cannot select or calibrate models")
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("walk-forward research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("walk-forward manifest identity mismatch")


def build_ml_walk_forward_fold(
    *,
    fold_index: int,
    training_partition: ResearchPartition,
    evaluation_partition: ResearchPartition,
    training_observations: Sequence[ClusterResearchObservation],
    evaluation_observations: Sequence[ClusterResearchObservation],
    config: MLTrainingConfig | None = None,
) -> MLWalkForwardFold:
    effective_config = config or build_ml_training_config()
    train_rows = tuple(training_observations)
    eval_rows = tuple(evaluation_observations)
    dataset_identity = training_partition.dataset_identity
    payload = {
        "config_identity": effective_config.config_identity,
        "dataset_identity": dataset_identity,
        "engine_version": ML_WALK_FORWARD_ENGINE_VERSION,
        "evaluation_observation_identities": tuple(
            sorted(item.observation_identity for item in eval_rows)
        ),
        "evaluation_partition_identity": evaluation_partition.partition_identity,
        "fold_index": fold_index,
        "schema_version": ML_WALK_FORWARD_SCHEMA_VERSION,
        "training_observation_identities": tuple(
            sorted(item.observation_identity for item in train_rows)
        ),
        "training_partition_identity": training_partition.partition_identity,
    }
    return MLWalkForwardFold(
        fold_identity=canonical_sha256(payload),
        schema_version=ML_WALK_FORWARD_SCHEMA_VERSION,
        engine_version=ML_WALK_FORWARD_ENGINE_VERSION,
        fold_index=fold_index,
        dataset_identity=dataset_identity,
        config_identity=effective_config.config_identity,
        training_partition=training_partition,
        evaluation_partition=evaluation_partition,
        training_observations=train_rows,
        evaluation_observations=eval_rows,
    )


def run_ml_walk_forward(
    features: Sequence[SymbolicFeatureSpec],
    folds: Sequence[MLWalkForwardFold],
    *,
    config: MLTrainingConfig | None = None,
) -> tuple[
    tuple[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation],
        ...,
    ],
    tuple[MLWalkForwardFoldResult, ...],
    MLWalkForwardManifest,
]:
    effective_config = config or build_ml_training_config()
    ordered = tuple(sorted(folds, key=lambda item: item.fold_index))
    _validate_fold_sequence(ordered, effective_config)

    artifacts: list[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation]
    ] = []
    results: list[MLWalkForwardFoldResult] = []
    for fold in ordered:
        model, training_manifest = fit_ml_baseline(
            features,
            fold.training_partition,
            fold.training_observations,
            config=effective_config,
        )
        _, evaluation = evaluate_ml_baseline(
            model,
            fold.evaluation_partition,
            fold.evaluation_observations,
            features,
        )
        result_payload = {
            "automatic_model_selection": False,
            "calibrated_probability_claim": False,
            "engine_version": ML_WALK_FORWARD_ENGINE_VERSION,
            "evaluation_identity": evaluation.evaluation_identity,
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "model_identity": model.model_identity,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
            "schema_version": ML_WALK_FORWARD_SCHEMA_VERSION,
            "training_identity": training_manifest.training_identity,
            "untouched_forward_used": False,
        }
        result = MLWalkForwardFoldResult(
            result_identity=canonical_sha256(result_payload),
            schema_version=ML_WALK_FORWARD_SCHEMA_VERSION,
            engine_version=ML_WALK_FORWARD_ENGINE_VERSION,
            fold_identity=fold.fold_identity,
            fold_index=fold.fold_index,
            model_identity=model.model_identity,
            training_identity=training_manifest.training_identity,
            evaluation_identity=evaluation.evaluation_identity,
        )
        artifacts.append((model, training_manifest, evaluation))
        results.append(result)

    fold_identities = tuple(item.fold_identity for item in ordered)
    result_identities = tuple(item.result_identity for item in results)
    manifest_payload = {
        "aggregate_winner_selection": False,
        "automatic_model_selection": False,
        "calibrated_probability_claim": False,
        "config_identity": effective_config.config_identity,
        "dataset_identity": ordered[0].dataset_identity,
        "engine_version": ML_WALK_FORWARD_ENGINE_VERSION,
        "fold_identities": fold_identities,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "result_identities": result_identities,
        "schema_version": ML_WALK_FORWARD_SCHEMA_VERSION,
        "semantic": (
            MLWalkForwardSemantic.DESCRIPTIVE_WALK_FORWARD_NOT_PROMOTION
        ),
        "untouched_forward_used": False,
    }
    manifest = MLWalkForwardManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_WALK_FORWARD_SCHEMA_VERSION,
        engine_version=ML_WALK_FORWARD_ENGINE_VERSION,
        semantic=MLWalkForwardSemantic.DESCRIPTIVE_WALK_FORWARD_NOT_PROMOTION,
        dataset_identity=ordered[0].dataset_identity,
        config_identity=effective_config.config_identity,
        fold_identities=fold_identities,
        result_identities=result_identities,
    )
    return tuple(artifacts), tuple(results), manifest


def _validate_fold_sequence(
    folds: tuple[MLWalkForwardFold, ...],
    config: MLTrainingConfig,
) -> None:
    if not MIN_WALK_FORWARD_FOLDS <= len(folds) <= MAX_WALK_FORWARD_FOLDS:
        raise ValueError("walk-forward run requires 2..6 folds")
    if tuple(item.fold_index for item in folds) != tuple(range(len(folds))):
        raise ValueError("walk-forward fold indexes must be contiguous from zero")

    dataset_identity = folds[0].dataset_identity
    previous_evaluation_end: int | None = None
    previous_training_end: int | None = None
    evaluation_partition_ids: set[str] = set()

    for fold in folds:
        if fold.dataset_identity != dataset_identity:
            raise ValueError("walk-forward folds must share dataset identity")
        if fold.config_identity != config.config_identity:
            raise ValueError("walk-forward fold config identity mismatch")
        if fold.evaluation_partition.partition_identity in evaluation_partition_ids:
            raise ValueError("walk-forward evaluation partitions must be unique")
        evaluation_partition_ids.add(
            fold.evaluation_partition.partition_identity
        )
        if (
            previous_evaluation_end is not None
            and fold.evaluation_partition.start_ms < previous_evaluation_end
        ):
            raise ValueError(
                "walk-forward evaluation windows must be chronological "
                "and non-overlapping"
            )
        if (
            previous_training_end is not None
            and fold.training_partition.end_ms < previous_training_end
        ):
            raise ValueError(
                "walk-forward training cutoff must not move backward"
            )
        previous_evaluation_end = fold.evaluation_partition.end_ms
        previous_training_end = fold.training_partition.end_ms


def _fold_payload(fold: MLWalkForwardFold) -> dict[str, object]:
    return {
        "config_identity": fold.config_identity,
        "dataset_identity": fold.dataset_identity,
        "engine_version": fold.engine_version,
        "evaluation_observation_identities": tuple(
            sorted(
                item.observation_identity
                for item in fold.evaluation_observations
            )
        ),
        "evaluation_partition_identity": (
            fold.evaluation_partition.partition_identity
        ),
        "fold_index": fold.fold_index,
        "schema_version": fold.schema_version,
        "training_observation_identities": tuple(
            sorted(
                item.observation_identity
                for item in fold.training_observations
            )
        ),
        "training_partition_identity": (
            fold.training_partition.partition_identity
        ),
    }


def _result_payload(result: MLWalkForwardFoldResult) -> dict[str, object]:
    return {
        "automatic_model_selection": result.automatic_model_selection,
        "calibrated_probability_claim": result.calibrated_probability_claim,
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "model_identity": result.model_identity,
        "production_authority": result.production_authority,
        "real_capital": result.real_capital,
        "schema_version": result.schema_version,
        "training_identity": result.training_identity,
        "untouched_forward_used": result.untouched_forward_used,
    }


def _manifest_payload(manifest: MLWalkForwardManifest) -> dict[str, object]:
    return {
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_model_selection": manifest.automatic_model_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "config_identity": manifest.config_identity,
        "dataset_identity": manifest.dataset_identity,
        "engine_version": manifest.engine_version,
        "fold_identities": manifest.fold_identities,
        "production_authority": manifest.production_authority,
        "real_capital": manifest.real_capital,
        "result_identities": manifest.result_identities,
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
