from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.symbolic_rules import (
    SymbolicFeatureSpec,
    SymbolicResearchObservation,
)

ML_ENGINE_VERSION = "alpha-factory-bounded-ml-foundation-v1/1"
ML_SCHEMA_VERSION = "alpha-factory-bounded-ml-schema-v1/1"
ML_MODEL_FAMILY = "deterministic-categorical-additive-net-r-v1"
MAX_ML_FEATURES = 4


class MLEvaluationSemantic(StrEnum):
    DESCRIPTIVE_NET_R_ERROR_NOT_PROBABILITY = (
        "descriptive_net_r_error_not_probability"
    )


class MLSelectionStatus(StrEnum):
    SINGLE_PREDECLARED_BASELINE_NO_AUTOMATIC_SELECTION = (
        "single_predeclared_baseline_no_automatic_selection"
    )


@dataclass(frozen=True, slots=True)
class MLConfig:
    min_cell_support: int = 2
    max_features: int = MAX_ML_FEATURES

    def __post_init__(self) -> None:
        if self.min_cell_support <= 0:
            raise ValueError("ML min_cell_support must be positive")
        if not 1 <= self.max_features <= MAX_ML_FEATURES:
            raise ValueError("ML max_features must be between 1 and 4")

    @property
    def config_identity(self) -> str:
        return canonical_sha256(
            {
                "max_features": self.max_features,
                "min_cell_support": self.min_cell_support,
                "model_family": ML_MODEL_FAMILY,
            }
        )


DEFAULT_ML_CONFIG = MLConfig()


@dataclass(frozen=True, slots=True)
class MLFeatureBinding:
    binding_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    allowed_values: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.binding_identity, "ML feature binding identity")
        _require_sha256(self.feature_identity, "ML feature identity")
        _require_token(self.feature_id, "ML feature id")
        _require_token(self.feature_version, "ML feature version")
        if not self.allowed_values:
            raise ValueError("ML feature requires allowed values")
        if tuple(sorted(set(self.allowed_values))) != self.allowed_values:
            raise ValueError("ML allowed values must be sorted and unique")
        if self.binding_identity != canonical_sha256(_binding_payload(self)):
            raise ValueError("ML feature binding identity mismatch")


@dataclass(frozen=True, slots=True)
class MLCell:
    cell_identity: str
    binding_identity: str
    feature_id: str
    feature_value: str
    support_count: int
    net_r_total: Decimal
    mean_net_r: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.cell_identity, "ML cell identity")
        _require_sha256(self.binding_identity, "ML binding identity")
        _require_token(self.feature_id, "ML cell feature id")
        _require_token(self.feature_value, "ML cell feature value")
        if self.support_count <= 0:
            raise ValueError("ML cell support must be positive")
        if self.mean_net_r != self.net_r_total / Decimal(self.support_count):
            raise ValueError("ML cell mean mismatch")
        if self.cell_identity != canonical_sha256(_cell_payload(self)):
            raise ValueError("ML cell identity mismatch")


@dataclass(frozen=True, slots=True)
class MLModel:
    model_identity: str
    schema_version: str
    engine_version: str
    model_family: str
    config_identity: str
    training_partition_identity: str
    feature_bindings: tuple[MLFeatureBinding, ...]
    cells: tuple[MLCell, ...]
    training_observation_count: int
    training_net_r_total: Decimal
    global_mean_net_r: Decimal
    selection_status: MLSelectionStatus
    automatic_model_selection: bool
    validation_used_in_fit: bool
    out_of_sample_used_in_fit: bool
    untouched_forward_used: bool
    calibrated_probability: bool

    def __post_init__(self) -> None:
        _require_sha256(self.model_identity, "ML model identity")
        _require_sha256(self.config_identity, "ML config identity")
        _require_sha256(
            self.training_partition_identity,
            "ML training partition identity",
        )
        if self.schema_version != ML_SCHEMA_VERSION:
            raise ValueError("unsupported ML schema")
        if self.engine_version != ML_ENGINE_VERSION:
            raise ValueError("unsupported ML engine")
        if self.model_family != ML_MODEL_FAMILY:
            raise ValueError("unsupported ML model family")
        if not 1 <= len(self.feature_bindings) <= MAX_ML_FEATURES:
            raise ValueError("ML model requires 1..4 features")
        feature_ids = tuple(item.feature_id for item in self.feature_bindings)
        if feature_ids != tuple(sorted(set(feature_ids))):
            raise ValueError("ML feature bindings must be canonical")
        cell_keys = tuple(
            (item.feature_id, item.feature_value) for item in self.cells
        )
        if cell_keys != tuple(sorted(set(cell_keys))):
            raise ValueError("ML cells must be canonical and unique")
        if self.training_observation_count <= 0:
            raise ValueError("ML model requires training observations")
        expected_mean = self.training_net_r_total / Decimal(
            self.training_observation_count
        )
        if self.global_mean_net_r != expected_mean:
            raise ValueError("ML global mean mismatch")
        if self.selection_status is not (
            MLSelectionStatus.SINGLE_PREDECLARED_BASELINE_NO_AUTOMATIC_SELECTION
        ):
            raise ValueError("unsupported ML selection status")
        if self.automatic_model_selection:
            raise ValueError("ML v1 cannot automatically select a model")
        if self.validation_used_in_fit or self.out_of_sample_used_in_fit:
            raise ValueError("ML fit must use TRAIN only")
        if self.untouched_forward_used:
            raise ValueError("ML v1 cannot use untouched-forward data")
        if self.calibrated_probability:
            raise ValueError("ML v1 cannot claim calibrated probability")
        if self.model_identity != canonical_sha256(_model_payload(self)):
            raise ValueError("ML model identity mismatch")


@dataclass(frozen=True, slots=True)
class MLPrediction:
    prediction_identity: str
    model_identity: str
    observation_identity: str
    score_net_r: Decimal
    contributor_cell_identities: tuple[str, ...]
    semantic: str = "descriptive_net_r_score_not_probability"

    def __post_init__(self) -> None:
        _require_sha256(self.prediction_identity, "ML prediction identity")
        _require_sha256(self.model_identity, "ML model identity")
        _require_sha256(self.observation_identity, "ML observation identity")
        if tuple(sorted(set(self.contributor_cell_identities))) != (
            self.contributor_cell_identities
        ):
            raise ValueError("ML contributor identities must be canonical")
        for identity in self.contributor_cell_identities:
            _require_sha256(identity, "ML contributor cell identity")
        if self.semantic != "descriptive_net_r_score_not_probability":
            raise ValueError("unsupported ML prediction semantic")
        if self.prediction_identity != canonical_sha256(
            _prediction_payload(self)
        ):
            raise ValueError("ML prediction identity mismatch")


@dataclass(frozen=True, slots=True)
class MLEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    model_identity: str
    partition_identity: str
    partition_role: PartitionRole
    semantic: MLEvaluationSemantic
    observation_count: int
    prediction_identities: tuple[str, ...]
    gross_r_total: Decimal
    explicit_cost_r_total: Decimal
    net_r_total: Decimal
    average_realized_net_r: Decimal
    average_predicted_net_r: Decimal
    mean_absolute_error_r: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_identity, "ML evaluation identity")
        _require_sha256(self.model_identity, "ML model identity")
        _require_sha256(self.partition_identity, "ML partition identity")
        if self.schema_version != ML_SCHEMA_VERSION:
            raise ValueError("unsupported ML evaluation schema")
        if self.engine_version != ML_ENGINE_VERSION:
            raise ValueError("unsupported ML evaluation engine")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "ML evaluation is limited to validation or out-of-sample"
            )
        if self.semantic is not (
            MLEvaluationSemantic.DESCRIPTIVE_NET_R_ERROR_NOT_PROBABILITY
        ):
            raise ValueError("unsupported ML evaluation semantic")
        if self.observation_count <= 0:
            raise ValueError("ML evaluation requires observations")
        if len(self.prediction_identities) != self.observation_count:
            raise ValueError("ML prediction count mismatch")
        if len(set(self.prediction_identities)) != len(
            self.prediction_identities
        ):
            raise ValueError("ML prediction identities must be unique")
        if self.explicit_cost_r_total < 0:
            raise ValueError("ML evaluation costs must be non-negative")
        if self.net_r_total != self.gross_r_total - self.explicit_cost_r_total:
            raise ValueError("ML evaluation net R mismatch")
        expected_realized = self.net_r_total / Decimal(self.observation_count)
        if self.average_realized_net_r != expected_realized:
            raise ValueError("ML realized average mismatch")
        if self.mean_absolute_error_r < 0:
            raise ValueError("ML MAE must be non-negative")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("ML evaluation identity mismatch")


def fit_ml_baseline(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[SymbolicResearchObservation],
    *,
    config: MLConfig = DEFAULT_ML_CONFIG,
) -> MLModel:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("ML fit requires the train partition")
    bindings = _build_bindings(features, config)
    ordered = _validate_observations(
        training_partition,
        observations,
        bindings,
    )
    training_total = sum(
        (item.net_outcome_r for item in ordered),
        start=Decimal(0),
    )
    cells: list[MLCell] = []
    for binding in bindings:
        for value in binding.allowed_values:
            matched = tuple(
                item
                for item in ordered
                if dict(item.feature_values)[binding.feature_id] == value
            )
            if len(matched) < config.min_cell_support:
                continue
            net_total = sum(
                (item.net_outcome_r for item in matched),
                start=Decimal(0),
            )
            payload = {
                "binding_identity": binding.binding_identity,
                "feature_id": binding.feature_id,
                "feature_value": value,
                "mean_net_r": net_total / Decimal(len(matched)),
                "net_r_total": net_total,
                "support_count": len(matched),
            }
            cells.append(
                MLCell(
                    cell_identity=canonical_sha256(payload),
                    binding_identity=binding.binding_identity,
                    feature_id=binding.feature_id,
                    feature_value=value,
                    support_count=len(matched),
                    net_r_total=net_total,
                    mean_net_r=net_total / Decimal(len(matched)),
                )
            )
    ordered_cells = tuple(
        sorted(cells, key=lambda item: (item.feature_id, item.feature_value))
    )
    global_mean = training_total / Decimal(len(ordered))
    payload = {
        "automatic_model_selection": False,
        "calibrated_probability": False,
        "cell_identities": tuple(item.cell_identity for item in ordered_cells),
        "config_identity": config.config_identity,
        "engine_version": ML_ENGINE_VERSION,
        "feature_binding_identities": tuple(
            item.binding_identity for item in bindings
        ),
        "global_mean_net_r": global_mean,
        "model_family": ML_MODEL_FAMILY,
        "out_of_sample_used_in_fit": False,
        "schema_version": ML_SCHEMA_VERSION,
        "selection_status": (
            MLSelectionStatus.SINGLE_PREDECLARED_BASELINE_NO_AUTOMATIC_SELECTION
        ),
        "training_net_r_total": training_total,
        "training_observation_count": len(ordered),
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
        "validation_used_in_fit": False,
    }
    return MLModel(
        model_identity=canonical_sha256(payload),
        schema_version=ML_SCHEMA_VERSION,
        engine_version=ML_ENGINE_VERSION,
        model_family=ML_MODEL_FAMILY,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        feature_bindings=bindings,
        cells=ordered_cells,
        training_observation_count=len(ordered),
        training_net_r_total=training_total,
        global_mean_net_r=global_mean,
        selection_status=(
            MLSelectionStatus.SINGLE_PREDECLARED_BASELINE_NO_AUTOMATIC_SELECTION
        ),
        automatic_model_selection=False,
        validation_used_in_fit=False,
        out_of_sample_used_in_fit=False,
        untouched_forward_used=False,
        calibrated_probability=False,
    )


def predict_ml(
    model: MLModel,
    observation: SymbolicResearchObservation,
) -> MLPrediction:
    values = _validated_values(observation, model.feature_bindings)
    by_key = {
        (item.feature_id, item.feature_value): item for item in model.cells
    }
    contributors = tuple(
        by_key[(binding.feature_id, values[binding.feature_id])]
        for binding in model.feature_bindings
        if (binding.feature_id, values[binding.feature_id]) in by_key
    )
    if contributors:
        score = sum(
            (item.mean_net_r for item in contributors),
            start=Decimal(0),
        ) / Decimal(len(contributors))
    else:
        score = model.global_mean_net_r
    contributor_ids = tuple(
        sorted(item.cell_identity for item in contributors)
    )
    payload = {
        "contributor_cell_identities": contributor_ids,
        "model_identity": model.model_identity,
        "observation_identity": observation.observation_identity,
        "score_net_r": score,
        "semantic": "descriptive_net_r_score_not_probability",
    }
    return MLPrediction(
        prediction_identity=canonical_sha256(payload),
        model_identity=model.model_identity,
        observation_identity=observation.observation_identity,
        score_net_r=score,
        contributor_cell_identities=contributor_ids,
    )


def evaluate_ml(
    model: MLModel,
    partition: ResearchPartition,
    observations: Sequence[SymbolicResearchObservation],
) -> MLEvaluation:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "ML evaluation is limited to validation or out-of-sample"
        )
    ordered = _validate_observations(
        partition,
        observations,
        model.feature_bindings,
    )
    predictions = tuple(predict_ml(model, item) for item in ordered)
    gross_total = sum(
        (item.gross_outcome_r for item in ordered),
        start=Decimal(0),
    )
    cost_total = sum(
        (item.explicit_cost_r for item in ordered),
        start=Decimal(0),
    )
    net_total = sum(
        (item.net_outcome_r for item in ordered),
        start=Decimal(0),
    )
    predicted_total = sum(
        (item.score_net_r for item in predictions),
        start=Decimal(0),
    )
    absolute_error = sum(
        (
            abs(prediction.score_net_r - observation.net_outcome_r)
            for prediction, observation in zip(
                predictions,
                ordered,
                strict=True,
            )
        ),
        start=Decimal(0),
    )
    payload = {
        "average_predicted_net_r": predicted_total / Decimal(len(ordered)),
        "average_realized_net_r": net_total / Decimal(len(ordered)),
        "engine_version": ML_ENGINE_VERSION,
        "explicit_cost_r_total": cost_total,
        "gross_r_total": gross_total,
        "mean_absolute_error_r": absolute_error / Decimal(len(ordered)),
        "model_identity": model.model_identity,
        "net_r_total": net_total,
        "observation_count": len(ordered),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "prediction_identities": tuple(
            item.prediction_identity for item in predictions
        ),
        "schema_version": ML_SCHEMA_VERSION,
        "semantic": MLEvaluationSemantic.DESCRIPTIVE_NET_R_ERROR_NOT_PROBABILITY,
    }
    return MLEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=ML_SCHEMA_VERSION,
        engine_version=ML_ENGINE_VERSION,
        model_identity=model.model_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=MLEvaluationSemantic.DESCRIPTIVE_NET_R_ERROR_NOT_PROBABILITY,
        observation_count=len(ordered),
        prediction_identities=tuple(
            item.prediction_identity for item in predictions
        ),
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_realized_net_r=net_total / Decimal(len(ordered)),
        average_predicted_net_r=predicted_total / Decimal(len(ordered)),
        mean_absolute_error_r=absolute_error / Decimal(len(ordered)),
    )


def _build_bindings(
    features: Sequence[SymbolicFeatureSpec],
    config: MLConfig,
) -> tuple[MLFeatureBinding, ...]:
    ordered = tuple(sorted(features, key=lambda item: item.feature_id))
    if not 1 <= len(ordered) <= config.max_features:
        raise ValueError("ML fit requires 1..max_features feature specs")
    ids = tuple(item.feature_id for item in ordered)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("ML features must have unique ids")
    identities = tuple(item.feature_identity for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("ML features must have unique identities")
    bindings: list[MLFeatureBinding] = []
    for feature in ordered:
        payload = {
            "allowed_values": feature.allowed_values,
            "feature_id": feature.feature_id,
            "feature_identity": feature.feature_identity,
            "feature_version": feature.feature_version,
        }
        bindings.append(
            MLFeatureBinding(
                binding_identity=canonical_sha256(payload),
                feature_identity=feature.feature_identity,
                feature_id=feature.feature_id,
                feature_version=feature.feature_version,
                allowed_values=feature.allowed_values,
            )
        )
    return tuple(bindings)


def _validate_observations(
    partition: ResearchPartition,
    observations: Sequence[SymbolicResearchObservation],
    bindings: tuple[MLFeatureBinding, ...],
) -> tuple[SymbolicResearchObservation, ...]:
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.decision_as_of_ms,
                item.source_evidence_identity,
                item.observation_identity,
            ),
        )
    )
    if not ordered:
        raise ValueError("ML requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError("ML observations must cover the partition exactly")
    expected_sources = set(partition.evidence_identities)
    seen_sources: set[str] = set()
    seen_records: set[str] = set()
    for item in ordered:
        if item.partition_identity != partition.partition_identity:
            raise ValueError("ML observation belongs to another partition")
        if not partition.start_ms <= item.decision_as_of_ms < partition.end_ms:
            raise ValueError("ML observation decision time is outside partition")
        if item.source_evidence_identity not in expected_sources:
            raise ValueError("ML observation source is outside partition")
        if item.source_evidence_identity in seen_sources:
            raise ValueError("duplicate source evidence in ML observations")
        if item.observation_identity in seen_records:
            raise ValueError("duplicate ML observation identity")
        _validated_values(item, bindings)
        seen_sources.add(item.source_evidence_identity)
        seen_records.add(item.observation_identity)
    if seen_sources != expected_sources:
        raise ValueError("ML observations do not cover exact partition evidence")
    return ordered


def _validated_values(
    observation: SymbolicResearchObservation,
    bindings: tuple[MLFeatureBinding, ...],
) -> dict[str, str]:
    values = dict(observation.feature_values)
    required = {item.feature_id for item in bindings}
    if set(values) != required:
        raise ValueError("ML observation feature set mismatch")
    for binding in bindings:
        if values[binding.feature_id] not in binding.allowed_values:
            raise ValueError("ML observation has unsupported feature value")
    return values


def _binding_payload(binding: MLFeatureBinding) -> dict[str, object]:
    return {
        "allowed_values": binding.allowed_values,
        "feature_id": binding.feature_id,
        "feature_identity": binding.feature_identity,
        "feature_version": binding.feature_version,
    }


def _cell_payload(cell: MLCell) -> dict[str, object]:
    return {
        "binding_identity": cell.binding_identity,
        "feature_id": cell.feature_id,
        "feature_value": cell.feature_value,
        "mean_net_r": cell.mean_net_r,
        "net_r_total": cell.net_r_total,
        "support_count": cell.support_count,
    }


def _model_payload(model: MLModel) -> dict[str, object]:
    return {
        "automatic_model_selection": model.automatic_model_selection,
        "calibrated_probability": model.calibrated_probability,
        "cell_identities": tuple(item.cell_identity for item in model.cells),
        "config_identity": model.config_identity,
        "engine_version": model.engine_version,
        "feature_binding_identities": tuple(
            item.binding_identity for item in model.feature_bindings
        ),
        "global_mean_net_r": model.global_mean_net_r,
        "model_family": model.model_family,
        "out_of_sample_used_in_fit": model.out_of_sample_used_in_fit,
        "schema_version": model.schema_version,
        "selection_status": model.selection_status,
        "training_net_r_total": model.training_net_r_total,
        "training_observation_count": model.training_observation_count,
        "training_partition_identity": model.training_partition_identity,
        "untouched_forward_used": model.untouched_forward_used,
        "validation_used_in_fit": model.validation_used_in_fit,
    }


def _prediction_payload(prediction: MLPrediction) -> dict[str, object]:
    return {
        "contributor_cell_identities": prediction.contributor_cell_identities,
        "model_identity": prediction.model_identity,
        "observation_identity": prediction.observation_identity,
        "score_net_r": prediction.score_net_r,
        "semantic": prediction.semantic,
    }


def _evaluation_payload(evaluation: MLEvaluation) -> dict[str, object]:
    return {
        "average_predicted_net_r": evaluation.average_predicted_net_r,
        "average_realized_net_r": evaluation.average_realized_net_r,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "gross_r_total": evaluation.gross_r_total,
        "mean_absolute_error_r": evaluation.mean_absolute_error_r,
        "model_identity": evaluation.model_identity,
        "net_r_total": evaluation.net_r_total,
        "observation_count": evaluation.observation_count,
        "partition_identity": evaluation.partition_identity,
        "partition_role": evaluation.partition_role,
        "prediction_identities": evaluation.prediction_identities,
        "schema_version": evaluation.schema_version,
        "semantic": evaluation.semantic,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be SHA256")


def _require_token(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty trimmed token")
    if any(character.isspace() for character in value):
        raise ValueError(f"{label} cannot contain whitespace")
