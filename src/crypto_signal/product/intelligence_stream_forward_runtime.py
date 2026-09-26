from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

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
from crypto_signal.product.intelligence_stream_models import (
    StreamActivationBoundary,
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
