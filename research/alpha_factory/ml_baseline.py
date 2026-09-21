from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import ClusterResearchObservation
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_BASELINE_ENGINE_VERSION = "alpha-factory-bounded-ml-baseline-v1/1"
ML_BASELINE_SCHEMA_VERSION = "alpha-factory-bounded-ml-schema-v1/1"
MAX_ML_FEATURES = 6
MAX_VALUES_PER_FEATURE = 8
POSITIVE_LABEL_THRESHOLD_R = Decimal(0)
REAL_CAPITAL = 0


class MLModelFamily(StrEnum):
    CATEGORICAL_COUNT_BASELINE = "categorical_count_baseline"


class MLEvaluationSemantic(StrEnum):
    DESCRIPTIVE_CLASSIFICATION_NET_R_NOT_PROBABILITY = (
        "descriptive_classification_net_r_not_probability"
    )


@dataclass(frozen=True, slots=True)
class MLTrainingConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    model_family: MLModelFamily
    max_features: int
    positive_label_threshold_r: Decimal
    automatic_hyperparameter_selection: bool = False
    model_search_performed: bool = False
    calibrated_probability_claim: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "ML training config identity")
        if self.schema_version != ML_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported ML training config schema")
        if self.engine_version != ML_BASELINE_ENGINE_VERSION:
            raise ValueError("unsupported ML baseline engine")
        if self.model_family is not MLModelFamily.CATEGORICAL_COUNT_BASELINE:
            raise ValueError("bounded ML v1 permits one baseline family only")
        if self.max_features != MAX_ML_FEATURES:
            raise ValueError("bounded ML v1 max_features is fixed")
        if self.positive_label_threshold_r != POSITIVE_LABEL_THRESHOLD_R:
            raise ValueError("bounded ML v1 label threshold is fixed")
        if self.automatic_hyperparameter_selection:
            raise ValueError("automatic hyperparameter selection is closed")
        if self.model_search_performed:
            raise ValueError("model search is closed in bounded ML v1")
        if self.calibrated_probability_claim:
            raise ValueError("bounded ML v1 makes no calibrated probability claim")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("ML training config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLCategoryCount:
    count_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    value: str
    positive_count: int
    non_positive_count: int

    def __post_init__(self) -> None:
        _require_sha256(self.count_identity, "ML category count identity")
        _require_sha256(self.feature_identity, "ML feature identity")
        _require_token(self.feature_id, "ML feature id")
        _require_token(self.feature_version, "ML feature version")
        _require_token(self.value, "ML feature value")
        if self.positive_count < 0 or self.non_positive_count < 0:
            raise ValueError("ML category counts must be non-negative")
        if self.positive_count + self.non_positive_count <= 0:
            raise ValueError("ML category count requires observed support")
        if self.count_identity != canonical_sha256(_count_payload(self)):
            raise ValueError("ML category count identity mismatch")


@dataclass(frozen=True, slots=True)
class MLBaselineModel:
    model_identity: str
    schema_version: str
    engine_version: str
    model_family: MLModelFamily
    config_identity: str
    training_partition_identity: str
    training_feature_set_identity: str
    feature_identities: tuple[str, ...]
    positive_count: int
    non_positive_count: int
    category_counts: tuple[MLCategoryCount, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.model_identity, "ML model identity")
        _require_sha256(self.config_identity, "ML config identity")
        _require_sha256(
            self.training_partition_identity,
            "ML training partition identity",
        )
        _require_sha256(
            self.training_feature_set_identity,
            "ML training feature-set identity",
        )
        if self.schema_version != ML_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported ML model schema")
        if self.engine_version != ML_BASELINE_ENGINE_VERSION:
            raise ValueError("unsupported ML model engine")
        if self.model_family is not MLModelFamily.CATEGORICAL_COUNT_BASELINE:
            raise ValueError("unsupported ML baseline family")
        if self.positive_count < 0 or self.non_positive_count < 0:
            raise ValueError("ML class counts must be non-negative")
        if self.positive_count + self.non_positive_count <= 0:
            raise ValueError("ML model requires training support")
        if not 1 <= len(self.feature_identities) <= MAX_ML_FEATURES:
            raise ValueError("ML model requires 1..6 feature identities")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError("ML feature identities must be sorted and unique")
        keys = tuple(
            (item.feature_id, item.feature_version, item.value)
            for item in self.category_counts
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("ML category counts must be canonically ordered")
        if self.model_identity != canonical_sha256(_model_payload(self)):
            raise ValueError("ML model identity mismatch")


@dataclass(frozen=True, slots=True)
class MLTrainingManifest:
    training_identity: str
    schema_version: str
    engine_version: str
    config_identity: str
    model_identity: str
    training_partition_identity: str
    training_observation_identities: tuple[str, ...]
    validation_used_in_fit: bool = False
    out_of_sample_used_in_fit: bool = False
    untouched_forward_used: bool = False
    automatic_hyperparameter_selection: bool = False
    model_search_performed: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.training_identity, "ML training identity")
        _require_sha256(self.config_identity, "ML config identity")
        _require_sha256(self.model_identity, "ML model identity")
        _require_sha256(
            self.training_partition_identity,
            "ML training partition identity",
        )
        if self.schema_version != ML_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported ML training manifest schema")
        if self.engine_version != ML_BASELINE_ENGINE_VERSION:
            raise ValueError("unsupported ML training manifest engine")
        if not self.training_observation_identities:
            raise ValueError("ML training manifest requires observations")
        if tuple(sorted(set(self.training_observation_identities))) != (
            self.training_observation_identities
        ):
            raise ValueError(
                "ML training observation identities must be sorted and unique"
            )
        if (
            self.validation_used_in_fit
            or self.out_of_sample_used_in_fit
            or self.untouched_forward_used
        ):
            raise ValueError("bounded ML v1 fit is TRAIN-only")
        if self.automatic_hyperparameter_selection or self.model_search_performed:
            raise ValueError("bounded ML v1 cannot select or search models")
        if self.production_authority:
            raise ValueError("bounded ML research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.training_identity != canonical_sha256(
            _training_manifest_payload(self)
        ):
            raise ValueError("ML training manifest identity mismatch")


@dataclass(frozen=True, slots=True)
class MLPrediction:
    prediction_identity: str
    schema_version: str
    engine_version: str
    model_identity: str
    observation_identity: str
    score: int
    predicted_positive: bool

    def __post_init__(self) -> None:
        _require_sha256(self.prediction_identity, "ML prediction identity")
        _require_sha256(self.model_identity, "ML prediction model identity")
        _require_sha256(
            self.observation_identity,
            "ML prediction observation identity",
        )
        if self.schema_version != ML_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported ML prediction schema")
        if self.engine_version != ML_BASELINE_ENGINE_VERSION:
            raise ValueError("unsupported ML prediction engine")
        if self.predicted_positive != (self.score > 0):
            raise ValueError("ML prediction label must match deterministic score")
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
    positive_prediction_count: int
    correct_direction_count: int
    prediction_identities: tuple[str, ...]
    selected_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_identity, "ML evaluation identity")
        _require_sha256(self.model_identity, "ML evaluation model identity")
        _require_sha256(
            self.partition_identity,
            "ML evaluation partition identity",
        )
        if self.schema_version != ML_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported ML evaluation schema")
        if self.engine_version != ML_BASELINE_ENGINE_VERSION:
            raise ValueError("unsupported ML evaluation engine")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "ML evaluation is limited to validation or out-of-sample"
            )
        if self.semantic is not (
            MLEvaluationSemantic
            .DESCRIPTIVE_CLASSIFICATION_NET_R_NOT_PROBABILITY
        ):
            raise ValueError("unsupported ML evaluation semantic")
        if self.observation_count <= 0:
            raise ValueError("ML evaluation requires observations")
        if not 0 <= self.positive_prediction_count <= self.observation_count:
            raise ValueError("ML positive prediction count is invalid")
        if not 0 <= self.correct_direction_count <= self.observation_count:
            raise ValueError("ML correct direction count is invalid")
        if len(self.prediction_identities) != self.observation_count:
            raise ValueError("ML evaluation must bind every prediction")
        if tuple(sorted(set(self.prediction_identities))) != (
            self.prediction_identities
        ):
            raise ValueError("ML prediction identities must be sorted and unique")
        if len(self.selected_observation_identities) != (
            self.positive_prediction_count
        ):
            raise ValueError("ML selected observation count mismatch")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "ML selected observation identities must be sorted and unique"
            )
        metrics = (
            self.gross_r_total,
            self.explicit_cost_r_total,
            self.net_r_total,
            self.average_net_r,
        )
        if self.positive_prediction_count == 0:
            if any(value is not None for value in metrics):
                raise ValueError(
                    "ML evaluation with no positive predictions has no R metrics"
                )
        else:
            if any(value is None for value in metrics):
                raise ValueError(
                    "ML positive predictions require explicit R metrics"
                )
            if (
                self.explicit_cost_r_total is not None
                and self.explicit_cost_r_total < 0
            ):
                raise ValueError("ML evaluation costs must be non-negative")
            if (
                self.gross_r_total is not None
                and self.explicit_cost_r_total is not None
                and self.net_r_total
                != self.gross_r_total - self.explicit_cost_r_total
            ):
                raise ValueError("ML evaluation net R accounting mismatch")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("ML evaluation identity mismatch")


def build_ml_training_config() -> MLTrainingConfig:
    payload = {
        "automatic_hyperparameter_selection": False,
        "calibrated_probability_claim": False,
        "engine_version": ML_BASELINE_ENGINE_VERSION,
        "max_features": MAX_ML_FEATURES,
        "model_family": MLModelFamily.CATEGORICAL_COUNT_BASELINE,
        "model_search_performed": False,
        "positive_label_threshold_r": POSITIVE_LABEL_THRESHOLD_R,
        "schema_version": ML_BASELINE_SCHEMA_VERSION,
    }
    return MLTrainingConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_BASELINE_SCHEMA_VERSION,
        engine_version=ML_BASELINE_ENGINE_VERSION,
        model_family=MLModelFamily.CATEGORICAL_COUNT_BASELINE,
        max_features=MAX_ML_FEATURES,
        positive_label_threshold_r=POSITIVE_LABEL_THRESHOLD_R,
    )


DEFAULT_ML_TRAINING_CONFIG = build_ml_training_config()


def fit_ml_baseline(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    *,
    config: MLTrainingConfig = DEFAULT_ML_TRAINING_CONFIG,
) -> tuple[MLBaselineModel, MLTrainingManifest]:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("ML fitting requires the train partition")

    ordered_features = _validate_feature_specs(features)
    ordered_observations = _validate_observation_partition(
        training_partition,
        observations,
        ordered_features,
    )
    if any(
        item.outcome_available_at_ms > training_partition.end_ms
        for item in ordered_observations
    ):
        raise ValueError(
            "ML training outcome must be available by train partition end"
        )

    training_feature_set_identity = canonical_sha256(
        {
            "feature_identities": tuple(
                item.feature_identity for item in ordered_features
            ),
            "feature_snapshot_identities": tuple(
                sorted(
                    item.feature_snapshot_identity
                    for item in ordered_observations
                )
            ),
            "training_partition_identity": (
                training_partition.partition_identity
            ),
        }
    )

    positive_count = sum(
        item.net_outcome_r > POSITIVE_LABEL_THRESHOLD_R
        for item in ordered_observations
    )
    non_positive_count = len(ordered_observations) - positive_count

    counts: dict[tuple[str, str, str, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )
    for observation in ordered_observations:
        positive = observation.net_outcome_r > POSITIVE_LABEL_THRESHOLD_R
        for reading in observation.feature_readings:
            key = (
                reading.feature_identity,
                reading.feature_id,
                reading.feature_version,
                reading.value,
            )
            counts[key][0 if positive else 1] += 1

    category_counts = tuple(
        _build_category_count(
            feature_identity=key[0],
            feature_id=key[1],
            feature_version=key[2],
            value=key[3],
            positive_count=value[0],
            non_positive_count=value[1],
        )
        for key, value in sorted(
            counts.items(),
            key=lambda item: (item[0][1], item[0][2], item[0][3]),
        )
    )

    feature_identities = tuple(
        sorted(item.feature_identity for item in ordered_features)
    )
    model_payload = {
        "category_count_identities": tuple(
            item.count_identity for item in category_counts
        ),
        "config_identity": config.config_identity,
        "engine_version": ML_BASELINE_ENGINE_VERSION,
        "feature_identities": feature_identities,
        "model_family": MLModelFamily.CATEGORICAL_COUNT_BASELINE,
        "non_positive_count": non_positive_count,
        "positive_count": positive_count,
        "schema_version": ML_BASELINE_SCHEMA_VERSION,
        "training_feature_set_identity": training_feature_set_identity,
        "training_partition_identity": training_partition.partition_identity,
    }
    model = MLBaselineModel(
        model_identity=canonical_sha256(model_payload),
        schema_version=ML_BASELINE_SCHEMA_VERSION,
        engine_version=ML_BASELINE_ENGINE_VERSION,
        model_family=MLModelFamily.CATEGORICAL_COUNT_BASELINE,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        training_feature_set_identity=training_feature_set_identity,
        feature_identities=feature_identities,
        positive_count=positive_count,
        non_positive_count=non_positive_count,
        category_counts=category_counts,
    )

    training_observation_identities = tuple(
        sorted(item.observation_identity for item in ordered_observations)
    )
    manifest_payload = {
        "automatic_hyperparameter_selection": False,
        "config_identity": config.config_identity,
        "engine_version": ML_BASELINE_ENGINE_VERSION,
        "model_identity": model.model_identity,
        "model_search_performed": False,
        "out_of_sample_used_in_fit": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_BASELINE_SCHEMA_VERSION,
        "training_observation_identities": training_observation_identities,
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
        "validation_used_in_fit": False,
    }
    manifest = MLTrainingManifest(
        training_identity=canonical_sha256(manifest_payload),
        schema_version=ML_BASELINE_SCHEMA_VERSION,
        engine_version=ML_BASELINE_ENGINE_VERSION,
        config_identity=config.config_identity,
        model_identity=model.model_identity,
        training_partition_identity=training_partition.partition_identity,
        training_observation_identities=training_observation_identities,
    )
    return model, manifest


def evaluate_ml_baseline(
    model: MLBaselineModel,
    partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    features: Sequence[SymbolicFeatureSpec],
) -> tuple[tuple[MLPrediction, ...], MLEvaluation]:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "ML evaluation is limited to validation or out-of-sample"
        )

    ordered_features = _validate_feature_specs(features)
    _validate_model_features(model, ordered_features)
    ordered_observations = _validate_observation_partition(
        partition,
        observations,
        ordered_features,
    )

    predictions = tuple(
        _predict(model, observation) for observation in ordered_observations
    )
    selected = tuple(
        observation
        for observation, prediction in zip(
            ordered_observations,
            predictions,
            strict=True,
        )
        if prediction.predicted_positive
    )
    correct_direction_count = sum(
        prediction.predicted_positive
        == (observation.net_outcome_r > POSITIVE_LABEL_THRESHOLD_R)
        for observation, prediction in zip(
            ordered_observations,
            predictions,
            strict=True,
        )
    )

    if selected:
        gross_total = sum(
            (item.gross_outcome_r for item in selected),
            start=Decimal(0),
        )
        cost_total = sum(
            (item.explicit_cost_r for item in selected),
            start=Decimal(0),
        )
        net_total = sum(
            (item.net_outcome_r for item in selected),
            start=Decimal(0),
        )
        average_net = net_total / Decimal(len(selected))
    else:
        gross_total = None
        cost_total = None
        net_total = None
        average_net = None

    prediction_identities = tuple(
        sorted(item.prediction_identity for item in predictions)
    )
    selected_ids = tuple(
        sorted(item.observation_identity for item in selected)
    )
    payload = {
        "average_net_r": average_net,
        "correct_direction_count": correct_direction_count,
        "engine_version": ML_BASELINE_ENGINE_VERSION,
        "explicit_cost_r_total": cost_total,
        "gross_r_total": gross_total,
        "model_identity": model.model_identity,
        "net_r_total": net_total,
        "observation_count": len(ordered_observations),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "positive_prediction_count": len(selected),
        "prediction_identities": prediction_identities,
        "schema_version": ML_BASELINE_SCHEMA_VERSION,
        "selected_observation_identities": selected_ids,
        "semantic": (
            MLEvaluationSemantic
            .DESCRIPTIVE_CLASSIFICATION_NET_R_NOT_PROBABILITY
        ),
    }
    evaluation = MLEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=ML_BASELINE_SCHEMA_VERSION,
        engine_version=ML_BASELINE_ENGINE_VERSION,
        model_identity=model.model_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=(
            MLEvaluationSemantic
            .DESCRIPTIVE_CLASSIFICATION_NET_R_NOT_PROBABILITY
        ),
        observation_count=len(ordered_observations),
        positive_prediction_count=len(selected),
        correct_direction_count=correct_direction_count,
        prediction_identities=prediction_identities,
        selected_observation_identities=selected_ids,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
    )
    return predictions, evaluation


def _predict(
    model: MLBaselineModel,
    observation: ClusterResearchObservation,
) -> MLPrediction:
    score = model.positive_count - model.non_positive_count
    count_by_key = {
        (item.feature_id, item.feature_version, item.value): item
        for item in model.category_counts
    }
    for reading in observation.feature_readings:
        category = count_by_key.get(
            (reading.feature_id, reading.feature_version, reading.value)
        )
        if category is not None:
            score += category.positive_count - category.non_positive_count

    payload = {
        "engine_version": ML_BASELINE_ENGINE_VERSION,
        "model_identity": model.model_identity,
        "observation_identity": observation.observation_identity,
        "predicted_positive": score > 0,
        "schema_version": ML_BASELINE_SCHEMA_VERSION,
        "score": score,
    }
    return MLPrediction(
        prediction_identity=canonical_sha256(payload),
        schema_version=ML_BASELINE_SCHEMA_VERSION,
        engine_version=ML_BASELINE_ENGINE_VERSION,
        model_identity=model.model_identity,
        observation_identity=observation.observation_identity,
        score=score,
        predicted_positive=score > 0,
    )


def _build_category_count(
    *,
    feature_identity: str,
    feature_id: str,
    feature_version: str,
    value: str,
    positive_count: int,
    non_positive_count: int,
) -> MLCategoryCount:
    payload = {
        "feature_id": feature_id,
        "feature_identity": feature_identity,
        "feature_version": feature_version,
        "non_positive_count": non_positive_count,
        "positive_count": positive_count,
        "value": value,
    }
    return MLCategoryCount(
        count_identity=canonical_sha256(payload),
        feature_identity=feature_identity,
        feature_id=feature_id,
        feature_version=feature_version,
        value=value,
        positive_count=positive_count,
        non_positive_count=non_positive_count,
    )


def _validate_feature_specs(
    features: Sequence[SymbolicFeatureSpec],
) -> tuple[SymbolicFeatureSpec, ...]:
    ordered = tuple(sorted(features, key=lambda item: item.feature_id))
    if not 1 <= len(ordered) <= MAX_ML_FEATURES:
        raise ValueError("bounded ML v1 requires 1..6 features")
    ids = tuple(item.feature_id for item in ordered)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("bounded ML v1 requires unique feature ids")
    identities = tuple(item.feature_identity for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("bounded ML v1 requires unique feature identities")
    if any(len(item.allowed_values) > MAX_VALUES_PER_FEATURE for item in ordered):
        raise ValueError("bounded ML feature cardinality exceeds 8 values")
    return ordered


def _validate_model_features(
    model: MLBaselineModel,
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    identities = tuple(sorted(item.feature_identity for item in features))
    if identities != model.feature_identities:
        raise ValueError("ML model feature identity mismatch")


def _validate_observation_partition(
    partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    features: tuple[SymbolicFeatureSpec, ...],
) -> tuple[ClusterResearchObservation, ...]:
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
        raise ValueError("ML research requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError("ML observations must cover the partition exactly")

    feature_by_id = {item.feature_id: item for item in features}
    expected_feature_ids = tuple(item.feature_id for item in features)
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    observed_records: set[str] = set()

    for observation in ordered:
        if observation.partition_identity != partition.partition_identity:
            raise ValueError("ML observation does not belong to partition")
        if not partition.start_ms <= observation.decision_as_of_ms < partition.end_ms:
            raise ValueError("ML observation decision time is outside partition")
        if observation.source_evidence_identity not in partition_sources:
            raise ValueError("ML observation source evidence is outside partition")
        if observation.source_evidence_identity in observed_sources:
            raise ValueError("duplicate ML source evidence")
        if observation.observation_identity in observed_records:
            raise ValueError("duplicate ML observation identity")
        observed_sources.add(observation.source_evidence_identity)
        observed_records.add(observation.observation_identity)

        reading_ids = tuple(item.feature_id for item in observation.feature_readings)
        if reading_ids != expected_feature_ids:
            raise ValueError("ML observation feature coverage mismatch")
        for reading in observation.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("ML observation feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("ML observation feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError("ML observation feature value outside contract")

    if observed_sources != partition_sources:
        raise ValueError("ML observations must cover the partition exactly")
    return ordered


def _config_payload(config: MLTrainingConfig) -> dict[str, object]:
    return {
        "automatic_hyperparameter_selection": (
            config.automatic_hyperparameter_selection
        ),
        "calibrated_probability_claim": config.calibrated_probability_claim,
        "engine_version": config.engine_version,
        "max_features": config.max_features,
        "model_family": config.model_family,
        "model_search_performed": config.model_search_performed,
        "positive_label_threshold_r": config.positive_label_threshold_r,
        "schema_version": config.schema_version,
    }


def _count_payload(count: MLCategoryCount) -> dict[str, object]:
    return {
        "feature_id": count.feature_id,
        "feature_identity": count.feature_identity,
        "feature_version": count.feature_version,
        "non_positive_count": count.non_positive_count,
        "positive_count": count.positive_count,
        "value": count.value,
    }


def _model_payload(model: MLBaselineModel) -> dict[str, object]:
    return {
        "category_count_identities": tuple(
            item.count_identity for item in model.category_counts
        ),
        "config_identity": model.config_identity,
        "engine_version": model.engine_version,
        "feature_identities": model.feature_identities,
        "model_family": model.model_family,
        "non_positive_count": model.non_positive_count,
        "positive_count": model.positive_count,
        "schema_version": model.schema_version,
        "training_feature_set_identity": model.training_feature_set_identity,
        "training_partition_identity": model.training_partition_identity,
    }


def _training_manifest_payload(
    manifest: MLTrainingManifest,
) -> dict[str, object]:
    return {
        "automatic_hyperparameter_selection": (
            manifest.automatic_hyperparameter_selection
        ),
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "model_identity": manifest.model_identity,
        "model_search_performed": manifest.model_search_performed,
        "out_of_sample_used_in_fit": manifest.out_of_sample_used_in_fit,
        "production_authority": manifest.production_authority,
        "real_capital": manifest.real_capital,
        "schema_version": manifest.schema_version,
        "training_observation_identities": (
            manifest.training_observation_identities
        ),
        "training_partition_identity": manifest.training_partition_identity,
        "untouched_forward_used": manifest.untouched_forward_used,
        "validation_used_in_fit": manifest.validation_used_in_fit,
    }


def _prediction_payload(prediction: MLPrediction) -> dict[str, object]:
    return {
        "engine_version": prediction.engine_version,
        "model_identity": prediction.model_identity,
        "observation_identity": prediction.observation_identity,
        "predicted_positive": prediction.predicted_positive,
        "schema_version": prediction.schema_version,
        "score": prediction.score,
    }


def _evaluation_payload(evaluation: MLEvaluation) -> dict[str, object]:
    return {
        "average_net_r": evaluation.average_net_r,
        "correct_direction_count": evaluation.correct_direction_count,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "gross_r_total": evaluation.gross_r_total,
        "model_identity": evaluation.model_identity,
        "net_r_total": evaluation.net_r_total,
        "observation_count": evaluation.observation_count,
        "partition_identity": evaluation.partition_identity,
        "partition_role": evaluation.partition_role,
        "positive_prediction_count": evaluation.positive_prediction_count,
        "prediction_identities": evaluation.prediction_identities,
        "schema_version": evaluation.schema_version,
        "selected_observation_identities": (
            evaluation.selected_observation_identities
        ),
        "semantic": evaluation.semantic,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256 hex") from exc


def _require_token(value: str, label: str) -> None:
    if not value or value.strip() != value or any(ch.isspace() for ch in value):
        raise ValueError(f"{label} must be a non-empty token")