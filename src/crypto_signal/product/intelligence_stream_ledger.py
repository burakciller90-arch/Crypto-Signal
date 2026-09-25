from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ACTIVATION_SCHEMA_VERSION,
    STREAM_DECISION_CONTEXT_SCHEMA_VERSION,
    STREAM_ENGINE_VERSION,
    STREAM_SOURCE_EVENT_SCHEMA_VERSION,
    StreamActivationBoundary,
    StreamDecisionContextSnapshot,
    StreamSourceEvent,
    activation_payload,
    decision_context_payload,
    source_event_payload,
)

STREAM_LEDGER_SCHEMA_VERSION = "intelligence-stream-ledger-v1/1"


class StreamLedgerConflictError(ValueError):
    """Raised when immutable Stream truth would be rebound, backfilled or forked."""


class StreamLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamLedgerStatus:
    activation_identity: str
    activated_at_ms: int
    decision_context_count: int
    source_event_count: int
    latest_event_at_ms: int | None
    schema_version: str = STREAM_LEDGER_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamLedger:
    """Append-only persistence for Intelligence Stream source truth.

    This ledger is not a Product message renderer and grants no paper/live execution
    authority. Query-only reads never initialize a missing database.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_activation (
                    activation_identity TEXT PRIMARY KEY,
                    activated_at_ms INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_decision_contexts (
                    context_identity TEXT PRIMARY KEY,
                    forecast_identity TEXT NOT NULL UNIQUE,
                    proof_identity TEXT NOT NULL UNIQUE,
                    confluence_identity TEXT NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    source_as_of_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_source_events (
                    stream_event_identity TEXT PRIMARY KEY,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    activation_identity TEXT NOT NULL,
                    decision_context_identity TEXT,
                    category TEXT NOT NULL,
                    subtype TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_as_of_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (activation_identity)
                        REFERENCES stream_activation(activation_identity),
                    FOREIGN KEY (decision_context_identity)
                        REFERENCES stream_decision_contexts(context_identity)
                );

                CREATE INDEX IF NOT EXISTS stream_source_events_chrono
                ON stream_source_events(event_at_ms, stream_event_identity);

                CREATE INDEX IF NOT EXISTS stream_decision_contexts_confluence
                ON stream_decision_contexts(confluence_identity);
                """
            )
            expected_meta = {
                "engine_version": STREAM_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected_meta.items():
                row = connection.execute(
                    "SELECT value FROM stream_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise StreamLedgerConflictError(
                        f"Stream ledger metadata mismatch for {key}"
                    )
            for table in (
                "stream_activation",
                "stream_decision_contexts",
                "stream_source_events",
                "stream_meta",
            ):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable intelligence stream ledger'
                            );
                        END
                        """
                    )

    def append_activation(
        self,
        activation: StreamActivationBoundary,
    ) -> StreamLedgerWriteDisposition:
        self.initialize()
        payload = canonical_json(activation)
        digest = sha256_text(payload)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT activation_identity, activated_at_ms, payload_json, payload_sha256
                FROM stream_activation
                ORDER BY activated_at_ms, activation_identity
                """
            ).fetchall()
            if rows:
                if len(rows) != 1:
                    raise StreamLedgerConflictError(
                        "Stream V1 permits exactly one activation boundary"
                    )
                row = rows[0]
                if (
                    str(row[0]) == activation.activation_identity
                    and int(row[1]) == activation.activated_at_ms
                    and str(row[2]) == payload
                    and str(row[3]) == digest
                ):
                    return StreamLedgerWriteDisposition.UNCHANGED
                raise StreamLedgerConflictError(
                    "Stream activation boundary is immutable"
                )
            connection.execute(
                """
                INSERT INTO stream_activation (
                    activation_identity,
                    activated_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    activation.activation_identity,
                    activation.activated_at_ms,
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return StreamLedgerWriteDisposition.INSERTED

    def append_issuance_bundle(
        self,
        context: StreamDecisionContextSnapshot,
        event: StreamSourceEvent,
    ) -> StreamLedgerWriteDisposition:
        if event.decision_context_identity != context.context_identity:
            raise StreamLedgerConflictError(
                "Stream issuance event/context identity mismatch"
            )
        if event.forecast_identity != context.forecast_identity:
            raise StreamLedgerConflictError(
                "Stream issuance event/context forecast mismatch"
            )
        if event.proof_identity != context.proof_identity:
            raise StreamLedgerConflictError(
                "Stream issuance event/context proof mismatch"
            )
        if event.event_at_ms != context.issued_at_ms:
            raise StreamLedgerConflictError(
                "Stream issuance event/context timestamp mismatch"
            )
        if event.source_as_of_ms != context.source_as_of_ms:
            raise StreamLedgerConflictError(
                "Stream issuance event/context source cutoff mismatch"
            )

        self.initialize()
        context_json = canonical_json(context)
        context_digest = sha256_text(context_json)
        event_json = canonical_json(event)
        event_digest = sha256_text(event_json)

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)
            activation = self._activation_row(connection)
            activation_identity = str(activation[0])
            activated_at_ms = int(activation[1])
            if event.activation_identity != activation_identity:
                raise StreamLedgerConflictError(
                    "Stream event activation identity mismatch"
                )
            if min(context.issued_at_ms, event.event_at_ms) < activated_at_ms:
                raise StreamLedgerConflictError(
                    "Stream refuses rich history before activation boundary"
                )

            existing_context = connection.execute(
                """
                SELECT context_identity, payload_json, payload_sha256
                FROM stream_decision_contexts
                WHERE context_identity = ?
                   OR forecast_identity = ?
                   OR proof_identity = ?
                LIMIT 1
                """,
                (
                    context.context_identity,
                    context.forecast_identity,
                    context.proof_identity,
                ),
            ).fetchone()
            existing_event = connection.execute(
                """
                SELECT stream_event_identity, payload_json, payload_sha256
                FROM stream_source_events
                WHERE stream_event_identity = ?
                   OR source_event_identity = ?
                LIMIT 1
                """,
                (event.stream_event_identity, event.source_event_identity),
            ).fetchone()

            present = (existing_context is not None, existing_event is not None)
            if any(present):
                if not all(present):
                    raise StreamLedgerConflictError(
                        "partial immutable Stream issuance bundle already exists"
                    )
                assert existing_context is not None
                assert existing_event is not None
                exact = (
                    str(existing_context[0]) == context.context_identity
                    and str(existing_context[1]) == context_json
                    and str(existing_context[2]) == context_digest
                    and str(existing_event[0]) == event.stream_event_identity
                    and str(existing_event[1]) == event_json
                    and str(existing_event[2]) == event_digest
                )
                if exact:
                    return StreamLedgerWriteDisposition.UNCHANGED
                raise StreamLedgerConflictError(
                    "immutable Stream issuance identity conflict"
                )

            last_event = connection.execute(
                """
                SELECT event_at_ms, stream_event_identity
                FROM stream_source_events
                ORDER BY event_at_ms DESC, stream_event_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last_event is not None and (
                event.event_at_ms,
                event.stream_event_identity,
            ) <= (int(last_event[0]), str(last_event[1])):
                raise StreamLedgerConflictError(
                    "Stream source-event append would backfill or fork chronology"
                )

            connection.execute(
                """
                INSERT INTO stream_decision_contexts (
                    context_identity,
                    forecast_identity,
                    proof_identity,
                    confluence_identity,
                    issued_at_ms,
                    source_as_of_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.context_identity,
                    context.forecast_identity,
                    context.proof_identity,
                    context.confluence_identity,
                    context.issued_at_ms,
                    context.source_as_of_ms,
                    context_json,
                    context_digest,
                ),
            )
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.stream_event_identity,
                    event.source_event_identity,
                    event.activation_identity,
                    event.decision_context_identity,
                    event.category.value,
                    event.subtype,
                    event.event_at_ms,
                    event.source_as_of_ms,
                    event_json,
                    event_digest,
                ),
            )
            connection.commit()
        return StreamLedgerWriteDisposition.INSERTED

    def read_status(self) -> StreamLedgerStatus:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            activation = self._activation_row(connection)
            context_count = self._table_count(
                connection,
                "stream_decision_contexts",
            )
            event_count = self._table_count(connection, "stream_source_events")
            latest = connection.execute(
                "SELECT MAX(event_at_ms) FROM stream_source_events"
            ).fetchone()
        latest_event = None if latest is None or latest[0] is None else int(latest[0])
        return StreamLedgerStatus(
            activation_identity=str(activation[0]),
            activated_at_ms=int(activation[1]),
            decision_context_count=context_count,
            source_event_count=event_count,
            latest_event_at_ms=latest_event,
        )

    def read_activation(self) -> dict[str, Any]:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = self._activation_row(connection)
        return self._verified_record(
            payload_json=str(row[2]),
            expected_digest=str(row[3]),
            identity_key="activation_identity",
            expected_identity=str(row[0]),
            expected_schema=STREAM_ACTIVATION_SCHEMA_VERSION,
        )

    def read_context_for_forecast(
        self,
        forecast_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(forecast_identity, "Stream forecast lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT context_identity, payload_json, payload_sha256
                FROM stream_decision_contexts
                WHERE forecast_identity = ?
                """,
                (forecast_identity,),
            ).fetchone()
        if row is None:
            return None
        raw = self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            identity_key="context_identity",
            expected_identity=str(row[0]),
            expected_schema=STREAM_DECISION_CONTEXT_SCHEMA_VERSION,
        )
        self._verify_confluence_payload(raw)
        return raw

    def read_events(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("Stream event limit must be inside 1..1000")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT stream_event_identity, payload_json, payload_sha256
                FROM stream_source_events
                ORDER BY event_at_ms DESC, stream_event_identity DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            self._verified_record(
                payload_json=str(row[1]),
                expected_digest=str(row[2]),
                identity_key="stream_event_identity",
                expected_identity=str(row[0]),
                expected_schema=STREAM_SOURCE_EVENT_SCHEMA_VERSION,
            )
            for row in rows
        )

    def _connect_ro(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        uri = f"file:{quote(str(self.path.resolve()), safe='/')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _activation_row(connection: sqlite3.Connection) -> tuple[object, ...]:
        rows = connection.execute(
            """
            SELECT activation_identity, activated_at_ms, payload_json, payload_sha256
            FROM stream_activation
            ORDER BY activated_at_ms, activation_identity
            """
        ).fetchall()
        if len(rows) != 1:
            raise StreamLedgerConflictError(
                "Stream ledger requires exactly one activation boundary"
            )
        return rows[0]

    @staticmethod
    def _table_count(connection: sqlite3.Connection, table: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row is None:
            raise StreamLedgerConflictError(f"Stream count failed for {table}")
        return int(row[0])

    @staticmethod
    def _require_schema(connection: sqlite3.Connection) -> None:
        for table in (
            "stream_meta",
            "stream_activation",
            "stream_decision_contexts",
            "stream_source_events",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise StreamLedgerConflictError(
                    f"Stream ledger missing table: {table}"
                )

    @staticmethod
    def _verify_meta(connection: sqlite3.Connection) -> None:
        expected = {
            "engine_version": STREAM_ENGINE_VERSION,
            "real_capital": str(REAL_CAPITAL),
            "schema_version": STREAM_LEDGER_SCHEMA_VERSION,
        }
        rows = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT key, value FROM stream_meta"
            ).fetchall()
        }
        if rows != expected:
            raise StreamLedgerConflictError("Stream ledger metadata mismatch")

    @staticmethod
    def _verified_record(
        *,
        payload_json: str,
        expected_digest: str,
        identity_key: str,
        expected_identity: str,
        expected_schema: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamLedgerConflictError("Stream persisted payload digest mismatch")
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamLedgerConflictError("Stream payload must decode to object")
        if raw.get(identity_key) != expected_identity:
            raise StreamLedgerConflictError("Stream persisted identity column mismatch")
        identity_payload = dict(raw)
        identity_payload.pop(identity_key, None)
        if canonical_sha256(identity_payload) != expected_identity:
            raise StreamLedgerConflictError("Stream persisted identity mismatch")
        if raw.get("schema_version") != expected_schema:
            raise StreamLedgerConflictError("Stream persisted schema mismatch")
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamLedgerConflictError("Stream persisted engine mismatch")
        if raw.get("read_only") is not True:
            raise StreamLedgerConflictError("Stream persisted read-only boundary mismatch")
        if raw.get("production_authority") is not False:
            raise StreamLedgerConflictError(
                "Stream persisted production authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamLedgerConflictError(
                "Stream persisted REAL_CAPITAL boundary mismatch"
            )
        return raw

    @staticmethod
    def _verify_confluence_payload(context: dict[str, Any]) -> None:
        raw_confluence = context.get("confluence")
        expected_identity = context.get("confluence_identity")
        if not isinstance(raw_confluence, dict) or not isinstance(
            expected_identity,
            str,
        ):
            raise StreamLedgerConflictError(
                "Stream context missing embedded M6 snapshot"
            )
        if raw_confluence.get("snapshot_identity") != expected_identity:
            raise StreamLedgerConflictError(
                "Stream embedded M6 identity column mismatch"
            )
        payload = dict(raw_confluence)
        payload.pop("snapshot_identity", None)
        if canonical_sha256(payload) != expected_identity:
            raise StreamLedgerConflictError(
                "Stream embedded M6 snapshot identity mismatch"
            )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
