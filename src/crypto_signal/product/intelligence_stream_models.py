from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crypto_signal.forecast_stream import ForecastResolution, ImmutableForecast
from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceMatrixSnapshot
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    DecisionProofSnapshot,
    LiveFeedEventKind,
    LiveIntelligenceFeedEvent,
)

STREAM_ENGINE_VERSION = "crypto-signal-intelligence-stream-event-model-v1/1"
STREAM_ACTIVATION_SCHEMA_VERSION = "intelligence-stream-activation-v1/1"
STREAM_DECISION_CONTEXT_SCHEMA_VERSION = "intelligence-stream-decision-context-v1/1"
STREAM_SOURCE_EVENT_SCHEMA_VERSION = "intelligence-stream-source-event-v1/1"
REAL_CAPITAL = 0


class StreamCategory(StrEnum):
    MARKET = "market"
    INTELLIGENCE = "intelligence"
    DECISION = "decision"
    CAPITAL = "capital"
    RISK = "risk"
    OUTCOME = "outcome"
    SYSTEM = "system"
    ROUTINE = "routine"


class StreamImportance(StrEnum):
    ROUTINE = "routine"
    IMPORTANT = "important"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class StreamActivationBoundary:
    activation_identity: str
    activated_at_ms: int
    activation_label: str = "intelligence_stream_v1_forward_activation"
    historical_rich_backfill_allowed: bool = False
    schema_version: str = STREAM_ACTIVATION_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.activation_identity, "Stream activation identity")
        if self.activated_at_ms < 0:
            raise ValueError("Stream activation time must be non-negative")
        if not self.activation_label.strip():
            raise ValueError("Stream activation label must be non-empty")
        if self.historical_rich_backfill_allowed:
            raise ValueError("Stream V1 cannot synthesize rich historical backfill")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_ACTIVATION_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.activation_identity != canonical_sha256(_activation_payload(self)):
            raise ValueError("Stream activation identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamDecisionContextSnapshot:
    context_identity: str
    forecast_identity: str
    proof_identity: str
    signal_freeze_identity: str
    confluence_identity: str
    event_context_identity: str
    asset: str
    symbol: str
    timeframe: str
    source_as_of_ms: int
    issued_at_ms: int
    confluence: ConfluenceMatrixSnapshot
    proof_slice_identities: tuple[str, ...]
    forecast_source_evidence_identities: tuple[str, ...]
    schema_version: str = STREAM_DECISION_CONTEXT_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.context_identity, "Stream decision context identity"),
            (self.forecast_identity, "Stream context forecast identity"),
            (self.proof_identity, "Stream context proof identity"),
            (self.signal_freeze_identity, "Stream context signal identity"),
            (self.confluence_identity, "Stream context confluence identity"),
            (self.event_context_identity, "Stream context event identity"),
        ):
            _require_sha256(value, label)
        for value, label in (
            (self.asset, "Stream context asset"),
            (self.symbol, "Stream context symbol"),
            (self.timeframe, "Stream context timeframe"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if min(self.source_as_of_ms, self.issued_at_ms) < 0:
            raise ValueError("Stream context timestamps must be non-negative")
        if self.issued_at_ms < self.source_as_of_ms:
            raise ValueError("Stream context issue time cannot predate source as-of")
        if self.confluence.snapshot_identity != self.confluence_identity:
            raise ValueError("Stream context lost exact M6 snapshot identity")
        if self.confluence.asset != self.symbol:
            raise ValueError("Stream context M6 symbol mismatch")
        if self.confluence.timeframe != self.timeframe:
            raise ValueError("Stream context M6 timeframe mismatch")
        if self.confluence.as_of_ms != self.source_as_of_ms:
            raise ValueError("Stream context M6/source as-of mismatch")
        _require_identity_tuple(
            self.proof_slice_identities,
            "Stream context proof slice identity",
            allow_empty=False,
        )
        _require_identity_tuple(
            self.forecast_source_evidence_identities,
            "Stream context forecast source evidence",
            allow_empty=False,
        )
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_DECISION_CONTEXT_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.context_identity != canonical_sha256(_decision_context_payload(self)):
            raise ValueError("Stream decision context identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamSourceEvent:
    stream_event_identity: str
    activation_identity: str
    source_event_identity: str
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    forecast_identity: str | None
    proof_identity: str | None
    resolution_identity: str | None
    decision_context_identity: str | None
    evidence_identities: tuple[str, ...]
    materiality_codes: tuple[str, ...]
    schema_version: str = STREAM_SOURCE_EVENT_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.stream_event_identity, "Stream source-event identity"),
            (self.activation_identity, "Stream source-event activation identity"),
            (self.source_event_identity, "Stream source event identity"),
        ):
            _require_sha256(value, label)
        for value, label in (
            (self.subtype, "Stream source-event subtype"),
            (self.asset, "Stream source-event asset"),
            (self.symbol, "Stream source-event symbol"),
            (self.timeframe, "Stream source-event timeframe"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.category, StreamCategory):
            raise TypeError("Stream source event requires canonical category")
        if not isinstance(self.importance, StreamImportance):
            raise TypeError("Stream source event requires canonical importance")
        if min(self.event_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("Stream source-event timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("Stream source event cannot predate source as-of")
        for optional_identity, label in (
            (self.forecast_identity, "Stream source-event forecast identity"),
            (self.proof_identity, "Stream source-event proof identity"),
            (self.resolution_identity, "Stream source-event resolution identity"),
            (self.decision_context_identity, "Stream source-event context identity"),
        ):
            if optional_identity is not None:
                _require_sha256(optional_identity, label)
        _require_identity_tuple(
            self.evidence_identities,
            "Stream source-event evidence identity",
            allow_empty=False,
        )
        _require_text_tuple(self.materiality_codes, "Stream materiality code")
        if not self.materiality_codes:
            raise ValueError("Stream source event requires materiality code")
        _require_common_authority(
            schema_version=self.schema_version,
            expected_schema=STREAM_SOURCE_EVENT_SCHEMA_VERSION,
            engine_version=self.engine_version,
            read_only=self.read_only,
            production_authority=self.production_authority,
            real_capital=self.real_capital,
        )
        if self.stream_event_identity != canonical_sha256(_source_event_payload(self)):
            raise ValueError("Stream source-event identity mismatch")


def build_stream_activation_boundary(*, activated_at_ms: int) -> StreamActivationBoundary:
    payload = {
        "activated_at_ms": activated_at_ms,
        "activation_label": "intelligence_stream_v1_forward_activation",
        "engine_version": STREAM_ENGINE_VERSION,
        "historical_rich_backfill_allowed": False,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_ACTIVATION_SCHEMA_VERSION,
    }
    return StreamActivationBoundary(
        activation_identity=canonical_sha256(payload),
        activated_at_ms=activated_at_ms,
    )


def build_stream_decision_context(
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    confluence: ConfluenceMatrixSnapshot,
) -> StreamDecisionContextSnapshot:
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("Stream context proof/forecast identity mismatch")
    if proof.signal_freeze_identity != forecast.signal_freeze_identity:
        raise ValueError("Stream context proof/forecast signal mismatch")
    if proof.confluence_identity != forecast.confluence_identity:
        raise ValueError("Stream context proof/forecast M6 mismatch")
    if confluence.snapshot_identity != forecast.confluence_identity:
        raise ValueError("Stream context forecast/full M6 identity mismatch")
    if proof.event_context_identity != forecast.event_context_identity:
        raise ValueError("Stream context proof/forecast Event Risk mismatch")
    if (
        proof.asset,
        proof.symbol,
        proof.timeframe,
        proof.source_as_of_ms,
        proof.issued_at_ms,
    ) != (
        forecast.asset,
        forecast.symbol,
        forecast.timeframe,
        forecast.source_as_of_ms,
        forecast.issued_at_ms,
    ):
        raise ValueError("Stream context proof/forecast market-time mismatch")
    proof_slice_ids = tuple(
        sorted(item.slice_identity for item in proof.evidence_slices)
    )
    source_ids = tuple(forecast.source_evidence_identities)
    payload = {
        "asset": forecast.asset,
        "confluence": confluence,
        "confluence_identity": forecast.confluence_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_context_identity": forecast.event_context_identity,
        "forecast_identity": forecast.forecast_identity,
        "forecast_source_evidence_identities": source_ids,
        "issued_at_ms": forecast.issued_at_ms,
        "production_authority": False,
        "proof_identity": proof.proof_identity,
        "proof_slice_identities": proof_slice_ids,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_DECISION_CONTEXT_SCHEMA_VERSION,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "source_as_of_ms": forecast.source_as_of_ms,
        "symbol": forecast.symbol,
        "timeframe": forecast.timeframe,
    }
    context_identity = canonical_sha256(payload)
    return StreamDecisionContextSnapshot(
        context_identity=context_identity,
        forecast_identity=forecast.forecast_identity,
        proof_identity=proof.proof_identity,
        signal_freeze_identity=forecast.signal_freeze_identity,
        confluence_identity=forecast.confluence_identity,
        event_context_identity=forecast.event_context_identity,
        asset=forecast.asset,
        symbol=forecast.symbol,
        timeframe=forecast.timeframe,
        source_as_of_ms=forecast.source_as_of_ms,
        issued_at_ms=forecast.issued_at_ms,
        confluence=confluence,
        proof_slice_identities=proof_slice_ids,
        forecast_source_evidence_identities=source_ids,
    )


def build_forecast_issued_source_event(
    activation: StreamActivationBoundary,
    context: StreamDecisionContextSnapshot,
    event: LiveIntelligenceFeedEvent,
) -> StreamSourceEvent:
    if event.kind is not LiveFeedEventKind.FORECAST_ISSUED:
        raise ValueError("Stream issuance projector requires FORECAST_ISSUED")
    if event.resolution_identity is not None:
        raise ValueError("Stream issuance source cannot carry resolution")
    if event.event_at_ms < activation.activated_at_ms:
        raise ValueError("Stream refuses rich event before activation boundary")
    if event.forecast_identity != context.forecast_identity:
        raise ValueError("Stream source/context forecast mismatch")
    if event.proof_identity != context.proof_identity:
        raise ValueError("Stream source/context proof mismatch")
    if (event.asset, event.symbol, event.timeframe, event.event_at_ms) != (
        context.asset,
        context.symbol,
        context.timeframe,
        context.issued_at_ms,
    ):
        raise ValueError("Stream source/context market-time mismatch")

    evidence_ids = tuple(
        sorted(
            {
                context.context_identity,
                context.confluence_identity,
                context.event_context_identity,
                context.signal_freeze_identity,
                *context.proof_slice_identities,
                *context.forecast_source_evidence_identities,
            }
        )
    )
    payload = {
        "activation_identity": activation.activation_identity,
        "asset": context.asset,
        "category": StreamCategory.DECISION,
        "decision_context_identity": context.context_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event.event_at_ms,
        "evidence_identities": evidence_ids,
        "forecast_identity": context.forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "materiality_codes": ("new_forecast_issued",),
        "production_authority": False,
        "proof_identity": context.proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": None,
        "schema_version": STREAM_SOURCE_EVENT_SCHEMA_VERSION,
        "source_as_of_ms": context.source_as_of_ms,
        "source_event_identity": event.event_identity,
        "subtype": LiveFeedEventKind.FORECAST_ISSUED.value,
        "symbol": context.symbol,
        "timeframe": context.timeframe,
    }
    stream_event_identity = canonical_sha256(payload)
    return StreamSourceEvent(
        stream_event_identity=stream_event_identity,
        activation_identity=activation.activation_identity,
        source_event_identity=event.event_identity,
        category=StreamCategory.DECISION,
        subtype=LiveFeedEventKind.FORECAST_ISSUED.value,
        importance=StreamImportance.IMPORTANT,
        asset=context.asset,
        symbol=context.symbol,
        timeframe=context.timeframe,
        event_at_ms=event.event_at_ms,
        source_as_of_ms=context.source_as_of_ms,
        forecast_identity=context.forecast_identity,
        proof_identity=context.proof_identity,
        resolution_identity=None,
        decision_context_identity=context.context_identity,
        evidence_identities=evidence_ids,
        materiality_codes=("new_forecast_issued",),
    )


def build_forecast_resolved_source_event(
    activation: StreamActivationBoundary,
    context: StreamDecisionContextSnapshot,
    event: LiveIntelligenceFeedEvent,
    resolution: ForecastResolution,
) -> StreamSourceEvent:
    if event.kind is not LiveFeedEventKind.FORECAST_RESOLVED:
        raise ValueError("Stream resolution projector requires FORECAST_RESOLVED")
    if event.resolution_identity != resolution.resolution_identity:
        raise ValueError("Stream resolution event/source identity mismatch")
    if resolution.forecast_identity != context.forecast_identity:
        raise ValueError("Stream resolution/context forecast mismatch")
    if resolution.signal_freeze_identity != context.signal_freeze_identity:
        raise ValueError("Stream resolution/context signal mismatch")
    if event.forecast_identity != context.forecast_identity:
        raise ValueError("Stream resolution event/context forecast mismatch")
    if event.proof_identity != context.proof_identity:
        raise ValueError("Stream resolution event/context proof mismatch")
    if event.event_at_ms != resolution.evaluated_at_ms:
        raise ValueError("Stream resolution event time mismatch")
    if event.state != resolution.state.value:
        raise ValueError("Stream resolution state mismatch")
    if event.event_at_ms < activation.activated_at_ms:
        raise ValueError("Stream refuses rich event before activation boundary")
    if (event.asset, event.symbol, event.timeframe) != (
        context.asset,
        context.symbol,
        context.timeframe,
    ):
        raise ValueError("Stream resolution event/context market mismatch")

    evidence_ids = tuple(
        sorted(
            {
                context.context_identity,
                context.confluence_identity,
                context.event_context_identity,
                context.signal_freeze_identity,
                resolution.resolution_identity,
                resolution.source_outcome_identity,
                *context.proof_slice_identities,
                *context.forecast_source_evidence_identities,
            }
        )
    )
    materiality_codes = tuple(
        sorted(
            {
                "forecast_outcome_resolved",
                f"resolution_{resolution.state.value}",
            }
        )
    )
    payload = {
        "activation_identity": activation.activation_identity,
        "asset": context.asset,
        "category": StreamCategory.OUTCOME,
        "decision_context_identity": context.context_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": resolution.evaluated_at_ms,
        "evidence_identities": evidence_ids,
        "forecast_identity": context.forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "materiality_codes": materiality_codes,
        "production_authority": False,
        "proof_identity": context.proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": resolution.resolution_identity,
        "schema_version": STREAM_SOURCE_EVENT_SCHEMA_VERSION,
        "source_as_of_ms": resolution.evaluated_at_ms,
        "source_event_identity": event.event_identity,
        "subtype": LiveFeedEventKind.FORECAST_RESOLVED.value,
        "symbol": context.symbol,
        "timeframe": context.timeframe,
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation.activation_identity,
        source_event_identity=event.event_identity,
        category=StreamCategory.OUTCOME,
        subtype=LiveFeedEventKind.FORECAST_RESOLVED.value,
        importance=StreamImportance.IMPORTANT,
        asset=context.asset,
        symbol=context.symbol,
        timeframe=context.timeframe,
        event_at_ms=resolution.evaluated_at_ms,
        source_as_of_ms=resolution.evaluated_at_ms,
        forecast_identity=context.forecast_identity,
        proof_identity=context.proof_identity,
        resolution_identity=resolution.resolution_identity,
        decision_context_identity=context.context_identity,
        evidence_identities=evidence_ids,
        materiality_codes=materiality_codes,
    )


def activation_payload(value: StreamActivationBoundary) -> dict[str, object]:
    return _activation_payload(value)


def decision_context_payload(
    value: StreamDecisionContextSnapshot,
) -> dict[str, object]:
    return _decision_context_payload(value)


def source_event_payload(value: StreamSourceEvent) -> dict[str, object]:
    return _source_event_payload(value)


def _activation_payload(value: StreamActivationBoundary) -> dict[str, object]:
    return {
        "activated_at_ms": value.activated_at_ms,
        "activation_label": value.activation_label,
        "engine_version": value.engine_version,
        "historical_rich_backfill_allowed": value.historical_rich_backfill_allowed,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
    }


def _decision_context_payload(
    value: StreamDecisionContextSnapshot,
) -> dict[str, object]:
    return {
        "asset": value.asset,
        "confluence": value.confluence,
        "confluence_identity": value.confluence_identity,
        "engine_version": value.engine_version,
        "event_context_identity": value.event_context_identity,
        "forecast_identity": value.forecast_identity,
        "forecast_source_evidence_identities": value.forecast_source_evidence_identities,
        "issued_at_ms": value.issued_at_ms,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "proof_slice_identities": value.proof_slice_identities,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "signal_freeze_identity": value.signal_freeze_identity,
        "source_as_of_ms": value.source_as_of_ms,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
    }


def _source_event_payload(value: StreamSourceEvent) -> dict[str, object]:
    return {
        "activation_identity": value.activation_identity,
        "asset": value.asset,
        "category": value.category,
        "decision_context_identity": value.decision_context_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "evidence_identities": value.evidence_identities,
        "forecast_identity": value.forecast_identity,
        "importance": value.importance,
        "materiality_codes": value.materiality_codes,
        "production_authority": value.production_authority,
        "proof_identity": value.proof_identity,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "resolution_identity": value.resolution_identity,
        "schema_version": value.schema_version,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
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
        raise ValueError("unsupported Stream schema version")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream engine version")
    if not read_only:
        raise ValueError("Stream source truth must remain read-only")
    if production_authority:
        raise ValueError("Stream source truth cannot grant production authority")
    if real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")


def _require_identity_tuple(
    values: tuple[str, ...],
    label: str,
    *,
    allow_empty: bool,
) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{label} cannot be empty")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_text_tuple(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot contain blank values")
