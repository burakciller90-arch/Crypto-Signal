"""Versioned shadow meta-intelligence policy.

This module combines accepted evidence descriptively while preserving hard
boundaries: no calibrated probability, no production contribution, no automatic
promotion and no deploy/order authority.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256

META_INTELLIGENCE_ENGINE_VERSION = "meta-intelligence-shadow-v1/1"
META_POLICY_SCHEMA_VERSION = "meta-intelligence-weight-policy-v1/1"
META_OBSERVATION_SCHEMA_VERSION = "meta-intelligence-observation-v1/1"
META_RELATION_SCHEMA_VERSION = "meta-intelligence-relation-v1/1"
META_SNAPSHOT_SCHEMA_VERSION = "meta-intelligence-shadow-snapshot-v1/1"
META_SCORE_SEMANTIC = "signed_weighted_balance_not_probability"
PROBABILITY_STATUS = "not_calibrated"
REAL_CAPITAL = 0


class MetaEvidenceState(StrEnum):
    OBSERVED = "observed"
    ABSTAIN = "abstain"
    NO_EVIDENCE = "no_evidence"
    NOT_EVALUABLE = "not_evaluable"


class MetaDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class MetaRelationKind(StrEnum):
    REDUNDANT = "redundant"
    OVERLAPPING = "overlapping"
    COMPLEMENTARY = "complementary"
    CONTRADICTORY = "contradictory"


class MetaResolution(StrEnum):
    BULLISH_LEAN = "bullish_lean"
    BEARISH_LEAN = "bearish_lean"
    BALANCED = "balanced"
    CONTRADICTORY = "contradictory"
    ABSTAIN_ONLY = "abstain_only"
    NO_EVIDENCE = "no_evidence"
    NOT_EVALUABLE = "not_evaluable"
    POLICY_INCOMPLETE = "policy_incomplete"


@dataclass(frozen=True, slots=True)
class MetaWeightRule:
    engine_id: str
    regime: str
    weight: Decimal

    def __post_init__(self) -> None:
        _require_text(self.engine_id, "meta weight engine_id")
        _require_text(self.regime, "meta weight regime")
        if not Decimal(0) <= self.weight <= Decimal(1):
            raise ValueError("meta weight must be inside [0,1]")


@dataclass(frozen=True, slots=True)
class MetaCorrelationGroup:
    group_id: str
    engine_ids: tuple[str, ...]
    max_total_weight: Decimal

    def __post_init__(self) -> None:
        _require_text(self.group_id, "meta correlation group_id")
        if len(self.engine_ids) < 2:
            raise ValueError("meta correlation group requires at least two engines")
        if tuple(sorted(set(self.engine_ids))) != self.engine_ids:
            raise ValueError("meta correlation engine_ids must be sorted and unique")
        for engine_id in self.engine_ids:
            _require_text(engine_id, "meta correlation engine_id")
        if not Decimal(0) < self.max_total_weight <= Decimal(1):
            raise ValueError("meta correlation cap must be inside (0,1]")


@dataclass(frozen=True, slots=True)
class MetaWeightPolicy:
    policy_identity: str
    schema_version: str
    engine_version: str
    policy_version: str
    rules: tuple[MetaWeightRule, ...]
    correlation_groups: tuple[MetaCorrelationGroup, ...]
    max_total_weight: Decimal
    shadow_only: bool = True
    production_contribution: int = 0
    production_authority: bool = False
    automatic_promotion: bool = False
    deploy_authority: bool = False
    probability_status: str = PROBABILITY_STATUS
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "meta policy identity")
        if self.schema_version != META_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported meta policy schema")
        if self.engine_version != META_INTELLIGENCE_ENGINE_VERSION:
            raise ValueError("unsupported meta policy engine")
        _require_text(self.policy_version, "meta policy version")
        if not self.rules:
            raise ValueError("meta policy requires weight rules")
        keys = tuple((item.engine_id, item.regime) for item in self.rules)
        if tuple(sorted(set(keys))) != keys:
            raise ValueError("meta weight rules must be canonical and unique")
        group_ids = tuple(item.group_id for item in self.correlation_groups)
        if tuple(sorted(set(group_ids))) != group_ids:
            raise ValueError("meta correlation groups must be canonical and unique")
        grouped_engines = [
            engine_id
            for group in self.correlation_groups
            for engine_id in group.engine_ids
        ]
        if len(set(grouped_engines)) != len(grouped_engines):
            raise ValueError("an engine cannot belong to multiple correlation groups")
        if not Decimal(0) < self.max_total_weight <= Decimal(1):
            raise ValueError("meta policy global cap must be inside (0,1]")
        if not self.shadow_only:
            raise ValueError("meta policy v1 must remain shadow-only")
        if self.production_contribution != 0:
            raise ValueError("meta policy production contribution must remain 0")
        if (
            self.production_authority
            or self.automatic_promotion
            or self.deploy_authority
        ):
            raise ValueError("meta policy has no production/promotion/deploy authority")
        if self.probability_status != PROBABILITY_STATUS:
            raise ValueError("meta policy probability remains not calibrated")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("meta policy identity mismatch")


@dataclass(frozen=True, slots=True)
class MetaEvidenceObservation:
    observation_identity: str
    schema_version: str
    engine_version: str
    source_engine_id: str
    source_engine_version: str
    asset: str
    timeframe: str
    regime: str
    as_of_ms: int
    market_available_at_ms: int | None
    observed_at_ms: int | None
    state: MetaEvidenceState
    direction: MetaDirection | None
    source_evidence_identities: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "meta observation identity")
        if self.schema_version != META_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("unsupported meta observation schema")
        if self.engine_version != META_INTELLIGENCE_ENGINE_VERSION:
            raise ValueError("unsupported meta observation engine")
        for value, label in (
            (self.source_engine_id, "meta source engine id"),
            (self.source_engine_version, "meta source engine version"),
            (self.asset, "meta asset"),
            (self.timeframe, "meta timeframe"),
            (self.regime, "meta regime"),
        ):
            _require_text(value, label)
        if self.as_of_ms < 0:
            raise ValueError("meta as_of_ms must be non-negative")
        if (self.market_available_at_ms is None) != (self.observed_at_ms is None):
            raise ValueError("meta evidence timestamps must both exist or both be absent")
        if self.market_available_at_ms is not None:
            assert self.observed_at_ms is not None
            if self.market_available_at_ms < 0 or self.observed_at_ms < 0:
                raise ValueError("meta evidence timestamps must be non-negative")
            if self.market_available_at_ms > self.observed_at_ms:
                raise ValueError("meta evidence cannot be observed before availability")
            if self.observed_at_ms > self.as_of_ms:
                raise ValueError("meta evidence cannot be observed after as_of")
        _require_identity_tuple(
            self.source_evidence_identities,
            "meta source evidence identity",
        )
        _require_text_tuple(self.uncertainty_flags, "meta uncertainty flag")
        if self.state is MetaEvidenceState.OBSERVED:
            if self.direction is None:
                raise ValueError("observed meta evidence requires direction")
            if not self.source_evidence_identities:
                raise ValueError("observed meta evidence requires source identities")
            if self.market_available_at_ms is None:
                raise ValueError("observed meta evidence requires timestamps")
        else:
            if self.direction is not None:
                raise ValueError("non-observed meta evidence cannot carry direction")
            if self.state is MetaEvidenceState.ABSTAIN:
                if not self.source_evidence_identities:
                    raise ValueError("abstention requires source evidence")
                if self.market_available_at_ms is None:
                    raise ValueError("abstention requires timestamps")
        if self.observation_identity != canonical_sha256(
            _observation_payload(self)
        ):
            raise ValueError("meta observation identity mismatch")


@dataclass(frozen=True, slots=True)
class MetaEvidenceRelation:
    relation_identity: str
    schema_version: str
    engine_version: str
    left_observation_identity: str
    right_observation_identity: str
    relation: MetaRelationKind
    basis_evidence_identity: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.relation_identity, "meta relation identity"),
            (self.left_observation_identity, "meta relation left identity"),
            (self.right_observation_identity, "meta relation right identity"),
            (self.basis_evidence_identity, "meta relation basis identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != META_RELATION_SCHEMA_VERSION:
            raise ValueError("unsupported meta relation schema")
        if self.engine_version != META_INTELLIGENCE_ENGINE_VERSION:
            raise ValueError("unsupported meta relation engine")
        if self.left_observation_identity >= self.right_observation_identity:
            raise ValueError("meta relation endpoints must be canonical and distinct")
        if self.relation_identity != canonical_sha256(_relation_payload(self)):
            raise ValueError("meta relation identity mismatch")


@dataclass(frozen=True, slots=True)
class MetaContribution:
    observation_identity: str
    source_engine_id: str
    state: MetaEvidenceState
    direction: MetaDirection | None
    base_weight: Decimal
    group_adjusted_weight: Decimal
    effective_weight: Decimal
    signed_contribution: Decimal
    correlation_group_id: str | None

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "meta contribution observation")
        _require_text(self.source_engine_id, "meta contribution engine")
        for value, label in (
            (self.base_weight, "meta base weight"),
            (self.group_adjusted_weight, "meta group adjusted weight"),
            (self.effective_weight, "meta effective weight"),
        ):
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if abs(self.signed_contribution) > self.effective_weight:
            raise ValueError("meta signed contribution exceeds effective weight")
        if self.state is not MetaEvidenceState.OBSERVED and any(
            value != Decimal(0)
            for value in (
                self.base_weight,
                self.group_adjusted_weight,
                self.effective_weight,
                self.signed_contribution,
            )
        ):
            raise ValueError("non-observed evidence cannot contribute")
        if self.direction is MetaDirection.NEUTRAL and self.signed_contribution != 0:
            raise ValueError("neutral evidence cannot have signed contribution")


@dataclass(frozen=True, slots=True)
class MetaShadowSnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    policy_identity: str
    asset: str
    timeframe: str
    regime: str
    as_of_ms: int
    observation_identities: tuple[str, ...]
    relation_identities: tuple[str, ...]
    contributions: tuple[MetaContribution, ...]
    state_counts: tuple[tuple[str, int], ...]
    relation_counts: tuple[tuple[str, int], ...]
    signed_balance: Decimal | None
    total_effective_weight: Decimal
    bullish_weight: Decimal
    bearish_weight: Decimal
    neutral_weight: Decimal
    explicit_contradiction_count: int
    directional_conflict: bool
    redundancy_scaled_group_count: int
    policy_gap_engine_ids: tuple[str, ...]
    uncovered_correlation_relation_ids: tuple[str, ...]
    resolution: MetaResolution
    score_semantic: str = META_SCORE_SEMANTIC
    probability_status: str = PROBABILITY_STATUS
    shadow_only: bool = True
    production_contribution: int = 0
    production_authority: bool = False
    automatic_promotion: bool = False
    deploy_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "meta snapshot identity")
        _require_sha256(self.policy_identity, "meta snapshot policy identity")
        if self.schema_version != META_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported meta snapshot schema")
        if self.engine_version != META_INTELLIGENCE_ENGINE_VERSION:
            raise ValueError("unsupported meta snapshot engine")
        for value, label in (
            (self.asset, "meta snapshot asset"),
            (self.timeframe, "meta snapshot timeframe"),
            (self.regime, "meta snapshot regime"),
        ):
            _require_text(value, label)
        if self.as_of_ms < 0:
            raise ValueError("meta snapshot as_of_ms must be non-negative")
        _require_identity_tuple(self.observation_identities, "meta snapshot observation")
        _require_identity_tuple(self.relation_identities, "meta snapshot relation")
        contribution_ids = tuple(
            item.observation_identity for item in self.contributions
        )
        if contribution_ids != self.observation_identities:
            raise ValueError("meta contributions must exactly match observations")
        if self.signed_balance is not None and abs(self.signed_balance) > Decimal(1):
            raise ValueError("meta signed balance must remain inside [-1,1]")
        for weight_value in (
            self.total_effective_weight,
            self.bullish_weight,
            self.bearish_weight,
            self.neutral_weight,
        ):
            if weight_value < Decimal(0) or weight_value > Decimal(1):
                raise ValueError("meta snapshot weights must remain inside [0,1]")
        if self.total_effective_weight > Decimal(1):
            raise ValueError("meta total effective weight exceeds global bound")
        if min(
            self.explicit_contradiction_count,
            self.redundancy_scaled_group_count,
        ) < 0:
            raise ValueError("meta snapshot counts cannot be negative")
        _require_text_tuple(self.policy_gap_engine_ids, "meta policy gap engine")
        _require_identity_tuple(
            self.uncovered_correlation_relation_ids,
            "meta uncovered correlation relation",
        )
        if self.resolution is MetaResolution.POLICY_INCOMPLETE:
            if not (
                self.policy_gap_engine_ids
                or self.uncovered_correlation_relation_ids
            ):
                raise ValueError("policy-incomplete meta snapshot needs a gap")
            if self.signed_balance is not None:
                raise ValueError("policy-incomplete snapshot cannot expose balance")
        elif self.signed_balance is None:
            raise ValueError("complete meta snapshot requires signed balance")
        if self.score_semantic != META_SCORE_SEMANTIC:
            raise ValueError("meta score semantic mismatch")
        if self.probability_status != PROBABILITY_STATUS:
            raise ValueError("meta probability remains not calibrated")
        if not self.shadow_only:
            raise ValueError("meta snapshot must remain shadow-only")
        if self.production_contribution != 0:
            raise ValueError("meta snapshot production contribution must remain 0")
        if (
            self.production_authority
            or self.automatic_promotion
            or self.deploy_authority
        ):
            raise ValueError("meta snapshot has no production/promotion/deploy authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("meta snapshot identity mismatch")


def build_meta_weight_policy(
    *,
    policy_version: str,
    rules: Sequence[MetaWeightRule],
    correlation_groups: Sequence[MetaCorrelationGroup] = (),
    max_total_weight: Decimal = Decimal(1),
) -> MetaWeightPolicy:
    ordered_rules = tuple(sorted(rules, key=lambda item: (item.engine_id, item.regime)))
    normalized_groups = tuple(
        sorted(
            (
                MetaCorrelationGroup(
                    group_id=item.group_id,
                    engine_ids=tuple(sorted(item.engine_ids)),
                    max_total_weight=item.max_total_weight,
                )
                for item in correlation_groups
            ),
            key=lambda item: item.group_id,
        )
    )
    payload = {
        "automatic_promotion": False,
        "correlation_groups": normalized_groups,
        "deploy_authority": False,
        "engine_version": META_INTELLIGENCE_ENGINE_VERSION,
        "max_total_weight": max_total_weight,
        "policy_version": policy_version,
        "probability_status": PROBABILITY_STATUS,
        "production_authority": False,
        "production_contribution": 0,
        "real_capital": REAL_CAPITAL,
        "rules": ordered_rules,
        "schema_version": META_POLICY_SCHEMA_VERSION,
        "shadow_only": True,
    }
    return MetaWeightPolicy(
        policy_identity=canonical_sha256(payload),
        schema_version=META_POLICY_SCHEMA_VERSION,
        engine_version=META_INTELLIGENCE_ENGINE_VERSION,
        policy_version=policy_version,
        rules=ordered_rules,
        correlation_groups=normalized_groups,
        max_total_weight=max_total_weight,
    )


def build_meta_observation(
    *,
    source_engine_id: str,
    source_engine_version: str,
    asset: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
    state: MetaEvidenceState,
    direction: MetaDirection | None,
    source_evidence_identities: Sequence[str] = (),
    uncertainty_flags: Sequence[str] = (),
    market_available_at_ms: int | None = None,
    observed_at_ms: int | None = None,
) -> MetaEvidenceObservation:
    evidence_ids = tuple(sorted(set(source_evidence_identities)))
    flags = tuple(sorted(set(uncertainty_flags)))
    payload = {
        "asset": asset,
        "as_of_ms": as_of_ms,
        "direction": direction,
        "engine_version": META_INTELLIGENCE_ENGINE_VERSION,
        "market_available_at_ms": market_available_at_ms,
        "observed_at_ms": observed_at_ms,
        "regime": regime,
        "schema_version": META_OBSERVATION_SCHEMA_VERSION,
        "source_engine_id": source_engine_id,
        "source_engine_version": source_engine_version,
        "source_evidence_identities": evidence_ids,
        "state": state,
        "timeframe": timeframe,
        "uncertainty_flags": flags,
    }
    return MetaEvidenceObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=META_OBSERVATION_SCHEMA_VERSION,
        engine_version=META_INTELLIGENCE_ENGINE_VERSION,
        source_engine_id=source_engine_id,
        source_engine_version=source_engine_version,
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=as_of_ms,
        market_available_at_ms=market_available_at_ms,
        observed_at_ms=observed_at_ms,
        state=state,
        direction=direction,
        source_evidence_identities=evidence_ids,
        uncertainty_flags=flags,
    )


def build_meta_relation(
    left_observation_identity: str,
    right_observation_identity: str,
    *,
    relation: MetaRelationKind,
    basis_evidence_identity: str,
) -> MetaEvidenceRelation:
    left, right = sorted((left_observation_identity, right_observation_identity))
    if left == right:
        raise ValueError("meta relation requires distinct observations")
    payload = {
        "basis_evidence_identity": basis_evidence_identity,
        "engine_version": META_INTELLIGENCE_ENGINE_VERSION,
        "left_observation_identity": left,
        "relation": relation,
        "right_observation_identity": right,
        "schema_version": META_RELATION_SCHEMA_VERSION,
    }
    return MetaEvidenceRelation(
        relation_identity=canonical_sha256(payload),
        schema_version=META_RELATION_SCHEMA_VERSION,
        engine_version=META_INTELLIGENCE_ENGINE_VERSION,
        left_observation_identity=left,
        right_observation_identity=right,
        relation=relation,
        basis_evidence_identity=basis_evidence_identity,
    )


def evaluate_meta_intelligence(
    policy: MetaWeightPolicy,
    observations: Sequence[MetaEvidenceObservation],
    relations: Sequence[MetaEvidenceRelation] = (),
) -> MetaShadowSnapshot:
    if not observations:
        raise ValueError("meta evaluation requires context observations")
    ordered = tuple(
        sorted(observations, key=lambda item: item.observation_identity)
    )
    observation_ids = tuple(item.observation_identity for item in ordered)
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("meta observations must be unique")
    engine_ids = tuple(item.source_engine_id for item in ordered)
    if len(set(engine_ids)) != len(engine_ids):
        raise ValueError("meta snapshot permits one observation per source engine")

    first = ordered[0]
    context = (first.asset, first.timeframe, first.regime, first.as_of_ms)
    if any(
        (item.asset, item.timeframe, item.regime, item.as_of_ms) != context
        for item in ordered
    ):
        raise ValueError("meta observations must share exact context")

    ordered_relations = tuple(
        sorted(relations, key=lambda item: item.relation_identity)
    )
    relation_ids = tuple(item.relation_identity for item in ordered_relations)
    if len(set(relation_ids)) != len(relation_ids):
        raise ValueError("meta relations must be unique")
    known = {item.observation_identity: item for item in ordered}
    for relation in ordered_relations:
        if (
            relation.left_observation_identity not in known
            or relation.right_observation_identity not in known
        ):
            raise ValueError("meta relation references unknown observation")

    rule_map = {(item.engine_id, item.regime): item.weight for item in policy.rules}
    group_by_engine = {
        engine_id: group
        for group in policy.correlation_groups
        for engine_id in group.engine_ids
    }

    base_weights: dict[str, Decimal] = {}
    policy_gaps: set[str] = set()
    for item in ordered:
        if item.state is not MetaEvidenceState.OBSERVED:
            base_weights[item.observation_identity] = Decimal(0)
            continue
        weight = rule_map.get((item.source_engine_id, first.regime))
        if weight is None:
            weight = rule_map.get((item.source_engine_id, "*"))
        if weight is None:
            policy_gaps.add(item.source_engine_id)
            weight = Decimal(0)
        base_weights[item.observation_identity] = weight

    uncovered_relations: set[str] = set()
    for relation in ordered_relations:
        if relation.relation not in {
            MetaRelationKind.REDUNDANT,
            MetaRelationKind.OVERLAPPING,
        }:
            continue
        left = known[relation.left_observation_identity]
        right = known[relation.right_observation_identity]
        left_group = group_by_engine.get(left.source_engine_id)
        right_group = group_by_engine.get(right.source_engine_id)
        if (
            left_group is None
            or right_group is None
            or left_group.group_id != right_group.group_id
        ):
            uncovered_relations.add(relation.relation_identity)

    group_adjusted = dict(base_weights)
    scaled_groups = 0
    with localcontext() as ctx:
        ctx.prec = 36
        for group in policy.correlation_groups:
            members = [
                item
                for item in ordered
                if item.state is MetaEvidenceState.OBSERVED
                and item.source_engine_id in group.engine_ids
            ]
            total = sum(
                (base_weights[item.observation_identity] for item in members),
                start=Decimal(0),
            )
            if total <= group.max_total_weight or total == 0:
                continue
            factor = group.max_total_weight / total
            scaled_groups += 1
            for item in members:
                identity = item.observation_identity
                group_adjusted[identity] = base_weights[identity] * factor

        total_group_adjusted = sum(
            (
                group_adjusted[item.observation_identity]
                for item in ordered
                if item.state is MetaEvidenceState.OBSERVED
            ),
            start=Decimal(0),
        )
        global_factor = (
            Decimal(1)
            if total_group_adjusted <= policy.max_total_weight
            or total_group_adjusted == 0
            else policy.max_total_weight / total_group_adjusted
        )

        contributions: list[MetaContribution] = []
        bullish = Decimal(0)
        bearish = Decimal(0)
        neutral = Decimal(0)
        for item in ordered:
            identity = item.observation_identity
            current_group = group_by_engine.get(item.source_engine_id)
            if item.state is not MetaEvidenceState.OBSERVED:
                contribution = MetaContribution(
                    observation_identity=identity,
                    source_engine_id=item.source_engine_id,
                    state=item.state,
                    direction=None,
                    base_weight=Decimal(0),
                    group_adjusted_weight=Decimal(0),
                    effective_weight=Decimal(0),
                    signed_contribution=Decimal(0),
                    correlation_group_id=(
                        None if current_group is None else current_group.group_id
                    ),
                )
                contributions.append(contribution)
                continue

            effective = group_adjusted[identity] * global_factor
            if item.direction is MetaDirection.BULLISH:
                signed = effective
                bullish += effective
            elif item.direction is MetaDirection.BEARISH:
                signed = -effective
                bearish += effective
            else:
                signed = Decimal(0)
                neutral += effective
            contributions.append(
                MetaContribution(
                    observation_identity=identity,
                    source_engine_id=item.source_engine_id,
                    state=item.state,
                    direction=item.direction,
                    base_weight=base_weights[identity],
                    group_adjusted_weight=group_adjusted[identity],
                    effective_weight=effective,
                    signed_contribution=signed,
                    correlation_group_id=(
                        None if current_group is None else current_group.group_id
                    ),
                )
            )

    total_effective = bullish + bearish + neutral
    state_counts = tuple(
        sorted(Counter(item.state.value for item in ordered).items())
    )
    relation_counts = tuple(
        sorted(Counter(item.relation.value for item in ordered_relations).items())
    )
    explicit_contradictions = sum(
        1
        for item in ordered_relations
        if item.relation is MetaRelationKind.CONTRADICTORY
    )
    directional_conflict = bullish > 0 and bearish > 0
    gap_engines = tuple(sorted(policy_gaps))
    uncovered = tuple(sorted(uncovered_relations))

    if gap_engines or uncovered:
        balance: Decimal | None = None
        resolution = MetaResolution.POLICY_INCOMPLETE
    else:
        balance = sum(
            (item.signed_contribution for item in contributions),
            start=Decimal(0),
        )
        observed_count = sum(
            1 for item in ordered if item.state is MetaEvidenceState.OBSERVED
        )
        abstain_count = sum(
            1 for item in ordered if item.state is MetaEvidenceState.ABSTAIN
        )
        not_evaluable_count = sum(
            1
            for item in ordered
            if item.state is MetaEvidenceState.NOT_EVALUABLE
        )
        if observed_count == 0:
            if not_evaluable_count:
                resolution = MetaResolution.NOT_EVALUABLE
            elif abstain_count:
                resolution = MetaResolution.ABSTAIN_ONLY
            else:
                resolution = MetaResolution.NO_EVIDENCE
        elif explicit_contradictions or directional_conflict:
            resolution = MetaResolution.CONTRADICTORY
        elif bullish > bearish:
            resolution = MetaResolution.BULLISH_LEAN
        elif bearish > bullish:
            resolution = MetaResolution.BEARISH_LEAN
        else:
            resolution = MetaResolution.BALANCED

    payload = {
        "as_of_ms": first.as_of_ms,
        "asset": first.asset,
        "automatic_promotion": False,
        "bearish_weight": bearish,
        "bullish_weight": bullish,
        "contributions": tuple(contributions),
        "deploy_authority": False,
        "directional_conflict": directional_conflict,
        "engine_version": META_INTELLIGENCE_ENGINE_VERSION,
        "explicit_contradiction_count": explicit_contradictions,
        "neutral_weight": neutral,
        "observation_identities": observation_ids,
        "policy_gap_engine_ids": gap_engines,
        "policy_identity": policy.policy_identity,
        "probability_status": PROBABILITY_STATUS,
        "production_authority": False,
        "production_contribution": 0,
        "real_capital": REAL_CAPITAL,
        "redundancy_scaled_group_count": scaled_groups,
        "regime": first.regime,
        "relation_counts": relation_counts,
        "relation_identities": relation_ids,
        "resolution": resolution,
        "schema_version": META_SNAPSHOT_SCHEMA_VERSION,
        "score_semantic": META_SCORE_SEMANTIC,
        "shadow_only": True,
        "signed_balance": balance,
        "state_counts": state_counts,
        "timeframe": first.timeframe,
        "total_effective_weight": total_effective,
        "uncovered_correlation_relation_ids": uncovered,
    }
    return MetaShadowSnapshot(
        snapshot_identity=canonical_sha256(payload),
        schema_version=META_SNAPSHOT_SCHEMA_VERSION,
        engine_version=META_INTELLIGENCE_ENGINE_VERSION,
        policy_identity=policy.policy_identity,
        asset=first.asset,
        timeframe=first.timeframe,
        regime=first.regime,
        as_of_ms=first.as_of_ms,
        observation_identities=observation_ids,
        relation_identities=relation_ids,
        contributions=tuple(contributions),
        state_counts=state_counts,
        relation_counts=relation_counts,
        signed_balance=balance,
        total_effective_weight=total_effective,
        bullish_weight=bullish,
        bearish_weight=bearish,
        neutral_weight=neutral,
        explicit_contradiction_count=explicit_contradictions,
        directional_conflict=directional_conflict,
        redundancy_scaled_group_count=scaled_groups,
        policy_gap_engine_ids=gap_engines,
        uncovered_correlation_relation_ids=uncovered,
        resolution=resolution,
    )


def _policy_payload(policy: MetaWeightPolicy) -> dict[str, object]:
    return {
        "automatic_promotion": policy.automatic_promotion,
        "correlation_groups": policy.correlation_groups,
        "deploy_authority": policy.deploy_authority,
        "engine_version": policy.engine_version,
        "max_total_weight": policy.max_total_weight,
        "policy_version": policy.policy_version,
        "probability_status": policy.probability_status,
        "production_authority": policy.production_authority,
        "production_contribution": policy.production_contribution,
        "real_capital": policy.real_capital,
        "rules": policy.rules,
        "schema_version": policy.schema_version,
        "shadow_only": policy.shadow_only,
    }


def _observation_payload(observation: MetaEvidenceObservation) -> dict[str, object]:
    return {
        "asset": observation.asset,
        "as_of_ms": observation.as_of_ms,
        "direction": observation.direction,
        "engine_version": observation.engine_version,
        "market_available_at_ms": observation.market_available_at_ms,
        "observed_at_ms": observation.observed_at_ms,
        "regime": observation.regime,
        "schema_version": observation.schema_version,
        "source_engine_id": observation.source_engine_id,
        "source_engine_version": observation.source_engine_version,
        "source_evidence_identities": observation.source_evidence_identities,
        "state": observation.state,
        "timeframe": observation.timeframe,
        "uncertainty_flags": observation.uncertainty_flags,
    }


def _relation_payload(relation: MetaEvidenceRelation) -> dict[str, object]:
    return {
        "basis_evidence_identity": relation.basis_evidence_identity,
        "engine_version": relation.engine_version,
        "left_observation_identity": relation.left_observation_identity,
        "relation": relation.relation,
        "right_observation_identity": relation.right_observation_identity,
        "schema_version": relation.schema_version,
    }


def _snapshot_payload(snapshot: MetaShadowSnapshot) -> dict[str, object]:
    return {
        "as_of_ms": snapshot.as_of_ms,
        "asset": snapshot.asset,
        "automatic_promotion": snapshot.automatic_promotion,
        "bearish_weight": snapshot.bearish_weight,
        "bullish_weight": snapshot.bullish_weight,
        "contributions": snapshot.contributions,
        "deploy_authority": snapshot.deploy_authority,
        "directional_conflict": snapshot.directional_conflict,
        "engine_version": snapshot.engine_version,
        "explicit_contradiction_count": snapshot.explicit_contradiction_count,
        "neutral_weight": snapshot.neutral_weight,
        "observation_identities": snapshot.observation_identities,
        "policy_gap_engine_ids": snapshot.policy_gap_engine_ids,
        "policy_identity": snapshot.policy_identity,
        "probability_status": snapshot.probability_status,
        "production_authority": snapshot.production_authority,
        "production_contribution": snapshot.production_contribution,
        "real_capital": snapshot.real_capital,
        "redundancy_scaled_group_count": snapshot.redundancy_scaled_group_count,
        "regime": snapshot.regime,
        "relation_counts": snapshot.relation_counts,
        "relation_identities": snapshot.relation_identities,
        "resolution": snapshot.resolution,
        "schema_version": snapshot.schema_version,
        "score_semantic": snapshot.score_semantic,
        "shadow_only": snapshot.shadow_only,
        "signed_balance": snapshot.signed_balance,
        "state_counts": snapshot.state_counts,
        "timeframe": snapshot.timeframe,
        "total_effective_weight": snapshot.total_effective_weight,
        "uncovered_correlation_relation_ids": (
            snapshot.uncovered_correlation_relation_ids
        ),
    }


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be sorted and unique")
    for value in values:
        _require_sha256(value, label)


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be sorted and unique")
    for value in values:
        _require_text(value, label)


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
