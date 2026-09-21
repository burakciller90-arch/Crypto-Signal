"""Deterministic robustness evidence for the accepted bounded two-family ML set."""

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
from research.alpha_factory.ml_walk_forward import MLWalkForwardFold
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_FAMILY_ROBUSTNESS_ENGINE_VERSION = (
    "alpha-factory-ml-family-robustness-ablation-v1/1"
)
ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION = (
    "alpha-factory-ml-family-robustness-schema-v1/1"
)
MIN_ROBUSTNESS_FEATURES = 2
MAX_ROBUSTNESS_FEATURES = 6
REAL_CAPITAL = 0


class MLFamilyRobustnessSemantic(StrEnum):
    DESCRIPTIVE_FAMILY_ROBUSTNESS_NOT_SELECTION = (
        "descriptive_family_robustness_not_selection"
    )


class MLFamilyRegimeEvidenceStatus(StrEnum):
    OBSERVED = "observed"
    NO_EVIDENCE = "no_evidence"


@dataclass(frozen=True, slots=True)
class MLFamilyRobustnessConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    feature_identities: tuple[str, ...]
    regime_feature_identity: str
    regime_feature_id: str
    regime_feature_version: str
    max_feature_ablations: int
    automatic_family_selection: bool = False
    automatic_feature_selection: bool = False
    automatic_regime_selection: bool = False
    model_refit_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "family robustness config identity")
        for identity in self.feature_identities:
            _require_sha256(identity, "family robustness feature identity")
        _require_sha256(
            self.regime_feature_identity,
            "family robustness regime feature identity",
        )
        _require_token(
            self.regime_feature_id,
            "family robustness regime feature id",
        )
        _require_token(
            self.regime_feature_version,
            "family robustness regime feature version",
        )
        if self.schema_version != ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported family robustness config schema")
        if self.engine_version != ML_FAMILY_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported family robustness config engine")
        if not MIN_ROBUSTNESS_FEATURES <= len(self.feature_identities) <= (
            MAX_ROBUSTNESS_FEATURES
        ):
            raise ValueError("family robustness v1 requires 2..6 features")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError(
                "family robustness feature identities must be sorted and unique"
            )
        if self.regime_feature_identity not in self.feature_identities:
            raise ValueError(
                "family robustness regime feature must belong to feature set"
            )
        if self.max_feature_ablations != len(self.feature_identities):
            raise ValueError(
                "family robustness must ablate every feature exactly once"
            )
        if self.automatic_family_selection:
            raise ValueError("automatic family selection is closed")
        if self.automatic_feature_selection:
            raise ValueError("automatic feature selection is closed")
        if self.automatic_regime_selection:
            raise ValueError("automatic regime selection is closed")
        if self.model_refit_allowed:
            raise ValueError("family robustness cannot refit models")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("family robustness config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyFeatureAblationResult:
    result_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    omitted_feature_identity: str
    omitted_feature_id: str
    omitted_feature_version: str
    baseline_selected_observation_identities: tuple[str, ...]
    ablated_selected_observation_identities: tuple[str, ...]
    baseline_positive_prediction_count: int
    ablated_positive_prediction_count: int
    changed_prediction_count: int
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    model_refit_performed: bool = False
    accepted_prediction_set_mutated: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.result_identity, "family ablation result identity"),
            (self.fold_identity, "family ablation fold identity"),
            (self.model_identity, "family ablation model identity"),
            (self.evaluation_identity, "family ablation evaluation identity"),
            (
                self.omitted_feature_identity,
                "family ablation omitted feature identity",
            ),
        ):
            _require_sha256(value, label)
        _require_token(self.omitted_feature_id, "family ablation feature id")
        _require_token(
            self.omitted_feature_version,
            "family ablation feature version",
        )
        if self.schema_version != ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported family ablation schema")
        if self.engine_version != ML_FAMILY_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported family ablation engine")
        if self.family not in FIXED_FAMILY_SET:
            raise ValueError("family ablation is outside accepted family set")
        if self.fold_index < 0:
            raise ValueError("family ablation fold index must be non-negative")
        for identities, label in (
            (
                self.baseline_selected_observation_identities,
                "baseline selection",
            ),
            (
                self.ablated_selected_observation_identities,
                "ablated selection",
            ),
        ):
            if tuple(sorted(set(identities))) != identities:
                raise ValueError(
                    f"family ablation {label} must be sorted and unique"
                )
        if self.baseline_positive_prediction_count != len(
            self.baseline_selected_observation_identities
        ):
            raise ValueError("family ablation baseline count mismatch")
        if self.ablated_positive_prediction_count != len(
            self.ablated_selected_observation_identities
        ):
            raise ValueError("family ablation selected count mismatch")
        if self.changed_prediction_count < 0:
            raise ValueError("family ablation changed count must be non-negative")
        _validate_metrics(
            selected_count=self.ablated_positive_prediction_count,
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
            average_net_r=self.average_net_r,
            label="family ablation",
        )
        if self.model_refit_performed:
            raise ValueError("family ablation cannot refit models")
        if self.accepted_prediction_set_mutated:
            raise ValueError("family ablation cannot mutate accepted predictions")
        if self.result_identity != canonical_sha256(_ablation_payload(self)):
            raise ValueError("family ablation result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyRegimeSliceResult:
    result_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    regime_feature_identity: str
    regime_feature_id: str
    regime_feature_version: str
    regime_value: str
    status: MLFamilyRegimeEvidenceStatus
    observation_identities: tuple[str, ...]
    positive_prediction_count: int
    selected_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None

    def __post_init__(self) -> None:
        for value, label in (
            (self.result_identity, "family regime result identity"),
            (self.fold_identity, "family regime fold identity"),
            (self.model_identity, "family regime model identity"),
            (self.evaluation_identity, "family regime evaluation identity"),
            (
                self.regime_feature_identity,
                "family regime feature identity",
            ),
        ):
            _require_sha256(value, label)
        _require_token(self.regime_feature_id, "family regime feature id")
        _require_token(
            self.regime_feature_version,
            "family regime feature version",
        )
        _require_token(self.regime_value, "family regime value")
        if self.schema_version != ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported family regime schema")
        if self.engine_version != ML_FAMILY_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported family regime engine")
        if self.family not in FIXED_FAMILY_SET:
            raise ValueError("family regime is outside accepted family set")
        if self.fold_index < 0:
            raise ValueError("family regime fold index must be non-negative")
        if tuple(sorted(set(self.observation_identities))) != (
            self.observation_identities
        ):
            raise ValueError("family regime observations must be sorted and unique")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "family regime selected observations must be sorted and unique"
            )
        if self.positive_prediction_count != len(
            self.selected_observation_identities
        ):
            raise ValueError("family regime selected count mismatch")
        if not self.observation_identities:
            if self.status is not MLFamilyRegimeEvidenceStatus.NO_EVIDENCE:
                raise ValueError("empty family regime must be explicit no-evidence")
            if self.positive_prediction_count:
                raise ValueError("empty family regime cannot have predictions")
        elif self.status is not MLFamilyRegimeEvidenceStatus.OBSERVED:
            raise ValueError("observed family regime must use observed status")
        _validate_metrics(
            selected_count=self.positive_prediction_count,
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
            average_net_r=self.average_net_r,
            label="family regime",
        )
        if self.result_identity != canonical_sha256(_regime_payload(self)):
            raise ValueError("family regime result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyRobustnessFoldResult:
    result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    comparison_identity: str
    family_cost_stress_fold_result_identity: str
    reference_ablation_result_identities: tuple[str, ...]
    challenger_ablation_result_identities: tuple[str, ...]
    reference_regime_result_identities: tuple[str, ...]
    challenger_regime_result_identities: tuple[str, ...]
    automatic_family_selection: bool = False
    automatic_feature_selection: bool = False
    automatic_regime_selection: bool = False
    aggregate_winner_selection: bool = False
    model_refit_performed: bool = False
    accepted_prediction_set_mutated: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.result_identity, "family robustness fold result identity"),
            (self.fold_identity, "family robustness fold identity"),
            (self.comparison_identity, "family robustness comparison identity"),
            (
                self.family_cost_stress_fold_result_identity,
                "family robustness cost-stress fold identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported family robustness fold schema")
        if self.engine_version != ML_FAMILY_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported family robustness fold engine")
        if self.fold_index < 0:
            raise ValueError("family robustness fold index must be non-negative")
        for identities, label in (
            (
                self.reference_ablation_result_identities,
                "reference ablation",
            ),
            (
                self.challenger_ablation_result_identities,
                "challenger ablation",
            ),
            (
                self.reference_regime_result_identities,
                "reference regime",
            ),
            (
                self.challenger_regime_result_identities,
                "challenger regime",
            ),
        ):
            if not identities:
                raise ValueError(
                    f"family robustness requires {label} results"
                )
            for identity in identities:
                _require_sha256(identity, f"family robustness {label} identity")
            if tuple(sorted(set(identities))) != identities:
                raise ValueError(
                    f"family robustness {label} identities must be sorted and unique"
                )
        if (
            self.automatic_family_selection
            or self.automatic_feature_selection
            or self.automatic_regime_selection
            or self.aggregate_winner_selection
            or self.model_refit_performed
            or self.accepted_prediction_set_mutated
        ):
            raise ValueError(
                "family robustness fold cannot select, refit or mutate predictions"
            )
        if self.result_identity != canonical_sha256(_fold_payload(self)):
            raise ValueError("family robustness fold result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyFoldSensitivitySummary:
    summary_identity: str
    schema_version: str
    engine_version: str
    rows: tuple[
        tuple[
            int,
            MLExpandedFamily,
            Decimal | None,
            Decimal | None,
            int,
        ],
        ...,
    ]
    automatic_fold_selection: bool = False
    automatic_family_selection: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.summary_identity, "family sensitivity identity")
        if self.schema_version != ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported family sensitivity schema")
        if self.engine_version != ML_FAMILY_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported family sensitivity engine")
        if not self.rows:
            raise ValueError("family sensitivity requires rows")
        expected_pairs: list[tuple[int, MLExpandedFamily]] = []
        max_fold = max(item[0] for item in self.rows)
        for fold_index in range(max_fold + 1):
            for family in FIXED_FAMILY_SET:
                expected_pairs.append((fold_index, family))
        actual_pairs = [(item[0], item[1]) for item in self.rows]
        if actual_pairs != expected_pairs:
            raise ValueError(
                "family sensitivity rows must cover every fold/family in order"
            )
        if any(item[4] < 0 for item in self.rows):
            raise ValueError("family sensitivity changed counts must be non-negative")
        if self.automatic_fold_selection:
            raise ValueError("automatic fold selection is closed")
        if self.automatic_family_selection:
            raise ValueError("automatic family selection is closed")
        if self.summary_identity != canonical_sha256(
            _sensitivity_payload(self)
        ):
            raise ValueError("family sensitivity identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyRobustnessManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLFamilyRobustnessSemantic
    config_identity: str
    family_expansion_run_identity: str
    family_cost_stress_run_identity: str
    family_set: tuple[MLExpandedFamily, ...]
    fold_identities: tuple[str, ...]
    fold_result_identities: tuple[str, ...]
    fold_sensitivity_identity: str
    automatic_family_selection: bool = False
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
        for value, label in (
            (self.run_identity, "family robustness run identity"),
            (self.config_identity, "family robustness config identity"),
            (
                self.family_expansion_run_identity,
                "family robustness expansion identity",
            ),
            (
                self.family_cost_stress_run_identity,
                "family robustness cost-stress identity",
            ),
            (
                self.fold_sensitivity_identity,
                "family robustness sensitivity identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION:
            raise ValueError("unsupported family robustness manifest schema")
        if self.engine_version != ML_FAMILY_ROBUSTNESS_ENGINE_VERSION:
            raise ValueError("unsupported family robustness manifest engine")
        if self.semantic is not (
            MLFamilyRobustnessSemantic
            .DESCRIPTIVE_FAMILY_ROBUSTNESS_NOT_SELECTION
        ):
            raise ValueError("unsupported family robustness semantic")
        if self.family_set != FIXED_FAMILY_SET:
            raise ValueError("family robustness manifest family set mismatch")
        if not self.fold_identities:
            raise ValueError("family robustness manifest requires folds")
        if len(self.fold_identities) != len(self.fold_result_identities):
            raise ValueError("family robustness fold/result count mismatch")
        for identities, label in (
            (self.fold_identities, "fold"),
            (self.fold_result_identities, "fold result"),
        ):
            for identity in identities:
                _require_sha256(identity, f"family robustness {label} identity")
            if len(set(identities)) != len(identities):
                raise ValueError(
                    f"family robustness {label} identities must be unique"
                )
        if (
            self.automatic_family_selection
            or self.automatic_feature_selection
            or self.automatic_regime_selection
            or self.aggregate_winner_selection
            or self.model_refit_performed
            or self.accepted_prediction_set_mutated
            or self.calibrated_probability_claim
        ):
            raise ValueError(
                "family robustness cannot select, refit, mutate or calibrate"
            )
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("family robustness has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("family robustness run identity mismatch")


def build_ml_family_robustness_config(
    features: Sequence[SymbolicFeatureSpec],
    *,
    regime_feature_id: str,
) -> MLFamilyRobustnessConfig:
    ordered = tuple(sorted(features, key=lambda item: item.feature_id))
    if not MIN_ROBUSTNESS_FEATURES <= len(ordered) <= MAX_ROBUSTNESS_FEATURES:
        raise ValueError("family robustness v1 requires 2..6 features")
    feature_ids = tuple(item.feature_id for item in ordered)
    if feature_ids != tuple(sorted(set(feature_ids))):
        raise ValueError("family robustness features must have unique ids")
    regime_matches = tuple(
        item for item in ordered if item.feature_id == regime_feature_id
    )
    if len(regime_matches) != 1:
        raise ValueError("family robustness requires one explicit regime feature")
    regime = regime_matches[0]
    feature_identities = tuple(sorted(item.feature_identity for item in ordered))
    payload = {
        "automatic_family_selection": False,
        "automatic_feature_selection": False,
        "automatic_regime_selection": False,
        "engine_version": ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        "feature_identities": feature_identities,
        "max_feature_ablations": len(ordered),
        "model_refit_allowed": False,
        "regime_feature_id": regime.feature_id,
        "regime_feature_identity": regime.feature_identity,
        "regime_feature_version": regime.feature_version,
        "schema_version": ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
    }
    return MLFamilyRobustnessConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        feature_identities=feature_identities,
        regime_feature_identity=regime.feature_identity,
        regime_feature_id=regime.feature_id,
        regime_feature_version=regime.feature_version,
        max_feature_ablations=len(ordered),
    )


def run_ml_family_robustness_ablation(
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
    *,
    regime_feature_id: str,
    config: MLFamilyRobustnessConfig | None = None,
) -> tuple[
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
]:
    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    effective_config = config or build_ml_family_robustness_config(
        ordered_features,
        regime_feature_id=regime_feature_id,
    )
    _validate_config_features(
        effective_config,
        ordered_features,
        regime_feature_id=regime_feature_id,
    )
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    references = tuple(reference_artifacts)
    expected_expansion = run_ml_family_expansion(
        ordered_features,
        ordered_folds,
        references,
    )
    if expected_expansion != family_expansion_evidence:
        raise ValueError(
            "family robustness requires exact accepted family expansion evidence"
        )
    expected_cost_stress = run_ml_family_cost_stress(
        ordered_features,
        ordered_folds,
        references,
        family_expansion_evidence,
    )
    if expected_cost_stress != family_cost_stress_evidence:
        raise ValueError(
            "family robustness requires exact accepted family cost-stress evidence"
        )

    challengers, comparisons, expansion_manifest = family_expansion_evidence
    stress_groups, stress_fold_results, stress_manifest = (
        family_cost_stress_evidence
    )
    regime_feature = next(
        item
        for item in ordered_features
        if item.feature_id == effective_config.regime_feature_id
    )

    ablation_groups: list[
        tuple[
            tuple[MLFamilyFeatureAblationResult, ...],
            tuple[MLFamilyFeatureAblationResult, ...],
        ]
    ] = []
    regime_groups: list[
        tuple[
            tuple[MLFamilyRegimeSliceResult, ...],
            tuple[MLFamilyRegimeSliceResult, ...],
        ]
    ] = []
    fold_results: list[MLFamilyRobustnessFoldResult] = []

    for (
        fold,
        reference,
        challenger,
        comparison,
        stress_pair,
        stress_fold,
    ) in zip(
        ordered_folds,
        references,
        challengers,
        comparisons,
        stress_groups,
        stress_fold_results,
        strict=True,
    ):
        reference_model, _, reference_evaluation = reference
        challenger_model, _, challenger_evaluation = challenger
        _validate_fold_bindings(
            fold=fold,
            comparison=comparison,
            reference_model=reference_model,
            reference_evaluation=reference_evaluation,
            challenger_model=challenger_model,
            challenger_evaluation=challenger_evaluation,
            stress_fold=stress_fold,
        )
        observations = tuple(
            sorted(
                fold.evaluation_observations,
                key=lambda item: item.observation_identity,
            )
        )
        reference_baseline = _accepted_prediction_map(
            family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
            reference_model=reference_model,
            challenger_model=challenger_model,
            observations=observations,
        )
        challenger_baseline = _accepted_prediction_map(
            family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
            reference_model=reference_model,
            challenger_model=challenger_model,
            observations=observations,
        )
        _validate_selected_set(
            reference_baseline,
            reference_evaluation.selected_observation_identities,
            "reference",
        )
        _validate_selected_set(
            challenger_baseline,
            challenger_evaluation.selected_observation_identities,
            "challenger",
        )

        reference_ablations = tuple(
            _build_ablation(
                family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
                fold=fold,
                reference_model=reference_model,
                challenger_model=challenger_model,
                evaluation_identity=reference_evaluation.evaluation_identity,
                baseline=reference_baseline,
                baseline_selected=(
                    reference_evaluation.selected_observation_identities
                ),
                observations=observations,
                omitted_feature=feature,
            )
            for feature in ordered_features
        )
        challenger_ablations = tuple(
            _build_ablation(
                family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
                fold=fold,
                reference_model=reference_model,
                challenger_model=challenger_model,
                evaluation_identity=challenger_evaluation.evaluation_identity,
                baseline=challenger_baseline,
                baseline_selected=(
                    challenger_evaluation.selected_observation_identities
                ),
                observations=observations,
                omitted_feature=feature,
            )
            for feature in ordered_features
        )
        reference_regimes = tuple(
            _build_regime_slice(
                family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
                fold=fold,
                model_identity=reference_model.model_identity,
                evaluation_identity=reference_evaluation.evaluation_identity,
                baseline=reference_baseline,
                observations=observations,
                regime_feature=regime_feature,
                regime_value=value,
            )
            for value in regime_feature.allowed_values
        )
        challenger_regimes = tuple(
            _build_regime_slice(
                family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
                fold=fold,
                model_identity=challenger_model.model_identity,
                evaluation_identity=challenger_evaluation.evaluation_identity,
                baseline=challenger_baseline,
                observations=observations,
                regime_feature=regime_feature,
                regime_value=value,
            )
            for value in regime_feature.allowed_values
        )
        payload = {
            "accepted_prediction_set_mutated": False,
            "aggregate_winner_selection": False,
            "automatic_family_selection": False,
            "automatic_feature_selection": False,
            "automatic_regime_selection": False,
            "challenger_ablation_result_identities": tuple(
                sorted(item.result_identity for item in challenger_ablations)
            ),
            "challenger_regime_result_identities": tuple(
                sorted(item.result_identity for item in challenger_regimes)
            ),
            "comparison_identity": comparison.comparison_identity,
            "engine_version": ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
            "family_cost_stress_fold_result_identity": (
                stress_fold.result_identity
            ),
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "model_refit_performed": False,
            "reference_ablation_result_identities": tuple(
                sorted(item.result_identity for item in reference_ablations)
            ),
            "reference_regime_result_identities": tuple(
                sorted(item.result_identity for item in reference_regimes)
            ),
            "schema_version": ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        }
        fold_result = MLFamilyRobustnessFoldResult(
            result_identity=canonical_sha256(payload),
            schema_version=ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
            engine_version=ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
            fold_identity=fold.fold_identity,
            fold_index=fold.fold_index,
            comparison_identity=comparison.comparison_identity,
            family_cost_stress_fold_result_identity=stress_fold.result_identity,
            reference_ablation_result_identities=tuple(
                sorted(item.result_identity for item in reference_ablations)
            ),
            challenger_ablation_result_identities=tuple(
                sorted(item.result_identity for item in challenger_ablations)
            ),
            reference_regime_result_identities=tuple(
                sorted(item.result_identity for item in reference_regimes)
            ),
            challenger_regime_result_identities=tuple(
                sorted(item.result_identity for item in challenger_regimes)
            ),
        )
        ablation_groups.append(
            (reference_ablations, challenger_ablations)
        )
        regime_groups.append((reference_regimes, challenger_regimes))
        fold_results.append(fold_result)

    sensitivity = _build_sensitivity(
        ordered_folds,
        references,
        challengers,
        stress_groups,
        tuple(ablation_groups),
    )
    fold_ids = tuple(item.fold_identity for item in ordered_folds)
    fold_result_ids = tuple(item.result_identity for item in fold_results)
    manifest_payload = {
        "accepted_prediction_set_mutated": False,
        "aggregate_winner_selection": False,
        "automatic_family_selection": False,
        "automatic_feature_selection": False,
        "automatic_regime_selection": False,
        "calibrated_probability_claim": False,
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        "family_cost_stress_run_identity": stress_manifest.run_identity,
        "family_expansion_run_identity": expansion_manifest.run_identity,
        "family_set": FIXED_FAMILY_SET,
        "fold_identities": fold_ids,
        "fold_result_identities": fold_result_ids,
        "fold_sensitivity_identity": sensitivity.summary_identity,
        "model_refit_performed": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        "semantic": (
            MLFamilyRobustnessSemantic
            .DESCRIPTIVE_FAMILY_ROBUSTNESS_NOT_SELECTION
        ),
        "untouched_forward_used": False,
    }
    manifest = MLFamilyRobustnessManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        semantic=(
            MLFamilyRobustnessSemantic
            .DESCRIPTIVE_FAMILY_ROBUSTNESS_NOT_SELECTION
        ),
        config_identity=effective_config.config_identity,
        family_expansion_run_identity=expansion_manifest.run_identity,
        family_cost_stress_run_identity=stress_manifest.run_identity,
        family_set=FIXED_FAMILY_SET,
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


def _accepted_prediction_map(
    *,
    family: MLExpandedFamily,
    reference_model: MLBaselineModel,
    challenger_model: MLSignVoteModel,
    observations: tuple[ClusterResearchObservation, ...],
) -> dict[str, bool]:
    return {
        item.observation_identity: (
            _score(
                family=family,
                reference_model=reference_model,
                challenger_model=challenger_model,
                observation=item,
                omitted_feature_identity=None,
            )
            > 0
        )
        for item in observations
    }


def _build_ablation(
    *,
    family: MLExpandedFamily,
    fold: MLWalkForwardFold,
    reference_model: MLBaselineModel,
    challenger_model: MLSignVoteModel,
    evaluation_identity: str,
    baseline: dict[str, bool],
    baseline_selected: tuple[str, ...],
    observations: tuple[ClusterResearchObservation, ...],
    omitted_feature: SymbolicFeatureSpec,
) -> MLFamilyFeatureAblationResult:
    model_identity = (
        reference_model.model_identity
        if family is MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE
        else challenger_model.model_identity
    )
    ablated = {
        item.observation_identity: (
            _score(
                family=family,
                reference_model=reference_model,
                challenger_model=challenger_model,
                observation=item,
                omitted_feature_identity=omitted_feature.feature_identity,
            )
            > 0
        )
        for item in observations
    }
    selected_ids = tuple(
        sorted(identity for identity, selected in ablated.items() if selected)
    )
    selected_set = set(selected_ids)
    selected = tuple(
        item
        for item in observations
        if item.observation_identity in selected_set
    )
    gross, cost, net, average = _selected_metrics(selected)
    changed = sum(
        baseline[identity] != ablated[identity] for identity in baseline
    )
    payload = {
        "accepted_prediction_set_mutated": False,
        "ablated_positive_prediction_count": len(selected_ids),
        "ablated_selected_observation_identities": selected_ids,
        "average_net_r": average,
        "baseline_positive_prediction_count": len(baseline_selected),
        "baseline_selected_observation_identities": baseline_selected,
        "changed_prediction_count": changed,
        "engine_version": ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        "evaluation_identity": evaluation_identity,
        "explicit_cost_r_total": cost,
        "family": family,
        "fold_identity": fold.fold_identity,
        "fold_index": fold.fold_index,
        "gross_r_total": gross,
        "model_identity": model_identity,
        "model_refit_performed": False,
        "net_r_total": net,
        "omitted_feature_id": omitted_feature.feature_id,
        "omitted_feature_identity": omitted_feature.feature_identity,
        "omitted_feature_version": omitted_feature.feature_version,
        "schema_version": ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
    }
    return MLFamilyFeatureAblationResult(
        result_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        family=family,
        fold_identity=fold.fold_identity,
        fold_index=fold.fold_index,
        model_identity=model_identity,
        evaluation_identity=evaluation_identity,
        omitted_feature_identity=omitted_feature.feature_identity,
        omitted_feature_id=omitted_feature.feature_id,
        omitted_feature_version=omitted_feature.feature_version,
        baseline_selected_observation_identities=baseline_selected,
        ablated_selected_observation_identities=selected_ids,
        baseline_positive_prediction_count=len(baseline_selected),
        ablated_positive_prediction_count=len(selected_ids),
        changed_prediction_count=changed,
        gross_r_total=gross,
        explicit_cost_r_total=cost,
        net_r_total=net,
        average_net_r=average,
    )


def _build_regime_slice(
    *,
    family: MLExpandedFamily,
    fold: MLWalkForwardFold,
    model_identity: str,
    evaluation_identity: str,
    baseline: dict[str, bool],
    observations: tuple[ClusterResearchObservation, ...],
    regime_feature: SymbolicFeatureSpec,
    regime_value: str,
) -> MLFamilyRegimeSliceResult:
    matching = tuple(
        item
        for item in observations
        if _reading_value(item, regime_feature.feature_id) == regime_value
    )
    observation_ids = tuple(
        sorted(item.observation_identity for item in matching)
    )
    selected = tuple(
        item for item in matching if baseline[item.observation_identity]
    )
    selected_ids = tuple(
        sorted(item.observation_identity for item in selected)
    )
    gross, cost, net, average = _selected_metrics(selected)
    status = (
        MLFamilyRegimeEvidenceStatus.OBSERVED
        if matching
        else MLFamilyRegimeEvidenceStatus.NO_EVIDENCE
    )
    payload = {
        "average_net_r": average,
        "engine_version": ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        "evaluation_identity": evaluation_identity,
        "explicit_cost_r_total": cost,
        "family": family,
        "fold_identity": fold.fold_identity,
        "fold_index": fold.fold_index,
        "gross_r_total": gross,
        "model_identity": model_identity,
        "net_r_total": net,
        "observation_identities": observation_ids,
        "positive_prediction_count": len(selected_ids),
        "regime_feature_id": regime_feature.feature_id,
        "regime_feature_identity": regime_feature.feature_identity,
        "regime_feature_version": regime_feature.feature_version,
        "regime_value": regime_value,
        "schema_version": ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        "selected_observation_identities": selected_ids,
        "status": status,
    }
    return MLFamilyRegimeSliceResult(
        result_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        family=family,
        fold_identity=fold.fold_identity,
        fold_index=fold.fold_index,
        model_identity=model_identity,
        evaluation_identity=evaluation_identity,
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


def _score(
    *,
    family: MLExpandedFamily,
    reference_model: MLBaselineModel,
    challenger_model: MLSignVoteModel,
    observation: ClusterResearchObservation,
    omitted_feature_identity: str | None,
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
        raise ValueError("unsupported family robustness family")
    for reading in observation.feature_readings:
        if reading.feature_identity == omitted_feature_identity:
            continue
        score += values.get(
            (reading.feature_id, reading.feature_version, reading.value),
            0,
        )
    return score


def _build_sensitivity(
    folds: tuple[MLWalkForwardFold, ...],
    references: tuple[
        tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation],
        ...,
    ],
    challengers: tuple[
        tuple[MLSignVoteModel, MLFamilyTrainingManifest, MLFamilyEvaluation],
        ...,
    ],
    stress_groups: tuple[
        tuple[
            tuple[MLFamilyCostStressScenario, ...],
            tuple[MLFamilyCostStressScenario, ...],
        ],
        ...,
    ],
    ablation_groups: tuple[
        tuple[
            tuple[MLFamilyFeatureAblationResult, ...],
            tuple[MLFamilyFeatureAblationResult, ...],
        ],
        ...,
    ],
) -> MLFamilyFoldSensitivitySummary:
    rows: list[
        tuple[
            int,
            MLExpandedFamily,
            Decimal | None,
            Decimal | None,
            int,
        ]
    ] = []
    for index, _ in enumerate(folds):
        reference_eval = references[index][2]
        challenger_eval = challengers[index][2]
        reference_stress, challenger_stress = stress_groups[index]
        reference_ablation, challenger_ablation = ablation_groups[index]
        rows.append(
            (
                index,
                MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
                reference_eval.net_r_total,
                reference_stress[-1].stressed_net_r_total,
                sum(item.changed_prediction_count for item in reference_ablation),
            )
        )
        rows.append(
            (
                index,
                MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
                challenger_eval.net_r_total,
                challenger_stress[-1].stressed_net_r_total,
                sum(item.changed_prediction_count for item in challenger_ablation),
            )
        )
    result_rows = tuple(rows)
    payload = {
        "automatic_family_selection": False,
        "automatic_fold_selection": False,
        "engine_version": ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        "rows": result_rows,
        "schema_version": ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
    }
    return MLFamilyFoldSensitivitySummary(
        summary_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_ROBUSTNESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_ROBUSTNESS_ENGINE_VERSION,
        rows=result_rows,
    )


def _validate_selected_set(
    baseline: dict[str, bool],
    selected: tuple[str, ...],
    label: str,
) -> None:
    expected = tuple(
        sorted(identity for identity, value in baseline.items() if value)
    )
    if expected != selected:
        raise ValueError(
            f"family robustness {label} accepted prediction set mismatch"
        )


def _validate_fold_bindings(
    *,
    fold: MLWalkForwardFold,
    comparison: MLFamilyFoldComparison,
    reference_model: MLBaselineModel,
    reference_evaluation: MLEvaluation,
    challenger_model: MLSignVoteModel,
    challenger_evaluation: MLFamilyEvaluation,
    stress_fold: MLFamilyCostStressFoldResult,
) -> None:
    if comparison.fold_identity != fold.fold_identity:
        raise ValueError("family robustness comparison/fold mismatch")
    if comparison.reference_model_identity != reference_model.model_identity:
        raise ValueError("family robustness reference model mismatch")
    if comparison.reference_evaluation_identity != (
        reference_evaluation.evaluation_identity
    ):
        raise ValueError("family robustness reference evaluation mismatch")
    if comparison.challenger_model_identity != challenger_model.model_identity:
        raise ValueError("family robustness challenger model mismatch")
    if comparison.challenger_evaluation_identity != (
        challenger_evaluation.evaluation_identity
    ):
        raise ValueError("family robustness challenger evaluation mismatch")
    if stress_fold.fold_identity != fold.fold_identity:
        raise ValueError("family robustness cost-stress fold mismatch")
    if stress_fold.comparison_identity != comparison.comparison_identity:
        raise ValueError("family robustness cost-stress comparison mismatch")


def _validate_config_features(
    config: MLFamilyRobustnessConfig,
    features: tuple[SymbolicFeatureSpec, ...],
    *,
    regime_feature_id: str,
) -> None:
    identities = tuple(sorted(item.feature_identity for item in features))
    if identities != config.feature_identities:
        raise ValueError("family robustness config feature mismatch")
    matches = tuple(
        item for item in features if item.feature_id == regime_feature_id
    )
    if len(matches) != 1:
        raise ValueError("family robustness requires one explicit regime feature")
    regime = matches[0]
    if (
        regime.feature_identity != config.regime_feature_identity
        or regime.feature_id != config.regime_feature_id
        or regime.feature_version != config.regime_feature_version
    ):
        raise ValueError("family robustness regime feature mismatch")


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
        raise ValueError("family robustness regime feature coverage mismatch")
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
            raise ValueError(f"{label} cannot fabricate metrics")
        return
    if any(item is None for item in metrics):
        raise ValueError(f"{label} requires complete metrics")
    assert gross_r_total is not None
    assert explicit_cost_r_total is not None
    assert net_r_total is not None
    assert average_net_r is not None
    if explicit_cost_r_total < 0:
        raise ValueError(f"{label} cost cannot be negative")
    if net_r_total != gross_r_total - explicit_cost_r_total:
        raise ValueError(f"{label} net-R accounting mismatch")
    if average_net_r != net_r_total / Decimal(selected_count):
        raise ValueError(f"{label} average net-R mismatch")


def _config_payload(config: MLFamilyRobustnessConfig) -> dict[str, object]:
    return {
        "automatic_family_selection": config.automatic_family_selection,
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


def _ablation_payload(
    result: MLFamilyFeatureAblationResult,
) -> dict[str, object]:
    return {
        "accepted_prediction_set_mutated": result.accepted_prediction_set_mutated,
        "ablated_positive_prediction_count": (
            result.ablated_positive_prediction_count
        ),
        "ablated_selected_observation_identities": (
            result.ablated_selected_observation_identities
        ),
        "average_net_r": result.average_net_r,
        "baseline_positive_prediction_count": (
            result.baseline_positive_prediction_count
        ),
        "baseline_selected_observation_identities": (
            result.baseline_selected_observation_identities
        ),
        "changed_prediction_count": result.changed_prediction_count,
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "explicit_cost_r_total": result.explicit_cost_r_total,
        "family": result.family,
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
    }


def _regime_payload(
    result: MLFamilyRegimeSliceResult,
) -> dict[str, object]:
    return {
        "average_net_r": result.average_net_r,
        "engine_version": result.engine_version,
        "evaluation_identity": result.evaluation_identity,
        "explicit_cost_r_total": result.explicit_cost_r_total,
        "family": result.family,
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


def _fold_payload(
    result: MLFamilyRobustnessFoldResult,
) -> dict[str, object]:
    return {
        "accepted_prediction_set_mutated": (
            result.accepted_prediction_set_mutated
        ),
        "aggregate_winner_selection": result.aggregate_winner_selection,
        "automatic_family_selection": result.automatic_family_selection,
        "automatic_feature_selection": result.automatic_feature_selection,
        "automatic_regime_selection": result.automatic_regime_selection,
        "challenger_ablation_result_identities": (
            result.challenger_ablation_result_identities
        ),
        "challenger_regime_result_identities": (
            result.challenger_regime_result_identities
        ),
        "comparison_identity": result.comparison_identity,
        "engine_version": result.engine_version,
        "family_cost_stress_fold_result_identity": (
            result.family_cost_stress_fold_result_identity
        ),
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "model_refit_performed": result.model_refit_performed,
        "reference_ablation_result_identities": (
            result.reference_ablation_result_identities
        ),
        "reference_regime_result_identities": (
            result.reference_regime_result_identities
        ),
        "schema_version": result.schema_version,
    }


def _sensitivity_payload(
    summary: MLFamilyFoldSensitivitySummary,
) -> dict[str, object]:
    return {
        "automatic_family_selection": summary.automatic_family_selection,
        "automatic_fold_selection": summary.automatic_fold_selection,
        "engine_version": summary.engine_version,
        "rows": summary.rows,
        "schema_version": summary.schema_version,
    }


def _manifest_payload(
    manifest: MLFamilyRobustnessManifest,
) -> dict[str, object]:
    return {
        "accepted_prediction_set_mutated": (
            manifest.accepted_prediction_set_mutated
        ),
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_family_selection": manifest.automatic_family_selection,
        "automatic_feature_selection": manifest.automatic_feature_selection,
        "automatic_regime_selection": manifest.automatic_regime_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "family_cost_stress_run_identity": (
            manifest.family_cost_stress_run_identity
        ),
        "family_expansion_run_identity": (
            manifest.family_expansion_run_identity
        ),
        "family_set": manifest.family_set,
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
