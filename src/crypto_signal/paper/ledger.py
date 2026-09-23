"""Append-only SQLite ledger for the virtual 100 USDT paper fund.

Insert-only public API. No update/delete surface. No real order execution.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any

from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.paper.models import (
    BenchmarkId,
    DecisionIntentRecord,
    ExecutionCostAssumptions,
    FundCreationRecord,
    NavSnapshotRecord,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    PositionCashMutationRecord,
    SimulatedFillRecord,
)


class PaperLedgerConflictError(ValueError):
    """Raised when a deterministic identity is rebound to different content."""


class PaperLedgerWriteAuthorityError(PaperLedgerConflictError):
    """Raised when an atomic mutation loses its required write authority."""


class PaperLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


class PaperRecordKind(StrEnum):
    FUND_CREATION = "fund_creation"
    DECISION_INTENT = "decision_intent"
    SIMULATED_FILL = "simulated_fill"
    POSITION_CASH_MUTATION = "position_cash_mutation"
    NAV_SNAPSHOT = "nav_snapshot"


PaperRecord = (
    FundCreationRecord
    | DecisionIntentRecord
    | SimulatedFillRecord
    | PositionCashMutationRecord
    | NavSnapshotRecord
)


@dataclass(frozen=True, slots=True)
class PaperLedgerEntry:
    sequence_id: int
    record_kind: PaperRecordKind
    record_identity: str
    appended_at_ms: int
    payload_json: str
    record: PaperRecord


@dataclass(frozen=True, slots=True)
class PaperProcessedEventWrite:
    event_identity: str
    activation_identity: str
    outcome: str
    payload_json: str
    processed_at_ms: int

    def __post_init__(self) -> None:
        for label, value in (
            ("event_identity", self.event_identity),
            ("activation_identity", self.activation_identity),
        ):
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{label} must be SHA256")
        if not self.outcome.strip() or not self.payload_json.strip():
            raise ValueError("processed event outcome/payload must be non-empty")
        if self.processed_at_ms < 0:
            raise ValueError("processed_at_ms must be non-negative")


class _ClosingPaperLedgerConnection(sqlite3.Connection):
    """SQLite transaction context that also closes deterministically on exit."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


_TABLE_BY_KIND: dict[PaperRecordKind, str] = {
    PaperRecordKind.FUND_CREATION: "paper_fund_creations",
    PaperRecordKind.DECISION_INTENT: "paper_decision_intents",
    PaperRecordKind.SIMULATED_FILL: "paper_simulated_fills",
    PaperRecordKind.POSITION_CASH_MUTATION: "paper_position_cash_mutations",
    PaperRecordKind.NAV_SNAPSHOT: "paper_nav_snapshots",
}


def _record_kind(record: PaperRecord) -> PaperRecordKind:
    if isinstance(record, FundCreationRecord):
        return PaperRecordKind.FUND_CREATION
    if isinstance(record, DecisionIntentRecord):
        return PaperRecordKind.DECISION_INTENT
    if isinstance(record, SimulatedFillRecord):
        return PaperRecordKind.SIMULATED_FILL
    if isinstance(record, PositionCashMutationRecord):
        return PaperRecordKind.POSITION_CASH_MUTATION
    if isinstance(record, NavSnapshotRecord):
        return PaperRecordKind.NAV_SNAPSHOT
    raise TypeError(f"unsupported paper record type: {type(record)!r}")


def _record_appended_at_ms(record: PaperRecord) -> int:
    if isinstance(record, FundCreationRecord):
        return record.created_at_ms
    if isinstance(record, DecisionIntentRecord):
        return record.decided_at_ms
    if isinstance(record, SimulatedFillRecord):
        return record.filled_at_ms
    if isinstance(record, PositionCashMutationRecord):
        return record.mutated_at_ms
    if isinstance(record, NavSnapshotRecord):
        return record.snapshot_at_ms
    raise TypeError(f"unsupported paper record type: {type(record)!r}")


class PaperFundLedger:
    """Caller-supplied-path append-only paper fund ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            for table in _TABLE_BY_KIND.values():
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        record_identity TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        appended_at_ms INTEGER NOT NULL
                    )
                    """
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_replay_index (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_kind TEXT NOT NULL,
                    record_identity TEXT NOT NULL UNIQUE,
                    appended_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_activation_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    activation_identity TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    activated_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_processed_events (
                    event_identity TEXT PRIMARY KEY,
                    activation_identity TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    processed_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_write_authority_events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    authority_event_identity TEXT NOT NULL UNIQUE,
                    activation_identity TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    previous_event_identity TEXT,
                    payload_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            self._install_immutability_triggers(connection)

    def append_fund_creation(
        self,
        record: FundCreationRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.FUND_CREATION,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.created_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_decision_intent(
        self,
        record: DecisionIntentRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.DECISION_INTENT,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.decided_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_simulated_fill(
        self,
        record: SimulatedFillRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.SIMULATED_FILL,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.filled_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_position_cash_mutation(
        self,
        record: PositionCashMutationRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.POSITION_CASH_MUTATION,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.mutated_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def append_nav_snapshot(
        self,
        record: NavSnapshotRecord,
        *,
        appended_at_ms: int | None = None,
    ) -> PaperLedgerWriteDisposition:
        return self._append(
            kind=PaperRecordKind.NAV_SNAPSHOT,
            record_identity=record.record_identity,
            payload_json=canonical_json(record),
            appended_at_ms=(
                record.snapshot_at_ms if appended_at_ms is None else appended_at_ms
            ),
        )

    def replay(self) -> tuple[PaperLedgerEntry, ...]:
        """Return all paper-fund records in append order."""
        self.initialize()
        with self._connect() as connection:
            return self._replay_with_connection(connection)

    def list_fund_creations(self) -> tuple[FundCreationRecord, ...]:
        return tuple(
            entry.record
            for entry in self.replay()
            if isinstance(entry.record, FundCreationRecord)
        )

    def get_by_identity(self, record_identity: str) -> PaperLedgerEntry | None:
        for entry in self.replay():
            if entry.record_identity == record_identity:
                return entry
        return None

    def _put_activation_state(
        self,
        *,
        activation_identity: str,
        payload_json: str,
        activated_at_ms: int,
    ) -> PaperLedgerWriteDisposition:
        if activated_at_ms < 0:
            raise ValueError("activated_at_ms must be non-negative")
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT activation_identity, payload_json, activated_at_ms
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["activation_identity"]) == activation_identity
                    and str(existing["payload_json"]) == payload_json
                    and int(existing["activated_at_ms"]) == activated_at_ms
                ):
                    return PaperLedgerWriteDisposition.UNCHANGED
                raise PaperLedgerConflictError(
                    "paper activation state is immutable once created"
                )
            connection.execute(
                """
                INSERT INTO paper_activation_state (
                    singleton,
                    activation_identity,
                    payload_json,
                    activated_at_ms
                ) VALUES (1, ?, ?, ?)
                """,
                (activation_identity, payload_json, activated_at_ms),
            )
        return PaperLedgerWriteDisposition.INSERTED

    def _get_activation_state_row(self) -> tuple[str, str, int] | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT activation_identity, payload_json, activated_at_ms
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
        if row is None:
            return None
        return (
            str(row["activation_identity"]),
            str(row["payload_json"]),
            int(row["activated_at_ms"]),
        )

    def _get_processed_event_row(
        self,
        event_identity: str,
    ) -> tuple[str, str, str, int] | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT activation_identity, outcome, payload_json, processed_at_ms
                FROM paper_processed_events
                WHERE event_identity = ?
                """,
                (event_identity,),
            ).fetchone()
        if row is None:
            return None
        return (
            str(row["activation_identity"]),
            str(row["outcome"]),
            str(row["payload_json"]),
            int(row["processed_at_ms"]),
        )

    def _list_processed_event_rows(
        self,
    ) -> tuple[tuple[str, str, str, str, int], ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    event_identity,
                    activation_identity,
                    outcome,
                    payload_json,
                    processed_at_ms
                FROM paper_processed_events
                ORDER BY processed_at_ms ASC, event_identity ASC
                """
            ).fetchall()
        return tuple(
            (
                str(row["event_identity"]),
                str(row["activation_identity"]),
                str(row["outcome"]),
                str(row["payload_json"]),
                int(row["processed_at_ms"]),
            )
            for row in rows
        )

    def _append_write_authority_event(
        self,
        *,
        authority_event_identity: str,
        activation_identity: str,
        enabled: bool,
        previous_event_identity: str | None,
        payload_json: str,
        created_at_ms: int,
    ) -> PaperLedgerWriteDisposition:
        if created_at_ms < 0:
            raise ValueError("authority created_at_ms must be non-negative")
        if not authority_event_identity or not activation_identity or not payload_json:
            raise ValueError("authority identity/activation/payload are required")
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            activation = connection.execute(
                """
                SELECT activation_identity
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
            if activation is None:
                raise PaperLedgerConflictError(
                    "write authority requires persistent paper activation state"
                )
            if str(activation["activation_identity"]) != activation_identity:
                raise PaperLedgerConflictError(
                    "write authority activation identity mismatch"
                )

            existing = connection.execute(
                """
                SELECT
                    activation_identity,
                    enabled,
                    previous_event_identity,
                    payload_json,
                    created_at_ms
                FROM paper_write_authority_events
                WHERE authority_event_identity = ?
                """,
                (authority_event_identity,),
            ).fetchone()
            if existing is not None:
                exact = (
                    str(existing["activation_identity"]) == activation_identity
                    and bool(int(existing["enabled"])) is enabled
                    and (
                        None
                        if existing["previous_event_identity"] is None
                        else str(existing["previous_event_identity"])
                    )
                    == previous_event_identity
                    and str(existing["payload_json"]) == payload_json
                    and int(existing["created_at_ms"]) == created_at_ms
                )
                if exact:
                    return PaperLedgerWriteDisposition.UNCHANGED
                raise PaperLedgerConflictError(
                    "immutable write-authority event identity conflict"
                )

            latest = connection.execute(
                """
                SELECT authority_event_identity, created_at_ms
                FROM paper_write_authority_events
                ORDER BY sequence_id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_identity = (
                None
                if latest is None
                else str(latest["authority_event_identity"])
            )
            if previous_event_identity != latest_identity:
                raise PaperLedgerConflictError(
                    "write-authority previous-event lineage is stale"
                )
            if latest is not None and created_at_ms < int(latest["created_at_ms"]):
                raise PaperLedgerConflictError(
                    "write-authority event cannot predate current authority state"
                )

            connection.execute(
                """
                INSERT INTO paper_write_authority_events (
                    authority_event_identity,
                    activation_identity,
                    enabled,
                    previous_event_identity,
                    payload_json,
                    created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    authority_event_identity,
                    activation_identity,
                    1 if enabled else 0,
                    previous_event_identity,
                    payload_json,
                    created_at_ms,
                ),
            )
        return PaperLedgerWriteDisposition.INSERTED

    def _latest_write_authority_row(
        self,
    ) -> tuple[str, str, bool, str | None, str, int] | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    authority_event_identity,
                    activation_identity,
                    enabled,
                    previous_event_identity,
                    payload_json,
                    created_at_ms
                FROM paper_write_authority_events
                ORDER BY sequence_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return (
            str(row["authority_event_identity"]),
            str(row["activation_identity"]),
            bool(int(row["enabled"])),
            (
                None
                if row["previous_event_identity"] is None
                else str(row["previous_event_identity"])
            ),
            str(row["payload_json"]),
            int(row["created_at_ms"]),
        )

    def _list_write_authority_rows(
        self,
    ) -> tuple[tuple[int, str, str, bool, str | None, str, int], ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    sequence_id,
                    authority_event_identity,
                    activation_identity,
                    enabled,
                    previous_event_identity,
                    payload_json,
                    created_at_ms
                FROM paper_write_authority_events
                ORDER BY sequence_id ASC
                """
            ).fetchall()
        return tuple(
            (
                int(row["sequence_id"]),
                str(row["authority_event_identity"]),
                str(row["activation_identity"]),
                bool(int(row["enabled"])),
                (
                    None
                    if row["previous_event_identity"] is None
                    else str(row["previous_event_identity"])
                ),
                str(row["payload_json"]),
                int(row["created_at_ms"]),
            )
            for row in rows
        )

    def _append_records_and_processed_event_atomic(
        self,
        records: Sequence[PaperRecord],
        *,
        expected_replayed_record_count: int,
        event_identity: str,
        activation_identity: str,
        outcome: str,
        event_payload_json: str,
        processed_at_ms: int,
        required_authority_event_identity: str | None = None,
    ) -> tuple[PaperLedgerWriteDisposition, tuple[PaperLedgerEntry, ...]]:
        """Atomically append optional paper records plus one terminal event receipt."""
        materialized = tuple(records)
        if expected_replayed_record_count < 0:
            raise ValueError("expected replayed record count must be non-negative")
        if processed_at_ms < 0:
            raise ValueError("processed_at_ms must be non-negative")
        if not event_identity or not activation_identity or not outcome:
            raise ValueError("processed event identity/activation/outcome are required")
        if (
            required_authority_event_identity is not None
            and not required_authority_event_identity
        ):
            raise ValueError("required authority event identity must be non-empty")

        identities = tuple(record.record_identity for record in materialized)
        if len(set(identities)) != len(identities):
            raise ValueError("atomic paper ledger bundle has duplicate identities")
        prepared = tuple(
            (
                _record_kind(record),
                record.record_identity,
                canonical_json(record),
                _record_appended_at_ms(record),
            )
            for record in materialized
        )
        if any(appended_at_ms < 0 for _, _, _, appended_at_ms in prepared):
            raise ValueError("appended_at_ms must be non-negative")

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            activation = connection.execute(
                """
                SELECT activation_identity
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
            if activation is None:
                raise PaperLedgerConflictError(
                    "processed event requires persistent paper activation state"
                )
            if str(activation["activation_identity"]) != activation_identity:
                raise PaperLedgerConflictError(
                    "processed event activation identity mismatch"
                )

            if required_authority_event_identity is not None:
                authority = connection.execute(
                    """
                    SELECT
                        authority_event_identity,
                        activation_identity,
                        enabled
                    FROM paper_write_authority_events
                    ORDER BY sequence_id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if authority is None or not bool(int(authority["enabled"])):
                    raise PaperLedgerWriteAuthorityError(
                        "processed event requires enabled current paper write authority"
                    )
                if (
                    str(authority["authority_event_identity"])
                    != required_authority_event_identity
                ):
                    raise PaperLedgerWriteAuthorityError(
                        "processed event paper write authority identity changed"
                    )
                if str(authority["activation_identity"]) != activation_identity:
                    raise PaperLedgerWriteAuthorityError(
                        "processed event paper write authority activation mismatch"
                    )

            present_count = 0
            for kind, record_identity, payload_json, _ in prepared:
                table = _TABLE_BY_KIND[kind]
                payload_row = connection.execute(
                    f"""
                    SELECT payload_json
                    FROM {table}
                    WHERE record_identity = ?
                    """,
                    (record_identity,),
                ).fetchone()
                index_row = connection.execute(
                    """
                    SELECT record_kind
                    FROM paper_replay_index
                    WHERE record_identity = ?
                    """,
                    (record_identity,),
                ).fetchone()
                if payload_row is None and index_row is None:
                    continue
                if payload_row is None or index_row is None:
                    raise PaperLedgerConflictError(
                        "immutable paper ledger has incomplete existing event record"
                    )
                if str(index_row["record_kind"]) != kind.value:
                    raise PaperLedgerConflictError(
                        "immutable paper ledger event record kind conflict"
                    )
                if str(payload_row["payload_json"]) != payload_json:
                    raise PaperLedgerConflictError(
                        "immutable paper ledger event record payload conflict"
                    )
                present_count += 1

            event_row = connection.execute(
                """
                SELECT activation_identity, outcome, payload_json, processed_at_ms
                FROM paper_processed_events
                WHERE event_identity = ?
                """,
                (event_identity,),
            ).fetchone()
            if event_row is not None:
                exact_event = (
                    str(event_row["activation_identity"]) == activation_identity
                    and str(event_row["outcome"]) == outcome
                    and str(event_row["payload_json"]) == event_payload_json
                    and int(event_row["processed_at_ms"]) == processed_at_ms
                )
                if exact_event and present_count == len(prepared):
                    return (
                        PaperLedgerWriteDisposition.UNCHANGED,
                        self._replay_with_connection(connection),
                    )
                raise PaperLedgerConflictError(
                    "immutable processed event identity conflict"
                )
            if present_count:
                raise PaperLedgerConflictError(
                    "paper event transaction rejects partially existing trade records"
                )

            current_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM paper_replay_index"
                ).fetchone()["count"]
            )
            if current_count != expected_replayed_record_count:
                raise PaperLedgerConflictError(
                    "processed event rejected stale paper replay state"
                )

            for kind, record_identity, payload_json, appended_at_ms in prepared:
                table = _TABLE_BY_KIND[kind]
                connection.execute(
                    f"""
                    INSERT INTO {table} (
                        record_identity,
                        payload_json,
                        appended_at_ms
                    ) VALUES (?, ?, ?)
                    """,
                    (record_identity, payload_json, appended_at_ms),
                )
                connection.execute(
                    """
                    INSERT INTO paper_replay_index (
                        record_kind,
                        record_identity,
                        appended_at_ms
                    ) VALUES (?, ?, ?)
                    """,
                    (kind.value, record_identity, appended_at_ms),
                )

            connection.execute(
                """
                INSERT INTO paper_processed_events (
                    event_identity,
                    activation_identity,
                    outcome,
                    payload_json,
                    processed_at_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_identity,
                    activation_identity,
                    outcome,
                    event_payload_json,
                    processed_at_ms,
                ),
            )
            return (
                PaperLedgerWriteDisposition.INSERTED,
                self._replay_with_connection(connection),
            )

    def _append_records_atomic(
        self,
        records: Sequence[PaperRecord],
        *,
        expected_replayed_record_count: int,
    ) -> tuple[PaperLedgerWriteDisposition, tuple[PaperLedgerEntry, ...]]:
        """Atomically append an exact record bundle or leave the ledger unchanged."""
        materialized = tuple(records)
        if not materialized:
            raise ValueError("atomic paper ledger append requires at least one record")
        if expected_replayed_record_count < 0:
            raise ValueError("expected replayed record count must be non-negative")

        identities = tuple(record.record_identity for record in materialized)
        if len(set(identities)) != len(identities):
            raise ValueError("atomic paper ledger bundle has duplicate identities")

        prepared = tuple(
            (
                _record_kind(record),
                record.record_identity,
                canonical_json(record),
                _record_appended_at_ms(record),
            )
            for record in materialized
        )
        if any(appended_at_ms < 0 for _, _, _, appended_at_ms in prepared):
            raise ValueError("appended_at_ms must be non-negative")

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            present_count = 0
            for kind, record_identity, payload_json, _ in prepared:
                table = _TABLE_BY_KIND[kind]
                payload_row = connection.execute(
                    f"""
                    SELECT payload_json
                    FROM {table}
                    WHERE record_identity = ?
                    """,
                    (record_identity,),
                ).fetchone()
                index_row = connection.execute(
                    """
                    SELECT record_kind
                    FROM paper_replay_index
                    WHERE record_identity = ?
                    """,
                    (record_identity,),
                ).fetchone()

                if payload_row is None and index_row is None:
                    continue
                if payload_row is None or index_row is None:
                    raise PaperLedgerConflictError(
                        "immutable paper ledger has incomplete existing bundle record"
                    )
                if str(index_row["record_kind"]) != kind.value:
                    raise PaperLedgerConflictError(
                        "immutable paper ledger identity already indexed under another kind"
                    )
                if str(payload_row["payload_json"]) != payload_json:
                    raise PaperLedgerConflictError(
                        f"immutable paper ledger conflict for {kind.value} identity"
                    )
                present_count += 1

            if present_count == len(prepared):
                return (
                    PaperLedgerWriteDisposition.UNCHANGED,
                    self._replay_with_connection(connection),
                )
            if present_count:
                raise PaperLedgerConflictError(
                    "immutable paper ledger rejects a partially existing bundle"
                )

            current_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM paper_replay_index"
                ).fetchone()["count"]
            )
            if current_count != expected_replayed_record_count:
                raise PaperLedgerConflictError(
                    "immutable paper ledger rejected stale replay state"
                )

            for kind, record_identity, payload_json, appended_at_ms in prepared:
                table = _TABLE_BY_KIND[kind]
                connection.execute(
                    f"""
                    INSERT INTO {table} (
                        record_identity,
                        payload_json,
                        appended_at_ms
                    ) VALUES (?, ?, ?)
                    """,
                    (record_identity, payload_json, appended_at_ms),
                )
                connection.execute(
                    """
                    INSERT INTO paper_replay_index (
                        record_kind,
                        record_identity,
                        appended_at_ms
                    ) VALUES (?, ?, ?)
                    """,
                    (kind.value, record_identity, appended_at_ms),
                )

            return (
                PaperLedgerWriteDisposition.INSERTED,
                self._replay_with_connection(connection),
            )

    def _replay_with_connection(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[PaperLedgerEntry, ...]:
        index_rows = connection.execute(
            """
            SELECT sequence_id, record_kind, record_identity, appended_at_ms
            FROM paper_replay_index
            ORDER BY sequence_id ASC
            """
        ).fetchall()
        entries: list[PaperLedgerEntry] = []
        for row in index_rows:
            kind = PaperRecordKind(str(row["record_kind"]))
            table = _TABLE_BY_KIND[kind]
            payload_row = connection.execute(
                f"""
                SELECT payload_json
                FROM {table}
                WHERE record_identity = ?
                """,
                (str(row["record_identity"]),),
            ).fetchone()
            if payload_row is None:
                raise RuntimeError(
                    f"missing payload for paper record {row['record_identity']}"
                )
            payload_json = str(payload_row["payload_json"])
            entries.append(
                PaperLedgerEntry(
                    sequence_id=int(row["sequence_id"]),
                    record_kind=kind,
                    record_identity=str(row["record_identity"]),
                    appended_at_ms=int(row["appended_at_ms"]),
                    payload_json=payload_json,
                    record=deserialize_paper_record(kind, payload_json),
                )
            )
        return tuple(entries)

    def _append(
        self,
        *,
        kind: PaperRecordKind,
        record_identity: str,
        payload_json: str,
        appended_at_ms: int,
    ) -> PaperLedgerWriteDisposition:
        if appended_at_ms < 0:
            raise ValueError("appended_at_ms must be non-negative")
        table = _TABLE_BY_KIND[kind]
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                f"""
                SELECT payload_json
                FROM {table}
                WHERE record_identity = ?
                """,
                (record_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) == payload_json:
                    return PaperLedgerWriteDisposition.UNCHANGED
                raise PaperLedgerConflictError(
                    f"immutable paper ledger conflict for {kind.value} identity"
                )

            index_existing = connection.execute(
                """
                SELECT record_kind
                FROM paper_replay_index
                WHERE record_identity = ?
                """,
                (record_identity,),
            ).fetchone()
            if index_existing is not None:
                raise PaperLedgerConflictError(
                    "immutable paper ledger identity already indexed under another kind"
                )

            connection.execute(
                f"""
                INSERT INTO {table} (
                    record_identity,
                    payload_json,
                    appended_at_ms
                ) VALUES (?, ?, ?)
                """,
                (record_identity, payload_json, appended_at_ms),
            )
            connection.execute(
                """
                INSERT INTO paper_replay_index (
                    record_kind,
                    record_identity,
                    appended_at_ms
                ) VALUES (?, ?, ?)
                """,
                (kind.value, record_identity, appended_at_ms),
            )
        return PaperLedgerWriteDisposition.INSERTED

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            factory=_ClosingPaperLedgerConnection,
        )
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _install_immutability_triggers(connection: sqlite3.Connection) -> None:
        tables = [
            *_TABLE_BY_KIND.values(),
            "paper_replay_index",
            "paper_activation_state",
            "paper_processed_events",
            "paper_write_authority_events",
        ]
        for table in tables:
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable paper ledger rejects UPDATE');
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable paper ledger rejects DELETE');
                END
                """
            )

def deserialize_paper_record(
    kind: PaperRecordKind,
    payload_json: str,
) -> PaperRecord:
    """Rebuild a typed paper record from canonical ledger JSON."""
    raw: dict[str, Any] = json.loads(payload_json)

    def decimal_or_none(value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    def positions(value: Any) -> tuple[PaperPosition, ...]:
        return tuple(
            PaperPosition(
                symbol=PaperSymbol(str(item["symbol"])),
                quantity=Decimal(str(item["quantity"])),
            )
            for item in value
        )

    if kind is PaperRecordKind.FUND_CREATION:
        return FundCreationRecord(
            record_identity=str(raw["record_identity"]),
            created_at_ms=int(raw["created_at_ms"]),
            initial_cash_usdt=Decimal(str(raw["initial_cash_usdt"])),
            real_capital=int(raw["real_capital"]),
            positions=positions(raw["positions"]),
            schema_version=str(raw["schema_version"]),
            execution_policy_version=str(raw["execution_policy_version"]),
            risk_policy_version=str(raw["risk_policy_version"]),
            permitted_symbols=tuple(
                PaperSymbol(str(item)) for item in raw["permitted_symbols"]
            ),
            benchmark_ids=tuple(
                BenchmarkId(str(item)) for item in raw["benchmark_ids"]
            ),
        )
    if kind is PaperRecordKind.DECISION_INTENT:
        return DecisionIntentRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            decided_at_ms=int(raw["decided_at_ms"]),
            action=PaperAction(str(raw["action"])),
            symbol=(
                None
                if raw["symbol"] is None
                else PaperSymbol(str(raw["symbol"]))
            ),
            quantity=decimal_or_none(raw["quantity"]),
            reference_price=decimal_or_none(raw["reference_price"]),
            reason=str(raw["reason"]),
            invalidation_context=str(raw["invalidation_context"]),
            schema_version=str(raw["schema_version"]),
            risk_policy_version=str(raw["risk_policy_version"]),
        )
    if kind is PaperRecordKind.SIMULATED_FILL:
        costs_raw = raw["costs"]
        return SimulatedFillRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            decision_identity=str(raw["decision_identity"]),
            filled_at_ms=int(raw["filled_at_ms"]),
            action=PaperAction(str(raw["action"])),
            symbol=PaperSymbol(str(raw["symbol"])),
            quantity=Decimal(str(raw["quantity"])),
            reference_price=Decimal(str(raw["reference_price"])),
            simulated_fill_price=Decimal(str(raw["simulated_fill_price"])),
            costs=ExecutionCostAssumptions(
                fee_usdt=Decimal(str(costs_raw["fee_usdt"])),
                spread_usdt=Decimal(str(costs_raw["spread_usdt"])),
                slippage_usdt=Decimal(str(costs_raw["slippage_usdt"])),
                execution_policy_version=str(
                    costs_raw["execution_policy_version"]
                ),
                partial_fills_supported=bool(
                    costs_raw["partial_fills_supported"]
                ),
            ),
            venue_reference=str(raw["venue_reference"]),
            schema_version=str(raw["schema_version"]),
        )
    if kind is PaperRecordKind.POSITION_CASH_MUTATION:
        return PositionCashMutationRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            source_identity=str(raw["source_identity"]),
            mutated_at_ms=int(raw["mutated_at_ms"]),
            cash_before_usdt=Decimal(str(raw["cash_before_usdt"])),
            cash_after_usdt=Decimal(str(raw["cash_after_usdt"])),
            positions_before=positions(raw["positions_before"]),
            positions_after=positions(raw["positions_after"]),
            schema_version=str(raw["schema_version"]),
        )
    if kind is PaperRecordKind.NAV_SNAPSHOT:
        return NavSnapshotRecord(
            record_identity=str(raw["record_identity"]),
            fund_identity=str(raw["fund_identity"]),
            snapshot_at_ms=int(raw["snapshot_at_ms"]),
            cash_usdt=Decimal(str(raw["cash_usdt"])),
            positions=positions(raw["positions"]),
            mark_prices=tuple(
                (
                    PaperSymbol(str(item[0])),
                    Decimal(str(item[1])),
                )
                for item in raw["mark_prices"]
            ),
            nav_usdt=Decimal(str(raw["nav_usdt"])),
            benchmark_ids=tuple(
                BenchmarkId(str(item)) for item in raw["benchmark_ids"]
            ),
            schema_version=str(raw["schema_version"]),
        )
    raise ValueError(f"unsupported paper record kind: {kind}")
