"""Deterministic two-family ML research expansion with no automatic selection."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import ClusterResearchObservation
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.ml_baseline import (
    MLBaselineModel,
    MLEvaluation,
    MLTrainingManifest,
    evaluate_ml_baseline,
)
from research.alpha_factory.ml_walk_forward import MLWalkForwardFold
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_FAMILY_EXPANSION_ENGINE_VERSION = "alpha-factory-ml-family-expansion-v1/1"
ML_FAMILY_EXPANSION_SCHEMA_VERSION = "alpha-factory-ml-family-schema-v1/1"
MIN_FAMILY_FEATURES = 1
MAX_FAMILY_FEATURES = 6
REAL_CAPITAL = 0


class MLExpandedFamily(StrEnum):
    CATEGORICAL_COUNT_REFERENCE = "categorical_count_reference"
    CATEGORICAL_SIGN_VOTE = "categorical_sign_vote"


FIXED_FAMILY_SET = (
    MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
    MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
)


class MLFamilyExpansionSemantic(StrEnum):
    DESCRIPTIVE_MULTI_FAMILY_NOT_SELECTION = (
        "descriptive_multi_family_not_selection"
    )


class MLFamilyMultipleTestingStatus(StrEnum):
    BOUNDED_TWO_FAMILIES_NO_AUTOMATIC_SELECTION = (
        "bounded_two_families_no_automatic_selection"
    )


@dataclass(frozen=True, slots=True)
class MLFamilyExpansionConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    family_set: tuple[MLExpandedFamily, ...]
    max_features: int
    automatic_family_selection: bool = False
    automatic_hyperparameter_selection: bool = False
    uncontrolled_model_search: bool = False
    calibrated_probability_claim: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "family config identity")
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family expansion config schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family expansion config engine")
        if self.family_set != FIXED_FAMILY_SET:
            raise ValueError("family expansion v1 family set is fixed")
        if self.max_features != MAX_FAMILY_FEATURES:
            raise ValueError("family expansion v1 max_features is fixed")
        if self.automatic_family_selection:
            raise ValueError("automatic family selection is closed")
        if self.automatic_hyperparameter_selection:
            raise ValueError("automatic hyperparameter selection is closed")
        if self.uncontrolled_model_search:
            raise ValueError("uncontrolled model search is closed")
        if self.calibrated_probability_claim:
            raise ValueError("family expansion makes no calibrated probability claim")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("family expansion config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyCategoryVote:
    vote_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    value: str
    positive_count: int
    non_positive_count: int
    vote: int

    def __post_init__(self) -> None:
        _require_sha256(self.vote_identity, "family category vote identity")
        _require_sha256(self.feature_identity, "family feature identity")
        _require_token(self.feature_id, "family feature id")
        _require_token(self.feature_version, "family feature version")
        _require_token(self.value, "family feature value")
        if self.positive_count < 0 or self.non_positive_count < 0:
            raise ValueError("family category counts must be non-negative")
        if self.positive_count + self.non_positive_count <= 0:
            raise ValueError("family category vote requires observed support")
        if self.vote not in {-1, 0, 1}:
            raise ValueError("family category vote must be -1, 0 or 1")
        if self.vote != _sign(self.positive_count - self.non_positive_count):
            raise ValueError("family category vote/count mismatch")
        if self.vote_identity != canonical_sha256(_vote_payload(self)):
            raise ValueError("family category vote identity mismatch")


@dataclass(frozen=True, slots=True)
class MLSignVoteModel:
    model_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    config_identity: str
    training_partition_identity: str
    training_feature_set_identity: str
    feature_identities: tuple[str, ...]
    positive_count: int
    non_positive_count: int
    prior_vote: int
    category_votes: tuple[MLFamilyCategoryVote, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.model_identity, "family model identity")
        _require_sha256(self.config_identity, "family config identity")
        _require_sha256(
            self.training_partition_identity,
            "family training partition identity",
        )
        _require_sha256(
            self.training_feature_set_identity,
            "family training feature-set identity",
        )
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family model schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family model engine")
        if self.family is not MLExpandedFamily.CATEGORICAL_SIGN_VOTE:
            raise ValueError("sign-vote model family mismatch")
        if self.positive_count < 0 or self.non_positive_count < 0:
            raise ValueError("family class counts must be non-negative")
        if self.positive_count + self.non_positive_count <= 0:
            raise ValueError("family model requires training support")
        if self.prior_vote != _sign(self.positive_count - self.non_positive_count):
            raise ValueError("family prior vote/count mismatch")
        if not MIN_FAMILY_FEATURES <= len(self.feature_identities) <= (
            MAX_FAMILY_FEATURES
        ):
            raise ValueError("family model requires 1..6 features")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError("family feature identities must be sorted and unique")
        keys = tuple(
            (item.feature_id, item.feature_version, item.value)
            for item in self.category_votes
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("family category votes must be canonically ordered")
        if self.model_identity != canonical_sha256(_model_payload(self)):
            raise ValueError("family model identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyTrainingManifest:
    training_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    config_identity: str
    model_identity: str
    training_partition_identity: str
    training_observation_identities: tuple[str, ...]
    validation_used_in_fit: bool = False
    out_of_sample_used_in_fit: bool = False
    untouched_forward_used: bool = False
    automatic_family_selection: bool = False
    automatic_hyperparameter_selection: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.training_identity, "family training identity")
        _require_sha256(self.config_identity, "family config identity")
        _require_sha256(self.model_identity, "family model identity")
        _require_sha256(
            self.training_partition_identity,
            "family training partition identity",
        )
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family training schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family training engine")
        if self.family is not MLExpandedFamily.CATEGORICAL_SIGN_VOTE:
            raise ValueError("unsupported family training target")
        if not self.training_observation_identities:
            raise ValueError("family training requires observations")
        if tuple(sorted(set(self.training_observation_identities))) != (
            self.training_observation_identities
        ):
            raise ValueError(
                "family training observations must be sorted and unique"
            )
        if (
            self.validation_used_in_fit
            or self.out_of_sample_used_in_fit
            or self.untouched_forward_used
        ):
            raise ValueError("family expansion fitting is TRAIN-only")
        if (
            self.automatic_family_selection
            or self.automatic_hyperparameter_selection
        ):
            raise ValueError("family training cannot automatically select")
        if self.production_authority:
            raise ValueError("family research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.training_identity != canonical_sha256(
            _training_payload(self)
        ):
            raise ValueError("family training identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyPrediction:
    prediction_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    model_identity: str
    observation_identity: str
    score: int
    predicted_positive: bool

    def __post_init__(self) -> None:
        _require_sha256(self.prediction_identity, "family prediction identity")
        _require_sha256(self.model_identity, "family prediction model identity")
        _require_sha256(
            self.observation_identity,
            "family prediction observation identity",
        )
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family prediction schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family prediction engine")
        if self.family is not MLExpandedFamily.CATEGORICAL_SIGN_VOTE:
            raise ValueError("unsupported family prediction target")
        if self.predicted_positive != (self.score > 0):
            raise ValueError("family prediction label/score mismatch")
        if self.prediction_identity != canonical_sha256(
            _prediction_payload(self)
        ):
            raise ValueError("family prediction identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    model_identity: str
    partition_identity: str
    partition_role: PartitionRole
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
        _require_sha256(self.evaluation_identity, "family evaluation identity")
        _require_sha256(self.model_identity, "family evaluation model identity")
        _require_sha256(
            self.partition_identity,
            "family evaluation partition identity",
        )
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family evaluation schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family evaluation engine")
        if self.family is not MLExpandedFamily.CATEGORICAL_SIGN_VOTE:
            raise ValueError("unsupported family evaluation target")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "family evaluation is limited to validation or out-of-sample"
            )
        if self.observation_count <= 0:
            raise ValueError("family evaluation requires observations")
        if not 0 <= self.positive_prediction_count <= self.observation_count:
            raise ValueError("invalid family positive prediction count")
        if not 0 <= self.correct_direction_count <= self.observation_count:
            raise ValueError("invalid family correct-direction count")
        if len(self.prediction_identities) != self.observation_count:
            raise ValueError("family evaluation must bind every prediction")
        if tuple(sorted(set(self.prediction_identities))) != (
            self.prediction_identities
        ):
            raise ValueError(
                "family prediction identities must be sorted and unique"
            )
        if len(self.selected_observation_identities) != (
            self.positive_prediction_count
        ):
            raise ValueError("family selected observation count mismatch")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "family selected observations must be sorted and unique"
            )
        _validate_metrics(
            selected_count=self.positive_prediction_count,
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
            average_net_r=self.average_net_r,
        )
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("family evaluation identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyFoldComparison:
    comparison_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    reference_family: MLExpandedFamily
    reference_model_identity: str
    reference_evaluation_identity: str
    challenger_family: MLExpandedFamily
    challenger_model_identity: str
    challenger_evaluation_identity: str
    automatic_winner_selection: bool = False
    calibrated_probability_claim: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.comparison_identity, "family comparison identity")
        _require_sha256(self.fold_identity, "family comparison fold identity")
        _require_sha256(
            self.reference_model_identity,
            "reference family model identity",
        )
        _require_sha256(
            self.reference_evaluation_identity,
            "reference family evaluation identity",
        )
        _require_sha256(
            self.challenger_model_identity,
            "challenger family model identity",
        )
        _require_sha256(
            self.challenger_evaluation_identity,
            "challenger family evaluation identity",
        )
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family comparison schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family comparison engine")
        if self.fold_index < 0:
            raise ValueError("family comparison fold index must be non-negative")
        if self.reference_family is not (
            MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE
        ):
            raise ValueError("family comparison reference mismatch")
        if self.challenger_family is not MLExpandedFamily.CATEGORICAL_SIGN_VOTE:
            raise ValueError("family comparison challenger mismatch")
        if self.automatic_winner_selection:
            raise ValueError("automatic family winner selection is closed")
        if self.calibrated_probability_claim:
            raise ValueError("family comparison makes no probability claim")
        if self.comparison_identity != canonical_sha256(
            _comparison_payload(self)
        ):
            raise ValueError("family comparison identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyExpansionManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLFamilyExpansionSemantic
    config_identity: str
    family_set: tuple[MLExpandedFamily, ...]
    fold_identities: tuple[str, ...]
    comparison_identities: tuple[str, ...]
    multiple_testing_status: MLFamilyMultipleTestingStatus
    automatic_family_selection: bool = False
    automatic_hyperparameter_selection: bool = False
    aggregate_winner_selection: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.run_identity, "family expansion run identity")
        _require_sha256(self.config_identity, "family expansion config identity")
        if self.schema_version != ML_FAMILY_EXPANSION_SCHEMA_VERSION:
            raise ValueError("unsupported family expansion manifest schema")
        if self.engine_version != ML_FAMILY_EXPANSION_ENGINE_VERSION:
            raise ValueError("unsupported family expansion manifest engine")
        if self.semantic is not (
            MLFamilyExpansionSemantic.DESCRIPTIVE_MULTI_FAMILY_NOT_SELECTION
        ):
            raise ValueError("unsupported family expansion semantic")
        if self.family_set != FIXED_FAMILY_SET:
            raise ValueError("family expansion manifest family set mismatch")
        if not self.fold_identities:
            raise ValueError("family expansion manifest requires folds")
        if len(self.fold_identities) != len(self.comparison_identities):
            raise ValueError("family expansion fold/comparison count mismatch")
        for identities, label in (
            (self.fold_identities, "fold"),
            (self.comparison_identities, "comparison"),
        ):
            for identity in identities:
                _require_sha256(identity, f"family expansion {label} identity")
            if len(set(identities)) != len(identities):
                raise ValueError(
                    f"family expansion {label} identities must be unique"
                )
        if self.multiple_testing_status is not (
            MLFamilyMultipleTestingStatus
            .BOUNDED_TWO_FAMILIES_NO_AUTOMATIC_SELECTION
        ):
            raise ValueError("unsupported family multiple-testing state")
        if (
            self.automatic_family_selection
            or self.automatic_hyperparameter_selection
            or self.aggregate_winner_selection
            or self.calibrated_probability_claim
        ):
            raise ValueError("family expansion cannot select or calibrate models")
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("family expansion has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("family expansion run identity mismatch")


def build_ml_family_expansion_config() -> MLFamilyExpansionConfig:
    payload = {
        "automatic_family_selection": False,
        "automatic_hyperparameter_selection": False,
        "calibrated_probability_claim": False,
        "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
        "family_set": FIXED_FAMILY_SET,
        "max_features": MAX_FAMILY_FEATURES,
        "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        "uncontrolled_model_search": False,
    }
    return MLFamilyExpansionConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
        family_set=FIXED_FAMILY_SET,
        max_features=MAX_FAMILY_FEATURES,
    )


def fit_ml_sign_vote_model(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    *,
    config: MLFamilyExpansionConfig | None = None,
) -> tuple[MLSignVoteModel, MLFamilyTrainingManifest]:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("family fitting requires TRAIN partition")
    effective_config = config or build_ml_family_expansion_config()
    ordered_features = _validate_features(features)
    ordered_observations = _validate_observations(
        training_partition,
        observations,
        ordered_features,
    )
    if any(
        item.outcome_available_at_ms > training_partition.end_ms
        for item in ordered_observations
    ):
        raise ValueError(
            "family training outcome must be available by train partition end"
        )

    positive_count = sum(item.net_outcome_r > 0 for item in ordered_observations)
    non_positive_count = len(ordered_observations) - positive_count
    counts: dict[tuple[str, str, str, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )
    for observation in ordered_observations:
        positive = observation.net_outcome_r > 0
        for reading in observation.feature_readings:
            key = (
                reading.feature_identity,
                reading.feature_id,
                reading.feature_version,
                reading.value,
            )
            counts[key][0 if positive else 1] += 1

    category_votes = tuple(
        _build_category_vote(
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
    training_feature_set_identity = canonical_sha256(
        {
            "feature_identities": feature_identities,
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
    model_payload = {
        "category_vote_identities": tuple(
            item.vote_identity for item in category_votes
        ),
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
        "family": MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        "feature_identities": feature_identities,
        "non_positive_count": non_positive_count,
        "positive_count": positive_count,
        "prior_vote": _sign(positive_count - non_positive_count),
        "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        "training_feature_set_identity": training_feature_set_identity,
        "training_partition_identity": training_partition.partition_identity,
    }
    model = MLSignVoteModel(
        model_identity=canonical_sha256(model_payload),
        schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
        family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        config_identity=effective_config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        training_feature_set_identity=training_feature_set_identity,
        feature_identities=feature_identities,
        positive_count=positive_count,
        non_positive_count=non_positive_count,
        prior_vote=_sign(positive_count - non_positive_count),
        category_votes=category_votes,
    )
    training_ids = tuple(
        sorted(item.observation_identity for item in ordered_observations)
    )
    training_payload = {
        "automatic_family_selection": False,
        "automatic_hyperparameter_selection": False,
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
        "family": MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        "model_identity": model.model_identity,
        "out_of_sample_used_in_fit": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        "training_observation_identities": training_ids,
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
        "validation_used_in_fit": False,
    }
    manifest = MLFamilyTrainingManifest(
        training_identity=canonical_sha256(training_payload),
        schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
        family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        config_identity=effective_config.config_identity,
        model_identity=model.model_identity,
        training_partition_identity=training_partition.partition_identity,
        training_observation_identities=training_ids,
    )
    return model, manifest


def evaluate_ml_sign_vote_model(
    model: MLSignVoteModel,
    partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    features: Sequence[SymbolicFeatureSpec],
) -> tuple[tuple[MLFamilyPrediction, ...], MLFamilyEvaluation]:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "family evaluation is limited to validation or out-of-sample"
        )
    ordered_features = _validate_features(features)
    if tuple(sorted(item.feature_identity for item in ordered_features)) != (
        model.feature_identities
    ):
        raise ValueError("family model feature identity mismatch")
    ordered_observations = _validate_observations(
        partition,
        observations,
        ordered_features,
    )
    predictions = tuple(
        _predict_sign_vote(model, item) for item in ordered_observations
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
        prediction.predicted_positive == (observation.net_outcome_r > 0)
        for observation, prediction in zip(
            ordered_observations,
            predictions,
            strict=True,
        )
    )
    gross, cost, net, average = _selected_metrics(selected)
    prediction_ids = tuple(
        sorted(item.prediction_identity for item in predictions)
    )
    selected_ids = tuple(
        sorted(item.observation_identity for item in selected)
    )
    payload = {
        "average_net_r": average,
        "correct_direction_count": correct_direction_count,
        "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
        "explicit_cost_r_total": cost,
        "family": MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        "gross_r_total": gross,
        "model_identity": model.model_identity,
        "net_r_total": net,
        "observation_count": len(ordered_observations),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "positive_prediction_count": len(selected),
        "prediction_identities": prediction_ids,
        "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        "selected_observation_identities": selected_ids,
    }
    evaluation = MLFamilyEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
        family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        model_identity=model.model_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        observation_count=len(ordered_observations),
        positive_prediction_count=len(selected),
        correct_direction_count=correct_direction_count,
        prediction_identities=prediction_ids,
        selected_observation_identities=selected_ids,
        gross_r_total=gross,
        explicit_cost_r_total=cost,
        net_r_total=net,
        average_net_r=average,
    )
    return predictions, evaluation


def run_ml_family_expansion(
    features: Sequence[SymbolicFeatureSpec],
    folds: Sequence[MLWalkForwardFold],
    reference_artifacts: Sequence[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation]
    ],
    *,
    config: MLFamilyExpansionConfig | None = None,
) -> tuple[
    tuple[tuple[MLSignVoteModel, MLFamilyTrainingManifest, MLFamilyEvaluation], ...],
    tuple[MLFamilyFoldComparison, ...],
    MLFamilyExpansionManifest,
]:
    effective_config = config or build_ml_family_expansion_config()
    ordered_features = _validate_features(features)
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    references = tuple(reference_artifacts)
    if not ordered_folds:
        raise ValueError("family expansion requires walk-forward folds")
    if len(ordered_folds) != len(references):
        raise ValueError("family expansion reference artifact count mismatch")
    if tuple(item.fold_index for item in ordered_folds) != tuple(
        range(len(ordered_folds))
    ):
        raise ValueError("family expansion fold indexes must be contiguous")

    challenger_artifacts: list[
        tuple[MLSignVoteModel, MLFamilyTrainingManifest, MLFamilyEvaluation]
    ] = []
    comparisons: list[MLFamilyFoldComparison] = []

    for fold, reference in zip(ordered_folds, references, strict=True):
        reference_model, reference_training, reference_evaluation = reference
        _validate_reference_artifact(
            fold,
            reference_model,
            reference_training,
            reference_evaluation,
        )
        _, rebuilt_reference = evaluate_ml_baseline(
            reference_model,
            fold.evaluation_partition,
            fold.evaluation_observations,
            ordered_features,
        )
        if rebuilt_reference != reference_evaluation:
            raise ValueError(
                "family expansion requires exact accepted reference evaluation"
            )

        model, training = fit_ml_sign_vote_model(
            ordered_features,
            fold.training_partition,
            fold.training_observations,
            config=effective_config,
        )
        _, evaluation = evaluate_ml_sign_vote_model(
            model,
            fold.evaluation_partition,
            fold.evaluation_observations,
            ordered_features,
        )
        comparison_payload = {
            "automatic_winner_selection": False,
            "calibrated_probability_claim": False,
            "challenger_evaluation_identity": evaluation.evaluation_identity,
            "challenger_family": MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
            "challenger_model_identity": model.model_identity,
            "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "reference_evaluation_identity": (
                reference_evaluation.evaluation_identity
            ),
            "reference_family": (
                MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE
            ),
            "reference_model_identity": reference_model.model_identity,
            "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        }
        comparison = MLFamilyFoldComparison(
            comparison_identity=canonical_sha256(comparison_payload),
            schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
            engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
            fold_identity=fold.fold_identity,
            fold_index=fold.fold_index,
            reference_family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
            reference_model_identity=reference_model.model_identity,
            reference_evaluation_identity=(
                reference_evaluation.evaluation_identity
            ),
            challenger_family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
            challenger_model_identity=model.model_identity,
            challenger_evaluation_identity=evaluation.evaluation_identity,
        )
        challenger_artifacts.append((model, training, evaluation))
        comparisons.append(comparison)

    fold_ids = tuple(item.fold_identity for item in ordered_folds)
    comparison_ids = tuple(item.comparison_identity for item in comparisons)
    manifest_payload = {
        "aggregate_winner_selection": False,
        "automatic_family_selection": False,
        "automatic_hyperparameter_selection": False,
        "calibrated_probability_claim": False,
        "comparison_identities": comparison_ids,
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
        "family_set": FIXED_FAMILY_SET,
        "fold_identities": fold_ids,
        "multiple_testing_status": (
            MLFamilyMultipleTestingStatus
            .BOUNDED_TWO_FAMILIES_NO_AUTOMATIC_SELECTION
        ),
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        "semantic": (
            MLFamilyExpansionSemantic.DESCRIPTIVE_MULTI_FAMILY_NOT_SELECTION
        ),
        "untouched_forward_used": False,
    }
    manifest = MLFamilyExpansionManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
        semantic=(
            MLFamilyExpansionSemantic.DESCRIPTIVE_MULTI_FAMILY_NOT_SELECTION
        ),
        config_identity=effective_config.config_identity,
        family_set=FIXED_FAMILY_SET,
        fold_identities=fold_ids,
        comparison_identities=comparison_ids,
        multiple_testing_status=(
            MLFamilyMultipleTestingStatus
            .BOUNDED_TWO_FAMILIES_NO_AUTOMATIC_SELECTION
        ),
    )
    return tuple(challenger_artifacts), tuple(comparisons), manifest


def _build_category_vote(
    *,
    feature_identity: str,
    feature_id: str,
    feature_version: str,
    value: str,
    positive_count: int,
    non_positive_count: int,
) -> MLFamilyCategoryVote:
    payload = {
        "feature_id": feature_id,
        "feature_identity": feature_identity,
        "feature_version": feature_version,
        "non_positive_count": non_positive_count,
        "positive_count": positive_count,
        "value": value,
        "vote": _sign(positive_count - non_positive_count),
    }
    return MLFamilyCategoryVote(
        vote_identity=canonical_sha256(payload),
        feature_identity=feature_identity,
        feature_id=feature_id,
        feature_version=feature_version,
        value=value,
        positive_count=positive_count,
        non_positive_count=non_positive_count,
        vote=_sign(positive_count - non_positive_count),
    )


def _predict_sign_vote(
    model: MLSignVoteModel,
    observation: ClusterResearchObservation,
) -> MLFamilyPrediction:
    score = model.prior_vote
    vote_by_key = {
        (item.feature_id, item.feature_version, item.value): item.vote
        for item in model.category_votes
    }
    for reading in observation.feature_readings:
        score += vote_by_key.get(
            (reading.feature_id, reading.feature_version, reading.value),
            0,
        )
    payload = {
        "engine_version": ML_FAMILY_EXPANSION_ENGINE_VERSION,
        "family": MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        "model_identity": model.model_identity,
        "observation_identity": observation.observation_identity,
        "predicted_positive": score > 0,
        "schema_version": ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        "score": score,
    }
    return MLFamilyPrediction(
        prediction_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_EXPANSION_SCHEMA_VERSION,
        engine_version=ML_FAMILY_EXPANSION_ENGINE_VERSION,
        family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        model_identity=model.model_identity,
        observation_identity=observation.observation_identity,
        score=score,
        predicted_positive=score > 0,
    )


def _validate_reference_artifact(
    fold: MLWalkForwardFold,
    model: MLBaselineModel,
    training: MLTrainingManifest,
    evaluation: MLEvaluation,
) -> None:
    if model.config_identity != fold.config_identity:
        raise ValueError("reference model/fold config mismatch")
    if model.training_partition_identity != (
        fold.training_partition.partition_identity
    ):
        raise ValueError("reference model training partition mismatch")
    if training.model_identity != model.model_identity:
        raise ValueError("reference training/model identity mismatch")
    if training.training_partition_identity != (
        fold.training_partition.partition_identity
    ):
        raise ValueError("reference training partition mismatch")
    if evaluation.model_identity != model.model_identity:
        raise ValueError("reference evaluation/model identity mismatch")
    if evaluation.partition_identity != (
        fold.evaluation_partition.partition_identity
    ):
        raise ValueError("reference evaluation partition mismatch")


def _validate_features(
    features: Sequence[SymbolicFeatureSpec],
) -> tuple[SymbolicFeatureSpec, ...]:
    ordered = tuple(sorted(features, key=lambda item: item.feature_id))
    if not MIN_FAMILY_FEATURES <= len(ordered) <= MAX_FAMILY_FEATURES:
        raise ValueError("family expansion requires 1..6 features")
    ids = tuple(item.feature_id for item in ordered)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("family expansion requires unique feature ids")
    identities = tuple(item.feature_identity for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("family expansion requires unique feature identities")
    return ordered


def _validate_observations(
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
        raise ValueError("family expansion requires observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError("family observations must cover partition exactly")

    feature_by_id = {item.feature_id: item for item in features}
    expected_feature_ids = tuple(item.feature_id for item in features)
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    observed_records: set[str] = set()
    for observation in ordered:
        if observation.partition_identity != partition.partition_identity:
            raise ValueError("family observation partition mismatch")
        if not partition.start_ms <= observation.decision_as_of_ms < (
            partition.end_ms
        ):
            raise ValueError("family observation decision time outside partition")
        if observation.source_evidence_identity not in partition_sources:
            raise ValueError("family observation source outside partition")
        if observation.source_evidence_identity in observed_sources:
            raise ValueError("duplicate family source evidence")
        if observation.observation_identity in observed_records:
            raise ValueError("duplicate family observation identity")
        observed_sources.add(observation.source_evidence_identity)
        observed_records.add(observation.observation_identity)

        reading_ids = tuple(item.feature_id for item in observation.feature_readings)
        if reading_ids != expected_feature_ids:
            raise ValueError("family observation feature coverage mismatch")
        for reading in observation.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("family observation feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("family observation feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError("family observation feature value outside contract")
    if observed_sources != partition_sources:
        raise ValueError("family observations must cover partition exactly")
    return ordered


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
) -> None:
    metrics = (
        gross_r_total,
        explicit_cost_r_total,
        net_r_total,
        average_net_r,
    )
    if selected_count == 0:
        if any(item is not None for item in metrics):
            raise ValueError("family evaluation cannot fabricate metrics")
        return
    if any(item is None for item in metrics):
        raise ValueError("family selections require complete metrics")
    assert gross_r_total is not None
    assert explicit_cost_r_total is not None
    assert net_r_total is not None
    assert average_net_r is not None
    if explicit_cost_r_total < 0:
        raise ValueError("family explicit cost cannot be negative")
    if net_r_total != gross_r_total - explicit_cost_r_total:
        raise ValueError("family net-R accounting mismatch")
    if average_net_r != net_r_total / Decimal(selected_count):
        raise ValueError("family average net-R mismatch")


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _config_payload(config: MLFamilyExpansionConfig) -> dict[str, object]:
    return {
        "automatic_family_selection": config.automatic_family_selection,
        "automatic_hyperparameter_selection": (
            config.automatic_hyperparameter_selection
        ),
        "calibrated_probability_claim": config.calibrated_probability_claim,
        "engine_version": config.engine_version,
        "family_set": config.family_set,
        "max_features": config.max_features,
        "schema_version": config.schema_version,
        "uncontrolled_model_search": config.uncontrolled_model_search,
    }


def _vote_payload(vote: MLFamilyCategoryVote) -> dict[str, object]:
    return {
        "feature_id": vote.feature_id,
        "feature_identity": vote.feature_identity,
        "feature_version": vote.feature_version,
        "non_positive_count": vote.non_positive_count,
        "positive_count": vote.positive_count,
        "value": vote.value,
        "vote": vote.vote,
    }


def _model_payload(model: MLSignVoteModel) -> dict[str, object]:
    return {
        "category_vote_identities": tuple(
            item.vote_identity for item in model.category_votes
        ),
        "config_identity": model.config_identity,
        "engine_version": model.engine_version,
        "family": model.family,
        "feature_identities": model.feature_identities,
        "non_positive_count": model.non_positive_count,
        "positive_count": model.positive_count,
        "prior_vote": model.prior_vote,
        "schema_version": model.schema_version,
        "training_feature_set_identity": model.training_feature_set_identity,
        "training_partition_identity": model.training_partition_identity,
    }


def _training_payload(
    manifest: MLFamilyTrainingManifest,
) -> dict[str, object]:
    return {
        "automatic_family_selection": manifest.automatic_family_selection,
        "automatic_hyperparameter_selection": (
            manifest.automatic_hyperparameter_selection
        ),
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "family": manifest.family,
        "model_identity": manifest.model_identity,
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


def _prediction_payload(
    prediction: MLFamilyPrediction,
) -> dict[str, object]:
    return {
        "engine_version": prediction.engine_version,
        "family": prediction.family,
        "model_identity": prediction.model_identity,
        "observation_identity": prediction.observation_identity,
        "predicted_positive": prediction.predicted_positive,
        "schema_version": prediction.schema_version,
        "score": prediction.score,
    }


def _evaluation_payload(
    evaluation: MLFamilyEvaluation,
) -> dict[str, object]:
    return {
        "average_net_r": evaluation.average_net_r,
        "correct_direction_count": evaluation.correct_direction_count,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "family": evaluation.family,
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
    }


def _comparison_payload(
    comparison: MLFamilyFoldComparison,
) -> dict[str, object]:
    return {
        "automatic_winner_selection": comparison.automatic_winner_selection,
        "calibrated_probability_claim": comparison.calibrated_probability_claim,
        "challenger_evaluation_identity": (
            comparison.challenger_evaluation_identity
        ),
        "challenger_family": comparison.challenger_family,
        "challenger_model_identity": comparison.challenger_model_identity,
        "engine_version": comparison.engine_version,
        "fold_identity": comparison.fold_identity,
        "fold_index": comparison.fold_index,
        "reference_evaluation_identity": (
            comparison.reference_evaluation_identity
        ),
        "reference_family": comparison.reference_family,
        "reference_model_identity": comparison.reference_model_identity,
        "schema_version": comparison.schema_version,
    }


def _manifest_payload(
    manifest: MLFamilyExpansionManifest,
) -> dict[str, object]:
    return {
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_family_selection": manifest.automatic_family_selection,
        "automatic_hyperparameter_selection": (
            manifest.automatic_hyperparameter_selection
        ),
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "comparison_identities": manifest.comparison_identities,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "family_set": manifest.family_set,
        "fold_identities": manifest.fold_identities,
        "multiple_testing_status": manifest.multiple_testing_status,
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
