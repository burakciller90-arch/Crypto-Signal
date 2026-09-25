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
from crypto_signal.product.intelligence_stream_analytical import (
    STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
    StreamAnalyticalView,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_story_ledger import (
    IntelligenceStreamStoryLedger,
)

STREAM_ANALYTICAL_LEDGER_SCHEMA_VERSION = "intelligence-stream-analytical-ledger-v1/2"


class StreamAnalyticalLedgerConflictError(ValueError):
    """Raised when immutable analytical history would fork or rewrite."""


class StreamAnalyticalLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamAnalyticalLedgerStatus:
    analytical_view_count: int
    story_count: int
    latest_event_at_ms: int | None
    schema_version: str = STREAM_ANALYTICAL_LEDGER_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamAnalyticalLedger:
    """Append-only persistence for deterministic S4 Analytical Views."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamStoryLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_analytical_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_analytical_views (
                    analytical_view_identity TEXT PRIMARY KEY,
                    policy_identity TEXT NOT NULL,
                    fact_bundle_identity TEXT NOT NULL UNIQUE,
                    change_set_identity TEXT NOT NULL UNIQUE,
                    current_state_identity TEXT NOT NULL UNIQUE,
                    source_message_identity TEXT UNIQUE,
                    story_identity TEXT NOT NULL,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (fact_bundle_identity)
                        REFERENCES stream_fact_bundles(fact_bundle_identity),
                    FOREIGN KEY (change_set_identity)
                        REFERENCES stream_story_change_sets(change_set_identity),
                    FOREIGN KEY (current_state_identity)
                        REFERENCES stream_story_states(state_identity),
                    FOREIGN KEY (source_message_identity)
                        REFERENCES stream_message_inputs(message_identity),
                    FOREIGN KEY (stream_event_identity)
                        REFERENCES stream_source_events(stream_event_identity)
                );

                CREATE INDEX IF NOT EXISTS stream_analytical_views_story
                ON stream_analytical_views(
                    story_identity,
                    event_at_ms,
                    analytical_view_identity
                );
                """
            )
            expected_meta = {
                "engine_version": STREAM_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_ANALYTICAL_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected_meta.items():
                row = connection.execute(
                    "SELECT value FROM stream_analytical_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_analytical_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise StreamAnalyticalLedgerConflictError(
                        f"Stream analytical ledger metadata mismatch for {key}"
                    )

            for table in (
                "stream_analytical_meta",
                "stream_analytical_views",
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
                                'immutable intelligence stream analytical ledger'
                            );
                        END
                        """
                    )

    def append_view(
        self,
        view: StreamAnalyticalView,
    ) -> StreamAnalyticalLedgerWriteDisposition:
        self.initialize()
        payload_json = canonical_json(view)
        payload_digest = sha256_text(payload_json)

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)

            fact_row = connection.execute(
                """
                SELECT story_identity, source_event_identity, stream_event_identity,
                       event_at_ms
                FROM stream_fact_bundles
                WHERE fact_bundle_identity = ?
                """,
                (view.fact_bundle_identity,),
            ).fetchone()
            if fact_row is None:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view references unknown fact bundle"
                )
            if str(fact_row[0]) != view.story_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/fact story mismatch"
                )
            if str(fact_row[1]) != view.source_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/fact source-event mismatch"
                )
            if str(fact_row[2]) != view.stream_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/fact stream-event mismatch"
                )
            if int(str(fact_row[3])) != view.event_at_ms:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/fact event-time mismatch"
                )

            state_row = connection.execute(
                """
                SELECT story_identity, source_event_identity,
                       current_stream_event_identity, current_message_identity,
                       event_at_ms
                FROM stream_story_states
                WHERE state_identity = ?
                """,
                (view.current_state_identity,),
            ).fetchone()
            if state_row is None:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view references unknown story state"
                )
            if str(state_row[0]) != view.story_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state story mismatch"
                )
            if str(state_row[1]) != view.source_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state source-event mismatch"
                )
            if str(state_row[2]) != view.stream_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state stream-event mismatch"
                )
            state_message_identity = (
                None if state_row[3] is None else str(state_row[3])
            )
            if state_message_identity != view.source_message_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state message mismatch"
                )
            if int(str(state_row[4])) != view.event_at_ms:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state event-time mismatch"
                )

            change_row = connection.execute(
                """
                SELECT story_identity, current_state_identity
                FROM stream_story_change_sets
                WHERE change_set_identity = ?
                """,
                (view.change_set_identity,),
            ).fetchone()
            if change_row is None:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view references unknown change set"
                )
            if str(change_row[0]) != view.story_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/change-set story mismatch"
                )
            if str(change_row[1]) != view.current_state_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/change-set state mismatch"
                )

            if view.source_message_identity is not None:
                state_row = connection.execute(
                """
                SELECT story_identity, source_event_identity,
                       current_stream_event_identity, current_message_identity,
                       event_at_ms
                FROM stream_story_states
                WHERE state_identity = ?
                """,
                (view.current_state_identity,),
            ).fetchone()
            if state_row is None:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view references unknown story state"
                )
            if str(state_row[0]) != view.story_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state story mismatch"
                )
            if str(state_row[1]) != view.source_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state source-event mismatch"
                )
            if str(state_row[2]) != view.stream_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state stream-event mismatch"
                )
            state_message = (
                None if state_row[3] is None else str(state_row[3])
            )
            if state_message != view.source_message_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state message mismatch"
                )
            if int(str(state_row[4])) != view.event_at_ms:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/state event-time mismatch"
                )

            change_row = connection.execute(
                """
                SELECT story_identity, current_state_identity
                FROM stream_story_change_sets
                WHERE change_set_identity = ?
                """,
                (view.change_set_identity,),
            ).fetchone()
            if change_row is None:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view references unknown change set"
                )
            if str(change_row[0]) != view.story_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/change-set story mismatch"
                )
            if str(change_row[1]) != view.current_state_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/change-set state mismatch"
                )

            source_row = connection.execute(
                """
                SELECT source_event_identity, event_at_ms
                FROM stream_source_events
                WHERE stream_event_identity = ?
                """,
                (view.stream_event_identity,),
            ).fetchone()
            if source_row is None:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view references unknown source event"
                )
            if str(source_row[0]) != view.source_event_identity:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/source-event mismatch"
                )
            if int(str(source_row[1])) != view.event_at_ms:
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical view/source-event time mismatch"
                )

            if view.source_message_identity is not None:
                message_row = connection.execute(
                    """
                    SELECT story_identity, fact_bundle_identity,
                           stream_event_identity, source_event_identity,
                           event_at_ms
                    FROM stream_message_inputs
                    WHERE message_identity = ?
                    """,
                    (view.source_message_identity,),
                ).fetchone()
                if message_row is None:
                    raise StreamAnalyticalLedgerConflictError(
                        "Stream analytical view references unknown source message"
                    )
                if str(message_row[0]) != view.story_identity:
                    raise StreamAnalyticalLedgerConflictError(
                        "Stream analytical view/message story mismatch"
                    )
                if str(message_row[1]) != view.fact_bundle_identity:
                    raise StreamAnalyticalLedgerConflictError(
                        "Stream analytical view/message fact mismatch"
                    )
                if str(message_row[2]) != view.stream_event_identity:
                    raise StreamAnalyticalLedgerConflictError(
                        "Stream analytical view/message stream-event mismatch"
                    )
                if str(message_row[3]) != view.source_event_identity:
                    raise StreamAnalyticalLedgerConflictError(
                        "Stream analytical view/message source-event mismatch"
                    )
                if int(str(message_row[4])) != view.event_at_ms:
                    raise StreamAnalyticalLedgerConflictError(
                        "Stream analytical view/message event-time mismatch"
                    )

            existing = connection.execute(
                """
                SELECT analytical_view_identity, payload_json, payload_sha256
                FROM stream_analytical_views
                WHERE analytical_view_identity = ?
                   OR fact_bundle_identity = ?
                   OR change_set_identity = ?
                   OR current_state_identity = ?
                   OR (? IS NOT NULL AND source_message_identity = ?)
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                LIMIT 1
                """,
                (
                    view.analytical_view_identity,
                    view.fact_bundle_identity,
                    view.change_set_identity,
                    view.current_state_identity,
                    view.source_message_identity,
                    view.source_message_identity,
                    view.source_event_identity,
                    view.stream_event_identity,
                ),
            ).fetchone()
            if existing is not None:
                exact = (
                    str(existing[0]) == view.analytical_view_identity
                    and str(existing[1]) == payload_json
                    and str(existing[2]) == payload_digest
                )
                if exact:
                    return StreamAnalyticalLedgerWriteDisposition.UNCHANGED
                raise StreamAnalyticalLedgerConflictError(
                    "immutable Stream analytical view conflict"
                )

            latest = connection.execute(
                """
                SELECT event_at_ms, analytical_view_identity
                FROM stream_analytical_views
                ORDER BY event_at_ms DESC, analytical_view_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if latest is not None and (
                view.event_at_ms,
                view.analytical_view_identity,
            ) <= (int(str(latest[0])), str(latest[1])):
                raise StreamAnalyticalLedgerConflictError(
                    "Stream analytical append would backfill or fork chronology"
                )

            connection.execute(
                """
                INSERT INTO stream_analytical_views (
                    analytical_view_identity,
                    policy_identity,
                    fact_bundle_identity,
                    change_set_identity,
                    current_state_identity,
                    source_message_identity,
                    story_identity,
                    source_event_identity,
                    stream_event_identity,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    view.analytical_view_identity,
                    view.policy_identity,
                    view.fact_bundle_identity,
                    view.change_set_identity,
                    view.current_state_identity,
                    view.source_message_identity,
                    view.story_identity,
                    view.source_event_identity,
                    view.stream_event_identity,
                    view.event_at_ms,
                    payload_json,
                    payload_digest,
                ),
            )
            connection.commit()
        return StreamAnalyticalLedgerWriteDisposition.INSERTED

    def read_status(self) -> StreamAnalyticalLedgerStatus:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            count_row = connection.execute(
                "SELECT COUNT(*) FROM stream_analytical_views"
            ).fetchone()
            story_row = connection.execute(
                "SELECT COUNT(DISTINCT story_identity) FROM stream_analytical_views"
            ).fetchone()
            latest_row = connection.execute(
                "SELECT MAX(event_at_ms) FROM stream_analytical_views"
            ).fetchone()
        return StreamAnalyticalLedgerStatus(
            analytical_view_count=(
                0 if count_row is None else int(str(count_row[0]))
            ),
            story_count=0 if story_row is None else int(str(story_row[0])),
            latest_event_at_ms=(
                None
                if latest_row is None or latest_row[0] is None
                else int(str(latest_row[0]))
            ),
        )

    def read_for_message(
        self,
        message_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(message_identity, "Stream analytical message lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT analytical_view_identity, payload_json, payload_sha256
                FROM stream_analytical_views
                WHERE source_message_identity = ?
                """,
                (message_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            expected_identity=str(row[0]),
        )

    def read_for_state(
        self,
        state_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(state_identity, "Stream analytical state lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT analytical_view_identity, payload_json, payload_sha256
                FROM stream_analytical_views
                WHERE current_state_identity = ?
                """,
                (state_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            expected_identity=str(row[0]),
        )

    def read_story(
        self,
        story_identity: str,
        *,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        _require_sha256(story_identity, "Stream analytical story lookup")
        if limit < 1 or limit > 1000:
            raise ValueError("Stream analytical story limit must be inside 1..1000")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT analytical_view_identity, payload_json, payload_sha256
                FROM stream_analytical_views
                WHERE story_identity = ?
                ORDER BY event_at_ms, analytical_view_identity
                LIMIT ?
                """,
                (story_identity, limit),
            ).fetchall()
        return tuple(
            self._verified_record(
                payload_json=str(row[1]),
                expected_digest=str(row[2]),
                expected_identity=str(row[0]),
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
            "stream_fact_bundles",
            "stream_message_inputs",
            "stream_story_states",
            "stream_story_change_sets",
            "stream_analytical_meta",
            "stream_analytical_views",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise StreamAnalyticalLedgerConflictError(
                    f"Stream analytical ledger missing table: {table}"
                )

    @staticmethod
    def _verify_meta(connection: sqlite3.Connection) -> None:
        expected = {
            "engine_version": STREAM_ENGINE_VERSION,
            "real_capital": str(REAL_CAPITAL),
            "schema_version": STREAM_ANALYTICAL_LEDGER_SCHEMA_VERSION,
        }
        rows = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT key, value FROM stream_analytical_meta"
            ).fetchall()
        }
        if rows != expected:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical ledger metadata mismatch"
            )

    @staticmethod
    def _verified_record(
        *,
        payload_json: str,
        expected_digest: str,
        expected_identity: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical payload must decode to object"
            )
        if raw.get("analytical_view_identity") != expected_identity:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted identity column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop("analytical_view_identity", None)
        if canonical_sha256(identity_payload) != expected_identity:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted identity mismatch"
            )
        if raw.get("schema_version") != STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted schema mismatch"
            )
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted engine mismatch"
            )
        if raw.get("read_only") is not True:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted read-only mismatch"
            )
        if raw.get("production_authority") is not False:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted production authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamAnalyticalLedgerConflictError(
                "Stream analytical persisted REAL_CAPITAL mismatch"
            )
        return raw


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
