from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256

ALPHA_FACTORY_FOUNDATION_VERSION = "alpha-factory-research-foundation-v1/1"
ALPHA_FACTORY_SCHEMA_VERSION = "alpha-factory-research-schema-v1/1"
RESEARCH_AUTHORITY = "research_only_no_deploy"
REAL_CAPITAL = 0


class ResearchGeneratorKind(StrEnum):
    SYMBOLIC_RULE = "symbolic_rule"


class PartitionRole(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    OUT_OF_SAMPLE = "out_of_sample"
    UNTOUCHED_FORWARD = "untouched_forward"


class LeakageAuditStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class PromotionGateStatus(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_SUPERVISOR_REVIEW = "ready_for_supervisor_review"
    SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION = (
        "supervisor_accepted_for_manual_promotion"
    )


_PARTITION_ORDER = (
    PartitionRole.TRAIN,
    PartitionRole.VALIDATION,
    PartitionRole.OUT_OF_SAMPLE,
    PartitionRole.UNTOUCHED_FORWARD,
)


@dataclass(frozen=True, slots=True)
class ResearchPartition:
    partition_identity: str
    schema_version: str
    dataset_identity: str
    role: PartitionRole
    start_ms: int
    end_ms: int
    row_count: int
    evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.partition_identity, "partition identity")
        _require_sha256(self.dataset_identity, "dataset identity")
        if self.schema_version != ALPHA_FACTORY_SCHEMA_VERSION:
            raise ValueError("unsupported research partition schema")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("research partition requires start_ms < end_ms")
        if self.row_count <= 0:
            raise ValueError("research partition row_count must be positive")
        if not self.evidence_identities:
            raise ValueError("research partition requires evidence identities")
        for identity in self.evidence_identities:
            _require_sha256(identity, "partition evidence identity")
        if tuple(sorted(set(self.evidence_identities))) != self.evidence_identities:
            raise ValueError(
                "partition evidence identities must be sorted and unique"
            )
        if self.partition_identity != canonical_sha256(
            _partition_payload(self)
        ):
            raise ValueError("research partition identity mismatch")


@dataclass(frozen=True, slots=True)
class ChallengerDefinition:
    challenger_identity: str
    schema_version: str
    name: str
    version: str
    hypothesis: str
    generator_kind: ResearchGeneratorKind
    rule_definition: str
    feature_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.challenger_identity, "challenger identity")
        if self.schema_version != ALPHA_FACTORY_SCHEMA_VERSION:
            raise ValueError("unsupported challenger schema")
        _require_text(self.name, "challenger name")
        _require_text(self.version, "challenger version")
        _require_text(self.hypothesis, "challenger hypothesis")
        _require_text(self.rule_definition, "challenger rule definition")
        if self.generator_kind is not ResearchGeneratorKind.SYMBOLIC_RULE:
            raise ValueError("foundation v1 permits symbolic-rule research only")
        if not self.feature_ids:
            raise ValueError("challenger requires at least one feature id")
        normalized = tuple(sorted(set(self.feature_ids)))
        if normalized != self.feature_ids:
            raise ValueError("challenger feature ids must be sorted and unique")
        for feature_id in self.feature_ids:
            _require_text(feature_id, "challenger feature id")
        if self.challenger_identity != canonical_sha256(
            _challenger_payload(self)
        ):
            raise ValueError("challenger identity mismatch")


@dataclass(frozen=True, slots=True)
class ResearchExperimentManifest:
    experiment_identity: str
    foundation_version: str
    schema_version: str
    challenger_identity: str
    dataset_identity: str
    partitions: tuple[ResearchPartition, ...]
    evaluation_policy_version: str
    cost_stress_profile_identity: str
    reproducibility_seed: int
    authority: str = RESEARCH_AUTHORITY
    can_self_promote: bool = False
    champion_write_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.experiment_identity, "experiment identity")
        _require_sha256(self.challenger_identity, "challenger identity")
        _require_sha256(self.dataset_identity, "dataset identity")
        _require_sha256(
            self.cost_stress_profile_identity,
            "cost stress profile identity",
        )
        if self.foundation_version != ALPHA_FACTORY_FOUNDATION_VERSION:
            raise ValueError("unsupported Alpha Factory foundation version")
        if self.schema_version != ALPHA_FACTORY_SCHEMA_VERSION:
            raise ValueError("unsupported experiment schema")
        _require_text(
            self.evaluation_policy_version,
            "evaluation policy version",
        )
        if self.reproducibility_seed < 0:
            raise ValueError("reproducibility seed must be non-negative")
        if self.authority != RESEARCH_AUTHORITY:
            raise ValueError("Alpha Factory authority must remain research-only")
        if self.can_self_promote:
            raise ValueError("challengers cannot self-promote")
        if self.champion_write_authority:
            raise ValueError("research cannot write champion state")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")

        if tuple(item.role for item in self.partitions) != _PARTITION_ORDER:
            raise ValueError(
                "experiment partitions must use the canonical role order"
            )
        if any(
            item.dataset_identity != self.dataset_identity
            for item in self.partitions
        ):
            raise ValueError("all research partitions must share dataset identity")

        seen_evidence: set[str] = set()
        previous_end: int | None = None
        for item in self.partitions:
            if previous_end is not None and item.start_ms < previous_end:
                raise ValueError("research partitions must not overlap")
            previous_end = item.end_ms
            overlap = seen_evidence.intersection(item.evidence_identities)
            if overlap:
                raise ValueError(
                    "evidence identity cannot cross research partitions"
                )
            seen_evidence.update(item.evidence_identities)

        if self.experiment_identity != canonical_sha256(
            _experiment_payload(self)
        ):
            raise ValueError("experiment identity mismatch")


@dataclass(frozen=True, slots=True)
class LeakageAudit:
    audit_identity: str
    schema_version: str
    experiment_identity: str
    audited_at_ms: int
    status: LeakageAuditStatus
    findings: tuple[str, ...]
    auditor_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.audit_identity, "leakage audit identity")
        _require_sha256(self.experiment_identity, "experiment identity")
        if self.schema_version != ALPHA_FACTORY_SCHEMA_VERSION:
            raise ValueError("unsupported leakage audit schema")
        if self.audited_at_ms < 0:
            raise ValueError("leakage audit time must be non-negative")
        _require_text(self.auditor_version, "leakage auditor version")
        for finding in self.findings:
            _require_text(finding, "leakage audit finding")
        if len(set(self.findings)) != len(self.findings):
            raise ValueError("leakage audit findings must be unique")
        if self.status is LeakageAuditStatus.PASSED and self.findings:
            raise ValueError("passed leakage audit cannot carry findings")
        if self.status is LeakageAuditStatus.FAILED and not self.findings:
            raise ValueError("failed leakage audit requires findings")
        if self.status is LeakageAuditStatus.PENDING and self.findings:
            raise ValueError("pending leakage audit cannot carry findings")
        if self.audit_identity != canonical_sha256(
            _leakage_audit_payload(self)
        ):
            raise ValueError("leakage audit identity mismatch")


@dataclass(frozen=True, slots=True)
class PromotionGateEvidence:
    evidence_identity: str
    schema_version: str
    experiment_identity: str
    data_contract_audit_identity: str | None
    reproducibility_identity: str | None
    transaction_cost_stress_identity: str | None
    in_sample_sanity_identity: str | None
    out_of_sample_identity: str | None
    walk_forward_identity: str | None
    untouched_forward_identity: str | None
    robustness_ablation_identity: str | None
    supervisor_acceptance_identity: str | None

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "promotion evidence identity")
        _require_sha256(self.experiment_identity, "experiment identity")
        if self.schema_version != ALPHA_FACTORY_SCHEMA_VERSION:
            raise ValueError("unsupported promotion evidence schema")
        for label, value in _promotion_evidence_fields(self):
            if value is not None:
                _require_sha256(value, label)
        if self.evidence_identity != canonical_sha256(
            _promotion_evidence_payload(self)
        ):
            raise ValueError("promotion evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class PromotionGateAssessment:
    assessment_identity: str
    schema_version: str
    experiment_identity: str
    leakage_audit_identity: str
    promotion_evidence_identity: str
    status: PromotionGateStatus
    blocking_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.assessment_identity, "promotion assessment identity")
        _require_sha256(self.experiment_identity, "experiment identity")
        _require_sha256(self.leakage_audit_identity, "leakage audit identity")
        _require_sha256(
            self.promotion_evidence_identity,
            "promotion evidence identity",
        )
        if self.schema_version != ALPHA_FACTORY_SCHEMA_VERSION:
            raise ValueError("unsupported promotion assessment schema")
        if self.status is PromotionGateStatus.BLOCKED:
            if not self.blocking_reasons:
                raise ValueError("blocked promotion assessment requires reasons")
        elif self.blocking_reasons:
            raise ValueError("non-blocked promotion assessment cannot have reasons")
        if len(set(self.blocking_reasons)) != len(self.blocking_reasons):
            raise ValueError("promotion blocking reasons must be unique")
        if self.assessment_identity != canonical_sha256(
            _promotion_assessment_payload(self)
        ):
            raise ValueError("promotion assessment identity mismatch")


def build_research_partition(
    *,
    dataset_identity: str,
    role: PartitionRole,
    start_ms: int,
    end_ms: int,
    row_count: int,
    evidence_identities: tuple[str, ...],
) -> ResearchPartition:
    normalized_evidence = tuple(sorted(set(evidence_identities)))
    draft = ResearchPartition(
        partition_identity="0" * 64,
        schema_version=ALPHA_FACTORY_SCHEMA_VERSION,
        dataset_identity=dataset_identity,
        role=role,
        start_ms=start_ms,
        end_ms=end_ms,
        row_count=row_count,
        evidence_identities=normalized_evidence,
    )
    return ResearchPartition(
        partition_identity=canonical_sha256(_partition_payload(draft)),
        schema_version=draft.schema_version,
        dataset_identity=draft.dataset_identity,
        role=draft.role,
        start_ms=draft.start_ms,
        end_ms=draft.end_ms,
        row_count=draft.row_count,
        evidence_identities=draft.evidence_identities,
    )


def build_challenger_definition(
    *,
    name: str,
    version: str,
    hypothesis: str,
    rule_definition: str,
    feature_ids: tuple[str, ...],
) -> ChallengerDefinition:
    draft = ChallengerDefinition(
        challenger_identity="0" * 64,
        schema_version=ALPHA_FACTORY_SCHEMA_VERSION,
        name=name,
        version=version,
        hypothesis=hypothesis,
        generator_kind=ResearchGeneratorKind.SYMBOLIC_RULE,
        rule_definition=rule_definition,
        feature_ids=tuple(sorted(set(feature_ids))),
    )
    return ChallengerDefinition(
        challenger_identity=canonical_sha256(_challenger_payload(draft)),
        schema_version=draft.schema_version,
        name=draft.name,
        version=draft.version,
        hypothesis=draft.hypothesis,
        generator_kind=draft.generator_kind,
        rule_definition=draft.rule_definition,
        feature_ids=draft.feature_ids,
    )


def build_research_experiment(
    *,
    challenger: ChallengerDefinition,
    partitions: tuple[ResearchPartition, ...],
    evaluation_policy_version: str,
    cost_stress_profile_identity: str,
    reproducibility_seed: int,
) -> ResearchExperimentManifest:
    by_role = {item.role: item for item in partitions}
    if set(by_role) != set(_PARTITION_ORDER) or len(partitions) != len(_PARTITION_ORDER):
        raise ValueError("experiment requires exactly one partition for each role")
    ordered = tuple(by_role[role] for role in _PARTITION_ORDER)
    dataset_identity = ordered[0].dataset_identity
    draft = ResearchExperimentManifest(
        experiment_identity="0" * 64,
        foundation_version=ALPHA_FACTORY_FOUNDATION_VERSION,
        schema_version=ALPHA_FACTORY_SCHEMA_VERSION,
        challenger_identity=challenger.challenger_identity,
        dataset_identity=dataset_identity,
        partitions=ordered,
        evaluation_policy_version=evaluation_policy_version,
        cost_stress_profile_identity=cost_stress_profile_identity,
        reproducibility_seed=reproducibility_seed,
    )
    return ResearchExperimentManifest(
        experiment_identity=canonical_sha256(_experiment_payload(draft)),
        foundation_version=draft.foundation_version,
        schema_version=draft.schema_version,
        challenger_identity=draft.challenger_identity,
        dataset_identity=draft.dataset_identity,
        partitions=draft.partitions,
        evaluation_policy_version=draft.evaluation_policy_version,
        cost_stress_profile_identity=draft.cost_stress_profile_identity,
        reproducibility_seed=draft.reproducibility_seed,
    )


def build_leakage_audit(
    *,
    experiment_identity: str,
    audited_at_ms: int,
    status: LeakageAuditStatus,
    findings: tuple[str, ...] = (),
    auditor_version: str,
) -> LeakageAudit:
    normalized_findings = tuple(sorted(set(findings)))
    draft = LeakageAudit(
        audit_identity="0" * 64,
        schema_version=ALPHA_FACTORY_SCHEMA_VERSION,
        experiment_identity=experiment_identity,
        audited_at_ms=audited_at_ms,
        status=status,
        findings=normalized_findings,
        auditor_version=auditor_version,
    )
    return LeakageAudit(
        audit_identity=canonical_sha256(_leakage_audit_payload(draft)),
        schema_version=draft.schema_version,
        experiment_identity=draft.experiment_identity,
        audited_at_ms=draft.audited_at_ms,
        status=draft.status,
        findings=draft.findings,
        auditor_version=draft.auditor_version,
    )


def build_promotion_gate_evidence(
    *,
    experiment_identity: str,
    data_contract_audit_identity: str | None = None,
    reproducibility_identity: str | None = None,
    transaction_cost_stress_identity: str | None = None,
    in_sample_sanity_identity: str | None = None,
    out_of_sample_identity: str | None = None,
    walk_forward_identity: str | None = None,
    untouched_forward_identity: str | None = None,
    robustness_ablation_identity: str | None = None,
    supervisor_acceptance_identity: str | None = None,
) -> PromotionGateEvidence:
    draft = PromotionGateEvidence(
        evidence_identity="0" * 64,
        schema_version=ALPHA_FACTORY_SCHEMA_VERSION,
        experiment_identity=experiment_identity,
        data_contract_audit_identity=data_contract_audit_identity,
        reproducibility_identity=reproducibility_identity,
        transaction_cost_stress_identity=transaction_cost_stress_identity,
        in_sample_sanity_identity=in_sample_sanity_identity,
        out_of_sample_identity=out_of_sample_identity,
        walk_forward_identity=walk_forward_identity,
        untouched_forward_identity=untouched_forward_identity,
        robustness_ablation_identity=robustness_ablation_identity,
        supervisor_acceptance_identity=supervisor_acceptance_identity,
    )
    return PromotionGateEvidence(
        evidence_identity=canonical_sha256(_promotion_evidence_payload(draft)),
        schema_version=draft.schema_version,
        experiment_identity=draft.experiment_identity,
        data_contract_audit_identity=draft.data_contract_audit_identity,
        reproducibility_identity=draft.reproducibility_identity,
        transaction_cost_stress_identity=draft.transaction_cost_stress_identity,
        in_sample_sanity_identity=draft.in_sample_sanity_identity,
        out_of_sample_identity=draft.out_of_sample_identity,
        walk_forward_identity=draft.walk_forward_identity,
        untouched_forward_identity=draft.untouched_forward_identity,
        robustness_ablation_identity=draft.robustness_ablation_identity,
        supervisor_acceptance_identity=draft.supervisor_acceptance_identity,
    )


def assess_promotion_gate(
    *,
    experiment: ResearchExperimentManifest,
    leakage_audit: LeakageAudit,
    evidence: PromotionGateEvidence,
) -> PromotionGateAssessment:
    if leakage_audit.experiment_identity != experiment.experiment_identity:
        raise ValueError("leakage audit does not belong to experiment")
    if evidence.experiment_identity != experiment.experiment_identity:
        raise ValueError("promotion evidence does not belong to experiment")

    reasons: list[str] = []
    if leakage_audit.status is not LeakageAuditStatus.PASSED:
        reasons.append("leakage_audit_not_passed")

    required = (
        ("data_contract_audit", evidence.data_contract_audit_identity),
        ("reproducibility", evidence.reproducibility_identity),
        ("transaction_cost_stress", evidence.transaction_cost_stress_identity),
        ("in_sample_sanity", evidence.in_sample_sanity_identity),
        ("out_of_sample", evidence.out_of_sample_identity),
        ("walk_forward", evidence.walk_forward_identity),
        ("untouched_forward", evidence.untouched_forward_identity),
        ("robustness_ablation", evidence.robustness_ablation_identity),
    )
    for label, identity in required:
        if identity is None:
            reasons.append(f"missing_{label}")

    if reasons:
        status = PromotionGateStatus.BLOCKED
    elif evidence.supervisor_acceptance_identity is None:
        status = PromotionGateStatus.READY_FOR_SUPERVISOR_REVIEW
    else:
        status = (
            PromotionGateStatus.SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION
        )

    normalized_reasons = tuple(sorted(set(reasons)))
    payload = {
        "experiment_identity": experiment.experiment_identity,
        "leakage_audit_identity": leakage_audit.audit_identity,
        "promotion_evidence_identity": evidence.evidence_identity,
        "schema_version": ALPHA_FACTORY_SCHEMA_VERSION,
        "status": status,
        "blocking_reasons": normalized_reasons,
    }
    return PromotionGateAssessment(
        assessment_identity=canonical_sha256(payload),
        schema_version=ALPHA_FACTORY_SCHEMA_VERSION,
        experiment_identity=experiment.experiment_identity,
        leakage_audit_identity=leakage_audit.audit_identity,
        promotion_evidence_identity=evidence.evidence_identity,
        status=status,
        blocking_reasons=normalized_reasons,
    )


def _partition_payload(partition: ResearchPartition) -> dict[str, object]:
    return {
        "dataset_identity": partition.dataset_identity,
        "end_ms": partition.end_ms,
        "evidence_identities": partition.evidence_identities,
        "role": partition.role,
        "row_count": partition.row_count,
        "schema_version": partition.schema_version,
        "start_ms": partition.start_ms,
    }


def _challenger_payload(challenger: ChallengerDefinition) -> dict[str, object]:
    return {
        "feature_ids": challenger.feature_ids,
        "generator_kind": challenger.generator_kind,
        "hypothesis": challenger.hypothesis,
        "name": challenger.name,
        "rule_definition": challenger.rule_definition,
        "schema_version": challenger.schema_version,
        "version": challenger.version,
    }


def _experiment_payload(
    experiment: ResearchExperimentManifest,
) -> dict[str, object]:
    return {
        "authority": experiment.authority,
        "can_self_promote": experiment.can_self_promote,
        "challenger_identity": experiment.challenger_identity,
        "champion_write_authority": experiment.champion_write_authority,
        "cost_stress_profile_identity": experiment.cost_stress_profile_identity,
        "dataset_identity": experiment.dataset_identity,
        "evaluation_policy_version": experiment.evaluation_policy_version,
        "foundation_version": experiment.foundation_version,
        "partition_identities": tuple(
            item.partition_identity for item in experiment.partitions
        ),
        "real_capital": experiment.real_capital,
        "reproducibility_seed": experiment.reproducibility_seed,
        "schema_version": experiment.schema_version,
    }


def _leakage_audit_payload(audit: LeakageAudit) -> dict[str, object]:
    return {
        "audited_at_ms": audit.audited_at_ms,
        "auditor_version": audit.auditor_version,
        "experiment_identity": audit.experiment_identity,
        "findings": audit.findings,
        "schema_version": audit.schema_version,
        "status": audit.status,
    }


def _promotion_evidence_fields(
    evidence: PromotionGateEvidence,
) -> tuple[tuple[str, str | None], ...]:
    return (
        ("data contract audit identity", evidence.data_contract_audit_identity),
        ("reproducibility identity", evidence.reproducibility_identity),
        (
            "transaction cost stress identity",
            evidence.transaction_cost_stress_identity,
        ),
        ("in sample sanity identity", evidence.in_sample_sanity_identity),
        ("out of sample identity", evidence.out_of_sample_identity),
        ("walk forward identity", evidence.walk_forward_identity),
        ("untouched forward identity", evidence.untouched_forward_identity),
        (
            "robustness ablation identity",
            evidence.robustness_ablation_identity,
        ),
        (
            "supervisor acceptance identity",
            evidence.supervisor_acceptance_identity,
        ),
    )


def _promotion_evidence_payload(
    evidence: PromotionGateEvidence,
) -> dict[str, object]:
    return {
        "data_contract_audit_identity": evidence.data_contract_audit_identity,
        "experiment_identity": evidence.experiment_identity,
        "in_sample_sanity_identity": evidence.in_sample_sanity_identity,
        "out_of_sample_identity": evidence.out_of_sample_identity,
        "reproducibility_identity": evidence.reproducibility_identity,
        "robustness_ablation_identity": evidence.robustness_ablation_identity,
        "schema_version": evidence.schema_version,
        "supervisor_acceptance_identity": (
            evidence.supervisor_acceptance_identity
        ),
        "transaction_cost_stress_identity": (
            evidence.transaction_cost_stress_identity
        ),
        "untouched_forward_identity": evidence.untouched_forward_identity,
        "walk_forward_identity": evidence.walk_forward_identity,
    }


def _promotion_assessment_payload(
    assessment: PromotionGateAssessment,
) -> dict[str, object]:
    return {
        "blocking_reasons": assessment.blocking_reasons,
        "experiment_identity": assessment.experiment_identity,
        "leakage_audit_identity": assessment.leakage_audit_identity,
        "promotion_evidence_identity": assessment.promotion_evidence_identity,
        "schema_version": assessment.schema_version,
        "status": assessment.status,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be SHA256")


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")
