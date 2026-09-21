from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import combinations, product
from statistics import median

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.clustering_regime import ClusterResearchObservation
from research.alpha_factory.foundation import PartitionRole, ResearchPartition
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

EVOLUTION_ENGINE_VERSION = "alpha-factory-evolutionary-search-v1/1"
EVOLUTION_SCHEMA_VERSION = "alpha-factory-evolutionary-schema-v1/1"
EVOLUTION_OPERATOR_VERSION = "deterministic-pair-crossover-mutation-v1/1"
MAX_EVOLUTION_FEATURES = 6
MAX_VALUES_PER_FEATURE = 8
MIN_POPULATION_SIZE = 4
MAX_POPULATION_SIZE = 8
MAX_GENERATIONS = 4
LCG_MODULUS = 2**31
LCG_MULTIPLIER = 1103515245
LCG_INCREMENT = 12345


class EvolutionEvaluationSemantic(StrEnum):
    DESCRIPTIVE_NET_R_NOT_PROBABILITY = "descriptive_net_r_not_probability"


class MultipleTestingControlStatus(StrEnum):
    BOUNDED_EVOLUTION_NO_AUTOMATIC_WINNER = (
        "bounded_evolution_no_automatic_winner"
    )


@dataclass(frozen=True, slots=True)
class EvolutionPredicate:
    predicate_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    expected_value: str

    def __post_init__(self) -> None:
        _require_sha256(self.predicate_identity, "evolution predicate identity")
        _require_sha256(self.feature_identity, "evolution feature identity")
        _require_token(self.feature_id, "evolution feature id")
        _require_token(self.feature_version, "evolution feature version")
        _require_token(self.expected_value, "evolution expected value")
        if self.predicate_identity != canonical_sha256(
            _predicate_payload(self)
        ):
            raise ValueError("evolution predicate identity mismatch")


@dataclass(frozen=True, slots=True)
class EvolutionGenome:
    genome_identity: str
    operator_version: str
    predicates: tuple[EvolutionPredicate, EvolutionPredicate]

    def __post_init__(self) -> None:
        _require_sha256(self.genome_identity, "evolution genome identity")
        if self.operator_version != EVOLUTION_OPERATOR_VERSION:
            raise ValueError("unsupported evolution operator version")
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
            raise ValueError("evolution predicates must be canonical")
        if self.predicates[0].feature_id == self.predicates[1].feature_id:
            raise ValueError("evolution genome requires distinct features")
        if self.genome_identity != canonical_sha256(_genome_payload(self)):
            raise ValueError("evolution genome identity mismatch")


@dataclass(frozen=True, slots=True)
class EvolutionSearchConfig:
    population_size: int = 4
    generations: int = 3
    min_train_support: int = 2
    seed: int = 7

    def __post_init__(self) -> None:
        if not MIN_POPULATION_SIZE <= self.population_size <= MAX_POPULATION_SIZE:
            raise ValueError("evolution population_size must be between 4 and 8")
        if not 1 <= self.generations <= MAX_GENERATIONS:
            raise ValueError("evolution generations must be between 1 and 4")
        if self.min_train_support <= 0:
            raise ValueError("evolution min_train_support must be positive")
        if not 0 <= self.seed < LCG_MODULUS:
            raise ValueError("evolution seed is outside deterministic range")

    @property
    def config_identity(self) -> str:
        return canonical_sha256(_config_payload(self))


DEFAULT_EVOLUTION_SEARCH_CONFIG = EvolutionSearchConfig()


@dataclass(frozen=True, slots=True)
class EvolutionTrainingMetric:
    metric_identity: str
    genome_identity: str
    training_partition_identity: str
    support_count: int
    support_snapshot_identities: tuple[str, ...]
    gross_r_total: Decimal
    explicit_cost_r_total: Decimal
    net_r_total: Decimal
    average_net_r: Decimal
    median_net_r: Decimal
    max_drawdown_r: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.metric_identity, "evolution training metric identity")
        _require_sha256(self.genome_identity, "evolution genome identity")
        _require_sha256(
            self.training_partition_identity,
            "evolution training partition identity",
        )
        if self.support_count <= 0:
            raise ValueError("evolution training support must be positive")
        if self.support_count != len(self.support_snapshot_identities):
            raise ValueError(
                "evolution support count does not match snapshot identities"
            )
        if tuple(sorted(set(self.support_snapshot_identities))) != (
            self.support_snapshot_identities
        ):
            raise ValueError(
                "evolution support snapshots must be sorted and unique"
            )
        for identity in self.support_snapshot_identities:
            _require_sha256(identity, "evolution support snapshot identity")
        if self.explicit_cost_r_total < 0:
            raise ValueError("evolution training costs must be non-negative")
        if self.net_r_total != (
            self.gross_r_total - self.explicit_cost_r_total
        ):
            raise ValueError("evolution training net R mismatch")
        if self.average_net_r != self.net_r_total / Decimal(self.support_count):
            raise ValueError("evolution training average R mismatch")
        if self.max_drawdown_r < 0:
            raise ValueError("evolution training drawdown must be non-negative")
        if self.metric_identity != canonical_sha256(
            _training_metric_payload(self)
        ):
            raise ValueError("evolution training metric identity mismatch")


@dataclass(frozen=True, slots=True)
class EvolutionGeneration:
    generation_identity: str
    generation_index: int
    genome_identities: tuple[str, ...]
    training_metric_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.generation_identity,
            "evolution generation identity",
        )
        if self.generation_index < 0:
            raise ValueError("evolution generation index must be non-negative")
        if not self.genome_identities:
            raise ValueError("evolution generation requires genomes")
        if len(self.genome_identities) != len(self.training_metric_identities):
            raise ValueError("evolution generation genome/metric count mismatch")
        if len(set(self.genome_identities)) != len(self.genome_identities):
            raise ValueError("evolution generation genomes must be unique")
        for identity in self.genome_identities:
            _require_sha256(identity, "evolution generation genome identity")
        for identity in self.training_metric_identities:
            _require_sha256(identity, "evolution generation metric identity")
        if self.generation_identity != canonical_sha256(
            _generation_payload(self)
        ):
            raise ValueError("evolution generation identity mismatch")


@dataclass(frozen=True, slots=True)
class EvolutionSearchManifest:
    search_identity: str
    engine_version: str
    operator_version: str
    config_identity: str
    training_partition_identity: str
    feature_identities: tuple[str, ...]
    seed: int
    generation_identities: tuple[str, ...]
    final_genome_identities: tuple[str, ...]
    multiple_testing_status: MultipleTestingControlStatus
    fitness_used_for_reproduction: bool
    automatic_winner_selection: bool
    validation_used_in_search: bool
    out_of_sample_used_in_search: bool
    untouched_forward_used: bool

    def __post_init__(self) -> None:
        _require_sha256(self.search_identity, "evolution search identity")
        _require_sha256(self.config_identity, "evolution config identity")
        _require_sha256(
            self.training_partition_identity,
            "evolution training partition identity",
        )
        if self.engine_version != EVOLUTION_ENGINE_VERSION:
            raise ValueError("unsupported evolution engine version")
        if self.operator_version != EVOLUTION_OPERATOR_VERSION:
            raise ValueError("unsupported evolution operator version")
        if not 0 <= self.seed < LCG_MODULUS:
            raise ValueError("evolution manifest seed is invalid")
        for identity in self.feature_identities:
            _require_sha256(identity, "evolution feature identity")
        for identity in self.generation_identities:
            _require_sha256(identity, "evolution generation identity")
        for identity in self.final_genome_identities:
            _require_sha256(identity, "evolution final genome identity")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError(
                "evolution feature identities must be sorted and unique"
            )
        if len(set(self.final_genome_identities)) != len(
            self.final_genome_identities
        ):
            raise ValueError("evolution final genomes must be unique")
        if self.multiple_testing_status is not (
            MultipleTestingControlStatus.BOUNDED_EVOLUTION_NO_AUTOMATIC_WINNER
        ):
            raise ValueError("unsupported evolution multiple-testing control")
        if self.fitness_used_for_reproduction:
            raise ValueError(
                "evolution v1 cannot use backtest fitness for reproduction"
            )
        if self.automatic_winner_selection:
            raise ValueError("evolution v1 cannot automatically select a winner")
        if self.validation_used_in_search:
            raise ValueError("evolution search cannot use validation data")
        if self.out_of_sample_used_in_search:
            raise ValueError("evolution search cannot use OOS data")
        if self.untouched_forward_used:
            raise ValueError("evolution v1 cannot use untouched-forward data")
        if self.search_identity != canonical_sha256(
            _search_manifest_payload(self)
        ):
            raise ValueError("evolution search identity mismatch")


@dataclass(frozen=True, slots=True)
class EvolutionEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    genome_identity: str
    partition_identity: str
    partition_role: PartitionRole
    semantic: EvolutionEvaluationSemantic
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
        _require_sha256(self.evaluation_identity, "evolution evaluation identity")
        _require_sha256(self.genome_identity, "evolution genome identity")
        _require_sha256(self.partition_identity, "evolution partition identity")
        if self.schema_version != EVOLUTION_SCHEMA_VERSION:
            raise ValueError("unsupported evolution evaluation schema")
        if self.engine_version != EVOLUTION_ENGINE_VERSION:
            raise ValueError("unsupported evolution evaluation engine")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "evolution evaluation is limited to validation or out-of-sample"
            )
        if self.semantic is not (
            EvolutionEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
        ):
            raise ValueError("unsupported evolution evaluation semantic")
        if self.observation_count <= 0:
            raise ValueError("evolution evaluation requires observations")
        if not 0 <= self.matched_count <= self.observation_count:
            raise ValueError("evolution matched_count is invalid")
        if self.matched_count != len(self.matched_observation_identities):
            raise ValueError("evolution matched_count does not match identities")
        if tuple(sorted(set(self.matched_observation_identities))) != (
            self.matched_observation_identities
        ):
            raise ValueError(
                "evolution matched identities must be sorted and unique"
            )
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
                raise ValueError(
                    "evolution no-match evaluation cannot carry metrics"
                )
        else:
            if any(value is None for value in metrics):
                raise ValueError(
                    "evolution matched evaluation requires all metrics"
                )
            if (
                self.explicit_cost_r_total is not None
                and self.explicit_cost_r_total < 0
            ):
                raise ValueError("evolution evaluation costs must be non-negative")
            if self.max_drawdown_r is not None and self.max_drawdown_r < 0:
                raise ValueError("evolution drawdown must be non-negative")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("evolution evaluation identity mismatch")


def run_evolutionary_search(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    *,
    config: EvolutionSearchConfig = DEFAULT_EVOLUTION_SEARCH_CONFIG,
) -> tuple[
    tuple[EvolutionGenome, ...],
    tuple[EvolutionGeneration, ...],
    tuple[EvolutionTrainingMetric, ...],
    EvolutionSearchManifest,
]:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("evolution search requires the train partition")

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_feature_specs(ordered_features)
    ordered_observations = _validate_observation_partition(
        training_partition,
        observations,
        ordered_features,
    )

    supported_catalog = _supported_genome_catalog(
        ordered_features,
        ordered_observations,
        config.min_train_support,
    )
    if len(supported_catalog) < config.population_size:
        raise ValueError(
            "evolution search has insufficient supported genomes for population"
        )

    population = _initial_population(
        supported_catalog,
        config.population_size,
        config.seed,
    )
    generations: list[EvolutionGeneration] = []
    all_metrics: list[EvolutionTrainingMetric] = []
    state = config.seed

    for generation_index in range(config.generations):
        metrics = tuple(
            _training_metric(
                genome,
                training_partition,
                ordered_observations,
            )
            for genome in population
        )
        all_metrics.extend(metrics)
        generation_payload = {
            "generation_index": generation_index,
            "genome_identities": tuple(
                item.genome_identity for item in population
            ),
            "training_metric_identities": tuple(
                item.metric_identity for item in metrics
            ),
        }
        generations.append(
            EvolutionGeneration(
                generation_identity=canonical_sha256(generation_payload),
                generation_index=generation_index,
                genome_identities=tuple(
                    item.genome_identity for item in population
                ),
                training_metric_identities=tuple(
                    item.metric_identity for item in metrics
                ),
            )
        )
        if generation_index + 1 < config.generations:
            population, state = _next_population(
                population,
                supported_catalog,
                state,
                config.population_size,
            )

    feature_identities = tuple(
        sorted(item.feature_identity for item in ordered_features)
    )
    generation_ids = tuple(item.generation_identity for item in generations)
    final_ids = tuple(item.genome_identity for item in population)
    manifest_payload = {
        "automatic_winner_selection": False,
        "config_identity": config.config_identity,
        "engine_version": EVOLUTION_ENGINE_VERSION,
        "feature_identities": feature_identities,
        "final_genome_identities": final_ids,
        "fitness_used_for_reproduction": False,
        "generation_identities": generation_ids,
        "multiple_testing_status": (
            MultipleTestingControlStatus.BOUNDED_EVOLUTION_NO_AUTOMATIC_WINNER
        ),
        "operator_version": EVOLUTION_OPERATOR_VERSION,
        "out_of_sample_used_in_search": False,
        "seed": config.seed,
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
        "validation_used_in_search": False,
    }
    manifest = EvolutionSearchManifest(
        search_identity=canonical_sha256(manifest_payload),
        engine_version=EVOLUTION_ENGINE_VERSION,
        operator_version=EVOLUTION_OPERATOR_VERSION,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        feature_identities=feature_identities,
        seed=config.seed,
        generation_identities=generation_ids,
        final_genome_identities=final_ids,
        multiple_testing_status=(
            MultipleTestingControlStatus.BOUNDED_EVOLUTION_NO_AUTOMATIC_WINNER
        ),
        fitness_used_for_reproduction=False,
        automatic_winner_selection=False,
        validation_used_in_search=False,
        out_of_sample_used_in_search=False,
        untouched_forward_used=False,
    )
    return population, tuple(generations), tuple(all_metrics), manifest


def evaluate_evolution_genome(
    genome: EvolutionGenome,
    partition: ResearchPartition,
    observations: Sequence[ClusterResearchObservation],
    features: Sequence[SymbolicFeatureSpec],
) -> EvolutionEvaluation:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "evolution evaluation is limited to validation or out-of-sample"
        )

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_genome_features(genome, ordered_features)
    _validate_feature_specs(ordered_features)
    ordered_observations = _validate_observation_partition(
        partition,
        observations,
        ordered_features,
    )
    matches = tuple(
        item for item in ordered_observations if _matches(genome, item)
    )
    matched_ids = tuple(
        sorted(item.observation_identity for item in matches)
    )
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
        "engine_version": EVOLUTION_ENGINE_VERSION,
        "explicit_cost_r_total": cost_total,
        "genome_identity": genome.genome_identity,
        "gross_r_total": gross_total,
        "matched_count": len(matches),
        "matched_observation_identities": matched_ids,
        "max_drawdown_r": max_drawdown,
        "median_net_r": median_net,
        "net_r_total": net_total,
        "observation_count": len(ordered_observations),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "schema_version": EVOLUTION_SCHEMA_VERSION,
        "semantic": EvolutionEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY,
    }
    return EvolutionEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=EVOLUTION_SCHEMA_VERSION,
        engine_version=EVOLUTION_ENGINE_VERSION,
        genome_identity=genome.genome_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=EvolutionEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY,
        observation_count=len(ordered_observations),
        matched_count=len(matches),
        matched_observation_identities=matched_ids,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
        median_net_r=median_net,
        max_drawdown_r=max_drawdown,
    )


def _supported_genome_catalog(
    features: tuple[SymbolicFeatureSpec, ...],
    observations: tuple[ClusterResearchObservation, ...],
    min_support: int,
) -> tuple[EvolutionGenome, ...]:
    genomes: list[EvolutionGenome] = []
    for first, second in combinations(features, 2):
        for first_value, second_value in product(
            first.allowed_values,
            second.allowed_values,
        ):
            genome = _build_genome(
                (
                    _build_predicate(first, first_value),
                    _build_predicate(second, second_value),
                )
            )
            support = sum(_matches(genome, item) for item in observations)
            if support >= min_support:
                genomes.append(genome)
    return tuple(sorted(genomes, key=lambda item: item.genome_identity))


def _initial_population(
    catalog: tuple[EvolutionGenome, ...],
    population_size: int,
    seed: int,
) -> tuple[EvolutionGenome, ...]:
    start = seed % len(catalog)
    rotated = catalog[start:] + catalog[:start]
    return rotated[:population_size]


def _next_population(
    population: tuple[EvolutionGenome, ...],
    catalog: tuple[EvolutionGenome, ...],
    state: int,
    population_size: int,
) -> tuple[tuple[EvolutionGenome, ...], int]:
    by_identity = {item.genome_identity: item for item in catalog}
    catalog_index = {
        item.genome_identity: index for index, item in enumerate(catalog)
    }
    next_items: list[EvolutionGenome] = []
    used: set[str] = set()

    for index, current in enumerate(population):
        partner = population[(index + 1) % len(population)]
        crossed = _crossover(current, partner)
        if crossed is not None and crossed.genome_identity in by_identity:
            candidate = by_identity[crossed.genome_identity]
        else:
            candidate = current

        state = _lcg_next(state)
        base_index = catalog_index[candidate.genome_identity]
        step = 1 + (state % len(catalog))
        mutated = catalog[(base_index + step) % len(catalog)]
        candidate = mutated

        if candidate.genome_identity in used:
            candidate = _first_unused_catalog(catalog, used, base_index)
        used.add(candidate.genome_identity)
        next_items.append(candidate)

    if len(next_items) != population_size:
        raise ValueError("evolution next population size mismatch")
    return tuple(next_items), state


def _crossover(
    first: EvolutionGenome,
    second: EvolutionGenome,
) -> EvolutionGenome | None:
    predicates = (first.predicates[0], second.predicates[1])
    if predicates[0].feature_id == predicates[1].feature_id:
        return None
    return _build_genome(predicates)


def _first_unused_catalog(
    catalog: tuple[EvolutionGenome, ...],
    used: set[str],
    start: int,
) -> EvolutionGenome:
    for offset in range(1, len(catalog) + 1):
        candidate = catalog[(start + offset) % len(catalog)]
        if candidate.genome_identity not in used:
            return candidate
    raise ValueError("evolution cannot build a unique bounded population")


def _training_metric(
    genome: EvolutionGenome,
    training_partition: ResearchPartition,
    observations: tuple[ClusterResearchObservation, ...],
) -> EvolutionTrainingMetric:
    matches = tuple(item for item in observations if _matches(genome, item))
    if not matches:
        raise ValueError("supported evolution genome lost all TRAIN support")
    ids = tuple(sorted(item.feature_snapshot_identity for item in matches))
    gross_values = tuple(item.gross_outcome_r for item in matches)
    cost_values = tuple(item.explicit_cost_r for item in matches)
    net_values = tuple(item.net_outcome_r for item in matches)
    gross_total = sum(gross_values, start=Decimal(0))
    cost_total = sum(cost_values, start=Decimal(0))
    net_total = sum(net_values, start=Decimal(0))
    average_net = net_total / Decimal(len(net_values))
    median_net = median(net_values)
    max_drawdown = _max_drawdown(net_values)
    payload = {
        "average_net_r": average_net,
        "explicit_cost_r_total": cost_total,
        "genome_identity": genome.genome_identity,
        "gross_r_total": gross_total,
        "max_drawdown_r": max_drawdown,
        "median_net_r": median_net,
        "net_r_total": net_total,
        "support_count": len(matches),
        "support_snapshot_identities": ids,
        "training_partition_identity": training_partition.partition_identity,
    }
    return EvolutionTrainingMetric(
        metric_identity=canonical_sha256(payload),
        genome_identity=genome.genome_identity,
        training_partition_identity=training_partition.partition_identity,
        support_count=len(matches),
        support_snapshot_identities=ids,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
        median_net_r=median_net,
        max_drawdown_r=max_drawdown,
    )


def _build_genome(
    predicates: tuple[EvolutionPredicate, EvolutionPredicate],
) -> EvolutionGenome:
    ordered_items = sorted(
        predicates,
        key=lambda item: (
            item.feature_id,
            item.feature_version,
            item.expected_value,
        ),
    )
    ordered = (ordered_items[0], ordered_items[1])
    payload = {
        "operator_version": EVOLUTION_OPERATOR_VERSION,
        "predicate_identities": tuple(
            item.predicate_identity for item in ordered
        ),
    }
    return EvolutionGenome(
        genome_identity=canonical_sha256(payload),
        operator_version=EVOLUTION_OPERATOR_VERSION,
        predicates=ordered,
    )


def _build_predicate(
    feature: SymbolicFeatureSpec,
    expected_value: str,
) -> EvolutionPredicate:
    if expected_value not in feature.allowed_values:
        raise ValueError("evolution value is outside feature contract")
    payload = {
        "expected_value": expected_value,
        "feature_id": feature.feature_id,
        "feature_identity": feature.feature_identity,
        "feature_version": feature.feature_version,
    }
    return EvolutionPredicate(
        predicate_identity=canonical_sha256(payload),
        feature_identity=feature.feature_identity,
        feature_id=feature.feature_id,
        feature_version=feature.feature_version,
        expected_value=expected_value,
    )


def _validate_feature_specs(
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    if not 2 <= len(features) <= MAX_EVOLUTION_FEATURES:
        raise ValueError("evolution v1 requires 2..6 feature specifications")
    ids = tuple(item.feature_id for item in features)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("evolution feature ids must be sorted and unique")
    identities = tuple(item.feature_identity for item in features)
    if len(set(identities)) != len(identities):
        raise ValueError("evolution feature identities must be unique")
    for item in features:
        if len(item.allowed_values) > MAX_VALUES_PER_FEATURE:
            raise ValueError(
                "evolution v1 supports at most 8 values per feature"
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
        raise ValueError("evolution research requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError(
            "evolution observations must cover the partition exactly"
        )

    feature_by_id = {item.feature_id: item for item in features}
    expected_feature_ids = tuple(sorted(feature_by_id))
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    observed_snapshots: set[str] = set()

    for item in ordered:
        if item.partition_identity != partition.partition_identity:
            raise ValueError("evolution observation belongs to another partition")
        if not partition.start_ms <= item.decision_as_of_ms < partition.end_ms:
            raise ValueError("evolution decision is outside partition")
        if item.source_evidence_identity not in partition_sources:
            raise ValueError("evolution source evidence is outside partition")
        if item.source_evidence_identity in observed_sources:
            raise ValueError("duplicate evolution source evidence")
        if item.feature_snapshot_identity in observed_snapshots:
            raise ValueError("duplicate evolution feature snapshot")
        observed_sources.add(item.source_evidence_identity)
        observed_snapshots.add(item.feature_snapshot_identity)

        reading_ids = tuple(
            reading.feature_id for reading in item.feature_readings
        )
        if reading_ids != expected_feature_ids:
            raise ValueError(
                "evolution observation feature set does not match contract"
            )
        for reading in item.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("evolution reading feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("evolution reading feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError(
                    "evolution reading value is outside feature contract"
                )

    if observed_sources != partition_sources:
        raise ValueError(
            "evolution observations do not cover exact partition evidence set"
        )
    return ordered


def _validate_genome_features(
    genome: EvolutionGenome,
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    feature_by_id = {item.feature_id: item for item in features}
    for predicate in genome.predicates:
        feature = feature_by_id.get(predicate.feature_id)
        if feature is None:
            raise ValueError("evolution genome references missing feature")
        if predicate.feature_identity != feature.feature_identity:
            raise ValueError("evolution genome feature identity mismatch")
        if predicate.feature_version != feature.feature_version:
            raise ValueError("evolution genome feature version mismatch")
        if predicate.expected_value not in feature.allowed_values:
            raise ValueError("evolution genome value is outside feature contract")


def _matches(
    genome: EvolutionGenome,
    observation: ClusterResearchObservation,
) -> bool:
    values = {
        item.feature_id: item.value for item in observation.feature_readings
    }
    for predicate in genome.predicates:
        if predicate.feature_id not in values:
            raise ValueError(
                f"evolution observation missing feature: {predicate.feature_id}"
            )
        if values[predicate.feature_id] != predicate.expected_value:
            return False
    return True


def _lcg_next(state: int) -> int:
    return (LCG_MULTIPLIER * state + LCG_INCREMENT) % LCG_MODULUS


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
    predicate: EvolutionPredicate,
) -> dict[str, object]:
    return {
        "expected_value": predicate.expected_value,
        "feature_id": predicate.feature_id,
        "feature_identity": predicate.feature_identity,
        "feature_version": predicate.feature_version,
    }


def _genome_payload(genome: EvolutionGenome) -> dict[str, object]:
    return {
        "operator_version": genome.operator_version,
        "predicate_identities": tuple(
            item.predicate_identity for item in genome.predicates
        ),
    }


def _config_payload(config: EvolutionSearchConfig) -> dict[str, object]:
    return {
        "generations": config.generations,
        "min_train_support": config.min_train_support,
        "operator_version": EVOLUTION_OPERATOR_VERSION,
        "population_size": config.population_size,
        "seed": config.seed,
    }


def _training_metric_payload(
    metric: EvolutionTrainingMetric,
) -> dict[str, object]:
    return {
        "average_net_r": metric.average_net_r,
        "explicit_cost_r_total": metric.explicit_cost_r_total,
        "genome_identity": metric.genome_identity,
        "gross_r_total": metric.gross_r_total,
        "max_drawdown_r": metric.max_drawdown_r,
        "median_net_r": metric.median_net_r,
        "net_r_total": metric.net_r_total,
        "support_count": metric.support_count,
        "support_snapshot_identities": metric.support_snapshot_identities,
        "training_partition_identity": metric.training_partition_identity,
    }


def _generation_payload(
    generation: EvolutionGeneration,
) -> dict[str, object]:
    return {
        "generation_index": generation.generation_index,
        "genome_identities": generation.genome_identities,
        "training_metric_identities": generation.training_metric_identities,
    }


def _search_manifest_payload(
    manifest: EvolutionSearchManifest,
) -> dict[str, object]:
    return {
        "automatic_winner_selection": manifest.automatic_winner_selection,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "feature_identities": manifest.feature_identities,
        "final_genome_identities": manifest.final_genome_identities,
        "fitness_used_for_reproduction": manifest.fitness_used_for_reproduction,
        "generation_identities": manifest.generation_identities,
        "multiple_testing_status": manifest.multiple_testing_status,
        "operator_version": manifest.operator_version,
        "out_of_sample_used_in_search": manifest.out_of_sample_used_in_search,
        "seed": manifest.seed,
        "training_partition_identity": manifest.training_partition_identity,
        "untouched_forward_used": manifest.untouched_forward_used,
        "validation_used_in_search": manifest.validation_used_in_search,
    }


def _evaluation_payload(
    evaluation: EvolutionEvaluation,
) -> dict[str, object]:
    return {
        "average_net_r": evaluation.average_net_r,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "genome_identity": evaluation.genome_identity,
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
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty trimmed token")
    if any(character.isspace() for character in value):
        raise ValueError(f"{label} cannot contain whitespace")
