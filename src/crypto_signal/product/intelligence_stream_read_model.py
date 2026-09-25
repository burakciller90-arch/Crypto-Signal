from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_narrative import (
    STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
)

STREAM_READ_MODEL_SCHEMA_VERSION = "intelligence-stream-read-model-v1/1"
STREAM_CURSOR_SCHEMA_VERSION = "intelligence-stream-cursor-v1/1"
DEFAULT_STREAM_PAGE_LIMIT = 50
MAX_STREAM_PAGE_LIMIT = 200


class StreamReadModelError(ValueError):
    """Raised when persisted Stream read truth is invalid or cursor input is unsafe."""


@dataclass(frozen=True, slots=True)
class StreamCursor:
    event_at_ms: int
    narrative_identity: str
    schema_version: str = STREAM_CURSOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.event_at_ms < 0:
            raise ValueError("Stream cursor time must be non-negative")
        _require_sha256(self.narrative_identity, "Stream cursor narrative identity")
        if self.schema_version != STREAM_CURSOR_SCHEMA_VERSION:
            raise ValueError("unsupported Stream cursor schema")


@dataclass(frozen=True, slots=True)
class StreamMessageQuery:
    limit: int = DEFAULT_STREAM_PAGE_LIMIT
    before: StreamCursor | None = None
    after: StreamCursor | None = None
    symbol: str | None = None
    timeframe: str | None = None
    story_identity: str | None = None
    source_kind: str | None = None
    effective_stance: str | None = None
    category: str | None = None
    importance: str | None = None
    evidence_domain: str | None = None
    from_ms: int | None = None
    to_ms: int | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > MAX_STREAM_PAGE_LIMIT:
            raise ValueError(
                f"Stream message limit must be inside 1..{MAX_STREAM_PAGE_LIMIT}"
            )
        if self.before is not None and self.after is not None:
            raise ValueError("Stream query cannot use before and after together")
        if self.story_identity is not None:
            _require_sha256(self.story_identity, "Stream query story identity")
        for value, label in (
            (self.symbol, "Stream query symbol"),
            (self.timeframe, "Stream query timeframe"),
            (self.source_kind, "Stream query source kind"),
            (self.effective_stance, "Stream query effective stance"),
            (self.category, "Stream query category"),
            (self.importance, "Stream query importance"),
            (self.evidence_domain, "Stream query evidence domain"),
            (self.text, "Stream query text"),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{label} cannot be blank")
        if self.from_ms is not None and self.from_ms < 0:
            raise ValueError("Stream query from_ms must be non-negative")
        if self.to_ms is not None and self.to_ms < 0:
            raise ValueError("Stream query to_ms must be non-negative")
        if (
            self.from_ms is not None
            and self.to_ms is not None
            and self.from_ms > self.to_ms
        ):
            raise ValueError("Stream query from_ms cannot exceed to_ms")


@dataclass(frozen=True, slots=True)
class StreamReadPage:
    items: tuple[dict[str, Any], ...]
    order: str
    newest_cursor: str | None
    oldest_cursor: str | None
    next_after_cursor: str | None
    next_before_cursor: str | None
    has_more: bool
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = STREAM_READ_MODEL_SCHEMA_VERSION


class IntelligenceStreamReadModel:
    """Read-only cursor/search model over immutable S5 narrative persistence."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read_messages(self, query: StreamMessageQuery) -> StreamReadPage:
        params: list[object] = []
        clauses = ["1 = 1"]

        if query.before is not None:
            clauses.append(
                "(n.event_at_ms < ? OR "
                "(n.event_at_ms = ? AND n.narrative_identity < ?))"
            )
            params.extend(
                (
                    query.before.event_at_ms,
                    query.before.event_at_ms,
                    query.before.narrative_identity,
                )
            )
        if query.after is not None:
            clauses.append(
                "(n.event_at_ms > ? OR "
                "(n.event_at_ms = ? AND n.narrative_identity > ?))"
            )
            params.extend(
                (
                    query.after.event_at_ms,
                    query.after.event_at_ms,
                    query.after.narrative_identity,
                )
            )
        if query.story_identity is not None:
            clauses.append("n.story_identity = ?")
            params.append(query.story_identity)
        if query.source_kind is not None:
            clauses.append("n.source_kind = ?")
            params.append(query.source_kind)
        if query.symbol is not None:
            clauses.append("json_extract(n.payload_json, '$.symbol') = ?")
            params.append(query.symbol)
        if query.timeframe is not None:
            clauses.append("json_extract(n.payload_json, '$.timeframe') = ?")
            params.append(query.timeframe)
        if query.effective_stance is not None:
            clauses.append(
                "json_extract(a.payload_json, '$.stance.effective_stance') = ?"
            )
            params.append(query.effective_stance)
        if query.category is not None:
            clauses.append("json_extract(m.payload_json, '$.category') = ?")
            params.append(query.category)
        if query.importance is not None:
            clauses.append("json_extract(m.payload_json, '$.importance') = ?")
            params.append(query.importance)
        if query.evidence_domain is not None:
            clauses.append(
                "EXISTS ("
                "SELECT 1 FROM json_each("
                "json_extract(f.payload_json, '$.available_evidence_domains')"
                ") AS evidence_domain "
                "WHERE evidence_domain.value = ?"
                ")"
            )
            params.append(query.evidence_domain)
        if query.from_ms is not None:
            clauses.append("n.event_at_ms >= ?")
            params.append(query.from_ms)
        if query.to_ms is not None:
            clauses.append("n.event_at_ms <= ?")
            params.append(query.to_ms)
        if query.text is not None:
            needle = f"%{_escape_like(query.text.casefold())}%"
            text_fields = (
                "$.text.collapsed_text",
                "$.text.simple_text",
                "$.text.technical_text",
                "$.text.intelligence_text",
                "$.text.decision_text",
                "$.text.capital_text",
            )
            clauses.append(
                "("
                + " OR ".join(
                    "lower(json_extract(n.payload_json, ?)) LIKE ? ESCAPE '\\'"
                    for _ in text_fields
                )
                + ")"
            )
            for field in text_fields:
                params.extend((field, needle))

        ascending = query.after is not None
        order_sql = (
            "ORDER BY n.event_at_ms ASC, n.narrative_identity ASC"
            if ascending
            else "ORDER BY n.event_at_ms DESC, n.narrative_identity DESC"
        )
        sql = f"""
            SELECT
                n.narrative_identity,
                n.event_at_ms,
                n.payload_json,
                n.payload_sha256
            FROM stream_narrative_messages AS n
            JOIN stream_narrative_plans AS p
              ON p.plan_identity = n.plan_identity
            JOIN stream_analytical_views AS a
              ON a.analytical_view_identity = n.analytical_view_identity
            JOIN stream_fact_bundles AS f
              ON f.fact_bundle_identity = p.fact_bundle_identity
            LEFT JOIN stream_message_inputs AS m
              ON m.message_identity = a.source_message_identity
            WHERE {" AND ".join(clauses)}
            {order_sql}
            LIMIT ?
        """
        params.append(query.limit + 1)

        with self._connect_ro() as connection:
            self._require_schema(connection)
            rows = connection.execute(sql, tuple(params)).fetchall()

        has_more = len(rows) > query.limit
        visible_rows = rows[: query.limit]
        items = tuple(
            self._verified_narrative_record(
                narrative_identity=str(row[0]),
                event_at_ms=int(str(row[1])),
                payload_json=str(row[2]),
                expected_digest=str(row[3]),
            )
            for row in visible_rows
        )
        if not items:
            return StreamReadPage(
                items=(),
                order="oldest_to_newest" if ascending else "newest_to_oldest",
                newest_cursor=None,
                oldest_cursor=None,
                next_after_cursor=None,
                next_before_cursor=None,
                has_more=False,
            )

        chronological = (
            items if ascending else tuple(reversed(items))
        )
        oldest_item = chronological[0]
        newest_item = chronological[-1]
        oldest_cursor = encode_stream_cursor(
            StreamCursor(
                event_at_ms=_record_event_at_ms(oldest_item),
                narrative_identity=_record_identity(oldest_item),
            )
        )
        newest_cursor = encode_stream_cursor(
            StreamCursor(
                event_at_ms=_record_event_at_ms(newest_item),
                narrative_identity=_record_identity(newest_item),
            )
        )
        return StreamReadPage(
            items=items,
            order="oldest_to_newest" if ascending else "newest_to_oldest",
            newest_cursor=newest_cursor,
            oldest_cursor=oldest_cursor,
            next_after_cursor=newest_cursor,
            next_before_cursor=oldest_cursor,
            has_more=has_more,
        )

    def read_message(self, narrative_identity: str) -> dict[str, Any] | None:
        _require_sha256(narrative_identity, "Stream narrative lookup identity")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            row = connection.execute(
                """
                SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                FROM stream_narrative_messages
                WHERE narrative_identity = ?
                """,
                (narrative_identity,),
            ).fetchone()
        if row is None:
            return None
        return self._verified_narrative_record(
            narrative_identity=str(row[0]),
            event_at_ms=int(str(row[1])),
            payload_json=str(row[2]),
            expected_digest=str(row[3]),
        )

    def latest_cursor(self) -> str | None:
        with self._connect_ro() as connection:
            self._require_schema(connection)
            row = connection.execute(
                """
                SELECT event_at_ms, narrative_identity
                FROM stream_narrative_messages
                ORDER BY event_at_ms DESC, narrative_identity DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return encode_stream_cursor(
            StreamCursor(
                event_at_ms=int(str(row[0])),
                narrative_identity=str(row[1]),
            )
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
            "stream_narrative_messages",
            "stream_narrative_plans",
            "stream_analytical_views",
            "stream_fact_bundles",
            "stream_message_inputs",
        ):
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None:
                raise StreamReadModelError(
                    f"Stream read model missing table: {table}"
                )

    @staticmethod
    def _verified_narrative_record(
        *,
        narrative_identity: str,
        event_at_ms: int,
        payload_json: str,
        expected_digest: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamReadModelError(
                "Stream read narrative payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamReadModelError(
                "Stream read narrative payload must decode to object"
            )
        if raw.get("narrative_identity") != narrative_identity:
            raise StreamReadModelError(
                "Stream read narrative identity column mismatch"
            )
        if raw.get("event_at_ms") != event_at_ms:
            raise StreamReadModelError(
                "Stream read narrative event-time column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop("narrative_identity", None)
        if canonical_sha256(identity_payload) != narrative_identity:
            raise StreamReadModelError(
                "Stream read narrative canonical identity mismatch"
            )
        if raw.get("schema_version") != STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION:
            raise StreamReadModelError(
                "Stream read narrative schema mismatch"
            )
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamReadModelError(
                "Stream read narrative engine mismatch"
            )
        if raw.get("read_only") is not True:
            raise StreamReadModelError(
                "Stream read narrative read-only mismatch"
            )
        if raw.get("production_authority") is not False:
            raise StreamReadModelError(
                "Stream read narrative production-authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamReadModelError(
                "Stream read narrative REAL_CAPITAL mismatch"
            )
        return raw


def encode_stream_cursor(cursor: StreamCursor) -> str:
    raw = canonical_json(
        {
            "event_at_ms": cursor.event_at_ms,
            "narrative_identity": cursor.narrative_identity,
            "schema_version": cursor.schema_version,
        }
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_stream_cursor(value: str) -> StreamCursor:
    if not value or len(value) > 512:
        raise StreamReadModelError("invalid Stream cursor")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding).decode("utf-8")
        raw = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StreamReadModelError("invalid Stream cursor") from exc
    if not isinstance(raw, dict):
        raise StreamReadModelError("invalid Stream cursor payload")
    if set(raw) != {"event_at_ms", "narrative_identity", "schema_version"}:
        raise StreamReadModelError("invalid Stream cursor shape")
    try:
        return StreamCursor(
            event_at_ms=int(raw["event_at_ms"]),
            narrative_identity=str(raw["narrative_identity"]),
            schema_version=str(raw["schema_version"]),
        )
    except (TypeError, ValueError) as exc:
        raise StreamReadModelError("invalid Stream cursor fields") from exc


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _record_identity(record: dict[str, Any]) -> str:
    value = record.get("narrative_identity")
    if not isinstance(value, str):
        raise StreamReadModelError("Stream read record missing narrative identity")
    _require_sha256(value, "Stream read record narrative identity")
    return value


def _record_event_at_ms(record: dict[str, Any]) -> int:
    value = record.get("event_at_ms")
    if not isinstance(value, int) or value < 0:
        raise StreamReadModelError("Stream read record missing event time")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")
