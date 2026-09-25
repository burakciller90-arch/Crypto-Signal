from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyContribution,
    ConfluenceMatrixResolution,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.intelligence.meta_intelligence import MetaEvidenceState
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_messages import (
    StreamFactBundle,
    StreamMessageInput,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_story import (
    StreamChangeSet,
    StreamFamilyChange,
    StreamStoryState,
)

STREAM_ANALYTICAL_POLICY_SCHEMA_VERSION = "intelligence-stream-analytical-policy-v1/1"
STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION = "intelligence-stream-analytical-view-v1/2"
STREAM_ANALYTICAL_POLICY_VERSION = "stream-v1-analytical-composer/1"


class StreamEffectiveStance(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    WATCH = "watch"
    BLOCKED = "blocked"
    RESOLVED = "resolved"


class StreamStanceStrength(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    NOT_APPLICABLE = "not_applicable"


class StreamAnalyticalPublicationDisposition(StrEnum):
    PUBLISH = "publish"
    SILENT = "silent"


class StreamCapitalConsequenceState(StrEnum):
    NOT_BOUND = "not_bound"
    BOUND_UNCHANGED = "bound_unchanged"
    REFERENCES_ADDED = "references_added"
    REFERENCES_REMOVED = "references_removed"
    REFERENCES_CHANGED = "references_changed"


class StreamConditionKind(StrEnum):
    ENTRY_ZONE = "entry_zone"
    INVALIDATION_PRICE = "invalidation_price"


@dataclass(frozen=True, slots=True)
class StreamAnalyticalPolicy:
    policy_identity: str
    policy_version: str
    high_support_min_0_100: Decimal
    high_opposition_max_0_100: Decimal
    moderate_support_min_0_100: Decimal
    moderate_opposition_max_0_100: Decimal
    material_score_delta_0_100: Decimal
    material_family_points_delta_0_100: Decimal
    schema_version: str = STREAM_ANALYTICAL_POLICY_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "Stream analytical policy identity")
        if self.policy_version != STREAM_ANALYTICAL_POLICY_VERSION:
            raise ValueError("unsupported Stream analytical policy version")
        for value, label in (
            (self.high_support_min_0_100, "high support minimum"),
            (self.high_opposition_max_0_100, "high opposition maximum"),
            (self.moderate_support_min_0_100, "moderate support minimum"),
            (self.moderate_opposition_max_0_100, "moderate opposition maximum"),
            (self.material_score_delta_0_100, "material score delta"),
            (
                self.material_family_points_delta_0_100,
                "material family points delta",
            ),
        ):
            if value < Decimal(0) or value > Decimal(100):
                raise ValueError(f"{label} must be inside [0,100]")
        if self.high_support_min_0_100 < self.moderate_support_min_0_100:
            raise ValueError("high support threshold cannot be below moderate")
        if self.high_opposition_max_0_100 > self.moderate_opposition_max_0_100:
            raise ValueError("high opposition maximum cannot exceed moderate")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_ANALYTICAL_POLICY_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("Stream analytical policy identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalStance:
    effective_stance: StreamEffectiveStance
    direction: str
    decision_state: str
    stance_key: str
    strength: StreamStanceStrength
    support_score_0_100: Decimal
    opposition_score_0_100: Decimal
    net_support_points: Decimal

    def __post_init__(self) -> None:
        if not self.direction.strip() or not self.decision_state.strip():
            raise ValueError("Stream analytical stance text must be non-empty")
        if self.stance_key != f"{self.direction}:{self.decision_state}":
            raise ValueError("Stream analytical stance key mismatch")
        for value in (
            self.support_score_0_100,
            self.opposition_score_0_100,
        ):
            if value < Decimal(0) or value > Decimal(100):
                raise ValueError("Stream analytical stance score outside [0,100]")
        if self.net_support_points != (
            self.support_score_0_100 - self.opposition_score_0_100
        ):
            raise ValueError("Stream analytical net support mismatch")
        if self.net_support_points < Decimal(-100) or self.net_support_points > Decimal(100):
            raise ValueError("Stream analytical net support outside [-100,100]")
        if (
            self.effective_stance
            in {StreamEffectiveStance.BLOCKED, StreamEffectiveStance.RESOLVED}
            and self.strength is not StreamStanceStrength.NOT_APPLICABLE
        ):
            raise ValueError("blocked/resolved stance strength must be not-applicable")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalEvidenceSignal:
    family: ConfluenceFamily
    state: str
    direction: str | None
    support_points: Decimal
    opposition_points: Decimal
    evidence_quality_0_1: Decimal | None
    freshness_0_1: Decimal | None
    material_conflict_count: int
    source_evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.state.strip():
            raise ValueError("Stream analytical evidence state must be non-empty")
        for points_value in (self.support_points, self.opposition_points):
            if points_value < Decimal(0) or points_value > Decimal(100):
                raise ValueError("Stream analytical evidence points outside [0,100]")
        for quality_value in (self.evidence_quality_0_1, self.freshness_0_1):
            if quality_value is not None and (
                quality_value < Decimal(0) or quality_value > Decimal(1)
            ):
                raise ValueError("Stream analytical evidence quality outside [0,1]")
        if self.material_conflict_count < 0:
            raise ValueError("Stream analytical material conflict count cannot be negative")
        _require_identity_tuple(
            self.source_evidence_identities,
            "Stream analytical source evidence",
        )


@dataclass(frozen=True, slots=True)
class StreamAnalyticalUncertainty:
    codes: tuple[str, ...]
    support_evidence_count: int
    contradict_evidence_count: int
    neutral_evidence_count: int
    insufficient_evidence_count: int
    available_evidence_count: int
    total_evidence_domain_count: int
    material_conflict_count: int
    probability_status: str
    calibrated_probability_0_1: Decimal | None

    def __post_init__(self) -> None:
        _require_text_tuple(self.codes, "Stream analytical uncertainty code")
        counts = (
            self.support_evidence_count,
            self.contradict_evidence_count,
            self.neutral_evidence_count,
            self.insufficient_evidence_count,
            self.available_evidence_count,
            self.total_evidence_domain_count,
            self.material_conflict_count,
        )
        if min(counts) < 0:
            raise ValueError("Stream analytical uncertainty counts cannot be negative")
        if not self.probability_status.strip():
            raise ValueError("Stream analytical probability status cannot be blank")
        if self.calibrated_probability_0_1 is not None and not (
            Decimal(0) <= self.calibrated_probability_0_1 <= Decimal(1)
        ):
            raise ValueError("Stream analytical probability outside [0,1]")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalCondition:
    kind: StreamConditionKind
    state: str
    low: Decimal | None
    high: Decimal | None
    price: Decimal | None
    reason_code: str

    def __post_init__(self) -> None:
        if not self.state.strip() or not self.reason_code.strip():
            raise ValueError("Stream analytical condition text must be non-empty")
        if self.kind is StreamConditionKind.ENTRY_ZONE:
            if self.low is None or self.high is None or self.price is not None:
                raise ValueError("entry-zone condition requires low/high only")
            if self.low <= Decimal(0) or self.high <= Decimal(0) or self.low > self.high:
                raise ValueError("invalid analytical entry zone")
        else:
            if self.price is None or self.low is not None or self.high is not None:
                raise ValueError("invalidation condition requires price only")
            if self.price <= Decimal(0):
                raise ValueError("invalid analytical invalidation price")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalCapitalConsequence:
    state: StreamCapitalConsequenceState
    current_reference_identities: tuple[str, ...]
    added_reference_identities: tuple[str, ...]
    removed_reference_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        for values, label in (
            (self.current_reference_identities, "Stream analytical capital reference"),
            (self.added_reference_identities, "Stream analytical capital added"),
            (self.removed_reference_identities, "Stream analytical capital removed"),
        ):
            _require_identity_tuple(values, label)
        if self.state is StreamCapitalConsequenceState.NOT_BOUND:
            if self.current_reference_identities:
                raise ValueError("unbound Stream capital consequence cannot carry current refs")
        elif self.state is StreamCapitalConsequenceState.BOUND_UNCHANGED:
            if not self.current_reference_identities:
                raise ValueError("bound Stream capital consequence requires references")
            if self.added_reference_identities or self.removed_reference_identities:
                raise ValueError("unchanged Stream capital consequence cannot carry deltas")
        elif self.state is StreamCapitalConsequenceState.REFERENCES_ADDED:
            if not self.added_reference_identities or self.removed_reference_identities:
                raise ValueError("capital-added consequence requires added refs only")
        elif self.state is StreamCapitalConsequenceState.REFERENCES_REMOVED:
            if self.added_reference_identities or not self.removed_reference_identities:
                raise ValueError("capital-removed consequence requires removed refs only")
        elif not (
            self.added_reference_identities and self.removed_reference_identities
        ):
            raise ValueError("capital-changed consequence requires add/remove refs")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalMateriality:
    disposition: StreamAnalyticalPublicationDisposition
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text_tuple(self.reason_codes, "Stream analytical materiality reason")
        if not self.reason_codes:
            raise ValueError("Stream analytical materiality requires reason code")
        if (
            self.disposition is StreamAnalyticalPublicationDisposition.SILENT
            and self.reason_codes != ("no_material_analytical_change",)
        ):
            raise ValueError("silent analytical materiality reason mismatch")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalView:
    analytical_view_identity: str
    policy_identity: str
    policy_version: str
    fact_bundle_identity: str
    change_set_identity: str
    current_state_identity: str
    source_message_identity: str | None
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    stance: StreamAnalyticalStance
    dominant_support: StreamAnalyticalEvidenceSignal | None
    secondary_support: StreamAnalyticalEvidenceSignal | None
    main_contradiction: StreamAnalyticalEvidenceSignal | None
    uncertainty: StreamAnalyticalUncertainty
    changed_codes: tuple[str, ...]
    changed_families: tuple[ConfluenceFamily, ...]
    next_condition: StreamAnalyticalCondition
    invalidation_condition: StreamAnalyticalCondition
    capital_consequence: StreamAnalyticalCapitalConsequence
    materiality: StreamAnalyticalMateriality
    schema_version: str = STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.analytical_view_identity, "Stream analytical view identity"),
            (self.policy_identity, "Stream analytical policy identity"),
            (self.fact_bundle_identity, "Stream analytical fact bundle"),
            (self.change_set_identity, "Stream analytical change set"),
            (self.current_state_identity, "Stream analytical current state"),
            (self.story_identity, "Stream analytical story identity"),
            (self.source_event_identity, "Stream analytical source-event identity"),
            (self.stream_event_identity, "Stream analytical stream-event identity"),
        ):
            _require_sha256(value, label)
        if self.source_message_identity is not None:
            _require_sha256(
                self.source_message_identity,
                "Stream analytical source message identity",
            )
        if self.policy_version != STREAM_ANALYTICAL_POLICY_VERSION:
            raise ValueError("Stream analytical policy version mismatch")
        for value, label in (
            (self.asset, "Stream analytical asset"),
            (self.symbol, "Stream analytical symbol"),
            (self.timeframe, "Stream analytical timeframe"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.event_at_ms < 0:
            raise ValueError("Stream analytical event time must be non-negative")
        _require_text_tuple(self.changed_codes, "Stream analytical changed code")
        if not self.changed_codes:
            raise ValueError("Stream analytical view requires change codes")
        family_values = tuple(item.value for item in self.changed_families)
        if family_values != tuple(sorted(set(family_values))):
            raise ValueError("Stream analytical changed families must be canonical")
        _require_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.analytical_view_identity != canonical_sha256(
            _analytical_view_payload(self)
        ):
            raise ValueError("Stream analytical view identity mismatch")


def build_stream_analytical_policy() -> StreamAnalyticalPolicy:
    payload = {
        "engine_version": STREAM_ENGINE_VERSION,
        "high_opposition_max_0_100": Decimal(10),
        "high_support_min_0_100": Decimal(80),
        "material_family_points_delta_0_100": Decimal(5),
        "material_score_delta_0_100": Decimal(5),
        "moderate_opposition_max_0_100": Decimal(20),
        "moderate_support_min_0_100": Decimal(70),
        "policy_version": STREAM_ANALYTICAL_POLICY_VERSION,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_ANALYTICAL_POLICY_SCHEMA_VERSION,
    }
    return StreamAnalyticalPolicy(
        policy_identity=canonical_sha256(payload),
        policy_version=STREAM_ANALYTICAL_POLICY_VERSION,
        high_support_min_0_100=Decimal(80),
        high_opposition_max_0_100=Decimal(10),
        moderate_support_min_0_100=Decimal(70),
        moderate_opposition_max_0_100=Decimal(20),
        material_score_delta_0_100=Decimal(5),
        material_family_points_delta_0_100=Decimal(5),
    )


def compose_stream_analytical_view(
    policy: StreamAnalyticalPolicy,
    fact_bundle: StreamFactBundle,
    state: StreamStoryState,
    change_set: StreamChangeSet,
    *,
    message: StreamMessageInput | None = None,
) -> StreamAnalyticalView:
    _validate_lineage(fact_bundle, state, change_set, message=message)
    effective_stance = _effective_stance(fact_bundle, state)
    strength = _stance_strength(policy, fact_bundle, effective_stance)
    stance = StreamAnalyticalStance(
        effective_stance=effective_stance,
        direction=fact_bundle.direction,
        decision_state=fact_bundle.decision_state,
        stance_key=f"{fact_bundle.direction}:{fact_bundle.decision_state}",
        strength=strength,
        support_score_0_100=fact_bundle.confluence_support_score_0_100,
        opposition_score_0_100=fact_bundle.confluence_opposition_score_0_100,
        net_support_points=(
            fact_bundle.confluence_support_score_0_100
            - fact_bundle.confluence_opposition_score_0_100
        ),
    )

    support_ranked = tuple(
        sorted(
            (
                item
                for item in fact_bundle.family_contributions
                if item.support_points > Decimal(0)
            ),
            key=_support_rank_key,
        )
    )
    contradiction_ranked = tuple(
        sorted(
            (
                item
                for item in fact_bundle.family_contributions
                if (
                    item.opposition_points > Decimal(0)
                    or item.material_conflict_count > 0
                )
            ),
            key=_contradiction_rank_key,
        )
    )
    dominant_support = (
        None if not support_ranked else _evidence_signal(support_ranked[0])
    )
    secondary_support = (
        None
        if len(support_ranked) < 2
        else _evidence_signal(support_ranked[1])
    )
    main_contradiction = (
        None
        if not contradiction_ranked
        else _evidence_signal(contradiction_ranked[0])
    )

    uncertainty_codes = set(fact_bundle.uncertainty_flags)
    summary = fact_bundle.evidence_summary
    if summary.insufficient_count > 0:
        uncertainty_codes.add("accepted_evidence_incomplete")
    if summary.contradict_count > 0:
        uncertainty_codes.add("accepted_evidence_contradiction")
    if fact_bundle.calibrated_probability_0_1 is None:
        uncertainty_codes.add("probability_not_calibrated")
    if fact_bundle.confluence_resolution is not ConfluenceMatrixResolution.MEASURED:
        uncertainty_codes.add(
            f"confluence_{fact_bundle.confluence_resolution.value}"
        )
    if fact_bundle.event_context_state != CircuitBreakerState.CLEAR.value:
        uncertainty_codes.add(f"event_risk_{fact_bundle.event_context_state}")
    material_conflicts = 0
    for item in fact_bundle.family_contributions:
        material_conflicts += item.material_conflict_count
        if item.state is not MetaEvidenceState.OBSERVED:
            uncertainty_codes.add(f"{item.family.value}_{item.state.value}")
        if item.material_conflict_count > 0:
            uncertainty_codes.add(f"{item.family.value}_material_conflict")

    uncertainty = StreamAnalyticalUncertainty(
        codes=tuple(sorted(uncertainty_codes)),
        support_evidence_count=summary.support_count,
        contradict_evidence_count=summary.contradict_count,
        neutral_evidence_count=summary.neutral_count,
        insufficient_evidence_count=summary.insufficient_count,
        available_evidence_count=summary.available_count,
        total_evidence_domain_count=summary.total_domain_count,
        material_conflict_count=material_conflicts,
        probability_status=fact_bundle.probability_status,
        calibrated_probability_0_1=fact_bundle.calibrated_probability_0_1,
    )

    next_state = (
        "resolved"
        if state.outcome_state is not None
        else state.trigger_state or "pending_or_not_observed"
    )
    next_condition = StreamAnalyticalCondition(
        kind=StreamConditionKind.ENTRY_ZONE,
        state=next_state,
        low=fact_bundle.trigger_zone.low,
        high=fact_bundle.trigger_zone.high,
        price=None,
        reason_code="canonical_forecast_entry_zone",
    )
    invalidation_condition = StreamAnalyticalCondition(
        kind=StreamConditionKind.INVALIDATION_PRICE,
        state=(
            "historical_resolved"
            if state.outcome_state is not None
            else "active_condition"
        ),
        low=None,
        high=None,
        price=fact_bundle.invalidation_price,
        reason_code="canonical_forecast_invalidation_price",
    )

    capital = _capital_consequence(state, change_set)
    materiality = _analytical_materiality(policy, change_set)
    changed_families = tuple(
        sorted(
            {item.family for item in change_set.family_changes},
            key=lambda item: item.value,
        )
    )

    payload = {
        "asset": fact_bundle.asset,
        "capital_consequence": capital,
        "changed_codes": change_set.changed_codes,
        "changed_families": changed_families,
        "change_set_identity": change_set.change_set_identity,
        "current_state_identity": state.state_identity,
        "dominant_support": dominant_support,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": fact_bundle.event_at_ms,
        "fact_bundle_identity": fact_bundle.fact_bundle_identity,
        "invalidation_condition": invalidation_condition,
        "main_contradiction": main_contradiction,
        "materiality": materiality,
        "next_condition": next_condition,
        "policy_identity": policy.policy_identity,
        "policy_version": policy.policy_version,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
        "secondary_support": secondary_support,
        "source_event_identity": fact_bundle.source_event_identity,
        "source_message_identity": (
            None if message is None else message.message_identity
        ),
        "stance": stance,
        "story_identity": fact_bundle.story_identity,
        "stream_event_identity": fact_bundle.stream_event_identity,
        "symbol": fact_bundle.symbol,
        "timeframe": fact_bundle.timeframe,
        "uncertainty": uncertainty,
    }
    return StreamAnalyticalView(
        analytical_view_identity=canonical_sha256(payload),
        policy_identity=policy.policy_identity,
        policy_version=policy.policy_version,
        fact_bundle_identity=fact_bundle.fact_bundle_identity,
        change_set_identity=change_set.change_set_identity,
        current_state_identity=state.state_identity,
        source_message_identity=None if message is None else message.message_identity,
        story_identity=fact_bundle.story_identity,
        source_event_identity=fact_bundle.source_event_identity,
        stream_event_identity=fact_bundle.stream_event_identity,
        asset=fact_bundle.asset,
        symbol=fact_bundle.symbol,
        timeframe=fact_bundle.timeframe,
        event_at_ms=fact_bundle.event_at_ms,
        stance=stance,
        dominant_support=dominant_support,
        secondary_support=secondary_support,
        main_contradiction=main_contradiction,
        uncertainty=uncertainty,
        changed_codes=change_set.changed_codes,
        changed_families=changed_families,
        next_condition=next_condition,
        invalidation_condition=invalidation_condition,
        capital_consequence=capital,
        materiality=materiality,
    )


def _validate_lineage(
    fact: StreamFactBundle,
    state: StreamStoryState,
    change_set: StreamChangeSet,
    *,
    message: StreamMessageInput | None,
) -> None:
    if state.story_identity != fact.story_identity:
        raise ValueError("Stream analytical state/fact story mismatch")
    if state.source_event_identity != fact.source_event_identity:
        raise ValueError("Stream analytical state/fact source-event mismatch")
    if state.current_stream_event_identity != fact.stream_event_identity:
        raise ValueError("Stream analytical state/fact stream-event mismatch")
    if state.event_at_ms != fact.event_at_ms:
        raise ValueError("Stream analytical state/fact event-time mismatch")
    if (state.asset, state.symbol, state.timeframe) != (
        fact.asset,
        fact.symbol,
        fact.timeframe,
    ):
        raise ValueError("Stream analytical state/fact market mismatch")
    if change_set.story_identity != state.story_identity:
        raise ValueError("Stream analytical change/state story mismatch")
    if change_set.current_state_identity != state.state_identity:
        raise ValueError("Stream analytical change/state identity mismatch")
    if state.support_score_0_100 != fact.confluence_support_score_0_100:
        raise ValueError("Stream analytical support-score lineage mismatch")
    if state.opposition_score_0_100 != fact.confluence_opposition_score_0_100:
        raise ValueError("Stream analytical opposition-score lineage mismatch")
    if message is not None:
        if message.fact_bundle_identity != fact.fact_bundle_identity:
            raise ValueError("Stream analytical message/fact identity mismatch")
        if message.story_identity != fact.story_identity:
            raise ValueError("Stream analytical message/fact story mismatch")
        if message.stream_event_identity != fact.stream_event_identity:
            raise ValueError("Stream analytical message/fact stream-event mismatch")
        if message.source_event_identity != fact.source_event_identity:
            raise ValueError("Stream analytical message/fact source-event mismatch")
        if (
            change_set.current_message_identity is not None
            and change_set.current_message_identity != message.message_identity
        ):
            raise ValueError("Stream analytical change/message identity mismatch")


def _effective_stance(
    fact: StreamFactBundle,
    state: StreamStoryState,
) -> StreamEffectiveStance:
    if state.outcome_state is not None:
        return StreamEffectiveStance.RESOLVED
    risk = CircuitBreakerState(fact.event_context_state)
    if risk in {
        CircuitBreakerState.EVENT_BLOCK,
        CircuitBreakerState.DEGRADED_DATA,
        CircuitBreakerState.ABSTAIN,
    }:
        return StreamEffectiveStance.BLOCKED
    if risk is CircuitBreakerState.CAUTION or state.decision_state == "watch":
        return StreamEffectiveStance.WATCH
    if state.direction == "bullish":
        return StreamEffectiveStance.BULLISH
    if state.direction == "bearish":
        return StreamEffectiveStance.BEARISH
    return StreamEffectiveStance.WATCH


def _stance_strength(
    policy: StreamAnalyticalPolicy,
    fact: StreamFactBundle,
    stance: StreamEffectiveStance,
) -> StreamStanceStrength:
    if stance in {StreamEffectiveStance.BLOCKED, StreamEffectiveStance.RESOLVED}:
        return StreamStanceStrength.NOT_APPLICABLE
    support = fact.confluence_support_score_0_100
    opposition = fact.confluence_opposition_score_0_100
    if (
        support >= policy.high_support_min_0_100
        and opposition <= policy.high_opposition_max_0_100
    ):
        return StreamStanceStrength.HIGH
    if (
        support >= policy.moderate_support_min_0_100
        and opposition <= policy.moderate_opposition_max_0_100
    ):
        return StreamStanceStrength.MODERATE
    return StreamStanceStrength.LOW


def _support_rank_key(
    contribution: ConfluenceFamilyContribution,
) -> tuple[Decimal, Decimal, str]:
    quality = (
        contribution.evidence_quality_0_1
        if contribution.evidence_quality_0_1 is not None
        else Decimal(-1)
    )
    return (-contribution.support_points, -quality, contribution.family.value)


def _contradiction_rank_key(
    contribution: ConfluenceFamilyContribution,
) -> tuple[Decimal, int, str]:
    return (
        -contribution.opposition_points,
        -contribution.material_conflict_count,
        contribution.family.value,
    )


def _evidence_signal(
    contribution: ConfluenceFamilyContribution,
) -> StreamAnalyticalEvidenceSignal:
    return StreamAnalyticalEvidenceSignal(
        family=contribution.family,
        state=contribution.state.value,
        direction=(
            None if contribution.direction is None else contribution.direction.value
        ),
        support_points=contribution.support_points,
        opposition_points=contribution.opposition_points,
        evidence_quality_0_1=contribution.evidence_quality_0_1,
        freshness_0_1=contribution.freshness_0_1,
        material_conflict_count=contribution.material_conflict_count,
        source_evidence_identities=contribution.source_evidence_identities,
    )


def _capital_consequence(
    state: StreamStoryState,
    change_set: StreamChangeSet,
) -> StreamAnalyticalCapitalConsequence:
    current = state.capital_reference_identities
    added = change_set.capital_reference_added
    removed = change_set.capital_reference_removed
    if added and removed:
        consequence_state = StreamCapitalConsequenceState.REFERENCES_CHANGED
    elif added:
        consequence_state = StreamCapitalConsequenceState.REFERENCES_ADDED
    elif removed:
        consequence_state = StreamCapitalConsequenceState.REFERENCES_REMOVED
    elif current:
        consequence_state = StreamCapitalConsequenceState.BOUND_UNCHANGED
    else:
        consequence_state = StreamCapitalConsequenceState.NOT_BOUND
    return StreamAnalyticalCapitalConsequence(
        state=consequence_state,
        current_reference_identities=current,
        added_reference_identities=added,
        removed_reference_identities=removed,
    )


def _analytical_materiality(
    policy: StreamAnalyticalPolicy,
    change_set: StreamChangeSet,
) -> StreamAnalyticalMateriality:
    reasons: set[str] = set()
    if change_set.story_started:
        reasons.add("story_started")
    if change_set.stance_changed:
        reasons.add("stance_changed")
    if change_set.risk_changed:
        reasons.add("risk_changed")
    if change_set.trigger_changed:
        reasons.add("trigger_changed")
    if change_set.capital_changed:
        reasons.add("capital_changed")
    if change_set.outcome_changed:
        reasons.add("outcome_changed")
    if (
        change_set.support_score_delta is not None
        and abs(change_set.support_score_delta)
        >= policy.material_score_delta_0_100
    ):
        reasons.add("support_score_changed_materially")
    if (
        change_set.opposition_score_delta is not None
        and abs(change_set.opposition_score_delta)
        >= policy.material_score_delta_0_100
    ):
        reasons.add("opposition_score_changed_materially")
    if any(
        _family_change_is_material(policy, item)
        for item in change_set.family_changes
    ):
        reasons.add("evidence_family_changed_materially")
    if not reasons:
        return StreamAnalyticalMateriality(
            disposition=StreamAnalyticalPublicationDisposition.SILENT,
            reason_codes=("no_material_analytical_change",),
        )
    return StreamAnalyticalMateriality(
        disposition=StreamAnalyticalPublicationDisposition.PUBLISH,
        reason_codes=tuple(sorted(reasons)),
    )


def _family_change_is_material(
    policy: StreamAnalyticalPolicy,
    item: StreamFamilyChange,
) -> bool:
    return (
        item.previous_state != item.current_state
        or item.previous_direction != item.current_direction
        or item.previous_material_conflict_count
        != item.current_material_conflict_count
        or abs(item.support_delta) >= policy.material_family_points_delta_0_100
        or abs(item.opposition_delta)
        >= policy.material_family_points_delta_0_100
    )


def analytical_view_payload(value: StreamAnalyticalView) -> dict[str, object]:
    return _analytical_view_payload(value)


def _policy_payload(value: StreamAnalyticalPolicy) -> dict[str, object]:
    return {
        "engine_version": value.engine_version,
        "high_opposition_max_0_100": value.high_opposition_max_0_100,
        "high_support_min_0_100": value.high_support_min_0_100,
        "material_family_points_delta_0_100": (
            value.material_family_points_delta_0_100
        ),
        "material_score_delta_0_100": value.material_score_delta_0_100,
        "moderate_opposition_max_0_100": value.moderate_opposition_max_0_100,
        "moderate_support_min_0_100": value.moderate_support_min_0_100,
        "policy_version": value.policy_version,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
    }


def _analytical_view_payload(value: StreamAnalyticalView) -> dict[str, object]:
    return {
        "asset": value.asset,
        "capital_consequence": value.capital_consequence,
        "changed_codes": value.changed_codes,
        "changed_families": value.changed_families,
        "change_set_identity": value.change_set_identity,
        "current_state_identity": value.current_state_identity,
        "dominant_support": value.dominant_support,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "invalidation_condition": value.invalidation_condition,
        "main_contradiction": value.main_contradiction,
        "materiality": value.materiality,
        "next_condition": value.next_condition,
        "policy_identity": value.policy_identity,
        "policy_version": value.policy_version,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "secondary_support": value.secondary_support,
        "source_event_identity": value.source_event_identity,
        "source_message_identity": value.source_message_identity,
        "stance": value.stance,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "uncertainty": value.uncertainty,
    }


def _require_authority(
    *,
    schema_version: str,
    expected_schema: str,
    engine_version: str,
    read_only: bool,
    production_authority: bool,
    real_capital: int,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("unsupported Stream analytical schema")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream analytical engine")
    if not read_only:
        raise ValueError("Stream analytical truth must remain read-only")
    if production_authority:
        raise ValueError("Stream analytical view cannot grant production authority")
    if real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot contain blank values")
