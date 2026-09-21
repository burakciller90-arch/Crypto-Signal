from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import combinations, product
from statistics import median

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import (
    ALPHA_FACTORY_SCHEMA_VERSION,
    ChallengerDefinition,
    PartitionRole,
    ResearchPartition,
    build_challenger_definition,
)

SYMBOLIC_RULE_ENGINE_VERSION = "alpha-factory-symbolic-rule-v1/1"
SYMBOLIC_EVALUATION_SCHEMA_VERSION = "alpha-factory-symbolic-evaluation-v1/1"
MAX_SYMBOLIC_FEATURES = 8
MAX_VALUES_PER_FEATURE = 8
MAX_PREDICATES = 2
MAX_CHALLENGERS = 256


class ResearchEvaluationSemantic(StrEnum):
    DESCRIPTIVE_NET_R_NOT_PROBABILITY = "descriptive_net_r_not_probability"


@dataclass(frozen=True, slots=True)
class SymbolicFeatureSpec:
    feature_identity: str
    feature_id: str
    feature_version: str
    allowed_values: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.feature_identity, "feature identity")
        _require_token(self.feature_id, "feature id")
        _require_token(self.feature_version, "feature version")
        if not 1 <= len(self.allowed_values) <= MAX_VALUES_PER_FEATURE:
            raise ValueError("symbolic feature requires 1..8 allowed values")
        if tuple(sorted(set(self.allowed_values))) != self.allowed_values:
            raise ValueError("allowed values must be sorted and unique")
        for value in self.allowed_values:
            _require_token(value, "allowed feature value")
        if self.feature_identity != canonical_sha256(_feature_payload(self)):
            raise ValueError("symbolic feature identity mismatch")


@dataclass(frozen=True, slots=True)
class SymbolicPredicate:
    predicate_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    expected_value: str

    def __post_init__(self) -> None:
        _require_sha256(self.predicate_identity, "predicate identity")
        _require_sha256(self.feature_identity, "feature identity")
        _require_token(self.feature_id, "predicate feature id")
        _require_token(self.feature_version, "predicate feature version")
        _require_token(self.expected_value, "predicate expected value")
        if self.predicate_identity != canonical_sha256(
            _predicate_payload(self)
        ):
            raise ValueError("symbolic predicate identity mismatch")


@dataclass(frozen=True, slots=True)
class GeneratedSymbolicChallenger:
    generated_identity: str
    engine_version: str
    definition: ChallengerDefinition
    predicates: tuple[SymbolicPredicate, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.generated_identity, "generated challenger identity")
        if self.engine_version != SYMBOLIC_RULE_ENGINE_VERSION:
            raise ValueError("unsupported symbolic-rule engine version")
        if not 1 <= len(self.predicates) <= MAX_PREDICATES:
            raise ValueError("symbolic challenger requires 1..2 predicates")
        ordered = tuple(
            sorted(
                self.predicates,
                key=lambda item: (
                    item.feature_id,
                    item.feature_version,
                    item.expected_value,
                ),
            )
        )
        if ordered != self.predicates:
            raise ValueError("symbolic predicates must be canonically ordered")
        feature_ids = tuple(item.feature_id for item in self.predicates)
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("symbolic challenger cannot repeat a feature")
        if self.definition.feature_ids != tuple(sorted(feature_ids)):
            raise ValueError("challenger feature ids do not match predicates")
        if self.definition.rule_definition != _rule_text(self.predicates):
            raise ValueError("challenger rule definition mismatch")
        if self.generated_identity != canonical_sha256(
            _generated_challenger_payload(self)
        ):
            raise ValueError("generated challenger identity mismatch")


@dataclass(frozen=True, slots=True)
class SymbolicSearchConfig:
    max_predicates: int = MAX_PREDICATES
    max_challengers: int = 128

    def __post_init__(self) -> None:
        if not 1 <= self.max_predicates <= MAX_PREDICATES:
            raise ValueError("max_predicates must be between 1 and 2")
        if not 1 <= self.max_challengers <= MAX_CHALLENGERS:
            raise ValueError("max_challengers must be between 1 and 256")


DEFAULT_SYMBOLIC_SEARCH_CONFIG = SymbolicSearchConfig()


@dataclass(frozen=True, slots=True)
class SymbolicResearchObservation:
    observation_identity: str
    schema_version: str
    partition_identity: str
    source_evidence_identity: str
    decision_as_of_ms: int
    feature_available_at_ms: int
    outcome_available_at_ms: int
    feature_values: tuple[tuple[str, str], ...]
    gross_outcome_r: Decimal
    explicit_cost_r: Decimal
    net_outcome_r: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "research observation identity")
        _require_sha256(self.partition_identity, "partition identity")
        _require_sha256(self.source_evidence_identity, "source evidence identity")
        if self.schema_version != SYMBOLIC_EVALUATION_SCHEMA_VERSION:
            raise ValueError("unsupported symbolic observation schema")
        if min(
            self.decision_as_of_ms,
            self.feature_available_at_ms,
            self.outcome_available_at_ms,
        ) < 0:
            raise ValueError("research observation times must be non-negative")
        if self.feature_available_at_ms > self.decision_as_of_ms:
            raise ValueError("feature evidence is unavailable at decision as-of")
        if self.outcome_available_at_ms < self.decision_as_of_ms:
            raise ValueError("outcome cannot be available before decision as-of")
        if not self.feature_values:
            raise ValueError("research observation requires feature values")
        feature_ids = tuple(item[0] for item in self.feature_values)
        if feature_ids != tuple(sorted(set(feature_ids))):
            raise ValueError("observation feature ids must be sorted and unique")
        for feature_id, value in self.feature_values:
            _require_token(feature_id, "observation feature id")
            _require_token(value, "observation feature value")
        if self.explicit_cost_r < Decimal(0):
            raise ValueError("explicit research cost R must be non-negative")
        if self.net_outcome_r != self.gross_outcome_r - self.explicit_cost_r:
            raise ValueError("net outcome R must equal gross R minus explicit cost R")
        if self.observation_identity != canonical_sha256(
            _observation_payload(self)
        ):
            raise ValueError("research observation identity mismatch")


@dataclass(frozen=True, slots=True)
class SymbolicEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    challenger_identity: str
    partition_identity: str
    partition_role: PartitionRole
    semantic: ResearchEvaluationSemantic
    observation_count: int
    matched_count: int
    matched_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    median_net_r: Decimal | None
    max_drawdown_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_identity, "symbolic evaluation identity")
        _require_sha256(self.challenger_identity, "challenger identity")
        _require_sha256(self.partition_identity, "partition identity")
        if self.schema_version != SYMBOLIC_EVALUATION_SCHEMA_VERSION:
            raise ValueError("unsupported symbolic evaluation schema")
        if self.engine_version != SYMBOLIC_RULE_ENGINE_VERSION:
            raise ValueError("unsupported symbolic evaluation engine")
        if self.semantic is not (
            ResearchEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
        ):
            raise ValueError("unsupported research evaluation semantic")
        if self.partition_role is PartitionRole.UNTOUCHED_FORWARD:
            raise ValueError("symbolic v1 cannot evaluate untouched-forward data")
        if self.observation_count <= 0:
            raise ValueError("symbolic evaluation requires observations")
        if not 0 <= self.matched_count <= self.observation_count:
            raise ValueError("symbolic matched count is invalid")
        if self.matched_count != len(self.matched_observation_identities):
            raise ValueError("matched count must equal matched identity count")
        if tuple(sorted(set(self.matched_observation_identities))) != (
            self.matched_observation_identities
        ):
            raise ValueError("matched observation identities must be sorted and unique")
        metrics = (
            self.gross_r_total,
            self.explicit_cost_r_total,
            self.net_r_total,
            self.average_net_r,
            self.median_net_r,
            self.max_drawdown_r,
        )
        if self.matched_count == 0:
            if any(value is not None for value in metrics):
                raise ValueError("no-match evaluation cannot carry performance metrics")
        else:
            if any(value is None for value in metrics):
                raise ValueError("matched evaluation requires all performance metrics")
            if (
                self.explicit_cost_r_total is not None
                and self.explicit_cost_r_total < 0
            ):
                raise ValueError("evaluation cost total must be non-negative")
            if self.max_drawdown_r is not None and self.max_drawdown_r < 0:
                raise ValueError("evaluation max drawdown must be non-negative")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("symbolic evaluation identity mismatch")


def build_symbolic_feature(
    *,
    feature_id: str,
    feature_version: str,
    allowed_values: tuple[str, ...],
) -> SymbolicFeatureSpec:
    normalized_values = tuple(sorted(set(allowed_values)))
    payload = {
        "allowed_values": normalized_values,
        "feature_id": feature_id,
        "feature_version": feature_version,
    }
    return SymbolicFeatureSpec(
        feature_identity=canonical_sha256(payload),
        feature_id=feature_id,
        feature_version=feature_version,
        allowed_values=normalized_values,
    )


def generate_symbolic_challengers(
    features: Sequence[SymbolicFeatureSpec],
    *,
    config: SymbolicSearchConfig = DEFAULT_SYMBOLIC_SEARCH_CONFIG,
) -> tuple[GeneratedSymbolicChallenger, ...]:
    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    if not 1 <= len(ordered_features) <= MAX_SYMBOLIC_FEATURES:
        raise ValueError("symbolic generation requires 1..8 features")
    ids = tuple(item.feature_id for item in ordered_features)
    if len(set(ids)) != len(ids):
        raise ValueError("symbolic generation requires unique feature ids")
    identities = tuple(item.feature_identity for item in ordered_features)
    if len(set(identities)) != len(identities):
        raise ValueError("symbolic generation requires unique feature identities")

    generated: list[GeneratedSymbolicChallenger] = []
    max_width = min(config.max_predicates, len(ordered_features))
    for width in range(1, max_width + 1):
        for feature_group in combinations(ordered_features, width):
            value_sets = tuple(item.allowed_values for item in feature_group)
            for values in product(*value_sets):
                predicates = tuple(
                    _build_predicate(feature, value)
                    for feature, value in zip(
                        feature_group,
                        values,
                        strict=True,
                    )
                )
                generated.append(_build_generated_challenger(predicates))
                if len(generated) >= config.max_challengers:
                    return tuple(generated)
    return tuple(generated)


def build_symbolic_research_observation(
    *,
    partition_identity: str,
    source_evidence_identity: str,
    decision_as_of_ms: int,
    feature_available_at_ms: int,
    outcome_available_at_ms: int,
    feature_values: tuple[tuple[str, str], ...],
    gross_outcome_r: Decimal,
    explicit_cost_r: Decimal,
) -> SymbolicResearchObservation:
    normalized_values = tuple(sorted(dict(feature_values).items()))
    net_outcome_r = gross_outcome_r - explicit_cost_r
    payload = {
        "decision_as_of_ms": decision_as_of_ms,
        "explicit_cost_r": explicit_cost_r,
        "feature_available_at_ms": feature_available_at_ms,
        "feature_values": normalized_values,
        "gross_outcome_r": gross_outcome_r,
        "net_outcome_r": net_outcome_r,
        "outcome_available_at_ms": outcome_available_at_ms,
        "partition_identity": partition_identity,
        "schema_version": SYMBOLIC_EVALUATION_SCHEMA_VERSION,
        "source_evidence_identity": source_evidence_identity,
    }
    return SymbolicResearchObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=SYMBOLIC_EVALUATION_SCHEMA_VERSION,
        partition_identity=partition_identity,
        source_evidence_identity=source_evidence_identity,
        decision_as_of_ms=decision_as_of_ms,
        feature_available_at_ms=feature_available_at_ms,
        outcome_available_at_ms=outcome_available_at_ms,
        feature_values=normalized_values,
        gross_outcome_r=gross_outcome_r,
        explicit_cost_r=explicit_cost_r,
        net_outcome_r=net_outcome_r,
    )


def evaluate_symbolic_challenger(
    challenger: GeneratedSymbolicChallenger,
    partition: ResearchPartition,
    observations: Sequence[SymbolicResearchObservation],
) -> SymbolicEvaluation:
    if partition.role is PartitionRole.UNTOUCHED_FORWARD:
        raise ValueError(
            "untouched-forward evaluation remains closed in symbolic v1"
        )
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
        raise ValueError("symbolic evaluation requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError("evaluation must cover every partition evidence identity")

    observed_source_ids: set[str] = set()
    observed_record_ids: set[str] = set()
    partition_sources = set(partition.evidence_identities)
    for item in ordered:
        if item.partition_identity != partition.partition_identity:
            raise ValueError("observation does not belong to evaluation partition")
        if not partition.start_ms <= item.decision_as_of_ms < partition.end_ms:
            raise ValueError("observation decision time is outside partition")
        if item.source_evidence_identity not in partition_sources:
            raise ValueError("observation source evidence is outside partition")
        if item.source_evidence_identity in observed_source_ids:
            raise ValueError("duplicate source evidence in symbolic evaluation")
        if item.observation_identity in observed_record_ids:
            raise ValueError("duplicate research observation identity")
        observed_source_ids.add(item.source_evidence_identity)
        observed_record_ids.add(item.observation_identity)

    if observed_source_ids != partition_sources:
        raise ValueError("evaluation does not cover exact partition evidence set")

    matches = tuple(
        item
        for item in ordered
        if _observation_matches(challenger.predicates, item)
    )
    matched_ids = tuple(sorted(item.observation_identity for item in matches))
    if matches:
        gross_values = tuple(item.gross_outcome_r for item in matches)
        cost_values = tuple(item.explicit_cost_r for item in matches)
        net_values = tuple(item.net_outcome_r for item in matches)
        gross_total = sum(gross_values, start=Decimal(0))
        cost_total = sum(cost_values, start=Decimal(0))
        net_total = sum(net_values, start=Decimal(0))
        average_net = net_total / Decimal(len(net_values))
        median_net = median(net_values)
        max_drawdown = _max_drawdown(net_values)
    else:
        gross_total = None
        cost_total = None
        net_total = None
        average_net = None
        median_net = None
        max_drawdown = None

    payload = {
        "average_net_r": average_net,
        "challenger_identity": challenger.definition.challenger_identity,
        "engine_version": SYMBOLIC_RULE_ENGINE_VERSION,
        "explicit_cost_r_total": cost_total,
        "gross_r_total": gross_total,
        "matched_count": len(matches),
        "matched_observation_identities": matched_ids,
        "max_drawdown_r": max_drawdown,
        "median_net_r": median_net,
        "net_r_total": net_total,
        "observation_count": len(ordered),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "schema_version": SYMBOLIC_EVALUATION_SCHEMA_VERSION,
        "semantic": (
            ResearchEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
        ),
    }
    return SymbolicEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=SYMBOLIC_EVALUATION_SCHEMA_VERSION,
        engine_version=SYMBOLIC_RULE_ENGINE_VERSION,
        challenger_identity=challenger.definition.challenger_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=ResearchEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY,
        observation_count=len(ordered),
        matched_count=len(matches),
        matched_observation_identities=matched_ids,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
        median_net_r=median_net,
        max_drawdown_r=max_drawdown,
    )


def _build_predicate(
    feature: SymbolicFeatureSpec,
    expected_value: str,
) -> SymbolicPredicate:
    if expected_value not in feature.allowed_values:
        raise ValueError("predicate value is not allowed by feature spec")
    payload = {
        "expected_value": expected_value,
        "feature_id": feature.feature_id,
        "feature_identity": feature.feature_identity,
        "feature_version": feature.feature_version,
    }
    return SymbolicPredicate(
        predicate_identity=canonical_sha256(payload),
        feature_identity=feature.feature_identity,
        feature_id=feature.feature_id,
        feature_version=feature.feature_version,
        expected_value=expected_value,
    )


def _build_generated_challenger(
    predicates: tuple[SymbolicPredicate, ...],
) -> GeneratedSymbolicChallenger:
    ordered = tuple(
        sorted(
            predicates,
            key=lambda item: (
                item.feature_id,
                item.feature_version,
                item.expected_value,
            ),
        )
    )
    rule_definition = _rule_text(ordered)
    rule_key = canonical_sha256(
        tuple(item.predicate_identity for item in ordered)
    )[:16]
    definition = build_challenger_definition(
        name=f"symbolic-{rule_key}",
        version=SYMBOLIC_RULE_ENGINE_VERSION,
        hypothesis=f"research-only conjunction: {rule_definition}",
        rule_definition=rule_definition,
        feature_ids=tuple(sorted(item.feature_id for item in ordered)),
    )
    payload = {
        "challenger_identity": definition.challenger_identity,
        "engine_version": SYMBOLIC_RULE_ENGINE_VERSION,
        "predicate_identities": tuple(
            item.predicate_identity for item in ordered
        ),
    }
    return GeneratedSymbolicChallenger(
        generated_identity=canonical_sha256(payload),
        engine_version=SYMBOLIC_RULE_ENGINE_VERSION,
        definition=definition,
        predicates=ordered,
    )


def _observation_matches(
    predicates: tuple[SymbolicPredicate, ...],
    observation: SymbolicResearchObservation,
) -> bool:
    values = dict(observation.feature_values)
    for predicate in predicates:
        if predicate.feature_id not in values:
            raise ValueError(
                f"observation missing challenger feature: {predicate.feature_id}"
            )
        if values[predicate.feature_id] != predicate.expected_value:
            return False
    return True


def _max_drawdown(values: tuple[Decimal, ...]) -> Decimal:
    equity = Decimal(0)
    peak = Decimal(0)
    max_drawdown = Decimal(0)
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def _rule_text(predicates: tuple[SymbolicPredicate, ...]) -> str:
    return " && ".join(
        (
            f"{item.feature_id}@{item.feature_version}"
            f"=={item.expected_value}"
        )
        for item in predicates
    )


def _feature_payload(feature: SymbolicFeatureSpec) -> dict[str, object]:
    return {
        "allowed_values": feature.allowed_values,
        "feature_id": feature.feature_id,
        "feature_version": feature.feature_version,
    }


def _predicate_payload(predicate: SymbolicPredicate) -> dict[str, object]:
    return {
        "expected_value": predicate.expected_value,
        "feature_id": predicate.feature_id,
        "feature_identity": predicate.feature_identity,
        "feature_version": predicate.feature_version,
    }


def _generated_challenger_payload(
    challenger: GeneratedSymbolicChallenger,
) -> dict[str, object]:
    return {
        "challenger_identity": challenger.definition.challenger_identity,
        "engine_version": challenger.engine_version,
        "predicate_identities": tuple(
            item.predicate_identity for item in challenger.predicates
        ),
    }


def _observation_payload(
    observation: SymbolicResearchObservation,
) -> dict[str, object]:
    return {
        "decision_as_of_ms": observation.decision_as_of_ms,
        "explicit_cost_r": observation.explicit_cost_r,
        "feature_available_at_ms": observation.feature_available_at_ms,
        "feature_values": observation.feature_values,
        "gross_outcome_r": observation.gross_outcome_r,
        "net_outcome_r": observation.net_outcome_r,
        "outcome_available_at_ms": observation.outcome_available_at_ms,
        "partition_identity": observation.partition_identity,
        "schema_version": observation.schema_version,
        "source_evidence_identity": observation.source_evidence_identity,
    }


def _evaluation_payload(evaluation: SymbolicEvaluation) -> dict[str, object]:
    return {
        "average_net_r": evaluation.average_net_r,
        "challenger_identity": evaluation.challenger_identity,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "gross_r_total": evaluation.gross_r_total,
        "matched_count": evaluation.matched_count,
        "matched_observation_identities": (
            evaluation.matched_observation_identities
        ),
        "max_drawdown_r": evaluation.max_drawdown_r,
        "median_net_r": evaluation.median_net_r,
        "net_r_total": evaluation.net_r_total,
        "observation_count": evaluation.observation_count,
        "partition_identity": evaluation.partition_identity,
        "partition_role": evaluation.partition_role,
        "schema_version": evaluation.schema_version,
        "semantic": evaluation.semantic,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be SHA256")


def _require_token(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must be non-empty")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.:-"
    )
    if any(character not in allowed for character in value):
        raise ValueError(f"{label} contains unsupported characters")
