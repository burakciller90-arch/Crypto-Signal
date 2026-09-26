from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.forecast_stream import ForecastResolution, ImmutableForecast
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyContribution,
    ConfluenceMatrixResolution,
    ConfluenceMatrixSnapshot,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.product.decision_proof import (
    DecisionProofSnapshot,
    build_live_intelligence_feed_event,
)
from crypto_signal.product.intelligence_stream_analytical import (
    StreamAnalyticalPublicationDisposition,
    build_stream_analytical_policy,
    compose_stream_analytical_view,
)
from crypto_signal.product.intelligence_stream_analytical_ledger import (
    IntelligenceStreamAnalyticalLedger,
)
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
    StreamLedgerConflictError,
)
from crypto_signal.product.intelligence_stream_message_ledger import (
    IntelligenceStreamMessageLedger,
)
from crypto_signal.product.intelligence_stream_messages import (
    StreamMessageRelation,
    StreamMessageRelationKind,
    build_forecast_story_identity,
    build_stream_fact_bundle,
    build_stream_message_input,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamActivationBoundary,
    StreamDecisionContextSnapshot,
    build_forecast_resolved_source_event,
    build_stream_activation_boundary,
    build_stream_decision_context,
)
from crypto_signal.product.intelligence_stream_narrative import (
    build_stream_narrative_plan,
    render_stream_narrative,
)
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)
from crypto_signal.product.intelligence_stream_projectors import (
    project_forecast_issuance,
)
from crypto_signal.product.intelligence_stream_story import (
    StreamStoryState,
    build_change_set,
    build_story_observation,
    build_story_state,
)
from crypto_signal.product.intelligence_stream_story_ledger import (
    IntelligenceStreamStoryLedger,
)
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

REAL_CAPITAL = 0


class StreamForwardProjectionDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"
    SKIPPED_BEFORE_ACTIVATION = "skipped_before_activation"
    SKIPPED_NO_FORWARD_ISSUANCE = "skipped_no_forward_issuance"
    SILENT = "silent"


@dataclass(frozen=True, slots=True)
class StreamForwardProjectionResult:
    disposition: StreamForwardProjectionDisposition
    forecast_identity: str
    narrative_identity: str | None
    activation_identity: str
    historical_backfill_performed: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.historical_backfill_performed:
            raise ValueError("Stream forward runtime cannot backfill history")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("Stream forward runtime crossed authority boundary")


class IntelligenceStreamForwardRuntime:
    """Forward-only Product projector for accepted same-cycle decision truth.

    The runtime never reconstructs historical rich messages. The first explicit
    activation boundary is immutable; only forecast events at or after that
    boundary may become Stream narratives.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.source_ledger = IntelligenceStreamLedger(path)
        self.message_ledger = IntelligenceStreamMessageLedger(path)
        self.story_ledger = IntelligenceStreamStoryLedger(path)
        self.analytical_ledger = IntelligenceStreamAnalyticalLedger(path)
        self.narrative_ledger = IntelligenceStreamNarrativeLedger(path)

    def ensure_activated(self, *, activated_at_ms: int) -> StreamActivationBoundary:
        if activated_at_ms < 0:
            raise ValueError("Stream activation time must be non-negative")

        # Initialize the complete read-model schema before Product reads begin.
        self.narrative_ledger.initialize()
        try:
            raw = self.source_ledger.read_activation()
        except StreamLedgerConflictError as exc:
            if "requires exactly one activation boundary" not in str(exc):
                raise
            activation = build_stream_activation_boundary(
                activated_at_ms=activated_at_ms
            )
            self.source_ledger.append_activation(activation)
            return activation
        return _activation_from_record(raw)

    def activation(self) -> StreamActivationBoundary:
        return _activation_from_record(self.source_ledger.read_activation())

    def project_issuance(
        self,
        issuance: UnifiedDecisionIssuance,
    ) -> StreamForwardProjectionResult:
        activation = self.activation()
        forecast = issuance.forecast
        if forecast.issued_at_ms < activation.activated_at_ms:
            return StreamForwardProjectionResult(
                disposition=StreamForwardProjectionDisposition.SKIPPED_BEFORE_ACTIVATION,
                forecast_identity=forecast.forecast_identity,
                narrative_identity=None,
                activation_identity=activation.activation_identity,
            )

        context = build_stream_decision_context(
            forecast,
            issuance.proof,
            issuance.confluence,
        )
        projected = project_forecast_issuance(
            activation,
            context,
            forecast,
            issuance.proof,
            issuance.feed_event,
        )

        source_disposition = self.source_ledger.append_issuance_bundle(
            context,
            projected.source_event,
        )
        message_disposition = self.message_ledger.append_message_bundle(
            projected.fact_bundle,
            projected.message_input,
        )

        observation = build_story_observation(
            projected.message_input,
            projected.fact_bundle,
            previous_state_identity=None,
        )
        state = build_story_state(observation)
        change_set = build_change_set(state)
        story_disposition = self.story_ledger.append_transition(
            observation,
            state,
            change_set,
        )

        view = compose_stream_analytical_view(
            build_stream_analytical_policy(),
            projected.fact_bundle,
            state,
            change_set,
            message=projected.message_input,
        )
        analytical_disposition = self.analytical_ledger.append_view(view)

        if (
            view.materiality.disposition
            is not StreamAnalyticalPublicationDisposition.PUBLISH
        ):
            return StreamForwardProjectionResult(
                disposition=StreamForwardProjectionDisposition.SILENT,
                forecast_identity=forecast.forecast_identity,
                narrative_identity=None,
                activation_identity=activation.activation_identity,
            )

        plan = build_stream_narrative_plan(
            view,
            projected.fact_bundle,
            change_set,
        )
        narrative = render_stream_narrative(
            plan,
            view,
            projected.fact_bundle,
            change_set,
        )
        narrative_disposition = self.narrative_ledger.append_narrative(
            plan,
            narrative,
        )

        dispositions = {
            source_disposition.value,
            message_disposition.value,
            story_disposition.value,
            analytical_disposition.value,
            narrative_disposition.value,
        }
        disposition = (
            StreamForwardProjectionDisposition.UNCHANGED
            if dispositions == {"unchanged"}
            else StreamForwardProjectionDisposition.INSERTED
        )
        return StreamForwardProjectionResult(
            disposition=disposition,
            forecast_identity=forecast.forecast_identity,
            narrative_identity=narrative.narrative_identity,
            activation_identity=activation.activation_identity,
        )



    def project_resolution(
        self,
        forecast: ImmutableForecast,
        proof: DecisionProofSnapshot,
        resolution: ForecastResolution,
    ) -> StreamForwardProjectionResult:
        activation = self.activation()
        context_raw = self.source_ledger.read_context_for_forecast(
            forecast.forecast_identity
        )
        if context_raw is None:
            return StreamForwardProjectionResult(
                disposition=(
                    StreamForwardProjectionDisposition.SKIPPED_NO_FORWARD_ISSUANCE
                ),
                forecast_identity=forecast.forecast_identity,
                narrative_identity=None,
                activation_identity=activation.activation_identity,
            )
        context = _context_from_record(context_raw)
        if context.forecast_identity != forecast.forecast_identity:
            raise ValueError("Stream resolution context/forecast mismatch")
        if context.proof_identity != proof.proof_identity:
            raise ValueError("Stream resolution context/proof mismatch")

        feed_event = build_live_intelligence_feed_event(
            proof,
            forecast,
            resolution=resolution,
        )
        source_event = build_forecast_resolved_source_event(
            activation,
            context,
            feed_event,
            resolution,
        )
        story_identity = build_forecast_story_identity(
            forecast.forecast_identity
        )

        existing_messages = self.message_ledger.read_story(story_identity)
        existing_resolution = tuple(
            item
            for item in existing_messages
            if item.get("stream_event_identity")
            == source_event.stream_event_identity
        )
        if existing_resolution:
            if len(existing_resolution) != 1:
                raise ValueError("Stream resolution replay found duplicate message")
            narratives = self.narrative_ledger.read_story(story_identity)
            existing_narrative = tuple(
                item
                for item in narratives
                if item.get("stream_event_identity")
                == source_event.stream_event_identity
            )
            if len(existing_narrative) != 1:
                raise ValueError(
                    "Stream resolution replay lost exact narrative identity"
                )
            return StreamForwardProjectionResult(
                disposition=StreamForwardProjectionDisposition.UNCHANGED,
                forecast_identity=forecast.forecast_identity,
                narrative_identity=str(
                    existing_narrative[0]["narrative_identity"]
                ),
                activation_identity=activation.activation_identity,
            )

        issuance_messages = tuple(
            item
            for item in existing_messages
            if item.get("subtype") == "forecast_issued"
        )
        if len(issuance_messages) != 1:
            raise ValueError(
                "Stream resolution requires exactly one forward issuance message"
            )
        issuance_message_identity = _text_field(
            issuance_messages[0],
            "message_identity",
        )

        fact_bundle = build_stream_fact_bundle(
            source_event,
            context,
            forecast,
            proof,
            resolution=resolution,
        )
        relation = StreamMessageRelation(
            kind=StreamMessageRelationKind.RESOLVES,
            target_message_identity=issuance_message_identity,
            reason_code="forecast_resolution_preserves_original_issuance",
        )
        message_input = build_stream_message_input(
            source_event,
            fact_bundle,
            relations=(relation,),
        )

        previous_raw = self.story_ledger.read_latest_state(story_identity)
        if previous_raw is None:
            raise ValueError("Stream resolution requires prior story state")
        previous_state = _story_state_from_record(previous_raw)

        source_disposition = self.source_ledger.append_source_event(
            source_event
        )
        message_disposition = self.message_ledger.append_message_bundle(
            fact_bundle,
            message_input,
        )
        observation = build_story_observation(
            message_input,
            fact_bundle,
            previous_state_identity=previous_state.state_identity,
        )
        state = build_story_state(
            observation,
            previous_state=previous_state,
        )
        change_set = build_change_set(
            state,
            previous_state=previous_state,
        )
        story_disposition = self.story_ledger.append_transition(
            observation,
            state,
            change_set,
        )

        view = compose_stream_analytical_view(
            build_stream_analytical_policy(),
            fact_bundle,
            state,
            change_set,
            message=message_input,
        )
        analytical_disposition = self.analytical_ledger.append_view(view)
        if (
            view.materiality.disposition
            is not StreamAnalyticalPublicationDisposition.PUBLISH
        ):
            return StreamForwardProjectionResult(
                disposition=StreamForwardProjectionDisposition.SILENT,
                forecast_identity=forecast.forecast_identity,
                narrative_identity=None,
                activation_identity=activation.activation_identity,
            )

        plan = build_stream_narrative_plan(
            view,
            fact_bundle,
            change_set,
        )
        narrative = render_stream_narrative(
            plan,
            view,
            fact_bundle,
            change_set,
        )
        narrative_disposition = self.narrative_ledger.append_narrative(
            plan,
            narrative,
        )
        dispositions = {
            source_disposition.value,
            message_disposition.value,
            story_disposition.value,
            analytical_disposition.value,
            narrative_disposition.value,
        }
        disposition = (
            StreamForwardProjectionDisposition.UNCHANGED
            if dispositions == {"unchanged"}
            else StreamForwardProjectionDisposition.INSERTED
        )
        return StreamForwardProjectionResult(
            disposition=disposition,
            forecast_identity=forecast.forecast_identity,
            narrative_identity=narrative.narrative_identity,
            activation_identity=activation.activation_identity,
        )


def _context_from_record(raw: dict[str, object]) -> StreamDecisionContextSnapshot:
    confluence_raw = _mapping_value(raw.get("confluence"), "Stream confluence")
    confluence = _confluence_from_record(confluence_raw)
    return StreamDecisionContextSnapshot(
        context_identity=_text_field(raw, "context_identity"),
        forecast_identity=_text_field(raw, "forecast_identity"),
        proof_identity=_text_field(raw, "proof_identity"),
        signal_freeze_identity=_text_field(raw, "signal_freeze_identity"),
        confluence_identity=_text_field(raw, "confluence_identity"),
        event_context_identity=_text_field(raw, "event_context_identity"),
        asset=_text_field(raw, "asset"),
        symbol=_text_field(raw, "symbol"),
        timeframe=_text_field(raw, "timeframe"),
        source_as_of_ms=_int_field(raw, "source_as_of_ms"),
        issued_at_ms=_int_field(raw, "issued_at_ms"),
        confluence=confluence,
        proof_slice_identities=_text_tuple_value(
            raw.get("proof_slice_identities"),
            "Stream proof slice identities",
        ),
        forecast_source_evidence_identities=_text_tuple_value(
            raw.get("forecast_source_evidence_identities"),
            "Stream forecast source identities",
        ),
        schema_version=_text_field(raw, "schema_version"),
        engine_version=_text_field(raw, "engine_version"),
        read_only=_bool_field(raw, "read_only"),
        production_authority=_bool_field(raw, "production_authority"),
        real_capital=_int_field(raw, "real_capital"),
    )


def _confluence_from_record(raw: dict[str, object]) -> ConfluenceMatrixSnapshot:
    contributions_raw = _list_value(
        raw.get("contributions"),
        "Stream confluence contributions",
    )
    contributions = tuple(
        _contribution_from_record(
            _mapping_value(item, "Stream confluence contribution")
        )
        for item in contributions_raw
    )
    return ConfluenceMatrixSnapshot(
        snapshot_identity=_text_field(raw, "snapshot_identity"),
        engine_version=_text_field(raw, "engine_version"),
        policy_identity=_text_field(raw, "policy_identity"),
        asset=_text_field(raw, "asset"),
        timeframe=_text_field(raw, "timeframe"),
        regime=_text_field(raw, "regime"),
        as_of_ms=_int_field(raw, "as_of_ms"),
        candidate_direction=MetaDirection(
            _text_field(raw, "candidate_direction")
        ),
        family_evidence_identities=_text_tuple_value(
            raw.get("family_evidence_identities"),
            "Stream family evidence identities",
        ),
        contributions=contributions,
        support_score_0_100=_decimal_field(raw, "support_score_0_100"),
        opposition_score_0_100=_decimal_field(
            raw,
            "opposition_score_0_100",
        ),
        evidence_coverage_0_100=_decimal_field(
            raw,
            "evidence_coverage_0_100",
        ),
        evidence_quality_0_1=_optional_decimal_value(
            raw.get("evidence_quality_0_1"),
            "Stream confluence evidence quality",
        ),
        freshness_0_1=_optional_decimal_value(
            raw.get("freshness_0_1"),
            "Stream confluence freshness",
        ),
        material_conflict_identities=_text_tuple_value(
            raw.get("material_conflict_identities"),
            "Stream material conflict identities",
        ),
        resolution=ConfluenceMatrixResolution(
            _text_field(raw, "resolution")
        ),
        threshold_hypotheses=tuple(
            _decimal_value(item, "Stream threshold hypothesis")
            for item in _list_value(
                raw.get("threshold_hypotheses"),
                "Stream threshold hypotheses",
            )
        ),
        score_semantic=_text_field(raw, "score_semantic"),
        probability_status=_text_field(raw, "probability_status"),
        event_risk_outside_matrix=_bool_field(
            raw,
            "event_risk_outside_matrix",
        ),
        automatic_activation=_bool_field(raw, "automatic_activation"),
        production_authority=_bool_field(raw, "production_authority"),
        real_capital=_int_field(raw, "real_capital"),
    )


def _contribution_from_record(
    raw: dict[str, object],
) -> ConfluenceFamilyContribution:
    direction_raw = raw.get("direction")
    direction = (
        None
        if direction_raw is None
        else MetaDirection(_text_value(direction_raw, "Stream family direction"))
    )
    return ConfluenceFamilyContribution(
        family=ConfluenceFamily(_text_field(raw, "family")),
        state=MetaEvidenceState(_text_field(raw, "state")),
        direction=direction,
        prior_weight=_decimal_field(raw, "prior_weight"),
        directional_strength_0_1=_optional_decimal_value(
            raw.get("directional_strength_0_1"),
            "Stream family directional strength",
        ),
        support_points=_decimal_field(raw, "support_points"),
        opposition_points=_decimal_field(raw, "opposition_points"),
        evidence_quality_0_1=_optional_decimal_value(
            raw.get("evidence_quality_0_1"),
            "Stream family evidence quality",
        ),
        freshness_0_1=_optional_decimal_value(
            raw.get("freshness_0_1"),
            "Stream family freshness",
        ),
        material_conflict_count=_int_field(
            raw,
            "material_conflict_count",
        ),
        source_evidence_identities=_text_tuple_value(
            raw.get("source_evidence_identities"),
            "Stream family source identities",
        ),
    )


def _story_state_from_record(raw: dict[str, object]) -> StreamStoryState:
    contributions = tuple(
        _contribution_from_record(
            _mapping_value(item, "Stream story contribution")
        )
        for item in _list_value(
            raw.get("family_contributions"),
            "Stream story contributions",
        )
    )
    return StreamStoryState(
        state_identity=_text_field(raw, "state_identity"),
        story_identity=_text_field(raw, "story_identity"),
        observation_identity=_text_field(raw, "observation_identity"),
        source_event_identity=_text_field(raw, "source_event_identity"),
        current_stream_event_identity=_text_field(
            raw,
            "current_stream_event_identity",
        ),
        current_message_identity=_optional_text_value(
            raw.get("current_message_identity"),
            "Stream current message identity",
        ),
        previous_state_identity=_optional_text_value(
            raw.get("previous_state_identity"),
            "Stream previous state identity",
        ),
        previous_message_identity=_optional_text_value(
            raw.get("previous_message_identity"),
            "Stream previous message identity",
        ),
        asset=_text_field(raw, "asset"),
        symbol=_text_field(raw, "symbol"),
        timeframe=_text_field(raw, "timeframe"),
        event_at_ms=_int_field(raw, "event_at_ms"),
        decision_state=_text_field(raw, "decision_state"),
        direction=_text_field(raw, "direction"),
        source_stance_key=_text_field(raw, "source_stance_key"),
        support_score_0_100=_decimal_field(raw, "support_score_0_100"),
        opposition_score_0_100=_decimal_field(
            raw,
            "opposition_score_0_100",
        ),
        family_contributions=contributions,
        event_risk_state=_text_field(raw, "event_risk_state"),
        trigger_state=_optional_text_value(
            raw.get("trigger_state"),
            "Stream trigger state",
        ),
        capital_reference_identities=_text_tuple_value(
            raw.get("capital_reference_identities"),
            "Stream capital reference identities",
        ),
        outcome_state=_optional_text_value(
            raw.get("outcome_state"),
            "Stream outcome state",
        ),
        schema_version=_text_field(raw, "schema_version"),
        engine_version=_text_field(raw, "engine_version"),
        read_only=_bool_field(raw, "read_only"),
        production_authority=_bool_field(raw, "production_authority"),
        real_capital=_int_field(raw, "real_capital"),
    )


def _mapping_value(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be object")
    return {str(key): item for key, item in value.items()}


def _list_value(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be array")
    return value


def _text_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be non-empty text")
    return value


def _optional_text_value(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text_value(value, label)


def _text_tuple_value(value: object, label: str) -> tuple[str, ...]:
    return tuple(
        _text_value(item, label)
        for item in _list_value(value, label)
    )


def _decimal_value(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise TypeError(f"{label} must be decimal-compatible")
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:
        raise TypeError(f"{label} must be decimal-compatible") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _optional_decimal_value(value: object, label: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal_value(value, label)


def _decimal_field(raw: dict[str, object], key: str) -> Decimal:
    return _decimal_value(raw.get(key), f"Stream {key}")


def _activation_from_record(raw: dict[str, object]) -> StreamActivationBoundary:
    return StreamActivationBoundary(
        activation_identity=_text_field(raw, "activation_identity"),
        activated_at_ms=_int_field(raw, "activated_at_ms"),
        activation_label=_text_field(raw, "activation_label"),
        historical_rich_backfill_allowed=_bool_field(
            raw,
            "historical_rich_backfill_allowed",
        ),
        schema_version=_text_field(raw, "schema_version"),
        engine_version=_text_field(raw, "engine_version"),
        read_only=_bool_field(raw, "read_only"),
        production_authority=_bool_field(raw, "production_authority"),
        real_capital=_int_field(raw, "real_capital"),
    )


def _text_field(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Stream activation {key} must be non-empty text")
    return value


def _int_field(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Stream activation {key} must be integer")
    return value


def _bool_field(raw: dict[str, object], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Stream activation {key} must be boolean")
    return value
