from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.forecast_stream import ForecastResolution, ImmutableForecast
from crypto_signal.product.decision_proof import (
    DecisionProofSnapshot,
    LiveIntelligenceFeedEvent,
)
from crypto_signal.product.intelligence_stream_messages import (
    StreamFactBundle,
    StreamMessageInput,
    build_forecast_story_identity,
    build_resolution_relation,
    build_stream_fact_bundle,
    build_stream_message_input,
)
from crypto_signal.product.intelligence_stream_models import (
    StreamActivationBoundary,
    StreamDecisionContextSnapshot,
    StreamSourceEvent,
    build_forecast_issued_source_event,
    build_forecast_resolved_source_event,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamProjectorImplementationState,
    accepted_stream_projector_registry,
)


@dataclass(frozen=True, slots=True)
class StreamProjectedMessage:
    source_event: StreamSourceEvent
    fact_bundle: StreamFactBundle
    message_input: StreamMessageInput

    def __post_init__(self) -> None:
        if (
            self.fact_bundle.stream_event_identity
            != self.source_event.stream_event_identity
        ):
            raise ValueError("Stream projection source/fact mismatch")
        if (
            self.message_input.stream_event_identity
            != self.source_event.stream_event_identity
        ):
            raise ValueError("Stream projection source/message mismatch")
        if (
            self.message_input.fact_bundle_identity
            != self.fact_bundle.fact_bundle_identity
        ):
            raise ValueError("Stream projection fact/message mismatch")
        if self.message_input.story_identity != self.fact_bundle.story_identity:
            raise ValueError("Stream projection story mismatch")


def project_forecast_issuance(
    activation: StreamActivationBoundary,
    context: StreamDecisionContextSnapshot,
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    feed_event: LiveIntelligenceFeedEvent,
) -> StreamProjectedMessage:
    _require_implemented_projector("r20_5_forecast_issued")
    source_event = build_forecast_issued_source_event(
        activation,
        context,
        feed_event,
    )
    fact_bundle = build_stream_fact_bundle(
        source_event,
        context,
        forecast,
        proof,
    )
    message_input = build_stream_message_input(source_event, fact_bundle)
    return StreamProjectedMessage(
        source_event=source_event,
        fact_bundle=fact_bundle,
        message_input=message_input,
    )


def project_forecast_resolution(
    activation: StreamActivationBoundary,
    context: StreamDecisionContextSnapshot,
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    feed_event: LiveIntelligenceFeedEvent,
    resolution: ForecastResolution,
    *,
    issuance_message: StreamMessageInput,
) -> StreamProjectedMessage:
    _require_implemented_projector("r20_5_forecast_resolved")
    if issuance_message.story_identity != build_forecast_story_identity(
        forecast.forecast_identity
    ):
        raise ValueError("Stream resolution issuance/story lineage mismatch")

    source_event = build_forecast_resolved_source_event(
        activation,
        context,
        feed_event,
        resolution,
    )
    fact_bundle = build_stream_fact_bundle(
        source_event,
        context,
        forecast,
        proof,
        resolution=resolution,
    )
    relation = build_resolution_relation(issuance_message)
    message_input = build_stream_message_input(
        source_event,
        fact_bundle,
        relations=(relation,),
    )
    return StreamProjectedMessage(
        source_event=source_event,
        fact_bundle=fact_bundle,
        message_input=message_input,
    )


def _require_implemented_projector(projector_id: str) -> None:
    selected = next(
        (
            item
            for item in accepted_stream_projector_registry()
            if item.projector_id == projector_id
        ),
        None,
    )
    if selected is None:
        raise ValueError("Stream projector is not in accepted registry")
    if selected.implementation_state is not StreamProjectorImplementationState.IMPLEMENTED:
        raise ValueError("Stream projector is not implemented")
