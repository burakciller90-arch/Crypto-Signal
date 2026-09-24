"""Immutable WC4 champion/challenger research-cycle manifest.

The "champion" in this module is only the frozen research reference model from
the accepted untouched-forward boundary. It is not production champion state,
and this module grants no authority to select, promote, write, deploy, or trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import PromotionGateStatus
from research.alpha_factory.ml_family_untouched_forward import (
    MLFrozenFamilySnapshot,
    MLUntouchedForwardManifest,
    MLUntouchedForwardStatus,
)
from research.alpha_factory.ml_promotion_dossier import (
    MLPromotionDossier,
    MLPromotionMachineEvidence,
)

WC4_CHAMPION_CHALLENGER_ENGINE_VERSION = (
    "alpha-factory-champion-challenger-cycle-v1/1"
)
WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION = (
    "alpha-factory-champion-challenger-cycle-schema-v1/1"
)
REAL_CAPITAL = 0


class WC4CycleSemantic(StrEnum):
    FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION = (
        "frozen_research_reference_not_production_champion"
    )


class WC4CycleStatus(StrEnum):
    REVIEW_READY_NOT_PROMOTED = "review_ready_not_promoted"
    SUPERVISOR_ACCEPTED_MANUAL_REVIEW_NOT_PROMOTED = (
        "supervisor_accepted_manual_review_not_promoted"
    )


@dataclass(frozen=True, slots=True)
class WC4ChampionChallengerCycle:
    cycle_identity: str
    schema_version: str
    engine_version: str
    semantic: WC4CycleSemantic
    status: WC4CycleStatus
    dataset_identity: str
    champion_reference_model_identity: str
    challenger_model_identity: str
    frozen_snapshot_identity: str
    machine_evidence_identity: str
    dossier_identity: str
    data_contract_identity: str
    leakage_audit_identity: str
    reproducibility_identity: str
    transaction_cost_stress_identity: str
    in_sample_sanity_identity: str
    out_of_sample_identity: str
    walk_forward_identity: str
    robustness_ablation_identity: str
    untouched_forward_identity: str
    supervisor_acceptance_identity: str | None
    untouched_forward_used: bool = True
    human_supervisor_required: bool = True
    performance_winner_declared: bool = False
    champion_state_mutation_performed: bool = False
    automatic_promotion: bool = False
    deploy_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.cycle_identity, "WC4 cycle identity"),
            (self.dataset_identity, "WC4 dataset identity"),
            (
                self.champion_reference_model_identity,
                "WC4 champion research-reference identity",
            ),
            (self.challenger_model_identity, "WC4 challenger model identity"),
            (self.frozen_snapshot_identity, "WC4 frozen snapshot identity"),
            (self.machine_evidence_identity, "WC4 machine evidence identity"),
            (self.dossier_identity, "WC4 promotion dossier identity"),
            (self.data_contract_identity, "WC4 data-contract identity"),
            (self.leakage_audit_identity, "WC4 leakage-audit identity"),
            (self.reproducibility_identity, "WC4 reproducibility identity"),
            (
                self.transaction_cost_stress_identity,
                "WC4 transaction-cost identity",
            ),
            (self.in_sample_sanity_identity, "WC4 in-sample identity"),
            (self.out_of_sample_identity, "WC4 out-of-sample identity"),
            (self.walk_forward_identity, "WC4 walk-forward identity"),
            (self.robustness_ablation_identity, "WC4 robustness identity"),
            (self.untouched_forward_identity, "WC4 untouched-forward identity"),
        ):
            _require_sha256(value, label)
        if self.supervisor_acceptance_identity is not None:
            _require_sha256(
                self.supervisor_acceptance_identity,
                "WC4 supervisor acceptance identity",
            )

        if self.schema_version != WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION:
            raise ValueError("unsupported WC4 champion/challenger schema")
        if self.engine_version != WC4_CHAMPION_CHALLENGER_ENGINE_VERSION:
            raise ValueError("unsupported WC4 champion/challenger engine")
        if self.semantic is not (
            WC4CycleSemantic.FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION
        ):
            raise ValueError("unsupported WC4 champion/challenger semantic")
        if (
            self.champion_reference_model_identity
            == self.challenger_model_identity
        ):
            raise ValueError("WC4 cycle requires distinct reference/challenger models")

        if self.status is WC4CycleStatus.REVIEW_READY_NOT_PROMOTED:
            if self.supervisor_acceptance_identity is not None:
                raise ValueError(
                    "review-ready WC4 cycle cannot carry supervisor acceptance"
                )
        elif self.status is (
            WC4CycleStatus.SUPERVISOR_ACCEPTED_MANUAL_REVIEW_NOT_PROMOTED
        ):
            if self.supervisor_acceptance_identity is None:
                raise ValueError(
                    "supervisor-accepted WC4 cycle requires acceptance identity"
                )
        else:
            raise ValueError("unsupported WC4 cycle status")

        if not self.untouched_forward_used:
            raise ValueError("WC4 cycle requires evaluated untouched-forward evidence")
        if not self.human_supervisor_required:
            raise ValueError("WC4 cycle must preserve manual supervisor boundary")
        if (
            self.performance_winner_declared
            or self.champion_state_mutation_performed
            or self.automatic_promotion
            or self.deploy_authority
            or self.production_authority
        ):
            raise ValueError(
                "WC4 research cycle cannot select/promote/mutate/deploy"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.cycle_identity != canonical_sha256(_cycle_payload(self)):
            raise ValueError("WC4 champion/challenger cycle identity mismatch")


def build_wc4_champion_challenger_cycle(
    machine: MLPromotionMachineEvidence,
    dossier: MLPromotionDossier,
    frozen_snapshot: MLFrozenFamilySnapshot,
    forward_manifest: MLUntouchedForwardManifest,
) -> WC4ChampionChallengerCycle:
    """Bind one complete research comparison cycle without choosing a winner."""

    if dossier.machine_evidence_identity != machine.evidence_identity:
        raise ValueError("WC4 dossier/machine evidence mismatch")
    if frozen_snapshot.snapshot_identity != forward_manifest.snapshot_identity:
        raise ValueError("WC4 frozen snapshot/forward manifest mismatch")
    if machine.untouched_forward_identity != forward_manifest.run_identity:
        raise ValueError("WC4 machine/untouched-forward evidence mismatch")
    if (
        forward_manifest.status is not MLUntouchedForwardStatus.EVALUATED
        or not forward_manifest.untouched_forward_used
    ):
        raise ValueError("WC4 cycle requires evaluated untouched-forward evidence")
    if (
        frozen_snapshot.reference_model_identity
        == frozen_snapshot.challenger_model_identity
    ):
        raise ValueError("WC4 cycle requires distinct reference/challenger models")
    if (
        dossier.automatic_family_selection
        or dossier.automatic_promotion
        or dossier.champion_write_authority
        or dossier.deploy_authority
        or dossier.production_authority
    ):
        raise ValueError("WC4 dossier carries forbidden promotion authority")
    if (
        forward_manifest.automatic_family_selection
        or forward_manifest.aggregate_winner_selection
        or forward_manifest.retrospective_optimization_performed
        or forward_manifest.model_refit_performed
        or forward_manifest.feature_change_performed
    ):
        raise ValueError("WC4 forward evidence was used for selection/optimization")

    if dossier.status is PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW:
        status = WC4CycleStatus.REVIEW_READY_NOT_PROMOTED
    elif dossier.status is (
        PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION
    ):
        status = (
            WC4CycleStatus.SUPERVISOR_ACCEPTED_MANUAL_REVIEW_NOT_PROMOTED
        )
    else:
        raise ValueError("WC4 cycle requires complete promotion dossier")

    payload = {
        "automatic_promotion": False,
        "champion_reference_model_identity": (
            frozen_snapshot.reference_model_identity
        ),
        "champion_state_mutation_performed": False,
        "challenger_model_identity": frozen_snapshot.challenger_model_identity,
        "data_contract_identity": machine.data_contract_identity,
        "dataset_identity": frozen_snapshot.dataset_identity,
        "deploy_authority": False,
        "dossier_identity": dossier.dossier_identity,
        "engine_version": WC4_CHAMPION_CHALLENGER_ENGINE_VERSION,
        "frozen_snapshot_identity": frozen_snapshot.snapshot_identity,
        "human_supervisor_required": True,
        "in_sample_sanity_identity": machine.in_sample_sanity_identity,
        "leakage_audit_identity": machine.leakage_audit_identity,
        "machine_evidence_identity": machine.evidence_identity,
        "out_of_sample_identity": machine.out_of_sample_identity,
        "performance_winner_declared": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reproducibility_identity": machine.reproducibility_identity,
        "robustness_ablation_identity": machine.robustness_ablation_identity,
        "schema_version": WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION,
        "semantic": (
            WC4CycleSemantic.FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION
        ),
        "status": status,
        "supervisor_acceptance_identity": (
            dossier.supervisor_acceptance_identity
        ),
        "transaction_cost_stress_identity": (
            machine.transaction_cost_stress_identity
        ),
        "untouched_forward_identity": machine.untouched_forward_identity,
        "untouched_forward_used": True,
        "walk_forward_identity": machine.walk_forward_identity,
    }
    return WC4ChampionChallengerCycle(
        cycle_identity=canonical_sha256(payload),
        schema_version=WC4_CHAMPION_CHALLENGER_SCHEMA_VERSION,
        engine_version=WC4_CHAMPION_CHALLENGER_ENGINE_VERSION,
        semantic=(
            WC4CycleSemantic.FROZEN_RESEARCH_REFERENCE_NOT_PRODUCTION_CHAMPION
        ),
        status=status,
        dataset_identity=frozen_snapshot.dataset_identity,
        champion_reference_model_identity=(
            frozen_snapshot.reference_model_identity
        ),
        challenger_model_identity=frozen_snapshot.challenger_model_identity,
        frozen_snapshot_identity=frozen_snapshot.snapshot_identity,
        machine_evidence_identity=machine.evidence_identity,
        dossier_identity=dossier.dossier_identity,
        data_contract_identity=machine.data_contract_identity,
        leakage_audit_identity=machine.leakage_audit_identity,
        reproducibility_identity=machine.reproducibility_identity,
        transaction_cost_stress_identity=(
            machine.transaction_cost_stress_identity
        ),
        in_sample_sanity_identity=machine.in_sample_sanity_identity,
        out_of_sample_identity=machine.out_of_sample_identity,
        walk_forward_identity=machine.walk_forward_identity,
        robustness_ablation_identity=machine.robustness_ablation_identity,
        untouched_forward_identity=machine.untouched_forward_identity,
        supervisor_acceptance_identity=dossier.supervisor_acceptance_identity,
    )


def _cycle_payload(cycle: WC4ChampionChallengerCycle) -> dict[str, object]:
    return {
        "automatic_promotion": cycle.automatic_promotion,
        "champion_reference_model_identity": (
            cycle.champion_reference_model_identity
        ),
        "champion_state_mutation_performed": (
            cycle.champion_state_mutation_performed
        ),
        "challenger_model_identity": cycle.challenger_model_identity,
        "data_contract_identity": cycle.data_contract_identity,
        "dataset_identity": cycle.dataset_identity,
        "deploy_authority": cycle.deploy_authority,
        "dossier_identity": cycle.dossier_identity,
        "engine_version": cycle.engine_version,
        "frozen_snapshot_identity": cycle.frozen_snapshot_identity,
        "human_supervisor_required": cycle.human_supervisor_required,
        "in_sample_sanity_identity": cycle.in_sample_sanity_identity,
        "leakage_audit_identity": cycle.leakage_audit_identity,
        "machine_evidence_identity": cycle.machine_evidence_identity,
        "out_of_sample_identity": cycle.out_of_sample_identity,
        "performance_winner_declared": cycle.performance_winner_declared,
        "production_authority": cycle.production_authority,
        "real_capital": cycle.real_capital,
        "reproducibility_identity": cycle.reproducibility_identity,
        "robustness_ablation_identity": cycle.robustness_ablation_identity,
        "schema_version": cycle.schema_version,
        "semantic": cycle.semantic,
        "status": cycle.status,
        "supervisor_acceptance_identity": cycle.supervisor_acceptance_identity,
        "transaction_cost_stress_identity": (
            cycle.transaction_cost_stress_identity
        ),
        "untouched_forward_identity": cycle.untouched_forward_identity,
        "untouched_forward_used": cycle.untouched_forward_used,
        "walk_forward_identity": cycle.walk_forward_identity,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be lowercase SHA256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be lowercase SHA256") from exc
    if value.lower() != value:
        raise ValueError(f"{label} must be lowercase SHA256")
