"""S11 Capital Story projection into the canonical Intelligence Stream.

Capital messages are projected only from already-persisted, read-verified R22/R21
paper accounting truth. The projector never mutates paper accounting and never
creates exchange or real-money authority. REAL_CAPITAL remains 0.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
    StreamLedgerWriteDisposition,
)
from crypto_signal.product.intelligence_stream_messages import (
    build_forecast_story_identity,
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

STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION = "intelligence-stream-capital-message-v1/1"
STREAM_CAPITAL_LEDGER_SCHEMA_VERSION = "intelligence-stream-capital-ledger-v1/1"
STREAM_CAPITAL_PROJECTOR_VERSION = "stream-s11-capital-projector-v1/1"


class StreamCapitalWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamCapitalText:
    collapsed_text: str
    simple_text: str
    technical_text: str
    intelligence_text: str
    decision_text: str
    capital_text: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.collapsed_text, "collapsed"),
            (self.simple_text, "simple"),
            (self.technical_text, "technical"),
            (self.intelligence_text, "intelligence"),
            (self.decision_text, "decision"),
            (self.capital_text, "capital"),
        ):
            if not value.strip():
                raise ValueError(f"S11 Capital Story {label} text must be non-empty")
        if "\n" in self.collapsed_text:
            raise ValueError("S11 Capital Story collapsed text must be one paragraph")


@dataclass(frozen=True, slots=True)
class StreamCapitalMessage:
    narrative_identity: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    forecast_identity: str
    proof_identity: str
    bundle_identity: str
    intent_identity: str
    fill_identity: str
    before_vault_snapshot_identity: str
    after_vault_snapshot_identity: str
    before_consolidated_snapshot_identity: str
    after_consolidated_snapshot_identity: str
    vault_id: PaperVaultId
    action: str
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    quantity: Decimal
    reference_price: Decimal
    simulated_fill_price: Decimal
    notional_usdt: Decimal
    cash_before_usdt: Decimal
    cash_after_usdt: Decimal
    vault_nav_before_usdt: Decimal
    vault_nav_after_usdt: Decimal
    consolidated_nav_before_usdt: Decimal
    consolidated_nav_after_usdt: Decimal
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    capital_reference_identities: tuple[str, ...]
    text: StreamCapitalText
    category: StreamCategory = StreamCategory.CAPITAL
    subtype: str = "capital_executed"
    importance: StreamImportance = StreamImportance.IMPORTANT
    source_kind: StreamNarrativeSourceKind = StreamNarrativeSourceKind.DETERMINISTIC
    original_text_preserved: bool = True
    projector_version: str = STREAM_CAPITAL_PROJECTOR_VERSION
    schema_version: str = STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.narrative_identity, "capital narrative"),
            (self.source_event_identity, "capital source event"),
            (self.stream_event_identity, "capital stream event"),
            (self.story_identity, "capital story"),
            (self.forecast_identity, "capital forecast"),
            (self.proof_identity, "capital proof"),
            (self.bundle_identity, "capital R22 bundle"),
            (self.intent_identity, "capital R22 intent"),
            (self.fill_identity, "capital R22 fill"),
            (self.before_vault_snapshot_identity, "capital before vault"),
            (self.after_vault_snapshot_identity, "capital after vault"),
            (
                self.before_consolidated_snapshot_identity,
                "capital before consolidated",
            ),
            (
                self.after_consolidated_snapshot_identity,
                "capital after consolidated",
            ),
        ):
            _require_sha256(value, label)
        if self.category is not StreamCategory.CAPITAL:
            raise ValueError("S11 Capital Story category must be capital")
        if self.subtype != "capital_executed":
            raise ValueError("S11 Slice1 supports capital_executed only")
        if self.importance is not StreamImportance.IMPORTANT:
            raise ValueError("S11 executed capital message must be important")
        if self.source_kind is not StreamNarrativeSourceKind.DETERMINISTIC:
            raise ValueError("S11 Capital Story must be deterministic")
        if not self.original_text_preserved:
            raise ValueError("S11 Capital Story original text must remain preserved")
        if self.projector_version != STREAM_CAPITAL_PROJECTOR_VERSION:
            raise ValueError("unsupported S11 Capital Story projector")
        if self.schema_version != STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION:
            raise ValueError("unsupported S11 Capital Story schema")
        if self.engine_version != STREAM_ENGINE_VERSION:
            raise ValueError("unsupported Stream engine for Capital Story")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 Capital Story requires canonical vault")
        if not self.asset.strip() or not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("S11 Capital Story market context must be non-empty")
        if self.event_at_ms < 0:
            raise ValueError("S11 Capital Story event time must be non-negative")
        for value, label, positive in (
            (self.quantity, "quantity", True),
            (self.reference_price, "reference price", True),
            (self.simulated_fill_price, "simulated fill price", True),
            (self.notional_usdt, "notional", True),
            (self.cash_before_usdt, "cash before", False),
            (self.cash_after_usdt, "cash after", False),
            (self.vault_nav_before_usdt, "vault NAV before", False),
            (self.vault_nav_after_usdt, "vault NAV after", False),
            (
                self.consolidated_nav_before_usdt,
                "consolidated NAV before",
                False,
            ),
            (
                self.consolidated_nav_after_usdt,
                "consolidated NAV after",
                False,
            ),
            (self.fee_usdt, "fee", False),
            (self.spread_usdt, "spread", False),
            (self.slippage_usdt, "slippage", False),
        ):
            _decimal(value, label, positive=positive)
        _identity_tuple(self.capital_reference_identities, "capital reference")
        required_refs = {
            self.bundle_identity,
            self.intent_identity,
            self.fill_identity,
            self.before_vault_snapshot_identity,
            self.after_vault_snapshot_identity,
            self.before_consolidated_snapshot_identity,
            self.after_consolidated_snapshot_identity,
        }
        if not required_refs.issubset(set(self.capital_reference_identities)):
            raise ValueError("S11 Capital Story lost exact R21/R22 lineage")
        if (
            not self.read_only
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("S11 Capital Story authority boundary mismatch")
        if self.narrative_identity != canonical_sha256(_capital_message_payload(self)):
            raise ValueError("S11 Capital Story narrative identity mismatch")


@dataclass(frozen=True, slots=True)
class StreamCapitalProjectionResult:
    source_event_identity: str
    stream_event_identity: str
    narrative_identity: str
    source_event_disposition: StreamLedgerWriteDisposition
    message_disposition: StreamCapitalWriteDisposition
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamCapitalLedger:
    """Append-only S11 Capital Story persistence inside the Stream database."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_capital_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_capital_messages (
                    narrative_identity TEXT PRIMARY KEY,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    forecast_identity TEXT NOT NULL,
                    bundle_identity TEXT NOT NULL UNIQUE,
                    vault_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (stream_event_identity)
                        REFERENCES stream_source_events(stream_event_identity)
                );

                CREATE INDEX IF NOT EXISTS stream_capital_story_order
                ON stream_capital_messages(
                    story_identity,
                    event_at_ms,
                    narrative_identity
                );
                """
            )
            expected = {
                "engine_version": STREAM_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_CAPITAL_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected.items():
                row = connection.execute(
                    "SELECT value FROM stream_capital_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_capital_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError(
                        f"S11 Capital Story ledger metadata mismatch for {key}"
                    )
            for table in ("stream_capital_meta", "stream_capital_messages"):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable intelligence stream capital ledger'
                            );
                        END
                        """
                    )

    def append_message(
        self,
        message: StreamCapitalMessage,
    ) -> StreamCapitalWriteDisposition:
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
                raise ValueError("S11 Capital Story source event is not persisted")
            if (
                str(source[0]) != message.source_event_identity
                or str(source[1]) != StreamCategory.CAPITAL.value
                or str(source[2]) != message.subtype
                or int(str(source[3])) != message.event_at_ms
            ):
                raise ValueError("S11 Capital Story source-event lineage mismatch")

            existing = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_capital_messages
                WHERE narrative_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                   OR bundle_identity = ?
                LIMIT 1
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.bundle_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == message.narrative_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return StreamCapitalWriteDisposition.UNCHANGED
                raise ValueError("immutable S11 Capital Story identity conflict")

            latest = connection.execute(
                """
                SELECT event_at_ms, narrative_identity
                FROM stream_capital_messages
                ORDER BY event_at_ms DESC, narrative_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if latest is not None and (
                message.event_at_ms,
                message.narrative_identity,
            ) <= (int(str(latest[0])), str(latest[1])):
                raise ValueError("S11 Capital Story append would backfill or fork")

            connection.execute(
                """
                INSERT INTO stream_capital_messages (
                    narrative_identity,
                    source_event_identity,
                    stream_event_identity,
                    story_identity,
                    forecast_identity,
                    bundle_identity,
                    vault_id,
                    symbol,
                    timeframe,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.story_identity,
                    message.forecast_identity,
                    message.bundle_identity,
                    message.vault_id.value,
                    message.symbol,
                    message.timeframe,
                    message.event_at_ms,
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return StreamCapitalWriteDisposition.INSERTED

    def read_message(self, narrative_identity: str) -> dict[str, object] | None:
        _require_sha256(narrative_identity, "S11 Capital Story lookup")
        if not self.path.is_file():
            return None
        uri = f"file:{quote(str(self.path.resolve()), safe='/')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                """
                SELECT event_at_ms, payload_json, payload_sha256
                FROM stream_capital_messages
                WHERE narrative_identity = ?
                """,
                (narrative_identity,),
            ).fetchone()
        if row is None:
            return None
        return _verify_capital_payload(
            narrative_identity=narrative_identity,
            event_at_ms=int(str(row[0])),
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
        )


def project_capital_bundle_to_stream(
    *,
    epoch2_path: Path,
    stream_path: Path,
    bundle_identity: str,
) -> StreamCapitalProjectionResult:
    """Project one already-persisted R22 accounting bundle into Stream V1."""
    context = R22Epoch2AtomicTape(epoch2_path).read_bundle_story_context(
        bundle_identity
    )
    bundle = _mapping(context, "bundle")
    intent = _mapping(context, "intent")
    fill = _mapping(context, "fill")
    before_vault = _mapping(context, "before_vault")
    after_vault = _mapping(context, "after_vault")
    before_parent = _mapping(context, "before_consolidated")
    after_parent = _mapping(context, "after_consolidated")

    forecast_identity = _sha_field(intent, "forecast_identity", "R22 intent forecast")
    proof_identity = _sha_field(intent, "proof_identity", "R22 intent proof")
    stream_ledger = IntelligenceStreamLedger(stream_path)
    activation = stream_ledger.read_activation()
    decision_context = stream_ledger.read_context_for_forecast(forecast_identity)
    if decision_context is None:
        raise ValueError(
            "S11 Capital Story requires existing forward Stream decision context"
        )
    if decision_context.get("proof_identity") != proof_identity:
        raise ValueError("S11 Capital Story decision-context proof mismatch")

    source_event = build_capital_executed_source_event(
        activation=activation,
        decision_context=decision_context,
        bundle=bundle,
        intent=intent,
        fill=fill,
        before_vault=before_vault,
        after_vault=after_vault,
        before_parent=before_parent,
        after_parent=after_parent,
    )
    event_disposition = stream_ledger.append_source_event(source_event)
    message = build_capital_executed_message(
        source_event=source_event,
        decision_context=decision_context,
        bundle=bundle,
        intent=intent,
        fill=fill,
        before_vault=before_vault,
        after_vault=after_vault,
        before_parent=before_parent,
        after_parent=after_parent,
    )
    message_disposition = IntelligenceStreamCapitalLedger(stream_path).append_message(
        message
    )
    return StreamCapitalProjectionResult(
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        narrative_identity=message.narrative_identity,
        source_event_disposition=event_disposition,
        message_disposition=message_disposition,
    )


def build_capital_executed_source_event(
    *,
    activation: Mapping[str, object],
    decision_context: Mapping[str, object],
    bundle: Mapping[str, object],
    intent: Mapping[str, object],
    fill: Mapping[str, object],
    before_vault: Mapping[str, object],
    after_vault: Mapping[str, object],
    before_parent: Mapping[str, object],
    after_parent: Mapping[str, object],
) -> StreamSourceEvent:
    activation_identity = _sha_field(
        activation,
        "activation_identity",
        "Stream activation",
    )
    context_identity = _sha_field(
        decision_context,
        "context_identity",
        "Stream decision context",
    )
    forecast_identity = _sha_field(intent, "forecast_identity", "capital forecast")
    proof_identity = _sha_field(intent, "proof_identity", "capital proof")
    bundle_identity = _sha_field(bundle, "bundle_identity", "R22 bundle")
    if decision_context.get("forecast_identity") != forecast_identity:
        raise ValueError("S11 Capital Story forecast/context mismatch")
    if decision_context.get("proof_identity") != proof_identity:
        raise ValueError("S11 Capital Story proof/context mismatch")
    event_at_ms = _int_field(bundle, "snapshot_at_ms")
    evidence = tuple(
        sorted(
            {
                bundle_identity,
                _sha_field(intent, "intent_identity", "R22 intent"),
                _sha_field(fill, "fill_identity", "R22 fill"),
                _sha_field(
                    before_vault,
                    "snapshot_identity",
                    "R21 before vault",
                ),
                _sha_field(
                    after_vault,
                    "snapshot_identity",
                    "R21 after vault",
                ),
                _sha_field(
                    before_parent,
                    "snapshot_identity",
                    "R21 before consolidated",
                ),
                _sha_field(
                    after_parent,
                    "snapshot_identity",
                    "R21 after consolidated",
                ),
                *_identity_values(intent.get("source_evidence_identities")),
            }
        )
    )
    vault_id = _vault_field(bundle)
    materiality_codes = tuple(
        sorted(
            {
                "capital_executed",
                "canonical_epoch2_paper_only",
                f"vault:{vault_id.value}",
            }
        )
    )
    payload = {
        "activation_identity": activation_identity,
        "asset": _text_field(decision_context, "asset"),
        "category": StreamCategory.CAPITAL,
        "decision_context_identity": context_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "evidence_identities": evidence,
        "forecast_identity": forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "materiality_codes": materiality_codes,
        "production_authority": False,
        "proof_identity": proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": None,
        "schema_version": STREAM_SOURCE_EVENT_SCHEMA_VERSION,
        "source_as_of_ms": event_at_ms,
        "source_event_identity": bundle_identity,
        "subtype": "capital_executed",
        "symbol": _text_field(decision_context, "symbol"),
        "timeframe": _text_field(decision_context, "timeframe"),
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation_identity,
        source_event_identity=bundle_identity,
        category=StreamCategory.CAPITAL,
        subtype="capital_executed",
        importance=StreamImportance.IMPORTANT,
        asset=_text_field(decision_context, "asset"),
        symbol=_text_field(decision_context, "symbol"),
        timeframe=_text_field(decision_context, "timeframe"),
        event_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        resolution_identity=None,
        decision_context_identity=context_identity,
        evidence_identities=evidence,
        materiality_codes=materiality_codes,
    )


def build_capital_executed_message(
    *,
    source_event: StreamSourceEvent,
    decision_context: Mapping[str, object],
    bundle: Mapping[str, object],
    intent: Mapping[str, object],
    fill: Mapping[str, object],
    before_vault: Mapping[str, object],
    after_vault: Mapping[str, object],
    before_parent: Mapping[str, object],
    after_parent: Mapping[str, object],
) -> StreamCapitalMessage:
    forecast_identity = _sha_field(intent, "forecast_identity", "capital forecast")
    proof_identity = _sha_field(intent, "proof_identity", "capital proof")
    bundle_identity = _sha_field(bundle, "bundle_identity", "capital bundle")
    vault_id = _vault_field(bundle)
    action = _text_field(intent, "action")
    if action != "BUY":
        raise ValueError("S11 Capital Story Slice1 supports persisted BUY fills only")
    quantity = _decimal_field(fill, "quantity")
    reference_price = _decimal_field(fill, "reference_price")
    simulated_fill_price = _decimal_field(fill, "simulated_fill_price")
    notional = _decimal_field(fill, "notional_usdt")
    cash_before = _decimal_field(before_vault, "cash_usdt")
    cash_after = _decimal_field(after_vault, "cash_usdt")
    nav_before = _decimal_field(before_vault, "nav_usdt")
    nav_after = _decimal_field(after_vault, "nav_usdt")
    parent_before = _decimal_field(before_parent, "nav_usdt")
    parent_after = _decimal_field(after_parent, "nav_usdt")
    fee = _decimal_field(fill, "fee_usdt")
    spread = _decimal_field(fill, "spread_usdt")
    slippage = _decimal_field(fill, "slippage_usdt")

    refs = tuple(
        sorted(
            {
                *source_event.evidence_identities,
                source_event.stream_event_identity,
            }
        )
    )
    text = _capital_text(
        vault_id=vault_id,
        symbol=source_event.symbol,
        quantity=quantity,
        reference_price=reference_price,
        simulated_fill_price=simulated_fill_price,
        notional=notional,
        cash_before=cash_before,
        cash_after=cash_after,
        nav_before=nav_before,
        nav_after=nav_after,
        consolidated_before=parent_before,
        consolidated_after=parent_after,
        fee=fee,
        spread=spread,
        slippage=slippage,
    )
    payload = {
        "action": action,
        "after_consolidated_snapshot_identity": _sha_field(
            after_parent,
            "snapshot_identity",
            "capital after parent",
        ),
        "after_vault_snapshot_identity": _sha_field(
            after_vault,
            "snapshot_identity",
            "capital after vault",
        ),
        "asset": source_event.asset,
        "before_consolidated_snapshot_identity": _sha_field(
            before_parent,
            "snapshot_identity",
            "capital before parent",
        ),
        "before_vault_snapshot_identity": _sha_field(
            before_vault,
            "snapshot_identity",
            "capital before vault",
        ),
        "bundle_identity": bundle_identity,
        "capital_reference_identities": refs,
        "cash_after_usdt": cash_after,
        "cash_before_usdt": cash_before,
        "category": StreamCategory.CAPITAL,
        "consolidated_nav_after_usdt": parent_after,
        "consolidated_nav_before_usdt": parent_before,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": source_event.event_at_ms,
        "fee_usdt": fee,
        "fill_identity": _sha_field(fill, "fill_identity", "capital fill"),
        "forecast_identity": forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "intent_identity": _sha_field(intent, "intent_identity", "capital intent"),
        "notional_usdt": notional,
        "original_text_preserved": True,
        "production_authority": False,
        "projector_version": STREAM_CAPITAL_PROJECTOR_VERSION,
        "proof_identity": proof_identity,
        "quantity": quantity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "reference_price": reference_price,
        "schema_version": STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION,
        "simulated_fill_price": simulated_fill_price,
        "slippage_usdt": slippage,
        "source_event_identity": source_event.source_event_identity,
        "source_kind": StreamNarrativeSourceKind.DETERMINISTIC,
        "spread_usdt": spread,
        "story_identity": build_forecast_story_identity(forecast_identity),
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": "capital_executed",
        "symbol": source_event.symbol,
        "text": text,
        "timeframe": source_event.timeframe,
        "vault_id": vault_id,
        "vault_nav_after_usdt": nav_after,
        "vault_nav_before_usdt": nav_before,
    }
    return StreamCapitalMessage(
        narrative_identity=canonical_sha256(payload),
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        story_identity=build_forecast_story_identity(forecast_identity),
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        bundle_identity=bundle_identity,
        intent_identity=_sha_field(intent, "intent_identity", "capital intent"),
        fill_identity=_sha_field(fill, "fill_identity", "capital fill"),
        before_vault_snapshot_identity=_sha_field(
            before_vault,
            "snapshot_identity",
            "capital before vault",
        ),
        after_vault_snapshot_identity=_sha_field(
            after_vault,
            "snapshot_identity",
            "capital after vault",
        ),
        before_consolidated_snapshot_identity=_sha_field(
            before_parent,
            "snapshot_identity",
            "capital before parent",
        ),
        after_consolidated_snapshot_identity=_sha_field(
            after_parent,
            "snapshot_identity",
            "capital after parent",
        ),
        vault_id=vault_id,
        action=action,
        asset=source_event.asset,
        symbol=source_event.symbol,
        timeframe=source_event.timeframe,
        event_at_ms=source_event.event_at_ms,
        quantity=quantity,
        reference_price=reference_price,
        simulated_fill_price=simulated_fill_price,
        notional_usdt=notional,
        cash_before_usdt=cash_before,
        cash_after_usdt=cash_after,
        vault_nav_before_usdt=nav_before,
        vault_nav_after_usdt=nav_after,
        consolidated_nav_before_usdt=parent_before,
        consolidated_nav_after_usdt=parent_after,
        fee_usdt=fee,
        spread_usdt=spread,
        slippage_usdt=slippage,
        capital_reference_identities=refs,
        text=text,
    )


def _capital_text(
    *,
    vault_id: PaperVaultId,
    symbol: str,
    quantity: Decimal,
    reference_price: Decimal,
    simulated_fill_price: Decimal,
    notional: Decimal,
    cash_before: Decimal,
    cash_after: Decimal,
    nav_before: Decimal,
    nav_after: Decimal,
    consolidated_before: Decimal,
    consolidated_after: Decimal,
    fee: Decimal,
    spread: Decimal,
    slippage: Decimal,
) -> StreamCapitalText:
    vault_label = {
        PaperVaultId.CORE: "Core",
        PaperVaultId.TACTICAL: "Tactical",
        PaperVaultId.OPPORTUNITY_RESERVE: "Opportunity",
    }[vault_id]
    collapsed = (
        f"{vault_label} kasası {symbol} için sanal alımı gerçekleştirdi: "
        f"{quantity} adet, referans {reference_price} USDT, "
        f"simüle fill {simulated_fill_price} USDT. REAL_CAPITAL=0."
    )
    simple = (
        f"{vault_label} kasasında yalnız kağıt üzerinde {symbol} alımı işlendi. "
        f"Kasa nakdi {cash_before} USDT'den {cash_after} USDT'ye geçti; "
        "gerçek para ve borsa emri kullanılmadı."
    )
    technical = (
        f"R22 intent/fill ile R21 Epoch 2 accounting aynı kanıt zincirinde bağlandı. "
        f"Notional {notional} USDT; ücret {fee}, spread {spread}, slippage {slippage} USDT."
    )
    intelligence = (
        "Bu kayıt piyasa görüşünü yeniden yorumlamaz; yalnız önceden doğrulanmış "
        "forecast/proof/sizing kararının kanonik paper-capital sonucunu anlatır."
    )
    decision = (
        f"Karar sonucu: {vault_label} vault BUY işlendi. "
        "Yeni sermaye hareketi ancak yeni exact evidence ve yeni immutable karar ile oluşabilir."
    )
    capital = (
        f"{vault_label} NAV {nav_before} → {nav_after} USDT; "
        f"konsolide Epoch 2 NAV {consolidated_before} → {consolidated_after} USDT. "
        "REAL_CAPITAL=0."
    )
    return StreamCapitalText(
        collapsed_text=collapsed,
        simple_text=simple,
        technical_text=technical,
        intelligence_text=intelligence,
        decision_text=decision,
        capital_text=capital,
    )


def _capital_message_payload(value: StreamCapitalMessage) -> dict[str, object]:
    return {
        "action": value.action,
        "after_consolidated_snapshot_identity": (
            value.after_consolidated_snapshot_identity
        ),
        "after_vault_snapshot_identity": value.after_vault_snapshot_identity,
        "asset": value.asset,
        "before_consolidated_snapshot_identity": (
            value.before_consolidated_snapshot_identity
        ),
        "before_vault_snapshot_identity": value.before_vault_snapshot_identity,
        "bundle_identity": value.bundle_identity,
        "capital_reference_identities": value.capital_reference_identities,
        "cash_after_usdt": value.cash_after_usdt,
        "cash_before_usdt": value.cash_before_usdt,
        "category": value.category,
        "consolidated_nav_after_usdt": value.consolidated_nav_after_usdt,
        "consolidated_nav_before_usdt": value.consolidated_nav_before_usdt,
        "engine_version": value.engine_version,
        "event_at_ms": value.event_at_ms,
        "fee_usdt": value.fee_usdt,
        "fill_identity": value.fill_identity,
        "forecast_identity": value.forecast_identity,
        "importance": value.importance,
        "intent_identity": value.intent_identity,
        "notional_usdt": value.notional_usdt,
        "original_text_preserved": value.original_text_preserved,
        "production_authority": value.production_authority,
        "projector_version": value.projector_version,
        "proof_identity": value.proof_identity,
        "quantity": value.quantity,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "reference_price": value.reference_price,
        "schema_version": value.schema_version,
        "simulated_fill_price": value.simulated_fill_price,
        "slippage_usdt": value.slippage_usdt,
        "source_event_identity": value.source_event_identity,
        "source_kind": value.source_kind,
        "spread_usdt": value.spread_usdt,
        "story_identity": value.story_identity,
        "stream_event_identity": value.stream_event_identity,
        "subtype": value.subtype,
        "symbol": value.symbol,
        "text": value.text,
        "timeframe": value.timeframe,
        "vault_id": value.vault_id,
        "vault_nav_after_usdt": value.vault_nav_after_usdt,
        "vault_nav_before_usdt": value.vault_nav_before_usdt,
    }


def _verify_capital_payload(
    *,
    narrative_identity: str,
    event_at_ms: int,
    payload_json: str,
    expected_digest: str,
) -> dict[str, object]:
    if sha256_text(payload_json) != expected_digest:
        raise ValueError("S11 Capital Story payload digest mismatch")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("S11 Capital Story payload must decode to object")
    if raw.get("narrative_identity") != narrative_identity:
        raise ValueError("S11 Capital Story identity column mismatch")
    if raw.get("event_at_ms") != event_at_ms:
        raise ValueError("S11 Capital Story event-time column mismatch")
    payload = dict(raw)
    payload.pop("narrative_identity", None)
    if canonical_sha256(payload) != narrative_identity:
        raise ValueError("S11 Capital Story canonical identity mismatch")
    if raw.get("schema_version") != STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION:
        raise ValueError("S11 Capital Story schema mismatch")
    if raw.get("engine_version") != STREAM_ENGINE_VERSION:
        raise ValueError("S11 Capital Story engine mismatch")
    if raw.get("read_only") is not True:
        raise ValueError("S11 Capital Story read-only boundary mismatch")
    if raw.get("production_authority") is not False:
        raise ValueError("S11 Capital Story production authority mismatch")
    if raw.get("real_capital") != REAL_CAPITAL:
        raise ValueError("S11 Capital Story REAL_CAPITAL mismatch")
    return raw


def _mapping(
    value: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise TypeError(f"S11 Capital Story context missing mapping: {key}")
    return selected


def _sha_field(
    value: Mapping[str, object],
    key: str,
    label: str,
) -> str:
    selected = value.get(key)
    if not isinstance(selected, str):
        raise TypeError(f"{label} must be string")
    _require_sha256(selected, label)
    return selected


def _text_field(value: Mapping[str, object], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError(f"S11 Capital Story field {key} must be non-empty text")
    return selected


def _int_field(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int) or selected < 0:
        raise ValueError(f"S11 Capital Story field {key} must be non-negative int")
    return selected


def _decimal_field(value: Mapping[str, object], key: str) -> Decimal:
    selected = value.get(key)
    try:
        result = Decimal(str(selected))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"S11 Capital Story field {key} must be Decimal-compatible"
        ) from exc
    if not result.is_finite():
        raise ValueError(f"S11 Capital Story field {key} must be finite")
    return result


def _identity_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        if isinstance(value, tuple):
            values = value
        else:
            raise TypeError("S11 Capital Story source evidence must be list/tuple")
    else:
        values = tuple(value)
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise TypeError("S11 Capital Story source evidence identity must be text")
        _require_sha256(item, "S11 Capital Story source evidence")
        result.append(item)
    return tuple(result)


def _vault_field(value: Mapping[str, object]) -> PaperVaultId:
    selected = value.get("vault_id")
    if not isinstance(selected, str):
        raise TypeError("S11 Capital Story vault_id must be text")
    return PaperVaultId(selected)


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"S11 {label}s must be non-empty sorted unique")
    for identity in values:
        _require_sha256(identity, f"S11 {label}")


def _decimal(value: Decimal, label: str, *, positive: bool) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"S11 Capital Story {label} must be finite Decimal")
    if value < 0 or (positive and value <= 0):
        raise ValueError(f"S11 Capital Story {label} is outside allowed range")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
