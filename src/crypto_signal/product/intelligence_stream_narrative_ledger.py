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
from crypto_signal.product.intelligence_stream_analytical_ledger import (
    IntelligenceStreamAnalyticalLedger,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_narrative import (
    STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
    STREAM_NARRATIVE_PLAN_SCHEMA_VERSION,
    StreamNarrativeMessage,
    StreamNarrativePlan,
)

STREAM_NARRATIVE_LEDGER_SCHEMA_VERSION = "intelligence-stream-narrative-ledger-v1/1"


class StreamNarrativeLedgerConflictError(ValueError):
    """Raised when immutable narrative history would fork or rewrite."""


class StreamNarrativeLedgerWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StreamNarrativeLedgerStatus:
    plan_count: int
    narrative_count: int
    story_count: int
    latest_event_at_ms: int | None
    schema_version: str = STREAM_NARRATIVE_LEDGER_SCHEMA_VERSION
    engine_version: str = STREAM_ENGINE_VERSION
    read_only: bool = True
    real_capital: int = REAL_CAPITAL


class IntelligenceStreamNarrativeLedger:
    """Append-only persistence for S5 narrative plans and original rendered text."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        IntelligenceStreamAnalyticalLedger(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stream_narrative_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stream_narrative_plans (
                    plan_identity TEXT PRIMARY KEY,
                    analytical_view_identity TEXT NOT NULL UNIQUE,
                    fact_bundle_identity TEXT NOT NULL UNIQUE,
                    change_set_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (analytical_view_identity)
                        REFERENCES stream_analytical_views(analytical_view_identity),
                    FOREIGN KEY (fact_bundle_identity)
                        REFERENCES stream_fact_bundles(fact_bundle_identity),
                    FOREIGN KEY (change_set_identity)
                        REFERENCES stream_story_change_sets(change_set_identity)
                );

                CREATE TABLE IF NOT EXISTS stream_narrative_messages (
                    narrative_identity TEXT PRIMARY KEY,
                    plan_identity TEXT NOT NULL UNIQUE,
                    analytical_view_identity TEXT NOT NULL UNIQUE,
                    story_identity TEXT NOT NULL,
                    source_event_identity TEXT NOT NULL UNIQUE,
                    stream_event_identity TEXT NOT NULL UNIQUE,
                    event_at_ms INTEGER NOT NULL,
                    source_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    FOREIGN KEY (plan_identity)
                        REFERENCES stream_narrative_plans(plan_identity),
                    FOREIGN KEY (analytical_view_identity)
                        REFERENCES stream_analytical_views(analytical_view_identity)
                );

                CREATE INDEX IF NOT EXISTS stream_narrative_story
                ON stream_narrative_messages(
                    story_identity,
                    event_at_ms,
                    narrative_identity
                );
                """
            )
            expected_meta = {
                "engine_version": STREAM_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": STREAM_NARRATIVE_LEDGER_SCHEMA_VERSION,
            }
            for key, value in expected_meta.items():
                row = connection.execute(
                    "SELECT value FROM stream_narrative_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO stream_narrative_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise StreamNarrativeLedgerConflictError(
                        f"Stream narrative ledger metadata mismatch for {key}"
                    )

            for table in (
                "stream_narrative_meta",
                "stream_narrative_plans",
                "stream_narrative_messages",
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
                                'immutable intelligence stream narrative ledger'
                            );
                        END
                        """
                    )

    def append_narrative(
        self,
        plan: StreamNarrativePlan,
        narrative: StreamNarrativeMessage,
    ) -> StreamNarrativeLedgerWriteDisposition:
        self._validate_pair(plan, narrative)
        self.initialize()
        plan_json = canonical_json(plan)
        plan_digest = sha256_text(plan_json)
        narrative_json = canonical_json(narrative)
        narrative_digest = sha256_text(narrative_json)

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            self._verify_meta(connection)

            analytical_row = connection.execute(
                """
                SELECT story_identity, fact_bundle_identity, change_set_identity,
                       source_event_identity, stream_event_identity, event_at_ms
                FROM stream_analytical_views
                WHERE analytical_view_identity = ?
                """,
                (plan.analytical_view_identity,),
            ).fetchone()
            if analytical_row is None:
                raise StreamNarrativeLedgerConflictError(
                    "Stream narrative references unknown Analytical View"
                )
            expected = (
                plan.story_identity,
                plan.fact_bundle_identity,
                plan.change_set_identity,
                plan.source_event_identity,
                plan.stream_event_identity,
                plan.event_at_ms,
            )
            actual = (
                str(analytical_row[0]),
                str(analytical_row[1]),
                str(analytical_row[2]),
                str(analytical_row[3]),
                str(analytical_row[4]),
                int(str(analytical_row[5])),
            )
            if actual != expected:
                raise StreamNarrativeLedgerConflictError(
                    "Stream narrative/Analytical View lineage mismatch"
                )

            existing_plan = connection.execute(
                """
                SELECT plan_identity, payload_json, payload_sha256
                FROM stream_narrative_plans
                WHERE plan_identity = ?
                   OR analytical_view_identity = ?
                   OR fact_bundle_identity = ?
                   OR change_set_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                LIMIT 1
                """,
                (
                    plan.plan_identity,
                    plan.analytical_view_identity,
                    plan.fact_bundle_identity,
                    plan.change_set_identity,
                    plan.source_event_identity,
                    plan.stream_event_identity,
                ),
            ).fetchone()
            existing_narrative = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_narrative_messages
                WHERE narrative_identity = ?
                   OR plan_identity = ?
                   OR analytical_view_identity = ?
                   OR source_event_identity = ?
                   OR stream_event_identity = ?
                LIMIT 1
                """,
                (
                    narrative.narrative_identity,
                    narrative.plan_identity,
                    narrative.analytical_view_identity,
                    narrative.source_event_identity,
                    narrative.stream_event_identity,
                ),
            ).fetchone()

            present = (
                existing_plan is not None,
                existing_narrative is not None,
            )
            if any(present):
                if not all(present):
                    raise StreamNarrativeLedgerConflictError(
                        "partial immutable Stream narrative already exists"
                    )
                assert existing_plan is not None
                assert existing_narrative is not None
                exact = (
                    str(existing_plan[0]) == plan.plan_identity
                    and str(existing_plan[1]) == plan_json
                    and str(existing_plan[2]) == plan_digest
                    and str(existing_narrative[0]) == narrative.narrative_identity
                    and str(existing_narrative[1]) == narrative_json
                    and str(existing_narrative[2]) == narrative_digest
                )
                if exact:
                    return StreamNarrativeLedgerWriteDisposition.UNCHANGED
                raise StreamNarrativeLedgerConflictError(
                    "immutable Stream narrative conflict"
                )

            latest = connection.execute(
                """
                SELECT event_at_ms, narrative_identity
                FROM stream_narrative_messages
                ORDER BY event_at_ms DESC, narrative_identity DESC
                LIMIT 1
                """
            ).fetchone()
            if latest is not None and (
                narrative.event_at_ms,
                narrative.narrative_identity,
            ) <= (int(str(latest[0])), str(latest[1])):
                raise StreamNarrativeLedgerConflictError(
                    "Stream narrative append would backfill or fork chronology"
                )

            connection.execute(
                """
                INSERT INTO stream_narrative_plans (
                    plan_identity,
                    analytical_view_identity,
                    fact_bundle_identity,
                    change_set_identity,
                    story_identity,
                    source_event_identity,
                    stream_event_identity,
                    event_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_identity,
                    plan.analytical_view_identity,
                    plan.fact_bundle_identity,
                    plan.change_set_identity,
                    plan.story_identity,
                    plan.source_event_identity,
                    plan.stream_event_identity,
                    plan.event_at_ms,
                    plan_json,
                    plan_digest,
                ),
            )
            connection.execute(
                """
                INSERT INTO stream_narrative_messages (
                    narrative_identity,
                    plan_identity,
                    analytical_view_identity,
                    story_identity,
                    source_event_identity,
                    stream_event_identity,
                    event_at_ms,
                    source_kind,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    narrative.narrative_identity,
                    narrative.plan_identity,
                    narrative.analytical_view_identity,
                    narrative.story_identity,
                    narrative.source_event_identity,
                    narrative.stream_event_identity,
                    narrative.event_at_ms,
                    narrative.source_kind.value,
                    narrative_json,
                    narrative_digest,
                ),
            )
            connection.commit()
        return StreamNarrativeLedgerWriteDisposition.INSERTED

    def read_status(self) -> StreamNarrativeLedgerStatus:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            plan_count = _count(connection, "stream_narrative_plans")
            narrative_count = _count(connection, "stream_narrative_messages")
            story_row = connection.execute(
                "SELECT COUNT(DISTINCT story_identity) FROM stream_narrative_messages"
            ).fetchone()
            latest_row = connection.execute(
                "SELECT MAX(event_at_ms) FROM stream_narrative_messages"
            ).fetchone()
        return StreamNarrativeLedgerStatus(
            plan_count=plan_count,
            narrative_count=narrative_count,
            story_count=0 if story_row is None else int(str(story_row[0])),
            latest_event_at_ms=(
                None
                if latest_row is None or latest_row[0] is None
                else int(str(latest_row[0]))
            ),
        )

    def read_for_analytical_view(
        self,
        analytical_view_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(
            analytical_view_identity,
            "Stream narrative Analytical View lookup",
        )
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            row = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_narrative_messages
                WHERE analytical_view_identity = ?
                """,
                (analytical_view_identity,),
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
        _require_sha256(story_identity, "Stream narrative story lookup")
        if limit < 1 or limit > 1000:
            raise ValueError("Stream narrative story limit must be inside 1..1000")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            self._verify_meta(connection)
            rows = connection.execute(
                """
                SELECT narrative_identity, payload_json, payload_sha256
                FROM stream_narrative_messages
                WHERE story_identity = ?
                ORDER BY event_at_ms, narrative_identity
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

    @staticmethod
    def _validate_pair(
        plan: StreamNarrativePlan,
        narrative: StreamNarrativeMessage,
    ) -> None:
        if narrative.plan_identity != plan.plan_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/plan identity mismatch"
            )
        if narrative.analytical_view_identity != plan.analytical_view_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/analytical identity mismatch"
            )
        if narrative.fact_bundle_identity != plan.fact_bundle_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/fact identity mismatch"
            )
        if narrative.change_set_identity != plan.change_set_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/change identity mismatch"
            )
        if narrative.story_identity != plan.story_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/story mismatch"
            )
        if narrative.source_event_identity != plan.source_event_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/source-event mismatch"
            )
        if narrative.stream_event_identity != plan.stream_event_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/stream-event mismatch"
            )
        if narrative.event_at_ms != plan.event_at_ms:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative message/event-time mismatch"
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
            "stream_analytical_views",
            "stream_fact_bundles",
            "stream_story_change_sets",
            "stream_narrative_meta",
            "stream_narrative_plans",
            "stream_narrative_messages",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise StreamNarrativeLedgerConflictError(
                    f"Stream narrative ledger missing table: {table}"
                )

    @staticmethod
    def _verify_meta(connection: sqlite3.Connection) -> None:
        expected = {
            "engine_version": STREAM_ENGINE_VERSION,
            "real_capital": str(REAL_CAPITAL),
            "schema_version": STREAM_NARRATIVE_LEDGER_SCHEMA_VERSION,
        }
        rows = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT key, value FROM stream_narrative_meta"
            ).fetchall()
        }
        if rows != expected:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative ledger metadata mismatch"
            )

    @staticmethod
    def _verified_record(
        *,
        payload_json: str,
        expected_digest: str,
        expected_identity: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative payload must decode to object"
            )
        if raw.get("narrative_identity") != expected_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted identity column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop("narrative_identity", None)
        if canonical_sha256(identity_payload) != expected_identity:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted identity mismatch"
            )
        if raw.get("schema_version") != STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted schema mismatch"
            )
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted engine mismatch"
            )
        if raw.get("read_only") is not True:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted read-only mismatch"
            )
        if raw.get("production_authority") is not False:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted production authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamNarrativeLedgerConflictError(
                "Stream narrative persisted REAL_CAPITAL mismatch"
            )
        return raw


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise StreamNarrativeLedgerConflictError(
            f"Stream narrative count failed for {table}"
        )
    return int(str(row[0]))


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
