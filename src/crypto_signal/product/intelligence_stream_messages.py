from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import PriceZone
from crypto_signal.forecast_stream import (
    ForecastResolution,
    ForecastResolutionState,
    ImmutableForecast,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamilyContribution,
    ConfluenceMatrixResolution,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass, OutcomeState
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSummary,
    DecisionProofSnapshot,
    ProofEvidenceAvailability,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    StreamCategory,
    StreamDecisionContextSnapshot,
    StreamImportance,
    StreamSourceEvent,
)

STREAM_FACT_BUNDLE_SCHEMA_VERSION = "intelligence-stream-fact-bundle-v1/1"
STREAM_MESSAGE_INPUT_SCHEMA_VERSION = "intelligence-stream-message-input-v1/2"
STREAM_MESSAGE_PROJECTOR_VERSION = "intelligence-stream-message-projector-v1/1"
STREAM_MATERIALITY_POLICY_VERSION = "intelligence-stream-materiality-policy-v1/1"
STREAM_PUBLISHED_MESSAGE_SCHEMA_VERSION = "intelligence-stream-published-message-v1/1"
STREAM_STORY_NAMESPACE_VERSION = "intelligence-stream-story-namespace-v1/1"


class StreamMateriality(StrEnum):
    ROUTINE = "routine"
    MATERIAL = "material"


class StreamMessageRelationKind(StrEnum):
    RELATES_TO = "relates_to"
    RESOLVES = "resolves"
    SUPERSEDES = "supersedes"


@dataclass(frozen=True, slots=True)
class StreamMessageRelation:
    kind: StreamMessageRelationKind
    target_message_identity: str
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StreamMessageRelationKind):
            raise TypeError("Stream message relation kind must be canonical")
        _require_sha256(
            self.target_message_identity,
            "Stream relation target message identity",
        )
        if not self.reason_code.strip():
            raise ValueError("Stream message relation reason must be non-empty")


@dataclass(frozen=True, slots=True)
class StreamSearchMetadata:
    asset: str
    symbol: str
    market: str
    timeframe: str
    category: StreamCategory
    importance: StreamImportance
    evidence_domains: tuple[str, ...]
    states: tuple[str, ...]
    vaults: tuple[str, ...]
    search_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.asset, "Stream search asset"),
            (self.symbol, "Stream search symbol"),
            (self.market, "Stream search market"),
            (self.timeframe, "Stream search timeframe"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.category, StreamCategory):
            raise TypeError("Stream search category must be canonical")
        if not isinstance(self.importance, StreamImportance):
            raise TypeError("Stream search importance must be canonical")
        _require_text_tuple(self.evidence_domains, "Stream search evidence domain")
        _require_text_tuple(self.states, "Stream search state")
        _require_text_tuple(self.vaults, "Stream search vault")
        _require_text_tuple(self.search_terms, "Stream search term")


@dataclass(frozen=True, slots=True)
class StreamFactBundle:
    fact_bundle_identity: str
    stream_event_identity: str
    source_event_identity: str
    story_identity: str
    decision_context_identity: str
    forecast_identity: str
    proof_identity: str
    resolution_identity: str | None
    source_outcome_identity: str | None
    asset: str
    symbol: str
    market: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    decision_source_as_of_ms: int
    decision_state: str
    direction: str
    confluence_support_score_0_100: Decimal
    confluence_opposition_score_0_100: Decimal
    confluence_resolution: ConfluenceMatrixResolution
    family_contributions: tuple[ConfluenceFamilyContribution, ...]
    event_context_state: str
    trigger_zone: PriceZone
    target_zone: PriceZone
    invalidation_price: Decimal
    probability_status: str
    calibrated_probability_0_1: Decimal | None
    freshness_0_1: Decimal | None
    uncertainty_flags: tuple[str, ...]
    available_evidence_domains: tuple[str, ...]
    evidence_summary: DecisionProofEvidenceSummary
    resolution_state: ForecastResolutionState | None
    source_outcome_state: OutcomeState | None
    outcome_evidence_class: EvidenceClass | None
    resolution_reason_codes: tuple[str, ...]
    schema_version: str = STREAM_FACT_BUNDLE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.fact_bundle_identity, "Stream fact bundle identity"),
            (self.stream_event_identity, "Stream fact stream-event identity"),
            (self.source_event_identity, "Stream fact source-event identity"),
            (self.story_identity, "Stream fact story identity"),
            (self.decision_context_identity, "Stream fact decision-context identity"),
            (self.forecast_identity, "Stream fact forecast identity"),
            (self.proof_identity, "Stream fact proof identity"),
        ):
            _require_sha256(value, label)
        for optional_identity, label in (
            (self.resolution_identity, "Stream fact resolution identity"),
            (self.source_outcome_identity, "Stream fact source-outcome identity"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        for value, label in (
            (self.asset, "Stream fact asset"),
            (self.symbol, "Stream fact symbol"),
            (self.market, "Stream fact market"),
            (self.timeframe, "Stream fact timeframe"),
            (self.decision_state, "Stream fact decision state"),
            (self.direction, "Stream fact direction"),
            (self.event_context_state, "Stream fact Event Risk state"),
            (self.probability_status, "Stream fact probability status"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if min(
            self.event_at_ms,
            self.source_as_of_ms,
            self.decision_source_as_of_ms,
        ) < 0:
            raise ValueError("Stream fact timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("Stream fact event cannot predate event source-as-of")
        if self.event_at_ms < self.decision_source_as_of_ms:
            raise ValueError("Stream fact event cannot predate decision source-as-of")
        for score in (
            self.confluence_support_score_0_100,
            self.confluence_opposition_score_0_100,
        ):
            if score < Decimal(0) or score > Decimal(100):
                raise ValueError("Stream fact confluence score outside [0,100]")
        if len(self.family_contributions) != 5:
            raise ValueError("Stream fact bundle requires all five M6 contributions")
        if self.invalidation_price <= Decimal(0):
            raise ValueError("Stream fact invalidation price must be positive")
        if self.calibrated_probability_0_1 is not None and not (
            Decimal(0) <= self.calibrated_probability_0_1 <= Decimal(1)
        ):
            raise ValueError("Stream fact calibrated probability outside [0,1]")
        if self.freshness_0_1 is not None and not (
            Decimal(0) <= self.freshness_0_1 <= Decimal(1)
        ):
            raise ValueError("Stream fact freshness outside [0,1]")
        _require_text_tuple(self.uncertainty_flags, "Stream fact uncertainty")
        _require_text_tuple(
            self.available_evidence_domains,
            "Stream fact available evidence domain",
        )
        _require_text_tuple(
            self.resolution_reason_codes,
            "Stream fact resolution reason",
        )
        resolution_fields = (
            self.resolution_identity,
            self.source_outcome_identity,
            self.resolution_state,
            self.source_outcome_state,
            self.outcome_evidence_class,
        )
        has_resolution = self.resolution_identity is not None
        if has_resolution != all(value is not None for value in resolution_fields):
            raise ValueError("Stream fact resolution fields must be all present or absent")
        if has_resolution and not self.resolution_reason_codes:
            raise ValueError("resolved Stream fact requires resolution reasons")
        if not has_resolution and self.resolution_reason_codes:
            raise ValueError("issuance Stream fact cannot carry resolution reasons")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_FACT_BUNDLE_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.fact_bundle_identity != canonical_sha256(_fact_bundle_payload(self)):
            raise ValueError("Stream fact bundle identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamMessageInput:
    message_identity: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    fact_bundle_identity: str
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    materiality: StreamMateriality
    asset: str
    symbol: str
    market: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    evidence_reference_identities: tuple[str, ...]
    proof_reference_identities: tuple[str, ...]
    capital_reference_identities: tuple[str, ...]
    relations: tuple[StreamMessageRelation, ...]
    supersedes_message_identity: str | None
    search_metadata: StreamSearchMetadata
    materiality_policy_version: str = STREAM_MATERIALITY_POLICY_VERSION
    projector_version: str = STREAM_MESSAGE_PROJECTOR_VERSION
    analytical_view_version: str | None = None
    narrative_schema_version: str | None = None
    renderer_version: str | None = None
    ready_for_analysis: bool = True
    ready_for_publication: bool = False
    schema_version: str = STREAM_MESSAGE_INPUT_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.message_identity, "Stream message identity"),
            (self.source_event_identity, "Stream message source-event identity"),
            (self.stream_event_identity, "Stream message normalized-event identity"),
            (self.story_identity, "Stream message story identity"),
            (self.fact_bundle_identity, "Stream message fact-bundle identity"),
        ):
            _require_sha256(value, label)
        if self.supersedes_message_identity is not None:
            _require_sha256(
                self.supersedes_message_identity,
                "Stream superseded message identity",
            )
        for value, label in (
            (self.subtype, "Stream message subtype"),
            (self.asset, "Stream message asset"),
            (self.symbol, "Stream message symbol"),
            (self.market, "Stream message market"),
            (self.timeframe, "Stream message timeframe"),
            (self.projector_version, "Stream message projector version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.category, StreamCategory):
            raise TypeError("Stream message category must be canonical")
        if not isinstance(self.importance, StreamImportance):
            raise TypeError("Stream message importance must be canonical")
        if not isinstance(self.materiality, StreamMateriality):
            raise TypeError("Stream message materiality must be canonical")
        if min(self.event_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("Stream message timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("Stream message event cannot predate source-as-of")
        _require_identity_tuple(
            self.evidence_reference_identities,
            "Stream message evidence reference",
        )
        _require_identity_tuple(
            self.proof_reference_identities,
            "Stream message proof reference",
        )
        _require_identity_tuple(
            self.capital_reference_identities,
            "Stream message capital reference",
        )
        relation_keys = tuple(
            (item.kind.value, item.target_message_identity, item.reason_code)
            for item in self.relations
        )
        if relation_keys != tuple(sorted(set(relation_keys))):
            raise ValueError("Stream message relations must be unique and canonical")
        if self.supersedes_message_identity is not None and not any(
            relation.kind is StreamMessageRelationKind.SUPERSEDES
            and relation.target_message_identity == self.supersedes_message_identity
            for relation in self.relations
        ):
            raise ValueError("Stream supersession requires exact SUPERSEDES relation")
        if self.search_metadata.asset != self.asset:
            raise ValueError("Stream message/search asset mismatch")
        if self.search_metadata.symbol != self.symbol:
            raise ValueError("Stream message/search symbol mismatch")
        if self.search_metadata.market != self.market:
            raise ValueError("Stream message/search market mismatch")
        if self.search_metadata.timeframe != self.timeframe:
            raise ValueError("Stream message/search timeframe mismatch")
        if self.search_metadata.category is not self.category:
            raise ValueError("Stream message/search category mismatch")
        if self.search_metadata.importance is not self.importance:
            raise ValueError("Stream message/search importance mismatch")
        if self.materiality_policy_version != STREAM_MATERIALITY_POLICY_VERSION:
            raise ValueError("unsupported Stream materiality policy version")
        if self.projector_version != STREAM_MESSAGE_PROJECTOR_VERSION:
            raise ValueError("unsupported Stream message projector version")
        if any(
            value is not None
            for value in (
                self.analytical_view_version,
                self.narrative_schema_version,
                self.renderer_version,
            )
        ):
            raise ValueError("S2 message input cannot claim later-stage render versions")
        if not self.ready_for_analysis or self.ready_for_publication:
            raise ValueError("S2 message input must be analysis-ready, not publish-ready")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.message_identity != canonical_sha256(_message_input_payload(self)):
            raise ValueError("Stream message input identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamPublishedMessage:
    publication_identity: str
    message_identity: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    fact_bundle_identity: str
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    materiality: StreamMateriality
    materiality_policy_version: str
    asset: str
    symbol: str
    market: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    published_at_ms: int
    analytical_view_identity: str
    analytical_view_version: str
    narrative_plan_identity: str
    narrative_schema_version: str
    renderer_version: str
    collapsed_text: str
    simple_content: str
    pro_evidence_reference_identities: tuple[str, ...]
    capital_reference_identities: tuple[str, ...]
    relations: tuple[StreamMessageRelation, ...]
    search_metadata: StreamSearchMetadata
    original_publication_preserved: bool = True
    schema_version: str = STREAM_PUBLISHED_MESSAGE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.publication_identity, "Stream publication identity"),
            (self.message_identity, "Stream publication message identity"),
            (self.source_event_identity, "Stream publication source-event identity"),
            (self.stream_event_identity, "Stream publication normalized-event identity"),
            (self.story_identity, "Stream publication story identity"),
            (self.fact_bundle_identity, "Stream publication fact-bundle identity"),
            (self.analytical_view_identity, "Stream publication analytical-view identity"),
            (self.narrative_plan_identity, "Stream publication narrative-plan identity"),
        ):
            _require_sha256(value, label)
        for value, label in (
            (self.subtype, "Stream publication subtype"),
            (self.asset, "Stream publication asset"),
            (self.symbol, "Stream publication symbol"),
            (self.market, "Stream publication market"),
            (self.timeframe, "Stream publication timeframe"),
            (self.analytical_view_version, "Stream analytical-view version"),
            (self.narrative_schema_version, "Stream narrative schema version"),
            (self.renderer_version, "Stream renderer version"),
            (self.collapsed_text, "Stream collapsed text"),
            (self.simple_content, "Stream SIMPLE content"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.category, StreamCategory):
            raise TypeError("Stream publication category must be canonical")
        if not isinstance(self.importance, StreamImportance):
            raise TypeError("Stream publication importance must be canonical")
        if not isinstance(self.materiality, StreamMateriality):
            raise TypeError("Stream publication materiality must be canonical")
        if self.materiality_policy_version != STREAM_MATERIALITY_POLICY_VERSION:
            raise ValueError("unsupported Stream publication materiality policy")
        if min(self.event_at_ms, self.source_as_of_ms, self.published_at_ms) < 0:
            raise ValueError("Stream publication timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("Stream publication event cannot predate source-as-of")
        if self.published_at_ms < self.event_at_ms:
            raise ValueError("Stream publication cannot predate source event")
        _require_identity_tuple(
            self.pro_evidence_reference_identities,
            "Stream publication PRO evidence reference",
        )
        _require_identity_tuple(
            self.capital_reference_identities,
            "Stream publication capital reference",
        )
        relation_keys = tuple(
            (item.kind.value, item.target_message_identity, item.reason_code)
            for item in self.relations
        )
        if relation_keys != tuple(sorted(set(relation_keys))):
            raise ValueError("Stream publication relations must be canonical")
        if self.search_metadata.asset != self.asset:
            raise ValueError("Stream publication/search asset mismatch")
        if self.search_metadata.symbol != self.symbol:
            raise ValueError("Stream publication/search symbol mismatch")
        if self.search_metadata.market != self.market:
            raise ValueError("Stream publication/search market mismatch")
        if self.search_metadata.timeframe != self.timeframe:
            raise ValueError("Stream publication/search timeframe mismatch")
        if self.search_metadata.category is not self.category:
            raise ValueError("Stream publication/search category mismatch")
        if self.search_metadata.importance is not self.importance:
            raise ValueError("Stream publication/search importance mismatch")
        if not self.original_publication_preserved:
            raise ValueError("Stream original publication must remain preserved")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_PUBLISHED_MESSAGE_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.publication_identity != canonical_sha256(
            _published_message_payload(self)
        ):
            raise ValueError("Stream publication identity mismatch")


def build_published_message_record(
    message: StreamMessageInput,
    *,
    published_at_ms: int,
    analytical_view_identity: str,
    analytical_view_version: str,
    narrative_plan_identity: str,
    narrative_schema_version: str,
    renderer_version: str,
    collapsed_text: str,
    simple_content: str,
) -> StreamPublishedMessage:
    if message.ready_for_publication:
        raise ValueError("S2 message input must remain pre-publication")
    payload = {
        "analytical_view_identity": analytical_view_identity,
        "analytical_view_version": analytical_view_version,
        "asset": message.asset,
        "capital_reference_identities": message.capital_reference_identities,
        "category": message.category,
        "collapsed_text": collapsed_text,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": message.event_at_ms,
        "fact_bundle_identity": message.fact_bundle_identity,
        "importance": message.importance,
        "market": message.market,
        "materiality": message.materiality,
        "materiality_policy_version": message.materiality_policy_version,
        "message_identity": message.message_identity,
        "narrative_plan_identity": narrative_plan_identity,
        "narrative_schema_version": narrative_schema_version,
        "original_publication_preserved": True,
        "pro_evidence_reference_identities": message.evidence_reference_identities,
        "production_authority": False,
        "published_at_ms": published_at_ms,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "relations": message.relations,
        "renderer_version": renderer_version,
        "schema_version": STREAM_PUBLISHED_MESSAGE_SCHEMA_VERSION,
        "search_metadata": message.search_metadata,
        "simple_content": simple_content,
        "source_as_of_ms": message.source_as_of_ms,
        "source_event_identity": message.source_event_identity,
        "story_identity": message.story_identity,
        "stream_event_identity": message.stream_event_identity,
        "subtype": message.subtype,
        "symbol": message.symbol,
        "timeframe": message.timeframe,
    }
    return StreamPublishedMessage(
        publication_identity=canonical_sha256(payload),
        message_identity=message.message_identity,
        source_event_identity=message.source_event_identity,
        stream_event_identity=message.stream_event_identity,
        story_identity=message.story_identity,
        fact_bundle_identity=message.fact_bundle_identity,
        category=message.category,
        subtype=message.subtype,
        importance=message.importance,
        materiality=message.materiality,
        materiality_policy_version=message.materiality_policy_version,
        asset=message.asset,
        symbol=message.symbol,
        market=message.market,
        timeframe=message.timeframe,
        event_at_ms=message.event_at_ms,
        source_as_of_ms=message.source_as_of_ms,
        published_at_ms=published_at_ms,
        analytical_view_identity=analytical_view_identity,
        analytical_view_version=analytical_view_version,
        narrative_plan_identity=narrative_plan_identity,
        narrative_schema_version=narrative_schema_version,
        renderer_version=renderer_version,
        collapsed_text=collapsed_text,
        simple_content=simple_content,
        pro_evidence_reference_identities=message.evidence_reference_identities,
        capital_reference_identities=message.capital_reference_identities,
        relations=message.relations,
        search_metadata=message.search_metadata,
    )


def build_forecast_story_identity(forecast_identity: str) -> str:
    _require_sha256(forecast_identity, "Stream story forecast identity")
    return canonical_sha256(
        {
            "forecast_identity": forecast_identity,
            "namespace_version": STREAM_STORY_NAMESPACE_VERSION,
            "story_kind": "forecast",
        }
    )


def build_stream_fact_bundle(
    source_event: StreamSourceEvent,
    context: StreamDecisionContextSnapshot,
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    *,
    resolution: ForecastResolution | None = None,
) -> StreamFactBundle:
    if source_event.decision_context_identity != context.context_identity:
        raise ValueError("Stream fact source/context identity mismatch")
    if source_event.forecast_identity != forecast.forecast_identity:
        raise ValueError("Stream fact source/forecast identity mismatch")
    if source_event.proof_identity != proof.proof_identity:
        raise ValueError("Stream fact source/proof identity mismatch")
    if context.forecast_identity != forecast.forecast_identity:
        raise ValueError("Stream fact context/forecast identity mismatch")
    if context.proof_identity != proof.proof_identity:
        raise ValueError("Stream fact context/proof identity mismatch")
    if context.confluence_identity != forecast.confluence_identity:
        raise ValueError("Stream fact context/forecast M6 mismatch")
    if proof.confluence_identity != context.confluence_identity:
        raise ValueError("Stream fact proof/context M6 mismatch")
    if (
        source_event.asset,
        source_event.symbol,
        source_event.timeframe,
    ) != (forecast.asset, forecast.symbol, forecast.timeframe):
        raise ValueError("Stream fact source/forecast market mismatch")
    if (
        proof.confluence_support_score_0_100
        != forecast.confluence_support_score_0_100
        or context.confluence.support_score_0_100
        != forecast.confluence_support_score_0_100
        or proof.confluence_opposition_score_0_100
        != forecast.confluence_opposition_score_0_100
        or context.confluence.opposition_score_0_100
        != forecast.confluence_opposition_score_0_100
    ):
        raise ValueError("Stream fact confluence score lineage mismatch")

    if resolution is None:
        if source_event.resolution_identity is not None:
            raise ValueError("issuance Stream fact cannot carry resolution identity")
        if source_event.event_at_ms != forecast.issued_at_ms:
            raise ValueError("issuance Stream fact event time mismatch")
        resolution_identity = None
        source_outcome_identity = None
        resolution_state = None
        source_outcome_state = None
        outcome_evidence_class = None
        resolution_reason_codes: tuple[str, ...] = ()
    else:
        if resolution.forecast_identity != forecast.forecast_identity:
            raise ValueError("resolved Stream fact forecast lineage mismatch")
        if resolution.signal_freeze_identity != forecast.signal_freeze_identity:
            raise ValueError("resolved Stream fact signal lineage mismatch")
        if source_event.resolution_identity != resolution.resolution_identity:
            raise ValueError("resolved Stream fact source/resolution mismatch")
        if source_event.event_at_ms != resolution.evaluated_at_ms:
            raise ValueError("resolved Stream fact event time mismatch")
        resolution_identity = resolution.resolution_identity
        source_outcome_identity = resolution.source_outcome_identity
        resolution_state = resolution.state
        source_outcome_state = resolution.source_outcome_state
        outcome_evidence_class = resolution.evidence_class
        resolution_reason_codes = resolution.reason_codes

    available_domains = tuple(
        sorted(
            item.domain.value
            for item in proof.evidence_slices
            if item.availability is ProofEvidenceAvailability.AVAILABLE
        )
    )
    story_identity = build_forecast_story_identity(forecast.forecast_identity)
    payload = {
        "asset": forecast.asset,
        "available_evidence_domains": available_domains,
        "calibrated_probability_0_1": proof.calibrated_probability_0_1,
        "confluence_opposition_score_0_100": (
            forecast.confluence_opposition_score_0_100
        ),
        "confluence_resolution": context.confluence.resolution,
        "confluence_support_score_0_100": forecast.confluence_support_score_0_100,
        "decision_context_identity": context.context_identity,
        "decision_source_as_of_ms": forecast.source_as_of_ms,
        "decision_state": proof.signal_state,
        "direction": proof.direction,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": source_event.event_at_ms,
        "event_context_state": proof.event_context_state,
        "evidence_summary": proof.evidence_summary,
        "family_contributions": context.confluence.contributions,
        "forecast_identity": forecast.forecast_identity,
        "freshness_0_1": proof.freshness_0_1,
        "invalidation_price": proof.invalidation_price,
        "market": forecast.symbol,
        "outcome_evidence_class": outcome_evidence_class,
        "probability_status": proof.probability_status,
        "production_authority": False,
        "proof_identity": proof.proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": resolution_identity,
        "resolution_reason_codes": resolution_reason_codes,
        "resolution_state": resolution_state,
        "schema_version": STREAM_FACT_BUNDLE_SCHEMA_VERSION,
        "source_as_of_ms": source_event.source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "source_outcome_identity": source_outcome_identity,
        "source_outcome_state": source_outcome_state,
        "story_identity": story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "symbol": forecast.symbol,
        "target_zone": proof.target_zone,
        "timeframe": forecast.timeframe,
        "trigger_zone": proof.trigger_zone,
        "uncertainty_flags": proof.uncertainty_flags,
    }
    return StreamFactBundle(
        fact_bundle_identity=canonical_sha256(payload),
        stream_event_identity=source_event.stream_event_identity,
        source_event_identity=source_event.source_event_identity,
        story_identity=story_identity,
        decision_context_identity=context.context_identity,
        forecast_identity=forecast.forecast_identity,
        proof_identity=proof.proof_identity,
        resolution_identity=resolution_identity,
        source_outcome_identity=source_outcome_identity,
        asset=forecast.asset,
        symbol=forecast.symbol,
        market=forecast.symbol,
        timeframe=forecast.timeframe,
        event_at_ms=source_event.event_at_ms,
        source_as_of_ms=source_event.source_as_of_ms,
        decision_source_as_of_ms=forecast.source_as_of_ms,
        decision_state=proof.signal_state,
        direction=proof.direction,
        confluence_support_score_0_100=forecast.confluence_support_score_0_100,
        confluence_opposition_score_0_100=(
            forecast.confluence_opposition_score_0_100
        ),
        confluence_resolution=context.confluence.resolution,
        family_contributions=context.confluence.contributions,
        event_context_state=proof.event_context_state,
        trigger_zone=proof.trigger_zone,
        target_zone=proof.target_zone,
        invalidation_price=proof.invalidation_price,
        probability_status=proof.probability_status,
        calibrated_probability_0_1=proof.calibrated_probability_0_1,
        freshness_0_1=proof.freshness_0_1,
        uncertainty_flags=proof.uncertainty_flags,
        available_evidence_domains=available_domains,
        evidence_summary=proof.evidence_summary,
        resolution_state=resolution_state,
        source_outcome_state=source_outcome_state,
        outcome_evidence_class=outcome_evidence_class,
        resolution_reason_codes=resolution_reason_codes,
    )


def build_stream_message_input(
    source_event: StreamSourceEvent,
    fact_bundle: StreamFactBundle,
    *,
    relations: tuple[StreamMessageRelation, ...] = (),
    supersedes_message_identity: str | None = None,
    capital_reference_identities: tuple[str, ...] = (),
) -> StreamMessageInput:
    if fact_bundle.stream_event_identity != source_event.stream_event_identity:
        raise ValueError("Stream message fact/source normalized-event mismatch")
    if fact_bundle.source_event_identity != source_event.source_event_identity:
        raise ValueError("Stream message fact/source event mismatch")
    if fact_bundle.event_at_ms != source_event.event_at_ms:
        raise ValueError("Stream message fact/source event-time mismatch")
    if fact_bundle.source_as_of_ms != source_event.source_as_of_ms:
        raise ValueError("Stream message fact/source cutoff mismatch")
    if (
        fact_bundle.asset,
        fact_bundle.symbol,
        fact_bundle.timeframe,
    ) != (source_event.asset, source_event.symbol, source_event.timeframe):
        raise ValueError("Stream message fact/source market mismatch")

    ordered_relations = tuple(
        sorted(
            relations,
            key=lambda item: (
                item.kind.value,
                item.target_message_identity,
                item.reason_code,
            ),
        )
    )
    capital_refs = tuple(sorted(set(capital_reference_identities)))
    for identity in capital_refs:
        _require_sha256(identity, "Stream message capital reference")

    proof_refs = tuple(
        sorted(
            {
                fact_bundle.decision_context_identity,
                fact_bundle.forecast_identity,
                fact_bundle.proof_identity,
                *(
                    ()
                    if fact_bundle.resolution_identity is None
                    else (fact_bundle.resolution_identity,)
                ),
            }
        )
    )
    evidence_refs = tuple(sorted(set(source_event.evidence_identities)))
    states = {
        fact_bundle.decision_state,
        fact_bundle.event_context_state,
        fact_bundle.confluence_resolution.value,
    }
    if fact_bundle.resolution_state is not None:
        states.add(fact_bundle.resolution_state.value)
    if fact_bundle.source_outcome_state is not None:
        states.add(fact_bundle.source_outcome_state.value)
    ordered_states = tuple(sorted(states))
    search_terms = tuple(
        sorted(
            {
                fact_bundle.asset.lower(),
                fact_bundle.symbol.lower(),
                fact_bundle.market.lower(),
                fact_bundle.timeframe.lower(),
                source_event.category.value,
                source_event.subtype,
                source_event.importance.value,
                fact_bundle.direction.lower(),
                *(value.lower() for value in ordered_states),
            }
        )
    )
    search = StreamSearchMetadata(
        asset=fact_bundle.asset,
        symbol=fact_bundle.symbol,
        market=fact_bundle.market,
        timeframe=fact_bundle.timeframe,
        category=source_event.category,
        importance=source_event.importance,
        evidence_domains=fact_bundle.available_evidence_domains,
        states=ordered_states,
        vaults=(),
        search_terms=search_terms,
    )
    materiality = (
        StreamMateriality.ROUTINE
        if source_event.category is StreamCategory.ROUTINE
        or source_event.importance is StreamImportance.ROUTINE
        else StreamMateriality.MATERIAL
    )
    payload = {
        "analytical_view_version": None,
        "asset": fact_bundle.asset,
        "capital_reference_identities": capital_refs,
        "category": source_event.category,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": source_event.event_at_ms,
        "evidence_reference_identities": evidence_refs,
        "fact_bundle_identity": fact_bundle.fact_bundle_identity,
        "importance": source_event.importance,
        "market": fact_bundle.market,
        "materiality": materiality,
        "materiality_policy_version": STREAM_MATERIALITY_POLICY_VERSION,
        "narrative_schema_version": None,
        "production_authority": False,
        "projector_version": STREAM_MESSAGE_PROJECTOR_VERSION,
        "proof_reference_identities": proof_refs,
        "read_only": True,
        "ready_for_analysis": True,
        "ready_for_publication": False,
        "real_capital": REAL_CAPITAL,
        "relations": ordered_relations,
        "renderer_version": None,
        "schema_version": STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
        "search_metadata": search,
        "source_as_of_ms": source_event.source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "story_identity": fact_bundle.story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": source_event.subtype,
        "supersedes_message_identity": supersedes_message_identity,
        "symbol": fact_bundle.symbol,
        "timeframe": fact_bundle.timeframe,
    }
    return StreamMessageInput(
        message_identity=canonical_sha256(payload),
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        story_identity=fact_bundle.story_identity,
        fact_bundle_identity=fact_bundle.fact_bundle_identity,
        category=source_event.category,
        subtype=source_event.subtype,
        importance=source_event.importance,
        materiality=materiality,
        asset=fact_bundle.asset,
        symbol=fact_bundle.symbol,
        market=fact_bundle.market,
        timeframe=fact_bundle.timeframe,
        event_at_ms=source_event.event_at_ms,
        source_as_of_ms=source_event.source_as_of_ms,
        evidence_reference_identities=evidence_refs,
        proof_reference_identities=proof_refs,
        capital_reference_identities=capital_refs,
        relations=ordered_relations,
        supersedes_message_identity=supersedes_message_identity,
        search_metadata=search,
        materiality_policy_version=STREAM_MATERIALITY_POLICY_VERSION,
    )


def build_resolution_relation(
    issuance_message: StreamMessageInput,
) -> StreamMessageRelation:
    return StreamMessageRelation(
        kind=StreamMessageRelationKind.RESOLVES,
        target_message_identity=issuance_message.message_identity,
        reason_code="forecast_resolution_preserves_original_issuance",
    )


def fact_bundle_payload(value: StreamFactBundle) -> dict[str, object]:
    return _fact_bundle_payload(value)


def message_input_payload(value: StreamMessageInput) -> dict[str, object]:
    return _message_input_payload(value)


def _fact_bundle_payload(value: StreamFactBundle) -> dict[str, object]:
    return {
        "asset": value.asset,
        "available_evidence_domains": value.available_evidence_domains,
        "calibrated_probability_0_1": value.calibrated_probability_0_1,
        "confluence_opposition_score_0_100": value.confluence_opposition_score_0_100,
        "confluence_resolution": value.confluence_resolution,
        "confluence_support_score_0_100": value.confluence_support_score_0_100,
        "decision_context_identity": value.decision_context_identity,
        "decision_source_as_of_ms": value.decision_source_as_of_ms,
        "decision_state": value.decision_state,
        "direction": value.direction,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "event_context_state": value.event_context_state,
        "evidence_summary": value.evidence_summary,
        "family_contributions": value.family_contributions,
        "forecast_identity": value.forecast_identity,
        "freshness_0_1": value.freshness_0_1,
        "invalidation_price": value.invalidation_price,
        "market": value.market,
        "outcome_evidence_class": value.outcome_evidence_class,
        "probability_status": value.probability_status,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "resolution_identity": value.resolution_identity,
        "resolution_reason_codes": value.resolution_reason_codes,
        "resolution_state": value.resolution_state,
        "schema_version": value.schema_version,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
        "source_outcome_identity": value.source_outcome_identity,
        "source_outcome_state": value.source_outcome_state,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "target_zone": value.target_zone,
        "timeframe": value.timeframe,
        "trigger_zone": value.trigger_zone,
        "uncertainty_flags": value.uncertainty_flags,
    }


def _message_input_payload(value: StreamMessageInput) -> dict[str, object]:
    return {
        "analytical_view_version": value.analytical_view_version,
        "asset": value.asset,
        "capital_reference_identities": value.capital_reference_identities,
        "category": value.category,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "evidence_reference_identities": value.evidence_reference_identities,
        "fact_bundle_identity": value.fact_bundle_identity,
        "importance": value.importance,
        "market": value.market,
        "materiality": value.materiality,
        "materiality_policy_version": value.materiality_policy_version,
        "narrative_schema_version": value.narrative_schema_version,
        "production_authority": value.production_authority,
        "projector_version": value.projector_version,
        "proof_reference_identities": value.proof_reference_identities,
        "read_only": value.read_only,
        "ready_for_analysis": value.ready_for_analysis,
        "ready_for_publication": value.ready_for_publication,
        "real_capital": value.real_capital,
        "relations": value.relations,
        "renderer_version": value.renderer_version,
        "schema_version": value.schema_version,
        "search_metadata": value.search_metadata,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "supersedes_message_identity": value.supersedes_message_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
    }


def published_message_payload(
    value: StreamPublishedMessage,
) -> dict[str, object]:
    return _published_message_payload(value)


def _published_message_payload(
    value: StreamPublishedMessage,
) -> dict[str, object]:
    return {
        "analytical_view_identity": value.analytical_view_identity,
        "analytical_view_version": value.analytical_view_version,
        "asset": value.asset,
        "capital_reference_identities": value.capital_reference_identities,
        "category": value.category,
        "collapsed_text": value.collapsed_text,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "importance": value.importance,
        "market": value.market,
        "materiality": value.materiality,
        "materiality_policy_version": value.materiality_policy_version,
        "message_identity": value.message_identity,
        "narrative_plan_identity": value.narrative_plan_identity,
        "narrative_schema_version": value.narrative_schema_version,
        "original_publication_preserved": value.original_publication_preserved,
        "pro_evidence_reference_identities": value.pro_evidence_reference_identities,
        "production_authority": value.production_authority,
        "published_at_ms": value.published_at_ms,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "relations": value.relations,
        "renderer_version": value.renderer_version,
        "schema_version": value.schema_version,
        "search_metadata": value.search_metadata,
        "simple_content": value.simple_content,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
    }


def _require_common_authority(
    *,
    schema_version: str,
    expected_schema: str,
    engine_version: str,
    read_only: bool,
    production_authority: bool,
    real_capital: int,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("unsupported Stream message schema version")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream message engine version")
    if not read_only:
        raise ValueError("Stream message truth must remain read-only")
    if production_authority:
        raise ValueError("Stream message truth cannot grant production authority")
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
