from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import combinations, product
from statistics import median

from crypto_signal.ledger.serialization import canonical_sha256
from research.alpha_factory.foundation import (
    ChallengerDefinition,
    PartitionRole,
    ResearchPartition,
    build_challenger_definition,
)
from research.alpha_factory.symbolic_rules import SymbolicFeatureSpec

TREE_MODEL_ENGINE_VERSION = "alpha-factory-tree-model-v1/1"
TREE_EVALUATION_SCHEMA_VERSION = "alpha-factory-tree-evaluation-v1/1"
MAX_TREE_FEATURES = 4
MAX_VALUES_PER_FEATURE = 4
MAX_TREE_DEPTH = 2
MAX_TREE_STRUCTURES = 128


class TreeLeafAction(StrEnum):
    TAKE = "take"
    ABSTAIN = "abstain"


class TreeEvaluationSemantic(StrEnum):
    DESCRIPTIVE_NET_R_NOT_PROBABILITY = "descriptive_net_r_not_probability"


class MultipleTestingControlStatus(StrEnum):
    BOUNDED_HYPOTHESIS_SET_NO_AUTOMATIC_SELECTION = (
        "bounded_hypothesis_set_no_automatic_selection"
    )


@dataclass(frozen=True, slots=True)
class TreeFeatureReading:
    reading_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    value: str
    available_at_ms: int

    def __post_init__(self) -> None:
        _require_sha256(self.reading_identity, "tree feature reading identity")
        _require_sha256(self.feature_identity, "tree feature identity")
        _require_token(self.feature_id, "tree feature id")
        _require_token(self.feature_version, "tree feature version")
        _require_token(self.value, "tree feature value")
        if self.available_at_ms < 0:
            raise ValueError("tree feature availability must be non-negative")
        if self.reading_identity != canonical_sha256(_reading_payload(self)):
            raise ValueError("tree feature reading identity mismatch")


@dataclass(frozen=True, slots=True)
class TreeResearchObservation:
    observation_identity: str
    schema_version: str
    partition_identity: str
    source_evidence_identity: str
    decision_as_of_ms: int
    outcome_available_at_ms: int
    feature_readings: tuple[TreeFeatureReading, ...]
    gross_outcome_r: Decimal
    explicit_cost_r: Decimal
    net_outcome_r: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "tree observation identity")
        _require_sha256(self.partition_identity, "tree partition identity")
        _require_sha256(
            self.source_evidence_identity,
            "tree source evidence identity",
        )
        if self.schema_version != TREE_EVALUATION_SCHEMA_VERSION:
            raise ValueError("unsupported tree observation schema")
        if self.decision_as_of_ms < 0 or self.outcome_available_at_ms < 0:
            raise ValueError("tree observation times must be non-negative")
        if self.outcome_available_at_ms < self.decision_as_of_ms:
            raise ValueError("tree outcome cannot predate decision as-of")
        if not self.feature_readings:
            raise ValueError("tree observation requires feature readings")

        ids = tuple(item.feature_id for item in self.feature_readings)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("tree feature readings must be sorted and unique")
        for item in self.feature_readings:
            if item.available_at_ms > self.decision_as_of_ms:
                raise ValueError(
                    "tree feature evidence is unavailable at decision as-of"
                )
        if self.explicit_cost_r < Decimal(0):
            raise ValueError("explicit tree research cost R must be non-negative")
        if self.net_outcome_r != self.gross_outcome_r - self.explicit_cost_r:
            raise ValueError(
                "tree net outcome R must equal gross R minus explicit cost R"
            )
        if self.observation_identity != canonical_sha256(
            _observation_payload(self)
        ):
            raise ValueError("tree observation identity mismatch")


@dataclass(frozen=True, slots=True)
class TreeSplit:
    split_identity: str
    feature_identity: str
    feature_id: str
    feature_version: str
    expected_value: str

    def __post_init__(self) -> None:
        _require_sha256(self.split_identity, "tree split identity")
        _require_sha256(self.feature_identity, "tree split feature identity")
        _require_token(self.feature_id, "tree split feature id")
        _require_token(self.feature_version, "tree split feature version")
        _require_token(self.expected_value, "tree split expected value")
        if self.split_identity != canonical_sha256(_split_payload(self)):
            raise ValueError("tree split identity mismatch")


@dataclass(frozen=True, slots=True)
class TreeSearchConfig:
    max_depth: int = MAX_TREE_DEPTH
    max_structures: int = MAX_TREE_STRUCTURES
    min_leaf_count: int = 2
    take_threshold_r: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not 1 <= self.max_depth <= MAX_TREE_DEPTH:
            raise ValueError("tree max_depth must be 1 or 2")
        if not 1 <= self.max_structures <= MAX_TREE_STRUCTURES:
            raise ValueError("tree max_structures must be between 1 and 128")
        if self.min_leaf_count <= 0:
            raise ValueError("tree min_leaf_count must be positive")

    @property
    def config_identity(self) -> str:
        return canonical_sha256(_config_payload(self))


DEFAULT_TREE_SEARCH_CONFIG = TreeSearchConfig()


@dataclass(frozen=True, slots=True)
class GeneratedTreeChallenger:
    generated_identity: str
    engine_version: str
    config_identity: str
    training_partition_identity: str
    definition: ChallengerDefinition
    splits: tuple[TreeSplit, ...]
    leaf_actions: tuple[TreeLeafAction, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.generated_identity, "generated tree identity")
        _require_sha256(self.config_identity, "tree config identity")
        _require_sha256(
            self.training_partition_identity,
            "tree training partition identity",
        )
        if self.engine_version != TREE_MODEL_ENGINE_VERSION:
            raise ValueError("unsupported tree engine version")
        if not 1 <= len(self.splits) <= MAX_TREE_DEPTH:
            raise ValueError("tree challenger requires depth 1..2")
        if len(self.leaf_actions) != 2 ** len(self.splits):
            raise ValueError("tree leaf action count does not match depth")

        ordered_splits = tuple(
            sorted(
                self.splits,
                key=lambda item: (
                    item.feature_id,
                    item.feature_version,
                    item.expected_value,
                ),
            )
        )
        if ordered_splits != self.splits:
            raise ValueError("tree splits must be canonically ordered")
        feature_ids = tuple(item.feature_id for item in self.splits)
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("tree cannot split the same feature twice")
        if self.definition.feature_ids != tuple(sorted(feature_ids)):
            raise ValueError("tree definition feature ids do not match splits")
        if self.definition.rule_definition != _tree_rule_text(
            self.splits,
            self.leaf_actions,
        ):
            raise ValueError("tree definition rule text mismatch")
        if all(
            action is TreeLeafAction.TAKE
            for action in self.leaf_actions
        ) or all(
            action is TreeLeafAction.ABSTAIN
            for action in self.leaf_actions
        ):
            raise ValueError("tree challenger must be selective")
        if self.generated_identity != canonical_sha256(
            _generated_tree_payload(self)
        ):
            raise ValueError("generated tree identity mismatch")


@dataclass(frozen=True, slots=True)
class TreeSearchManifest:
    search_identity: str
    engine_version: str
    config_identity: str
    training_partition_identity: str
    feature_identities: tuple[str, ...]
    structures_evaluated: int
    candidate_identities: tuple[str, ...]
    multiple_testing_status: MultipleTestingControlStatus
    automatic_selection: bool
    out_of_sample_used_in_generation: bool
    untouched_forward_used: bool

    def __post_init__(self) -> None:
        _require_sha256(self.search_identity, "tree search identity")
        _require_sha256(self.config_identity, "tree config identity")
        _require_sha256(
            self.training_partition_identity,
            "tree training partition identity",
        )
        for identity in self.feature_identities:
            _require_sha256(identity, "tree search feature identity")
        for identity in self.candidate_identities:
            _require_sha256(identity, "tree candidate identity")
        if self.engine_version != TREE_MODEL_ENGINE_VERSION:
            raise ValueError("unsupported tree search engine")
        if not 1 <= self.structures_evaluated <= MAX_TREE_STRUCTURES:
            raise ValueError("tree structures_evaluated is invalid")
        if tuple(sorted(set(self.feature_identities))) != self.feature_identities:
            raise ValueError(
                "tree search feature identities must be sorted and unique"
            )
        if len(set(self.candidate_identities)) != len(
            self.candidate_identities
        ):
            raise ValueError("tree candidate identities must be unique")
        if self.multiple_testing_status is not (
            MultipleTestingControlStatus
            .BOUNDED_HYPOTHESIS_SET_NO_AUTOMATIC_SELECTION
        ):
            raise ValueError("unsupported tree multiple-testing control")
        if self.automatic_selection:
            raise ValueError("tree v1 cannot automatically select a winner")
        if self.out_of_sample_used_in_generation:
            raise ValueError("tree generation cannot use out-of-sample data")
        if self.untouched_forward_used:
            raise ValueError("tree v1 cannot use untouched-forward data")
        if self.search_identity != canonical_sha256(
            _search_manifest_payload(self)
        ):
            raise ValueError("tree search identity mismatch")


@dataclass(frozen=True, slots=True)
class TreeEvaluation:
    evaluation_identity: str
    schema_version: str
    engine_version: str
    challenger_identity: str
    partition_identity: str
    partition_role: PartitionRole
    semantic: TreeEvaluationSemantic
    observation_count: int
    taken_count: int
    taken_observation_identities: tuple[str, ...]
    gross_r_total: Decimal | None
    explicit_cost_r_total: Decimal | None
    net_r_total: Decimal | None
    average_net_r: Decimal | None
    median_net_r: Decimal | None
    max_drawdown_r: Decimal | None

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_identity, "tree evaluation identity")
        _require_sha256(self.challenger_identity, "tree challenger identity")
        _require_sha256(self.partition_identity, "tree evaluation partition")
        if self.schema_version != TREE_EVALUATION_SCHEMA_VERSION:
            raise ValueError("unsupported tree evaluation schema")
        if self.engine_version != TREE_MODEL_ENGINE_VERSION:
            raise ValueError("unsupported tree evaluation engine")
        if self.partition_role not in {
            PartitionRole.VALIDATION,
            PartitionRole.OUT_OF_SAMPLE,
        }:
            raise ValueError(
                "tree evaluation is limited to validation or out-of-sample"
            )
        if self.semantic is not (
            TreeEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY
        ):
            raise ValueError("unsupported tree evaluation semantic")
        if self.observation_count <= 0:
            raise ValueError("tree evaluation requires observations")
        if not 0 <= self.taken_count <= self.observation_count:
            raise ValueError("tree taken_count is invalid")
        if self.taken_count != len(self.taken_observation_identities):
            raise ValueError("tree taken_count does not match identities")
        if tuple(sorted(set(self.taken_observation_identities))) != (
            self.taken_observation_identities
        ):
            raise ValueError(
                "tree taken observation identities must be sorted and unique"
            )

        metrics = (
            self.gross_r_total,
            self.explicit_cost_r_total,
            self.net_r_total,
            self.average_net_r,
            self.median_net_r,
            self.max_drawdown_r,
        )
        if self.taken_count == 0:
            if any(value is not None for value in metrics):
                raise ValueError(
                    "tree no-take evaluation cannot carry performance metrics"
                )
        else:
            if any(value is None for value in metrics):
                raise ValueError(
                    "tree taken evaluation requires all performance metrics"
                )
            if (
                self.explicit_cost_r_total is not None
                and self.explicit_cost_r_total < 0
            ):
                raise ValueError("tree evaluation cost total must be non-negative")
            if self.max_drawdown_r is not None and self.max_drawdown_r < 0:
                raise ValueError("tree evaluation drawdown must be non-negative")
        if self.evaluation_identity != canonical_sha256(
            _evaluation_payload(self)
        ):
            raise ValueError("tree evaluation identity mismatch")


def build_tree_feature_reading(
    *,
    feature: SymbolicFeatureSpec,
    value: str,
    available_at_ms: int,
) -> TreeFeatureReading:
    if value not in feature.allowed_values:
        raise ValueError("tree reading value is outside feature contract")
    payload = {
        "available_at_ms": available_at_ms,
        "feature_id": feature.feature_id,
        "feature_identity": feature.feature_identity,
        "feature_version": feature.feature_version,
        "value": value,
    }
    return TreeFeatureReading(
        reading_identity=canonical_sha256(payload),
        feature_identity=feature.feature_identity,
        feature_id=feature.feature_id,
        feature_version=feature.feature_version,
        value=value,
        available_at_ms=available_at_ms,
    )


def build_tree_research_observation(
    *,
    partition_identity: str,
    source_evidence_identity: str,
    decision_as_of_ms: int,
    outcome_available_at_ms: int,
    feature_readings: tuple[TreeFeatureReading, ...],
    gross_outcome_r: Decimal,
    explicit_cost_r: Decimal,
) -> TreeResearchObservation:
    ordered_readings = tuple(
        sorted(feature_readings, key=lambda item: item.feature_id)
    )
    net_outcome_r = gross_outcome_r - explicit_cost_r
    payload = {
        "decision_as_of_ms": decision_as_of_ms,
        "explicit_cost_r": explicit_cost_r,
        "feature_reading_identities": tuple(
            item.reading_identity for item in ordered_readings
        ),
        "gross_outcome_r": gross_outcome_r,
        "net_outcome_r": net_outcome_r,
        "outcome_available_at_ms": outcome_available_at_ms,
        "partition_identity": partition_identity,
        "schema_version": TREE_EVALUATION_SCHEMA_VERSION,
        "source_evidence_identity": source_evidence_identity,
    }
    return TreeResearchObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=TREE_EVALUATION_SCHEMA_VERSION,
        partition_identity=partition_identity,
        source_evidence_identity=source_evidence_identity,
        decision_as_of_ms=decision_as_of_ms,
        outcome_available_at_ms=outcome_available_at_ms,
        feature_readings=ordered_readings,
        gross_outcome_r=gross_outcome_r,
        explicit_cost_r=explicit_cost_r,
        net_outcome_r=net_outcome_r,
    )


def generate_tree_challengers(
    features: Sequence[SymbolicFeatureSpec],
    training_partition: ResearchPartition,
    observations: Sequence[TreeResearchObservation],
    *,
    config: TreeSearchConfig = DEFAULT_TREE_SEARCH_CONFIG,
) -> tuple[tuple[GeneratedTreeChallenger, ...], TreeSearchManifest]:
    if training_partition.role is not PartitionRole.TRAIN:
        raise ValueError("tree generation requires the train partition")

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_tree_feature_specs(ordered_features)
    ordered_observations = _validate_observation_partition(
        training_partition,
        observations,
        ordered_features,
    )

    generated: list[GeneratedTreeChallenger] = []
    structures_evaluated = 0
    for splits in _iter_split_structures(ordered_features, config.max_depth):
        if structures_evaluated >= config.max_structures:
            break
        structures_evaluated += 1
        leaf_actions = _derive_leaf_actions(
            splits,
            ordered_observations,
            config,
        )
        if leaf_actions is None:
            continue
        generated.append(
            _build_tree_challenger(
                splits=splits,
                leaf_actions=leaf_actions,
                training_partition=training_partition,
                config=config,
            )
        )

    if structures_evaluated == 0:
        raise ValueError("tree search produced no structures to evaluate")

    candidate_ids = tuple(item.generated_identity for item in generated)
    feature_ids = tuple(
        sorted(item.feature_identity for item in ordered_features)
    )
    manifest_payload = {
        "automatic_selection": False,
        "candidate_identities": candidate_ids,
        "config_identity": config.config_identity,
        "engine_version": TREE_MODEL_ENGINE_VERSION,
        "feature_identities": feature_ids,
        "multiple_testing_status": (
            MultipleTestingControlStatus
            .BOUNDED_HYPOTHESIS_SET_NO_AUTOMATIC_SELECTION
        ),
        "out_of_sample_used_in_generation": False,
        "structures_evaluated": structures_evaluated,
        "training_partition_identity": training_partition.partition_identity,
        "untouched_forward_used": False,
    }
    manifest = TreeSearchManifest(
        search_identity=canonical_sha256(manifest_payload),
        engine_version=TREE_MODEL_ENGINE_VERSION,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        feature_identities=feature_ids,
        structures_evaluated=structures_evaluated,
        candidate_identities=candidate_ids,
        multiple_testing_status=(
            MultipleTestingControlStatus
            .BOUNDED_HYPOTHESIS_SET_NO_AUTOMATIC_SELECTION
        ),
        automatic_selection=False,
        out_of_sample_used_in_generation=False,
        untouched_forward_used=False,
    )
    return tuple(generated), manifest


def evaluate_tree_challenger(
    challenger: GeneratedTreeChallenger,
    partition: ResearchPartition,
    observations: Sequence[TreeResearchObservation],
    features: Sequence[SymbolicFeatureSpec],
) -> TreeEvaluation:
    if partition.role not in {
        PartitionRole.VALIDATION,
        PartitionRole.OUT_OF_SAMPLE,
    }:
        raise ValueError(
            "tree evaluation is limited to validation or out-of-sample"
        )

    ordered_features = tuple(sorted(features, key=lambda item: item.feature_id))
    _validate_tree_feature_specs(ordered_features)
    _validate_challenger_features(challenger, ordered_features)
    ordered_observations = _validate_observation_partition(
        partition,
        observations,
        ordered_features,
    )

    taken = tuple(
        item
        for item in ordered_observations
        if _action_for_observation(challenger, item)
        is TreeLeafAction.TAKE
    )
    taken_ids = tuple(sorted(item.observation_identity for item in taken))
    if taken:
        gross_values = tuple(item.gross_outcome_r for item in taken)
        cost_values = tuple(item.explicit_cost_r for item in taken)
        net_values = tuple(item.net_outcome_r for item in taken)
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
        "challenger_identity": challenger.generated_identity,
        "engine_version": TREE_MODEL_ENGINE_VERSION,
        "explicit_cost_r_total": cost_total,
        "gross_r_total": gross_total,
        "max_drawdown_r": max_drawdown,
        "median_net_r": median_net,
        "net_r_total": net_total,
        "observation_count": len(ordered_observations),
        "partition_identity": partition.partition_identity,
        "partition_role": partition.role,
        "schema_version": TREE_EVALUATION_SCHEMA_VERSION,
        "semantic": TreeEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY,
        "taken_count": len(taken),
        "taken_observation_identities": taken_ids,
    }
    return TreeEvaluation(
        evaluation_identity=canonical_sha256(payload),
        schema_version=TREE_EVALUATION_SCHEMA_VERSION,
        engine_version=TREE_MODEL_ENGINE_VERSION,
        challenger_identity=challenger.generated_identity,
        partition_identity=partition.partition_identity,
        partition_role=partition.role,
        semantic=TreeEvaluationSemantic.DESCRIPTIVE_NET_R_NOT_PROBABILITY,
        observation_count=len(ordered_observations),
        taken_count=len(taken),
        taken_observation_identities=taken_ids,
        gross_r_total=gross_total,
        explicit_cost_r_total=cost_total,
        net_r_total=net_total,
        average_net_r=average_net,
        median_net_r=median_net,
        max_drawdown_r=max_drawdown,
    )


def _validate_tree_feature_specs(
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    if not 1 <= len(features) <= MAX_TREE_FEATURES:
        raise ValueError("tree v1 requires 1..4 feature specifications")
    ids = tuple(item.feature_id for item in features)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("tree feature ids must be sorted and unique")
    identities = tuple(item.feature_identity for item in features)
    if len(set(identities)) != len(identities):
        raise ValueError("tree feature identities must be unique")
    for item in features:
        if len(item.allowed_values) > MAX_VALUES_PER_FEATURE:
            raise ValueError(
                "tree v1 supports at most 4 values per feature"
            )


def _validate_observation_partition(
    partition: ResearchPartition,
    observations: Sequence[TreeResearchObservation],
    features: tuple[SymbolicFeatureSpec, ...],
) -> tuple[TreeResearchObservation, ...]:
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
        raise ValueError("tree research requires partition observations")
    if len(ordered) != len(partition.evidence_identities):
        raise ValueError("tree observations must cover the partition exactly")

    feature_by_id = {item.feature_id: item for item in features}
    expected_feature_ids = tuple(sorted(feature_by_id))
    partition_sources = set(partition.evidence_identities)
    observed_sources: set[str] = set()
    observed_records: set[str] = set()

    for item in ordered:
        if item.partition_identity != partition.partition_identity:
            raise ValueError("tree observation belongs to another partition")
        if not partition.start_ms <= item.decision_as_of_ms < partition.end_ms:
            raise ValueError("tree observation decision is outside partition")
        if item.source_evidence_identity not in partition_sources:
            raise ValueError("tree source evidence is outside partition")
        if item.source_evidence_identity in observed_sources:
            raise ValueError("duplicate tree source evidence")
        if item.observation_identity in observed_records:
            raise ValueError("duplicate tree observation identity")
        observed_sources.add(item.source_evidence_identity)
        observed_records.add(item.observation_identity)

        reading_ids = tuple(
            reading.feature_id for reading in item.feature_readings
        )
        if reading_ids != expected_feature_ids:
            raise ValueError(
                "tree observation feature set does not match feature contract"
            )
        for reading in item.feature_readings:
            feature = feature_by_id[reading.feature_id]
            if reading.feature_identity != feature.feature_identity:
                raise ValueError("tree reading feature identity mismatch")
            if reading.feature_version != feature.feature_version:
                raise ValueError("tree reading feature version mismatch")
            if reading.value not in feature.allowed_values:
                raise ValueError("tree reading value is outside feature contract")

    if observed_sources != partition_sources:
        raise ValueError(
            "tree observations do not cover exact partition evidence set"
        )
    return ordered


def _iter_split_structures(
    features: tuple[SymbolicFeatureSpec, ...],
    max_depth: int,
) -> Sequence[tuple[TreeSplit, ...]]:
    structures: list[tuple[TreeSplit, ...]] = []
    for feature in features:
        for value in feature.allowed_values:
            structures.append((_build_split(feature, value),))

    if max_depth >= 2:
        for first, second in combinations(features, 2):
            for first_value, second_value in product(
                first.allowed_values,
                second.allowed_values,
            ):
                structures.append(
                    (
                        _build_split(first, first_value),
                        _build_split(second, second_value),
                    )
                )
    return tuple(structures)


def _derive_leaf_actions(
    splits: tuple[TreeSplit, ...],
    observations: tuple[TreeResearchObservation, ...],
    config: TreeSearchConfig,
) -> tuple[TreeLeafAction, ...] | None:
    leaf_count = 2 ** len(splits)
    buckets: list[list[TreeResearchObservation]] = [
        [] for _ in range(leaf_count)
    ]
    for item in observations:
        buckets[_leaf_index(splits, item)].append(item)

    actions: list[TreeLeafAction] = []
    for bucket in buckets:
        if len(bucket) < config.min_leaf_count:
            actions.append(TreeLeafAction.ABSTAIN)
            continue
        average_net = sum(
            (item.net_outcome_r for item in bucket),
            start=Decimal(0),
        ) / Decimal(len(bucket))
        actions.append(
            TreeLeafAction.TAKE
            if average_net > config.take_threshold_r
            else TreeLeafAction.ABSTAIN
        )

    result = tuple(actions)
    if all(action is TreeLeafAction.ABSTAIN for action in result):
        return None
    if all(action is TreeLeafAction.TAKE for action in result):
        return None
    return result


def _build_tree_challenger(
    *,
    splits: tuple[TreeSplit, ...],
    leaf_actions: tuple[TreeLeafAction, ...],
    training_partition: ResearchPartition,
    config: TreeSearchConfig,
) -> GeneratedTreeChallenger:
    rule_text = _tree_rule_text(splits, leaf_actions)
    feature_ids = tuple(sorted(item.feature_id for item in splits))
    definition = build_challenger_definition(
        name="bounded shallow categorical tree",
        version=TREE_MODEL_ENGINE_VERSION,
        hypothesis=(
            "train-only shallow categorical partitioning may identify "
            "contexts with positive descriptive net R after explicit costs"
        ),
        rule_definition=rule_text,
        feature_ids=feature_ids,
    )
    payload = {
        "config_identity": config.config_identity,
        "definition_identity": definition.challenger_identity,
        "engine_version": TREE_MODEL_ENGINE_VERSION,
        "leaf_actions": leaf_actions,
        "split_identities": tuple(item.split_identity for item in splits),
        "training_partition_identity": training_partition.partition_identity,
    }
    return GeneratedTreeChallenger(
        generated_identity=canonical_sha256(payload),
        engine_version=TREE_MODEL_ENGINE_VERSION,
        config_identity=config.config_identity,
        training_partition_identity=training_partition.partition_identity,
        definition=definition,
        splits=splits,
        leaf_actions=leaf_actions,
    )


def _build_split(
    feature: SymbolicFeatureSpec,
    expected_value: str,
) -> TreeSplit:
    if expected_value not in feature.allowed_values:
        raise ValueError("tree split value is outside feature contract")
    payload = {
        "expected_value": expected_value,
        "feature_id": feature.feature_id,
        "feature_identity": feature.feature_identity,
        "feature_version": feature.feature_version,
    }
    return TreeSplit(
        split_identity=canonical_sha256(payload),
        feature_identity=feature.feature_identity,
        feature_id=feature.feature_id,
        feature_version=feature.feature_version,
        expected_value=expected_value,
    )


def _validate_challenger_features(
    challenger: GeneratedTreeChallenger,
    features: tuple[SymbolicFeatureSpec, ...],
) -> None:
    feature_by_id = {item.feature_id: item for item in features}
    for split in challenger.splits:
        feature = feature_by_id.get(split.feature_id)
        if feature is None:
            raise ValueError("tree challenger references missing feature")
        if split.feature_identity != feature.feature_identity:
            raise ValueError("tree challenger feature identity mismatch")
        if split.feature_version != feature.feature_version:
            raise ValueError("tree challenger feature version mismatch")
        if split.expected_value not in feature.allowed_values:
            raise ValueError("tree challenger split value is outside feature contract")


def _action_for_observation(
    challenger: GeneratedTreeChallenger,
    observation: TreeResearchObservation,
) -> TreeLeafAction:
    index = _leaf_index(challenger.splits, observation)
    return challenger.leaf_actions[index]


def _leaf_index(
    splits: tuple[TreeSplit, ...],
    observation: TreeResearchObservation,
) -> int:
    readings = {
        item.feature_id: item.value for item in observation.feature_readings
    }
    index = 0
    for split in splits:
        if split.feature_id not in readings:
            raise ValueError("tree observation is missing split feature")
        index = index * 2 + int(
            readings[split.feature_id] == split.expected_value
        )
    return index


def _tree_rule_text(
    splits: tuple[TreeSplit, ...],
    leaf_actions: tuple[TreeLeafAction, ...],
) -> str:
    split_text = ";".join(
        f"{item.feature_id}@{item.feature_version}=={item.expected_value}"
        for item in splits
    )
    action_text = ",".join(action.value for action in leaf_actions)
    return f"tree[{split_text}]=>[{action_text}]"


def _max_drawdown(values: tuple[Decimal, ...]) -> Decimal:
    equity = Decimal(0)
    peak = Decimal(0)
    max_drawdown = Decimal(0)
    for value in values:
        equity += value
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _reading_payload(reading: TreeFeatureReading) -> dict[str, object]:
    return {
        "available_at_ms": reading.available_at_ms,
        "feature_id": reading.feature_id,
        "feature_identity": reading.feature_identity,
        "feature_version": reading.feature_version,
        "value": reading.value,
    }


def _observation_payload(
    observation: TreeResearchObservation,
) -> dict[str, object]:
    return {
        "decision_as_of_ms": observation.decision_as_of_ms,
        "explicit_cost_r": observation.explicit_cost_r,
        "feature_reading_identities": tuple(
            item.reading_identity for item in observation.feature_readings
        ),
        "gross_outcome_r": observation.gross_outcome_r,
        "net_outcome_r": observation.net_outcome_r,
        "outcome_available_at_ms": observation.outcome_available_at_ms,
        "partition_identity": observation.partition_identity,
        "schema_version": observation.schema_version,
        "source_evidence_identity": observation.source_evidence_identity,
    }


def _split_payload(split: TreeSplit) -> dict[str, object]:
    return {
        "expected_value": split.expected_value,
        "feature_id": split.feature_id,
        "feature_identity": split.feature_identity,
        "feature_version": split.feature_version,
    }


def _config_payload(config: TreeSearchConfig) -> dict[str, object]:
    return {
        "max_depth": config.max_depth,
        "max_structures": config.max_structures,
        "min_leaf_count": config.min_leaf_count,
        "take_threshold_r": config.take_threshold_r,
    }


def _generated_tree_payload(
    challenger: GeneratedTreeChallenger,
) -> dict[str, object]:
    return {
        "config_identity": challenger.config_identity,
        "definition_identity": challenger.definition.challenger_identity,
        "engine_version": challenger.engine_version,
        "leaf_actions": challenger.leaf_actions,
        "split_identities": tuple(
            item.split_identity for item in challenger.splits
        ),
        "training_partition_identity": challenger.training_partition_identity,
    }


def _search_manifest_payload(
    manifest: TreeSearchManifest,
) -> dict[str, object]:
    return {
        "automatic_selection": manifest.automatic_selection,
        "candidate_identities": manifest.candidate_identities,
        "config_identity": manifest.config_identity,
        "engine_version": manifest.engine_version,
        "feature_identities": manifest.feature_identities,
        "multiple_testing_status": manifest.multiple_testing_status,
        "out_of_sample_used_in_generation": (
            manifest.out_of_sample_used_in_generation
        ),
        "structures_evaluated": manifest.structures_evaluated,
        "training_partition_identity": manifest.training_partition_identity,
        "untouched_forward_used": manifest.untouched_forward_used,
    }


def _evaluation_payload(evaluation: TreeEvaluation) -> dict[str, object]:
    return {
        "average_net_r": evaluation.average_net_r,
        "challenger_identity": evaluation.challenger_identity,
        "engine_version": evaluation.engine_version,
        "explicit_cost_r_total": evaluation.explicit_cost_r_total,
        "gross_r_total": evaluation.gross_r_total,
        "max_drawdown_r": evaluation.max_drawdown_r,
        "median_net_r": evaluation.median_net_r,
        "net_r_total": evaluation.net_r_total,
        "observation_count": evaluation.observation_count,
        "partition_identity": evaluation.partition_identity,
        "partition_role": evaluation.partition_role,
        "schema_version": evaluation.schema_version,
        "semantic": evaluation.semantic,
        "taken_count": evaluation.taken_count,
        "taken_observation_identities": (
            evaluation.taken_observation_identities
        ),
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
