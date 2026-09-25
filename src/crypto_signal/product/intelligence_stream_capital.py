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
    outcome_identity: str | None
    financial_outcome: str | None
    realized_pnl_delta_usdt: Decimal | None
    position_quantity_before: Decimal | None
    position_quantity_after: Decimal | None
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
        expected_subtype = {
            "BUY": "capital_executed",
            "REDUCE": "capital_reduced",
            "EXIT": "capital_exited",
        }.get(self.action)
        if expected_subtype is None or self.subtype != expected_subtype:
            raise ValueError("S11 Capital Story action/subtype mismatch")
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
        for amount, amount_label, positive in (
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
            _decimal(amount, amount_label, positive=positive)
        if self.action == "BUY":
            if any(
                value is not None
                for value in (
                    self.outcome_identity,
                    self.financial_outcome,
                    self.realized_pnl_delta_usdt,
                    self.position_quantity_before,
                    self.position_quantity_after,
                )
            ):
                raise ValueError("S11 BUY cannot carry sell outcome evidence")
        else:
            if self.outcome_identity is None:
                raise ValueError("S11 sell Capital Story requires outcome identity")
            _require_sha256(self.outcome_identity, "capital outcome")
            if not self.financial_outcome:
                raise ValueError("S11 sell Capital Story requires financial outcome")
            if self.realized_pnl_delta_usdt is None:
                raise ValueError("S11 sell Capital Story requires realized PnL")
            if (
                not self.realized_pnl_delta_usdt.is_finite()
                or self.position_quantity_before is None
                or self.position_quantity_after is None
            ):
                raise ValueError("S11 sell Capital Story outcome quantities are invalid")
            _decimal(
                self.position_quantity_before,
                "position quantity before",
                positive=True,
            )
            _decimal(
                self.position_quantity_after,
                "position quantity after",
                positive=False,
            )
            if self.action == "EXIT" and self.position_quantity_after != 0:
                raise ValueError("S11 EXIT Capital Story must flatten position")
            if self.action == "REDUCE" and self.position_quantity_after <= 0:
                raise ValueError("S11 REDUCE Capital Story must leave open position")
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
        if self.outcome_identity is not None:
            required_refs.add(self.outcome_identity)
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
    outcome_value = context.get("outcome")
    outcome = outcome_value if isinstance(outcome_value, dict) else None

    forecast_identity = _sha_field(intent, "forecast_identity", "R22 intent forecast")
    proof_identity = _sha_field(intent, "proof_identity", "R22 intent proof")
    action = _text_field(intent, "action")
    if action == "BUY":
        if outcome is not None:
            raise ValueError("S11 BUY bundle unexpectedly carries sell outcome")
    elif action in {"REDUCE", "EXIT"}:
        if outcome is None:
            raise ValueError("S11 sell bundle lost persisted outcome evidence")
    else:
        raise ValueError("S11 Capital Story supports BUY/REDUCE/EXIT bundles only")

    stream_ledger = IntelligenceStreamLedger(stream_path)
    activation = stream_ledger.read_activation()
    decision_context = stream_ledger.read_context_for_forecast(forecast_identity)
    if decision_context is None:
        raise ValueError(
            "S11 Capital Story requires existing forward Stream decision context"
        )
    if decision_context.get("proof_identity") != proof_identity:
        raise ValueError("S11 Capital Story decision-context proof mismatch")

    source_event = _build_capital_source_event(
        activation=activation,
        decision_context=decision_context,
        bundle=bundle,
        intent=intent,
        fill=fill,
        before_vault=before_vault,
        after_vault=after_vault,
        before_parent=before_parent,
        after_parent=after_parent,
        outcome=outcome,
    )
    event_disposition = stream_ledger.append_source_event(source_event)
    message = _build_capital_message(
        source_event=source_event,
        decision_context=decision_context,
        bundle=bundle,
        intent=intent,
        fill=fill,
        before_vault=before_vault,
        after_vault=after_vault,
        before_parent=before_parent,
        after_parent=after_parent,
        outcome=outcome,
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
    return _build_capital_source_event(
        activation=activation,
        decision_context=decision_context,
        bundle=bundle,
        intent=intent,
        fill=fill,
        before_vault=before_vault,
        after_vault=after_vault,
        before_parent=before_parent,
        after_parent=after_parent,
        outcome=None,
    )


def _build_capital_source_event(
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
    outcome: Mapping[str, object] | None,
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
    action = _text_field(intent, "action")
    subtype = _capital_subtype(action)
    if decision_context.get("forecast_identity") != forecast_identity:
        raise ValueError("S11 Capital Story forecast/context mismatch")
    if decision_context.get("proof_identity") != proof_identity:
        raise ValueError("S11 Capital Story proof/context mismatch")
    event_at_ms = _int_field(bundle, "snapshot_at_ms")
    evidence_set = {
        bundle_identity,
        _sha_field(intent, "intent_identity", "R22 intent"),
        _sha_field(fill, "fill_identity", "R22 fill"),
        _sha_field(before_vault, "snapshot_identity", "R21 before vault"),
        _sha_field(after_vault, "snapshot_identity", "R21 after vault"),
        _sha_field(before_parent, "snapshot_identity", "R21 before consolidated"),
        _sha_field(after_parent, "snapshot_identity", "R21 after consolidated"),
        *_identity_values(intent.get("source_evidence_identities")),
    }
    if outcome is not None:
        outcome_identity = _sha_field(outcome, "outcome_identity", "S11 outcome")
        if outcome.get("source_fill_identity") != fill.get("fill_identity"):
            raise ValueError("S11 sell outcome/fill lineage mismatch")
        if outcome.get("action") != action:
            raise ValueError("S11 sell outcome/action mismatch")
        evidence_set.add(outcome_identity)
        evidence_set.update(_identity_values(outcome.get("source_evidence_identities")))
    elif action != "BUY":
        raise ValueError("S11 sell source event requires persisted outcome")

    evidence = tuple(sorted(evidence_set))
    vault_id = _vault_field(bundle)
    materiality_codes = tuple(
        sorted(
            {
                subtype,
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
        "subtype": subtype,
        "symbol": _text_field(decision_context, "symbol"),
        "timeframe": _text_field(decision_context, "timeframe"),
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation_identity,
        source_event_identity=bundle_identity,
        category=StreamCategory.CAPITAL,
        subtype=subtype,
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
    return _build_capital_message(
        source_event=source_event,
        decision_context=decision_context,
        bundle=bundle,
        intent=intent,
        fill=fill,
        before_vault=before_vault,
        after_vault=after_vault,
        before_parent=before_parent,
        after_parent=after_parent,
        outcome=None,
    )


def _build_capital_message(
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
    outcome: Mapping[str, object] | None,
) -> StreamCapitalMessage:
    forecast_identity = _sha_field(intent, "forecast_identity", "capital forecast")
    proof_identity = _sha_field(intent, "proof_identity", "capital proof")
    bundle_identity = _sha_field(bundle, "bundle_identity", "capital bundle")
    vault_id = _vault_field(bundle)
    action = _text_field(intent, "action")
    subtype = _capital_subtype(action)
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

    outcome_identity: str | None = None
    financial_outcome: str | None = None
    realized_pnl: Decimal | None = None
    position_before: Decimal | None = None
    position_after: Decimal | None = None
    if action == "BUY":
        if outcome is not None:
            raise ValueError("S11 BUY message unexpectedly carries sell outcome")
        text_bundle = _capital_text(
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
    else:
        if outcome is None:
            raise ValueError("S11 sell message requires persisted outcome")
        outcome_identity = _sha_field(outcome, "outcome_identity", "capital outcome")
        financial_outcome = _text_field(outcome, "financial_outcome")
        realized_pnl = _decimal_field(outcome, "realized_pnl_delta_usdt")
        position_before = _decimal_field(outcome, "position_quantity_before")
        position_after = _decimal_field(outcome, "position_quantity_after")
        if outcome.get("source_fill_identity") != fill.get("fill_identity"):
            raise ValueError("S11 sell message outcome/fill mismatch")
        if outcome.get("action") != action:
            raise ValueError("S11 sell message outcome/action mismatch")
        text_bundle = _capital_sell_text(
            action=action,
            vault_id=vault_id,
            symbol=source_event.symbol,
            quantity=quantity,
            reference_price=reference_price,
            simulated_fill_price=simulated_fill_price,
            cash_before=cash_before,
            cash_after=cash_after,
            nav_before=nav_before,
            nav_after=nav_after,
            consolidated_before=parent_before,
            consolidated_after=parent_after,
            realized_pnl=realized_pnl,
            financial_outcome=financial_outcome,
            position_before=position_before,
            position_after=position_after,
            fee=fee,
            spread=spread,
            slippage=slippage,
        )

    refs = tuple(
        sorted(
            {
                *source_event.evidence_identities,
                source_event.stream_event_identity,
            }
        )
    )
    payload = {
        "action": action,
        "after_consolidated_snapshot_identity": _sha_field(
            after_parent, "snapshot_identity", "capital after parent"
        ),
        "after_vault_snapshot_identity": _sha_field(
            after_vault, "snapshot_identity", "capital after vault"
        ),
        "asset": source_event.asset,
        "before_consolidated_snapshot_identity": _sha_field(
            before_parent, "snapshot_identity", "capital before parent"
        ),
        "before_vault_snapshot_identity": _sha_field(
            before_vault, "snapshot_identity", "capital before vault"
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
        "financial_outcome": financial_outcome,
        "forecast_identity": forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "intent_identity": _sha_field(intent, "intent_identity", "capital intent"),
        "notional_usdt": notional,
        "original_text_preserved": True,
        "outcome_identity": outcome_identity,
        "position_quantity_after": position_after,
        "position_quantity_before": position_before,
        "production_authority": False,
        "projector_version": STREAM_CAPITAL_PROJECTOR_VERSION,
        "proof_identity": proof_identity,
        "quantity": quantity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "realized_pnl_delta_usdt": realized_pnl,
        "reference_price": reference_price,
        "schema_version": STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION,
        "simulated_fill_price": simulated_fill_price,
        "slippage_usdt": slippage,
        "source_event_identity": source_event.source_event_identity,
        "source_kind": StreamNarrativeSourceKind.DETERMINISTIC,
        "spread_usdt": spread,
        "story_identity": build_forecast_story_identity(forecast_identity),
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": subtype,
        "symbol": source_event.symbol,
        "text": text_bundle,
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
            before_vault, "snapshot_identity", "capital before vault"
        ),
        after_vault_snapshot_identity=_sha_field(
            after_vault, "snapshot_identity", "capital after vault"
        ),
        before_consolidated_snapshot_identity=_sha_field(
            before_parent, "snapshot_identity", "capital before parent"
        ),
        after_consolidated_snapshot_identity=_sha_field(
            after_parent, "snapshot_identity", "capital after parent"
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
        outcome_identity=outcome_identity,
        financial_outcome=financial_outcome,
        realized_pnl_delta_usdt=realized_pnl,
        position_quantity_before=position_before,
        position_quantity_after=position_after,
        capital_reference_identities=refs,
        text=text_bundle,
        subtype=subtype,
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



def _capital_sell_text(
    *,
    action: str,
    vault_id: PaperVaultId,
    symbol: str,
    quantity: Decimal,
    reference_price: Decimal,
    simulated_fill_price: Decimal,
    cash_before: Decimal,
    cash_after: Decimal,
    nav_before: Decimal,
    nav_after: Decimal,
    consolidated_before: Decimal,
    consolidated_after: Decimal,
    realized_pnl: Decimal,
    financial_outcome: str,
    position_before: Decimal,
    position_after: Decimal,
    fee: Decimal,
    spread: Decimal,
    slippage: Decimal,
) -> StreamCapitalText:
    vault_label = {
        PaperVaultId.CORE: "Core",
        PaperVaultId.TACTICAL: "Tactical",
        PaperVaultId.OPPORTUNITY_RESERVE: "Opportunity",
    }[vault_id]
    verb = "azalttı" if action == "REDUCE" else "kapattı"
    collapsed = (
        f"{vault_label} kasası {symbol} paper pozisyonunu {verb}: {quantity} adet, "
        f"simüle fill {simulated_fill_price} USDT, gerçekleşen PnL {realized_pnl} USDT. "
        "REAL_CAPITAL=0."
    )
    simple = (
        f"{vault_label} kasasında {symbol} pozisyon miktarı "
        f"{position_before} → {position_after} oldu. Bu yalnız sanal muhasebe hareketidir."
    )
    technical = (
        f"R22 {action} fill ve immutable outcome evidence birlikte doğrulandı. "
        f"Referans {reference_price}; fee {fee}, spread {spread}, slippage {slippage} USDT."
    )
    intelligence = (
        "Bu mesaj yeni piyasa yorumu üretmez; açık pozisyonun exact geçmiş fill maliyet "
        "bazından hesaplanan kanonik paper sonucunu taşır."
    )
    decision = (
        f"Karar sonucu: {vault_label} vault {action}. Finansal sonuç: {financial_outcome}."
    )
    capital = (
        f"Nakit {cash_before} → {cash_after} USDT; vault NAV {nav_before} → {nav_after}; "
        f"Epoch 2 NAV {consolidated_before} → {consolidated_after} USDT. REAL_CAPITAL=0."
    )
    return StreamCapitalText(
        collapsed_text=collapsed,
        simple_text=simple,
        technical_text=technical,
        intelligence_text=intelligence,
        decision_text=decision,
        capital_text=capital,
    )


def _capital_subtype(action: str) -> str:
    mapping = {
        "BUY": "capital_executed",
        "REDUCE": "capital_reduced",
        "EXIT": "capital_exited",
    }
    subtype = mapping.get(action)
    if subtype is None:
        raise ValueError("S11 Capital Story action is not projectable")
    return subtype

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
        "financial_outcome": value.financial_outcome,
        "forecast_identity": value.forecast_identity,
        "importance": value.importance,
        "intent_identity": value.intent_identity,
        "notional_usdt": value.notional_usdt,
        "original_text_preserved": value.original_text_preserved,
        "outcome_identity": value.outcome_identity,
        "position_quantity_after": value.position_quantity_after,
        "position_quantity_before": value.position_quantity_before,
        "production_authority": value.production_authority,
        "projector_version": value.projector_version,
        "proof_identity": value.proof_identity,
        "quantity": value.quantity,
        "read_only": value.read_only,
        "real_capital": value.real_capital,
        "realized_pnl_delta_usdt": value.realized_pnl_delta_usdt,
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
