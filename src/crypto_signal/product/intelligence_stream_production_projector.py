from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_sha256
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
    StreamLedgerWriteDisposition,
)
from crypto_signal.product.intelligence_stream_message_ledger import (
    IntelligenceStreamMessageLedger,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    StreamCategory,
    StreamImportance,
)
from crypto_signal.product.intelligence_stream_narrative import (
    build_stream_narrative_plan,
    render_stream_narrative,
)
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamProjectorImplementationState,
    StreamProjectorSpec,
    accepted_stream_projector_registry,
)
from crypto_signal.product.intelligence_stream_projectors import (
    StreamProjectedMessage,
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

STREAM_PRODUCTION_PROJECTOR_CONTRACT_SCHEMA_VERSION = (
    "intelligence-stream-production-projector-contract-v1/1"
)


class StreamProductionProjectionDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"
    SILENT = "silent"


@dataclass(frozen=True, slots=True)
class StreamProductionProjectorContract:
    contract_identity: str
    projector_id: str
    source_event_identity: str
    stream_event_identity: str
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    asset: str
    symbol: str
    market: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    evidence_identities: tuple[str, ...]
    story_identity: str
    current_fact_reference_identity: str
    previous_state_reference_identity: str | None
    materiality_reason_codes: tuple[str, ...]
    materiality_decision_identity: str
    schema_version: str = STREAM_PRODUCTION_PROJECTOR_CONTRACT_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.contract_identity, "Stream production contract identity"),
            (self.source_event_identity, "Stream production source identity"),
            (self.stream_event_identity, "Stream production event identity"),
            (self.story_identity, "Stream production story identity"),
            (
                self.current_fact_reference_identity,
                "Stream production current fact reference",
            ),
            (
                self.materiality_decision_identity,
                "Stream production materiality decision",
            ),
        ):
            _require_sha256(value, label)
        if self.previous_state_reference_identity is not None:
            _require_sha256(
                self.previous_state_reference_identity,
                "Stream production previous state reference",
            )
        for value, label in (
            (self.projector_id, "Stream production projector id"),
            (self.subtype, "Stream production subtype"),
            (self.asset, "Stream production asset"),
            (self.symbol, "Stream production symbol"),
            (self.market, "Stream production market"),
            (self.timeframe, "Stream production timeframe"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.category, StreamCategory):
            raise TypeError("Stream production category must be canonical")
        if not isinstance(self.importance, StreamImportance):
            raise TypeError("Stream production importance must be canonical")
        if min(self.event_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("Stream production timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("Stream production event cannot predate source as-of")
        _require_identity_tuple(
            self.evidence_identities,
            "Stream production evidence identity",
        )
        _require_text_tuple(
            self.materiality_reason_codes,
            "Stream production materiality reason",
        )
        if not self.evidence_identities:
            raise ValueError("Stream production contract requires evidence identity")
        if not self.materiality_reason_codes:
            raise ValueError("Stream production contract requires materiality reason")
        if self.schema_version != STREAM_PRODUCTION_PROJECTOR_CONTRACT_SCHEMA_VERSION:
            raise ValueError("unsupported Stream production contract schema")
        if self.engine_version != STREAM_ENGINE_VERSION:
            raise ValueError("unsupported Stream production contract engine")
        if not self.read_only:
            raise ValueError("Stream production projection must remain read-only")
        if self.production_authority:
            raise ValueError("Stream production projection cannot grant authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.contract_identity != canonical_sha256(
            _production_contract_payload(self)
        ):
            raise ValueError("Stream production contract identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamProductionProjectionResult:
    disposition: StreamProductionProjectionDisposition
    projector_id: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    state_identity: str
    narrative_identity: str | None
    contract_identity: str
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_event_identity, "Stream production result source identity"),
            (self.stream_event_identity, "Stream production result event identity"),
            (self.story_identity, "Stream production result story identity"),
            (self.state_identity, "Stream production result state identity"),
            (self.contract_identity, "Stream production result contract identity"),
        ):
            _require_sha256(value, label)
        if self.narrative_identity is not None:
            _require_sha256(
                self.narrative_identity,
                "Stream production result narrative identity",
            )
        if not self.projector_id.strip():
            raise ValueError("Stream production result requires projector id")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("Stream production result crossed authority boundary")


def build_stream_production_projector_contract(
    projector_id: str,
    projected: StreamProjectedMessage,
    *,
    previous_state: StreamStoryState | None = None,
) -> StreamProductionProjectorContract:
    spec = _require_implemented_projector(projector_id)
    source_event = projected.source_event
    fact_bundle = projected.fact_bundle
    message_input = projected.message_input

    if source_event.category is not spec.category:
        raise ValueError("Stream production projector/category mismatch")
    if source_event.subtype not in spec.subtypes:
        raise ValueError("Stream production projector/subtype mismatch")
    if message_input.category is not source_event.category:
        raise ValueError("Stream production message/source category mismatch")
    if message_input.subtype != source_event.subtype:
        raise ValueError("Stream production message/source subtype mismatch")
    if message_input.importance is not source_event.importance:
        raise ValueError("Stream production message/source importance mismatch")
    if (
        fact_bundle.asset,
        fact_bundle.symbol,
        fact_bundle.market,
        fact_bundle.timeframe,
    ) != (
        source_event.asset,
        source_event.symbol,
        source_event.symbol,
        source_event.timeframe,
    ):
        raise ValueError("Stream production fact/source market mismatch")
    if message_input.evidence_reference_identities != source_event.evidence_identities:
        raise ValueError("Stream production source/message evidence mismatch")
    if previous_state is not None and previous_state.story_identity != fact_bundle.story_identity:
        raise ValueError("Stream production previous state/story mismatch")

    previous_state_identity = (
        None if previous_state is None else previous_state.state_identity
    )
    payload = {
        "asset": source_event.asset,
        "category": source_event.category,
        "current_fact_reference_identity": fact_bundle.fact_bundle_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": source_event.event_at_ms,
        "evidence_identities": source_event.evidence_identities,
        "importance": source_event.importance,
        "market": fact_bundle.market,
        "materiality_decision_identity": message_input.materiality_decision_identity,
        "materiality_reason_codes": source_event.materiality_codes,
        "previous_state_reference_identity": previous_state_identity,
        "production_authority": False,
        "projector_id": projector_id,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_PRODUCTION_PROJECTOR_CONTRACT_SCHEMA_VERSION,
        "source_as_of_ms": source_event.source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "story_identity": fact_bundle.story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": source_event.subtype,
        "symbol": source_event.symbol,
        "timeframe": source_event.timeframe,
    }
    return StreamProductionProjectorContract(
        contract_identity=canonical_sha256(payload),
        projector_id=projector_id,
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        category=source_event.category,
        subtype=source_event.subtype,
        importance=source_event.importance,
        asset=source_event.asset,
        symbol=source_event.symbol,
        market=fact_bundle.market,
        timeframe=source_event.timeframe,
        event_at_ms=source_event.event_at_ms,
        source_as_of_ms=source_event.source_as_of_ms,
        evidence_identities=source_event.evidence_identities,
        story_identity=fact_bundle.story_identity,
        current_fact_reference_identity=fact_bundle.fact_bundle_identity,
        previous_state_reference_identity=previous_state_identity,
        materiality_reason_codes=source_event.materiality_codes,
        materiality_decision_identity=message_input.materiality_decision_identity,
    )


class IntelligenceStreamProductionProjector:
    """Canonical S3/S4/S5 production backbone for source-specific projectors.

    A source-specific adapter must first create one canonical StreamProjectedMessage.
    This class then owns the accepted message -> story -> analytical -> narrative
    chain. Later source families must use this path rather than writing directly to
    downstream ledgers.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.source_ledger = IntelligenceStreamLedger(path)
        self.message_ledger = IntelligenceStreamMessageLedger(path)
        self.story_ledger = IntelligenceStreamStoryLedger(path)
        self.analytical_ledger = IntelligenceStreamAnalyticalLedger(path)
        self.narrative_ledger = IntelligenceStreamNarrativeLedger(path)

    def project(
        self,
        projector_id: str,
        projected: StreamProjectedMessage,
        *,
        previous_state: StreamStoryState | None = None,
    ) -> StreamProductionProjectionResult:
        contract = build_stream_production_projector_contract(
            projector_id,
            projected,
            previous_state=previous_state,
        )
        activation = self.source_ledger.read_activation()
        if activation.get("activation_identity") != projected.source_event.activation_identity:
            raise ValueError("Stream production event/activation mismatch")

        source_disposition = self.source_ledger.append_source_event(
            projected.source_event
        )
        return self._project_after_source_write(
            contract,
            projected,
            source_disposition=source_disposition,
            previous_state=previous_state,
        )

    def _project_after_source_write(
        self,
        contract: StreamProductionProjectorContract,
        projected: StreamProjectedMessage,
        *,
        source_disposition: StreamLedgerWriteDisposition,
        previous_state: StreamStoryState | None,
    ) -> StreamProductionProjectionResult:
        message_disposition = self.message_ledger.append_message_bundle(
            projected.fact_bundle,
            projected.message_input,
        )
        observation = build_story_observation(
            projected.message_input,
            projected.fact_bundle,
            previous_state_identity=(
                None if previous_state is None else previous_state.state_identity
            ),
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
            return StreamProductionProjectionResult(
                disposition=StreamProductionProjectionDisposition.SILENT,
                projector_id=contract.projector_id,
                source_event_identity=contract.source_event_identity,
                stream_event_identity=contract.stream_event_identity,
                story_identity=contract.story_identity,
                state_identity=state.state_identity,
                narrative_identity=None,
                contract_identity=contract.contract_identity,
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
            StreamProductionProjectionDisposition.UNCHANGED
            if dispositions == {"unchanged"}
            else StreamProductionProjectionDisposition.INSERTED
        )
        return StreamProductionProjectionResult(
            disposition=disposition,
            projector_id=contract.projector_id,
            source_event_identity=contract.source_event_identity,
            stream_event_identity=contract.stream_event_identity,
            story_identity=contract.story_identity,
            state_identity=state.state_identity,
            narrative_identity=narrative.narrative_identity,
            contract_identity=contract.contract_identity,
        )


def _require_implemented_projector(projector_id: str) -> StreamProjectorSpec:
    selected = next(
        (
            item
            for item in accepted_stream_projector_registry()
            if item.projector_id == projector_id
        ),
        None,
    )
    if selected is None:
        raise ValueError("Stream production projector is not in accepted registry")
    if (
        selected.implementation_state
        is not StreamProjectorImplementationState.IMPLEMENTED
    ):
        raise ValueError("Stream production projector is not implemented")
    return selected


def _production_contract_payload(
    value: StreamProductionProjectorContract,
) -> dict[str, object]:
    return {
        "asset": value.asset,
        "category": value.category,
        "current_fact_reference_identity": value.current_fact_reference_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "evidence_identities": value.evidence_identities,
        "importance": value.importance,
        "market": value.market,
        "materiality_decision_identity": value.materiality_decision_identity,
        "materiality_reason_codes": value.materiality_reason_codes,
        "previous_state_reference_identity": value.previous_state_reference_identity,
        "production_authority": value.production_authority,
        "projector_id": value.projector_id,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
    }


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
