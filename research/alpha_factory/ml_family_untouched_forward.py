"""Frozen-model untouched-forward paper evidence for the accepted ML family set."""

from __future__ import annotations

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
)
from research.alpha_factory.ml_family_cost_stress import (
    MLFamilyCostStressFoldResult,
    MLFamilyCostStressManifest,
    MLFamilyCostStressScenario,
    run_ml_family_cost_stress,
)
from research.alpha_factory.ml_family_expansion import (
    FIXED_FAMILY_SET,
    MLExpandedFamily,
    MLFamilyEvaluation,
    MLFamilyExpansionManifest,
    MLFamilyFoldComparison,
    MLFamilyTrainingManifest,
    MLSignVoteModel,
    run_ml_family_expansion,
)
from research.alpha_factory.ml_family_robustness_ablation import (
    MLFamilyFeatureAblationResult,
    MLFamilyFoldSensitivitySummary,
    MLFamilyRegimeSliceResult,
    MLFamilyRobustnessFoldResult,
    MLFamilyRobustnessManifest,
    run_ml_family_robustness_ablation,
)
from research.alpha_factory.ml_walk_forward import MLWalkForwardFold
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION = (
    "alpha-factory-ml-family-untouched-forward-v1/1"
)
ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION = (
    "alpha-factory-ml-family-untouched-forward-schema-v1/1"
)
REAL_CAPITAL = 0


class MLUntouchedForwardSemantic(StrEnum):
    DESCRIPTIVE_FORWARD_PAPER_NOT_SELECTION = (
        "descriptive_forward_paper_not_selection"
    )


class MLFrozenModelPolicy(StrEnum):
    LATEST_ACCEPTED_WALK_FORWARD_FOLD = (
        "latest_accepted_walk_forward_fold_chronological_not_performance_selected"
    )


class MLUntouchedForwardStatus(StrEnum):
    OBSERVED = "observed"
    OBSERVED_NO_SELECTION = "observed_no_selection"


@dataclass(frozen=True, slots=True)
class MLUntouchedForwardConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    freeze_policy: MLFrozenModelPolicy
    automatic_family_selection: bool = False
    automatic_threshold_selection: bool = False
    feature_change_allowed: bool = False
    model_refit_allowed: bool = False
    retrospective_optimization_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "forward config identity")
        if self.schema_version != ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported untouched-forward config schema")
        if self.engine_version != ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported untouched-forward config engine")
        if self.freeze_policy is not (
            MLFrozenModelPolicy.LATEST_ACCEPTED_WALK_FORWARD_FOLD
        ):
            raise ValueError("unsupported frozen-model policy")
        if (
            self.automatic_family_selection
            or self.automatic_threshold_selection
            or self.feature_change_allowed
            or self.model_refit_allowed
            or self.retrospective_optimization_allowed
        ):
            raise ValueError(
                "untouched-forward config cannot select, refit or optimize"
            )
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("forward config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFrozenFamilySnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    config_identity: str
    freeze_policy: MLFrozenModelPolicy
    source_fold_identity: str
    source_fold_index: int
    source_evaluation_end_ms: int
    reference_model_identity: str
    challenger_model_identity: str
    family_expansion_run_identity: str
    family_cost_stress_run_identity: str
    family_robustness_run_identity: str
    feature_identities: tuple[str, ...]
    model_refit_performed: bool = False
    family_selection_performed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.snapshot_identity, "forward snapshot identity"),
            (self.config_identity, "forward snapshot config identity"),
            (self.source_fold_identity, "forward source fold identity"),
            (
                self.reference_model_identity,
                "forward reference model identity",
            ),
            (
                self.challenger_model_identity,
                "forward challenger model identity",
            ),
            (
                self.family_expansion_run_identity,
                "forward family expansion run identity",
            ),
            (
                self.family_cost_stress_run_identity,
                "forward family cost-stress run identity",
            ),
            (
                self.family_robustness_run_identity,
                "forward family robustness run identity",
            ),
        ):
            _require_sha256(value, label)
        for identity in self.feature_identities:
            _require_sha256(identity, "forward feature identity")
        if self.schema_version != ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported forward snapshot schema")
        if self.engine_version != ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported forward snapshot engine")
        if self.freeze_policy is not (
            MLFrozenModelPolicy.LATEST_ACCEPTED_WALK_FORWARD_FOLD
        ):
            raise ValueError("unsupported snapshot freeze policy")
        if self.source_fold_index < 0:
            raise ValueError("source fold index must be non-negative")
        if self.source_evaluation_end_ms <= 0:
            raise ValueError("source evaluation end must be positive")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError("forward feature identities must be sorted and unique")
        if self.model_refit_performed or self.family_selection_performed:
            raise ValueError("forward snapshot cannot refit or select a family")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("forward snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class MLUntouchedForwardPrediction:
    prediction_identity: str
    schema_version: str
    engine_version: str
    snapshot_identity: str
    family: MLExpandedFamily
    model_identity: str
    partition_identity: str
    observation_identity: str
    decision_as_of_ms: int
    score: int
    predicted_positive: bool

    def __post_init__(self) -> None:
        for value, label in (
            (self.prediction_identity, "forward prediction identity"),
            (self.snapshot_identity, "forward prediction snapshot identity"),
            (self.model_identity, "forward prediction model identity"),
            (self.partition_identity, "forward prediction partition identity"),
            (
                self.observation_identity,
                "forward prediction observation identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported forward prediction schema")
        if self.engine_version != ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported forward prediction engine")
        if self.family not in FIXED_FAMILY_SET:
            raise ValueError("forward prediction is outside accepted family set")
        if self.decision_as_of_ms < 0:
            raise ValueError("forward decision time must be non-negative")
        if self.predicted_positive != (self.score > 0):
            raise ValueError("forward prediction label/score mismatch")
        if self.prediction_identity != canonical_sha256(
            _prediction_payload(self)
        ):
            raise ValueError("forward prediction identity mismatch")


@dataclass(frozen=True, slots=True)
class MLUntouchedForwardFamilyEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    snapshot_identity: str
    family: MLExpandedFamily
    model_identity: str
    partition_identity: str
    status: MLUntouchedForwardStatus
    observation_count: int
    prediction_identities: tuple[str, ...]
    selected_observation_identities: tuple[str, ...]
    positive_prediction_count: int
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    model_refit_performed: bool = False
    feature_change_performed: bool = False
    threshold_change_performed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.evaluation_identity, "forward evaluation identity"),
            (self.snapshot_identity, "forward evaluation snapshot identity"),
            (self.model_identity, "forward evaluation model identity"),
            (self.partition_identity, "forward evaluation partition identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported forward evaluation schema")
        if self.engine_version != ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported forward evaluation engine")
        if self.family not in FIXED_FAMILY_SET:
            raise ValueError("forward evaluation is outside accepted family set")
        if self.observation_count <= 0:
            raise ValueError("forward evaluation requires observations")
        if len(self.prediction_identities) != self.observation_count:
            raise ValueError("forward evaluation must bind every prediction")
        if tuple(sorted(set(self.prediction_identities))) != (
            self.prediction_identities
        ):
            raise ValueError(
                "forward prediction identities must be sorted and unique"
            )
        if len(self.selected_observation_identities) != (
            self.positive_prediction_count
        ):
            raise ValueError("forward selected observation count mismatch")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "forward selected observations must be sorted and unique"
            )
        expected_status = (
            MLUntouchedForwardStatus.OBSERVED
            if self.positive_prediction_count > 0
            else MLUntouchedForwardStatus.OBSERVED_NO_SELECTION
        )
        if self.status is not expected_status:
            raise ValueError("forward evaluation status/count mismatch")
        _validate_metrics(
            selected_count=self.positive_prediction_count,
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
            average_net_r=self.average_net_r,
        )
        if (
            self.model_refit_performed
            or self.feature_change_performed
            or self.threshold_change_performed
        ):
            raise ValueError(
                "forward evaluation cannot refit/change features/thresholds"
            )
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("forward evaluation identity mismatch")


@dataclass(frozen=True, slots=True)
class MLUntouchedForwardManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLUntouchedForwardSemantic
    config_identity: str
    snapshot_identity: str
    partition_identity: str
    reference_evaluation_identity: str
    challenger_evaluation_identity: str
    family_set: tuple[MLExpandedFamily, ...]
    automatic_family_selection: bool = False
    automatic_threshold_selection: bool = False
    aggregate_winner_selection: bool = False
    retrospective_optimization_performed: bool = False
    model_refit_performed: bool = False
    feature_change_performed: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_identity, "forward run identity"),
            (self.config_identity, "forward run config identity"),
            (self.snapshot_identity, "forward run snapshot identity"),
            (self.partition_identity, "forward run partition identity"),
            (
                self.reference_evaluation_identity,
                "forward reference evaluation identity",
            ),
            (
                self.challenger_evaluation_identity,
                "forward challenger evaluation identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported forward manifest schema")
        if self.engine_version != ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION:
            raise ValueError("unsupported forward manifest engine")
        if self.semantic is not (
            MLUntouchedForwardSemantic.DESCRIPTIVE_FORWARD_PAPER_NOT_SELECTION
        ):
            raise ValueError("unsupported forward semantic")
        if self.family_set != FIXED_FAMILY_SET:
            raise ValueError("forward manifest family set mismatch")
        if (
            self.automatic_family_selection
            or self.automatic_threshold_selection
            or self.aggregate_winner_selection
            or self.retrospective_optimization_performed
            or self.model_refit_performed
            or self.feature_change_performed
            or self.calibrated_probability_claim
        ):
            raise ValueError(
                "forward manifest cannot select, optimize, refit or calibrate"
            )
        if not self.untouched_forward_used:
            raise ValueError("forward manifest must explicitly use forward evidence")
        if self.production_authority:
            raise ValueError("untouched-forward research has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("forward run identity mismatch")


def build_ml_untouched_forward_config() -> MLUntouchedForwardConfig:
    payload = {
        "automatic_family_selection": False,
        "automatic_threshold_selection": False,
        "engine_version": ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        "feature_change_allowed": False,
        "freeze_policy": MLFrozenModelPolicy.LATEST_ACCEPTED_WALK_FORWARD_FOLD,
        "model_refit_allowed": False,
        "retrospective_optimization_allowed": False,
        "schema_version": ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
    }
    return MLUntouchedForwardConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        engine_version=ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        freeze_policy=MLFrozenModelPolicy.LATEST_ACCEPTED_WALK_FORWARD_FOLD,
    )


def run_ml_family_untouched_forward_paper(
    features: Sequence[SymbolicFeatureSpec],
    folds: Sequence[MLWalkForwardFold],
    reference_artifacts: Sequence[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation]
    ],
    family_expansion_evidence: tuple[
        tuple[
            tuple[
                MLSignVoteModel,
                MLFamilyTrainingManifest,
                MLFamilyEvaluation,
            ],
            ...,
        ],
        tuple[MLFamilyFoldComparison, ...],
        MLFamilyExpansionManifest,
    ],
    family_cost_stress_evidence: tuple[
        tuple[
            tuple[
                tuple[MLFamilyCostStressScenario, ...],
                tuple[MLFamilyCostStressScenario, ...],
            ],
            ...,
        ],
        tuple[MLFamilyCostStressFoldResult, ...],
        MLFamilyCostStressManifest,
    ],
    family_robustness_evidence: tuple[
        tuple[
            tuple[
                tuple[MLFamilyFeatureAblationResult, ...],
                tuple[MLFamilyFeatureAblationResult, ...],
            ],
            ...,
        ],
        tuple[
            tuple[
                tuple[MLFamilyRegimeSliceResult, ...],
                tuple[MLFamilyRegimeSliceResult, ...],
            ],
            ...,
        ],
        tuple[MLFamilyRobustnessFoldResult, ...],
        MLFamilyFoldSensitivitySummary,
        MLFamilyRobustnessManifest,
    ],
    untouched_partition: ResearchPartition,
    untouched_observations: Sequence[ClusterResearchObservation],
    *,
    regime_feature_id: str,
    config: MLUntouchedForwardConfig | None = None,
) -> tuple[
    tuple[MLUntouchedForwardPrediction, ...],
    tuple[MLUntouchedForwardPrediction, ...],
    MLUntouchedForwardFamilyEvaluation,
    MLUntouchedForwardFamilyEvaluation,
    MLFrozenFamilySnapshot,
    MLUntouchedForwardManifest,
]:
    effective_config = config or build_ml_untouched_forward_config()
    ordered_features = _validate_features(features)
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    references = tuple(reference_artifacts)
    if not ordered_folds:
        raise ValueError("untouched-forward requires accepted walk-forward folds")
    if len(ordered_folds) != len(references):
        raise ValueError("untouched-forward reference artifact count mismatch")
    if tuple(item.fold_index for item in ordered_folds) != tuple(
        range(len(ordered_folds))
    ):
        raise ValueError("untouched-forward fold indexes must be contiguous")

    expected_expansion = run_ml_family_expansion(
        ordered_features,
        ordered_folds,
        references,
    )
    if expected_expansion != family_expansion_evidence:
        raise ValueError(
            "untouched-forward requires exact accepted family expansion evidence"
        )
    expected_cost = run_ml_family_cost_stress(
        ordered_features,
        ordered_folds,
        references,
        family_expansion_evidence,
    )
    if expected_cost != family_cost_stress_evidence:
        raise ValueError(
            "untouched-forward requires exact accepted family cost-stress evidence"
        )
    expected_robustness = run_ml_family_robustness_ablation(
        ordered_features,
        ordered_folds,
        references,
        family_expansion_evidence,
        family_cost_stress_evidence,
        regime_feature_id=regime_feature_id,
    )
    if expected_robustness != family_robustness_evidence:
        raise ValueError(
            "untouched-forward requires exact accepted family robustness evidence"
        )

    if untouched_partition.role is not PartitionRole.UNTOUCHED_FORWARD:
        raise ValueError("forward evaluator requires untouched-forward partition")

    final_fold = ordered_folds[-1]
    if untouched_partition.dataset_identity != (
        final_fold.evaluation_partition.dataset_identity
    ):
        raise ValueError("forward partition dataset identity mismatch")
    if untouched_partition.start_ms < final_fold.evaluation_partition.end_ms:
        raise ValueError(
            "untouched-forward must begin after accepted OOS evidence closes"
        )

    challengers, _, expansion_manifest = family_expansion_evidence
    _, _, cost_manifest = family_cost_stress_evidence
    _, _, _, _, robustness_manifest = family_robustness_evidence
    reference_model = references[-1][0]
    challenger_model = challengers[-1][0]
    _validate_model_feature_identities(
        ordered_features,
        reference_model,
        challenger_model,
    )

    snapshot_payload = {
        "challenger_model_identity": challenger_model.model_identity,
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        "family_cost_stress_run_identity": cost_manifest.run_identity,
        "family_expansion_run_identity": expansion_manifest.run_identity,
        "family_robustness_run_identity": robustness_manifest.run_identity,
        "family_selection_performed": False,
        "feature_identities": tuple(
            sorted(item.feature_identity for item in ordered_features)
        ),
        "freeze_policy": effective_config.freeze_policy,
        "model_refit_performed": False,
        "reference_model_identity": reference_model.model_identity,
        "schema_version": ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        "source_evaluation_end_ms": final_fold.evaluation_partition.end_ms,
        "source_fold_identity": final_fold.fold_identity,
        "source_fold_index": final_fold.fold_index,
    }
    snapshot = MLFrozenFamilySnapshot(
        snapshot_identity=canonical_sha256(snapshot_payload),
        schema_version=ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        engine_version=ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        config_identity=effective_config.config_identity,
        freeze_policy=effective_config.freeze_policy,
        source_fold_identity=final_fold.fold_identity,
        source_fold_index=final_fold.fold_index,
        source_evaluation_end_ms=final_fold.evaluation_partition.end_ms,
        reference_model_identity=reference_model.model_identity,
        challenger_model_identity=challenger_model.model_identity,
        family_expansion_run_identity=expansion_manifest.run_identity,
        family_cost_stress_run_identity=cost_manifest.run_identity,
        family_robustness_run_identity=robustness_manifest.run_identity,
        feature_identities=tuple(
            sorted(item.feature_identity for item in ordered_features)
        ),
    )

    ordered_observations = _validate_forward_observations(
        untouched_partition,
        untouched_observations,
        ordered_features,
    )
    reference_predictions = tuple(
        _build_prediction(
            family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
            snapshot=snapshot,
            partition=untouched_partition,
            observation=observation,
            reference_model=reference_model,
            challenger_model=challenger_model,
        )
        for observation in ordered_observations
    )
    challenger_predictions = tuple(
        _build_prediction(
            family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
            snapshot=snapshot,
            partition=untouched_partition,
            observation=observation,
            reference_model=reference_model,
            challenger_model=challenger_model,
        )
        for observation in ordered_observations
    )
    reference_evaluation = _build_evaluation(
        family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
        model_identity=reference_model.model_identity,
        snapshot=snapshot,
        partition=untouched_partition,
        observations=ordered_observations,
        predictions=reference_predictions,
    )
    challenger_evaluation = _build_evaluation(
        family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
        model_identity=challenger_model.model_identity,
        snapshot=snapshot,
        partition=untouched_partition,
        observations=ordered_observations,
        predictions=challenger_predictions,
    )

    manifest_payload = {
        "aggregate_winner_selection": False,
        "automatic_family_selection": False,
        "automatic_threshold_selection": False,
        "calibrated_probability_claim": False,
        "challenger_evaluation_identity": (
            challenger_evaluation.evaluation_identity
        ),
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        "family_set": FIXED_FAMILY_SET,
        "feature_change_performed": False,
        "model_refit_performed": False,
        "partition_identity": untouched_partition.partition_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reference_evaluation_identity": (
            reference_evaluation.evaluation_identity
        ),
        "retrospective_optimization_performed": False,
        "schema_version": ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        "semantic": (
            MLUntouchedForwardSemantic.DESCRIPTIVE_FORWARD_PAPER_NOT_SELECTION
        ),
        "snapshot_identity": snapshot.snapshot_identity,
        "untouched_forward_used": True,
    }
    manifest = MLUntouchedForwardManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        engine_version=ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        semantic=(
            MLUntouchedForwardSemantic.DESCRIPTIVE_FORWARD_PAPER_NOT_SELECTION
        ),
        config_identity=effective_config.config_identity,
        snapshot_identity=snapshot.snapshot_identity,
        partition_identity=untouched_partition.partition_identity,
        reference_evaluation_identity=reference_evaluation.evaluation_identity,
        challenger_evaluation_identity=challenger_evaluation.evaluation_identity,
        family_set=FIXED_FAMILY_SET,
    )
    return (
        reference_predictions,
        challenger_predictions,
        reference_evaluation,
        challenger_evaluation,
        snapshot,
        manifest,
    )


def _validate_features(
    features: Sequence[SymbolicFeatureSpec],
) -> tuple[SymbolicFeatureSpec, ...]:
    ordered = tuple(sorted(features, key=lambda item: item.feature_id))
    if not ordered:
        raise ValueError("untouched-forward requires features")
    ids = tuple(item.feature_id for item in ordered)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("untouched-forward feature ids must be unique")
    identities = tuple(item.feature_identity for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("untouched-forward feature identities must be unique")
    return ordered


def _validate_model_feature_identities(
    features: tuple[SymbolicFeatureSpec, ...],
    reference_model: MLBaselineModel,
    challenger_model: MLSignVoteModel,
) -> None:
    expected = tuple(sorted(item.feature_identity for item in features))
    if reference_model.feature_identities != expected:
        raise ValueError("forward reference feature identity mismatch")
    if challenger_model.feature_identities != expected:
        raise ValueError("forward challenger feature identity mismatch")


def _validate_forward_observations(
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
        raise ValueError("untouched-forward requires observations")
    if len(ordered) != partition.row_count:
        raise ValueError("forward observations must match partition row_count")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError("forward observations must cover partition exactly")

    feature_by_id = {item.feature_id: item for item in features}
    expected_ids = tuple(item.feature_id for item in features)
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    observed_records: set[str] = set()

    for observation in ordered:
        if observation.partition_identity != partition.partition_identity:
            raise ValueError("forward observation partition mismatch")
        if not partition.start_ms <= observation.decision_as_of_ms < (
            partition.end_ms
        ):
            raise ValueError("forward decision time outside partition")
        if observation.outcome_available_at_ms < observation.decision_as_of_ms:
            raise ValueError("forward outcome cannot predate decision")
        if observation.outcome_available_at_ms > partition.end_ms:
            raise ValueError("forward observation is not yet evaluable")
        if observation.source_evidence_identity not in partition_sources:
            raise ValueError("forward observation source outside partition")
        if observation.source_evidence_identity in observed_sources:
            raise ValueError("duplicate forward source evidence")
        if observation.observation_identity in observed_records:
            raise ValueError("duplicate forward observation identity")
        observed_sources.add(observation.source_evidence_identity)
        observed_records.add(observation.observation_identity)

        reading_ids = tuple(item.feature_id for item in observation.feature_readings)
        if reading_ids != expected_ids:
            raise ValueError("forward observation feature coverage mismatch")
        for reading in observation.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("forward feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("forward feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError("forward feature value outside contract")
            if reading.available_at_ms > observation.decision_as_of_ms:
                raise ValueError("forward feature evidence arrives after decision")

    if observed_sources != partition_sources:
        raise ValueError("forward observations must cover partition exactly")
    return ordered


def _build_prediction(
    *,
    family: MLExpandedFamily,
    snapshot: MLFrozenFamilySnapshot,
    partition: ResearchPartition,
    observation: ClusterResearchObservation,
    reference_model: MLBaselineModel,
    challenger_model: MLSignVoteModel,
) -> MLUntouchedForwardPrediction:
    score = _score(
        family=family,
        reference_model=reference_model,
        challenger_model=challenger_model,
        observation=observation,
    )
    model_identity = (
        reference_model.model_identity
        if family is MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE
        else challenger_model.model_identity
    )
    payload = {
        "decision_as_of_ms": observation.decision_as_of_ms,
        "engine_version": ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        "family": family,
        "model_identity": model_identity,
        "observation_identity": observation.observation_identity,
        "partition_identity": partition.partition_identity,
        "predicted_positive": score > 0,
        "schema_version": ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        "score": score,
        "snapshot_identity": snapshot.snapshot_identity,
    }
    return MLUntouchedForwardPrediction(
        prediction_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        engine_version=ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        snapshot_identity=snapshot.snapshot_identity,
        family=family,
        model_identity=model_identity,
        partition_identity=partition.partition_identity,
        observation_identity=observation.observation_identity,
        decision_as_of_ms=observation.decision_as_of_ms,
        score=score,
        predicted_positive=score > 0,
    )


def _score(
    *,
    family: MLExpandedFamily,
    reference_model: MLBaselineModel,
    challenger_model: MLSignVoteModel,
    observation: ClusterResearchObservation,
) -> int:
    if family is MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE:
        score = reference_model.positive_count - reference_model.non_positive_count
        values = {
            (item.feature_id, item.feature_version, item.value): (
                item.positive_count - item.non_positive_count
            )
            for item in reference_model.category_counts
        }
    elif family is MLExpandedFamily.CATEGORICAL_SIGN_VOTE:
        score = challenger_model.prior_vote
        values = {
            (item.feature_id, item.feature_version, item.value): item.vote
            for item in challenger_model.category_votes
        }
    else:
        raise ValueError("unsupported untouched-forward family")
    for reading in observation.feature_readings:
        score += values.get(
            (reading.feature_id, reading.feature_version, reading.value),
            0,
        )
    return score


def _build_evaluation(
    *,
    family: MLExpandedFamily,
    model_identity: str,
    snapshot: MLFrozenFamilySnapshot,
    partition: ResearchPartition,
    observations: tuple[ClusterResearchObservation, ...],
    predictions: tuple[MLUntouchedForwardPrediction, ...],
) -> MLUntouchedForwardFamilyEvaluation:
    prediction_by_observation = {
        item.observation_identity: item for item in predictions
    }
    selected = tuple(
        observation
        for observation in observations
        if prediction_by_observation[
            observation.observation_identity
        ].predicted_positive
    )
    selected_ids = tuple(
        sorted(item.observation_identity for item in selected)
    )
    prediction_ids = tuple(
        sorted(item.prediction_identity for item in predictions)
    )
    gross, cost, net, average = _selected_metrics(selected)
    status = (
        MLUntouchedForwardStatus.OBSERVED
        if selected
        else MLUntouchedForwardStatus.OBSERVED_NO_SELECTION
    )
    payload = {
        "average_net_r": average,
        "engine_version": ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        "explicit_cost_r_total": cost,
        "family": family,
        "feature_change_performed": False,
        "gross_r_total": gross,
        "model_identity": model_identity,
        "model_refit_performed": False,
        "net_r_total": net,
        "observation_count": len(observations),
        "partition_identity": partition.partition_identity,
        "positive_prediction_count": len(selected),
        "prediction_identities": prediction_ids,
        "schema_version": ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        "selected_observation_identities": selected_ids,
        "snapshot_identity": snapshot.snapshot_identity,
        "status": status,
        "threshold_change_performed": False,
    }
    return MLUntouchedForwardFamilyEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_UNTOUCHED_FORWARD_SCHEMA_VERSION,
        engine_version=ML_FAMILY_UNTOUCHED_FORWARD_ENGINE_VERSION,
        snapshot_identity=snapshot.snapshot_identity,
        family=family,
        model_identity=model_identity,
        partition_identity=partition.partition_identity,
        status=status,
        observation_count=len(observations),
        prediction_identities=prediction_ids,
        selected_observation_identities=selected_ids,
        positive_prediction_count=len(selected),
        gross_r_total=gross,
        explicit_cost_r_total=cost,
        net_r_total=net,
        average_net_r=average,
    )


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
            raise ValueError("forward no-selection state cannot fabricate metrics")
        return
    if any(item is None for item in metrics):
        raise ValueError("forward selections require complete metrics")
    assert gross_r_total is not None
    assert explicit_cost_r_total is not None
    assert net_r_total is not None
    assert average_net_r is not None
    if explicit_cost_r_total < 0:
        raise ValueError("forward explicit cost cannot be negative")
    if net_r_total != gross_r_total - explicit_cost_r_total:
        raise ValueError("forward net-R accounting mismatch")
    if average_net_r != net_r_total / Decimal(selected_count):
        raise ValueError("forward average net-R mismatch")


def _config_payload(config: MLUntouchedForwardConfig) -> dict[str, object]:
    return {
        "automatic_family_selection": config.automatic_family_selection,
        "automatic_threshold_selection": config.automatic_threshold_selection,
        "engine_version": config.engine_version,
        "feature_change_allowed": config.feature_change_allowed,
        "freeze_policy": config.freeze_policy,
        "model_refit_allowed": config.model_refit_allowed,
        "retrospective_optimization_allowed": (
            config.retrospective_optimization_allowed
        ),
        "schema_version": config.schema_version,
    }


def _snapshot_payload(snapshot: MLFrozenFamilySnapshot) -> dict[str, object]:
    return {
        "challenger_model_identity": snapshot.challenger_model_identity,
        "config_identity": snapshot.config_identity,
        "engine_version": snapshot.engine_version,
        "family_cost_stress_run_identity": (
            snapshot.family_cost_stress_run_identity
        ),
        "family_expansion_run_identity": snapshot.family_expansion_run_identity,
        "family_robustness_run_identity": snapshot.family_robustness_run_identity,
        "family_selection_performed": snapshot.family_selection_performed,
        "feature_identities": snapshot.feature_identities,
        "freeze_policy": snapshot.freeze_policy,
        "model_refit_performed": snapshot.model_refit_performed,
        "reference_model_identity": snapshot.reference_model_identity,
        "schema_version": snapshot.schema_version,
        "source_evaluation_end_ms": snapshot.source_evaluation_end_ms,
        "source_fold_identity": snapshot.source_fold_identity,
        "source_fold_index": snapshot.source_fold_index,
    }


def _prediction_payload(
    prediction: MLUntouchedForwardPrediction,
) -> dict[str, object]:
    return {
        "decision_as_of_ms": prediction.decision_as_of_ms,
        "engine_version": prediction.engine_version,
        "family": prediction.family,
        "model_identity": prediction.model_identity,
        "observation_identity": prediction.observation_identity,
        "partition_identity": prediction.partition_identity,
        "predicted_positive": prediction.predicted_positive,
        "schema_version": prediction.schema_version,
        "score": prediction.score,
        "snapshot_identity": prediction.snapshot_identity,
    }


def _evaluation_payload(
    evaluation: MLUntouchedForwardFamilyEvaluation,
) -> dict[str, object]:
    return {
        "average_net_r": evaluation.average_net_r,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "family": evaluation.family,
        "feature_change_performed": evaluation.feature_change_performed,
        "gross_r_total": evaluation.gross_r_total,
        "model_identity": evaluation.model_identity,
        "model_refit_performed": evaluation.model_refit_performed,
        "net_r_total": evaluation.net_r_total,
        "observation_count": evaluation.observation_count,
        "partition_identity": evaluation.partition_identity,
        "positive_prediction_count": evaluation.positive_prediction_count,
        "prediction_identities": evaluation.prediction_identities,
        "schema_version": evaluation.schema_version,
        "selected_observation_identities": (
            evaluation.selected_observation_identities
        ),
        "snapshot_identity": evaluation.snapshot_identity,
        "status": evaluation.status,
        "threshold_change_performed": evaluation.threshold_change_performed,
    }


def _manifest_payload(
    manifest: MLUntouchedForwardManifest,
) -> dict[str, object]:
    return {
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_family_selection": manifest.automatic_family_selection,
        "automatic_threshold_selection": manifest.automatic_threshold_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "challenger_evaluation_identity": (
            manifest.challenger_evaluation_identity
        ),
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "family_set": manifest.family_set,
        "feature_change_performed": manifest.feature_change_performed,
        "model_refit_performed": manifest.model_refit_performed,
        "partition_identity": manifest.partition_identity,
        "production_authority": manifest.production_authority,
        "real_capital": manifest.real_capital,
        "reference_evaluation_identity": manifest.reference_evaluation_identity,
        "retrospective_optimization_performed": (
            manifest.retrospective_optimization_performed
        ),
        "schema_version": manifest.schema_version,
        "semantic": manifest.semantic,
        "snapshot_identity": manifest.snapshot_identity,
        "untouched_forward_used": manifest.untouched_forward_used,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256 hex") from exc
