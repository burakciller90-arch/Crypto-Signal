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
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
)
from crypto_signal.product.intelligence_stream_messages import (
    STREAM_FACT_BUNDLE_SCHEMA_VERSION,
    STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
    STREAM_PUBLISHED_MESSAGE_SCHEMA_VERSION,
    StreamFactBundle,
    StreamMessageInput,
    StreamPublishedMessage,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)

STREAM_MESSAGE_LEDGER_SCHEMA_VERSION = "intelligence-stream-message-ledger-v1/2"


class StreamMessageLedgerConflictError(ValueError):
    """Raised when canonical Stream message projection would fork or rewrite history."""


class StreamMessageLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamMessageLedgerStatus:
    fact_bundle_count: int
    message_input_count: int
    published_message_count: int
    story_count: int
    latest_event_at_ms: int | None
    schema_version: str = STREAM_MESSAGE_LEDGER_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamMessageLedger:
    """Append-only canonical Stream message-input projection.

    The ledger stores facts and deterministic message inputs only. It does not
    claim analytical/narrative/rendered publication stages that are not built yet.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_message_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_fact_bundles (
                    fact_bundle_identity TEXT PRIMARY KEY,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (stream_event_identity)
                        REFERENCES stream_source_events(stream_event_identity)
                );

                CREATE TABLE IF NOT EXISTS stream_message_inputs (
                    message_identity TEXT PRIMARY KEY,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    fact_bundle_identity TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    subtype TEXT NOT NULL,
                    importance TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (stream_event_identity)
                        REFERENCES stream_source_events(stream_event_identity),
                    FOREIGN KEY (fact_bundle_identity)
                        REFERENCES stream_fact_bundles(fact_bundle_identity)
                );

                CREATE TABLE IF NOT EXISTS stream_published_messages (
                    publication_identity TEXT PRIMARY KEY,
                    message_identity TEXT NOT NULL UNIQUE,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    fact_bundle_identity TEXT NOT NULL,
                    published_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (message_identity)
                        REFERENCES stream_message_inputs(message_identity),
                    FOREIGN KEY (fact_bundle_identity)
                        REFERENCES stream_fact_bundles(fact_bundle_identity)
                );

                CREATE INDEX IF NOT EXISTS stream_message_inputs_chrono
                ON stream_message_inputs(event_at_ms, stream_event_identity);

                CREATE INDEX IF NOT EXISTS stream_message_inputs_story
                ON stream_message_inputs(story_identity, event_at_ms, stream_event_identity);

                CREATE INDEX IF NOT EXISTS stream_fact_bundles_story
                ON stream_fact_bundles(story_identity, event_at_ms, stream_event_identity);

                CREATE INDEX IF NOT EXISTS stream_published_messages_story
                ON stream_published_messages(story_identity, published_at_ms, publication_identity);
                """
            )
            expected_meta = {
                "engine_version": STREAM_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_MESSAGE_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected_meta.items():
                row = connection.execute(
                    "SELECT value FROM stream_message_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_message_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise StreamMessageLedgerConflictError(
                        f"Stream message ledger metadata mismatch for {key}"
                    )

            for table in (
                "stream_message_meta",
                "stream_fact_bundles",
                "stream_message_inputs",
                "stream_published_messages",
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
                                'immutable intelligence stream message ledger'
                            );
                        END
                        """
                    )

    def append_message_bundle(
        self,
        fact_bundle: StreamFactBundle,
        message: StreamMessageInput,
    ) -> StreamMessageLedgerWriteDisposition:
        if message.fact_bundle_identity != fact_bundle.fact_bundle_identity:
            raise StreamMessageLedgerConflictError(
                "Stream message/fact bundle identity mismatch"
            )
        if message.stream_event_identity != fact_bundle.stream_event_identity:
            raise StreamMessageLedgerConflictError(
                "Stream message/fact normalized-event mismatch"
            )
        if message.source_event_identity != fact_bundle.source_event_identity:
            raise StreamMessageLedgerConflictError(
                "Stream message/fact source-event mismatch"
            )
        if message.story_identity != fact_bundle.story_identity:
            raise StreamMessageLedgerConflictError(
                "Stream message/fact story mismatch"
            )
        if message.event_at_ms != fact_bundle.event_at_ms:
            raise StreamMessageLedgerConflictError(
                "Stream message/fact event-time mismatch"
            )

        self.initialize()
        fact_json = canonical_json(fact_bundle)
        fact_digest = sha256_text(fact_json)
        message_json = canonical_json(message)
        message_digest = sha256_text(message_json)

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)

            source_row = connection.execute(
                """
                SELECT source_event_identity, category, subtype, event_at_ms
                FROM stream_source_events
                WHERE stream_event_identity = ?
                """,
                (message.stream_event_identity,),
            ).fetchone()
            if source_row is None:
                raise StreamMessageLedgerConflictError(
                    "Stream message references unknown source event"
                )
            if str(source_row[0]) != message.source_event_identity:
                raise StreamMessageLedgerConflictError(
                    "Stream message source-event column mismatch"
                )
            if str(source_row[1]) != message.category.value:
                raise StreamMessageLedgerConflictError(
                    "Stream message/source category mismatch"
                )
            if str(source_row[2]) != message.subtype:
                raise StreamMessageLedgerConflictError(
                    "Stream message/source subtype mismatch"
                )
            if int(str(source_row[3])) != message.event_at_ms:
                raise StreamMessageLedgerConflictError(
                    "Stream message/source event-time mismatch"
                )

            context_row = connection.execute(
                """
                SELECT 1 FROM stream_decision_contexts
                WHERE context_identity = ?
                """,
                (fact_bundle.decision_context_identity,),
            ).fetchone()
            if context_row is None:
                raise StreamMessageLedgerConflictError(
                    "Stream fact bundle references unknown decision context"
                )

            existing_fact = connection.execute(
                """
                SELECT fact_bundle_identity, payload_json, payload_sha256
                FROM stream_fact_bundles
                WHERE fact_bundle_identity = ?
                   OR stream_event_identity = ?
                   OR source_event_identity = ?
                LIMIT 1
                """,
                (
                    fact_bundle.fact_bundle_identity,
                    fact_bundle.stream_event_identity,
                    fact_bundle.source_event_identity,
                ),
            ).fetchone()
            existing_message = connection.execute(
                """
                SELECT message_identity, payload_json, payload_sha256
                FROM stream_message_inputs
                WHERE message_identity = ?
                   OR stream_event_identity = ?
                   OR source_event_identity = ?
                LIMIT 1
                """,
                (
                    message.message_identity,
                    message.stream_event_identity,
                    message.source_event_identity,
                ),
            ).fetchone()

            present = (existing_fact is not None, existing_message is not None)
            if any(present):
                if not all(present):
                    raise StreamMessageLedgerConflictError(
                        "partial immutable Stream message bundle already exists"
                    )
                assert existing_fact is not None
                assert existing_message is not None
                exact = (
                    str(existing_fact[0]) == fact_bundle.fact_bundle_identity
                    and str(existing_fact[1]) == fact_json
                    and str(existing_fact[2]) == fact_digest
                    and str(existing_message[0]) == message.message_identity
                    and str(existing_message[1]) == message_json
                    and str(existing_message[2]) == message_digest
                )
                if exact:
                    return StreamMessageLedgerWriteDisposition.UNCHANGED
                raise StreamMessageLedgerConflictError(
                    "immutable Stream message projection conflict"
                )

            last_message = connection.execute(
                """
                SELECT event_at_ms, stream_event_identity
                FROM stream_message_inputs
                ORDER BY event_at_ms DESC, stream_event_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last_message is not None and (
                message.event_at_ms,
                message.stream_event_identity,
            ) <= (int(str(last_message[0])), str(last_message[1])):
                raise StreamMessageLedgerConflictError(
                    "Stream message append would backfill or fork chronology"
                )

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
                    fact_bundle.fact_bundle_identity,
                    fact_bundle.stream_event_identity,
                    fact_bundle.source_event_identity,
                    fact_bundle.story_identity,
                    fact_bundle.event_at_ms,
                    fact_json,
                    fact_digest,
                ),
            )
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
                    message_digest,
                ),
            )
            connection.commit()
        return StreamMessageLedgerWriteDisposition.INSERTED

    def append_published_message(
        self,
        publication: StreamPublishedMessage,
    ) -> StreamMessageLedgerWriteDisposition:
        self.initialize()
        payload_json = canonical_json(publication)
        payload_digest = sha256_text(payload_json)

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)

            message_row = connection.execute(
                """
                SELECT source_event_identity, story_identity, fact_bundle_identity
                FROM stream_message_inputs
                WHERE message_identity = ?
                """,
                (publication.message_identity,),
            ).fetchone()
            if message_row is None:
                raise StreamMessageLedgerConflictError(
                    "Stream publication references unknown message input"
                )
            if str(message_row[0]) != publication.source_event_identity:
                raise StreamMessageLedgerConflictError(
                    "Stream publication/message source-event mismatch"
                )
            if str(message_row[1]) != publication.story_identity:
                raise StreamMessageLedgerConflictError(
                    "Stream publication/message story mismatch"
                )
            if str(message_row[2]) != publication.fact_bundle_identity:
                raise StreamMessageLedgerConflictError(
                    "Stream publication/message fact-bundle mismatch"
                )

            existing = connection.execute(
                """
                SELECT publication_identity, payload_json, payload_sha256
                FROM stream_published_messages
                WHERE publication_identity = ?
                   OR message_identity = ?
                   OR source_event_identity = ?
                LIMIT 1
                """,
                (
                    publication.publication_identity,
                    publication.message_identity,
                    publication.source_event_identity,
                ),
            ).fetchone()
            if existing is not None:
                exact = (
                    str(existing[0]) == publication.publication_identity
                    and str(existing[1]) == payload_json
                    and str(existing[2]) == payload_digest
                )
                if exact:
                    return StreamMessageLedgerWriteDisposition.UNCHANGED
                raise StreamMessageLedgerConflictError(
                    "immutable Stream publication conflict"
                )

            last_row = connection.execute(
                """
                SELECT published_at_ms, publication_identity
                FROM stream_published_messages
                ORDER BY published_at_ms DESC, publication_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if last_row is not None and (
                publication.published_at_ms,
                publication.publication_identity,
            ) <= (int(str(last_row[0])), str(last_row[1])):
                raise StreamMessageLedgerConflictError(
                    "Stream publication append would backfill or fork chronology"
                )

            connection.execute(
                """
                INSERT INTO stream_published_messages (
                    publication_identity,
                    message_identity,
                    source_event_identity,
                    story_identity,
                    fact_bundle_identity,
                    published_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    publication.publication_identity,
                    publication.message_identity,
                    publication.source_event_identity,
                    publication.story_identity,
                    publication.fact_bundle_identity,
                    publication.published_at_ms,
                    payload_json,
                    payload_digest,
                ),
            )
            connection.commit()
        return StreamMessageLedgerWriteDisposition.INSERTED

    def read_status(self) -> StreamMessageLedgerStatus:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            fact_count = self._table_count(connection, "stream_fact_bundles")
            message_count = self._table_count(connection, "stream_message_inputs")
            published_count = self._table_count(
                connection,
                "stream_published_messages",
            )
            story_row = connection.execute(
                "SELECT COUNT(DISTINCT story_identity) FROM stream_message_inputs"
            ).fetchone()
            latest_row = connection.execute(
                "SELECT MAX(event_at_ms) FROM stream_message_inputs"
            ).fetchone()
        story_count = 0 if story_row is None else int(str(story_row[0]))
        latest = (
            None
            if latest_row is None or latest_row[0] is None
            else int(str(latest_row[0]))
        )
        return StreamMessageLedgerStatus(
            fact_bundle_count=fact_count,
            message_input_count=message_count,
            published_message_count=published_count,
            story_count=story_count,
            latest_event_at_ms=latest,
        )

    def read_message_for_source_event(
        self,
        source_event_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(source_event_identity, "Stream message source-event lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT message_identity, payload_json, payload_sha256
                FROM stream_message_inputs
                WHERE source_event_identity = ?
                """,
                (source_event_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            identity_key="message_identity",
            expected_identity=str(row[0]),
            expected_schema=STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
        )

    def read_published_message(
        self,
        message_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(message_identity, "Stream publication message lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT publication_identity, payload_json, payload_sha256
                FROM stream_published_messages
                WHERE message_identity = ?
                """,
                (message_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            identity_key="publication_identity",
            expected_identity=str(row[0]),
            expected_schema=STREAM_PUBLISHED_MESSAGE_SCHEMA_VERSION,
        )

    def read_fact_bundle(
        self,
        fact_bundle_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(fact_bundle_identity, "Stream fact-bundle lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM stream_fact_bundles
                WHERE fact_bundle_identity = ?
                """,
                (fact_bundle_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[0]),
            expected_digest=str(row[1]),
            identity_key="fact_bundle_identity",
            expected_identity=fact_bundle_identity,
            expected_schema=STREAM_FACT_BUNDLE_SCHEMA_VERSION,
        )

    def read_story(
        self,
        story_identity: str,
        *,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        _require_sha256(story_identity, "Stream story lookup")
        if limit < 1 or limit > 1000:
            raise ValueError("Stream story limit must be inside 1..1000")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT message_identity, payload_json, payload_sha256
                FROM stream_message_inputs
                WHERE story_identity = ?
                ORDER BY event_at_ms, stream_event_identity
                LIMIT ?
                """,
                (story_identity, limit),
            ).fetchall()
        return tuple(
            self._verified_record(
                payload_json=str(row[1]),
                expected_digest=str(row[2]),
                identity_key="message_identity",
                expected_identity=str(row[0]),
                expected_schema=STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
            )
            for row in rows
        )

    def read_messages(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("Stream message limit must be inside 1..1000")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT message_identity, payload_json, payload_sha256
                FROM stream_message_inputs
                ORDER BY event_at_ms DESC, stream_event_identity DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            self._verified_record(
                payload_json=str(row[1]),
                expected_digest=str(row[2]),
                identity_key="message_identity",
                expected_identity=str(row[0]),
                expected_schema=STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
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
    def _require_schema(connection: sqlite3.Connection) -> None:
        for table in (
            "stream_source_events",
            "stream_decision_contexts",
            "stream_message_meta",
            "stream_fact_bundles",
            "stream_message_inputs",
            "stream_published_messages",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise StreamMessageLedgerConflictError(
                    f"Stream message ledger missing table: {table}"
                )

    @staticmethod
    def _verify_meta(connection: sqlite3.Connection) -> None:
        expected = {
            "engine_version": STREAM_ENGINE_VERSION,
            "real_capital": str(REAL_CAPITAL),
            "schema_version": STREAM_MESSAGE_LEDGER_SCHEMA_VERSION,
        }
        rows = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT key, value FROM stream_message_meta"
            ).fetchall()
        }
        if rows != expected:
            raise StreamMessageLedgerConflictError(
                "Stream message ledger metadata mismatch"
            )

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
            raise StreamMessageLedgerConflictError(
                "Stream message persisted payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamMessageLedgerConflictError(
                "Stream message payload must decode to object"
            )
        if raw.get(identity_key) != expected_identity:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted identity column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop(identity_key, None)
        if canonical_sha256(identity_payload) != expected_identity:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted identity mismatch"
            )
        if raw.get("schema_version") != expected_schema:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted schema mismatch"
            )
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted engine mismatch"
            )
        if raw.get("read_only") is not True:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted read-only mismatch"
            )
        if raw.get("production_authority") is not False:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted production authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamMessageLedgerConflictError(
                "Stream message persisted REAL_CAPITAL mismatch"
            )
        return raw

    @staticmethod
    def _table_count(connection: sqlite3.Connection, table: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row is None:
            raise StreamMessageLedgerConflictError(
                f"Stream message count failed for {table}"
            )
        return int(str(row[0]))


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
