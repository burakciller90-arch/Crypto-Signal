from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import PriceZone
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyContribution,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.intelligence_stream_messages import (
    StreamFactBundle,
    StreamMessageInput,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamMateriality,
    StreamPublicationDisposition,
)
from crypto_signal.product.intelligence_stream_story import StreamChangeSet

STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION = "intelligence-stream-analytical-view-v1/1"
STREAM_ANALYTICAL_COMPOSER_VERSION = "intelligence-stream-analytical-composer-v1/1"


class StreamCapitalConsequenceState(StrEnum):
    NOT_BOUND = "not_bound"
    BOUND_UNCHANGED = "bound_unchanged"
    REFERENCES_CHANGED = "references_changed"


@dataclass(frozen=True, slots=True)
class StreamAnalyticalStance:
    direction: str
    decision_state: str
    stance_key: str
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
        for value in (self.support_points, self.opposition_points):
            if value < Decimal(0) or value > Decimal(100):
                raise ValueError("Stream analytical evidence points outside [0,100]")
        for value in (self.evidence_quality_0_1, self.freshness_0_1):
            if value is not None and (value < Decimal(0) or value > Decimal(1)):
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
class StreamAnalyticalNextCondition:
    trigger_zone: PriceZone
    trigger_state: str | None
    target_zone: PriceZone
    invalidation_price: Decimal

    def __post_init__(self) -> None:
        if self.trigger_state is not None and not self.trigger_state.strip():
            raise ValueError("Stream analytical trigger state cannot be blank")
        if self.invalidation_price <= Decimal(0):
            raise ValueError("Stream analytical invalidation must be positive")


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
            if (
                self.current_reference_identities
                or self.added_reference_identities
                or self.removed_reference_identities
            ):
                raise ValueError("unbound Stream capital consequence cannot carry references")
        elif self.state is StreamCapitalConsequenceState.BOUND_UNCHANGED:
            if not self.current_reference_identities:
                raise ValueError("bound Stream capital consequence requires references")
            if self.added_reference_identities or self.removed_reference_identities:
                raise ValueError("unchanged Stream capital consequence cannot carry deltas")
        else:
            if not (
                self.added_reference_identities or self.removed_reference_identities
            ):
                raise ValueError("changed Stream capital consequence requires deltas")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalMateriality:
    disposition: StreamPublicationDisposition
    materiality: StreamMateriality
    materiality_decision_identity: str
    materiality_policy_identity: str
    materiality_policy_version: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.materiality_decision_identity,
            "Stream analytical materiality decision",
        )
        _require_sha256(
            self.materiality_policy_identity,
            "Stream analytical materiality policy",
        )
        if not self.materiality_policy_version.strip():
            raise ValueError("Stream analytical materiality version cannot be blank")
        _require_text_tuple(self.reason_codes, "Stream analytical materiality reason")
        if not self.reason_codes:
            raise ValueError("Stream analytical materiality requires reason code")


@dataclass(frozen=True, slots=True)
class StreamAnalyticalView:
    analytical_view_identity: str
    fact_bundle_identity: str
    change_set_identity: str
    message_identity: str
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
    next_condition: StreamAnalyticalNextCondition
    capital_consequence: StreamAnalyticalCapitalConsequence
    materiality: StreamAnalyticalMateriality
    schema_version: str = STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION
    composer_version: str = STREAM_ANALYTICAL_COMPOSER_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.analytical_view_identity, "Stream analytical view identity"),
            (self.fact_bundle_identity, "Stream analytical fact bundle"),
            (self.change_set_identity, "Stream analytical change set"),
            (self.message_identity, "Stream analytical message identity"),
            (self.story_identity, "Stream analytical story identity"),
            (self.source_event_identity, "Stream analytical source-event identity"),
            (self.stream_event_identity, "Stream analytical stream-event identity"),
        ):
            _require_sha256(value, label)
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
        if self.schema_version != STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION:
            raise ValueError("unsupported Stream analytical view schema")
        if self.composer_version != STREAM_ANALYTICAL_COMPOSER_VERSION:
            raise ValueError("unsupported Stream analytical composer version")
        if self.engine_version != STREAM_ENGINE_VERSION:
            raise ValueError("unsupported Stream analytical engine version")
        if not self.read_only:
            raise ValueError("Stream analytical view must remain read-only")
        if self.production_authority:
            raise ValueError("Stream analytical view cannot grant production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.analytical_view_identity != canonical_sha256(
            _analytical_view_payload(self)
        ):
            raise ValueError("Stream analytical view identity mismatch")


def compose_stream_analytical_view(
    fact_bundle: StreamFactBundle,
    change_set: StreamChangeSet,
    message: StreamMessageInput,
) -> StreamAnalyticalView:
    if fact_bundle.story_identity != change_set.story_identity:
        raise ValueError("Stream analytical fact/change story mismatch")
    if fact_bundle.story_identity != message.story_identity:
        raise ValueError("Stream analytical fact/message story mismatch")
    if fact_bundle.fact_bundle_identity != message.fact_bundle_identity:
        raise ValueError("Stream analytical fact/message identity mismatch")
    if fact_bundle.source_event_identity != message.source_event_identity:
        raise ValueError("Stream analytical fact/message source-event mismatch")
    if fact_bundle.stream_event_identity != message.stream_event_identity:
        raise ValueError("Stream analytical fact/message stream-event mismatch")
    if change_set.current_message_identity != message.message_identity:
        raise ValueError("Stream analytical change/message identity mismatch")
    if (fact_bundle.asset, fact_bundle.symbol, fact_bundle.timeframe) != (
        message.asset,
        message.symbol,
        message.timeframe,
    ):
        raise ValueError("Stream analytical market context mismatch")

    contributions = fact_bundle.family_contributions
    support_ranked = tuple(
        sorted(
            (
                item
                for item in contributions
                if item.support_points > Decimal(0)
            ),
            key=_support_rank_key,
        )
    )
    contradiction_ranked = tuple(
        sorted(
            (
                item
                for item in contributions
                if (
                    item.opposition_points > Decimal(0)
                    or item.material_conflict_count > 0
                )
            ),
            key=_contradiction_rank_key,
        )
    )

    stance = StreamAnalyticalStance(
        direction=fact_bundle.direction,
        decision_state=fact_bundle.decision_state,
        stance_key=f"{fact_bundle.direction}:{fact_bundle.decision_state}",
        support_score_0_100=fact_bundle.confluence_support_score_0_100,
        opposition_score_0_100=fact_bundle.confluence_opposition_score_0_100,
        net_support_points=(
            fact_bundle.confluence_support_score_0_100
            - fact_bundle.confluence_opposition_score_0_100
        ),
    )
    summary = fact_bundle.evidence_summary
    uncertainty_codes = set(fact_bundle.uncertainty_flags)
    if summary.insufficient_count > 0:
        uncertainty_codes.add("accepted_evidence_incomplete")
    if summary.contradict_count > 0:
        uncertainty_codes.add("accepted_evidence_contradiction")
    material_conflicts = sum(
        item.material_conflict_count for item in contributions
    )
    if material_conflicts > 0:
        uncertainty_codes.add("m6_material_conflict_present")
    if fact_bundle.calibrated_probability_0_1 is None:
        uncertainty_codes.add("probability_not_calibrated")
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
    current_capital = tuple(sorted(set(message.capital_reference_identities)))
    if change_set.capital_changed:
        capital_state = StreamCapitalConsequenceState.REFERENCES_CHANGED
    elif current_capital:
        capital_state = StreamCapitalConsequenceState.BOUND_UNCHANGED
    else:
        capital_state = StreamCapitalConsequenceState.NOT_BOUND
    capital = StreamAnalyticalCapitalConsequence(
        state=capital_state,
        current_reference_identities=current_capital,
        added_reference_identities=change_set.capital_reference_added,
        removed_reference_identities=change_set.capital_reference_removed,
    )
    materiality = StreamAnalyticalMateriality(
        disposition=message.publication_disposition,
        materiality=message.materiality,
        materiality_decision_identity=message.materiality_decision_identity,
        materiality_policy_identity=message.materiality_policy_identity,
        materiality_policy_version=message.materiality_policy_version,
        reason_codes=("s2_materiality_decision_bound",),
    )
    changed_families = tuple(
        sorted(
            {item.family for item in change_set.family_changes},
            key=lambda item: item.value,
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
    next_condition = StreamAnalyticalNextCondition(
        trigger_zone=fact_bundle.trigger_zone,
        trigger_state=change_set.current_trigger_state,
        target_zone=fact_bundle.target_zone,
        invalidation_price=fact_bundle.invalidation_price,
    )
    payload = {
        "asset": fact_bundle.asset,
        "capital_consequence": capital,
        "changed_codes": change_set.changed_codes,
        "changed_families": changed_families,
        "change_set_identity": change_set.change_set_identity,
        "composer_version": STREAM_ANALYTICAL_COMPOSER_VERSION,
        "dominant_support": dominant_support,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": fact_bundle.event_at_ms,
        "fact_bundle_identity": fact_bundle.fact_bundle_identity,
        "main_contradiction": main_contradiction,
        "materiality": materiality,
        "message_identity": message.message_identity,
        "next_condition": next_condition,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
        "secondary_support": secondary_support,
        "source_event_identity": fact_bundle.source_event_identity,
        "stance": stance,
        "story_identity": fact_bundle.story_identity,
        "stream_event_identity": fact_bundle.stream_event_identity,
        "symbol": fact_bundle.symbol,
        "timeframe": fact_bundle.timeframe,
        "uncertainty": uncertainty,
    }
    return StreamAnalyticalView(
        analytical_view_identity=canonical_sha256(payload),
        fact_bundle_identity=fact_bundle.fact_bundle_identity,
        change_set_identity=change_set.change_set_identity,
        message_identity=message.message_identity,
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
        capital_consequence=capital,
        materiality=materiality,
    )


def _support_rank_key(
    contribution: ConfluenceFamilyContribution,
) -> tuple[Decimal, Decimal, str]:
    quality = (
        contribution.evidence_quality_0_1
        if contribution.evidence_quality_0_1 is not None
        else Decimal(-1)
    )
    return (
        -contribution.support_points,
        -quality,
        contribution.family.value,
    )


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
            None
            if contribution.direction is None
            else contribution.direction.value
        ),
        support_points=contribution.support_points,
        opposition_points=contribution.opposition_points,
        evidence_quality_0_1=contribution.evidence_quality_0_1,
        freshness_0_1=contribution.freshness_0_1,
        material_conflict_count=contribution.material_conflict_count,
        source_evidence_identities=contribution.source_evidence_identities,
    )


def _analytical_view_payload(
    value: StreamAnalyticalView,
) -> dict[str, object]:
    return {
        "asset": value.asset,
        "capital_consequence": value.capital_consequence,
        "changed_codes": value.changed_codes,
        "changed_families": value.changed_families,
        "change_set_identity": value.change_set_identity,
        "composer_version": value.composer_version,
        "dominant_support": value.dominant_support,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "main_contradiction": value.main_contradiction,
        "materiality": value.materiality,
        "message_identity": value.message_identity,
        "next_condition": value.next_condition,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "secondary_support": value.secondary_support,
        "source_event_identity": value.source_event_identity,
        "stance": value.stance,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "uncertainty": value.uncertainty,
    }


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


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
