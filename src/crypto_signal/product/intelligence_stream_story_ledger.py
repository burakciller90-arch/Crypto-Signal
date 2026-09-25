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
from crypto_signal.product.intelligence_stream_message_ledger import (
    IntelligenceStreamMessageLedger,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_story import (
    STREAM_CHANGE_SET_SCHEMA_VERSION,
    STREAM_STORY_OBSERVATION_SCHEMA_VERSION,
    STREAM_STORY_STATE_SCHEMA_VERSION,
    StreamChangeSet,
    StreamStoryObservation,
    StreamStoryState,
)

STREAM_STORY_LEDGER_SCHEMA_VERSION = "intelligence-stream-story-ledger-v1/1"


class StreamStoryLedgerConflictError(ValueError):
    """Raised when immutable story continuity would fork or rewrite history."""


class StreamStoryLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamStoryLedgerStatus:
    observation_count: int
    state_count: int
    change_set_count: int
    story_count: int
    schema_version: str = STREAM_STORY_LEDGER_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamStoryLedger:
    """Append-only story memory over canonical Stream source/message truth."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamMessageLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_story_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_story_observations (
                    observation_identity TEXT PRIMARY KEY,
                    story_identity TEXT NOT NULL,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    message_identity TEXT UNIQUE,
                    previous_state_identity TEXT,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (stream_event_identity)
                        REFERENCES stream_source_events(stream_event_identity),
                    FOREIGN KEY (message_identity)
                        REFERENCES stream_message_inputs(message_identity)
                );

                CREATE TABLE IF NOT EXISTS stream_story_states (
                    state_identity TEXT PRIMARY KEY,
                    story_identity TEXT NOT NULL,
                    observation_identity TEXT NOT NULL UNIQUE,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    current_stream_event_identity TEXT NOT NULL UNIQUE,
                    current_message_identity TEXT UNIQUE,
                    previous_state_identity TEXT,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (observation_identity)
                        REFERENCES stream_story_observations(observation_identity),
                    FOREIGN KEY (previous_state_identity)
                        REFERENCES stream_story_states(state_identity),
                    FOREIGN KEY (current_message_identity)
                        REFERENCES stream_message_inputs(message_identity)
                );

                CREATE TABLE IF NOT EXISTS stream_story_change_sets (
                    change_set_identity TEXT PRIMARY KEY,
                    story_identity TEXT NOT NULL,
                    current_state_identity TEXT NOT NULL UNIQUE,
                    previous_state_identity TEXT,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (current_state_identity)
                        REFERENCES stream_story_states(state_identity),
                    FOREIGN KEY (previous_state_identity)
                        REFERENCES stream_story_states(state_identity)
                );

                CREATE INDEX IF NOT EXISTS stream_story_states_story
                ON stream_story_states(story_identity, event_at_ms, state_identity);

                CREATE INDEX IF NOT EXISTS stream_story_observations_story
                ON stream_story_observations(
                    story_identity,
                    event_at_ms,
                    observation_identity
                );
                """
            )
            expected_meta = {
                "engine_version": STREAM_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_STORY_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected_meta.items():
                row = connection.execute(
                    "SELECT value FROM stream_story_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_story_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise StreamStoryLedgerConflictError(
                        f"Stream story ledger metadata mismatch for {key}"
                    )

            for table in (
                "stream_story_meta",
                "stream_story_observations",
                "stream_story_states",
                "stream_story_change_sets",
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
                                'immutable intelligence stream story ledger'
                            );
                        END
                        """
                    )

    def append_transition(
        self,
        observation: StreamStoryObservation,
        state: StreamStoryState,
        change_set: StreamChangeSet,
    ) -> StreamStoryLedgerWriteDisposition:
        self._validate_bundle(observation, state, change_set)
        self.initialize()

        observation_json = canonical_json(observation)
        observation_digest = sha256_text(observation_json)
        state_json = canonical_json(state)
        state_digest = sha256_text(state_json)
        change_json = canonical_json(change_set)
        change_digest = sha256_text(change_json)

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)

            source_row = connection.execute(
                """
                SELECT source_event_identity, event_at_ms
                FROM stream_source_events
                WHERE stream_event_identity = ?
                """,
                (observation.stream_event_identity,),
            ).fetchone()
            if source_row is None:
                raise StreamStoryLedgerConflictError(
                    "Stream story observation references unknown source event"
                )
            if str(source_row[0]) != observation.source_event_identity:
                raise StreamStoryLedgerConflictError(
                    "Stream story/source-event identity mismatch"
                )
            if int(str(source_row[1])) != observation.event_at_ms:
                raise StreamStoryLedgerConflictError(
                    "Stream story/source-event time mismatch"
                )

            if observation.message_identity is not None:
                message_row = connection.execute(
                    """
                    SELECT story_identity, stream_event_identity, source_event_identity
                    FROM stream_message_inputs
                    WHERE message_identity = ?
                    """,
                    (observation.message_identity,),
                ).fetchone()
                if message_row is None:
                    raise StreamStoryLedgerConflictError(
                        "Stream story references unknown message input"
                    )
                if str(message_row[0]) != observation.story_identity:
                    raise StreamStoryLedgerConflictError(
                        "Stream story/message story mismatch"
                    )
                if str(message_row[1]) != observation.stream_event_identity:
                    raise StreamStoryLedgerConflictError(
                        "Stream story/message stream-event mismatch"
                    )
                if str(message_row[2]) != observation.source_event_identity:
                    raise StreamStoryLedgerConflictError(
                        "Stream story/message source-event mismatch"
                    )

            existing_observation = connection.execute(
                """
                SELECT observation_identity, payload_json, payload_sha256
                FROM stream_story_observations
                WHERE observation_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                LIMIT 1
                """,
                (
                    observation.observation_identity,
                    observation.source_event_identity,
                    observation.stream_event_identity,
                ),
            ).fetchone()
            existing_state = connection.execute(
                """
                SELECT state_identity, payload_json, payload_sha256
                FROM stream_story_states
                WHERE state_identity = ?
                   OR observation_identity = ?
                   OR source_event_identity = ?
                   OR current_stream_event_identity = ?
                LIMIT 1
                """,
                (
                    state.state_identity,
                    state.observation_identity,
                    state.source_event_identity,
                    state.current_stream_event_identity,
                ),
            ).fetchone()
            existing_change = connection.execute(
                """
                SELECT change_set_identity, payload_json, payload_sha256
                FROM stream_story_change_sets
                WHERE change_set_identity = ?
                   OR current_state_identity = ?
                LIMIT 1
                """,
                (change_set.change_set_identity, change_set.current_state_identity),
            ).fetchone()

            present = (
                existing_observation is not None,
                existing_state is not None,
                existing_change is not None,
            )
            if any(present):
                if not all(present):
                    raise StreamStoryLedgerConflictError(
                        "partial immutable Stream story transition already exists"
                    )
                assert existing_observation is not None
                assert existing_state is not None
                assert existing_change is not None
                exact = (
                    str(existing_observation[0]) == observation.observation_identity
                    and str(existing_observation[1]) == observation_json
                    and str(existing_observation[2]) == observation_digest
                    and str(existing_state[0]) == state.state_identity
                    and str(existing_state[1]) == state_json
                    and str(existing_state[2]) == state_digest
                    and str(existing_change[0]) == change_set.change_set_identity
                    and str(existing_change[1]) == change_json
                    and str(existing_change[2]) == change_digest
                )
                if exact:
                    return StreamStoryLedgerWriteDisposition.UNCHANGED
                raise StreamStoryLedgerConflictError(
                    "immutable Stream story transition conflict"
                )

            latest = connection.execute(
                """
                SELECT state_identity, event_at_ms, current_stream_event_identity
                FROM stream_story_states
                WHERE story_identity = ?
                ORDER BY event_at_ms DESC, state_identity DESC
                LIMIT 1
                """,
                (observation.story_identity,),
            ).fetchone()
            if latest is None:
                if observation.previous_state_identity is not None:
                    raise StreamStoryLedgerConflictError(
                        "new Stream story cannot reference unknown previous state"
                    )
            else:
                latest_identity = str(latest[0])
                if observation.previous_state_identity != latest_identity:
                    raise StreamStoryLedgerConflictError(
                        "Stream story append requires exact latest previous state"
                    )
                if (
                    observation.event_at_ms,
                    observation.stream_event_identity,
                ) <= (int(str(latest[1])), str(latest[2])):
                    raise StreamStoryLedgerConflictError(
                        "Stream story append would backfill or fork chronology"
                    )

            connection.execute(
                """
                INSERT INTO stream_story_observations (
                    observation_identity,
                    story_identity,
                    source_event_identity,
                    stream_event_identity,
                    message_identity,
                    previous_state_identity,
                    event_at_ms,
                    payload_json,
                    payload_sha256
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
                    observation_digest,
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_story_states (
                    state_identity,
                    story_identity,
                    observation_identity,
                    source_event_identity,
                    current_stream_event_identity,
                    current_message_identity,
                    previous_state_identity,
                    event_at_ms,
                    payload_json,
                    payload_sha256
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
                    state_digest,
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_story_change_sets (
                    change_set_identity,
                    story_identity,
                    current_state_identity,
                    previous_state_identity,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    change_set.change_set_identity,
                    change_set.story_identity,
                    change_set.current_state_identity,
                    change_set.previous_state_identity,
                    change_json,
                    change_digest,
                ),
            )
            connection.commit()
        return StreamStoryLedgerWriteDisposition.INSERTED

    def read_status(self) -> StreamStoryLedgerStatus:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            observation_count = self._count(
                connection,
                "stream_story_observations",
            )
            state_count = self._count(connection, "stream_story_states")
            change_count = self._count(
                connection,
                "stream_story_change_sets",
            )
            story_row = connection.execute(
                "SELECT COUNT(DISTINCT story_identity) FROM stream_story_states"
            ).fetchone()
        return StreamStoryLedgerStatus(
            observation_count=observation_count,
            state_count=state_count,
            change_set_count=change_count,
            story_count=0 if story_row is None else int(str(story_row[0])),
        )

    def read_latest_state(
        self,
        story_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(story_identity, "Stream story lookup")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT state_identity, payload_json, payload_sha256
                FROM stream_story_states
                WHERE story_identity = ?
                ORDER BY event_at_ms DESC, state_identity DESC
                LIMIT 1
                """,
                (story_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            identity_key="state_identity",
            expected_identity=str(row[0]),
            expected_schema=STREAM_STORY_STATE_SCHEMA_VERSION,
        )

    def read_change_set(
        self,
        current_state_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(
            current_state_identity,
            "Stream story change-set state lookup",
        )
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT change_set_identity, payload_json, payload_sha256
                FROM stream_story_change_sets
                WHERE current_state_identity = ?
                """,
                (current_state_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_record(
            payload_json=str(row[1]),
            expected_digest=str(row[2]),
            identity_key="change_set_identity",
            expected_identity=str(row[0]),
            expected_schema=STREAM_CHANGE_SET_SCHEMA_VERSION,
        )

    def read_story_states(
        self,
        story_identity: str,
        *,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        _require_sha256(story_identity, "Stream story history lookup")
        if limit < 1 or limit > 1000:
            raise ValueError("Stream story history limit must be inside 1..1000")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT state_identity, payload_json, payload_sha256
                FROM stream_story_states
                WHERE story_identity = ?
                ORDER BY event_at_ms, state_identity
                LIMIT ?
                """,
                (story_identity, limit),
            ).fetchall()
        return tuple(
            self._verified_record(
                payload_json=str(row[1]),
                expected_digest=str(row[2]),
                identity_key="state_identity",
                expected_identity=str(row[0]),
                expected_schema=STREAM_STORY_STATE_SCHEMA_VERSION,
            )
            for row in rows
        )

    @staticmethod
    def _validate_bundle(
        observation: StreamStoryObservation,
        state: StreamStoryState,
        change_set: StreamChangeSet,
    ) -> None:
        if state.observation_identity != observation.observation_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story state/observation mismatch"
            )
        if state.story_identity != observation.story_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story state/observation story mismatch"
            )
        if state.source_event_identity != observation.source_event_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story state/source-event mismatch"
            )
        if state.current_stream_event_identity != observation.stream_event_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story state/stream-event mismatch"
            )
        if state.current_message_identity != observation.message_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story state/message mismatch"
            )
        if state.previous_state_identity != observation.previous_state_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story previous-state mismatch"
            )
        if change_set.story_identity != state.story_identity:
            raise StreamStoryLedgerConflictError(
                "Stream change-set/state story mismatch"
            )
        if change_set.current_state_identity != state.state_identity:
            raise StreamStoryLedgerConflictError(
                "Stream change-set current-state mismatch"
            )
        if change_set.previous_state_identity != state.previous_state_identity:
            raise StreamStoryLedgerConflictError(
                "Stream change-set previous-state mismatch"
            )
        if change_set.current_message_identity != state.current_message_identity:
            raise StreamStoryLedgerConflictError(
                "Stream change-set current-message mismatch"
            )
        if change_set.previous_message_identity != state.previous_message_identity:
            raise StreamStoryLedgerConflictError(
                "Stream change-set previous-message mismatch"
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
            "stream_message_inputs",
            "stream_story_meta",
            "stream_story_observations",
            "stream_story_states",
            "stream_story_change_sets",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise StreamStoryLedgerConflictError(
                    f"Stream story ledger missing table: {table}"
                )

    @staticmethod
    def _verify_meta(connection: sqlite3.Connection) -> None:
        expected = {
            "engine_version": STREAM_ENGINE_VERSION,
            "real_capital": str(REAL_CAPITAL),
            "schema_version": STREAM_STORY_LEDGER_SCHEMA_VERSION,
        }
        rows = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT key, value FROM stream_story_meta"
            ).fetchall()
        }
        if rows != expected:
            raise StreamStoryLedgerConflictError(
                "Stream story ledger metadata mismatch"
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
            raise StreamStoryLedgerConflictError(
                "Stream story persisted payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamStoryLedgerConflictError(
                "Stream story payload must decode to object"
            )
        if raw.get(identity_key) != expected_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted identity column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop(identity_key, None)
        if canonical_sha256(identity_payload) != expected_identity:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted identity mismatch"
            )
        if raw.get("schema_version") != expected_schema:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted schema mismatch"
            )
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted engine mismatch"
            )
        if raw.get("read_only") is not True:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted read-only mismatch"
            )
        if raw.get("production_authority") is not False:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted production authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamStoryLedgerConflictError(
                "Stream story persisted REAL_CAPITAL mismatch"
            )
        return raw

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row is None:
            raise StreamStoryLedgerConflictError(
                f"Stream story count failed for {table}"
            )
        return int(str(row[0]))


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
