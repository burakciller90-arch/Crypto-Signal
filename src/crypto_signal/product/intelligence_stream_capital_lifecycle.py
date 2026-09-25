"""S11 first-class candidate, accounting and outcome messages.

This module completes the Capital Story lifecycle without inventing market truth:
- candidate is reconstructed only from the three persisted allocator vault decisions;
- accounting_updated is reconstructed only from the verified R22/R21 bundle context;
- outcome is reconstructed only from persisted S11 outcome evidence.

All messages remain paper-only and REAL_CAPITAL=0.
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
from crypto_signal.paper.canonical_vault_decisions import CanonicalVaultDecisionLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital import (
    StreamCapitalProjectionResult,
    StreamCapitalText,
    project_capital_bundle_to_stream,
)
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

STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION = (
    "intelligence-stream-capital-lifecycle-message-v1/1"
)
STREAM_CAPITAL_LIFECYCLE_LEDGER_SCHEMA_VERSION = (
    "intelligence-stream-capital-lifecycle-ledger-v1/1"
)
STREAM_CAPITAL_LIFECYCLE_PROJECTOR_VERSION = (
    "stream-s11-capital-lifecycle-projector-v1/1"
)


class StreamCapitalLifecycleWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamCapitalLifecycleMessage:
    narrative_identity: str
    source_event_identity: str
    stream_event_identity: str
    story_identity: str
    lifecycle_identity: str
    subtype: str
    asset: str
    symbol: str
    timeframe: str
    event_at_ms: int
    source_as_of_ms: int
    vault_id: PaperVaultId | None
    allocator_assessment_identity: str | None
    allocator_candidate_identity: str | None
    forecast_identity: str | None
    proof_identity: str | None
    decision_context_identity: str | None
    bundle_identity: str | None
    outcome_identity: str | None
    action: str | None
    financial_outcome: str | None
    realized_pnl_delta_usdt: Decimal | None
    position_quantity_before: Decimal | None
    position_quantity_after: Decimal | None
    cash_before_usdt: Decimal | None
    cash_after_usdt: Decimal | None
    vault_nav_before_usdt: Decimal | None
    vault_nav_after_usdt: Decimal | None
    consolidated_nav_before_usdt: Decimal | None
    consolidated_nav_after_usdt: Decimal | None
    capital_reference_identities: tuple[str, ...]
    text: StreamCapitalText
    category: StreamCategory = StreamCategory.CAPITAL
    importance: StreamImportance = StreamImportance.IMPORTANT
    source_kind: StreamNarrativeSourceKind = StreamNarrativeSourceKind.DETERMINISTIC
    original_text_preserved: bool = True
    projector_version: str = STREAM_CAPITAL_LIFECYCLE_PROJECTOR_VERSION
    schema_version: str = STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.narrative_identity, "capital lifecycle narrative"),
            (self.source_event_identity, "capital lifecycle source event"),
            (self.stream_event_identity, "capital lifecycle stream event"),
            (self.story_identity, "capital lifecycle story"),
            (self.lifecycle_identity, "capital lifecycle identity"),
        ):
            _sha(identity, label)
        for identity, label in (
            (self.allocator_assessment_identity, "allocator assessment"),
            (self.allocator_candidate_identity, "allocator candidate"),
            (self.forecast_identity, "forecast"),
            (self.proof_identity, "proof"),
            (self.decision_context_identity, "decision context"),
            (self.bundle_identity, "R22 bundle"),
            (self.outcome_identity, "capital outcome"),
        ):
            if identity is not None:
                _sha(identity, label)
        if self.subtype not in {
            "capital_candidate",
            "capital_accounting_updated",
            "capital_outcome",
        }:
            raise ValueError("unsupported S11 capital lifecycle subtype")
        if not self.asset.strip() or not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("S11 capital lifecycle market context must be non-empty")
        if min(self.event_at_ms, self.source_as_of_ms) < 0:
            raise ValueError("S11 capital lifecycle timestamps must be non-negative")
        if self.event_at_ms < self.source_as_of_ms:
            raise ValueError("S11 capital lifecycle event predates source truth")
        _identities(self.capital_reference_identities, "capital lifecycle reference")
        if self.lifecycle_identity not in self.capital_reference_identities:
            raise ValueError("S11 capital lifecycle lost lifecycle identity")
        if self.subtype == "capital_candidate":
            self._validate_candidate()
        elif self.subtype == "capital_accounting_updated":
            self._validate_accounting()
        else:
            self._validate_outcome()
        if (
            self.category is not StreamCategory.CAPITAL
            or self.importance is not StreamImportance.IMPORTANT
            or self.source_kind is not StreamNarrativeSourceKind.DETERMINISTIC
            or not self.original_text_preserved
            or self.projector_version != STREAM_CAPITAL_LIFECYCLE_PROJECTOR_VERSION
            or self.schema_version != STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION
            or self.engine_version != STREAM_ENGINE_VERSION
            or not self.read_only
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("S11 capital lifecycle authority/version mismatch")
        if self.narrative_identity != canonical_sha256(_message_payload(self)):
            raise ValueError("S11 capital lifecycle narrative identity mismatch")

    def _validate_candidate(self) -> None:
        if (
            self.vault_id is not None
            or self.allocator_assessment_identity is None
            or self.allocator_candidate_identity is None
            or self.lifecycle_identity != self.allocator_candidate_identity
        ):
            raise ValueError("S11 candidate identity/context mismatch")
        if any(
            value is not None
            for value in (
                self.forecast_identity,
                self.proof_identity,
                self.decision_context_identity,
                self.bundle_identity,
                self.outcome_identity,
                self.action,
                self.financial_outcome,
                self.realized_pnl_delta_usdt,
                self.position_quantity_before,
                self.position_quantity_after,
                self.cash_before_usdt,
                self.cash_after_usdt,
                self.vault_nav_before_usdt,
                self.vault_nav_after_usdt,
                self.consolidated_nav_before_usdt,
                self.consolidated_nav_after_usdt,
            )
        ):
            raise ValueError("S11 candidate cannot invent trade/accounting state")
        if not {
            self.allocator_assessment_identity,
            self.allocator_candidate_identity,
        }.issubset(set(self.capital_reference_identities)):
            raise ValueError("S11 candidate lost allocator lineage")

    def _validate_accounting(self) -> None:
        if (
            self.vault_id is None
            or self.bundle_identity is None
            or self.forecast_identity is None
            or self.proof_identity is None
            or self.decision_context_identity is None
            or self.action not in {"BUY", "REDUCE", "EXIT"}
        ):
            raise ValueError("S11 accounting lifecycle context is incomplete")
        required_amounts = (
            self.cash_before_usdt,
            self.cash_after_usdt,
            self.vault_nav_before_usdt,
            self.vault_nav_after_usdt,
            self.consolidated_nav_before_usdt,
            self.consolidated_nav_after_usdt,
        )
        if any(value is None for value in required_amounts):
            raise ValueError("S11 accounting lifecycle amounts are incomplete")
        for value in required_amounts:
            assert value is not None
            _decimal(value, "accounting amount", positive=False)
        if any(
            value is not None
            for value in (
                self.allocator_assessment_identity,
                self.allocator_candidate_identity,
                self.outcome_identity,
                self.financial_outcome,
                self.realized_pnl_delta_usdt,
                self.position_quantity_before,
                self.position_quantity_after,
            )
        ):
            raise ValueError("S11 accounting message mixes unrelated lifecycle truth")
        if self.bundle_identity not in self.capital_reference_identities:
            raise ValueError("S11 accounting message lost R22 bundle lineage")

    def _validate_outcome(self) -> None:
        if (
            self.vault_id is None
            or self.bundle_identity is None
            or self.outcome_identity is None
            or self.lifecycle_identity != self.outcome_identity
            or self.forecast_identity is None
            or self.proof_identity is None
            or self.decision_context_identity is None
            or self.action not in {"REDUCE", "EXIT"}
            or not self.financial_outcome
            or self.realized_pnl_delta_usdt is None
            or self.position_quantity_before is None
            or self.position_quantity_after is None
        ):
            raise ValueError("S11 outcome lifecycle context is incomplete")
        if any(
            value is not None
            for value in (
                self.allocator_assessment_identity,
                self.allocator_candidate_identity,
                self.cash_before_usdt,
                self.cash_after_usdt,
                self.vault_nav_before_usdt,
                self.vault_nav_after_usdt,
                self.consolidated_nav_before_usdt,
                self.consolidated_nav_after_usdt,
            )
        ):
            raise ValueError("S11 outcome message mixes unrelated accounting truth")
        _decimal(self.realized_pnl_delta_usdt, "realized PnL", positive=None)
        _decimal(self.position_quantity_before, "position before", positive=True)
        _decimal(self.position_quantity_after, "position after", positive=False)
        if self.action == "EXIT" and self.position_quantity_after != 0:
            raise ValueError("S11 EXIT outcome must flatten the position")
        if self.action == "REDUCE" and self.position_quantity_after <= 0:
            raise ValueError("S11 REDUCE outcome must leave an open position")
        if self.outcome_identity not in self.capital_reference_identities:
            raise ValueError("S11 outcome message lost outcome lineage")


@dataclass(frozen=True, slots=True)
class StreamCapitalLifecycleProjectionResult:
    subtype: str
    narrative_identity: str
    source_event_identity: str
    stream_event_identity: str
    source_event_disposition: StreamLedgerWriteDisposition
    message_disposition: StreamCapitalLifecycleWriteDisposition
    real_capital: int = REAL_CAPITAL


@dataclass(frozen=True, slots=True)
class StreamCapitalBundleLifecycleProjectionResult:
    execution: StreamCapitalProjectionResult
    outcome: StreamCapitalLifecycleProjectionResult | None
    accounting: StreamCapitalLifecycleProjectionResult
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamCapitalLifecycleLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_capital_lifecycle_messages (
                    narrative_identity TEXT PRIMARY KEY,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    lifecycle_identity TEXT NOT NULL UNIQUE,
                    subtype TEXT NOT NULL,
                    vault_id TEXT,
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
                    stream_capital_lifecycle_messages_immutable_{operation.lower()}
                    BEFORE {operation} ON stream_capital_lifecycle_messages
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable intelligence stream capital-lifecycle ledger'
                        );
                    END
                    """
                )

    def append(
        self,
        message: StreamCapitalLifecycleMessage,
    ) -> StreamCapitalLifecycleWriteDisposition:
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
                raise ValueError("S11 capital lifecycle source event is not persisted")
            if (
                str(source[0]) != message.source_event_identity
                or str(source[1]) != StreamCategory.CAPITAL.value
                or str(source[2]) != message.subtype
                or int(str(source[3])) != message.event_at_ms
            ):
                raise ValueError("S11 capital lifecycle source-event mismatch")
            existing = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_capital_lifecycle_messages
                WHERE narrative_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                   OR lifecycle_identity = ?
                LIMIT 1
                """,
                (
                    message.narrative_identity,
                    message.source_event_identity,
                    message.stream_event_identity,
                    message.lifecycle_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == message.narrative_identity
                    and str(existing[1]) == payload
                    and str(existing[2]) == digest
                ):
                    return StreamCapitalLifecycleWriteDisposition.UNCHANGED
                raise ValueError("immutable S11 capital lifecycle identity conflict")
            latest = connection.execute(
                """
                SELECT event_at_ms, narrative_identity
                FROM stream_capital_lifecycle_messages
                ORDER BY event_at_ms DESC, narrative_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if latest is not None and (
                message.event_at_ms,
                message.narrative_identity,
            ) <= (int(str(latest[0])), str(latest[1])):
                raise ValueError("S11 capital lifecycle append would backfill or fork")
            connection.execute(
                """
                INSERT INTO stream_capital_lifecycle_messages (
                    narrative_identity,
                    source_event_identity,
                    stream_event_identity,
                    story_identity,
                    lifecycle_identity,
                    subtype,
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
                    message.lifecycle_identity,
                    message.subtype,
                    None if message.vault_id is None else message.vault_id.value,
                    message.symbol,
                    message.timeframe,
                    message.event_at_ms,
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return StreamCapitalLifecycleWriteDisposition.INSERTED

    def read(self, narrative_identity: str) -> dict[str, object] | None:
        _sha(narrative_identity, "capital lifecycle lookup")
        if not self.path.is_file():
            return None
        uri = f"file:{quote(str(self.path.resolve()), safe='/')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                """
                SELECT event_at_ms, payload_json, payload_sha256
                FROM stream_capital_lifecycle_messages
                WHERE narrative_identity = ?
                """,
                (narrative_identity,),
            ).fetchone()
        if row is None:
            return None
        return _verify_payload(
            narrative_identity=narrative_identity,
            event_at_ms=int(str(row[0])),
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
        )


def project_capital_candidate_to_stream(
    *,
    epoch2_path: Path,
    stream_path: Path,
    allocator_assessment_identity: str,
) -> StreamCapitalLifecycleProjectionResult:
    decisions = CanonicalVaultDecisionLedger(
        epoch2_path
    ).read_assessment_decisions(allocator_assessment_identity)
    if len(decisions) != len(tuple(PaperVaultId)):
        raise ValueError("S11 candidate projection requires all three vault decisions")
    vaults = {PaperVaultId(_text(item, "vault_id")) for item in decisions}
    if vaults != set(PaperVaultId):
        raise ValueError("S11 candidate projection lost a canonical vault")
    candidate_ids = {_sha_field(item, "allocator_candidate_identity") for item in decisions}
    if len(candidate_ids) != 1:
        raise ValueError("S11 candidate projection found candidate fork")
    candidate_identity = next(iter(candidate_ids))
    assessment_ids = {
        _sha_field(item, "allocator_assessment_identity") for item in decisions
    }
    if assessment_ids != {allocator_assessment_identity}:
        raise ValueError("S11 candidate projection assessment mismatch")
    assets = {_text(item, "asset") for item in decisions}
    candidate_times = {_integer(item, "candidate_as_of_ms") for item in decisions}
    assessed_times = {_integer(item, "assessed_at_ms") for item in decisions}
    if len(assets) != 1 or len(candidate_times) != 1 or len(assessed_times) != 1:
        raise ValueError("S11 candidate projection source context fork")
    asset = next(iter(assets))
    source_as_of_ms = next(iter(candidate_times))
    event_at_ms = next(iter(assessed_times))
    refs = tuple(
        sorted(
            {
                candidate_identity,
                allocator_assessment_identity,
                *(
                    identity
                    for item in decisions
                    for identity in _identity_values(
                        item.get("source_evidence_identities")
                    )
                ),
            }
        )
    )
    story_identity = canonical_sha256(
        {
            "allocator_candidate_identity": candidate_identity,
            "capital_story_kind": "candidate",
        }
    )
    text = _candidate_text(asset)
    message = _message(
        lifecycle_identity=candidate_identity,
        subtype="capital_candidate",
        story_identity=story_identity,
        asset=asset,
        symbol=asset,
        timeframe="allocator",
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        vault_id=None,
        allocator_assessment_identity=allocator_assessment_identity,
        allocator_candidate_identity=candidate_identity,
        forecast_identity=None,
        proof_identity=None,
        decision_context_identity=None,
        bundle_identity=None,
        outcome_identity=None,
        action=None,
        financial_outcome=None,
        realized_pnl_delta_usdt=None,
        position_quantity_before=None,
        position_quantity_after=None,
        cash_before_usdt=None,
        cash_after_usdt=None,
        vault_nav_before_usdt=None,
        vault_nav_after_usdt=None,
        consolidated_nav_before_usdt=None,
        consolidated_nav_after_usdt=None,
        capital_reference_identities=refs,
        text=text,
        activation=IntelligenceStreamLedger(stream_path).read_activation(),
    )
    return _persist(stream_path, message)


def project_capital_bundle_lifecycle_to_stream(
    *,
    epoch2_path: Path,
    stream_path: Path,
    bundle_identity: str,
) -> StreamCapitalBundleLifecycleProjectionResult:
    execution = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=bundle_identity,
    )
    context = R22Epoch2AtomicTape(epoch2_path).read_bundle_story_context(
        bundle_identity
    )
    outcome = (
        None
        if context.get("outcome") is None
        else _project_outcome(
            stream_path=stream_path,
            context=context,
        )
    )
    accounting = _project_accounting(
        stream_path=stream_path,
        context=context,
    )
    return StreamCapitalBundleLifecycleProjectionResult(
        execution=execution,
        outcome=outcome,
        accounting=accounting,
    )


def _project_accounting(
    *,
    stream_path: Path,
    context: Mapping[str, object],
) -> StreamCapitalLifecycleProjectionResult:
    bundle = _mapping(context, "bundle")
    intent = _mapping(context, "intent")
    fill = _mapping(context, "fill")
    before_vault = _mapping(context, "before_vault")
    after_vault = _mapping(context, "after_vault")
    before_parent = _mapping(context, "before_consolidated")
    after_parent = _mapping(context, "after_consolidated")
    forecast_identity, proof_identity, decision_context = _decision_context(
        stream_path,
        intent,
    )
    lifecycle_identity = _sha_field(
        after_parent,
        "snapshot_identity",
    )
    vault_id = PaperVaultId(_text(bundle, "vault_id"))
    action = _text(intent, "action")
    refs = {
        lifecycle_identity,
        _sha_field(bundle, "bundle_identity"),
        _sha_field(intent, "intent_identity"),
        _sha_field(fill, "fill_identity"),
        _sha_field(before_vault, "snapshot_identity"),
        _sha_field(after_vault, "snapshot_identity"),
        _sha_field(before_parent, "snapshot_identity"),
        forecast_identity,
        proof_identity,
    }
    outcome_value = context.get("outcome")
    if isinstance(outcome_value, dict):
        refs.add(_sha_field(outcome_value, "outcome_identity"))
    text = _accounting_text(
        vault_id=vault_id,
        action=action,
        cash_before=_decimal_field(before_vault, "cash_usdt"),
        cash_after=_decimal_field(after_vault, "cash_usdt"),
        vault_nav_before=_decimal_field(before_vault, "nav_usdt"),
        vault_nav_after=_decimal_field(after_vault, "nav_usdt"),
        parent_nav_before=_decimal_field(before_parent, "nav_usdt"),
        parent_nav_after=_decimal_field(after_parent, "nav_usdt"),
    )
    message = _message(
        lifecycle_identity=lifecycle_identity,
        subtype="capital_accounting_updated",
        story_identity=build_forecast_story_identity(forecast_identity),
        asset=_text(decision_context, "asset"),
        symbol=_text(decision_context, "symbol"),
        timeframe=_text(decision_context, "timeframe"),
        event_at_ms=_integer(fill, "snapshot_at_ms"),
        source_as_of_ms=_integer(fill, "mutated_at_ms"),
        vault_id=vault_id,
        allocator_assessment_identity=None,
        allocator_candidate_identity=None,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        decision_context_identity=_sha_field(decision_context, "context_identity"),
        bundle_identity=_sha_field(bundle, "bundle_identity"),
        outcome_identity=None,
        action=action,
        financial_outcome=None,
        realized_pnl_delta_usdt=None,
        position_quantity_before=None,
        position_quantity_after=None,
        cash_before_usdt=_decimal_field(before_vault, "cash_usdt"),
        cash_after_usdt=_decimal_field(after_vault, "cash_usdt"),
        vault_nav_before_usdt=_decimal_field(before_vault, "nav_usdt"),
        vault_nav_after_usdt=_decimal_field(after_vault, "nav_usdt"),
        consolidated_nav_before_usdt=_decimal_field(before_parent, "nav_usdt"),
        consolidated_nav_after_usdt=_decimal_field(after_parent, "nav_usdt"),
        capital_reference_identities=tuple(sorted(refs)),
        text=text,
        activation=IntelligenceStreamLedger(stream_path).read_activation(),
    )
    return _persist(stream_path, message)


def _project_outcome(
    *,
    stream_path: Path,
    context: Mapping[str, object],
) -> StreamCapitalLifecycleProjectionResult:
    bundle = _mapping(context, "bundle")
    intent = _mapping(context, "intent")
    fill = _mapping(context, "fill")
    outcome = _mapping(context, "outcome")
    forecast_identity, proof_identity, decision_context = _decision_context(
        stream_path,
        intent,
    )
    outcome_identity = _sha_field(outcome, "outcome_identity")
    if fill.get("outcome_evidence_identity") != outcome_identity:
        raise ValueError("S11 outcome lifecycle fill/outcome mismatch")
    if outcome.get("source_fill_identity") != fill.get("source_fill_identity"):
        raise ValueError("S11 outcome lifecycle source-fill mismatch")
    action = _text(intent, "action")
    if action not in {"REDUCE", "EXIT"} or outcome.get("action") != action:
        raise ValueError("S11 outcome lifecycle action mismatch")
    vault_id = PaperVaultId(_text(bundle, "vault_id"))
    refs = tuple(
        sorted(
            {
                outcome_identity,
                _sha_field(bundle, "bundle_identity"),
                _sha_field(intent, "intent_identity"),
                _sha_field(fill, "fill_identity"),
                forecast_identity,
                proof_identity,
                *_identity_values(outcome.get("source_evidence_identities")),
            }
        )
    )
    realized = _decimal_field(outcome, "realized_pnl_delta_usdt")
    position_before = _decimal_field(outcome, "position_quantity_before")
    position_after = _decimal_field(outcome, "position_quantity_after")
    financial_outcome = _text(outcome, "financial_outcome")
    text = _outcome_text(
        vault_id=vault_id,
        action=action,
        symbol=_text(decision_context, "symbol"),
        financial_outcome=financial_outcome,
        realized_pnl=realized,
        position_before=position_before,
        position_after=position_after,
    )
    message = _message(
        lifecycle_identity=outcome_identity,
        subtype="capital_outcome",
        story_identity=build_forecast_story_identity(forecast_identity),
        asset=_text(decision_context, "asset"),
        symbol=_text(decision_context, "symbol"),
        timeframe=_text(decision_context, "timeframe"),
        event_at_ms=_integer(fill, "mutated_at_ms"),
        source_as_of_ms=_integer(outcome, "filled_at_ms"),
        vault_id=vault_id,
        allocator_assessment_identity=None,
        allocator_candidate_identity=None,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        decision_context_identity=_sha_field(decision_context, "context_identity"),
        bundle_identity=_sha_field(bundle, "bundle_identity"),
        outcome_identity=outcome_identity,
        action=action,
        financial_outcome=financial_outcome,
        realized_pnl_delta_usdt=realized,
        position_quantity_before=position_before,
        position_quantity_after=position_after,
        cash_before_usdt=None,
        cash_after_usdt=None,
        vault_nav_before_usdt=None,
        vault_nav_after_usdt=None,
        consolidated_nav_before_usdt=None,
        consolidated_nav_after_usdt=None,
        capital_reference_identities=refs,
        text=text,
        activation=IntelligenceStreamLedger(stream_path).read_activation(),
    )
    return _persist(stream_path, message)


def _message(
    *,
    lifecycle_identity: str,
    subtype: str,
    story_identity: str,
    asset: str,
    symbol: str,
    timeframe: str,
    event_at_ms: int,
    source_as_of_ms: int,
    vault_id: PaperVaultId | None,
    allocator_assessment_identity: str | None,
    allocator_candidate_identity: str | None,
    forecast_identity: str | None,
    proof_identity: str | None,
    decision_context_identity: str | None,
    bundle_identity: str | None,
    outcome_identity: str | None,
    action: str | None,
    financial_outcome: str | None,
    realized_pnl_delta_usdt: Decimal | None,
    position_quantity_before: Decimal | None,
    position_quantity_after: Decimal | None,
    cash_before_usdt: Decimal | None,
    cash_after_usdt: Decimal | None,
    vault_nav_before_usdt: Decimal | None,
    vault_nav_after_usdt: Decimal | None,
    consolidated_nav_before_usdt: Decimal | None,
    consolidated_nav_after_usdt: Decimal | None,
    capital_reference_identities: tuple[str, ...],
    text: StreamCapitalText,
    activation: Mapping[str, object],
) -> StreamCapitalLifecycleMessage:
    source_event = _source_event(
        activation=activation,
        lifecycle_identity=lifecycle_identity,
        subtype=subtype,
        asset=asset,
        symbol=symbol,
        timeframe=timeframe,
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        decision_context_identity=decision_context_identity,
        evidence_identities=capital_reference_identities,
        vault_id=vault_id,
    )
    payload = {
        "action": action,
        "allocator_assessment_identity": allocator_assessment_identity,
        "allocator_candidate_identity": allocator_candidate_identity,
        "asset": asset,
        "bundle_identity": bundle_identity,
        "capital_reference_identities": capital_reference_identities,
        "cash_after_usdt": cash_after_usdt,
        "cash_before_usdt": cash_before_usdt,
        "category": StreamCategory.CAPITAL,
        "consolidated_nav_after_usdt": consolidated_nav_after_usdt,
        "consolidated_nav_before_usdt": consolidated_nav_before_usdt,
        "decision_context_identity": decision_context_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "financial_outcome": financial_outcome,
        "forecast_identity": forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "lifecycle_identity": lifecycle_identity,
        "original_text_preserved": True,
        "outcome_identity": outcome_identity,
        "position_quantity_after": position_quantity_after,
        "position_quantity_before": position_quantity_before,
        "production_authority": False,
        "projector_version": STREAM_CAPITAL_LIFECYCLE_PROJECTOR_VERSION,
        "proof_identity": proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "realized_pnl_delta_usdt": realized_pnl_delta_usdt,
        "schema_version": STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION,
        "source_as_of_ms": source_as_of_ms,
        "source_event_identity": source_event.source_event_identity,
        "source_kind": StreamNarrativeSourceKind.DETERMINISTIC,
        "story_identity": story_identity,
        "stream_event_identity": source_event.stream_event_identity,
        "subtype": subtype,
        "symbol": symbol,
        "text": text,
        "timeframe": timeframe,
        "vault_id": vault_id,
        "vault_nav_after_usdt": vault_nav_after_usdt,
        "vault_nav_before_usdt": vault_nav_before_usdt,
    }
    return StreamCapitalLifecycleMessage(
        narrative_identity=canonical_sha256(payload),
        source_event_identity=source_event.source_event_identity,
        stream_event_identity=source_event.stream_event_identity,
        story_identity=story_identity,
        lifecycle_identity=lifecycle_identity,
        subtype=subtype,
        asset=asset,
        symbol=symbol,
        timeframe=timeframe,
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        vault_id=vault_id,
        allocator_assessment_identity=allocator_assessment_identity,
        allocator_candidate_identity=allocator_candidate_identity,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        decision_context_identity=decision_context_identity,
        bundle_identity=bundle_identity,
        outcome_identity=outcome_identity,
        action=action,
        financial_outcome=financial_outcome,
        realized_pnl_delta_usdt=realized_pnl_delta_usdt,
        position_quantity_before=position_quantity_before,
        position_quantity_after=position_quantity_after,
        cash_before_usdt=cash_before_usdt,
        cash_after_usdt=cash_after_usdt,
        vault_nav_before_usdt=vault_nav_before_usdt,
        vault_nav_after_usdt=vault_nav_after_usdt,
        consolidated_nav_before_usdt=consolidated_nav_before_usdt,
        consolidated_nav_after_usdt=consolidated_nav_after_usdt,
        capital_reference_identities=capital_reference_identities,
        text=text,
    )


def _source_event(
    *,
    activation: Mapping[str, object],
    lifecycle_identity: str,
    subtype: str,
    asset: str,
    symbol: str,
    timeframe: str,
    event_at_ms: int,
    source_as_of_ms: int,
    forecast_identity: str | None,
    proof_identity: str | None,
    decision_context_identity: str | None,
    evidence_identities: tuple[str, ...],
    vault_id: PaperVaultId | None,
) -> StreamSourceEvent:
    activation_identity = _sha_field(activation, "activation_identity")
    materiality = {subtype}
    if vault_id is not None:
        materiality.add(f"vault:{vault_id.value}")
    payload = {
        "activation_identity": activation_identity,
        "asset": asset,
        "category": StreamCategory.CAPITAL,
        "decision_context_identity": decision_context_identity,
        "engine_version": STREAM_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "evidence_identities": evidence_identities,
        "forecast_identity": forecast_identity,
        "importance": StreamImportance.IMPORTANT,
        "materiality_codes": tuple(sorted(materiality)),
        "production_authority": False,
        "proof_identity": proof_identity,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "resolution_identity": None,
        "schema_version": STREAM_SOURCE_EVENT_SCHEMA_VERSION,
        "source_as_of_ms": source_as_of_ms,
        "source_event_identity": lifecycle_identity,
        "subtype": subtype,
        "symbol": symbol,
        "timeframe": timeframe,
    }
    return StreamSourceEvent(
        stream_event_identity=canonical_sha256(payload),
        activation_identity=activation_identity,
        source_event_identity=lifecycle_identity,
        category=StreamCategory.CAPITAL,
        subtype=subtype,
        importance=StreamImportance.IMPORTANT,
        asset=asset,
        symbol=symbol,
        timeframe=timeframe,
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        resolution_identity=None,
        decision_context_identity=decision_context_identity,
        evidence_identities=evidence_identities,
        materiality_codes=tuple(sorted(materiality)),
    )


def _persist(
    stream_path: Path,
    message: StreamCapitalLifecycleMessage,
) -> StreamCapitalLifecycleProjectionResult:
    stream = IntelligenceStreamLedger(stream_path)
    source_event = StreamSourceEvent(
        stream_event_identity=message.stream_event_identity,
        activation_identity=_sha_field(stream.read_activation(), "activation_identity"),
        source_event_identity=message.source_event_identity,
        category=message.category,
        subtype=message.subtype,
        importance=message.importance,
        asset=message.asset,
        symbol=message.symbol,
        timeframe=message.timeframe,
        event_at_ms=message.event_at_ms,
        source_as_of_ms=message.source_as_of_ms,
        forecast_identity=message.forecast_identity,
        proof_identity=message.proof_identity,
        resolution_identity=None,
        decision_context_identity=message.decision_context_identity,
        evidence_identities=message.capital_reference_identities,
        materiality_codes=tuple(
            sorted(
                {
                    message.subtype,
                    *(
                        ()
                        if message.vault_id is None
                        else (f"vault:{message.vault_id.value}",)
                    ),
                }
            )
        ),
    )
    event_disposition = stream.append_source_event(source_event)
    message_disposition = IntelligenceStreamCapitalLifecycleLedger(
        stream_path
    ).append(message)
    return StreamCapitalLifecycleProjectionResult(
        subtype=message.subtype,
        narrative_identity=message.narrative_identity,
        source_event_identity=message.source_event_identity,
        stream_event_identity=message.stream_event_identity,
        source_event_disposition=event_disposition,
        message_disposition=message_disposition,
    )


def _decision_context(
    stream_path: Path,
    intent: Mapping[str, object],
) -> tuple[str, str, dict[str, object]]:
    forecast_identity = _sha_field(intent, "forecast_identity")
    proof_identity = _sha_field(intent, "proof_identity")
    context = IntelligenceStreamLedger(stream_path).read_context_for_forecast(
        forecast_identity
    )
    if context is None:
        raise ValueError("S11 capital lifecycle requires Stream decision context")
    if context.get("proof_identity") != proof_identity:
        raise ValueError("S11 capital lifecycle proof/context mismatch")
    return forecast_identity, proof_identity, context


def _candidate_text(asset: str) -> StreamCapitalText:
    return StreamCapitalText(
        collapsed_text=(
            f"{asset} Smart Capital adayı üç vault değerlendirmesine alındı. "
            "Henüz sizing veya fill yok. REAL_CAPITAL=0."
        ),
        simple_text=(
            "Sistem sanal sermaye için bir aday tespit etti; Core, Tactical ve "
            "Opportunity kuralları şimdi bu adayı bağımsız değerlendirecek."
        ),
        technical_text=(
            "Candidate, aynı immutable allocator assessment ve source-evidence "
            "kimliklerinden yeniden üretildi; trade authority taşımaz."
        ),
        intelligence_text=(
            "Bu mesaj işlem önerisi değildir; yalnız üç-vault karar zincirinin "
            "başladığını gösterir."
        ),
        decision_text="Henüz vault kararı yok; eligible/hold/blocked mesajları sonra gelir.",
        capital_text="Sermaye hareketi yok · sizing yok · fill yok · REAL_CAPITAL=0.",
    )


def _accounting_text(
    *,
    vault_id: PaperVaultId,
    action: str,
    cash_before: Decimal,
    cash_after: Decimal,
    vault_nav_before: Decimal,
    vault_nav_after: Decimal,
    parent_nav_before: Decimal,
    parent_nav_after: Decimal,
) -> StreamCapitalText:
    label = _vault_label(vault_id)
    return StreamCapitalText(
        collapsed_text=(
            f"{label} muhasebesi {action} sonrası güncellendi: nakit "
            f"{cash_before} → {cash_after} USDT, vault NAV "
            f"{vault_nav_before} → {vault_nav_after}. REAL_CAPITAL=0."
        ),
        simple_text=(
            "Simüle işlem sonrasında kasa ve NAV kanonik Epoch 2 muhasebesine işlendi."
        ),
        technical_text=(
            f"R21 after-snapshot ve consolidated snapshot exact R22 bundle ile bağlı. "
            f"Epoch 2 NAV {parent_nav_before} → {parent_nav_after} USDT."
        ),
        intelligence_text=(
            "Bu olay piyasa sinyali değildir; yalnız immutable paper accounting değişimini açıklar."
        ),
        decision_text=f"Muhasebe sonucu: {label} vault {action} sonrası yeni snapshot'a geçti.",
        capital_text=(
            f"Nakit {cash_before} → {cash_after}; vault NAV {vault_nav_before} → "
            f"{vault_nav_after}; Epoch 2 NAV {parent_nav_before} → {parent_nav_after}. "
            "REAL_CAPITAL=0."
        ),
    )


def _outcome_text(
    *,
    vault_id: PaperVaultId,
    action: str,
    symbol: str,
    financial_outcome: str,
    realized_pnl: Decimal,
    position_before: Decimal,
    position_after: Decimal,
) -> StreamCapitalText:
    label = _vault_label(vault_id)
    return StreamCapitalText(
        collapsed_text=(
            f"{label} {symbol} {action} sonucu: {financial_outcome}, gerçekleşen "
            f"paper PnL {realized_pnl} USDT. REAL_CAPITAL=0."
        ),
        simple_text=(
            f"Pozisyon miktarı {position_before} → {position_after}; sonuç yalnız sanal sermayeye aittir."
        ),
        technical_text=(
            "Outcome, verified R22 source fill ve weighted-average cost-basis evidence "
            "üzerinden immutable olarak yeniden doğrulandı."
        ),
        intelligence_text=(
            "Bu olay yeni piyasa yorumu üretmez; kapanan/azalan pozisyonun finansal sonucudur."
        ),
        decision_text=f"Finansal sonuç: {financial_outcome}.",
        capital_text=f"Gerçekleşen paper PnL {realized_pnl} USDT · REAL_CAPITAL=0.",
    )


def _vault_label(vault_id: PaperVaultId) -> str:
    return {
        PaperVaultId.CORE: "Core",
        PaperVaultId.TACTICAL: "Tactical",
        PaperVaultId.OPPORTUNITY_RESERVE: "Opportunity",
    }[vault_id]


def _message_payload(value: StreamCapitalLifecycleMessage) -> dict[str, object]:
    return {
        field: getattr(value, field)
        for field in (
            "action",
            "allocator_assessment_identity",
            "allocator_candidate_identity",
            "asset",
            "bundle_identity",
            "capital_reference_identities",
            "cash_after_usdt",
            "cash_before_usdt",
            "category",
            "consolidated_nav_after_usdt",
            "consolidated_nav_before_usdt",
            "decision_context_identity",
            "engine_version",
            "event_at_ms",
            "financial_outcome",
            "forecast_identity",
            "importance",
            "lifecycle_identity",
            "original_text_preserved",
            "outcome_identity",
            "position_quantity_after",
            "position_quantity_before",
            "production_authority",
            "projector_version",
            "proof_identity",
            "read_only",
            "real_capital",
            "realized_pnl_delta_usdt",
            "schema_version",
            "source_as_of_ms",
            "source_event_identity",
            "source_kind",
            "story_identity",
            "stream_event_identity",
            "subtype",
            "symbol",
            "text",
            "timeframe",
            "vault_id",
            "vault_nav_after_usdt",
            "vault_nav_before_usdt",
        )
    }


def _verify_payload(
    *,
    narrative_identity: str,
    event_at_ms: int,
    payload_json: str,
    expected_digest: str,
) -> dict[str, object]:
    if sha256_text(payload_json) != expected_digest:
        raise ValueError("S11 capital lifecycle payload digest mismatch")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("S11 capital lifecycle payload must decode to object")
    if raw.get("narrative_identity") != narrative_identity:
        raise ValueError("S11 capital lifecycle identity column mismatch")
    if raw.get("event_at_ms") != event_at_ms:
        raise ValueError("S11 capital lifecycle event-time column mismatch")
    payload = dict(raw)
    payload.pop("narrative_identity", None)
    if canonical_sha256(payload) != narrative_identity:
        raise ValueError("S11 capital lifecycle canonical identity mismatch")
    if raw.get("schema_version") != STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION:
        raise ValueError("S11 capital lifecycle schema mismatch")
    if raw.get("real_capital") != REAL_CAPITAL:
        raise ValueError("S11 capital lifecycle REAL_CAPITAL mismatch")
    if raw.get("production_authority") is not False:
        raise ValueError("S11 capital lifecycle authority mismatch")
    return raw


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise TypeError(f"S11 capital lifecycle missing mapping: {key}")
    return selected


def _sha_field(value: Mapping[str, object], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str):
        raise TypeError(f"S11 capital lifecycle field {key} must be text")
    _sha(selected, key)
    return selected


def _text(value: Mapping[str, object], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError(f"S11 capital lifecycle field {key} must be non-empty text")
    return selected


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int) or selected < 0:
        raise ValueError(f"S11 capital lifecycle field {key} must be non-negative int")
    return selected


def _decimal_field(value: Mapping[str, object], key: str) -> Decimal:
    selected = value.get(key)
    try:
        result = Decimal(str(selected))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"S11 capital lifecycle field {key} must be Decimal-compatible"
        ) from exc
    if not result.is_finite():
        raise ValueError(f"S11 capital lifecycle field {key} must be finite")
    return result


def _identity_values(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        values = tuple(value)
    elif isinstance(value, tuple):
        values = value
    else:
        raise TypeError("S11 capital lifecycle evidence must be list/tuple")
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise TypeError("S11 capital lifecycle evidence identity must be text")
        _sha(item, "capital lifecycle evidence")
        result.append(item)
    return tuple(result)


def _identities(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"S11 {label} identities must be non-empty sorted unique")
    for identity in values:
        _sha(identity, label)


def _decimal(
    value: Decimal,
    label: str,
    *,
    positive: bool | None,
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"S11 {label} must be finite Decimal")
    if positive is True and value <= 0:
        raise ValueError(f"S11 {label} must be positive")
    if positive is False and value < 0:
        raise ValueError(f"S11 {label} must be non-negative")


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
