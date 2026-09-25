"""S11 projection of durable canonical sizing events into Intelligence Stream."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.canonical_sizing_events import CanonicalSizingEventLedger
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

STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION = (
    "intelligence-stream-capital-sizing-message-v1/1"
)
STREAM_CAPITAL_SIZING_PROJECTOR_VERSION = "stream-s11-capital-sizing-projector-v1/1"


class StreamCapitalSizingWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamCapitalSizingMessage:
    narrative_identity: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    sizing_event_identity: str
    selection_identity: str
    eligibility_proof_identity: str
    allocator_candidate_identity: str
    vault_id: PaperVaultId
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    fraction_of_vault: Decimal
    canonical_notional_usdt: Decimal
    current_cash_usdt: Decimal
    current_nav_usdt: Decimal
    reason_codes: tuple[str, ...]
    capital_reference_identities: tuple[str, ...]
    text: StreamCapitalText
    category: StreamCategory = StreamCategory.CAPITAL
    subtype: str = "capital_sized"
    importance: StreamImportance = StreamImportance.IMPORTANT
    source_kind: StreamNarrativeSourceKind = StreamNarrativeSourceKind.DETERMINISTIC
    original_text_preserved: bool = True
    projector_version: str = STREAM_CAPITAL_SIZING_PROJECTOR_VERSION
    schema_version: str = STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.narrative_identity, "capital-sizing narrative"),
            (self.source_event_identity, "capital-sizing source"),
            (self.stream_event_identity, "capital-sizing stream event"),
            (self.story_identity, "capital-sizing story"),
            (self.sizing_event_identity, "capital-sizing event"),
            (self.selection_identity, "capital-sizing selection"),
            (self.eligibility_proof_identity, "capital-sizing eligibility"),
            (self.allocator_candidate_identity, "capital-sizing candidate"),
        ):
            _sha(value, label)
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("capital-sizing message requires canonical vault")
        if not self.asset.strip() or not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("capital-sizing market context must be non-empty")
        if min(self.source_as_of_ms, self.event_at_ms) < 0:
            raise ValueError("capital-sizing timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("capital-sizing event predates source truth")
        for amount, label, positive in (
            (self.fraction_of_vault, "fraction", True),
            (self.canonical_notional_usdt, "notional", True),
            (self.current_cash_usdt, "cash", False),
            (self.current_nav_usdt, "NAV", False),
        ):
            _decimal(amount, label, positive=positive)
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("capital-sizing reasons must be sorted unique")
        _identity_tuple(self.capital_reference_identities, "capital-sizing reference")
        required = {
            self.sizing_event_identity,
            self.selection_identity,
            self.eligibility_proof_identity,
            self.allocator_candidate_identity,
        }
        if not required.issubset(set(self.capital_reference_identities)):
            raise ValueError("capital-sizing message lost exact lineage")
        if self.category is not StreamCategory.CAPITAL or self.subtype != "capital_sized":
            raise ValueError("capital-sizing message category/subtype mismatch")
        if self.importance is not StreamImportance.IMPORTANT:
            raise ValueError("capital-sizing message must be important")
        if self.source_kind is not StreamNarrativeSourceKind.DETERMINISTIC:
            raise ValueError("capital-sizing message must be deterministic")
        if (
            not self.read_only
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("capital-sizing authority boundary mismatch")
        if self.narrative_identity != canonical_sha256(_message_payload(self)):
            raise ValueError("capital-sizing narrative identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamCapitalSizingProjectionResult:
    source_event_identity: str
    stream_event_identity: str
    narrative_identity: str
    source_event_disposition: StreamLedgerWriteDisposition
    message_disposition: StreamCapitalSizingWriteDisposition
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamCapitalSizingLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_capital_sizing_messages (
                    narrative_identity TEXT PRIMARY KEY,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    sizing_event_identity TEXT NOT NULL UNIQUE,
                    vault_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
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
                    stream_capital_sizing_messages_immutable_{operation.lower()}
                    BEFORE {operation} ON stream_capital_sizing_messages
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable intelligence stream capital-sizing ledger'
                        );
                    END
                    """
                )

    def append(
        self,
        message: StreamCapitalSizingMessage,
    ) -> StreamCapitalSizingWriteDisposition:
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
                raise ValueError("capital-sizing source event is not persisted")
            if (
                str(source[0]) != message.source_event_identity
                or str(source[1]) != StreamCategory.CAPITAL.value
                or str(source[2]) != message.subtype
                or int(str(source[3])) != message.event_at_ms
            ):
                raise ValueError("capital-sizing source-event lineage mismatch")
            existing = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_capital_sizing_messages
                WHERE narrative_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                   OR sizing_event_identity = ?
                LIMIT 1
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.sizing_event_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == message.narrative_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return StreamCapitalSizingWriteDisposition.UNCHANGED
                raise ValueError("immutable capital-sizing message conflict")
            connection.execute(
                """
                INSERT INTO stream_capital_sizing_messages (
                    narrative_identity,
                    source_event_identity,
                    stream_event_identity,
                    story_identity,
                    sizing_event_identity,
                    vault_id,
                    symbol,
                    timeframe,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.story_identity,
                    message.sizing_event_identity,
                    message.vault_id.value,
                    message.symbol,
                    message.timeframe,
                    message.event_at_ms,
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return StreamCapitalSizingWriteDisposition.INSERTED


def project_sizing_event_to_stream(
    *,
    epoch2_path: Path,
    stream_path: Path,
    sizing_event_identity: str,
) -> StreamCapitalSizingProjectionResult:
    raw = CanonicalSizingEventLedger(epoch2_path).read(sizing_event_identity)
    if raw is None:
        raise ValueError("capital-sizing projector source record is missing")
    stream = IntelligenceStreamLedger(stream_path)
    activation = stream.read_activation()
    source_event = _source_event(activation, raw)
    event_disposition = stream.append_source_event(source_event)
    message = _message(source_event, raw)
    message_disposition = IntelligenceStreamCapitalSizingLedger(stream_path).append(
        message
    )
    return StreamCapitalSizingProjectionResult(
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
    source_identity = _sha_field(raw, "event_identity")
    evidence = tuple(
        sorted(
            {
                source_identity,
                *_identities(raw.get("source_evidence_identities")),
            }
        )
    )
    event_at_ms = _integer(raw, "selected_at_ms")
    source_as_of_ms = _integer(raw, "candidate_as_of_ms")
    activation_identity = _sha_field(activation, "activation_identity")
    vault_id = _text(raw, "vault_id")
    materiality = tuple(
        sorted(
            {
                "capital_sized",
                "fixed_fractional_only",
                f"vault:{vault_id}",
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
        "evidence_identities": evidence,
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
        "subtype": "capital_sized",
        "symbol": _text(raw, "asset"),
        "timeframe": _text(raw, "timeframe"),
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation_identity,
        source_event_identity=source_identity,
        category=StreamCategory.CAPITAL,
        subtype="capital_sized",
        importance=StreamImportance.IMPORTANT,
        asset=_text(raw, "asset"),
        symbol=_text(raw, "asset"),
        timeframe=_text(raw, "timeframe"),
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        forecast_identity=None,
        proof_identity=None,
        resolution_identity=None,
        decision_context_identity=None,
        evidence_identities=evidence,
        materiality_codes=materiality,
    )


def _message(
    source_event: StreamSourceEvent,
    raw: dict[str, object],
) -> StreamCapitalSizingMessage:
    sizing_event_identity = _sha_field(raw, "event_identity")
    selection_identity = _sha_field(raw, "selection_identity")
    eligibility_identity = _sha_field(raw, "eligibility_proof_identity")
    candidate_identity = _sha_field(raw, "allocator_candidate_identity")
    vault_id = PaperVaultId(_text(raw, "vault_id"))
    refs = tuple(
        sorted(
            {
                sizing_event_identity,
                selection_identity,
                eligibility_identity,
                candidate_identity,
                *source_event.evidence_identities,
            }
        )
    )
    reasons = _text_values(raw.get("reason_codes"))
    fraction = _decimal_field(raw, "fraction_of_vault")
    notional = _decimal_field(raw, "canonical_notional_usdt")
    current_cash = _decimal_field(raw, "current_cash_usdt")
    current_nav = _decimal_field(raw, "current_nav_usdt")
    story_identity = canonical_sha256(
        {
            "allocator_candidate_identity": candidate_identity,
            "capital_story_kind": "vault_decision",
            "vault_id": vault_id,
        }
    )
    text_bundle = _text_bundle(
        vault_id=vault_id,
        fraction=fraction,
        notional=notional,
        current_cash=current_cash,
        reasons=reasons,
    )
    payload = {
        "allocator_candidate_identity": candidate_identity,
        "asset": source_event.asset,
        "canonical_notional_usdt": notional,
        "capital_reference_identities": refs,
        "category": StreamCategory.CAPITAL,
        "current_cash_usdt": current_cash,
        "current_nav_usdt": current_nav,
        "eligibility_proof_identity": eligibility_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": source_event.event_at_ms,
        "fraction_of_vault": fraction,
        "importance": StreamImportance.IMPORTANT,
        "original_text_preserved": True,
        "production_authority": False,
        "projector_version": STREAM_CAPITAL_SIZING_PROJECTOR_VERSION,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reason_codes": reasons,
        "schema_version": STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION,
        "selection_identity": selection_identity,
        "sizing_event_identity": sizing_event_identity,
        "source_as_of_ms": source_event.source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "source_kind": StreamNarrativeSourceKind.DETERMINISTIC,
        "story_identity": story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": "capital_sized",
        "symbol": source_event.symbol,
        "text": text_bundle,
        "timeframe": source_event.timeframe,
        "vault_id": vault_id,
    }
    return StreamCapitalSizingMessage(
        narrative_identity=canonical_sha256(payload),
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        story_identity=story_identity,
        sizing_event_identity=sizing_event_identity,
        selection_identity=selection_identity,
        eligibility_proof_identity=eligibility_identity,
        allocator_candidate_identity=candidate_identity,
        vault_id=vault_id,
        asset=source_event.asset,
        symbol=source_event.symbol,
        timeframe=source_event.timeframe,
        event_at_ms=source_event.event_at_ms,
        source_as_of_ms=source_event.source_as_of_ms,
        fraction_of_vault=fraction,
        canonical_notional_usdt=notional,
        current_cash_usdt=current_cash,
        current_nav_usdt=current_nav,
        reason_codes=reasons,
        capital_reference_identities=refs,
        text=text_bundle,
    )


def _text_bundle(
    *,
    vault_id: PaperVaultId,
    fraction: Decimal,
    notional: Decimal,
    current_cash: Decimal,
    reasons: tuple[str, ...],
) -> StreamCapitalText:
    label = {
        PaperVaultId.CORE: "Core",
        PaperVaultId.TACTICAL: "Tactical",
        PaperVaultId.OPPORTUNITY_RESERVE: "Opportunity",
    }[vault_id]
    reason_text = ", ".join(reasons)
    return StreamCapitalText(
        collapsed_text=(
            f"{label} kasası için paper boyut seçildi: {notional} USDT "
            f"({fraction * Decimal(100)}%). REAL_CAPITAL=0."
        ),
        simple_text=(
            f"{label} kasası {current_cash} USDT nakit içinden {notional} USDT'lik "
            "sanal işlem bütçesi ayırdı; henüz fill oluşmadı."
        ),
        technical_text=(
            "Canonical fixed-fractional sizing exact allocator eligibility ve "
            f"mevcut vault snapshot'ına bağlandı. Nedenler: {reason_text}."
        ),
        intelligence_text=(
            "Bu mesaj execution değildir; yalnız kanıtlanmış paper sizing kararını "
            "gösterir. Fiyat/trigger veya execution şartı bozulursa işlem oluşmayabilir."
        ),
        decision_text=(
            f"Boyut kararı: {notional} USDT. Kelly varyantları production'a terfi etmedi."
        ),
        capital_text=(
            f"{label} vault sizing aktif; gerçek sermaye yok, borsa emri yok, REAL_CAPITAL=0."
        ),
    )


def _message_payload(value: StreamCapitalSizingMessage) -> dict[str, object]:
    return {
        "allocator_candidate_identity": value.allocator_candidate_identity,
        "asset": value.asset,
        "canonical_notional_usdt": value.canonical_notional_usdt,
        "capital_reference_identities": value.capital_reference_identities,
        "category": value.category,
        "current_cash_usdt": value.current_cash_usdt,
        "current_nav_usdt": value.current_nav_usdt,
        "eligibility_proof_identity": value.eligibility_proof_identity,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fraction_of_vault": value.fraction_of_vault,
        "importance": value.importance,
        "original_text_preserved": value.original_text_preserved,
        "production_authority": value.production_authority,
        "projector_version": value.projector_version,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reason_codes": value.reason_codes,
        "schema_version": value.schema_version,
        "selection_identity": value.selection_identity,
        "sizing_event_identity": value.sizing_event_identity,
        "source_as_of_ms": value.source_as_of_ms,
        "source_event_identity": value.source_event_identity,
        "source_kind": value.source_kind,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "symbol": value.symbol,
        "text": value.text,
        "timeframe": value.timeframe,
        "vault_id": value.vault_id,
    }


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")


def _sha_field(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be string")
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


def _identities(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError("source evidence must be list/tuple")
    result = tuple(str(item) for item in value)
    _identity_tuple(result, "capital-sizing source")
    return result


def _text_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError("capital-sizing reasons must be list/tuple")
    result = tuple(str(item) for item in value)
    if not result or result != tuple(sorted(set(result))):
        raise ValueError("capital-sizing reasons must be sorted unique")
    return result


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} identities must be non-empty sorted unique")
    for identity in values:
        _sha(identity, label)


def _decimal(value: Decimal, label: str, *, positive: bool) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"{label} must be finite Decimal")
    if value < 0 or (positive and value <= 0):
        raise ValueError(f"{label} is outside allowed range")
