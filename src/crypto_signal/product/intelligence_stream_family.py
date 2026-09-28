from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.intelligence.confluence_matrix_v2 import ConfluenceFamily
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.product.intelligence_stream_ledger import IntelligenceStreamLedger
from crypto_signal.product.intelligence_stream_messages import (
    STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
    STREAM_MESSAGE_PROJECTOR_VERSION,
    StreamMessageInput,
    StreamSearchMetadata,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    StreamCategory,
    StreamImportance,
    StreamSourceEvent,
)
from crypto_signal.product.intelligence_stream_narrative import (
    STREAM_NARRATIVE_VALIDATOR_VERSION,
    STREAM_NARRATIVE_VOICE_VERSION,
    StreamNarrativeSourceKind,
    StreamNarrativeText,
    StreamNarrativeValidation,
)
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)
from crypto_signal.product.intelligence_stream_policy import (
    StreamMateriality,
    StreamProjectorImplementationState,
    StreamProjectorSpec,
    StreamPublicationDisposition,
    accepted_stream_projector_registry,
    build_stream_materiality_policy,
    evaluate_stream_materiality,
)

STREAM_FAMILY_FACT_SCHEMA_VERSION = "intelligence-stream-family-fact-v1/1"
STREAM_FAMILY_STORY_OBSERVATION_SCHEMA_VERSION = (
    "intelligence-stream-family-story-observation-v1/1"
)
STREAM_FAMILY_STORY_STATE_SCHEMA_VERSION = (
    "intelligence-stream-family-story-state-v1/1"
)
STREAM_FAMILY_CHANGE_SET_SCHEMA_VERSION = (
    "intelligence-stream-family-change-set-v1/1"
)
STREAM_FAMILY_ANALYTICAL_VIEW_SCHEMA_VERSION = (
    "intelligence-stream-family-analytical-view-v1/1"
)
STREAM_FAMILY_NARRATIVE_PLAN_SCHEMA_VERSION = (
    "intelligence-stream-family-narrative-plan-v1/1"
)
STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION = (
    "intelligence-stream-family-narrative-message-v1/1"
)
STREAM_FAMILY_NARRATIVE_RENDERER_VERSION = (
    "crypto-signal-family-customer-tr-v2/1"
)
STREAM_FAMILY_PROJECTOR_VERSION = "stream-final-f3-family-projector/1"
STREAM_FAMILY_ANALYTICAL_POLICY_VERSION = "stream-final-f3-family-analytical/1"
STREAM_FAMILY_ACTIVATION_SCHEMA_VERSION = (
    "intelligence-stream-family-activation-v1/1"
)


class StreamTrustDomain(StrEnum):
    EVENT_RISK = "event_risk"
    PROVIDER_QUALITY = "provider_quality"


StreamFamilyDomain = ConfluenceFamily | StreamTrustDomain


class StreamFamilyProjectionDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"
    SILENT_UNCHANGED = "silent_unchanged"
    SILENT_INITIAL_BASELINE = "silent_initial_baseline"
    SKIPPED_BEFORE_ACTIVATION = "skipped_before_activation"


@dataclass(frozen=True, slots=True)
class StreamFamilyStateComponent:
    name: str
    value: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.value.strip():
            raise ValueError("Stream family state component must be non-empty")


@dataclass(frozen=True, slots=True)
class StreamFamilySnapshot:
    projector_id: str
    family: StreamFamilyDomain
    category: StreamCategory
    subtype: str
    importance: StreamImportance
    source_event_identity: str
    source_scope: str
    asset: str
    symbol: str
    market: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    evidence_identities: tuple[str, ...]
    evidence_domains: tuple[str, ...]
    state_label: str
    state_components: tuple[StreamFamilyStateComponent, ...]
    direction: str | None
    source_quality: str
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.projector_id, "family projector id"),
            (self.subtype, "family subtype"),
            (self.source_scope, "family source scope"),
            (self.asset, "family asset"),
            (self.symbol, "family symbol"),
            (self.market, "family market"),
            (self.timeframe, "family timeframe"),
            (self.state_label, "family state label"),
            (self.source_quality, "family source quality"),
        ):
            if not value.strip():
                raise ValueError(f"Stream {label} must be non-empty")
        _require_sha256(self.source_event_identity, "family source event identity")
        if min(self.event_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("Stream family timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("Stream family event cannot predate source as-of")
        _require_identity_tuple(self.evidence_identities, "family evidence identity")
        _require_text_tuple(self.evidence_domains, "family evidence domain")
        _require_text_tuple(self.uncertainty_flags, "family uncertainty")
        if not self.evidence_identities:
            raise ValueError("Stream family snapshot requires exact evidence")
        component_keys = tuple(item.name for item in self.state_components)
        if component_keys != tuple(sorted(set(component_keys))):
            raise ValueError("Stream family state components must be unique and sorted")
        if not self.state_components:
            raise ValueError("Stream family snapshot requires state components")
        if self.direction is not None and not self.direction.strip():
            raise ValueError("Stream family direction cannot be blank")


@dataclass(frozen=True, slots=True)
class StreamFamilyFactBundle:
    fact_bundle_identity: str
    stream_event_identity: str
    source_event_identity: str
    story_identity: str
    projector_id: str
    family: StreamFamilyDomain
    source_scope: str
    asset: str
    symbol: str
    market: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    evidence_identities: tuple[str, ...]
    available_evidence_domains: tuple[str, ...]
    state_label: str
    state_key: str
    state_components: tuple[StreamFamilyStateComponent, ...]
    direction: str | None
    source_quality: str
    uncertainty_flags: tuple[str, ...]
    previous_fact_bundle_identity: str | None
    schema_version: str = STREAM_FAMILY_FACT_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.fact_bundle_identity, "family fact identity"),
            (self.stream_event_identity, "family fact stream event"),
            (self.source_event_identity, "family fact source event"),
            (self.story_identity, "family fact story"),
            (self.state_key, "family fact state key"),
        ):
            _require_sha256(value, label)
        if self.previous_fact_bundle_identity is not None:
            _require_sha256(
                self.previous_fact_bundle_identity,
                "family previous fact identity",
            )
        _require_identity_tuple(self.evidence_identities, "family fact evidence")
        _require_text_tuple(
            self.available_evidence_domains,
            "family fact evidence domain",
        )
        _require_text_tuple(self.uncertainty_flags, "family fact uncertainty")
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_FACT_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.fact_bundle_identity != canonical_sha256(
            _family_fact_payload(self)
        ):
            raise ValueError("Stream family fact identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyStoryObservation:
    observation_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    message_identity: str
    previous_state_identity: str | None
    current_fact_bundle_identity: str
    family: StreamFamilyDomain
    state_label: str
    state_key: str
    state_components: tuple[StreamFamilyStateComponent, ...]
    event_at_ms: int
    asset: str
    symbol: str
    timeframe: str
    schema_version: str = STREAM_FAMILY_STORY_OBSERVATION_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value in (
            self.observation_identity,
            self.story_identity,
            self.source_event_identity,
            self.stream_event_identity,
            self.message_identity,
            self.current_fact_bundle_identity,
            self.state_key,
        ):
            _require_sha256(value, "family story observation identity")
        if self.previous_state_identity is not None:
            _require_sha256(
                self.previous_state_identity,
                "family story previous state",
            )
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_STORY_OBSERVATION_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.observation_identity != canonical_sha256(
            _family_observation_payload(self)
        ):
            raise ValueError("Stream family story observation identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyStoryState:
    state_identity: str
    story_identity: str
    observation_identity: str
    source_event_identity: str
    current_stream_event_identity: str
    current_message_identity: str
    previous_state_identity: str | None
    current_fact_bundle_identity: str
    family: StreamFamilyDomain
    state_label: str
    state_key: str
    state_components: tuple[StreamFamilyStateComponent, ...]
    event_at_ms: int
    asset: str
    symbol: str
    timeframe: str
    schema_version: str = STREAM_FAMILY_STORY_STATE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value in (
            self.state_identity,
            self.story_identity,
            self.observation_identity,
            self.source_event_identity,
            self.current_stream_event_identity,
            self.current_message_identity,
            self.current_fact_bundle_identity,
            self.state_key,
        ):
            _require_sha256(value, "family story state identity")
        if self.previous_state_identity is not None:
            _require_sha256(
                self.previous_state_identity,
                "family story previous state",
            )
        component_keys = tuple(item.name for item in self.state_components)
        if component_keys != tuple(sorted(set(component_keys))):
            raise ValueError("Stream family story components must be canonical")
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_STORY_STATE_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.state_identity != canonical_sha256(_family_state_payload(self)):
            raise ValueError("Stream family story state identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyChangeSet:
    change_set_identity: str
    story_identity: str
    previous_state_identity: str | None
    current_state_identity: str
    previous_message_identity: str | None
    current_message_identity: str
    previous_state_label: str | None
    current_state_label: str
    changed_components: tuple[str, ...]
    story_started: bool
    schema_version: str = STREAM_FAMILY_CHANGE_SET_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value in (
            self.change_set_identity,
            self.story_identity,
            self.current_state_identity,
            self.current_message_identity,
        ):
            _require_sha256(value, "family change identity")
        for optional in (
            self.previous_state_identity,
            self.previous_message_identity,
        ):
            if optional is not None:
                _require_sha256(optional, "family change previous identity")
        _require_text_tuple(self.changed_components, "family changed component")
        if not self.changed_components:
            raise ValueError("Stream family change set requires changed component")
        if self.story_started != (self.previous_state_identity is None):
            raise ValueError("Stream family story-start semantics mismatch")
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_CHANGE_SET_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.change_set_identity != canonical_sha256(
            _family_change_payload(self)
        ):
            raise ValueError("Stream family change-set identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyAnalyticalView:
    analytical_view_identity: str
    policy_identity: str
    policy_version: str
    materiality_decision_identity: str
    materiality_reason_codes: tuple[str, ...]
    fact_bundle_identity: str
    change_set_identity: str
    current_state_identity: str
    source_message_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    family: StreamFamilyDomain
    family_state_label: str
    previous_family_state_label: str | None
    direction: str | None
    source_quality: str
    uncertainty_flags: tuple[str, ...]
    changed_components: tuple[str, ...]
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    schema_version: str = STREAM_FAMILY_ANALYTICAL_VIEW_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value in (
            self.analytical_view_identity,
            self.policy_identity,
            self.materiality_decision_identity,
            self.fact_bundle_identity,
            self.change_set_identity,
            self.current_state_identity,
            self.source_message_identity,
            self.story_identity,
            self.source_event_identity,
            self.stream_event_identity,
        ):
            _require_sha256(value, "family analytical identity")
        _require_text_tuple(
            self.materiality_reason_codes,
            "family analytical materiality reason",
        )
        _require_text_tuple(self.uncertainty_flags, "family analytical uncertainty")
        _require_text_tuple(
            self.changed_components,
            "family analytical changed component",
        )
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_ANALYTICAL_VIEW_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.analytical_view_identity != canonical_sha256(
            _family_analytical_payload(self)
        ):
            raise ValueError("Stream family analytical identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyNarrativePlan:
    plan_identity: str
    analytical_view_identity: str
    fact_bundle_identity: str
    change_set_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    family: StreamFamilyDomain
    state_label: str
    previous_state_label: str | None
    changed_components: tuple[str, ...]
    symbol: str
    timeframe: str
    event_at_ms: int
    schema_version: str = STREAM_FAMILY_NARRATIVE_PLAN_SCHEMA_VERSION
    voice_version: str = STREAM_NARRATIVE_VOICE_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value in (
            self.plan_identity,
            self.analytical_view_identity,
            self.fact_bundle_identity,
            self.change_set_identity,
            self.story_identity,
            self.source_event_identity,
            self.stream_event_identity,
        ):
            _require_sha256(value, "family narrative plan identity")
        _require_text_tuple(
            self.changed_components,
            "family narrative changed component",
        )
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_NARRATIVE_PLAN_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.voice_version != STREAM_NARRATIVE_VOICE_VERSION:
            raise ValueError("unsupported family narrative voice")
        if self.plan_identity != canonical_sha256(_family_plan_payload(self)):
            raise ValueError("Stream family narrative plan identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyNarrativeMessage:
    narrative_identity: str
    plan_identity: str
    analytical_view_identity: str
    fact_bundle_identity: str
    change_set_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    family: StreamFamilyDomain
    state_label: str
    symbol: str
    timeframe: str
    event_at_ms: int
    source_kind: StreamNarrativeSourceKind
    text: StreamNarrativeText
    validation: StreamNarrativeValidation
    original_text_preserved: bool = True
    schema_version: str = STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION
    renderer_version: str = STREAM_FAMILY_NARRATIVE_RENDERER_VERSION
    voice_version: str = STREAM_NARRATIVE_VOICE_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value in (
            self.narrative_identity,
            self.plan_identity,
            self.analytical_view_identity,
            self.fact_bundle_identity,
            self.change_set_identity,
            self.story_identity,
            self.source_event_identity,
            self.stream_event_identity,
        ):
            _require_sha256(value, "family narrative identity")
        if self.source_kind is not StreamNarrativeSourceKind.DETERMINISTIC:
            raise ValueError("F3 family narrative must be deterministic")
        if not self.validation.valid or not self.original_text_preserved:
            raise ValueError("F3 family narrative must preserve validated original text")
        _require_authority(
            self.schema_version,
            STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION,
            self.engine_version,
            self.read_only,
            self.production_authority,
            self.real_capital,
        )
        if self.renderer_version != STREAM_FAMILY_NARRATIVE_RENDERER_VERSION:
            raise ValueError("unsupported family narrative renderer")
        if self.voice_version != STREAM_NARRATIVE_VOICE_VERSION:
            raise ValueError("unsupported family narrative voice")
        if self.narrative_identity != canonical_sha256(
            _family_narrative_payload(self)
        ):
            raise ValueError("Stream family narrative identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamFamilyProjectionResult:
    disposition: StreamFamilyProjectionDisposition
    projector_id: str
    source_event_identity: str
    stream_event_identity: str | None
    story_identity: str
    narrative_identity: str | None
    activation_identity: str
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamFamilyRuntime:
    """Forward-only material source-family projection into canonical Stream tables."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamNarrativeLedger(self.path).initialize()
        with sqlite3.connect(self.path) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_family_projection_boundaries (
                    projector_id TEXT PRIMARY KEY,
                    activation_identity TEXT NOT NULL UNIQUE,
                    activated_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    stream_family_projection_boundaries_immutable_{operation.lower()}
                    BEFORE {operation} ON stream_family_projection_boundaries
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable intelligence stream family activation'
                        );
                    END
                    """
                )

    def ensure_projector_activation(
        self,
        projector_id: str,
        *,
        activated_at_ms: int,
    ) -> str:
        if not projector_id.strip() or activated_at_ms < 0:
            raise ValueError("invalid Stream family activation")
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            row = connection.execute(
                """
                SELECT activation_identity, activated_at_ms, payload_json, payload_sha256
                FROM stream_family_projection_boundaries
                WHERE projector_id = ?
                """,
                (projector_id,),
            ).fetchone()
            if row is not None:
                raw = str(row[2])
                if sha256_text(raw) != str(row[3]):
                    raise ValueError("Stream family activation digest mismatch")
                payload = json.loads(raw)
                if (
                    payload.get("activation_identity") != str(row[0])
                    or payload.get("activated_at_ms") != int(str(row[1]))
                    or payload.get("projector_id") != projector_id
                ):
                    raise ValueError("Stream family activation payload mismatch")
                return str(row[0])

            payload_without_identity = {
                "activated_at_ms": activated_at_ms,
                "engine_version": STREAM_ENGINE_VERSION,
                "historical_rich_backfill_allowed": False,
                "production_authority": False,
                "projector_id": projector_id,
                "read_only": True,
                "real_capital": REAL_CAPITAL,
                "schema_version": STREAM_FAMILY_ACTIVATION_SCHEMA_VERSION,
            }
            identity = canonical_sha256(payload_without_identity)
            payload = {"activation_identity": identity, **payload_without_identity}
            encoded = canonical_json(payload)
            connection.execute(
                """
                INSERT INTO stream_family_projection_boundaries (
                    projector_id,
                    activation_identity,
                    activated_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    projector_id,
                    identity,
                    activated_at_ms,
                    encoded,
                    sha256_text(encoded),
                ),
            )
            connection.commit()
            return identity

    def project(
        self,
        snapshot: StreamFamilySnapshot,
        *,
        activated_at_ms: int,
        silent_initial_state_labels: tuple[str, ...] = (),
    ) -> StreamFamilyProjectionResult:
        spec = _require_family_projector_spec(snapshot.projector_id)
        if snapshot.category is not spec.category:
            raise ValueError("Stream family projector/category mismatch")
        if snapshot.subtype not in spec.subtypes:
            raise ValueError("Stream family projector/subtype mismatch")
        activation_identity = self.ensure_projector_activation(
            snapshot.projector_id,
            activated_at_ms=activated_at_ms,
        )
        boundary_ms = self._projector_activation_ms(snapshot.projector_id)
        story_identity = _family_story_identity(snapshot)
        if snapshot.event_at_ms < boundary_ms:
            return StreamFamilyProjectionResult(
                disposition=StreamFamilyProjectionDisposition.SKIPPED_BEFORE_ACTIVATION,
                projector_id=snapshot.projector_id,
                source_event_identity=snapshot.source_event_identity,
                stream_event_identity=None,
                story_identity=story_identity,
                narrative_identity=None,
                activation_identity=activation_identity,
            )

        global_activation = IntelligenceStreamLedger(self.path).read_activation()
        global_activation_identity = _text(global_activation, "activation_identity")
        materiality_code = f"{snapshot.projector_id}_state_changed"
        source_event = _build_family_source_event(
            snapshot,
            activation_identity=global_activation_identity,
            materiality_code=materiality_code,
        )
        existing = self._existing_family_projection(
            source_event,
            projector_id=snapshot.projector_id,
            story_identity=story_identity,
            activation_identity=activation_identity,
        )
        if existing is not None:
            return existing

        previous = self._latest_family_state(story_identity)
        normalized_silent_initial = tuple(
            sorted(set(silent_initial_state_labels))
        )
        if (
            previous is None
            and snapshot.state_label in normalized_silent_initial
        ):
            return StreamFamilyProjectionResult(
                disposition=(
                    StreamFamilyProjectionDisposition.SILENT_INITIAL_BASELINE
                ),
                projector_id=snapshot.projector_id,
                source_event_identity=snapshot.source_event_identity,
                stream_event_identity=None,
                story_identity=story_identity,
                narrative_identity=None,
                activation_identity=activation_identity,
            )

        state_key = _snapshot_state_key(snapshot)
        if previous is not None and previous.get("state_key") == state_key:
            return StreamFamilyProjectionResult(
                disposition=StreamFamilyProjectionDisposition.SILENT_UNCHANGED,
                projector_id=snapshot.projector_id,
                source_event_identity=snapshot.source_event_identity,
                stream_event_identity=None,
                story_identity=story_identity,
                narrative_identity=None,
                activation_identity=activation_identity,
            )

        materiality = evaluate_stream_materiality(
            build_stream_materiality_policy(),
            source_event,
        )
        if materiality.disposition is not StreamPublicationDisposition.PUBLISH:
            raise ValueError(
                "implemented Stream family projector lacks publish materiality rule"
            )
        previous_fact = (
            None
            if previous is None
            else _text(previous, "current_fact_bundle_identity")
        )
        fact = _build_family_fact(
            snapshot,
            source_event=source_event,
            story_identity=story_identity,
            state_key=state_key,
            previous_fact_bundle_identity=previous_fact,
        )
        message = _build_family_message_input(
            snapshot,
            source_event=source_event,
            fact=fact,
            materiality_decision_identity=materiality.decision_identity,
            materiality=materiality.materiality,
            publication_disposition=materiality.disposition,
            materiality_policy_identity=materiality.policy_identity,
            materiality_policy_version=materiality.policy_version,
        )
        observation, state, change = _build_family_story(
            snapshot,
            fact=fact,
            message=message,
            previous=previous,
        )
        analytical = _build_family_analytical(
            snapshot,
            fact=fact,
            message=message,
            state=state,
            change=change,
            materiality_decision_identity=materiality.decision_identity,
            materiality_policy_identity=materiality.policy_identity,
            materiality_policy_version=materiality.policy_version,
            materiality_reason_codes=materiality.reason_codes,
        )
        plan, narrative = _build_family_narrative(
            snapshot,
            fact=fact,
            state=state,
            change=change,
            analytical=analytical,
        )

        disposition = self._append_atomic(
            source_event=source_event,
            fact=fact,
            message=message,
            observation=observation,
            state=state,
            change=change,
            analytical=analytical,
            plan=plan,
            narrative=narrative,
        )
        return StreamFamilyProjectionResult(
            disposition=disposition,
            projector_id=snapshot.projector_id,
            source_event_identity=snapshot.source_event_identity,
            stream_event_identity=source_event.stream_event_identity,
            story_identity=story_identity,
            narrative_identity=narrative.narrative_identity,
            activation_identity=activation_identity,
        )

    def projector_activation_ms(self, projector_id: str) -> int:
        return self._projector_activation_ms(projector_id)

    def _projector_activation_ms(self, projector_id: str) -> int:
        with self._connect_ro() as connection:
            row = connection.execute(
                """
                SELECT activated_at_ms
                FROM stream_family_projection_boundaries
                WHERE projector_id = ?
                """,
                (projector_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Stream family activation missing")
        return int(str(row[0]))

    def _existing_family_projection(
        self,
        source_event: StreamSourceEvent,
        *,
        projector_id: str,
        story_identity: str,
        activation_identity: str,
    ) -> StreamFamilyProjectionResult | None:
        with self._connect_ro() as connection:
            row = connection.execute(
                """
                SELECT
                    s.stream_event_identity,
                    s.payload_json,
                    s.payload_sha256,
                    n.narrative_identity,
                    n.story_identity
                FROM stream_source_events AS s
                LEFT JOIN stream_narrative_messages AS n
                  ON n.stream_event_identity = s.stream_event_identity
                WHERE s.source_event_identity = ?
                """,
                (source_event.source_event_identity,),
            ).fetchone()
        if row is None:
            return None
        source_json = canonical_json(source_event)
        if (
            str(row[0]) != source_event.stream_event_identity
            or str(row[1]) != source_json
            or str(row[2]) != sha256_text(source_json)
        ):
            raise ValueError("immutable Stream family source replay conflict")
        if row[3] is None or row[4] is None:
            raise ValueError("partial immutable Stream family projection exists")
        narrative_identity = str(row[3])
        persisted_story_identity = str(row[4])
        if persisted_story_identity != story_identity:
            raise ValueError("Stream family replay story identity mismatch")
        _require_sha256(narrative_identity, "Stream family replay narrative identity")
        return StreamFamilyProjectionResult(
            disposition=StreamFamilyProjectionDisposition.UNCHANGED,
            projector_id=projector_id,
            source_event_identity=source_event.source_event_identity,
            stream_event_identity=source_event.stream_event_identity,
            story_identity=story_identity,
            narrative_identity=narrative_identity,
            activation_identity=activation_identity,
        )

    def _latest_family_state(self, story_identity: str) -> dict[str, Any] | None:
        with self._connect_ro() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM stream_story_states
                WHERE story_identity = ?
                ORDER BY event_at_ms DESC, state_identity DESC
                LIMIT 1
                """,
                (story_identity,),
            ).fetchone()
        if row is None:
            return None
        payload_json = str(row[0])
        if sha256_text(payload_json) != str(row[1]):
            raise ValueError("Stream family latest-state digest mismatch")
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise TypeError("Stream family latest state must decode to object")
        if raw.get("schema_version") != STREAM_FAMILY_STORY_STATE_SCHEMA_VERSION:
            raise ValueError("Stream family story collided with non-family schema")
        return raw

    def _append_atomic(
        self,
        *,
        source_event: StreamSourceEvent,
        fact: StreamFamilyFactBundle,
        message: StreamMessageInput,
        observation: StreamFamilyStoryObservation,
        state: StreamFamilyStoryState,
        change: StreamFamilyChangeSet,
        analytical: StreamFamilyAnalyticalView,
        plan: StreamFamilyNarrativePlan,
        narrative: StreamFamilyNarrativeMessage,
    ) -> StreamFamilyProjectionDisposition:
        self.initialize()
        records = {
            "source": (source_event.stream_event_identity, canonical_json(source_event)),
            "fact": (fact.fact_bundle_identity, canonical_json(fact)),
            "message": (message.message_identity, canonical_json(message)),
            "observation": (observation.observation_identity, canonical_json(observation)),
            "state": (state.state_identity, canonical_json(state)),
            "change": (change.change_set_identity, canonical_json(change)),
            "analytical": (
                analytical.analytical_view_identity,
                canonical_json(analytical),
            ),
            "plan": (plan.plan_identity, canonical_json(plan)),
            "narrative": (narrative.narrative_identity, canonical_json(narrative)),
        }
        with sqlite3.connect(self.path, timeout=30.0) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT n.narrative_identity, n.payload_json, n.payload_sha256
                FROM stream_narrative_messages AS n
                WHERE n.stream_event_identity = ?
                """,
                (source_event.stream_event_identity,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == narrative.narrative_identity
                    and str(existing[1]) == records["narrative"][1]
                    and str(existing[2]) == sha256_text(records["narrative"][1])
                ):
                    connection.rollback()
                    return StreamFamilyProjectionDisposition.UNCHANGED
                raise ValueError("immutable Stream family replay conflict")

            source_json = records["source"][1]
            connection.execute(
                """
                INSERT INTO stream_source_events (
                    stream_event_identity,
                    source_event_identity,
                    activation_identity,
                    decision_context_identity,
                    category,
                    subtype,
                    event_at_ms,
                    source_as_of_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_event.stream_event_identity,
                    source_event.source_event_identity,
                    source_event.activation_identity,
                    source_event.category.value,
                    source_event.subtype,
                    source_event.event_at_ms,
                    source_event.source_as_of_ms,
                    source_json,
                    sha256_text(source_json),
                ),
            )
            fact_json = records["fact"][1]
            connection.execute(
                """
                INSERT INTO stream_fact_bundles (
                    fact_bundle_identity,
                    stream_event_identity,
                    source_event_identity,
                    story_identity,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact.fact_bundle_identity,
                    fact.stream_event_identity,
                    fact.source_event_identity,
                    fact.story_identity,
                    fact.event_at_ms,
                    fact_json,
                    sha256_text(fact_json),
                ),
            )
            message_json = records["message"][1]
            connection.execute(
                """
                INSERT INTO stream_message_inputs (
                    message_identity,
                    stream_event_identity,
                    source_event_identity,
                    story_identity,
                    fact_bundle_identity,
                    category,
                    subtype,
                    importance,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_identity,
                    message.stream_event_identity,
                    message.source_event_identity,
                    message.story_identity,
                    message.fact_bundle_identity,
                    message.category.value,
                    message.subtype,
                    message.importance.value,
                    message.event_at_ms,
                    message_json,
                    sha256_text(message_json),
                ),
            )
            observation_json = records["observation"][1]
            connection.execute(
                """
                INSERT INTO stream_story_observations (
                    observation_identity, story_identity, source_event_identity,
                    stream_event_identity, message_identity,
                    previous_state_identity, event_at_ms,
                    payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_identity,
                    observation.story_identity,
                    observation.source_event_identity,
                    observation.stream_event_identity,
                    observation.message_identity,
                    observation.previous_state_identity,
                    observation.event_at_ms,
                    observation_json,
                    sha256_text(observation_json),
                ),
            )
            state_json = records["state"][1]
            connection.execute(
                """
                INSERT INTO stream_story_states (
                    state_identity, story_identity, observation_identity,
                    source_event_identity, current_stream_event_identity,
                    current_message_identity, previous_state_identity,
                    event_at_ms, payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.state_identity,
                    state.story_identity,
                    state.observation_identity,
                    state.source_event_identity,
                    state.current_stream_event_identity,
                    state.current_message_identity,
                    state.previous_state_identity,
                    state.event_at_ms,
                    state_json,
                    sha256_text(state_json),
                ),
            )
            change_json = records["change"][1]
            connection.execute(
                """
                INSERT INTO stream_story_change_sets (
                    change_set_identity, story_identity, current_state_identity,
                    previous_state_identity, payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    change.change_set_identity,
                    change.story_identity,
                    change.current_state_identity,
                    change.previous_state_identity,
                    change_json,
                    sha256_text(change_json),
                ),
            )
            analytical_json = records["analytical"][1]
            connection.execute(
                """
                INSERT INTO stream_analytical_views (
                    analytical_view_identity, policy_identity,
                    fact_bundle_identity, change_set_identity,
                    current_state_identity, source_message_identity,
                    story_identity, source_event_identity,
                    stream_event_identity, event_at_ms,
                    payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analytical.analytical_view_identity,
                    analytical.policy_identity,
                    analytical.fact_bundle_identity,
                    analytical.change_set_identity,
                    analytical.current_state_identity,
                    analytical.source_message_identity,
                    analytical.story_identity,
                    analytical.source_event_identity,
                    analytical.stream_event_identity,
                    analytical.event_at_ms,
                    analytical_json,
                    sha256_text(analytical_json),
                ),
            )
            plan_json = records["plan"][1]
            connection.execute(
                """
                INSERT INTO stream_narrative_plans (
                    plan_identity, analytical_view_identity,
                    fact_bundle_identity, change_set_identity,
                    story_identity, source_event_identity,
                    stream_event_identity, event_at_ms,
                    payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_identity,
                    plan.analytical_view_identity,
                    plan.fact_bundle_identity,
                    plan.change_set_identity,
                    plan.story_identity,
                    plan.source_event_identity,
                    plan.stream_event_identity,
                    plan.event_at_ms,
                    plan_json,
                    sha256_text(plan_json),
                ),
            )
            narrative_json = records["narrative"][1]
            connection.execute(
                """
                INSERT INTO stream_narrative_messages (
                    narrative_identity, plan_identity,
                    analytical_view_identity, story_identity,
                    source_event_identity, stream_event_identity,
                    event_at_ms, source_kind, payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    narrative.narrative_identity,
                    narrative.plan_identity,
                    narrative.analytical_view_identity,
                    narrative.story_identity,
                    narrative.source_event_identity,
                    narrative.stream_event_identity,
                    narrative.event_at_ms,
                    narrative.source_kind.value,
                    narrative_json,
                    sha256_text(narrative_json),
                ),
            )
            connection.commit()
        return StreamFamilyProjectionDisposition.INSERTED

    def _connect_ro(self) -> sqlite3.Connection:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=10.0)
        connection.execute("PRAGMA query_only=ON")
        return connection


def build_family_snapshot(
    *,
    projector_id: str,
    family: StreamFamilyDomain,
    category: StreamCategory,
    subtype: str,
    importance: StreamImportance,
    source_event_identity: str,
    source_scope: str,
    asset: str,
    symbol: str,
    market: str,
    timeframe: str,
    event_at_ms: int,
    source_as_of_ms: int,
    evidence_identities: tuple[str, ...],
    evidence_domains: tuple[str, ...],
    state_label: str,
    state_components: tuple[tuple[str, str], ...],
    direction: str | None,
    source_quality: str,
    uncertainty_flags: tuple[str, ...] = (),
) -> StreamFamilySnapshot:
    components = tuple(
        sorted(
            (
                StreamFamilyStateComponent(name=str(name), value=str(value))
                for name, value in state_components
            ),
            key=lambda item: item.name,
        )
    )
    return StreamFamilySnapshot(
        projector_id=projector_id,
        family=family,
        category=category,
        subtype=subtype,
        importance=importance,
        source_event_identity=source_event_identity,
        source_scope=source_scope,
        asset=asset,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        evidence_identities=tuple(sorted(set(evidence_identities))),
        evidence_domains=tuple(sorted(set(evidence_domains))),
        state_label=state_label,
        state_components=components,
        direction=direction,
        source_quality=source_quality,
        uncertainty_flags=tuple(sorted(set(uncertainty_flags))),
    )


def _build_family_source_event(
    snapshot: StreamFamilySnapshot,
    *,
    activation_identity: str,
    materiality_code: str,
) -> StreamSourceEvent:
    payload = {
        "activation_identity": activation_identity,
        "asset": snapshot.asset,
        "category": snapshot.category,
        "decision_context_identity": None,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "evidence_identities": snapshot.evidence_identities,
        "forecast_identity": None,
        "importance": snapshot.importance,
        "materiality_codes": (materiality_code,),
        "production_authority": False,
        "proof_identity": None,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": None,
        "schema_version": "intelligence-stream-source-event-v1/1",
        "source_as_of_ms": snapshot.source_as_of_ms,
        "source_event_identity": snapshot.source_event_identity,
        "subtype": snapshot.subtype,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation_identity,
        source_event_identity=snapshot.source_event_identity,
        category=snapshot.category,
        subtype=snapshot.subtype,
        importance=snapshot.importance,
        asset=snapshot.asset,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
        source_as_of_ms=snapshot.source_as_of_ms,
        forecast_identity=None,
        proof_identity=None,
        resolution_identity=None,
        decision_context_identity=None,
        evidence_identities=snapshot.evidence_identities,
        materiality_codes=(materiality_code,),
    )


def _family_story_identity(snapshot: StreamFamilySnapshot) -> str:
    return canonical_sha256(
        {
            "family": snapshot.family,
            "projector_id": snapshot.projector_id,
            "source_scope": snapshot.source_scope,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "version": "stream-family-story-v1/1",
        }
    )


def _snapshot_state_key(snapshot: StreamFamilySnapshot) -> str:
    return canonical_sha256(
        {
            "direction": snapshot.direction,
            "family": snapshot.family,
            "source_quality": snapshot.source_quality,
            "state_components": snapshot.state_components,
            "state_label": snapshot.state_label,
            "uncertainty_flags": snapshot.uncertainty_flags,
            "version": "stream-family-state-key-v1/1",
        }
    )


def _build_family_fact(
    snapshot: StreamFamilySnapshot,
    *,
    source_event: StreamSourceEvent,
    story_identity: str,
    state_key: str,
    previous_fact_bundle_identity: str | None,
) -> StreamFamilyFactBundle:
    payload = _family_fact_payload_values(
        stream_event_identity=source_event.stream_event_identity,
        source_event_identity=source_event.source_event_identity,
        story_identity=story_identity,
        projector_id=snapshot.projector_id,
        family=snapshot.family,
        source_scope=snapshot.source_scope,
        asset=snapshot.asset,
        symbol=snapshot.symbol,
        market=snapshot.market,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
        source_as_of_ms=snapshot.source_as_of_ms,
        evidence_identities=snapshot.evidence_identities,
        available_evidence_domains=snapshot.evidence_domains,
        state_label=snapshot.state_label,
        state_key=state_key,
        state_components=snapshot.state_components,
        direction=snapshot.direction,
        source_quality=snapshot.source_quality,
        uncertainty_flags=snapshot.uncertainty_flags,
        previous_fact_bundle_identity=previous_fact_bundle_identity,
    )
    return StreamFamilyFactBundle(
        fact_bundle_identity=canonical_sha256(payload),
        stream_event_identity=source_event.stream_event_identity,
        source_event_identity=source_event.source_event_identity,
        story_identity=story_identity,
        projector_id=snapshot.projector_id,
        family=snapshot.family,
        source_scope=snapshot.source_scope,
        asset=snapshot.asset,
        symbol=snapshot.symbol,
        market=snapshot.market,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
        source_as_of_ms=snapshot.source_as_of_ms,
        evidence_identities=snapshot.evidence_identities,
        available_evidence_domains=snapshot.evidence_domains,
        state_label=snapshot.state_label,
        state_key=state_key,
        state_components=snapshot.state_components,
        direction=snapshot.direction,
        source_quality=snapshot.source_quality,
        uncertainty_flags=snapshot.uncertainty_flags,
        previous_fact_bundle_identity=previous_fact_bundle_identity,
    )

def _build_family_message_input(
    snapshot: StreamFamilySnapshot,
    *,
    source_event: StreamSourceEvent,
    fact: StreamFamilyFactBundle,
    materiality_decision_identity: str,
    materiality: StreamMateriality,
    publication_disposition: StreamPublicationDisposition,
    materiality_policy_identity: str,
    materiality_policy_version: str,
) -> StreamMessageInput:
    search = StreamSearchMetadata(
        asset=snapshot.asset,
        symbol=snapshot.symbol,
        market=snapshot.market,
        timeframe=snapshot.timeframe,
        category=snapshot.category,
        importance=snapshot.importance,
        evidence_domains=snapshot.evidence_domains,
        states=(snapshot.state_label,),
        vaults=(),
        search_terms=tuple(
            sorted(
                {
                    snapshot.asset.lower(),
                    snapshot.symbol.lower(),
                    snapshot.market.lower(),
                    snapshot.timeframe.lower(),
                    snapshot.family.value,
                    snapshot.state_label.lower(),
                    snapshot.category.value,
                    snapshot.subtype,
                }
            )
        ),
    )
    payload = {
        "analytical_view_version": None,
        "asset": snapshot.asset,
        "capital_reference_identities": (),
        "category": snapshot.category,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "evidence_reference_identities": snapshot.evidence_identities,
        "fact_bundle_identity": fact.fact_bundle_identity,
        "importance": snapshot.importance,
        "market": snapshot.market,
        "materiality": materiality,
        "materiality_decision_identity": materiality_decision_identity,
        "materiality_policy_identity": materiality_policy_identity,
        "materiality_policy_version": materiality_policy_version,
        "narrative_schema_version": None,
        "publication_disposition": publication_disposition,
        "production_authority": False,
        "projector_version": STREAM_MESSAGE_PROJECTOR_VERSION,
        "proof_reference_identities": (),
        "read_only": True,
        "ready_for_analysis": True,
        "ready_for_publication": False,
        "real_capital": REAL_CAPITAL,
        "relations": (),
        "renderer_version": None,
        "schema_version": STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
        "search_metadata": search,
        "source_as_of_ms": snapshot.source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "story_identity": fact.story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": snapshot.subtype,
        "supersedes_message_identity": None,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
    }
    return StreamMessageInput(
        message_identity=canonical_sha256(payload),
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        story_identity=fact.story_identity,
        fact_bundle_identity=fact.fact_bundle_identity,
        category=snapshot.category,
        subtype=snapshot.subtype,
        importance=snapshot.importance,
        materiality=materiality,
        materiality_decision_identity=materiality_decision_identity,
        materiality_policy_identity=materiality_policy_identity,
        materiality_policy_version=materiality_policy_version,
        publication_disposition=publication_disposition,
        asset=snapshot.asset,
        symbol=snapshot.symbol,
        market=snapshot.market,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
        source_as_of_ms=snapshot.source_as_of_ms,
        evidence_reference_identities=snapshot.evidence_identities,
        proof_reference_identities=(),
        capital_reference_identities=(),
        relations=(),
        supersedes_message_identity=None,
        search_metadata=search,
    )


def _build_family_story(
    snapshot: StreamFamilySnapshot,
    *,
    fact: StreamFamilyFactBundle,
    message: StreamMessageInput,
    previous: dict[str, Any] | None,
) -> tuple[
    StreamFamilyStoryObservation,
    StreamFamilyStoryState,
    StreamFamilyChangeSet,
]:
    previous_state_identity = (
        None if previous is None else _text(previous, "state_identity")
    )
    previous_message_identity = (
        None if previous is None else _text(previous, "current_message_identity")
    )
    observation_payload = {
        "asset": snapshot.asset,
        "current_fact_bundle_identity": fact.fact_bundle_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "family": snapshot.family,
        "message_identity": message.message_identity,
        "previous_state_identity": previous_state_identity,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_FAMILY_STORY_OBSERVATION_SCHEMA_VERSION,
        "source_event_identity": fact.source_event_identity,
        "state_components": fact.state_components,
        "state_key": fact.state_key,
        "state_label": fact.state_label,
        "story_identity": fact.story_identity,
        "stream_event_identity": fact.stream_event_identity,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
    }
    observation = StreamFamilyStoryObservation(
        observation_identity=canonical_sha256(observation_payload),
        story_identity=fact.story_identity,
        source_event_identity=fact.source_event_identity,
        stream_event_identity=fact.stream_event_identity,
        message_identity=message.message_identity,
        previous_state_identity=previous_state_identity,
        current_fact_bundle_identity=fact.fact_bundle_identity,
        family=snapshot.family,
        state_label=fact.state_label,
        state_key=fact.state_key,
        state_components=fact.state_components,
        event_at_ms=fact.event_at_ms,
        asset=fact.asset,
        symbol=fact.symbol,
        timeframe=fact.timeframe,
    )
    state_payload = {
        "asset": snapshot.asset,
        "current_fact_bundle_identity": fact.fact_bundle_identity,
        "current_message_identity": message.message_identity,
        "current_stream_event_identity": fact.stream_event_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "family": snapshot.family,
        "observation_identity": observation.observation_identity,
        "previous_state_identity": previous_state_identity,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_FAMILY_STORY_STATE_SCHEMA_VERSION,
        "source_event_identity": fact.source_event_identity,
        "state_components": fact.state_components,
        "state_key": fact.state_key,
        "state_label": fact.state_label,
        "story_identity": fact.story_identity,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
    }
    state = StreamFamilyStoryState(
        state_identity=canonical_sha256(state_payload),
        story_identity=fact.story_identity,
        observation_identity=observation.observation_identity,
        source_event_identity=fact.source_event_identity,
        current_stream_event_identity=fact.stream_event_identity,
        current_message_identity=message.message_identity,
        previous_state_identity=previous_state_identity,
        current_fact_bundle_identity=fact.fact_bundle_identity,
        family=snapshot.family,
        state_label=fact.state_label,
        state_key=fact.state_key,
        state_components=fact.state_components,
        event_at_ms=fact.event_at_ms,
        asset=fact.asset,
        symbol=fact.symbol,
        timeframe=fact.timeframe,
    )
    previous_components = (
        {}
        if previous is None
        else _previous_state_components(previous)
    )
    current_components = {item.name: item.value for item in fact.state_components}
    changed_names = tuple(
        sorted(
            name
            for name in set(previous_components) | set(current_components)
            if previous_components.get(name) != current_components.get(name)
        )
    )
    if not changed_names:
        changed_names = ("state_key",)
    previous_state_label = (
        None if previous is None else _text(previous, "state_label")
    )
    change_payload = {
        "changed_components": changed_names,
        "current_message_identity": message.message_identity,
        "current_state_identity": state.state_identity,
        "current_state_label": state.state_label,
        "engine_version": STREAM_ENGINE_VERSION,
        "previous_message_identity": previous_message_identity,
        "previous_state_identity": previous_state_identity,
        "previous_state_label": previous_state_label,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_FAMILY_CHANGE_SET_SCHEMA_VERSION,
        "story_identity": state.story_identity,
        "story_started": previous is None,
    }
    change = StreamFamilyChangeSet(
        change_set_identity=canonical_sha256(change_payload),
        story_identity=state.story_identity,
        previous_state_identity=previous_state_identity,
        current_state_identity=state.state_identity,
        previous_message_identity=previous_message_identity,
        current_message_identity=message.message_identity,
        previous_state_label=previous_state_label,
        current_state_label=state.state_label,
        changed_components=changed_names,
        story_started=previous is None,
    )
    return observation, state, change


def _build_family_analytical(
    snapshot: StreamFamilySnapshot,
    *,
    fact: StreamFamilyFactBundle,
    message: StreamMessageInput,
    state: StreamFamilyStoryState,
    change: StreamFamilyChangeSet,
    materiality_decision_identity: str,
    materiality_policy_identity: str,
    materiality_policy_version: str,
    materiality_reason_codes: tuple[str, ...],
) -> StreamFamilyAnalyticalView:
    payload = {
        "asset": snapshot.asset,
        "change_set_identity": change.change_set_identity,
        "changed_components": change.changed_components,
        "current_state_identity": state.state_identity,
        "direction": snapshot.direction,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "fact_bundle_identity": fact.fact_bundle_identity,
        "family": snapshot.family,
        "family_state_label": snapshot.state_label,
        "materiality_decision_identity": materiality_decision_identity,
        "materiality_reason_codes": materiality_reason_codes,
        "policy_identity": materiality_policy_identity,
        "policy_version": materiality_policy_version,
        "previous_family_state_label": change.previous_state_label,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_FAMILY_ANALYTICAL_VIEW_SCHEMA_VERSION,
        "source_event_identity": fact.source_event_identity,
        "source_message_identity": message.message_identity,
        "source_quality": snapshot.source_quality,
        "story_identity": fact.story_identity,
        "stream_event_identity": fact.stream_event_identity,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "uncertainty_flags": snapshot.uncertainty_flags,
    }
    return StreamFamilyAnalyticalView(
        analytical_view_identity=canonical_sha256(payload),
        policy_identity=materiality_policy_identity,
        policy_version=materiality_policy_version,
        materiality_decision_identity=materiality_decision_identity,
        materiality_reason_codes=materiality_reason_codes,
        fact_bundle_identity=fact.fact_bundle_identity,
        change_set_identity=change.change_set_identity,
        current_state_identity=state.state_identity,
        source_message_identity=message.message_identity,
        story_identity=fact.story_identity,
        source_event_identity=fact.source_event_identity,
        stream_event_identity=fact.stream_event_identity,
        family=snapshot.family,
        family_state_label=snapshot.state_label,
        previous_family_state_label=change.previous_state_label,
        direction=snapshot.direction,
        source_quality=snapshot.source_quality,
        uncertainty_flags=snapshot.uncertainty_flags,
        changed_components=change.changed_components,
        asset=snapshot.asset,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
    )


def _build_family_narrative(
    snapshot: StreamFamilySnapshot,
    *,
    fact: StreamFamilyFactBundle,
    state: StreamFamilyStoryState,
    change: StreamFamilyChangeSet,
    analytical: StreamFamilyAnalyticalView,
) -> tuple[StreamFamilyNarrativePlan, StreamFamilyNarrativeMessage]:
    plan_payload = {
        "analytical_view_identity": analytical.analytical_view_identity,
        "change_set_identity": change.change_set_identity,
        "changed_components": change.changed_components,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "fact_bundle_identity": fact.fact_bundle_identity,
        "family": snapshot.family,
        "previous_state_label": change.previous_state_label,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_FAMILY_NARRATIVE_PLAN_SCHEMA_VERSION,
        "source_event_identity": fact.source_event_identity,
        "state_label": snapshot.state_label,
        "story_identity": fact.story_identity,
        "stream_event_identity": fact.stream_event_identity,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "voice_version": STREAM_NARRATIVE_VOICE_VERSION,
    }
    plan = StreamFamilyNarrativePlan(
        plan_identity=canonical_sha256(plan_payload),
        analytical_view_identity=analytical.analytical_view_identity,
        fact_bundle_identity=fact.fact_bundle_identity,
        change_set_identity=change.change_set_identity,
        story_identity=fact.story_identity,
        source_event_identity=fact.source_event_identity,
        stream_event_identity=fact.stream_event_identity,
        family=snapshot.family,
        state_label=snapshot.state_label,
        previous_state_label=change.previous_state_label,
        changed_components=change.changed_components,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
    )
    text = _render_family_text(snapshot, change)
    validation = StreamNarrativeValidation(
        valid=True,
        violation_codes=(),
        observed_numeric_values=(),
        validator_version=STREAM_NARRATIVE_VALIDATOR_VERSION,
    )
    narrative_payload = {
        "analytical_view_identity": analytical.analytical_view_identity,
        "change_set_identity": change.change_set_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": snapshot.event_at_ms,
        "fact_bundle_identity": fact.fact_bundle_identity,
        "family": snapshot.family,
        "original_text_preserved": True,
        "plan_identity": plan.plan_identity,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "renderer_version": STREAM_FAMILY_NARRATIVE_RENDERER_VERSION,
        "schema_version": STREAM_FAMILY_NARRATIVE_MESSAGE_SCHEMA_VERSION,
        "source_event_identity": fact.source_event_identity,
        "source_kind": StreamNarrativeSourceKind.DETERMINISTIC,
        "state_label": snapshot.state_label,
        "story_identity": fact.story_identity,
        "stream_event_identity": fact.stream_event_identity,
        "symbol": snapshot.symbol,
        "text": text,
        "timeframe": snapshot.timeframe,
        "validation": validation,
        "voice_version": STREAM_NARRATIVE_VOICE_VERSION,
    }
    narrative = StreamFamilyNarrativeMessage(
        narrative_identity=canonical_sha256(narrative_payload),
        plan_identity=plan.plan_identity,
        analytical_view_identity=analytical.analytical_view_identity,
        fact_bundle_identity=fact.fact_bundle_identity,
        change_set_identity=change.change_set_identity,
        story_identity=fact.story_identity,
        source_event_identity=fact.source_event_identity,
        stream_event_identity=fact.stream_event_identity,
        family=snapshot.family,
        state_label=snapshot.state_label,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        event_at_ms=snapshot.event_at_ms,
        source_kind=StreamNarrativeSourceKind.DETERMINISTIC,
        text=text,
        validation=validation,
    )
    return plan, narrative


def _render_family_text(
    snapshot: StreamFamilySnapshot,
    change: StreamFamilyChangeSet,
) -> StreamNarrativeText:
    if isinstance(snapshot.family, StreamTrustDomain):
        return _render_trust_family_text(snapshot, change)

    family_label = {
        ConfluenceFamily.GEOMETRY: "Geometri / Piyasa Yapısı",
        ConfluenceFamily.LIQUIDITY: "Likidite",
        ConfluenceFamily.ORDER_FLOW: "Emir Akışı",
        ConfluenceFamily.DERIVATIVES: "Türevler",
        ConfluenceFamily.ONCHAIN: "On-chain",
    }[snapshot.family]
    collapsed = _family_customer_summary(snapshot, change)
    simple = (
        f"{collapsed} Bu katman toplam sistem görüşünün yalnızca bir parçasıdır; "
        "tek başına işlem kararı değildir."
    )
    changed = (
        "ilk kayıt"
        if change.story_started
        else ", ".join(change.changed_components)
    )
    uncertainty = (
        " Belirsizlik kodları: " + ", ".join(snapshot.uncertainty_flags) + "."
        if snapshot.uncertainty_flags
        else ""
    )
    technical = (
        f"{family_label} exact persisted evidence ile güncellendi. "
        f"Raw durum: {snapshot.state_label}. "
        f"Değişen bileşenler: {changed}. "
        f"Kaynak kalitesi: {snapshot.source_quality}.{uncertainty}"
    )
    intelligence = simple
    decision = (
        "Bu tek kanıt ailesindeki değişimi bildirir. Toplam yön görüşü; "
        "Geometri, Likidite, Emir Akışı, Türevler ve mevcutsa On-chain kanıtları "
        "birlikte değerlendirilmeden çıkarılmaz."
    )
    capital = (
        "Bu kanıt ailesi mesajı canonical sanal-sermaye durumunu tek başına "
        "değiştirmez. REAL_CAPITAL=0."
    )
    return StreamNarrativeText(
        collapsed_text=collapsed,
        simple_text=simple,
        technical_text=technical,
        intelligence_text=intelligence,
        decision_text=decision,
        capital_text=capital,
    )


def _family_customer_summary(
    snapshot: StreamFamilySnapshot,
    change: StreamFamilyChangeSet,
) -> str:
    if snapshot.family is ConfluenceFamily.GEOMETRY:
        return _geometry_customer_summary(snapshot)
    if snapshot.family is ConfluenceFamily.LIQUIDITY:
        return _liquidity_customer_summary(snapshot)
    if snapshot.family is ConfluenceFamily.ORDER_FLOW:
        return _order_flow_customer_summary(snapshot, change)
    if snapshot.family is ConfluenceFamily.DERIVATIVES:
        return _derivatives_customer_summary(snapshot)
    if snapshot.family is ConfluenceFamily.ONCHAIN:
        return _onchain_customer_summary(snapshot)
    raise ValueError("unsupported Stream family narrative domain")


def _onchain_customer_summary(snapshot: StreamFamilySnapshot) -> str:
    components = _snapshot_components(snapshot)
    status = components.get("onchain_status", snapshot.state_label)
    if (
        snapshot.source_quality.lower() == "unavailable"
        or status == "unavailable"
    ):
        return (
            "On-chain tarafında kabul edilmiş güncel canlı sermaye akışı "
            "bağlamı yok; bu katmanı yön görüşüne eklemiyorum."
        )
    if status == "stablecoin_context_partial":
        return (
            "Stablecoin dolaşım arzı bağlamının bir bölümü canlı ve exact "
            "kaynak zinciriyle ölçülüyor; bunu doğrudan yükseliş veya düşüş "
            "sinyali saymıyorum."
        )
    return (
        "USDT ve USDC dolaşım arzı bağlamı canlı ve exact kaynak zinciriyle "
        "ölçülüyor; arz değişimini tek başına yükseliş veya düşüş sinyali "
        "saymıyorum."
    )


def _snapshot_components(snapshot: StreamFamilySnapshot) -> dict[str, str]:
    return {item.name: item.value for item in snapshot.state_components}


def _direction_phrase(direction: str | None) -> str | None:
    if direction == "bullish":
        return "yukarı yönlü"
    if direction == "bearish":
        return "aşağı yönlü"
    return None


def _geometry_customer_summary(snapshot: StreamFamilySnapshot) -> str:
    components = _snapshot_components(snapshot)
    direction = _direction_phrase(snapshot.direction)
    signal_state = components.get("signal_state", "")
    to_state = components.get("to_state", "")

    if snapshot.subtype == "trigger_transition" or to_state == "invalidated":
        if direction is not None:
            return (
                f"Önceki {direction} senaryo geçersizleşti; takip ettiğim piyasa "
                "yapısı artık korunmuyor."
            )
        return (
            "Önceki piyasa senaryosu geçersizleşti; takip ettiğim yapı artık "
            "korunmuyor."
        )

    if signal_state in {"no_signal", "neutral"} or snapshot.direction in {None, "none"}:
        return (
            "Piyasa yapısı şu anda net bir yön beklentisi üretmiyor; yeni bir "
            "teyit oluşmasını bekliyorum."
        )

    if signal_state == "active" and direction is not None:
        return (
            f"{direction.capitalize()} senaryo aktif; tanımlı piyasa yapısı ve "
            "geçersizlik sınırı korunuyor."
        )

    if direction is not None:
        return (
            f"{direction.capitalize()} bir senaryoyu izliyorum; görüşü "
            "güçlendirmek için ek teyit bekliyorum."
        )

    return (
        "Piyasa yapısında yeni bir değişim var ancak bu değişim tek başına net "
        "bir yön beklentisi üretmiyor."
    )


def _liquidity_customer_summary(snapshot: StreamFamilySnapshot) -> str:
    components = _snapshot_components(snapshot)
    candidate = (
        components.get("liquidity_take_candidate")
        or components.get("candidate")
        or snapshot.state_label
    ).lower()
    state = snapshot.state_label.lower()
    quality = snapshot.source_quality.lower()

    if (
        "unavailable" in candidate
        or "unresolved" in state
        or quality in {"degraded", "unavailable", "unresolved"}
    ):
        return (
            "Likidite görünümü için yeterli güncel ve güvenilir kanıt yok; bu "
            "katmanda yön teyidi vermiyorum."
        )
    if "both_sides" in candidate:
        return (
            "Tahtanın iki tarafındaki bekleyen emirlerde belirgin azalma "
            "ölçüldü; kısa vadeli yapı karışık ve ek teyit gerekiyor."
        )
    if "bid_side" in candidate:
        return (
            "Tahtanın alış tarafındaki bekleyen emirlerde belirgin azalma "
            "ölçüldü; bunu tek başına yön sinyali olarak kullanmıyorum."
        )
    if "ask_side" in candidate:
        return (
            "Tahtanın satış tarafındaki bekleyen emirlerde belirgin azalma "
            "ölçüldü; bunu tek başına yön sinyali olarak kullanmıyorum."
        )
    return (
        "Likidite tarafında belirgin bir hızlı çekilme ölçülmedi; ana görüş için "
        "diğer kanıtların teyidini bekliyorum."
    )


def _order_flow_customer_summary(
    snapshot: StreamFamilySnapshot,
    change: StreamFamilyChangeSet,
) -> str:
    current = snapshot.state_label.lower()
    previous = (change.previous_state_label or "").lower()

    if current == "buy_pressure":
        if previous and previous != current:
            return (
                "Emir akışı alıcılar lehine netleşti; kısa vadede yukarı yönlü "
                "baskı güçlendi."
            )
        return (
            "Alıcı baskısı korunuyor; emir akışı kısa vadede yukarı yönü "
            "destekliyor."
        )

    if current == "sell_pressure":
        if previous and previous != current:
            return (
                "Emir akışı satıcılar lehine netleşti; kısa vadede aşağı yönlü "
                "baskı güçlendi."
            )
        return (
            "Satıcı baskısı korunuyor; emir akışı kısa vadede aşağı yönü "
            "destekliyor."
        )

    if current in {"mixed", "balanced"}:
        if previous == "sell_pressure":
            return (
                "Önceki satış baskısı zayıfladı; emir akışı şu an net bir yön "
                "teyidi vermiyor."
            )
        if previous == "buy_pressure":
            return (
                "Önceki alım baskısı zayıfladı; emir akışı şu an net bir yön "
                "teyidi vermiyor."
            )
        if current == "balanced":
            return (
                "Alım ve satım baskısı dengede; emir akışı şu an net bir yön "
                "teyidi vermiyor."
            )
        return (
            "Tahta ile gerçekleşen işlemler aynı yöne işaret etmiyor; emir "
            "akışında net teyit yok."
        )

    return (
        "Emir akışı için yeterli güncel kanıt yok; bu katmanda yön teyidi "
        "vermiyorum."
    )


def _derivatives_customer_summary(snapshot: StreamFamilySnapshot) -> str:
    state = snapshot.state_label.lower()
    if state == "crowded_long":
        return (
            "Vadeli piyasada long tarafı kalabalıklaşıyor; ters yönde sert "
            "hareket riski arttı."
        )
    if state == "crowded_short":
        return (
            "Vadeli piyasada short tarafı kalabalıklaşıyor; ters yönde sert "
            "hareket riski arttı."
        )
    if state == "leverage_buildup":
        return (
            "Vadeli piyasada açık pozisyon yükü büyüyor; kaldıraç birikimi "
            "arttığı için hareketin kırılganlığı yükseliyor."
        )
    if state == "deleveraging":
        return (
            "Vadeli piyasada kaldıraç çözülüyor; açık pozisyon yükü azalıyor."
        )
    if state == "balanced":
        return (
            "Türev göstergeleri dengeli; belirgin bir kalabalıklaşma veya "
            "kaldıraç baskısı yok."
        )
    if state == "mixed":
        return (
            "Türev göstergeleri aynı yönde birleşmiyor; bu katman şu an net "
            "teyit vermiyor."
        )
    return (
        "Türev görünümü için yeterli güncel kanıt yok; bu katmanda yön teyidi "
        "vermiyorum."
    )


def _render_trust_family_text(
    snapshot: StreamFamilySnapshot,
    change: StreamFamilyChangeSet,
) -> StreamNarrativeText:
    components = _snapshot_components(snapshot)
    previous = change.previous_state_label
    changed = (
        "ilk kayıt"
        if change.story_started
        else ", ".join(change.changed_components)
    )
    uncertainty = (
        " Belirsizlik kodları: " + ", ".join(snapshot.uncertainty_flags) + "."
        if snapshot.uncertainty_flags
        else ""
    )

    if snapshot.family is StreamTrustDomain.EVENT_RISK:
        if snapshot.state_label == "event_block":
            collapsed = (
                "Yakın dönem olay riski nedeniyle yeni işlem görüşünü "
                "blokluyorum."
            )
            restore = (
                "Olayın blok ve stabilizasyon penceresi güvenli biçimde "
                "tamamlandığında normal değerlendirmeye dönebilirim."
            )
        elif snapshot.state_label == "pre_event_caution":
            collapsed = (
                "Yaklaşan önemli olay nedeniyle temkinliyim; yön görüşünü daha "
                "düşük güvenle değerlendiriyorum."
            )
            restore = (
                "Olay penceresi güvenli biçimde geçildiğinde bu ek temkin "
                "kalkabilir."
            )
        elif snapshot.state_label == "post_event_stabilization":
            collapsed = (
                "Önemli olay sonrası piyasanın sakinleşmesini bekliyorum; henüz "
                "normal risk durumuna dönmedim."
            )
            restore = (
                "Stabilizasyon penceresi tamamlanıp olay riski temizlendiğinde "
                "normal değerlendirmeye dönebilirim."
            )
        elif snapshot.state_label == "degraded_data":
            collapsed = (
                "Olay takvimi verisi yeterince güvenilir değil; risk durumunu "
                "temiz kabul etmiyorum."
            )
            restore = (
                "Güncel ve yeterli olay takvimi kanıtı yeniden geldiğinde risk "
                "durumu tekrar değerlendirilecek."
            )
        else:
            collapsed = (
                "Olay riski tarafı şu an temiz; ek bir takvim engeli görünmüyor."
            )
            restore = (
                "Bu durum yalnız olay takvimi kapsamı güncel kaldığı sürece "
                "geçerlidir."
            )
        technical = (
            "Event Risk exact persisted calendar/freeze evidence ile güncellendi. "
            f"Raw durum: {snapshot.state_label}; önceki durum: {previous or 'none'}. "
            f"Nearest event identity: {components.get('nearest_event_identity', 'none')}. "
            f"Değişen bileşenler: {changed}. "
            f"Kaynak kalitesi: {snapshot.source_quality}.{uncertainty}"
        )
        decision = (
            "Bu risk mesajı yön veya getiri olasılığı üretmez; yalnızca mevcut "
            "olay riskinin karar güvenine etkisini açıklar."
        )
    else:
        if snapshot.state_label in {
            "degraded_provider_unavailable",
            "degraded_provider_stale",
        }:
            collapsed = (
                "Piyasa verisi sağlayıcılarından biri yeterince güvenilir değil; "
                "bu nedenle teyit gücünü düşürüyorum."
            )
            restore = (
                "Gerekli sağlayıcılar yeniden güncel ve erişilebilir olduğunda "
                "normal veri güvenine dönebilirim."
            )
        elif snapshot.state_label == "degraded_no_overlap":
            collapsed = (
                "Veri sağlayıcıları aynı piyasa penceresini yeterince "
                "doğrulamıyor; teyit gücünü düşürüyorum."
            )
            restore = (
                "Sağlayıcılar yeniden aynı veri aralığını eksiksiz doğruladığında "
                "normal güvene dönebilirim."
            )
        elif snapshot.state_label == "caution_partial_coverage":
            collapsed = (
                "Piyasa verisi kısmi; sistem çalışıyor ancak teyit gücü şu an "
                "daha düşük."
            )
            restore = (
                "Eksik kapsam kapanıp sağlayıcılar yeniden tam örtüştüğünde "
                "normal güvene dönebilirim."
            )
        else:
            collapsed = (
                "Piyasa verisi sağlıklı; gerekli sağlayıcılar birbirini yeterince "
                "doğruluyor."
            )
            restore = (
                "Bu durum sağlayıcılar güncel ve kapsama alanı eksiksiz kaldığı "
                "sürece geçerlidir."
            )
        technical = (
            "Provider trust exact persisted divergence snapshot ile güncellendi. "
            f"Raw durum: {snapshot.state_label}; önceki durum: {previous or 'none'}. "
            f"Grid: {components.get('grid_state', 'unknown')}. "
            f"Değişen bileşenler: {changed}. "
            f"Kaynak kalitesi: {snapshot.source_quality}.{uncertainty}"
        )
        decision = (
            "Bu sistem mesajı veri güvenini açıklar; yön veya forecast üretmez. "
            "Veri güveni düştüğünde diğer analizlerin teyit gücü de daha temkinli "
            "yorumlanır."
        )

    simple = f"{collapsed} {restore}"
    intelligence = simple
    capital = (
        "Bu güven mesajı canonical sanal-sermaye durumunu tek başına değiştirmez. "
        "REAL_CAPITAL=0."
    )
    return StreamNarrativeText(
        collapsed_text=collapsed,
        simple_text=simple,
        technical_text=technical,
        intelligence_text=intelligence,
        decision_text=decision,
        capital_text=capital,
    )


def _family_fact_payload_values(
    *,
    stream_event_identity: str,
    source_event_identity: str,
    story_identity: str,
    projector_id: str,
    family: StreamFamilyDomain,
    source_scope: str,
    asset: str,
    symbol: str,
    market: str,
    timeframe: str,
    event_at_ms: int,
    source_as_of_ms: int,
    evidence_identities: tuple[str, ...],
    available_evidence_domains: tuple[str, ...],
    state_label: str,
    state_key: str,
    state_components: tuple[StreamFamilyStateComponent, ...],
    direction: str | None,
    source_quality: str,
    uncertainty_flags: tuple[str, ...],
    previous_fact_bundle_identity: str | None,
) -> dict[str, object]:
    return {
        "asset": asset,
        "available_evidence_domains": available_evidence_domains,
        "direction": direction,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "evidence_identities": evidence_identities,
        "family": family,
        "market": market,
        "previous_fact_bundle_identity": previous_fact_bundle_identity,
        "production_authority": False,
        "projector_id": projector_id,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "schema_version": STREAM_FAMILY_FACT_SCHEMA_VERSION,
        "source_as_of_ms": source_as_of_ms,
        "source_event_identity": source_event_identity,
        "source_quality": source_quality,
        "source_scope": source_scope,
        "state_components": state_components,
        "state_key": state_key,
        "state_label": state_label,
        "story_identity": story_identity,
        "stream_event_identity": stream_event_identity,
        "symbol": symbol,
        "timeframe": timeframe,
        "uncertainty_flags": uncertainty_flags,
    }


def _family_fact_payload(value: StreamFamilyFactBundle) -> dict[str, object]:
    return _family_fact_payload_values(
        stream_event_identity=value.stream_event_identity,
        source_event_identity=value.source_event_identity,
        story_identity=value.story_identity,
        projector_id=value.projector_id,
        family=value.family,
        source_scope=value.source_scope,
        asset=value.asset,
        symbol=value.symbol,
        market=value.market,
        timeframe=value.timeframe,
        event_at_ms=value.event_at_ms,
        source_as_of_ms=value.source_as_of_ms,
        evidence_identities=value.evidence_identities,
        available_evidence_domains=value.available_evidence_domains,
        state_label=value.state_label,
        state_key=value.state_key,
        state_components=value.state_components,
        direction=value.direction,
        source_quality=value.source_quality,
        uncertainty_flags=value.uncertainty_flags,
        previous_fact_bundle_identity=value.previous_fact_bundle_identity,
    )

def _family_observation_payload(
    value: StreamFamilyStoryObservation,
) -> dict[str, object]:
    return {
        "asset": value.asset,
        "current_fact_bundle_identity": value.current_fact_bundle_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "family": value.family,
        "message_identity": value.message_identity,
        "previous_state_identity": value.previous_state_identity,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "state_components": value.state_components,
        "state_key": value.state_key,
        "state_label": value.state_label,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
    }


def _family_state_payload(value: StreamFamilyStoryState) -> dict[str, object]:
    return {
        "asset": value.asset,
        "current_fact_bundle_identity": value.current_fact_bundle_identity,
        "current_message_identity": value.current_message_identity,
        "current_stream_event_identity": value.current_stream_event_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "family": value.family,
        "observation_identity": value.observation_identity,
        "previous_state_identity": value.previous_state_identity,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "state_components": value.state_components,
        "state_key": value.state_key,
        "state_label": value.state_label,
        "story_identity": value.story_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
    }


def _family_change_payload(value: StreamFamilyChangeSet) -> dict[str, object]:
    return {
        "changed_components": value.changed_components,
        "current_message_identity": value.current_message_identity,
        "current_state_identity": value.current_state_identity,
        "current_state_label": value.current_state_label,
        "engine_version": value.engine_version,
        "previous_message_identity": value.previous_message_identity,
        "previous_state_identity": value.previous_state_identity,
        "previous_state_label": value.previous_state_label,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "story_identity": value.story_identity,
        "story_started": value.story_started,
    }


def _family_analytical_payload(
    value: StreamFamilyAnalyticalView,
) -> dict[str, object]:
    return {
        "asset": value.asset,
        "change_set_identity": value.change_set_identity,
        "changed_components": value.changed_components,
        "current_state_identity": value.current_state_identity,
        "direction": value.direction,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "family": value.family,
        "family_state_label": value.family_state_label,
        "materiality_decision_identity": value.materiality_decision_identity,
        "materiality_reason_codes": value.materiality_reason_codes,
        "policy_identity": value.policy_identity,
        "policy_version": value.policy_version,
        "previous_family_state_label": value.previous_family_state_label,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "source_message_identity": value.source_message_identity,
        "source_quality": value.source_quality,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "uncertainty_flags": value.uncertainty_flags,
    }


def _family_plan_payload(value: StreamFamilyNarrativePlan) -> dict[str, object]:
    return {
        "analytical_view_identity": value.analytical_view_identity,
        "change_set_identity": value.change_set_identity,
        "changed_components": value.changed_components,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "family": value.family,
        "previous_state_label": value.previous_state_label,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "state_label": value.state_label,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "timeframe": value.timeframe,
        "voice_version": value.voice_version,
    }


def _family_narrative_payload(
    value: StreamFamilyNarrativeMessage,
) -> dict[str, object]:
    return {
        "analytical_view_identity": value.analytical_view_identity,
        "change_set_identity": value.change_set_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fact_bundle_identity": value.fact_bundle_identity,
        "family": value.family,
        "original_text_preserved": value.original_text_preserved,
        "plan_identity": value.plan_identity,
        "production_authority": value.production_authority,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "renderer_version": value.renderer_version,
        "schema_version": value.schema_version,
        "source_event_identity": value.source_event_identity,
        "source_kind": value.source_kind,
        "state_label": value.state_label,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "symbol": value.symbol,
        "text": value.text,
        "timeframe": value.timeframe,
        "validation": value.validation,
        "voice_version": value.voice_version,
    }


def _previous_state_components(previous: dict[str, Any]) -> dict[str, str]:
    raw = previous.get("state_components")
    if not isinstance(raw, list):
        raise TypeError("Stream family previous state components must be a list")
    result: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("Stream family previous component must be an object")
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not name:
            raise ValueError("Stream family previous component name is invalid")
        if not isinstance(value, str) or not value:
            raise ValueError("Stream family previous component value is invalid")
        if name in result:
            raise ValueError("Stream family previous component is duplicated")
        result[name] = value
    return result

def _require_family_projector_spec(projector_id: str) -> StreamProjectorSpec:
    selected = next(
        (
            item
            for item in accepted_stream_projector_registry()
            if item.projector_id == projector_id
        ),
        None,
    )
    if selected is None:
        raise ValueError("Stream family projector is not in accepted registry")
    if (
        selected.implementation_state
        is not StreamProjectorImplementationState.IMPLEMENTED
    ):
        raise ValueError("Stream family projector is not implemented")
    return selected


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Stream family field {key} must be non-empty text")
    return value


def _require_authority(
    schema_version: str,
    expected_schema: str,
    engine_version: str,
    read_only: bool,
    production_authority: bool,
    real_capital: int,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("unsupported Stream family schema")
    if engine_version != STREAM_ENGINE_VERSION:
        raise ValueError("unsupported Stream family engine")
    if not read_only or production_authority or real_capital != REAL_CAPITAL:
        raise ValueError("Stream family authority boundary mismatch")


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
