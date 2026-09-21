"""Deterministic transaction-cost stress for the accepted bounded ML family set."""

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
from research.alpha_factory.ml_cost_stress import DEFAULT_COST_MULTIPLIERS
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

ML_FAMILY_COST_STRESS_ENGINE_VERSION = (
    "alpha-factory-ml-family-cost-stress-v1/1"
)
ML_FAMILY_COST_STRESS_SCHEMA_VERSION = (
    "alpha-factory-ml-family-cost-stress-schema-v1/1"
)
REAL_CAPITAL = 0


class MLFamilyCostStressSemantic(StrEnum):
    DESCRIPTIVE_FAMILY_COST_STRESS_NOT_SELECTION = (
        "descriptive_family_cost_stress_not_selection"
    )


@dataclass(frozen=True, slots=True)
class MLFamilyCostStressConfig:
    config_identity: str
    schema_version: str
    engine_version: str
    multipliers: tuple[Decimal, ...]
    automatic_family_selection: bool = False
    automatic_scenario_selection: bool = False
    model_refit_allowed: bool = False
    prediction_change_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.config_identity, "family cost-stress config identity")
        if self.schema_version != ML_FAMILY_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported family cost-stress config schema")
        if self.engine_version != ML_FAMILY_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported family cost-stress config engine")
        if self.multipliers != DEFAULT_COST_MULTIPLIERS:
            raise ValueError("family cost-stress multiplier grid is fixed")
        if any(item < Decimal(1) for item in self.multipliers):
            raise ValueError("family cost stress cannot reduce costs")
        if self.automatic_family_selection:
            raise ValueError("automatic family selection is closed")
        if self.automatic_scenario_selection:
            raise ValueError("automatic stress scenario selection is closed")
        if self.model_refit_allowed:
            raise ValueError("family cost stress cannot refit models")
        if self.prediction_change_allowed:
            raise ValueError("family cost stress cannot change predictions")
        if self.config_identity != canonical_sha256(_config_payload(self)):
            raise ValueError("family cost-stress config identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyCostStressScenario:
    scenario_identity: str
    schema_version: str
    engine_version: str
    family: MLExpandedFamily
    config_identity: str
    fold_identity: str
    fold_index: int
    model_identity: str
    evaluation_identity: str
    multiplier: Decimal
    selected_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    original_cost_r_total: Decimal | None
    stressed_cost_r_total: Decimal | None
    original_net_r_total: Decimal | None
    stressed_net_r_total: Decimal | None
    model_refit_performed: bool = False
    prediction_set_changed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.scenario_identity, "family stress scenario identity"),
            (self.config_identity, "family stress config identity"),
            (self.fold_identity, "family stress fold identity"),
            (self.model_identity, "family stress model identity"),
            (self.evaluation_identity, "family stress evaluation identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported family stress scenario schema")
        if self.engine_version != ML_FAMILY_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported family stress scenario engine")
        if self.family not in FIXED_FAMILY_SET:
            raise ValueError("family stress scenario is outside accepted family set")
        if self.fold_index < 0:
            raise ValueError("family stress fold index must be non-negative")
        if self.multiplier not in DEFAULT_COST_MULTIPLIERS:
            raise ValueError("family stress scenario multiplier is outside grid")
        if tuple(sorted(set(self.selected_observation_identities))) != (
            self.selected_observation_identities
        ):
            raise ValueError(
                "family stress selected observations must be sorted and unique"
            )
        if self.model_refit_performed:
            raise ValueError("family stress cannot refit models")
        if self.prediction_set_changed:
            raise ValueError("family stress cannot change predictions")
        _validate_metrics(
            selected_count=len(self.selected_observation_identities),
            multiplier=self.multiplier,
            gross_r_total=self.gross_r_total,
            original_cost_r_total=self.original_cost_r_total,
            stressed_cost_r_total=self.stressed_cost_r_total,
            original_net_r_total=self.original_net_r_total,
            stressed_net_r_total=self.stressed_net_r_total,
        )
        if self.scenario_identity != canonical_sha256(_scenario_payload(self)):
            raise ValueError("family stress scenario identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyCostStressFoldResult:
    result_identity: str
    schema_version: str
    engine_version: str
    fold_identity: str
    fold_index: int
    comparison_identity: str
    reference_scenario_identities: tuple[str, ...]
    challenger_scenario_identities: tuple[str, ...]
    automatic_family_selection: bool = False
    automatic_scenario_selection: bool = False
    aggregate_winner_selection: bool = False
    model_refit_performed: bool = False
    prediction_set_changed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.result_identity, "family stress fold result identity")
        _require_sha256(self.fold_identity, "family stress fold identity")
        _require_sha256(
            self.comparison_identity,
            "family stress comparison identity",
        )
        if self.schema_version != ML_FAMILY_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported family stress fold schema")
        if self.engine_version != ML_FAMILY_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported family stress fold engine")
        if self.fold_index < 0:
            raise ValueError("family stress fold index must be non-negative")
        for identities, label in (
            (self.reference_scenario_identities, "reference"),
            (self.challenger_scenario_identities, "challenger"),
        ):
            if len(identities) != len(DEFAULT_COST_MULTIPLIERS):
                raise ValueError(
                    f"family stress {label} scenarios must use fixed grid"
                )
            for identity in identities:
                _require_sha256(identity, f"family stress {label} scenario")
            if len(set(identities)) != len(identities):
                raise ValueError(
                    f"family stress {label} scenarios must be unique"
                )
        if (
            self.automatic_family_selection
            or self.automatic_scenario_selection
            or self.aggregate_winner_selection
            or self.model_refit_performed
            or self.prediction_set_changed
        ):
            raise ValueError(
                "family stress fold cannot select, refit or change predictions"
            )
        if self.result_identity != canonical_sha256(_fold_payload(self)):
            raise ValueError("family stress fold result identity mismatch")


@dataclass(frozen=True, slots=True)
class MLFamilyCostStressManifest:
    run_identity: str
    schema_version: str
    engine_version: str
    semantic: MLFamilyCostStressSemantic
    config_identity: str
    family_expansion_run_identity: str
    family_set: tuple[MLExpandedFamily, ...]
    fold_identities: tuple[str, ...]
    fold_result_identities: tuple[str, ...]
    automatic_family_selection: bool = False
    automatic_scenario_selection: bool = False
    aggregate_winner_selection: bool = False
    model_refit_performed: bool = False
    prediction_set_changed: bool = False
    calibrated_probability_claim: bool = False
    untouched_forward_used: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_identity, "family stress run identity"),
            (self.config_identity, "family stress config identity"),
            (
                self.family_expansion_run_identity,
                "family expansion run identity",
            ),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_FAMILY_COST_STRESS_SCHEMA_VERSION:
            raise ValueError("unsupported family stress manifest schema")
        if self.engine_version != ML_FAMILY_COST_STRESS_ENGINE_VERSION:
            raise ValueError("unsupported family stress manifest engine")
        if self.semantic is not (
            MLFamilyCostStressSemantic
            .DESCRIPTIVE_FAMILY_COST_STRESS_NOT_SELECTION
        ):
            raise ValueError("unsupported family stress semantic")
        if self.family_set != FIXED_FAMILY_SET:
            raise ValueError("family stress manifest family set mismatch")
        if not self.fold_identities:
            raise ValueError("family stress manifest requires folds")
        if len(self.fold_identities) != len(self.fold_result_identities):
            raise ValueError("family stress fold/result count mismatch")
        for identities, label in (
            (self.fold_identities, "fold"),
            (self.fold_result_identities, "fold result"),
        ):
            for identity in identities:
                _require_sha256(identity, f"family stress {label} identity")
            if len(set(identities)) != len(identities):
                raise ValueError(
                    f"family stress {label} identities must be unique"
                )
        if (
            self.automatic_family_selection
            or self.automatic_scenario_selection
            or self.aggregate_winner_selection
            or self.model_refit_performed
            or self.prediction_set_changed
            or self.calibrated_probability_claim
        ):
            raise ValueError(
                "family stress manifest cannot select, refit, change or calibrate"
            )
        if self.untouched_forward_used:
            raise ValueError("untouched-forward remains closed")
        if self.production_authority:
            raise ValueError("family stress has no production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.run_identity != canonical_sha256(_manifest_payload(self)):
            raise ValueError("family stress run identity mismatch")


def build_ml_family_cost_stress_config() -> MLFamilyCostStressConfig:
    payload = {
        "automatic_family_selection": False,
        "automatic_scenario_selection": False,
        "engine_version": ML_FAMILY_COST_STRESS_ENGINE_VERSION,
        "model_refit_allowed": False,
        "multipliers": DEFAULT_COST_MULTIPLIERS,
        "prediction_change_allowed": False,
        "schema_version": ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
    }
    return MLFamilyCostStressConfig(
        config_identity=canonical_sha256(payload),
        schema_version=ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_COST_STRESS_ENGINE_VERSION,
        multipliers=DEFAULT_COST_MULTIPLIERS,
    )


def run_ml_family_cost_stress(
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
    *,
    config: MLFamilyCostStressConfig | None = None,
) -> tuple[
    tuple[
        tuple[
            tuple[MLFamilyCostStressScenario, ...],
            tuple[MLFamilyCostStressScenario, ...],
        ],
        ...,
    ],
    tuple[MLFamilyCostStressFoldResult, ...],
    MLFamilyCostStressManifest,
]:
    effective_config = config or build_ml_family_cost_stress_config()
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    references = tuple(reference_artifacts)
    if not ordered_folds:
        raise ValueError("family cost stress requires walk-forward folds")
    if len(ordered_folds) != len(references):
        raise ValueError("family cost stress reference artifact count mismatch")

    expected_expansion = run_ml_family_expansion(
        features,
        ordered_folds,
        references,
    )
    if expected_expansion != family_expansion_evidence:
        raise ValueError(
            "family cost stress requires exact accepted family expansion evidence"
        )
    challengers, comparisons, expansion_manifest = family_expansion_evidence
    if len(challengers) != len(ordered_folds):
        raise ValueError("family cost stress challenger artifact count mismatch")
    if len(comparisons) != len(ordered_folds):
        raise ValueError("family cost stress comparison count mismatch")

    scenario_groups: list[
        tuple[
            tuple[MLFamilyCostStressScenario, ...],
            tuple[MLFamilyCostStressScenario, ...],
        ]
    ] = []
    fold_results: list[MLFamilyCostStressFoldResult] = []

    for fold, reference, challenger, comparison in zip(
        ordered_folds,
        references,
        challengers,
        comparisons,
        strict=True,
    ):
        reference_model, _, reference_evaluation = reference
        challenger_model, _, challenger_evaluation = challenger
        _validate_comparison_bindings(
            fold=fold,
            comparison=comparison,
            reference_model=reference_model,
            reference_evaluation=reference_evaluation,
            challenger_model=challenger_model,
            challenger_evaluation=challenger_evaluation,
        )

        reference_scenarios = _stress_family_evaluation(
            family=MLExpandedFamily.CATEGORICAL_COUNT_REFERENCE,
            fold=fold,
            model_identity=reference_model.model_identity,
            evaluation_identity=reference_evaluation.evaluation_identity,
            selected_observation_identities=(
                reference_evaluation.selected_observation_identities
            ),
            gross_r_total=reference_evaluation.gross_r_total,
            original_cost_r_total=reference_evaluation.explicit_cost_r_total,
            original_net_r_total=reference_evaluation.net_r_total,
            observations=fold.evaluation_observations,
            config=effective_config,
        )
        challenger_scenarios = _stress_family_evaluation(
            family=MLExpandedFamily.CATEGORICAL_SIGN_VOTE,
            fold=fold,
            model_identity=challenger_model.model_identity,
            evaluation_identity=challenger_evaluation.evaluation_identity,
            selected_observation_identities=(
                challenger_evaluation.selected_observation_identities
            ),
            gross_r_total=challenger_evaluation.gross_r_total,
            original_cost_r_total=(
                challenger_evaluation.explicit_cost_r_total
            ),
            original_net_r_total=challenger_evaluation.net_r_total,
            observations=fold.evaluation_observations,
            config=effective_config,
        )
        reference_ids = tuple(
            item.scenario_identity for item in reference_scenarios
        )
        challenger_ids = tuple(
            item.scenario_identity for item in challenger_scenarios
        )
        payload = {
            "aggregate_winner_selection": False,
            "automatic_family_selection": False,
            "automatic_scenario_selection": False,
            "challenger_scenario_identities": challenger_ids,
            "comparison_identity": comparison.comparison_identity,
            "engine_version": ML_FAMILY_COST_STRESS_ENGINE_VERSION,
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "model_refit_performed": False,
            "prediction_set_changed": False,
            "reference_scenario_identities": reference_ids,
            "schema_version": ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
        }
        fold_result = MLFamilyCostStressFoldResult(
            result_identity=canonical_sha256(payload),
            schema_version=ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
            engine_version=ML_FAMILY_COST_STRESS_ENGINE_VERSION,
            fold_identity=fold.fold_identity,
            fold_index=fold.fold_index,
            comparison_identity=comparison.comparison_identity,
            reference_scenario_identities=reference_ids,
            challenger_scenario_identities=challenger_ids,
        )
        scenario_groups.append(
            (reference_scenarios, challenger_scenarios)
        )
        fold_results.append(fold_result)

    fold_ids = tuple(item.fold_identity for item in ordered_folds)
    fold_result_ids = tuple(item.result_identity for item in fold_results)
    manifest_payload = {
        "aggregate_winner_selection": False,
        "automatic_family_selection": False,
        "automatic_scenario_selection": False,
        "calibrated_probability_claim": False,
        "config_identity": effective_config.config_identity,
        "engine_version": ML_FAMILY_COST_STRESS_ENGINE_VERSION,
        "family_expansion_run_identity": expansion_manifest.run_identity,
        "family_set": FIXED_FAMILY_SET,
        "fold_identities": fold_ids,
        "fold_result_identities": fold_result_ids,
        "model_refit_performed": False,
        "prediction_set_changed": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
        "semantic": (
            MLFamilyCostStressSemantic
            .DESCRIPTIVE_FAMILY_COST_STRESS_NOT_SELECTION
        ),
        "untouched_forward_used": False,
    }
    manifest = MLFamilyCostStressManifest(
        run_identity=canonical_sha256(manifest_payload),
        schema_version=ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
        engine_version=ML_FAMILY_COST_STRESS_ENGINE_VERSION,
        semantic=(
            MLFamilyCostStressSemantic
            .DESCRIPTIVE_FAMILY_COST_STRESS_NOT_SELECTION
        ),
        config_identity=effective_config.config_identity,
        family_expansion_run_identity=expansion_manifest.run_identity,
        family_set=FIXED_FAMILY_SET,
        fold_identities=fold_ids,
        fold_result_identities=fold_result_ids,
    )
    return tuple(scenario_groups), tuple(fold_results), manifest


def _stress_family_evaluation(
    *,
    family: MLExpandedFamily,
    fold: MLWalkForwardFold,
    model_identity: str,
    evaluation_identity: str,
    selected_observation_identities: tuple[str, ...],
    gross_r_total: Decimal | None,
    original_cost_r_total: Decimal | None,
    original_net_r_total: Decimal | None,
    observations: Sequence[ClusterResearchObservation],
    config: MLFamilyCostStressConfig,
) -> tuple[MLFamilyCostStressScenario, ...]:
    by_identity = {
        item.observation_identity: item for item in observations
    }
    if len(by_identity) != len(tuple(observations)):
        raise ValueError("family cost-stress observations must be unique")
    if tuple(sorted(set(selected_observation_identities))) != (
        selected_observation_identities
    ):
        raise ValueError(
            "family cost-stress selected observations must be sorted and unique"
        )
    if any(
        identity not in by_identity
        for identity in selected_observation_identities
    ):
        raise ValueError(
            "family cost-stress observations must cover selected evaluation rows"
        )
    selected = tuple(
        by_identity[identity]
        for identity in selected_observation_identities
    )
    _verify_original_metrics(
        selected=selected,
        gross_r_total=gross_r_total,
        original_cost_r_total=original_cost_r_total,
        original_net_r_total=original_net_r_total,
    )

    scenarios: list[MLFamilyCostStressScenario] = []
    for multiplier in config.multipliers:
        if selected:
            assert gross_r_total is not None
            assert original_cost_r_total is not None
            assert original_net_r_total is not None
            stressed_cost = original_cost_r_total * multiplier
            stressed_net = gross_r_total - stressed_cost
        else:
            stressed_cost = None
            stressed_net = None
        payload = {
            "config_identity": config.config_identity,
            "engine_version": ML_FAMILY_COST_STRESS_ENGINE_VERSION,
            "evaluation_identity": evaluation_identity,
            "family": family,
            "fold_identity": fold.fold_identity,
            "fold_index": fold.fold_index,
            "gross_r_total": gross_r_total,
            "model_identity": model_identity,
            "model_refit_performed": False,
            "multiplier": multiplier,
            "original_cost_r_total": original_cost_r_total,
            "original_net_r_total": original_net_r_total,
            "prediction_set_changed": False,
            "schema_version": ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
            "selected_observation_identities": (
                selected_observation_identities
            ),
            "stressed_cost_r_total": stressed_cost,
            "stressed_net_r_total": stressed_net,
        }
        scenarios.append(
            MLFamilyCostStressScenario(
                scenario_identity=canonical_sha256(payload),
                schema_version=ML_FAMILY_COST_STRESS_SCHEMA_VERSION,
                engine_version=ML_FAMILY_COST_STRESS_ENGINE_VERSION,
                family=family,
                config_identity=config.config_identity,
                fold_identity=fold.fold_identity,
                fold_index=fold.fold_index,
                model_identity=model_identity,
                evaluation_identity=evaluation_identity,
                multiplier=multiplier,
                selected_observation_identities=(
                    selected_observation_identities
                ),
                gross_r_total=gross_r_total,
                original_cost_r_total=original_cost_r_total,
                stressed_cost_r_total=stressed_cost,
                original_net_r_total=original_net_r_total,
                stressed_net_r_total=stressed_net,
            )
        )
    return tuple(scenarios)


def _validate_comparison_bindings(
    *,
    fold: MLWalkForwardFold,
    comparison: MLFamilyFoldComparison,
    reference_model: MLBaselineModel,
    reference_evaluation: MLEvaluation,
    challenger_model: MLSignVoteModel,
    challenger_evaluation: MLFamilyEvaluation,
) -> None:
    if comparison.fold_identity != fold.fold_identity:
        raise ValueError("family stress comparison/fold identity mismatch")
    if comparison.fold_index != fold.fold_index:
        raise ValueError("family stress comparison/fold index mismatch")
    if comparison.reference_model_identity != reference_model.model_identity:
        raise ValueError("family stress reference model identity mismatch")
    if comparison.reference_evaluation_identity != (
        reference_evaluation.evaluation_identity
    ):
        raise ValueError("family stress reference evaluation identity mismatch")
    if comparison.challenger_model_identity != challenger_model.model_identity:
        raise ValueError("family stress challenger model identity mismatch")
    if comparison.challenger_evaluation_identity != (
        challenger_evaluation.evaluation_identity
    ):
        raise ValueError("family stress challenger evaluation identity mismatch")


def _verify_original_metrics(
    *,
    selected: tuple[ClusterResearchObservation, ...],
    gross_r_total: Decimal | None,
    original_cost_r_total: Decimal | None,
    original_net_r_total: Decimal | None,
) -> None:
    metrics = (
        gross_r_total,
        original_cost_r_total,
        original_net_r_total,
    )
    if not selected:
        if any(item is not None for item in metrics):
            raise ValueError(
                "empty family cost-stress selection cannot fabricate metrics"
            )
        return
    if any(item is None for item in metrics):
        raise ValueError(
            "family cost-stress selection requires complete original metrics"
        )
    observed_gross = sum(
        (item.gross_outcome_r for item in selected),
        start=Decimal(0),
    )
    observed_cost = sum(
        (item.explicit_cost_r for item in selected),
        start=Decimal(0),
    )
    observed_net = sum(
        (item.net_outcome_r for item in selected),
        start=Decimal(0),
    )
    if gross_r_total != observed_gross:
        raise ValueError("family cost-stress gross-R evidence mismatch")
    if original_cost_r_total != observed_cost:
        raise ValueError("family cost-stress cost evidence mismatch")
    if original_net_r_total != observed_net:
        raise ValueError("family cost-stress net-R evidence mismatch")


def _validate_metrics(
    *,
    selected_count: int,
    multiplier: Decimal,
    gross_r_total: Decimal | None,
    original_cost_r_total: Decimal | None,
    stressed_cost_r_total: Decimal | None,
    original_net_r_total: Decimal | None,
    stressed_net_r_total: Decimal | None,
) -> None:
    metrics = (
        gross_r_total,
        original_cost_r_total,
        stressed_cost_r_total,
        original_net_r_total,
        stressed_net_r_total,
    )
    if selected_count == 0:
        if any(item is not None for item in metrics):
            raise ValueError(
                "empty family stress scenario cannot fabricate metrics"
            )
        return
    if any(item is None for item in metrics):
        raise ValueError("family stress scenario requires complete metrics")
    assert gross_r_total is not None
    assert original_cost_r_total is not None
    assert stressed_cost_r_total is not None
    assert original_net_r_total is not None
    assert stressed_net_r_total is not None
    if original_cost_r_total < 0:
        raise ValueError("family stress original cost cannot be negative")
    if stressed_cost_r_total != original_cost_r_total * multiplier:
        raise ValueError("family stress cost calculation mismatch")
    if original_net_r_total != gross_r_total - original_cost_r_total:
        raise ValueError("family stress original net-R mismatch")
    if stressed_net_r_total != gross_r_total - stressed_cost_r_total:
        raise ValueError("family stress stressed net-R mismatch")
    if stressed_cost_r_total < original_cost_r_total:
        raise ValueError("family stress cannot improve cost")


def _config_payload(config: MLFamilyCostStressConfig) -> dict[str, object]:
    return {
        "automatic_family_selection": config.automatic_family_selection,
        "automatic_scenario_selection": config.automatic_scenario_selection,
        "engine_version": config.engine_version,
        "model_refit_allowed": config.model_refit_allowed,
        "multipliers": config.multipliers,
        "prediction_change_allowed": config.prediction_change_allowed,
        "schema_version": config.schema_version,
    }


def _scenario_payload(
    scenario: MLFamilyCostStressScenario,
) -> dict[str, object]:
    return {
        "config_identity": scenario.config_identity,
        "engine_version": scenario.engine_version,
        "evaluation_identity": scenario.evaluation_identity,
        "family": scenario.family,
        "fold_identity": scenario.fold_identity,
        "fold_index": scenario.fold_index,
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


def _fold_payload(
    result: MLFamilyCostStressFoldResult,
) -> dict[str, object]:
    return {
        "aggregate_winner_selection": result.aggregate_winner_selection,
        "automatic_family_selection": result.automatic_family_selection,
        "automatic_scenario_selection": result.automatic_scenario_selection,
        "challenger_scenario_identities": (
            result.challenger_scenario_identities
        ),
        "comparison_identity": result.comparison_identity,
        "engine_version": result.engine_version,
        "fold_identity": result.fold_identity,
        "fold_index": result.fold_index,
        "model_refit_performed": result.model_refit_performed,
        "prediction_set_changed": result.prediction_set_changed,
        "reference_scenario_identities": (
            result.reference_scenario_identities
        ),
        "schema_version": result.schema_version,
    }


def _manifest_payload(
    manifest: MLFamilyCostStressManifest,
) -> dict[str, object]:
    return {
        "aggregate_winner_selection": manifest.aggregate_winner_selection,
        "automatic_family_selection": manifest.automatic_family_selection,
        "automatic_scenario_selection": manifest.automatic_scenario_selection,
        "calibrated_probability_claim": manifest.calibrated_probability_claim,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "family_expansion_run_identity": (
            manifest.family_expansion_run_identity
        ),
        "family_set": manifest.family_set,
        "fold_identities": manifest.fold_identities,
        "fold_result_identities": manifest.fold_result_identities,
        "model_refit_performed": manifest.model_refit_performed,
        "prediction_set_changed": manifest.prediction_set_changed,
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
