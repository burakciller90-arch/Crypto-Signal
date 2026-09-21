"""Immutable promotion-evidence dossier for the accepted bounded ML chain."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import ClusterResearchObservation
from research.alpha_factory.foundation import (
    LeakageAuditStatus,
    PromotionGateStatus,
    ResearchPartition,
)
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
from research.alpha_factory.ml_family_untouched_forward import (
    MLFrozenFamilySnapshot,
    MLUntouchedForwardFamilyEvaluation,
    MLUntouchedForwardManifest,
    MLUntouchedForwardPrediction,
    run_ml_family_untouched_forward_paper,
)
from research.alpha_factory.ml_walk_forward import (
    MLWalkForwardFold,
    MLWalkForwardFoldResult,
    MLWalkForwardManifest,
    run_ml_walk_forward,
)
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

ML_PROMOTION_DOSSIER_ENGINE_VERSION = "alpha-factory-ml-promotion-dossier-v1/1"
ML_PROMOTION_DOSSIER_SCHEMA_VERSION = "alpha-factory-ml-promotion-dossier-schema-v1/1"
REAL_CAPITAL = 0

WalkForwardEvidence = tuple[
    tuple[tuple[MLBaselineModel, MLTrainingManifest, MLEvaluation], ...],
    tuple[MLWalkForwardFoldResult, ...],
    MLWalkForwardManifest,
]
FamilyExpansionEvidence = tuple[
    tuple[
        tuple[MLSignVoteModel, MLFamilyTrainingManifest, MLFamilyEvaluation],
        ...,
    ],
    tuple[MLFamilyFoldComparison, ...],
    MLFamilyExpansionManifest,
]
FamilyCostStressEvidence = tuple[
    tuple[
        tuple[
            tuple[MLFamilyCostStressScenario, ...],
            tuple[MLFamilyCostStressScenario, ...],
        ],
        ...,
    ],
    tuple[MLFamilyCostStressFoldResult, ...],
    MLFamilyCostStressManifest,
]
FamilyRobustnessEvidence = tuple[
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
]
UntouchedForwardEvidence = tuple[
    tuple[MLUntouchedForwardPrediction, ...],
    tuple[MLUntouchedForwardPrediction, ...],
    MLUntouchedForwardFamilyEvaluation,
    MLUntouchedForwardFamilyEvaluation,
    MLFrozenFamilySnapshot,
    MLUntouchedForwardManifest,
]


class MLPromotionDossierSemantic(StrEnum):
    EVIDENCE_COMPLETE_NOT_PROMOTION = "evidence_complete_not_promotion"


class MLSupervisorDecision(StrEnum):
    ACCEPTED_FOR_MANUAL_PROMOTION_REVIEW_ONLY = (
        "accepted_for_manual_promotion_review_only"
    )


@dataclass(frozen=True, slots=True)
class MLPromotionMachineEvidence:
    evidence_identity: str
    schema_version: str
    engine_version: str
    data_contract_identity: str
    leakage_audit_identity: str
    leakage_audit_status: LeakageAuditStatus
    reproducibility_identity: str
    transaction_cost_stress_identity: str
    in_sample_sanity_identity: str
    out_of_sample_identity: str
    walk_forward_identity: str
    untouched_forward_identity: str
    robustness_ablation_identity: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.evidence_identity, "machine evidence identity"),
            (self.data_contract_identity, "data-contract identity"),
            (self.leakage_audit_identity, "leakage audit identity"),
            (self.reproducibility_identity, "reproducibility identity"),
            (
                self.transaction_cost_stress_identity,
                "transaction cost-stress identity",
            ),
            (self.in_sample_sanity_identity, "in-sample sanity identity"),
            (self.out_of_sample_identity, "out-of-sample identity"),
            (self.walk_forward_identity, "walk-forward identity"),
            (self.untouched_forward_identity, "untouched-forward identity"),
            (self.robustness_ablation_identity, "robustness identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != ML_PROMOTION_DOSSIER_SCHEMA_VERSION:
            raise ValueError("unsupported promotion machine-evidence schema")
        if self.engine_version != ML_PROMOTION_DOSSIER_ENGINE_VERSION:
            raise ValueError("unsupported promotion machine-evidence engine")
        if self.leakage_audit_status is not LeakageAuditStatus.PASSED:
            raise ValueError("promotion machine evidence requires passed leakage audit")
        if self.evidence_identity != canonical_sha256(_machine_payload(self)):
            raise ValueError("promotion machine-evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class MLPromotionDossier:
    dossier_identity: str
    schema_version: str
    engine_version: str
    semantic: MLPromotionDossierSemantic
    machine_evidence_identity: str
    family_set: tuple[MLExpandedFamily, ...]
    status: PromotionGateStatus
    blocking_reasons: tuple[str, ...]
    supervisor_acceptance_identity: str | None = None
    automatic_family_selection: bool = False
    automatic_promotion: bool = False
    champion_write_authority: bool = False
    deploy_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.dossier_identity, "promotion dossier identity")
        _require_sha256(
            self.machine_evidence_identity,
            "promotion machine evidence identity",
        )
        if self.supervisor_acceptance_identity is not None:
            _require_sha256(
                self.supervisor_acceptance_identity,
                "supervisor acceptance identity",
            )
        if self.schema_version != ML_PROMOTION_DOSSIER_SCHEMA_VERSION:
            raise ValueError("unsupported promotion dossier schema")
        if self.engine_version != ML_PROMOTION_DOSSIER_ENGINE_VERSION:
            raise ValueError("unsupported promotion dossier engine")
        if self.semantic is not MLPromotionDossierSemantic.EVIDENCE_COMPLETE_NOT_PROMOTION:
            raise ValueError("unsupported promotion dossier semantic")
        if self.family_set != FIXED_FAMILY_SET:
            raise ValueError("promotion dossier family set mismatch")
        if self.blocking_reasons:
            raise ValueError("complete promotion dossier cannot carry blockers")
        if self.status is PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW:
            if self.supervisor_acceptance_identity is not None:
                raise ValueError("ready dossier cannot carry supervisor acceptance")
        elif self.status is (
            PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION
        ):
            if self.supervisor_acceptance_identity is None:
                raise ValueError(
                    "supervisor-accepted dossier requires explicit acceptance"
                )
        else:
            raise ValueError("complete dossier cannot use BLOCKED status")
        if (
            self.automatic_family_selection
            or self.automatic_promotion
            or self.champion_write_authority
            or self.deploy_authority
            or self.production_authority
        ):
            raise ValueError(
                "promotion dossier has no automatic promotion/write/deploy authority"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.dossier_identity != canonical_sha256(_dossier_payload(self)):
            raise ValueError("promotion dossier identity mismatch")


@dataclass(frozen=True, slots=True)
class MLSupervisorAcceptanceEvidence:
    acceptance_identity: str
    schema_version: str
    engine_version: str
    source_dossier_identity: str
    decision: MLSupervisorDecision
    reviewer_role: str
    review_version: str
    acceptance_note: str
    manual_promotion_required: bool = True
    champion_write_authority: bool = False
    deploy_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.acceptance_identity, "supervisor acceptance identity")
        _require_sha256(
            self.source_dossier_identity,
            "supervisor source dossier identity",
        )
        if self.schema_version != ML_PROMOTION_DOSSIER_SCHEMA_VERSION:
            raise ValueError("unsupported supervisor acceptance schema")
        if self.engine_version != ML_PROMOTION_DOSSIER_ENGINE_VERSION:
            raise ValueError("unsupported supervisor acceptance engine")
        if self.decision is not (
            MLSupervisorDecision.ACCEPTED_FOR_MANUAL_PROMOTION_REVIEW_ONLY
        ):
            raise ValueError("unsupported supervisor decision")
        _require_text(self.reviewer_role, "supervisor reviewer role")
        _require_text(self.review_version, "supervisor review version")
        _require_text(self.acceptance_note, "supervisor acceptance note")
        if not self.manual_promotion_required:
            raise ValueError("supervisor acceptance must require manual promotion")
        if (
            self.champion_write_authority
            or self.deploy_authority
            or self.production_authority
        ):
            raise ValueError("supervisor acceptance grants no write/deploy authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.acceptance_identity != canonical_sha256(
            _supervisor_payload(self)
        ):
            raise ValueError("supervisor acceptance identity mismatch")


def build_ml_promotion_dossier(
    features: Sequence[SymbolicFeatureSpec],
    folds: Sequence[MLWalkForwardFold],
    walk_forward_evidence: WalkForwardEvidence,
    family_expansion_evidence: FamilyExpansionEvidence,
    family_cost_stress_evidence: FamilyCostStressEvidence,
    family_robustness_evidence: FamilyRobustnessEvidence,
    untouched_partition: ResearchPartition,
    untouched_observations: Sequence[ClusterResearchObservation],
    untouched_forward_evidence: UntouchedForwardEvidence,
    *,
    regime_feature_id: str,
) -> tuple[MLPromotionMachineEvidence, MLPromotionDossier]:
    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    ordered_folds = tuple(sorted(folds, key=lambda item: item.fold_index))
    if not ordered_features:
        raise ValueError("promotion dossier requires features")
    if not ordered_folds:
        raise ValueError("promotion dossier requires walk-forward folds")

    expected_walk = run_ml_walk_forward(ordered_features, ordered_folds)
    if expected_walk != walk_forward_evidence:
        raise ValueError("promotion dossier requires exact walk-forward evidence")
    references, walk_results, walk_manifest = walk_forward_evidence

    expected_expansion = run_ml_family_expansion(
        ordered_features,
        ordered_folds,
        references,
    )
    if expected_expansion != family_expansion_evidence:
        raise ValueError("promotion dossier requires exact family expansion evidence")
    challengers, comparisons, expansion_manifest = family_expansion_evidence

    expected_cost = run_ml_family_cost_stress(
        ordered_features,
        ordered_folds,
        references,
        family_expansion_evidence,
    )
    if expected_cost != family_cost_stress_evidence:
        raise ValueError("promotion dossier requires exact cost-stress evidence")
    _, _, cost_manifest = family_cost_stress_evidence

    expected_robustness = run_ml_family_robustness_ablation(
        ordered_features,
        ordered_folds,
        references,
        family_expansion_evidence,
        family_cost_stress_evidence,
        regime_feature_id=regime_feature_id,
    )
    if expected_robustness != family_robustness_evidence:
        raise ValueError("promotion dossier requires exact robustness evidence")
    _, _, _, _, robustness_manifest = family_robustness_evidence

    expected_forward = run_ml_family_untouched_forward_paper(
        ordered_features,
        ordered_folds,
        references,
        family_expansion_evidence,
        family_cost_stress_evidence,
        family_robustness_evidence,
        untouched_partition,
        untouched_observations,
        regime_feature_id=regime_feature_id,
    )
    if expected_forward != untouched_forward_evidence:
        raise ValueError(
            "promotion dossier requires exact untouched-forward evidence"
        )
    _, _, _, _, frozen_snapshot, forward_manifest = untouched_forward_evidence

    _validate_no_forward_evidence_reuse(ordered_folds, untouched_partition)

    feature_identities = tuple(
        sorted(item.feature_identity for item in ordered_features)
    )
    data_contract_identity = canonical_sha256(
        {
            "dataset_identity": walk_manifest.dataset_identity,
            "feature_identities": feature_identities,
            "fold_identities": tuple(item.fold_identity for item in ordered_folds),
            "fold_partition_identities": tuple(
                (
                    item.training_partition.partition_identity,
                    item.evaluation_partition.partition_identity,
                )
                for item in ordered_folds
            ),
            "untouched_partition_identity": untouched_partition.partition_identity,
        }
    )
    leakage_audit_identity = canonical_sha256(
        {
            "forward_source_evidence_identities": (
                untouched_partition.evidence_identities
            ),
            "last_oos_end_ms": ordered_folds[-1].evaluation_partition.end_ms,
            "leakage_status": LeakageAuditStatus.PASSED,
            "untouched_start_ms": untouched_partition.start_ms,
            "walk_forward_result_identities": tuple(
                item.result_identity for item in walk_results
            ),
        }
    )
    reproducibility_identity = canonical_sha256(
        {
            "cost_stress_run_identity": cost_manifest.run_identity,
            "family_expansion_run_identity": expansion_manifest.run_identity,
            "feature_identities": feature_identities,
            "forward_run_identity": forward_manifest.run_identity,
            "frozen_snapshot_identity": frozen_snapshot.snapshot_identity,
            "robustness_run_identity": robustness_manifest.run_identity,
            "walk_forward_run_identity": walk_manifest.run_identity,
        }
    )
    in_sample_sanity_identity = canonical_sha256(
        {
            "challenger_training_identities": tuple(
                item[1].training_identity for item in challengers
            ),
            "reference_training_identities": tuple(
                item[1].training_identity for item in references
            ),
            "reference_model_identities": tuple(
                item[0].model_identity for item in references
            ),
            "challenger_model_identities": tuple(
                item[0].model_identity for item in challengers
            ),
        }
    )
    out_of_sample_identity = canonical_sha256(
        {
            "comparison_identities": tuple(
                item.comparison_identity for item in comparisons
            ),
            "family_expansion_run_identity": expansion_manifest.run_identity,
            "reference_oos_evaluation_identities": tuple(
                item[2].evaluation_identity for item in references
            ),
            "challenger_oos_evaluation_identities": tuple(
                item[2].evaluation_identity for item in challengers
            ),
        }
    )

    machine_payload = {
        "data_contract_identity": data_contract_identity,
        "engine_version": ML_PROMOTION_DOSSIER_ENGINE_VERSION,
        "in_sample_sanity_identity": in_sample_sanity_identity,
        "leakage_audit_identity": leakage_audit_identity,
        "leakage_audit_status": LeakageAuditStatus.PASSED,
        "out_of_sample_identity": out_of_sample_identity,
        "reproducibility_identity": reproducibility_identity,
        "robustness_ablation_identity": robustness_manifest.run_identity,
        "schema_version": ML_PROMOTION_DOSSIER_SCHEMA_VERSION,
        "transaction_cost_stress_identity": cost_manifest.run_identity,
        "untouched_forward_identity": forward_manifest.run_identity,
        "walk_forward_identity": walk_manifest.run_identity,
    }
    machine = MLPromotionMachineEvidence(
        evidence_identity=canonical_sha256(machine_payload),
        schema_version=ML_PROMOTION_DOSSIER_SCHEMA_VERSION,
        engine_version=ML_PROMOTION_DOSSIER_ENGINE_VERSION,
        data_contract_identity=data_contract_identity,
        leakage_audit_identity=leakage_audit_identity,
        leakage_audit_status=LeakageAuditStatus.PASSED,
        reproducibility_identity=reproducibility_identity,
        transaction_cost_stress_identity=cost_manifest.run_identity,
        in_sample_sanity_identity=in_sample_sanity_identity,
        out_of_sample_identity=out_of_sample_identity,
        walk_forward_identity=walk_manifest.run_identity,
        untouched_forward_identity=forward_manifest.run_identity,
        robustness_ablation_identity=robustness_manifest.run_identity,
    )
    dossier_payload = {
        "automatic_family_selection": False,
        "automatic_promotion": False,
        "blocking_reasons": (),
        "champion_write_authority": False,
        "deploy_authority": False,
        "engine_version": ML_PROMOTION_DOSSIER_ENGINE_VERSION,
        "family_set": FIXED_FAMILY_SET,
        "machine_evidence_identity": machine.evidence_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": ML_PROMOTION_DOSSIER_SCHEMA_VERSION,
        "semantic": MLPromotionDossierSemantic.EVIDENCE_COMPLETE_NOT_PROMOTION,
        "status": PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW,
        "supervisor_acceptance_identity": None,
    }
    dossier = MLPromotionDossier(
        dossier_identity=canonical_sha256(dossier_payload),
        schema_version=ML_PROMOTION_DOSSIER_SCHEMA_VERSION,
        engine_version=ML_PROMOTION_DOSSIER_ENGINE_VERSION,
        semantic=MLPromotionDossierSemantic.EVIDENCE_COMPLETE_NOT_PROMOTION,
        machine_evidence_identity=machine.evidence_identity,
        family_set=FIXED_FAMILY_SET,
        status=PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW,
        blocking_reasons=(),
    )
    return machine, dossier


def record_ml_supervisor_acceptance(
    dossier: MLPromotionDossier,
    *,
    reviewer_role: str,
    review_version: str,
    acceptance_note: str,
) -> tuple[MLSupervisorAcceptanceEvidence, MLPromotionDossier]:
    if dossier.status is not PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW:
        raise ValueError("supervisor acceptance requires ready machine dossier")
    if dossier.supervisor_acceptance_identity is not None:
        raise ValueError("dossier already has supervisor acceptance")
    payload = {
        "acceptance_note": acceptance_note,
        "champion_write_authority": False,
        "decision": (
            MLSupervisorDecision.ACCEPTED_FOR_MANUAL_PROMOTION_REVIEW_ONLY
        ),
        "deploy_authority": False,
        "engine_version": ML_PROMOTION_DOSSIER_ENGINE_VERSION,
        "manual_promotion_required": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "review_version": review_version,
        "reviewer_role": reviewer_role,
        "schema_version": ML_PROMOTION_DOSSIER_SCHEMA_VERSION,
        "source_dossier_identity": dossier.dossier_identity,
    }
    acceptance = MLSupervisorAcceptanceEvidence(
        acceptance_identity=canonical_sha256(payload),
        schema_version=ML_PROMOTION_DOSSIER_SCHEMA_VERSION,
        engine_version=ML_PROMOTION_DOSSIER_ENGINE_VERSION,
        source_dossier_identity=dossier.dossier_identity,
        decision=MLSupervisorDecision.ACCEPTED_FOR_MANUAL_PROMOTION_REVIEW_ONLY,
        reviewer_role=reviewer_role,
        review_version=review_version,
        acceptance_note=acceptance_note,
    )
    accepted_payload = {
        "automatic_family_selection": dossier.automatic_family_selection,
        "automatic_promotion": dossier.automatic_promotion,
        "blocking_reasons": dossier.blocking_reasons,
        "champion_write_authority": dossier.champion_write_authority,
        "deploy_authority": dossier.deploy_authority,
        "engine_version": dossier.engine_version,
        "family_set": dossier.family_set,
        "machine_evidence_identity": dossier.machine_evidence_identity,
        "production_authority": dossier.production_authority,
        "real_capital": dossier.real_capital,
        "schema_version": dossier.schema_version,
        "semantic": dossier.semantic,
        "status": PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION,
        "supervisor_acceptance_identity": acceptance.acceptance_identity,
    }
    accepted = MLPromotionDossier(
        dossier_identity=canonical_sha256(accepted_payload),
        schema_version=dossier.schema_version,
        engine_version=dossier.engine_version,
        semantic=dossier.semantic,
        machine_evidence_identity=dossier.machine_evidence_identity,
        family_set=dossier.family_set,
        status=PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION,
        blocking_reasons=dossier.blocking_reasons,
        supervisor_acceptance_identity=acceptance.acceptance_identity,
        automatic_family_selection=dossier.automatic_family_selection,
        automatic_promotion=dossier.automatic_promotion,
        champion_write_authority=dossier.champion_write_authority,
        deploy_authority=dossier.deploy_authority,
        production_authority=dossier.production_authority,
        real_capital=dossier.real_capital,
    )
    return acceptance, accepted


def _validate_no_forward_evidence_reuse(
    folds: tuple[MLWalkForwardFold, ...],
    untouched_partition: ResearchPartition,
) -> None:
    historical: set[str] = set()
    for fold in folds:
        historical.update(fold.training_partition.evidence_identities)
        historical.update(fold.evaluation_partition.evidence_identities)
    overlap = historical.intersection(untouched_partition.evidence_identities)
    if overlap:
        raise ValueError("untouched-forward evidence reuses historical evidence")
    if untouched_partition.start_ms < folds[-1].evaluation_partition.end_ms:
        raise ValueError("untouched-forward chronology overlaps accepted OOS")


def _machine_payload(machine: MLPromotionMachineEvidence) -> dict[str, object]:
    return {
        "data_contract_identity": machine.data_contract_identity,
        "engine_version": machine.engine_version,
        "in_sample_sanity_identity": machine.in_sample_sanity_identity,
        "leakage_audit_identity": machine.leakage_audit_identity,
        "leakage_audit_status": machine.leakage_audit_status,
        "out_of_sample_identity": machine.out_of_sample_identity,
        "reproducibility_identity": machine.reproducibility_identity,
        "robustness_ablation_identity": machine.robustness_ablation_identity,
        "schema_version": machine.schema_version,
        "transaction_cost_stress_identity": (
            machine.transaction_cost_stress_identity
        ),
        "untouched_forward_identity": machine.untouched_forward_identity,
        "walk_forward_identity": machine.walk_forward_identity,
    }


def _dossier_payload(dossier: MLPromotionDossier) -> dict[str, object]:
    return {
        "automatic_family_selection": dossier.automatic_family_selection,
        "automatic_promotion": dossier.automatic_promotion,
        "blocking_reasons": dossier.blocking_reasons,
        "champion_write_authority": dossier.champion_write_authority,
        "deploy_authority": dossier.deploy_authority,
        "engine_version": dossier.engine_version,
        "family_set": dossier.family_set,
        "machine_evidence_identity": dossier.machine_evidence_identity,
        "production_authority": dossier.production_authority,
        "real_capital": dossier.real_capital,
        "schema_version": dossier.schema_version,
        "semantic": dossier.semantic,
        "status": dossier.status,
        "supervisor_acceptance_identity": dossier.supervisor_acceptance_identity,
    }


def _supervisor_payload(
    acceptance: MLSupervisorAcceptanceEvidence,
) -> dict[str, object]:
    return {
        "acceptance_note": acceptance.acceptance_note,
        "champion_write_authority": acceptance.champion_write_authority,
        "decision": acceptance.decision,
        "deploy_authority": acceptance.deploy_authority,
        "engine_version": acceptance.engine_version,
        "manual_promotion_required": acceptance.manual_promotion_required,
        "production_authority": acceptance.production_authority,
        "real_capital": acceptance.real_capital,
        "review_version": acceptance.review_version,
        "reviewer_role": acceptance.reviewer_role,
        "schema_version": acceptance.schema_version,
        "source_dossier_identity": acceptance.source_dossier_identity,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256 hex") from exc


def _require_text(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be non-empty trimmed text")
