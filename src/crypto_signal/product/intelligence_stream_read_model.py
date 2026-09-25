from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.product.intelligence_stream_analytical import (
    STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital import (
    STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital_decisions import (
    STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital_sizing import (
    STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_capital_lifecycle import (
    STREAM_CAPITAL_LIFECYCLE_MESSAGE_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_messages import (
    STREAM_FACT_BUNDLE_SCHEMA_VERSION,
    STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
)
from crypto_signal.product.intelligence_stream_models import (
    REAL_CAPITAL,
    STREAM_ENGINE_VERSION,
)
from crypto_signal.product.intelligence_stream_narrative import (
    STREAM_NARRATIVE_MESSAGE_SCHEMA_VERSION,
)

STREAM_READ_MODEL_SCHEMA_VERSION = "intelligence-stream-read-model-v1/1"
STREAM_CURSOR_SCHEMA_VERSION = "intelligence-stream-cursor-v1/1"
STREAM_MESSAGE_DETAIL_SCHEMA_VERSION = "intelligence-stream-message-detail-v1/1"
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
            capital_items = self._read_capital_messages(connection, query)
            capital_decision_items = self._read_capital_decision_messages(
                connection,
                query,
            )
            capital_sizing_items = self._read_capital_sizing_messages(
                connection,
                query,
            )
            capital_lifecycle_items = self._read_capital_lifecycle_messages(
                connection,
                query,
            )

        regular_items = tuple(
            self._verified_narrative_record(
                narrative_identity=str(row[0]),
                event_at_ms=int(str(row[1])),
                payload_json=str(row[2]),
                expected_digest=str(row[3]),
            )
            for row in rows
        )
        combined = [
            *regular_items,
            *capital_items,
            *capital_decision_items,
            *capital_sizing_items,
            *capital_lifecycle_items,
        ]
        combined.sort(
            key=lambda item: (
                _record_event_at_ms(item),
                _record_identity(item),
            ),
            reverse=not ascending,
        )
        has_more = len(combined) > query.limit
        items = tuple(combined[: query.limit])
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
            capital_row = None
            if row is None and self._table_exists(
                connection,
                "stream_capital_messages",
            ):
                capital_row = connection.execute(
                    """
                    SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                    FROM stream_capital_messages
                    WHERE narrative_identity = ?
                    """,
                    (narrative_identity,),
                ).fetchone()
            capital_decision_row = None
            if (
                row is None
                and capital_row is None
                and self._table_exists(
                    connection,
                    "stream_capital_decision_messages",
                )
            ):
                capital_decision_row = connection.execute(
                    """
                    SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                    FROM stream_capital_decision_messages
                    WHERE narrative_identity = ?
                    """,
                    (narrative_identity,),
                ).fetchone()
            capital_sizing_row = None
            if (
                row is None
                and capital_row is None
                and capital_decision_row is None
                and self._table_exists(
                    connection,
                    "stream_capital_sizing_messages",
                )
            ):
                capital_sizing_row = connection.execute(
                    """
                    SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                    FROM stream_capital_sizing_messages
                    WHERE narrative_identity = ?
                    """,
                    (narrative_identity,),
                ).fetchone()
                capital_lifecycle_row = None
                if (
                    capital_row is None
                    and capital_decision_row is None
                    and capital_sizing_row is None
                    and self._table_exists(
                        connection,
                        "stream_capital_lifecycle_messages",
                    )
                ):
                    capital_lifecycle_row = connection.execute(
                        """
                        SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                        FROM stream_capital_lifecycle_messages
                        WHERE narrative_identity = ?
                        """,
                        (narrative_identity,),
                    ).fetchone()
            capital_lifecycle_row = None
            if (
                row is None
                and capital_row is None
                and capital_decision_row is None
                and capital_sizing_row is None
                and self._table_exists(
                    connection,
                    "stream_capital_lifecycle_messages",
                )
            ):
                capital_lifecycle_row = connection.execute(
                    """
                    SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                    FROM stream_capital_lifecycle_messages
                    WHERE narrative_identity = ?
                    """,
                    (narrative_identity,),
                ).fetchone()
        if row is not None:
            return self._verified_narrative_record(
                narrative_identity=str(row[0]),
                event_at_ms=int(str(row[1])),
                payload_json=str(row[2]),
                expected_digest=str(row[3]),
            )
        if capital_row is not None:
            return self._verified_capital_record(
                narrative_identity=str(capital_row[0]),
                event_at_ms=int(str(capital_row[1])),
                payload_json=str(capital_row[2]),
                expected_digest=str(capital_row[3]),
            )
        if capital_decision_row is not None:
            return self._verified_capital_decision_record(
                narrative_identity=str(capital_decision_row[0]),
                event_at_ms=int(str(capital_decision_row[1])),
                payload_json=str(capital_decision_row[2]),
                expected_digest=str(capital_decision_row[3]),
            )
        if capital_sizing_row is not None:
            return self._verified_capital_sizing_record(
                narrative_identity=str(capital_sizing_row[0]),
                event_at_ms=int(str(capital_sizing_row[1])),
                payload_json=str(capital_sizing_row[2]),
                expected_digest=str(capital_sizing_row[3]),
            )
        if capital_lifecycle_row is None:
            return None
        return self._verified_capital_lifecycle_record(
            narrative_identity=str(capital_lifecycle_row[0]),
            event_at_ms=int(str(capital_lifecycle_row[1])),
            payload_json=str(capital_lifecycle_row[2]),
            expected_digest=str(capital_lifecycle_row[3]),
        )

    def read_message_detail(
        self,
        narrative_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(narrative_identity, "Stream detail narrative identity")
        with self._connect_ro() as connection:
            self._require_schema(connection)
            row = connection.execute(
                """
                SELECT
                    n.narrative_identity,
                    n.event_at_ms,
                    n.payload_json,
                    n.payload_sha256,
                    a.analytical_view_identity,
                    a.payload_json,
                    a.payload_sha256,
                    f.fact_bundle_identity,
                    f.payload_json,
                    f.payload_sha256,
                    m.message_identity,
                    m.payload_json,
                    m.payload_sha256
                FROM stream_narrative_messages AS n
                JOIN stream_narrative_plans AS p
                  ON p.plan_identity = n.plan_identity
                JOIN stream_analytical_views AS a
                  ON a.analytical_view_identity = n.analytical_view_identity
                JOIN stream_fact_bundles AS f
                  ON f.fact_bundle_identity = p.fact_bundle_identity
                LEFT JOIN stream_message_inputs AS m
                  ON m.message_identity = a.source_message_identity
                WHERE n.narrative_identity = ?
                """,
                (narrative_identity,),
            ).fetchone()
        if row is None:
            with self._connect_ro() as connection:
                capital_row = None
                if self._table_exists(connection, "stream_capital_messages"):
                    capital_row = connection.execute(
                        """
                        SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                        FROM stream_capital_messages
                        WHERE narrative_identity = ?
                        """,
                        (narrative_identity,),
                    ).fetchone()
                capital_decision_row = None
                if (
                    capital_row is None
                    and self._table_exists(
                        connection,
                        "stream_capital_decision_messages",
                    )
                ):
                    capital_decision_row = connection.execute(
                        """
                        SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                        FROM stream_capital_decision_messages
                        WHERE narrative_identity = ?
                        """,
                        (narrative_identity,),
                    ).fetchone()
                capital_sizing_row = None
                if (
                    capital_row is None
                    and capital_decision_row is None
                    and self._table_exists(
                        connection,
                        "stream_capital_sizing_messages",
                    )
                ):
                    capital_sizing_row = connection.execute(
                        """
                        SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
                        FROM stream_capital_sizing_messages
                        WHERE narrative_identity = ?
                        """,
                        (narrative_identity,),
                    ).fetchone()
            if capital_row is not None:
                capital = self._verified_capital_record(
                    narrative_identity=str(capital_row[0]),
                    event_at_ms=int(str(capital_row[1])),
                    payload_json=str(capital_row[2]),
                    expected_digest=str(capital_row[3]),
                )
                return {
                    "narrative": capital,
                    "capital_story": capital,
                    "schema_version": STREAM_MESSAGE_DETAIL_SCHEMA_VERSION,
                    "read_only": True,
                    "production_authority": False,
                    "real_capital": REAL_CAPITAL,
                }
            if capital_decision_row is not None:
                capital_decision = self._verified_capital_decision_record(
                    narrative_identity=str(capital_decision_row[0]),
                    event_at_ms=int(str(capital_decision_row[1])),
                    payload_json=str(capital_decision_row[2]),
                    expected_digest=str(capital_decision_row[3]),
                )
                return {
                    "narrative": capital_decision,
                    "capital_decision": capital_decision,
                    "schema_version": STREAM_MESSAGE_DETAIL_SCHEMA_VERSION,
                    "read_only": True,
                    "production_authority": False,
                    "real_capital": REAL_CAPITAL,
                }
            if capital_sizing_row is not None:
                capital_sizing = self._verified_capital_sizing_record(
                    narrative_identity=str(capital_sizing_row[0]),
                    event_at_ms=int(str(capital_sizing_row[1])),
                    payload_json=str(capital_sizing_row[2]),
                    expected_digest=str(capital_sizing_row[3]),
                )
                return {
                    "narrative": capital_sizing,
                    "capital_sizing": capital_sizing,
                    "schema_version": STREAM_MESSAGE_DETAIL_SCHEMA_VERSION,
                    "read_only": True,
                    "production_authority": False,
                    "real_capital": REAL_CAPITAL,
                }
            if capital_lifecycle_row is None:
                return None
            capital_lifecycle = self._verified_capital_lifecycle_record(
                narrative_identity=str(capital_lifecycle_row[0]),
                event_at_ms=int(str(capital_lifecycle_row[1])),
                payload_json=str(capital_lifecycle_row[2]),
                expected_digest=str(capital_lifecycle_row[3]),
            )
            return {
                "narrative": capital_lifecycle,
                "capital_lifecycle": capital_lifecycle,
                "schema_version": STREAM_MESSAGE_DETAIL_SCHEMA_VERSION,
                "read_only": True,
                "production_authority": False,
                "real_capital": REAL_CAPITAL,
            }

        narrative = self._verified_narrative_record(
            narrative_identity=str(row[0]),
            event_at_ms=int(str(row[1])),
            payload_json=str(row[2]),
            expected_digest=str(row[3]),
        )
        analytical = self._verified_linked_record(
            payload_json=str(row[5]),
            expected_digest=str(row[6]),
            identity_key="analytical_view_identity",
            expected_identity=str(row[4]),
            expected_schema=STREAM_ANALYTICAL_VIEW_SCHEMA_VERSION,
        )
        fact_bundle = self._verified_linked_record(
            payload_json=str(row[8]),
            expected_digest=str(row[9]),
            identity_key="fact_bundle_identity",
            expected_identity=str(row[7]),
            expected_schema=STREAM_FACT_BUNDLE_SCHEMA_VERSION,
        )
        message_input = (
            None
            if row[10] is None
            else self._verified_linked_record(
                payload_json=str(row[11]),
                expected_digest=str(row[12]),
                identity_key="message_identity",
                expected_identity=str(row[10]),
                expected_schema=STREAM_MESSAGE_INPUT_SCHEMA_VERSION,
            )
        )
        self._verify_detail_lineage(
            narrative=narrative,
            analytical=analytical,
            fact_bundle=fact_bundle,
            message_input=message_input,
        )
        return {
            "narrative": narrative,
            "analytical_view": analytical,
            "fact_bundle": fact_bundle,
            "message_input": message_input,
            "schema_version": STREAM_MESSAGE_DETAIL_SCHEMA_VERSION,
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }

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
            capital_row = None
            if self._table_exists(connection, "stream_capital_messages"):
                capital_row = connection.execute(
                    """
                    SELECT event_at_ms, narrative_identity
                    FROM stream_capital_messages
                    ORDER BY event_at_ms DESC, narrative_identity DESC
                    LIMIT 1
                    """
                ).fetchone()
            capital_decision_row = None
            if self._table_exists(
                connection,
                "stream_capital_decision_messages",
            ):
                capital_decision_row = connection.execute(
                    """
                    SELECT event_at_ms, narrative_identity
                    FROM stream_capital_decision_messages
                    ORDER BY event_at_ms DESC, narrative_identity DESC
                    LIMIT 1
                    """
                ).fetchone()
            capital_sizing_row = None
            if self._table_exists(
                connection,
                "stream_capital_sizing_messages",
            ):
                capital_sizing_row = connection.execute(
                    """
                    SELECT event_at_ms, narrative_identity
                    FROM stream_capital_sizing_messages
                    ORDER BY event_at_ms DESC, narrative_identity DESC
                    LIMIT 1
                    """
                ).fetchone()
            capital_lifecycle_row = None
            if self._table_exists(
                connection,
                "stream_capital_lifecycle_messages",
            ):
                capital_lifecycle_row = connection.execute(
                    """
                    SELECT event_at_ms, narrative_identity
                    FROM stream_capital_lifecycle_messages
                    ORDER BY event_at_ms DESC, narrative_identity DESC
                    LIMIT 1
                    """
                ).fetchone()
        candidates = tuple(
            (int(str(item[0])), str(item[1]))
            for item in (
                row,
                capital_row,
                capital_decision_row,
                capital_sizing_row,
                capital_lifecycle_row,
            )
            if item is not None
        )
        if not candidates:
            return None
        event_at_ms, narrative_identity = max(candidates)
        return encode_stream_cursor(
            StreamCursor(
                event_at_ms=event_at_ms,
                narrative_identity=narrative_identity,
            )
        )

    def _read_capital_messages(
        self,
        connection: sqlite3.Connection,
        query: StreamMessageQuery,
    ) -> tuple[dict[str, Any], ...]:
        if not self._table_exists(connection, "stream_capital_messages"):
            return ()
        if query.effective_stance is not None or query.evidence_domain is not None:
            return ()
        if query.category is not None and query.category != "capital":
            return ()
        if query.importance is not None and query.importance != "important":
            return ()
        if query.source_kind is not None and query.source_kind != "deterministic":
            return ()

        clauses = ["1 = 1"]
        params: list[object] = []
        if query.before is not None:
            clauses.append(
                "(event_at_ms < ? OR "
                "(event_at_ms = ? AND narrative_identity < ?))"
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
                "(event_at_ms > ? OR "
                "(event_at_ms = ? AND narrative_identity > ?))"
            )
            params.extend(
                (
                    query.after.event_at_ms,
                    query.after.event_at_ms,
                    query.after.narrative_identity,
                )
            )
        if query.story_identity is not None:
            clauses.append("story_identity = ?")
            params.append(query.story_identity)
        if query.symbol is not None:
            clauses.append("symbol = ?")
            params.append(query.symbol)
        if query.timeframe is not None:
            clauses.append("timeframe = ?")
            params.append(query.timeframe)
        if query.from_ms is not None:
            clauses.append("event_at_ms >= ?")
            params.append(query.from_ms)
        if query.to_ms is not None:
            clauses.append("event_at_ms <= ?")
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
                    "lower(json_extract(payload_json, ?)) LIKE ? ESCAPE '\\'"
                    for _ in text_fields
                )
                + ")"
            )
            for field in text_fields:
                params.extend((field, needle))

        ascending = query.after is not None
        order_sql = (
            "ORDER BY event_at_ms ASC, narrative_identity ASC"
            if ascending
            else "ORDER BY event_at_ms DESC, narrative_identity DESC"
        )
        rows = connection.execute(
            f"""
            SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
            FROM stream_capital_messages
            WHERE {" AND ".join(clauses)}
            {order_sql}
            LIMIT ?
            """,
            (*params, query.limit + 1),
        ).fetchall()
        return tuple(
            self._verified_capital_record(
                narrative_identity=str(row[0]),
                event_at_ms=int(str(row[1])),
                payload_json=str(row[2]),
                expected_digest=str(row[3]),
            )
            for row in rows
        )

    def _read_capital_decision_messages(
        self,
        connection: sqlite3.Connection,
        query: StreamMessageQuery,
    ) -> tuple[dict[str, Any], ...]:
        if not self._table_exists(
            connection,
            "stream_capital_decision_messages",
        ):
            return ()
        if query.effective_stance is not None or query.evidence_domain is not None:
            return ()
        if query.category is not None and query.category != "capital":
            return ()
        if query.importance is not None and query.importance != "important":
            return ()
        if query.source_kind is not None and query.source_kind != "deterministic":
            return ()

        clauses = ["1 = 1"]
        params: list[object] = []
        if query.before is not None:
            clauses.append(
                "(event_at_ms < ? OR "
                "(event_at_ms = ? AND narrative_identity < ?))"
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
                "(event_at_ms > ? OR "
                "(event_at_ms = ? AND narrative_identity > ?))"
            )
            params.extend(
                (
                    query.after.event_at_ms,
                    query.after.event_at_ms,
                    query.after.narrative_identity,
                )
            )
        if query.story_identity is not None:
            clauses.append("story_identity = ?")
            params.append(query.story_identity)
        if query.symbol is not None:
            clauses.append("symbol = ?")
            params.append(query.symbol)
        if query.timeframe is not None:
            clauses.append("timeframe = ?")
            params.append(query.timeframe)
        if query.from_ms is not None:
            clauses.append("event_at_ms >= ?")
            params.append(query.from_ms)
        if query.to_ms is not None:
            clauses.append("event_at_ms <= ?")
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
                    "lower(json_extract(payload_json, ?)) LIKE ? ESCAPE '\\'"
                    for _ in text_fields
                )
                + ")"
            )
            for field in text_fields:
                params.extend((field, needle))

        ascending = query.after is not None
        order_sql = (
            "ORDER BY event_at_ms ASC, narrative_identity ASC"
            if ascending
            else "ORDER BY event_at_ms DESC, narrative_identity DESC"
        )
        rows = connection.execute(
            f"""
            SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
            FROM stream_capital_decision_messages
            WHERE {" AND ".join(clauses)}
            {order_sql}
            LIMIT ?
            """,
            (*params, query.limit + 1),
        ).fetchall()
        return tuple(
            self._verified_capital_decision_record(
                narrative_identity=str(row[0]),
                event_at_ms=int(str(row[1])),
                payload_json=str(row[2]),
                expected_digest=str(row[3]),
            )
            for row in rows
        )

    def _read_capital_sizing_messages(
        self,
        connection: sqlite3.Connection,
        query: StreamMessageQuery,
    ) -> tuple[dict[str, Any], ...]:
        if not self._table_exists(
            connection,
            "stream_capital_sizing_messages",
        ):
            return ()
        if query.effective_stance is not None or query.evidence_domain is not None:
            return ()
        if query.category is not None and query.category != "capital":
            return ()
        if query.importance is not None and query.importance != "important":
            return ()
        if query.source_kind is not None and query.source_kind != "deterministic":
            return ()

        clauses = ["1 = 1"]
        params: list[object] = []
        if query.before is not None:
            clauses.append(
                "(event_at_ms < ? OR "
                "(event_at_ms = ? AND narrative_identity < ?))"
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
                "(event_at_ms > ? OR "
                "(event_at_ms = ? AND narrative_identity > ?))"
            )
            params.extend(
                (
                    query.after.event_at_ms,
                    query.after.event_at_ms,
                    query.after.narrative_identity,
                )
            )
        if query.story_identity is not None:
            clauses.append("story_identity = ?")
            params.append(query.story_identity)
        if query.symbol is not None:
            clauses.append("symbol = ?")
            params.append(query.symbol)
        if query.timeframe is not None:
            clauses.append("timeframe = ?")
            params.append(query.timeframe)
        if query.from_ms is not None:
            clauses.append("event_at_ms >= ?")
            params.append(query.from_ms)
        if query.to_ms is not None:
            clauses.append("event_at_ms <= ?")
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
                    "lower(json_extract(payload_json, ?)) LIKE ? ESCAPE '\\'"
                    for _ in text_fields
                )
                + ")"
            )
            for field in text_fields:
                params.extend((field, needle))

        ascending = query.after is not None
        order_sql = (
            "ORDER BY event_at_ms ASC, narrative_identity ASC"
            if ascending
            else "ORDER BY event_at_ms DESC, narrative_identity DESC"
        )
        rows = connection.execute(
            f"""
            SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
            FROM stream_capital_sizing_messages
            WHERE {" AND ".join(clauses)}
            {order_sql}
            LIMIT ?
            """,
            (*params, query.limit + 1),
        ).fetchall()
        return tuple(
            self._verified_capital_sizing_record(
                narrative_identity=str(row[0]),
                event_at_ms=int(str(row[1])),
                payload_json=str(row[2]),
                expected_digest=str(row[3]),
            )
            for row in rows
        )

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return (
            connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            is not None
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
    def _verified_linked_record(
        *,
        payload_json: str,
        expected_digest: str,
        identity_key: str,
        expected_identity: str,
        expected_schema: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamReadModelError("Stream detail persisted payload digest mismatch")
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamReadModelError("Stream detail payload must decode to object")
        if raw.get(identity_key) != expected_identity:
            raise StreamReadModelError("Stream detail identity column mismatch")
        identity_payload = dict(raw)
        identity_payload.pop(identity_key, None)
        if canonical_sha256(identity_payload) != expected_identity:
            raise StreamReadModelError("Stream detail canonical identity mismatch")
        if raw.get("schema_version") != expected_schema:
            raise StreamReadModelError("Stream detail schema mismatch")
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamReadModelError("Stream detail engine mismatch")
        if raw.get("read_only") is not True:
            raise StreamReadModelError("Stream detail read-only mismatch")
        if raw.get("production_authority") is not False:
            raise StreamReadModelError("Stream detail production-authority mismatch")
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamReadModelError("Stream detail REAL_CAPITAL mismatch")
        return raw

    @staticmethod
    def _verify_detail_lineage(
        *,
        narrative: dict[str, Any],
        analytical: dict[str, Any],
        fact_bundle: dict[str, Any],
        message_input: dict[str, Any] | None,
    ) -> None:
        if narrative.get("analytical_view_identity") != analytical.get(
            "analytical_view_identity"
        ):
            raise StreamReadModelError("Stream detail narrative/analytical mismatch")
        if narrative.get("fact_bundle_identity") != fact_bundle.get(
            "fact_bundle_identity"
        ):
            raise StreamReadModelError("Stream detail narrative/fact mismatch")
        if analytical.get("fact_bundle_identity") != fact_bundle.get(
            "fact_bundle_identity"
        ):
            raise StreamReadModelError("Stream detail analytical/fact mismatch")

        for key in (
            "story_identity",
            "source_event_identity",
            "stream_event_identity",
            "symbol",
            "timeframe",
            "event_at_ms",
        ):
            expected = narrative.get(key)
            if analytical.get(key) != expected or fact_bundle.get(key) != expected:
                raise StreamReadModelError(
                    f"Stream detail lineage mismatch for {key}"
                )

        source_message_identity = analytical.get("source_message_identity")
        if source_message_identity is None:
            if message_input is not None:
                raise StreamReadModelError(
                    "Stream detail unexpected message-input projection"
                )
            return
        if message_input is None:
            raise StreamReadModelError("Stream detail missing source message input")
        if message_input.get("message_identity") != source_message_identity:
            raise StreamReadModelError("Stream detail analytical/message mismatch")
        if message_input.get("fact_bundle_identity") != fact_bundle.get(
            "fact_bundle_identity"
        ):
            raise StreamReadModelError("Stream detail message/fact mismatch")
        for key in (
            "story_identity",
            "source_event_identity",
            "stream_event_identity",
            "symbol",
            "timeframe",
            "event_at_ms",
        ):
            if message_input.get(key) != narrative.get(key):
                raise StreamReadModelError(
                    f"Stream detail message lineage mismatch for {key}"
                )

    @staticmethod
    def _verified_capital_sizing_record(
        *,
        narrative_identity: str,
        event_at_ms: int,
        payload_json: str,
        expected_digest: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamReadModelError(
                "Stream read capital-sizing payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamReadModelError(
                "Stream read capital-sizing payload must decode to object"
            )
        if raw.get("narrative_identity") != narrative_identity:
            raise StreamReadModelError(
                "Stream read capital-sizing identity column mismatch"
            )
        if raw.get("event_at_ms") != event_at_ms:
            raise StreamReadModelError(
                "Stream read capital-sizing event-time column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop("narrative_identity", None)
        if canonical_sha256(identity_payload) != narrative_identity:
            raise StreamReadModelError(
                "Stream read capital-sizing canonical identity mismatch"
            )
        if raw.get("schema_version") != STREAM_CAPITAL_SIZING_MESSAGE_SCHEMA_VERSION:
            raise StreamReadModelError("Stream read capital-sizing schema mismatch")
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamReadModelError("Stream read capital-sizing engine mismatch")
        if raw.get("read_only") is not True:
            raise StreamReadModelError("Stream read capital-sizing read-only mismatch")
        if raw.get("production_authority") is not False:
            raise StreamReadModelError(
                "Stream read capital-sizing production-authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamReadModelError(
                "Stream read capital-sizing REAL_CAPITAL mismatch"
            )
        return raw

    @staticmethod
    def _verified_capital_decision_record(
        *,
        narrative_identity: str,
        event_at_ms: int,
        payload_json: str,
        expected_digest: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamReadModelError(
                "Stream read capital-decision payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamReadModelError(
                "Stream read capital-decision payload must decode to object"
            )
        if raw.get("narrative_identity") != narrative_identity:
            raise StreamReadModelError(
                "Stream read capital-decision identity column mismatch"
            )
        if raw.get("event_at_ms") != event_at_ms:
            raise StreamReadModelError(
                "Stream read capital-decision event-time column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop("narrative_identity", None)
        if canonical_sha256(identity_payload) != narrative_identity:
            raise StreamReadModelError(
                "Stream read capital-decision canonical identity mismatch"
            )
        if (
            raw.get("schema_version")
            != STREAM_CAPITAL_DECISION_MESSAGE_SCHEMA_VERSION
        ):
            raise StreamReadModelError(
                "Stream read capital-decision schema mismatch"
            )
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamReadModelError(
                "Stream read capital-decision engine mismatch"
            )
        if raw.get("read_only") is not True:
            raise StreamReadModelError(
                "Stream read capital-decision read-only mismatch"
            )
        if raw.get("production_authority") is not False:
            raise StreamReadModelError(
                "Stream read capital-decision production-authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamReadModelError(
                "Stream read capital-decision REAL_CAPITAL mismatch"
            )
        return raw

    @staticmethod
    def _verified_capital_record(
        *,
        narrative_identity: str,
        event_at_ms: int,
        payload_json: str,
        expected_digest: str,
    ) -> dict[str, Any]:
        if sha256_text(payload_json) != expected_digest:
            raise StreamReadModelError(
                "Stream read capital payload digest mismatch"
            )
        raw = json.loads(payload_json)
        if not isinstance(raw, dict):
            raise StreamReadModelError(
                "Stream read capital payload must decode to object"
            )
        if raw.get("narrative_identity") != narrative_identity:
            raise StreamReadModelError(
                "Stream read capital identity column mismatch"
            )
        if raw.get("event_at_ms") != event_at_ms:
            raise StreamReadModelError(
                "Stream read capital event-time column mismatch"
            )
        identity_payload = dict(raw)
        identity_payload.pop("narrative_identity", None)
        if canonical_sha256(identity_payload) != narrative_identity:
            raise StreamReadModelError(
                "Stream read capital canonical identity mismatch"
            )
        if raw.get("schema_version") != STREAM_CAPITAL_MESSAGE_SCHEMA_VERSION:
            raise StreamReadModelError("Stream read capital schema mismatch")
        if raw.get("engine_version") != STREAM_ENGINE_VERSION:
            raise StreamReadModelError("Stream read capital engine mismatch")
        if raw.get("read_only") is not True:
            raise StreamReadModelError("Stream read capital read-only mismatch")
        if raw.get("production_authority") is not False:
            raise StreamReadModelError(
                "Stream read capital production-authority mismatch"
            )
        if raw.get("real_capital") != REAL_CAPITAL:
            raise StreamReadModelError("Stream read capital REAL_CAPITAL mismatch")
        return raw

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
