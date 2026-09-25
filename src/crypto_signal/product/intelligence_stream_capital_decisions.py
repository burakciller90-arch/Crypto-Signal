"""S11 Stream projection for canonical allocator vault decisions.

Projects persisted Epoch 2 allocator decisions (eligible / hold / blocked) into
the same Intelligence Stream without inventing fills, PnL, or analytical facts.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.canonical_vault_decisions import (
    CanonicalVaultDecisionDisposition,
    CanonicalVaultDecisionLedger,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.product.intelligence_stream_capital import StreamCapitalText
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
    StreamLedgerWriteDisposition,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
    STREAM_SOURCE_EVENT_SCHEMA_VERSION,
    StreamCategory,
    StreamImportance,
    StreamSourceEvent,
)
from crypto_signal.product.intelligence_stream_narrative import (
    StreamNarrativeSourceKind,
)

STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION = (
    "intelligence-stream-capital-decision-message-v1/1"
)
STREAM_CAPITAL_DECISION_LEDGER_SCHEMA_VERSION = (
    "intelligence-stream-capital-decision-ledger-v1/1"
)
STREAM_CAPITAL_DECISION_PROJECTOR_VERSION = "stream-s11-capital-decision-projector-v1/1"


class StreamCapitalDecisionWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamCapitalDecisionMessage:
    narrative_identity: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    decision_identity: str
    allocator_assessment_identity: str
    allocator_candidate_identity: str
    vault_id: PaperVaultId
    disposition: CanonicalVaultDecisionDisposition
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    starting_budget_usdt: Decimal
    reason_codes: tuple[str, ...]
    event_risk_state: str
    capital_reference_identities: tuple[str, ...]
    text: StreamCapitalText
    category: StreamCategory = StreamCategory.CAPITAL
    subtype: str = ""
    importance: StreamImportance = StreamImportance.IMPORTANT
    source_kind: StreamNarrativeSourceKind = StreamNarrativeSourceKind.DETERMINISTIC
    original_text_preserved: bool = True
    projector_version: str = STREAM_CAPITAL_DECISION_PROJECTOR_VERSION
    schema_version: str = STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.narrative_identity, "capital-decision narrative"),
            (self.source_event_identity, "capital-decision source event"),
            (self.stream_event_identity, "capital-decision stream event"),
            (self.story_identity, "capital-decision story"),
            (self.decision_identity, "capital-decision record"),
            (self.allocator_assessment_identity, "allocator assessment"),
            (self.allocator_candidate_identity, "allocator candidate"),
        ):
            _sha(value, label)
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("capital-decision message requires canonical vault")
        if not isinstance(self.disposition, CanonicalVaultDecisionDisposition):
            raise TypeError("capital-decision message requires canonical disposition")
        expected_subtype = _subtype(self.disposition)
        if self.subtype != expected_subtype:
            raise ValueError("capital-decision subtype/disposition mismatch")
        if not self.asset.strip() or not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("capital-decision market context must be non-empty")
        if min(self.event_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("capital-decision timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("capital-decision event cannot predate source truth")
        if (
            not isinstance(self.starting_budget_usdt, Decimal)
            or not self.starting_budget_usdt.is_finite()
            or self.starting_budget_usdt <= 0
        ):
            raise ValueError("capital-decision budget must be finite and positive")
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("capital-decision reasons must be sorted unique")
        _identity_tuple(self.capital_reference_identities)
        if self.decision_identity not in self.capital_reference_identities:
            raise ValueError("capital-decision message lost decision identity")
        if (
            self.category is not StreamCategory.CAPITAL
            or self.importance is not StreamImportance.IMPORTANT
            or self.source_kind is not StreamNarrativeSourceKind.DETERMINISTIC
            or not self.original_text_preserved
            or self.projector_version != STREAM_CAPITAL_DECISION_PROJECTOR_VERSION
            or self.schema_version != STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION
            or self.engine_version != STREAM_ENGINE_VERSION
            or not self.read_only
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("capital-decision message authority/version mismatch")
        if self.narrative_identity != canonical_sha256(_message_payload(self)):
            raise ValueError("capital-decision narrative identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamCapitalDecisionProjectionResult:
    source_event_identity: str
    stream_event_identity: str
    narrative_identity: str
    source_event_disposition: StreamLedgerWriteDisposition
    message_disposition: StreamCapitalDecisionWriteDisposition
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamCapitalDecisionLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_capital_decision_messages (
                    narrative_identity TEXT PRIMARY KEY,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    decision_identity TEXT NOT NULL UNIQUE,
                    vault_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    subtype TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (stream_event_identity)
                        REFERENCES stream_source_events(stream_event_identity)
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                    stream_capital_decision_messages_immutable_{operation.lower()}
                    BEFORE {operation} ON stream_capital_decision_messages
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable intelligence stream capital-decision ledger'
                        );
                    END
                    """
                )

    def append(
        self,
        message: StreamCapitalDecisionMessage,
    ) -> StreamCapitalDecisionWriteDisposition:
        self.initialize()
        payload = canonical_json(message)
        digest = sha256_text(payload)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                """
                SELECT source_event_identity, category, subtype, event_at_ms
                FROM stream_source_events
                WHERE stream_event_identity = ?
                """,
                (message.stream_event_identity,),
            ).fetchone()
            if source is None:
                raise ValueError("capital-decision source event is not persisted")
            if (
                str(source[0]) != message.source_event_identity
                or str(source[1]) != StreamCategory.CAPITAL.value
                or str(source[2]) != message.subtype
                or int(str(source[3])) != message.event_at_ms
            ):
                raise ValueError("capital-decision source-event lineage mismatch")
            existing = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_capital_decision_messages
                WHERE narrative_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                   OR decision_identity = ?
                LIMIT 1
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.decision_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == message.narrative_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return StreamCapitalDecisionWriteDisposition.UNCHANGED
                raise ValueError("immutable capital-decision message conflict")
            connection.execute(
                """
                INSERT INTO stream_capital_decision_messages (
                    narrative_identity, source_event_identity, stream_event_identity,
                    story_identity, decision_identity, vault_id, symbol, timeframe,
                    subtype, event_at_ms, payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.story_identity,
                    message.decision_identity,
                    message.vault_id.value,
                    message.symbol,
                    message.timeframe,
                    message.subtype,
                    message.event_at_ms,
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return StreamCapitalDecisionWriteDisposition.INSERTED


def project_vault_decision_to_stream(
    *,
    epoch2_path: Path,
    stream_path: Path,
    decision_identity: str,
) -> StreamCapitalDecisionProjectionResult:
    raw = CanonicalVaultDecisionLedger(epoch2_path).read(decision_identity)
    if raw is None:
        raise ValueError("capital-decision projector source record is missing")
    stream = IntelligenceStreamLedger(stream_path)
    activation = stream.read_activation()
    source_event = _source_event(activation, raw)
    event_disposition = stream.append_source_event(source_event)
    message = _message(source_event, raw)
    message_disposition = IntelligenceStreamCapitalDecisionLedger(stream_path).append(
        message
    )
    return StreamCapitalDecisionProjectionResult(
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        narrative_identity=message.narrative_identity,
        source_event_disposition=event_disposition,
        message_disposition=message_disposition,
    )


def _source_event(
    activation: dict[str, object],
    raw: dict[str, object],
) -> StreamSourceEvent:
    disposition = CanonicalVaultDecisionDisposition(_text(raw, "disposition"))
    subtype = _subtype(disposition)
    source_identity = _sha_field(raw, "decision_identity")
    source_ids = tuple(
        sorted(
            {
                source_identity,
                *_identities(raw.get("source_evidence_identities")),
            }
        )
    )
    event_at_ms = _integer(raw, "decided_at_ms")
    source_as_of_ms = _integer(raw, "candidate_as_of_ms")
    activation_identity = _sha_field(activation, "activation_identity")
    materiality = tuple(
        sorted(
            {
                subtype,
                f"vault:{_text(raw, 'vault_id')}",
                *_text_values(raw.get("reason_codes")),
            }
        )
    )
    payload = {
        "activation_identity": activation_identity,
        "asset": _text(raw, "asset"),
        "category": StreamCategory.CAPITAL,
        "decision_context_identity": None,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "evidence_identities": source_ids,
        "forecast_identity": None,
        "importance": StreamImportance.IMPORTANT,
        "materiality_codes": materiality,
        "production_authority": False,
        "proof_identity": None,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": None,
        "schema_version": STREAM_SOURCE_EVENT_SCHEMA_VERSION,
        "source_as_of_ms": source_as_of_ms,
        "source_event_identity": source_identity,
        "subtype": subtype,
        "symbol": _text(raw, "asset"),
        "timeframe": _text(raw, "source_timeframe"),
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation_identity,
        source_event_identity=source_identity,
        category=StreamCategory.CAPITAL,
        subtype=subtype,
        importance=StreamImportance.IMPORTANT,
        asset=_text(raw, "asset"),
        symbol=_text(raw, "asset"),
        timeframe=_text(raw, "source_timeframe"),
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        forecast_identity=None,
        proof_identity=None,
        resolution_identity=None,
        decision_context_identity=None,
        evidence_identities=source_ids,
        materiality_codes=materiality,
    )


def _message(
    source_event: StreamSourceEvent,
    raw: dict[str, object],
) -> StreamCapitalDecisionMessage:
    disposition = CanonicalVaultDecisionDisposition(_text(raw, "disposition"))
    vault_id = PaperVaultId(_text(raw, "vault_id"))
    decision_identity = _sha_field(raw, "decision_identity")
    assessment_identity = _sha_field(raw, "allocator_assessment_identity")
    candidate_identity = _sha_field(raw, "allocator_candidate_identity")
    refs = tuple(
        sorted(
            {
                decision_identity,
                assessment_identity,
                candidate_identity,
                *source_event.evidence_identities,
            }
        )
    )
    reason_codes = _text_values(raw.get("reason_codes"))
    story_identity = canonical_sha256(
        {
            "allocator_candidate_identity": candidate_identity,
            "capital_story_kind": "vault_decision",
            "vault_id": vault_id,
        }
    )
    text_bundle = _text_bundle(
        vault_id=vault_id,
        disposition=disposition,
        event_risk_state=_text(raw, "event_risk_state"),
        reason_codes=reason_codes,
        starting_budget=_decimal_field(raw, "starting_budget_usdt"),
    )
    payload = {
        "allocator_assessment_identity": assessment_identity,
        "allocator_candidate_identity": candidate_identity,
        "asset": source_event.asset,
        "capital_reference_identities": refs,
        "category": StreamCategory.CAPITAL,
        "decision_identity": decision_identity,
        "disposition": disposition,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": source_event.event_at_ms,
        "event_risk_state": _text(raw, "event_risk_state"),
        "importance": StreamImportance.IMPORTANT,
        "original_text_preserved": True,
        "production_authority": False,
        "projector_version": STREAM_CAPITAL_DECISION_PROJECTOR_VERSION,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reason_codes": reason_codes,
        "schema_version": STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION,
        "source_as_of_ms": source_event.source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "source_kind": StreamNarrativeSourceKind.DETERMINISTIC,
        "starting_budget_usdt": _decimal_field(raw, "starting_budget_usdt"),
        "story_identity": story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": source_event.subtype,
        "symbol": source_event.symbol,
        "text": text_bundle,
        "timeframe": source_event.timeframe,
        "vault_id": vault_id,
    }
    return StreamCapitalDecisionMessage(
        narrative_identity=canonical_sha256(payload),
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        story_identity=story_identity,
        decision_identity=decision_identity,
        allocator_assessment_identity=assessment_identity,
        allocator_candidate_identity=candidate_identity,
        vault_id=vault_id,
        disposition=disposition,
        asset=source_event.asset,
        symbol=source_event.symbol,
        timeframe=source_event.timeframe,
        event_at_ms=source_event.event_at_ms,
        source_as_of_ms=source_event.source_as_of_ms,
        starting_budget_usdt=_decimal_field(raw, "starting_budget_usdt"),
        reason_codes=reason_codes,
        event_risk_state=_text(raw, "event_risk_state"),
        capital_reference_identities=refs,
        text=text_bundle,
        subtype=source_event.subtype,
    )


def _text_bundle(
    *,
    vault_id: PaperVaultId,
    disposition: CanonicalVaultDecisionDisposition,
    event_risk_state: str,
    reason_codes: tuple[str, ...],
    starting_budget: Decimal,
) -> StreamCapitalText:
    label = {
        PaperVaultId.CORE: "Core",
        PaperVaultId.TACTICAL: "Tactical",
        PaperVaultId.OPPORTUNITY_RESERVE: "Opportunity",
    }[vault_id]
    reasons = ", ".join(code.replace("_", " ") for code in reason_codes)
    if disposition is CanonicalVaultDecisionDisposition.BLOCKED:
        collapsed = f"{label} kasası işlem açmadı: Event Risk {event_risk_state}; sermaye bloklandı."
        simple = f"{label} kasası nakitte kaldı. Blok nedeni: {reasons}."
        decision = "Karar: işlem açma; blok kalkmadan sizing veya fill üretme."
    elif disposition is CanonicalVaultDecisionDisposition.HOLD:
        collapsed = f"{label} kasası nakitte kaldı; gerekli teyitler tamamlanmadı."
        simple = f"{label} için işlem açılmadı. Eksik veya yetersiz koşullar: {reasons}."
        decision = "Karar: HOLD_CASH; yeni exact evidence gelene kadar sermayeyi koru."
    else:
        collapsed = f"{label} kasası paper execution için uygun; henüz fill üretilmedi."
        simple = f"{label} uygunluk kontrolünü geçti. Bu durum işlem değildir; sizing ve tetik hâlâ zorunlu."
        decision = "Karar: execution adayı; sizing ve exact trigger olmadan fill üretme."
    technical = (
        f"Allocator reason codes: {reasons}. Event Risk: {event_risk_state}. "
        "Karar immutable S11 vault-decision kimliğiyle bağlı."
    )
    intelligence = (
        "Bu mesaj allocator kararını açıklar; piyasa yönü, olasılık veya gerçekleşmiş "
        "performans hakkında ek iddia üretmez."
    )
    capital = (
        f"{label} başlangıç zarfı {starting_budget} USDT. "
        "Bu kayıt accounting/NAV mutasyonu değildir; REAL_CAPITAL=0."
    )
    return StreamCapitalText(
        collapsed_text=collapsed,
        simple_text=simple,
        technical_text=technical,
        intelligence_text=intelligence,
        decision_text=decision,
        capital_text=capital,
    )


def _message_payload(value: StreamCapitalDecisionMessage) -> dict[str, object]:
    return {
        "allocator_assessment_identity": value.allocator_assessment_identity,
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "asset": value.asset,
        "capital_reference_identities": value.capital_reference_identities,
        "category": value.category,
        "decision_identity": value.decision_identity,
        "disposition": value.disposition,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "event_risk_state": value.event_risk_state,
        "importance": value.importance,
        "original_text_preserved": value.original_text_preserved,
        "production_authority": value.production_authority,
        "projector_version": value.projector_version,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "schema_version": value.schema_version,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
        "source_kind": value.source_kind,
        "starting_budget_usdt": value.starting_budget_usdt,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "symbol": value.symbol,
        "text": value.text,
        "timeframe": value.timeframe,
        "vault_id": value.vault_id,
    }


def _subtype(disposition: CanonicalVaultDecisionDisposition) -> str:
    return {
        CanonicalVaultDecisionDisposition.ELIGIBLE: "capital_eligible",
        CanonicalVaultDecisionDisposition.HOLD: "capital_hold",
        CanonicalVaultDecisionDisposition.BLOCKED: "capital_blocked",
    }[disposition]


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")


def _sha_field(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text")
    _sha(value, key)
    return value


def _text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _integer(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be non-negative int")
    return value


def _decimal_field(raw: dict[str, object], key: str) -> Decimal:
    try:
        value = Decimal(str(raw.get(key)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be Decimal-compatible") from exc
    if not value.is_finite():
        raise ValueError(f"{key} must be finite")
    return value


def _text_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError("reason codes must be list/tuple")
    items = tuple(str(item) for item in value)
    if not items or items != tuple(sorted(set(items))):
        raise ValueError("reason codes must be non-empty sorted unique")
    return items


def _identities(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError("evidence identities must be list/tuple")
    items = tuple(str(item) for item in value)
    _identity_tuple(items)
    return items


def _identity_tuple(values: tuple[str, ...]) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError("capital-decision identities must be non-empty sorted unique")
    for identity in values:
        _sha(identity, "capital-decision evidence")
