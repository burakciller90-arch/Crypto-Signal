from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from statistics import median

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

CLUSTER_ENGINE_VERSION = "alpha-factory-clustering-regime-v1/1"
CLUSTER_SCHEMA_VERSION = "alpha-factory-clustering-schema-v1/1"
MAX_CLUSTER_FEATURES = 6
MAX_VALUES_PER_FEATURE = 8
MIN_CLUSTERS = 2
MAX_CLUSTERS = 4
MAX_ITERATIONS = 8


class ClusterFitStatus(StrEnum):
    ACCEPTED = "accepted"
    UNRESOLVED_INSUFFICIENT_UNIQUE_PATTERNS = (
        "unresolved_insufficient_unique_patterns"
    )
    UNRESOLVED_SMALL_CLUSTER = "unresolved_small_cluster"
    UNRESOLVED_NOT_CONVERGED = "unresolved_not_converged"


class ClusterEvaluationSemantic(StrEnum):
    DESCRIPTIVE_REGIME_NET_R_NOT_PROBABILITY = (
        "descriptive_regime_net_r_not_probability"
    )


class MultipleTestingControlStatus(StrEnum):
    BOUNDED_CLUSTER_COUNT_NO_AUTOMATIC_SELECTION = (
        "bounded_cluster_count_no_automatic_selection"
    )


@dataclass(frozen=True, slots=True)
class ClusterFeatureReading:
    reading_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    value: str
    available_at_ms: int

    def __post_init__(self) -> None:
        _require_sha256(self.reading_identity, "cluster feature reading identity")
        _require_sha256(self.feature_identity, "cluster feature identity")
        _require_token(self.feature_id, "cluster feature id")
        _require_token(self.feature_version, "cluster feature version")
        _require_token(self.value, "cluster feature value")
        if self.available_at_ms < 0:
            raise ValueError("cluster feature availability must be non-negative")
        if self.reading_identity != canonical_sha256(_reading_payload(self)):
            raise ValueError("cluster feature reading identity mismatch")


@dataclass(frozen=True, slots=True)
class ClusterResearchObservation:
    observation_identity: str
    feature_snapshot_identity: str
    schema_version: str
    partition_identity: str
    source_evidence_identity: str
    decision_as_of_ms: int
    outcome_available_at_ms: int
    feature_readings: tuple[ClusterFeatureReading, ...]
    gross_outcome_r: Decimal
    explicit_cost_r: Decimal
    net_outcome_r: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "cluster observation identity")
        _require_sha256(
            self.feature_snapshot_identity,
            "cluster feature snapshot identity",
        )
        _require_sha256(self.partition_identity, "cluster partition identity")
        _require_sha256(
            self.source_evidence_identity,
            "cluster source evidence identity",
        )
        if self.schema_version != CLUSTER_SCHEMA_VERSION:
            raise ValueError("unsupported cluster observation schema")
        if self.decision_as_of_ms < 0 or self.outcome_available_at_ms < 0:
            raise ValueError("cluster observation times must be non-negative")
        if self.outcome_available_at_ms < self.decision_as_of_ms:
            raise ValueError("cluster outcome cannot predate decision as-of")
        if not self.feature_readings:
            raise ValueError("cluster observation requires feature readings")
        feature_ids = tuple(item.feature_id for item in self.feature_readings)
        if feature_ids != tuple(sorted(set(feature_ids))):
            raise ValueError(
                "cluster feature readings must be sorted and unique"
            )
        for item in self.feature_readings:
            if item.available_at_ms > self.decision_as_of_ms:
                raise ValueError(
                    "cluster feature evidence is unavailable at decision as-of"
                )
        if self.explicit_cost_r < Decimal(0):
            raise ValueError("cluster explicit cost R must be non-negative")
        if self.net_outcome_r != self.gross_outcome_r - self.explicit_cost_r:
            raise ValueError(
                "cluster net outcome R must equal gross R minus explicit cost R"
            )
        if self.feature_snapshot_identity != canonical_sha256(
            _feature_snapshot_payload(self)
        ):
            raise ValueError("cluster feature snapshot identity mismatch")
        if self.observation_identity != canonical_sha256(
            _observation_payload(self)
        ):
            raise ValueError("cluster observation identity mismatch")


@dataclass(frozen=True, slots=True)
class ClusterPrototype:
    prototype_identity: str
    cluster_index: int
    feature_values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_sha256(self.prototype_identity, "cluster prototype identity")
        if self.cluster_index < 0:
            raise ValueError("cluster index must be non-negative")
        if not self.feature_values:
            raise ValueError("cluster prototype requires feature values")
        ids = tuple(item[0] for item in self.feature_values)
        if ids != tuple(sorted(set(ids))):
            raise ValueError(
                "cluster prototype feature values must be sorted and unique"
            )
        for feature_id, value in self.feature_values:
            _require_token(feature_id, "cluster prototype feature id")
            _require_token(value, "cluster prototype value")
        if self.prototype_identity != canonical_sha256(
            _prototype_payload(self)
        ):
            raise ValueError("cluster prototype identity mismatch")


@dataclass(frozen=True, slots=True)
class ClusterSearchConfig:
    min_clusters: int = MIN_CLUSTERS
    max_clusters: int = 3
    max_iterations: int = 6
    min_cluster_size: int = 2

    def __post_init__(self) -> None:
        if not MIN_CLUSTERS <= self.min_clusters <= MAX_CLUSTERS:
            raise ValueError("cluster min_clusters must be between 2 and 4")
        if not self.min_clusters <= self.max_clusters <= MAX_CLUSTERS:
            raise ValueError("cluster max_clusters must be between min and 4")
        if not 1 <= self.max_iterations <= MAX_ITERATIONS:
            raise ValueError("cluster max_iterations must be between 1 and 8")
        if self.min_cluster_size <= 0:
            raise ValueError("cluster min_cluster_size must be positive")

    @property
    def config_identity(self) -> str:
        return canonical_sha256(_config_payload(self))


DEFAULT_CLUSTER_SEARCH_CONFIG = ClusterSearchConfig()


@dataclass(frozen=True, slots=True)
class ClusterFitAttempt:
    attempt_identity: str
    config_identity: str
    training_partition_identity: str
    training_feature_set_identity: str
    cluster_count: int
    status: ClusterFitStatus
    iterations_used: int
    prototype_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.attempt_identity, "cluster fit attempt identity")
        _require_sha256(self.config_identity, "cluster config identity")
        _require_sha256(
            self.training_partition_identity,
            "cluster training partition identity",
        )
        _require_sha256(
            self.training_feature_set_identity,
            "cluster training feature-set identity",
        )
        if not MIN_CLUSTERS <= self.cluster_count <= MAX_CLUSTERS:
            raise ValueError("cluster fit count is outside bounded range")
        if not 0 <= self.iterations_used <= MAX_ITERATIONS:
            raise ValueError("cluster fit iterations_used is invalid")
        for identity in self.prototype_identities:
            _require_sha256(identity, "cluster fit prototype identity")
        if self.status is ClusterFitStatus.ACCEPTED:
            if len(self.prototype_identities) != self.cluster_count:
                raise ValueError(
                    "accepted cluster fit must bind every prototype"
                )
            if self.iterations_used <= 0:
                raise ValueError(
                    "accepted cluster fit requires at least one iteration"
                )
        elif self.prototype_identities:
            raise ValueError(
                "unresolved cluster fit cannot expose accepted prototypes"
            )
        if self.attempt_identity != canonical_sha256(
            _fit_attempt_payload(self)
        ):
            raise ValueError("cluster fit attempt identity mismatch")


@dataclass(frozen=True, slots=True)
class GeneratedClusterModel:
    model_identity: str
    engine_version: str
    config_identity: str
    training_partition_identity: str
    training_feature_set_identity: str
    cluster_count: int
    feature_identities: tuple[str, ...]
    prototypes: tuple[ClusterPrototype, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.model_identity, "cluster model identity")
        _require_sha256(self.config_identity, "cluster config identity")
        _require_sha256(
            self.training_partition_identity,
            "cluster training partition identity",
        )
        _require_sha256(
            self.training_feature_set_identity,
            "cluster training feature-set identity",
        )
        if self.engine_version != CLUSTER_ENGINE_VERSION:
            raise ValueError("unsupported cluster engine version")
        if not MIN_CLUSTERS <= self.cluster_count <= MAX_CLUSTERS:
            raise ValueError("cluster model count is outside bounded range")
        if len(self.prototypes) != self.cluster_count:
            raise ValueError("cluster model prototype count mismatch")
        if tuple(item.cluster_index for item in self.prototypes) != tuple(
            range(self.cluster_count)
        ):
            raise ValueError("cluster prototype indexes must be canonical")
        if tuple(sorted(set(self.feature_identities))) != (
            self.feature_identities
        ):
            raise ValueError(
                "cluster model feature identities must be sorted and unique"
            )
        if self.model_identity != canonical_sha256(_model_payload(self)):
            raise ValueError("cluster model identity mismatch")


@dataclass(frozen=True, slots=True)
class ClusterSearchManifest:
    search_identity: str
    engine_version: str
    config_identity: str
    training_partition_identity: str
    training_feature_set_identity: str
    feature_identities: tuple[str, ...]
    attempt_identities: tuple[str, ...]
    model_identities: tuple[str, ...]
    multiple_testing_status: MultipleTestingControlStatus
    automatic_selection: bool
    out_of_sample_used_in_fit: bool
    untouched_forward_used: bool

    def __post_init__(self) -> None:
        _require_sha256(self.search_identity, "cluster search identity")
        _require_sha256(self.config_identity, "cluster config identity")
        _require_sha256(
            self.training_partition_identity,
            "cluster training partition identity",
        )
        _require_sha256(
            self.training_feature_set_identity,
            "cluster training feature-set identity",
        )
        for identity in self.feature_identities:
            _require_sha256(identity, "cluster search feature identity")
        for identity in self.attempt_identities:
            _require_sha256(identity, "cluster fit attempt identity")
        for identity in self.model_identities:
            _require_sha256(identity, "cluster model identity")
        if self.engine_version != CLUSTER_ENGINE_VERSION:
            raise ValueError("unsupported cluster search engine")
        if self.multiple_testing_status is not (
            MultipleTestingControlStatus
            .BOUNDED_CLUSTER_COUNT_NO_AUTOMATIC_SELECTION
        ):
            raise ValueError("unsupported cluster multiple-testing control")
        if self.automatic_selection:
            raise ValueError("cluster v1 cannot automatically select a model")
        if self.out_of_sample_used_in_fit:
            raise ValueError("cluster fit cannot use out-of-sample data")
        if self.untouched_forward_used:
            raise ValueError("cluster v1 cannot use untouched-forward data")
        if self.search_identity != canonical_sha256(
            _search_manifest_payload(self)
        ):
            raise ValueError("cluster search identity mismatch")


@dataclass(frozen=True, slots=True)
class ClusterEvaluationBucket:
    bucket_identity: str
    cluster_index: int
    observation_count: int
    observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    median_net_r: Decimal | None
    max_drawdown_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.bucket_identity, "cluster bucket identity")
        if self.cluster_index < 0:
            raise ValueError("cluster evaluation index must be non-negative")
        if self.observation_count < 0:
            raise ValueError("cluster observation_count cannot be negative")
        if self.observation_count != len(self.observation_identities):
            raise ValueError("cluster bucket count does not match identities")
        if tuple(sorted(set(self.observation_identities))) != (
            self.observation_identities
        ):
            raise ValueError(
                "cluster bucket observation identities must be sorted and unique"
            )
        for identity in self.observation_identities:
            _require_sha256(identity, "cluster bucket observation identity")
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
                    "empty cluster bucket cannot carry performance metrics"
                )
        else:
            if any(value is None for value in metrics):
                raise ValueError(
                    "non-empty cluster bucket requires all metrics"
                )
            if (
                self.explicit_cost_r_total is not None
                and self.explicit_cost_r_total < 0
            ):
                raise ValueError("cluster bucket costs must be non-negative")
            if self.max_drawdown_r is not None and self.max_drawdown_r < 0:
                raise ValueError("cluster bucket drawdown must be non-negative")
        if self.bucket_identity != canonical_sha256(_bucket_payload(self)):
            raise ValueError("cluster bucket identity mismatch")


@dataclass(frozen=True, slots=True)
class ClusterEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    model_identity: str
    partition_identity: str
    partition_role: PartitionRole
    semantic: ClusterEvaluationSemantic
    observation_count: int
    buckets: tuple[ClusterEvaluationBucket, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_identity, "cluster evaluation identity")
        _require_sha256(self.model_identity, "cluster evaluation model identity")
        _require_sha256(
            self.partition_identity,
            "cluster evaluation partition identity",
        )
        if self.schema_version != CLUSTER_SCHEMA_VERSION:
            raise ValueError("unsupported cluster evaluation schema")
        if self.engine_version != CLUSTER_ENGINE_VERSION:
            raise ValueError("unsupported cluster evaluation engine")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "cluster evaluation is limited to validation or out-of-sample"
            )
        if self.semantic is not (
            ClusterEvaluationSemantic
            .DESCRIPTIVE_REGIME_NET_R_NOT_PROBABILITY
        ):
            raise ValueError("unsupported cluster evaluation semantic")
        if self.observation_count <= 0:
            raise ValueError("cluster evaluation requires observations")
        if sum(item.observation_count for item in self.buckets) != (
            self.observation_count
        ):
            raise ValueError(
                "cluster bucket counts must cover every observation"
            )
        if tuple(item.cluster_index for item in self.buckets) != tuple(
            range(len(self.buckets))
        ):
            raise ValueError("cluster evaluation buckets must be canonical")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("cluster evaluation identity mismatch")


def build_cluster_feature_reading(
    *,
    feature: SymbolicFeatureSpec,
    value: str,
    available_at_ms: int,
) -> ClusterFeatureReading:
    if value not in feature.allowed_values:
        raise ValueError("cluster reading value is outside feature contract")
    payload = {
        "available_at_ms": available_at_ms,
        "feature_id": feature.feature_id,
        "feature_identity": feature.feature_identity,
        "feature_version": feature.feature_version,
        "value": value,
    }
    return ClusterFeatureReading(
        reading_identity=canonical_sha256(payload),
        feature_identity=feature.feature_identity,
        feature_id=feature.feature_id,
        feature_version=feature.feature_version,
        value=value,
        available_at_ms=available_at_ms,
    )


def build_cluster_research_observation(
    *,
    partition_identity: str,
    source_evidence_identity: str,
    decision_as_of_ms: int,
    outcome_available_at_ms: int,
    feature_readings: tuple[ClusterFeatureReading, ...],
    gross_outcome_r: Decimal,
    explicit_cost_r: Decimal,
) -> ClusterResearchObservation:
    ordered_readings = tuple(
        sorted(feature_readings, key=lambda item: item.feature_id)
    )
    snapshot_payload = {
        "decision_as_of_ms": decision_as_of_ms,
        "feature_reading_identities": tuple(
            item.reading_identity for item in ordered_readings
        ),
        "partition_identity": partition_identity,
        "schema_version": CLUSTER_SCHEMA_VERSION,
        "source_evidence_identity": source_evidence_identity,
    }
    feature_snapshot_identity = canonical_sha256(snapshot_payload)
    net_outcome_r = gross_outcome_r - explicit_cost_r
    observation_payload = {
        **snapshot_payload,
        "explicit_cost_r": explicit_cost_r,
        "feature_snapshot_identity": feature_snapshot_identity,
        "gross_outcome_r": gross_outcome_r,
        "net_outcome_r": net_outcome_r,
        "outcome_available_at_ms": outcome_available_at_ms,
    }
    return ClusterResearchObservation(
        observation_identity=canonical_sha256(observation_payload),
        feature_snapshot_identity=feature_snapshot_identity,
        schema_version=CLUSTER_SCHEMA_VERSION,
        partition_identity=partition_identity,
        source_evidence_identity=source_evidence_identity,
        decision_as_of_ms=decision_as_of_ms,
        outcome_available_at_ms=outcome_available_at_ms,
        feature_readings=ordered_readings,
        gross_outcome_r=gross_outcome_r,
        explicit_cost_r=explicit_cost_r,
        net_outcome_r=net_outcome_r,
    )


def fit_cluster_models(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    *,
    config: ClusterSearchConfig = DEFAULT_CLUSTER_SEARCH_CONFIG,
) -> tuple[
    tuple[GeneratedClusterModel, ...],
    tuple[ClusterFitAttempt, ...],
    ClusterSearchManifest,
]:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("cluster fitting requires the train partition")

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_feature_specs(ordered_features)
    ordered_observations = _validate_observation_partition(
        training_partition,
        observations,
        ordered_features,
    )
    training_feature_set_identity = canonical_sha256(
        {
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
    vectors = tuple(_vector(item) for item in ordered_observations)
    unique_vectors = tuple(sorted(set(vectors)))

    models: list[GeneratedClusterModel] = []
    attempts: list[ClusterFitAttempt] = []
    for cluster_count in range(
        config.min_clusters,
        config.max_clusters + 1,
    ):
        model, attempt = _fit_one_cluster_count(
            ordered_features,
            training_partition,
            training_feature_set_identity,
            vectors,
            unique_vectors,
            cluster_count,
            config,
        )
        attempts.append(attempt)
        if model is not None:
            models.append(model)

    manifest_payload = {
        "attempt_identities": tuple(
            item.attempt_identity for item in attempts
        ),
        "automatic_selection": False,
        "config_identity": config.config_identity,
        "engine_version": CLUSTER_ENGINE_VERSION,
        "feature_identities": tuple(
            sorted(item.feature_identity for item in ordered_features)
        ),
        "model_identities": tuple(item.model_identity for item in models),
        "multiple_testing_status": (
            MultipleTestingControlStatus
            .BOUNDED_CLUSTER_COUNT_NO_AUTOMATIC_SELECTION
        ),
        "out_of_sample_used_in_fit": False,
        "training_feature_set_identity": training_feature_set_identity,
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
    }
    manifest = ClusterSearchManifest(
        search_identity=canonical_sha256(manifest_payload),
        engine_version=CLUSTER_ENGINE_VERSION,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        training_feature_set_identity=training_feature_set_identity,
        feature_identities=tuple(
            sorted(item.feature_identity for item in ordered_features)
        ),
        attempt_identities=tuple(
            item.attempt_identity for item in attempts
        ),
        model_identities=tuple(item.model_identity for item in models),
        multiple_testing_status=(
            MultipleTestingControlStatus
            .BOUNDED_CLUSTER_COUNT_NO_AUTOMATIC_SELECTION
        ),
        automatic_selection=False,
        out_of_sample_used_in_fit=False,
        untouched_forward_used=False,
    )
    return tuple(models), tuple(attempts), manifest


def evaluate_cluster_model(
    model: GeneratedClusterModel,
    partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    features: Sequence[SymbolicFeatureSpec],
) -> ClusterEvaluation:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "cluster evaluation is limited to validation or out-of-sample"
        )

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_feature_specs(ordered_features)
    _validate_model_features(model, ordered_features)
    ordered_observations = _validate_observation_partition(
        partition,
        observations,
        ordered_features,
    )

    grouped: list[list[ClusterResearchObservation]] = [
        [] for _ in range(model.cluster_count)
    ]
    prototypes = tuple(
        tuple(value for _, value in item.feature_values)
        for item in model.prototypes
    )
    for observation in ordered_observations:
        grouped[
            _nearest_prototype_index(_vector(observation), prototypes)
        ].append(observation)

    buckets = tuple(
        _build_evaluation_bucket(index, tuple(items))
        for index, items in enumerate(grouped)
    )
    payload = {
        "buckets": tuple(item.bucket_identity for item in buckets),
        "engine_version": CLUSTER_ENGINE_VERSION,
        "model_identity": model.model_identity,
        "observation_count": len(ordered_observations),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "schema_version": CLUSTER_SCHEMA_VERSION,
        "semantic": (
            ClusterEvaluationSemantic
            .DESCRIPTIVE_REGIME_NET_R_NOT_PROBABILITY
        ),
    }
    return ClusterEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=CLUSTER_SCHEMA_VERSION,
        engine_version=CLUSTER_ENGINE_VERSION,
        model_identity=model.model_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=(
            ClusterEvaluationSemantic
            .DESCRIPTIVE_REGIME_NET_R_NOT_PROBABILITY
        ),
        observation_count=len(ordered_observations),
        buckets=buckets,
    )


def _fit_one_cluster_count(
    features: tuple[SymbolicFeatureSpec, ...],
    training_partition: ResearchPartition,
    training_feature_set_identity: str,
    vectors: tuple[tuple[str, ...], ...],
    unique_vectors: tuple[tuple[str, ...], ...],
    cluster_count: int,
    config: ClusterSearchConfig,
) -> tuple[GeneratedClusterModel | None, ClusterFitAttempt]:
    if len(unique_vectors) < cluster_count:
        attempt = _build_attempt(
            config=config,
            training_partition=training_partition,
            training_feature_set_identity=training_feature_set_identity,
            cluster_count=cluster_count,
            status=(
                ClusterFitStatus
                .UNRESOLVED_INSUFFICIENT_UNIQUE_PATTERNS
            ),
            iterations_used=0,
            prototype_identities=(),
        )
        return None, attempt

    prototypes = _initialize_prototypes(unique_vectors, cluster_count)
    converged = False
    assignments: tuple[int, ...] = ()
    iterations_used = 0
    for iteration in range(1, config.max_iterations + 1):
        iterations_used = iteration
        assignments = tuple(
            _nearest_prototype_index(vector, prototypes)
            for vector in vectors
        )
        sizes = tuple(
            assignments.count(index) for index in range(cluster_count)
        )
        if any(size < config.min_cluster_size for size in sizes):
            attempt = _build_attempt(
                config=config,
                training_partition=training_partition,
                training_feature_set_identity=training_feature_set_identity,
                cluster_count=cluster_count,
                status=ClusterFitStatus.UNRESOLVED_SMALL_CLUSTER,
                iterations_used=iterations_used,
                prototype_identities=(),
            )
            return None, attempt

        updated = _update_prototypes(
            vectors,
            assignments,
            cluster_count,
        )
        if updated == prototypes:
            converged = True
            break
        prototypes = updated

    if not converged:
        attempt = _build_attempt(
            config=config,
            training_partition=training_partition,
            training_feature_set_identity=training_feature_set_identity,
            cluster_count=cluster_count,
            status=ClusterFitStatus.UNRESOLVED_NOT_CONVERGED,
            iterations_used=iterations_used,
            prototype_identities=(),
        )
        return None, attempt

    prototype_objects = tuple(
        _build_prototype(index, prototype, features)
        for index, prototype in enumerate(prototypes)
    )
    feature_identities = tuple(
        sorted(item.feature_identity for item in features)
    )
    model_payload = {
        "cluster_count": cluster_count,
        "config_identity": config.config_identity,
        "engine_version": CLUSTER_ENGINE_VERSION,
        "feature_identities": feature_identities,
        "prototype_identities": tuple(
            item.prototype_identity for item in prototype_objects
        ),
        "training_feature_set_identity": training_feature_set_identity,
        "training_partition_identity": training_partition.partition_identity,
    }
    model = GeneratedClusterModel(
        model_identity=canonical_sha256(model_payload),
        engine_version=CLUSTER_ENGINE_VERSION,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        training_feature_set_identity=training_feature_set_identity,
        cluster_count=cluster_count,
        feature_identities=feature_identities,
        prototypes=prototype_objects,
    )
    attempt = _build_attempt(
        config=config,
        training_partition=training_partition,
        training_feature_set_identity=training_feature_set_identity,
        cluster_count=cluster_count,
        status=ClusterFitStatus.ACCEPTED,
        iterations_used=iterations_used,
        prototype_identities=tuple(
            item.prototype_identity for item in prototype_objects
        ),
    )
    return model, attempt


def _initialize_prototypes(
    unique_vectors: tuple[tuple[str, ...], ...],
    cluster_count: int,
) -> tuple[tuple[str, ...], ...]:
    selected: list[tuple[str, ...]] = [unique_vectors[0]]
    while len(selected) < cluster_count:
        remaining = tuple(
            item for item in unique_vectors if item not in selected
        )
        next_vector = max(
            remaining,
            key=lambda item: (
                min(_hamming_distance(item, proto) for proto in selected),
                tuple(item),
            ),
        )
        selected.append(next_vector)
    return tuple(selected)


def _update_prototypes(
    vectors: tuple[tuple[str, ...], ...],
    assignments: tuple[int, ...],
    cluster_count: int,
) -> tuple[tuple[str, ...], ...]:
    updated: list[tuple[str, ...]] = []
    width = len(vectors[0])
    for cluster_index in range(cluster_count):
        members = tuple(
            vector
            for vector, assignment in zip(
                vectors,
                assignments,
                strict=True,
            )
            if assignment == cluster_index
        )
        if not members:
            raise ValueError("cluster update cannot process empty cluster")
        values: list[str] = []
        for column in range(width):
            counts = Counter(member[column] for member in members)
            max_count = max(counts.values())
            values.append(
                min(
                    value
                    for value, count in counts.items()
                    if count == max_count
                )
            )
        updated.append(tuple(values))
    return tuple(updated)


def _nearest_prototype_index(
    vector: tuple[str, ...],
    prototypes: tuple[tuple[str, ...], ...],
) -> int:
    return min(
        range(len(prototypes)),
        key=lambda index: (
            _hamming_distance(vector, prototypes[index]),
            index,
        ),
    )


def _hamming_distance(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> int:
    if len(left) != len(right):
        raise ValueError("cluster vectors must have equal width")
    return sum(
        left_value != right_value
        for left_value, right_value in zip(left, right, strict=True)
    )


def _build_prototype(
    cluster_index: int,
    vector: tuple[str, ...],
    features: tuple[SymbolicFeatureSpec, ...],
) -> ClusterPrototype:
    feature_values = tuple(
        (feature.feature_id, value)
        for feature, value in zip(features, vector, strict=True)
    )
    payload = {
        "cluster_index": cluster_index,
        "feature_values": feature_values,
    }
    return ClusterPrototype(
        prototype_identity=canonical_sha256(payload),
        cluster_index=cluster_index,
        feature_values=feature_values,
    )


def _build_attempt(
    *,
    config: ClusterSearchConfig,
    training_partition: ResearchPartition,
    training_feature_set_identity: str,
    cluster_count: int,
    status: ClusterFitStatus,
    iterations_used: int,
    prototype_identities: tuple[str, ...],
) -> ClusterFitAttempt:
    payload = {
        "cluster_count": cluster_count,
        "config_identity": config.config_identity,
        "iterations_used": iterations_used,
        "prototype_identities": prototype_identities,
        "status": status,
        "training_feature_set_identity": training_feature_set_identity,
        "training_partition_identity": training_partition.partition_identity,
    }
    return ClusterFitAttempt(
        attempt_identity=canonical_sha256(payload),
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        training_feature_set_identity=training_feature_set_identity,
        cluster_count=cluster_count,
        status=status,
        iterations_used=iterations_used,
        prototype_identities=prototype_identities,
    )


def _build_evaluation_bucket(
    cluster_index: int,
    observations: tuple[ClusterResearchObservation, ...],
) -> ClusterEvaluationBucket:
    ordered = tuple(
        sorted(observations, key=lambda item: item.observation_identity)
    )
    ids = tuple(item.observation_identity for item in ordered)
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
        "cluster_index": cluster_index,
        "explicit_cost_r_total": cost_total,
        "gross_r_total": gross_total,
        "max_drawdown_r": max_drawdown,
        "median_net_r": median_net,
        "net_r_total": net_total,
        "observation_count": len(ordered),
        "observation_identities": ids,
    }
    return ClusterEvaluationBucket(
        bucket_identity=canonical_sha256(payload),
        cluster_index=cluster_index,
        observation_count=len(ordered),
        observation_identities=ids,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
        median_net_r=median_net,
        max_drawdown_r=max_drawdown,
    )


def _validate_feature_specs(
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    if not 1 <= len(features) <= MAX_CLUSTER_FEATURES:
        raise ValueError("cluster v1 requires 1..6 feature specifications")
    ids = tuple(item.feature_id for item in features)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("cluster feature ids must be sorted and unique")
    identities = tuple(item.feature_identity for item in features)
    if len(set(identities)) != len(identities):
        raise ValueError("cluster feature identities must be unique")
    for item in features:
        if len(item.allowed_values) > MAX_VALUES_PER_FEATURE:
            raise ValueError(
                "cluster v1 supports at most 8 values per feature"
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
        raise ValueError("cluster research requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError(
            "cluster observations must cover the partition exactly"
        )

    feature_by_id = {item.feature_id: item for item in features}
    expected_feature_ids = tuple(sorted(feature_by_id))
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    observed_snapshots: set[str] = set()

    for item in ordered:
        if item.partition_identity != partition.partition_identity:
            raise ValueError("cluster observation belongs to another partition")
        if not partition.start_ms <= item.decision_as_of_ms < partition.end_ms:
            raise ValueError("cluster decision is outside partition")
        if item.source_evidence_identity not in partition_sources:
            raise ValueError("cluster source evidence is outside partition")
        if item.source_evidence_identity in observed_sources:
            raise ValueError("duplicate cluster source evidence")
        if item.feature_snapshot_identity in observed_snapshots:
            raise ValueError("duplicate cluster feature snapshot")
        observed_sources.add(item.source_evidence_identity)
        observed_snapshots.add(item.feature_snapshot_identity)

        reading_ids = tuple(
            reading.feature_id for reading in item.feature_readings
        )
        if reading_ids != expected_feature_ids:
            raise ValueError(
                "cluster observation feature set does not match contract"
            )
        for reading in item.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("cluster reading feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("cluster reading feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError(
                    "cluster reading value is outside feature contract"
                )

    if observed_sources != partition_sources:
        raise ValueError(
            "cluster observations do not cover exact partition evidence set"
        )
    return ordered


def _validate_model_features(
    model: GeneratedClusterModel,
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    feature_identities = tuple(
        sorted(item.feature_identity for item in features)
    )
    if model.feature_identities != feature_identities:
        raise ValueError("cluster model feature contract mismatch")
    feature_ids = tuple(item.feature_id for item in features)
    for prototype in model.prototypes:
        if tuple(item[0] for item in prototype.feature_values) != feature_ids:
            raise ValueError("cluster prototype feature contract mismatch")


def _vector(
    observation: ClusterResearchObservation,
) -> tuple[str, ...]:
    return tuple(item.value for item in observation.feature_readings)


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


def _reading_payload(
    reading: ClusterFeatureReading,
) -> dict[str, object]:
    return {
        "available_at_ms": reading.available_at_ms,
        "feature_id": reading.feature_id,
        "feature_identity": reading.feature_identity,
        "feature_version": reading.feature_version,
        "value": reading.value,
    }


def _feature_snapshot_payload(
    observation: ClusterResearchObservation,
) -> dict[str, object]:
    return {
        "decision_as_of_ms": observation.decision_as_of_ms,
        "feature_reading_identities": tuple(
            item.reading_identity for item in observation.feature_readings
        ),
        "partition_identity": observation.partition_identity,
        "schema_version": observation.schema_version,
        "source_evidence_identity": observation.source_evidence_identity,
    }


def _observation_payload(
    observation: ClusterResearchObservation,
) -> dict[str, object]:
    return {
        **_feature_snapshot_payload(observation),
        "explicit_cost_r": observation.explicit_cost_r,
        "feature_snapshot_identity": observation.feature_snapshot_identity,
        "gross_outcome_r": observation.gross_outcome_r,
        "net_outcome_r": observation.net_outcome_r,
        "outcome_available_at_ms": observation.outcome_available_at_ms,
    }


def _prototype_payload(
    prototype: ClusterPrototype,
) -> dict[str, object]:
    return {
        "cluster_index": prototype.cluster_index,
        "feature_values": prototype.feature_values,
    }


def _config_payload(config: ClusterSearchConfig) -> dict[str, object]:
    return {
        "max_clusters": config.max_clusters,
        "max_iterations": config.max_iterations,
        "min_cluster_size": config.min_cluster_size,
        "min_clusters": config.min_clusters,
    }


def _fit_attempt_payload(
    attempt: ClusterFitAttempt,
) -> dict[str, object]:
    return {
        "cluster_count": attempt.cluster_count,
        "config_identity": attempt.config_identity,
        "iterations_used": attempt.iterations_used,
        "prototype_identities": attempt.prototype_identities,
        "status": attempt.status,
        "training_feature_set_identity": (
            attempt.training_feature_set_identity
        ),
        "training_partition_identity": attempt.training_partition_identity,
    }


def _model_payload(model: GeneratedClusterModel) -> dict[str, object]:
    return {
        "cluster_count": model.cluster_count,
        "config_identity": model.config_identity,
        "engine_version": model.engine_version,
        "feature_identities": model.feature_identities,
        "prototype_identities": tuple(
            item.prototype_identity for item in model.prototypes
        ),
        "training_feature_set_identity": model.training_feature_set_identity,
        "training_partition_identity": model.training_partition_identity,
    }


def _search_manifest_payload(
    manifest: ClusterSearchManifest,
) -> dict[str, object]:
    return {
        "attempt_identities": manifest.attempt_identities,
        "automatic_selection": manifest.automatic_selection,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "feature_identities": manifest.feature_identities,
        "model_identities": manifest.model_identities,
        "multiple_testing_status": manifest.multiple_testing_status,
        "out_of_sample_used_in_fit": manifest.out_of_sample_used_in_fit,
        "training_feature_set_identity": (
            manifest.training_feature_set_identity
        ),
        "training_partition_identity": manifest.training_partition_identity,
        "untouched_forward_used": manifest.untouched_forward_used,
    }


def _bucket_payload(
    bucket: ClusterEvaluationBucket,
) -> dict[str, object]:
    return {
        "average_net_r": bucket.average_net_r,
        "cluster_index": bucket.cluster_index,
        "explicit_cost_r_total": bucket.explicit_cost_r_total,
        "gross_r_total": bucket.gross_r_total,
        "max_drawdown_r": bucket.max_drawdown_r,
        "median_net_r": bucket.median_net_r,
        "net_r_total": bucket.net_r_total,
        "observation_count": bucket.observation_count,
        "observation_identities": bucket.observation_identities,
    }


def _evaluation_payload(
    evaluation: ClusterEvaluation,
) -> dict[str, object]:
    return {
        "buckets": tuple(
            item.bucket_identity for item in evaluation.buckets
        ),
        "engine_version": evaluation.engine_version,
        "model_identity": evaluation.model_identity,
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
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty trimmed token")
    if any(character.isspace() for character in value):
        raise ValueError(f"{label} cannot contain whitespace")
