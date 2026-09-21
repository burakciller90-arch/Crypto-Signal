from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import combinations, product
from statistics import median

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import (
    ClusterResearchObservation,
)
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

INTERACTION_ENGINE_VERSION = "alpha-factory-feature-interaction-v1/1"
INTERACTION_SCHEMA_VERSION = "alpha-factory-feature-interaction-schema-v1/1"
MAX_INTERACTION_FEATURES = 6
MAX_VALUES_PER_FEATURE = 8
INTERACTION_ORDER = 2
MAX_INTERACTION_HYPOTHESES = 256


class InteractionEvaluationSemantic(StrEnum):
    DESCRIPTIVE_INCREMENT_NOT_CAUSAL_OR_PROBABILITY = (
        "descriptive_increment_not_causal_or_probability"
    )


class MultipleTestingControlStatus(StrEnum):
    BOUNDED_INTERACTION_SET_NO_AUTOMATIC_SELECTION = (
        "bounded_interaction_set_no_automatic_selection"
    )


@dataclass(frozen=True, slots=True)
class InteractionPredicate:
    predicate_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    expected_value: str

    def __post_init__(self) -> None:
        _require_sha256(self.predicate_identity, "interaction predicate identity")
        _require_sha256(self.feature_identity, "interaction feature identity")
        _require_token(self.feature_id, "interaction feature id")
        _require_token(self.feature_version, "interaction feature version")
        _require_token(self.expected_value, "interaction expected value")
        if self.predicate_identity != canonical_sha256(
            _predicate_payload(self)
        ):
            raise ValueError("interaction predicate identity mismatch")


@dataclass(frozen=True, slots=True)
class GeneratedInteractionHypothesis:
    hypothesis_identity: str
    engine_version: str
    training_partition_identity: str
    predicates: tuple[InteractionPredicate, InteractionPredicate]
    training_support_count: int
    training_support_snapshot_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.hypothesis_identity, "interaction hypothesis identity")
        _require_sha256(
            self.training_partition_identity,
            "interaction training partition identity",
        )
        if self.engine_version != INTERACTION_ENGINE_VERSION:
            raise ValueError("unsupported interaction engine version")
        if self.training_support_count <= 0:
            raise ValueError("interaction support must be positive")
        if self.training_support_count != len(
            self.training_support_snapshot_identities
        ):
            raise ValueError("interaction support count does not match snapshots")
        if tuple(sorted(set(self.training_support_snapshot_identities))) != (
            self.training_support_snapshot_identities
        ):
            raise ValueError(
                "interaction support snapshots must be sorted and unique"
            )
        for identity in self.training_support_snapshot_identities:
            _require_sha256(identity, "interaction support snapshot identity")
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
            raise ValueError("interaction predicates must be canonical")
        if self.predicates[0].feature_id == self.predicates[1].feature_id:
            raise ValueError("interaction requires two distinct features")
        if self.hypothesis_identity != canonical_sha256(
            _hypothesis_payload(self)
        ):
            raise ValueError("interaction hypothesis identity mismatch")


@dataclass(frozen=True, slots=True)
class InteractionSearchConfig:
    min_train_support: int = 2
    max_hypotheses: int = 128

    def __post_init__(self) -> None:
        if self.min_train_support <= 0:
            raise ValueError("interaction min_train_support must be positive")
        if not 1 <= self.max_hypotheses <= MAX_INTERACTION_HYPOTHESES:
            raise ValueError(
                "interaction max_hypotheses must be between 1 and 256"
            )

    @property
    def config_identity(self) -> str:
        return canonical_sha256(
            {
                "interaction_order": INTERACTION_ORDER,
                "max_hypotheses": self.max_hypotheses,
                "min_train_support": self.min_train_support,
            }
        )


DEFAULT_INTERACTION_SEARCH_CONFIG = InteractionSearchConfig()


@dataclass(frozen=True, slots=True)
class InteractionSearchManifest:
    search_identity: str
    engine_version: str
    config_identity: str
    training_partition_identity: str
    feature_identities: tuple[str, ...]
    hypothesis_identities: tuple[str, ...]
    candidates_considered: int
    multiple_testing_status: MultipleTestingControlStatus
    automatic_selection: bool
    outcome_used_in_generation: bool
    out_of_sample_used_in_generation: bool
    untouched_forward_used: bool

    def __post_init__(self) -> None:
        _require_sha256(self.search_identity, "interaction search identity")
        _require_sha256(self.config_identity, "interaction config identity")
        _require_sha256(
            self.training_partition_identity,
            "interaction training partition identity",
        )
        for identity in self.feature_identities:
            _require_sha256(identity, "interaction search feature identity")
        for identity in self.hypothesis_identities:
            _require_sha256(identity, "interaction hypothesis identity")
        if self.engine_version != INTERACTION_ENGINE_VERSION:
            raise ValueError("unsupported interaction search engine")
        if self.candidates_considered <= 0:
            raise ValueError("interaction search must consider candidates")
        if self.multiple_testing_status is not (
            MultipleTestingControlStatus
            .BOUNDED_INTERACTION_SET_NO_AUTOMATIC_SELECTION
        ):
            raise ValueError("unsupported interaction multiple-testing status")
        if self.automatic_selection:
            raise ValueError("interaction v1 cannot automatically select")
        if self.outcome_used_in_generation:
            raise ValueError("interaction generation cannot use outcomes")
        if self.out_of_sample_used_in_generation:
            raise ValueError("interaction generation cannot use OOS")
        if self.untouched_forward_used:
            raise ValueError("interaction v1 cannot use untouched-forward")
        if self.search_identity != canonical_sha256(
            _search_manifest_payload(self)
        ):
            raise ValueError("interaction search identity mismatch")


@dataclass(frozen=True, slots=True)
class InteractionMetric:
    metric_identity: str
    label: str
    observation_count: int
    observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    median_net_r: Decimal | None
    max_drawdown_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.metric_identity, "interaction metric identity")
        _require_token(self.label, "interaction metric label")
        if self.observation_count < 0:
            raise ValueError("interaction observation_count cannot be negative")
        if self.observation_count != len(self.observation_identities):
            raise ValueError("interaction metric count does not match identities")
        if tuple(sorted(set(self.observation_identities))) != (
            self.observation_identities
        ):
            raise ValueError(
                "interaction metric observation identities must be unique"
            )
        for identity in self.observation_identities:
            _require_sha256(identity, "interaction observation identity")
        metrics = (
            self.gross_r_total,
            self.explicit_cost_r_total,
            self.net_r_total,
            self.average_net_r,
            self.median_net_r,
            self.max_drawdown_r,
        )
        if self.observation_count == 0:
            if any(value is not None for value in metrics):
                raise ValueError(
                    "empty interaction metric cannot carry performance values"
                )
        else:
            if any(value is None for value in metrics):
                raise ValueError(
                    "non-empty interaction metric requires all performance values"
                )
            if (
                self.explicit_cost_r_total is not None
                and self.explicit_cost_r_total < 0
            ):
                raise ValueError("interaction cost total must be non-negative")
            if self.max_drawdown_r is not None and self.max_drawdown_r < 0:
                raise ValueError("interaction drawdown must be non-negative")
        if self.metric_identity != canonical_sha256(_metric_payload(self)):
            raise ValueError("interaction metric identity mismatch")


@dataclass(frozen=True, slots=True)
class InteractionEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    hypothesis_identity: str
    partition_identity: str
    partition_role: PartitionRole
    semantic: InteractionEvaluationSemantic
    interaction_metric: InteractionMetric
    first_marginal_metric: InteractionMetric
    second_marginal_metric: InteractionMetric
    incremental_vs_best_marginal_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_identity, "interaction evaluation identity")
        _require_sha256(self.hypothesis_identity, "interaction hypothesis identity")
        _require_sha256(
            self.partition_identity,
            "interaction evaluation partition identity",
        )
        if self.schema_version != INTERACTION_SCHEMA_VERSION:
            raise ValueError("unsupported interaction evaluation schema")
        if self.engine_version != INTERACTION_ENGINE_VERSION:
            raise ValueError("unsupported interaction evaluation engine")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "interaction evaluation is limited to validation or out-of-sample"
            )
        if self.semantic is not (
            InteractionEvaluationSemantic
            .DESCRIPTIVE_INCREMENT_NOT_CAUSAL_OR_PROBABILITY
        ):
            raise ValueError("unsupported interaction evaluation semantic")
        if self.interaction_metric.observation_count == 0:
            if self.incremental_vs_best_marginal_r is not None:
                raise ValueError(
                    "empty interaction cannot carry incremental metric"
                )
        else:
            if (
                self.interaction_metric.average_net_r is None
                or self.first_marginal_metric.average_net_r is None
                or self.second_marginal_metric.average_net_r is None
            ):
                raise ValueError(
                    "interaction increment requires interaction and marginals"
                )
            expected = self.interaction_metric.average_net_r - max(
                self.first_marginal_metric.average_net_r,
                self.second_marginal_metric.average_net_r,
            )
            if self.incremental_vs_best_marginal_r != expected:
                raise ValueError("interaction incremental metric mismatch")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("interaction evaluation identity mismatch")


def generate_interaction_hypotheses(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    *,
    config: InteractionSearchConfig = DEFAULT_INTERACTION_SEARCH_CONFIG,
) -> tuple[
    tuple[GeneratedInteractionHypothesis, ...],
    InteractionSearchManifest,
]:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("interaction generation requires the train partition")

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_feature_specs(ordered_features)
    ordered_observations = _validate_observation_partition(
        training_partition,
        observations,
        ordered_features,
    )

    generated: list[GeneratedInteractionHypothesis] = []
    candidates_considered = 0
    for first, second in combinations(ordered_features, 2):
        for first_value, second_value in product(
            first.allowed_values,
            second.allowed_values,
        ):
            candidates_considered += 1
            predicates = (
                _build_predicate(first, first_value),
                _build_predicate(second, second_value),
            )
            matched_snapshots = tuple(
                sorted(
                    item.feature_snapshot_identity
                    for item in ordered_observations
                    if _matches(item, predicates)
                )
            )
            if len(matched_snapshots) < config.min_train_support:
                continue
            generated.append(
                _build_hypothesis(
                    predicates=predicates,
                    training_partition=training_partition,
                    matched_snapshots=matched_snapshots,
                )
            )
            if len(generated) >= config.max_hypotheses:
                break
        if len(generated) >= config.max_hypotheses:
            break

    if candidates_considered == 0:
        raise ValueError("interaction search produced no candidate combinations")

    feature_identities = tuple(
        sorted(item.feature_identity for item in ordered_features)
    )
    hypothesis_ids = tuple(item.hypothesis_identity for item in generated)
    payload = {
        "automatic_selection": False,
        "candidates_considered": candidates_considered,
        "config_identity": config.config_identity,
        "engine_version": INTERACTION_ENGINE_VERSION,
        "feature_identities": feature_identities,
        "hypothesis_identities": hypothesis_ids,
        "multiple_testing_status": (
            MultipleTestingControlStatus
            .BOUNDED_INTERACTION_SET_NO_AUTOMATIC_SELECTION
        ),
        "out_of_sample_used_in_generation": False,
        "outcome_used_in_generation": False,
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
    }
    manifest = InteractionSearchManifest(
        search_identity=canonical_sha256(payload),
        engine_version=INTERACTION_ENGINE_VERSION,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        feature_identities=feature_identities,
        hypothesis_identities=hypothesis_ids,
        candidates_considered=candidates_considered,
        multiple_testing_status=(
            MultipleTestingControlStatus
            .BOUNDED_INTERACTION_SET_NO_AUTOMATIC_SELECTION
        ),
        automatic_selection=False,
        outcome_used_in_generation=False,
        out_of_sample_used_in_generation=False,
        untouched_forward_used=False,
    )
    return tuple(generated), manifest


def evaluate_interaction_hypothesis(
    hypothesis: GeneratedInteractionHypothesis,
    partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    features: Sequence[SymbolicFeatureSpec],
) -> InteractionEvaluation:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "interaction evaluation is limited to validation or out-of-sample"
        )
    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_feature_specs(ordered_features)
    _validate_hypothesis_features(hypothesis, ordered_features)
    ordered_observations = _validate_observation_partition(
        partition,
        observations,
        ordered_features,
    )

    first, second = hypothesis.predicates
    interaction_rows = tuple(
        item
        for item in ordered_observations
        if _matches(item, hypothesis.predicates)
    )
    first_rows = tuple(
        item
        for item in ordered_observations
        if _matches(item, (first,))
    )
    second_rows = tuple(
        item
        for item in ordered_observations
        if _matches(item, (second,))
    )

    interaction_metric = _build_metric("interaction", interaction_rows)
    first_metric = _build_metric("first_marginal", first_rows)
    second_metric = _build_metric("second_marginal", second_rows)
    if interaction_metric.observation_count == 0:
        incremental = None
    else:
        assert interaction_metric.average_net_r is not None
        assert first_metric.average_net_r is not None
        assert second_metric.average_net_r is not None
        incremental = interaction_metric.average_net_r - max(
            first_metric.average_net_r,
            second_metric.average_net_r,
        )

    payload = {
        "engine_version": INTERACTION_ENGINE_VERSION,
        "first_marginal_metric_identity": first_metric.metric_identity,
        "hypothesis_identity": hypothesis.hypothesis_identity,
        "incremental_vs_best_marginal_r": incremental,
        "interaction_metric_identity": interaction_metric.metric_identity,
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "schema_version": INTERACTION_SCHEMA_VERSION,
        "second_marginal_metric_identity": second_metric.metric_identity,
        "semantic": (
            InteractionEvaluationSemantic
            .DESCRIPTIVE_INCREMENT_NOT_CAUSAL_OR_PROBABILITY
        ),
    }
    return InteractionEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=INTERACTION_SCHEMA_VERSION,
        engine_version=INTERACTION_ENGINE_VERSION,
        hypothesis_identity=hypothesis.hypothesis_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=(
            InteractionEvaluationSemantic
            .DESCRIPTIVE_INCREMENT_NOT_CAUSAL_OR_PROBABILITY
        ),
        interaction_metric=interaction_metric,
        first_marginal_metric=first_metric,
        second_marginal_metric=second_metric,
        incremental_vs_best_marginal_r=incremental,
    )


def _build_predicate(
    feature: SymbolicFeatureSpec,
    expected_value: str,
) -> InteractionPredicate:
    if expected_value not in feature.allowed_values:
        raise ValueError("interaction value is outside feature contract")
    payload = {
        "expected_value": expected_value,
        "feature_id": feature.feature_id,
        "feature_identity": feature.feature_identity,
        "feature_version": feature.feature_version,
    }
    return InteractionPredicate(
        predicate_identity=canonical_sha256(payload),
        feature_identity=feature.feature_identity,
        feature_id=feature.feature_id,
        feature_version=feature.feature_version,
        expected_value=expected_value,
    )


def _build_hypothesis(
    *,
    predicates: tuple[InteractionPredicate, InteractionPredicate],
    training_partition: ResearchPartition,
    matched_snapshots: tuple[str, ...],
) -> GeneratedInteractionHypothesis:
    payload = {
        "engine_version": INTERACTION_ENGINE_VERSION,
        "predicates": tuple(
            item.predicate_identity for item in predicates
        ),
        "training_partition_identity": training_partition.partition_identity,
        "training_support_count": len(matched_snapshots),
        "training_support_snapshot_identities": matched_snapshots,
    }
    return GeneratedInteractionHypothesis(
        hypothesis_identity=canonical_sha256(payload),
        engine_version=INTERACTION_ENGINE_VERSION,
        training_partition_identity=training_partition.partition_identity,
        predicates=predicates,
        training_support_count=len(matched_snapshots),
        training_support_snapshot_identities=matched_snapshots,
    )


def _build_metric(
    label: str,
    observations: tuple[ClusterResearchObservation, ...],
) -> InteractionMetric:
    ordered = tuple(
        sorted(observations, key=lambda item: item.observation_identity)
    )
    identities = tuple(item.observation_identity for item in ordered)
    if ordered:
        gross_values = tuple(item.gross_outcome_r for item in ordered)
        cost_values = tuple(item.explicit_cost_r for item in ordered)
        net_values = tuple(item.net_outcome_r for item in ordered)
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
        "explicit_cost_r_total": cost_total,
        "gross_r_total": gross_total,
        "label": label,
        "max_drawdown_r": max_drawdown,
        "median_net_r": median_net,
        "net_r_total": net_total,
        "observation_count": len(ordered),
        "observation_identities": identities,
    }
    return InteractionMetric(
        metric_identity=canonical_sha256(payload),
        label=label,
        observation_count=len(ordered),
        observation_identities=identities,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
        median_net_r=median_net,
        max_drawdown_r=max_drawdown,
    )


def _matches(
    observation: ClusterResearchObservation,
    predicates: tuple[InteractionPredicate, ...],
) -> bool:
    values = {
        item.feature_id: item.value
        for item in observation.feature_readings
    }
    return all(
        values.get(item.feature_id) == item.expected_value
        for item in predicates
    )


def _validate_feature_specs(
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    if not 2 <= len(features) <= MAX_INTERACTION_FEATURES:
        raise ValueError("interaction v1 requires 2..6 feature specifications")
    ids = tuple(item.feature_id for item in features)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("interaction feature ids must be sorted and unique")
    identities = tuple(item.feature_identity for item in features)
    if len(set(identities)) != len(identities):
        raise ValueError("interaction feature identities must be unique")
    for item in features:
        if len(item.allowed_values) > MAX_VALUES_PER_FEATURE:
            raise ValueError(
                "interaction v1 supports at most 8 values per feature"
            )


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
                item.feature_snapshot_identity,
            ),
        )
    )
    if not ordered:
        raise ValueError("interaction research requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError(
            "interaction observations must cover the partition exactly"
        )

    feature_by_id = {item.feature_id: item for item in features}
    expected_ids = tuple(sorted(feature_by_id))
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    snapshots: set[str] = set()

    for item in ordered:
        if item.partition_identity != partition.partition_identity:
            raise ValueError("interaction observation belongs to another partition")
        if not partition.start_ms <= item.decision_as_of_ms < partition.end_ms:
            raise ValueError("interaction decision is outside partition")
        if item.source_evidence_identity not in partition_sources:
            raise ValueError("interaction source evidence is outside partition")
        if item.source_evidence_identity in observed_sources:
            raise ValueError("duplicate interaction source evidence")
        if item.feature_snapshot_identity in snapshots:
            raise ValueError("duplicate interaction feature snapshot")
        observed_sources.add(item.source_evidence_identity)
        snapshots.add(item.feature_snapshot_identity)

        reading_ids = tuple(item.feature_id for item in item.feature_readings)
        if reading_ids != expected_ids:
            raise ValueError(
                "interaction observation feature set does not match contract"
            )
        for reading in item.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("interaction reading feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("interaction reading feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError(
                    "interaction reading value is outside feature contract"
                )

    if observed_sources != partition_sources:
        raise ValueError(
            "interaction observations do not cover exact partition evidence set"
        )
    return ordered


def _validate_hypothesis_features(
    hypothesis: GeneratedInteractionHypothesis,
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    feature_by_id = {item.feature_id: item for item in features}
    for predicate in hypothesis.predicates:
        feature = feature_by_id.get(predicate.feature_id)
        if feature is None:
            raise ValueError("interaction hypothesis references missing feature")
        if predicate.feature_identity != feature.feature_identity:
            raise ValueError("interaction hypothesis feature identity mismatch")
        if predicate.feature_version != feature.feature_version:
            raise ValueError("interaction hypothesis feature version mismatch")
        if predicate.expected_value not in feature.allowed_values:
            raise ValueError(
                "interaction hypothesis value is outside feature contract"
            )


def _max_drawdown(values: tuple[Decimal, ...]) -> Decimal:
    equity = Decimal(0)
    peak = Decimal(0)
    max_drawdown = Decimal(0)
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = peak - equity
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def _predicate_payload(
    predicate: InteractionPredicate,
) -> dict[str, object]:
    return {
        "expected_value": predicate.expected_value,
        "feature_id": predicate.feature_id,
        "feature_identity": predicate.feature_identity,
        "feature_version": predicate.feature_version,
    }


def _hypothesis_payload(
    hypothesis: GeneratedInteractionHypothesis,
) -> dict[str, object]:
    return {
        "engine_version": hypothesis.engine_version,
        "predicates": tuple(
            item.predicate_identity for item in hypothesis.predicates
        ),
        "training_partition_identity": hypothesis.training_partition_identity,
        "training_support_count": hypothesis.training_support_count,
        "training_support_snapshot_identities": (
            hypothesis.training_support_snapshot_identities
        ),
    }


def _search_manifest_payload(
    manifest: InteractionSearchManifest,
) -> dict[str, object]:
    return {
        "automatic_selection": manifest.automatic_selection,
        "candidates_considered": manifest.candidates_considered,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "feature_identities": manifest.feature_identities,
        "hypothesis_identities": manifest.hypothesis_identities,
        "multiple_testing_status": manifest.multiple_testing_status,
        "out_of_sample_used_in_generation": (
            manifest.out_of_sample_used_in_generation
        ),
        "outcome_used_in_generation": manifest.outcome_used_in_generation,
        "training_partition_identity": manifest.training_partition_identity,
        "untouched_forward_used": manifest.untouched_forward_used,
    }


def _metric_payload(metric: InteractionMetric) -> dict[str, object]:
    return {
        "average_net_r": metric.average_net_r,
        "explicit_cost_r_total": metric.explicit_cost_r_total,
        "gross_r_total": metric.gross_r_total,
        "label": metric.label,
        "max_drawdown_r": metric.max_drawdown_r,
        "median_net_r": metric.median_net_r,
        "net_r_total": metric.net_r_total,
        "observation_count": metric.observation_count,
        "observation_identities": metric.observation_identities,
    }


def _evaluation_payload(
    evaluation: InteractionEvaluation,
) -> dict[str, object]:
    return {
        "engine_version": evaluation.engine_version,
        "first_marginal_metric_identity": (
            evaluation.first_marginal_metric.metric_identity
        ),
        "hypothesis_identity": evaluation.hypothesis_identity,
        "incremental_vs_best_marginal_r": (
            evaluation.incremental_vs_best_marginal_r
        ),
        "interaction_metric_identity": (
            evaluation.interaction_metric.metric_identity
        ),
        "partition_identity": evaluation.partition_identity,
        "partition_role": evaluation.partition_role,
        "schema_version": evaluation.schema_version,
        "second_marginal_metric_identity": (
            evaluation.second_marginal_metric.metric_identity
        ),
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
