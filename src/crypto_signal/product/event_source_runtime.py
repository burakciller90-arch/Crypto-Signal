"""Read-only Product Truth for persisted Event Source runtime evidence."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EVENT_SOURCE_SCHEMA = "event-source-runtime-v1/2"
_MAX_PRODUCT_DB_BYTES = 128 * 1024 * 1024
_REQUIRED_TABLES = frozenset(
    {
        "event_source_runtime_meta",
        "event_source_raw_payloads",
        "event_calendar_coverages",
        "structured_event_observations",
        "news_event_observations",
        "event_source_fetches",
    }
)
_ACCEPTED_TIMESTAMP_BASES = frozenset(
    {"http_last_modified", "http_date", "fetch_time_fallback"}
)
_REQUIRED_FETCH_COLUMNS = frozenset(
    {
        "sequence_id",
        "fetch_identity",
        "source_provider",
        "source_kind",
        "fetched_at_ms",
        "outcome",
        "payload_json",
    }
)

_STRUCTURED_EVENT_SCHEMA = "structured-event-v1/1"
_EVENT_CALENDAR_COVERAGE_SCHEMA = "event-calendar-coverage-v1/1"
_EVENT_CATEGORIES = frozenset(
    {
        "inflation",
        "central_bank",
        "employment",
        "regulatory",
        "exchange_security",
        "listing",
        "delisting",
        "other",
    }
)
_EVENT_SOURCE_QUALITIES = frozenset(
    {
        "official",
        "primary_provider",
        "secondary_aggregator",
        "unverified",
    }
)
_MAX_EVENT_RAIL_LIMIT = 200


@dataclass(frozen=True, slots=True)
class EventSourceProviderRuntimeTruth:
    fetch_identity: str
    source_provider: str
    source_kind: str
    fetched_at_ms: int
    fetch_age_ms: int
    source_timestamp_ms: int | None
    source_timestamp_basis: str | None
    http_status: int | None
    outcome: str
    raw_payload_sha256: str | None
    raw_payload_bytes: int | None
    item_count: int
    item_categories: tuple[str, ...]
    coverage_identity: str | None
    coverage_categories: tuple[str, ...]
    reason_code: str | None
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.fetch_identity, "event source fetch identity")
        if not self.source_provider.strip():
            raise ValueError("event source provider missing")
        if self.source_kind not in {"calendar", "news"}:
            raise ValueError("event source kind invalid")
        if self.fetched_at_ms < 0 or self.fetch_age_ms < 0:
            raise ValueError("event source fetch time invalid")
        if self.source_timestamp_ms is not None:
            if self.source_timestamp_ms < 0:
                raise ValueError("event source timestamp invalid")
            if self.source_timestamp_ms > self.fetched_at_ms:
                raise ValueError("event source timestamp cannot postdate fetch")
        if (self.source_timestamp_ms is None) != (
            self.source_timestamp_basis is None
        ):
            raise ValueError("event source timestamp basis mismatch")
        if (
            self.source_timestamp_basis is not None
            and self.source_timestamp_basis not in _ACCEPTED_TIMESTAMP_BASES
        ):
            raise ValueError("event source timestamp basis invalid")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("event source HTTP status invalid")
        if self.outcome not in {"success", "failure"}:
            raise ValueError("event source outcome invalid")
        if (self.raw_payload_sha256 is None) != (
            self.raw_payload_bytes is None
        ):
            raise ValueError("event source raw payload evidence mismatch")
        if self.raw_payload_sha256 is not None:
            _require_sha256(
                self.raw_payload_sha256,
                "event source raw payload identity",
            )
        if self.raw_payload_bytes is not None and self.raw_payload_bytes <= 0:
            raise ValueError("event source raw payload bytes invalid")
        if self.item_count < 0:
            raise ValueError("event source item count invalid")
        if self.item_categories != tuple(sorted(set(self.item_categories))):
            raise ValueError("event source item categories must be canonical")
        if self.coverage_categories != tuple(
            sorted(set(self.coverage_categories))
        ):
            raise ValueError("event source coverage categories must be canonical")
        if self.coverage_identity is not None:
            _require_sha256(
                self.coverage_identity,
                "event source coverage identity",
            )
        if not self.adapter_version.strip():
            raise ValueError("event source adapter version missing")
        if self.outcome == "success":
            if self.http_status != 200:
                raise ValueError("event source success requires HTTP 200")
            if self.raw_payload_sha256 is None:
                raise ValueError("event source success requires raw payload")
            if self.item_count <= 0:
                raise ValueError("event source success requires items")
            if self.reason_code is not None:
                raise ValueError("event source success cannot carry failure reason")
            if self.source_kind == "calendar":
                if self.coverage_identity is None:
                    raise ValueError("calendar success requires coverage")
                if not self.coverage_categories:
                    raise ValueError("calendar coverage categories missing")
            elif self.coverage_identity is not None:
                raise ValueError("news success cannot carry calendar coverage")
        elif self.reason_code is None or not self.reason_code.strip():
            raise ValueError("event source failure requires reason code")


@dataclass(frozen=True, slots=True)
class EventSourceRuntimeTruth:
    schema_version: str
    raw_payload_count: int
    calendar_coverage_count: int
    structured_event_count: int
    news_event_count: int
    fetch_count: int
    latest_successful_fetch_at_ms: int | None
    latest_successful_fetch_age_ms: int | None
    latest_fetches: tuple[EventSourceProviderRuntimeTruth, ...]
    runtime_status: str = "PERSISTED_EVIDENCE_ONLY"
    online_status: str = "NOT_ASSERTED"
    process_status: str = "NOT_MEASURED"
    coverage_claim: str = "SOURCE_SCOPED_ONLY"
    read_only_verified: bool = True
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != _EVENT_SOURCE_SCHEMA:
            raise ValueError("event source Product schema mismatch")
        counts = (
            self.raw_payload_count,
            self.calendar_coverage_count,
            self.structured_event_count,
            self.news_event_count,
            self.fetch_count,
        )
        if min(counts) < 0:
            raise ValueError("event source Product counts cannot be negative")
        if (self.latest_successful_fetch_at_ms is None) != (
            self.latest_successful_fetch_age_ms is None
        ):
            raise ValueError("event source latest success age mismatch")
        if (
            self.latest_successful_fetch_age_ms is not None
            and self.latest_successful_fetch_age_ms < 0
        ):
            raise ValueError("event source latest success age invalid")
        if self.runtime_status != "PERSISTED_EVIDENCE_ONLY":
            raise ValueError("event source runtime status invalid")
        if self.online_status != "NOT_ASSERTED":
            raise ValueError("event source Product Truth cannot assert ONLINE")
        if self.process_status != "NOT_MEASURED":
            raise ValueError("event source process status is not measured")
        if self.coverage_claim != "SOURCE_SCOPED_ONLY":
            raise ValueError("event source coverage claim invalid")
        if not self.read_only_verified:
            raise ValueError("event source Product Truth must be read-only")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("event source Product Truth cannot grant authority")


@dataclass(frozen=True, slots=True)
class EventSourceCalendarCoverageTruth:
    coverage_identity: str
    source_provider: str
    coverage_start_ms: int
    coverage_end_ms: int
    categories: tuple[str, ...]
    source_quality: str
    source: str
    observed_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.coverage_identity, "calendar coverage identity")
        if not self.source_provider.strip() or not self.adapter_version.strip():
            raise ValueError("calendar coverage provider/adapter missing")
        if min(
            self.coverage_start_ms,
            self.coverage_end_ms,
            self.observed_at_ms,
        ) < 0:
            raise ValueError("calendar coverage time invalid")
        if self.coverage_end_ms < self.coverage_start_ms:
            raise ValueError("calendar coverage window invalid")
        if self.categories != tuple(sorted(set(self.categories))):
            raise ValueError("calendar coverage categories not canonical")
        if not self.categories or not set(self.categories).issubset(
            _EVENT_CATEGORIES
        ):
            raise ValueError("calendar coverage categories invalid")
        if self.source_quality not in _EVENT_SOURCE_QUALITIES:
            raise ValueError("calendar coverage source quality invalid")
        if not self.source.strip():
            raise ValueError("calendar coverage source missing")


@dataclass(frozen=True, slots=True)
class EventSourceCalendarEventTruth:
    event_identity: str
    provider_event_id: str
    title: str
    category: str
    scheduled_at_ms: int
    affected_assets: tuple[str, ...]
    source_provider: str
    source_quality: str
    source: str
    source_timestamp_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "calendar event identity")
        for value, label in (
            (self.provider_event_id, "calendar provider event id"),
            (self.title, "calendar event title"),
            (self.source_provider, "calendar event provider"),
            (self.source, "calendar event source"),
            (self.adapter_version, "calendar event adapter"),
        ):
            if not value.strip():
                raise ValueError(f"{label} missing")
        if self.category not in _EVENT_CATEGORIES:
            raise ValueError("calendar event category invalid")
        if self.source_quality not in _EVENT_SOURCE_QUALITIES:
            raise ValueError("calendar event source quality invalid")
        if min(
            self.scheduled_at_ms,
            self.source_timestamp_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("calendar event time invalid")
        if self.ingested_at_ms < self.source_timestamp_ms:
            raise ValueError("calendar event ingestion precedes source")
        if self.affected_assets != tuple(sorted(set(self.affected_assets))):
            raise ValueError("calendar event assets not canonical")
        if any(not value or value != value.upper() for value in self.affected_assets):
            raise ValueError("calendar event asset invalid")


@dataclass(frozen=True, slots=True)
class EventSourceCalendarRailTruth:
    observed_at_ms: int
    window_start_ms: int
    window_end_ms: int
    asset: str | None
    categories: tuple[str, ...]
    events: tuple[EventSourceCalendarEventTruth, ...]
    total_matching_events: int
    coverages: tuple[EventSourceCalendarCoverageTruth, ...]
    coverage_status: str
    latest_calendar_fetches: tuple[EventSourceProviderRuntimeTruth, ...]
    read_only_verified: bool = True
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if min(
            self.observed_at_ms,
            self.window_start_ms,
            self.window_end_ms,
        ) < 0:
            raise ValueError("calendar rail time invalid")
        if self.window_end_ms < self.window_start_ms:
            raise ValueError("calendar rail window invalid")
        if self.asset is not None and (
            not self.asset or self.asset != self.asset.upper()
        ):
            raise ValueError("calendar rail asset invalid")
        if self.categories != tuple(sorted(set(self.categories))):
            raise ValueError("calendar rail categories not canonical")
        if not set(self.categories).issubset(_EVENT_CATEGORIES):
            raise ValueError("calendar rail category invalid")
        if self.total_matching_events < len(self.events):
            raise ValueError("calendar rail total count invalid")
        if self.coverage_status not in {
            "COMPLETE",
            "INCOMPLETE",
            "UNAVAILABLE",
            "SOURCE_SCOPED_ONLY",
        }:
            raise ValueError("calendar rail coverage status invalid")
        event_keys = tuple(
            (item.scheduled_at_ms, item.event_identity) for item in self.events
        )
        if event_keys != tuple(sorted(event_keys)):
            raise ValueError("calendar rail events not canonical")
        if not self.read_only_verified:
            raise ValueError("calendar rail must be read-only verified")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("calendar rail cannot grant authority")


def read_event_source_runtime_truth(
    path: Path,
    *,
    observed_at_ms: int,
) -> EventSourceRuntimeTruth:
    if observed_at_ms < 0:
        raise ValueError("event source observation time cannot be negative")
    if not path.is_file():
        raise ValueError("event source runtime database missing")

    wal_path = Path(f"{path}-wal")
    if wal_path.exists() and wal_path.stat().st_size > 0:
        raise ValueError(
            "event source runtime has uncheckpointed WAL evidence"
        )

    database_bytes = _detached_sqlite_bytes(path)

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(database_bytes)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("event source SQLite quick_check failed")
        _verify_schema(connection)

        counts = {
            "raw_payloads": _count(connection, "event_source_raw_payloads"),
            "calendar_coverages": _count(
                connection,
                "event_calendar_coverages",
            ),
            "structured_events": _count(
                connection,
                "structured_event_observations",
            ),
            "news_events": _count(
                connection,
                "news_event_observations",
            ),
            "fetches": _count(connection, "event_source_fetches"),
        }
        rows = connection.execute(
            """
            SELECT
                f.sequence_id,
                f.fetch_identity,
                f.source_provider,
                f.source_kind,
                f.fetched_at_ms,
                f.outcome,
                f.payload_json
            FROM event_source_fetches AS f
            WHERE f.fetched_at_ms <= ?
              AND f.sequence_id = (
                SELECT candidate.sequence_id
                FROM event_source_fetches AS candidate
                WHERE candidate.source_provider = f.source_provider
                  AND candidate.source_kind = f.source_kind
                  AND candidate.fetched_at_ms <= ?
                ORDER BY
                    candidate.fetched_at_ms DESC,
                    candidate.sequence_id DESC
                LIMIT 1
              )
            ORDER BY f.source_provider, f.source_kind
            """,
            (observed_at_ms, observed_at_ms),
        ).fetchall()
        latest_fetches = tuple(
            _provider_truth_from_row(
                connection,
                row,
                observed_at_ms=observed_at_ms,
            )
            for row in rows
        )
        latest_success_row = connection.execute(
            """
            SELECT MAX(fetched_at_ms)
            FROM event_source_fetches
            WHERE outcome='success'
              AND fetched_at_ms <= ?
            """,
            (observed_at_ms,),
        ).fetchone()

    latest_success = (
        None
        if latest_success_row is None or latest_success_row[0] is None
        else int(latest_success_row[0])
    )
    if latest_success is not None and latest_success > observed_at_ms:
        raise ValueError("event source contains future successful fetch")

    return EventSourceRuntimeTruth(
        schema_version=_EVENT_SOURCE_SCHEMA,
        raw_payload_count=counts["raw_payloads"],
        calendar_coverage_count=counts["calendar_coverages"],
        structured_event_count=counts["structured_events"],
        news_event_count=counts["news_events"],
        fetch_count=counts["fetches"],
        latest_successful_fetch_at_ms=latest_success,
        latest_successful_fetch_age_ms=(
            None
            if latest_success is None
            else observed_at_ms - latest_success
        ),
        latest_fetches=latest_fetches,
    )


def read_event_source_calendar_rail(
    path: Path,
    *,
    observed_at_ms: int,
    window_start_ms: int,
    window_end_ms: int,
    asset: str | None = None,
    categories: tuple[str, ...] = (),
    limit: int = 50,
) -> EventSourceCalendarRailTruth:
    if min(observed_at_ms, window_start_ms, window_end_ms) < 0:
        raise ValueError("event rail times cannot be negative")
    if window_end_ms < window_start_ms:
        raise ValueError("event rail window end precedes start")
    if limit < 1 or limit > _MAX_EVENT_RAIL_LIMIT:
        raise ValueError(
            f"event rail limit must be inside 1..{_MAX_EVENT_RAIL_LIMIT}"
        )
    normalized_asset = None if asset is None else asset.strip().upper()
    if normalized_asset == "":
        raise ValueError("event rail asset cannot be blank")
    normalized_categories = tuple(
        sorted({value.strip().lower() for value in categories})
    )
    if any(not value for value in normalized_categories):
        raise ValueError("event rail category cannot be blank")
    if not set(normalized_categories).issubset(_EVENT_CATEGORIES):
        raise ValueError("event rail category invalid")
    if not path.is_file():
        raise ValueError("event source runtime database missing")

    wal_path = Path(f"{path}-wal")
    if wal_path.exists() and wal_path.stat().st_size > 0:
        raise ValueError(
            "event source runtime has uncheckpointed WAL evidence"
        )
    database_bytes = _detached_sqlite_bytes(path)

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(database_bytes)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("event source SQLite quick_check failed")
        _verify_schema(connection)

        successful_rows = connection.execute(
            """
            SELECT
                sequence_id,
                fetch_identity,
                source_provider,
                source_kind,
                fetched_at_ms,
                outcome,
                payload_json
            FROM event_source_fetches
            WHERE source_kind='calendar'
              AND outcome='success'
              AND fetched_at_ms <= ?
            ORDER BY fetched_at_ms, sequence_id
            """,
            (observed_at_ms,),
        ).fetchall()
        trusted_event_ids: set[str] = set()
        for row in successful_rows:
            _provider_truth_from_row(
                connection,
                row,
                observed_at_ms=observed_at_ms,
            )
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise TypeError("event source fetch payload must be object")
            trusted_event_ids.update(
                _identity_list(payload.get("item_identities"))
            )

        latest_rows = connection.execute(
            """
            SELECT
                f.sequence_id,
                f.fetch_identity,
                f.source_provider,
                f.source_kind,
                f.fetched_at_ms,
                f.outcome,
                f.payload_json
            FROM event_source_fetches AS f
            WHERE f.source_kind='calendar'
              AND f.fetched_at_ms <= ?
              AND f.sequence_id = (
                SELECT candidate.sequence_id
                FROM event_source_fetches AS candidate
                WHERE candidate.source_provider = f.source_provider
                  AND candidate.source_kind='calendar'
                  AND candidate.fetched_at_ms <= ?
                ORDER BY
                    candidate.fetched_at_ms DESC,
                    candidate.sequence_id DESC
                LIMIT 1
              )
            ORDER BY f.source_provider
            """,
            (observed_at_ms, observed_at_ms),
        ).fetchall()
        latest_fetches = tuple(
            _provider_truth_from_row(
                connection,
                row,
                observed_at_ms=observed_at_ms,
            )
            for row in latest_rows
        )

        coverage_truths: list[EventSourceCalendarCoverageTruth] = []
        for row, fetch_truth in zip(latest_rows, latest_fetches, strict=True):
            if fetch_truth.outcome != "success":
                continue
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise TypeError("event source fetch payload must be object")
            coverage_identity = _optional_text(payload.get("coverage_identity"))
            if coverage_identity is None:
                raise ValueError("calendar fetch coverage identity missing")
            coverage_truths.append(
                _calendar_coverage_truth(
                    connection,
                    coverage_identity=coverage_identity,
                    source_provider=fetch_truth.source_provider,
                    observed_at_ms=observed_at_ms,
                )
            )

        event_rows = connection.execute(
            """
            SELECT
                event_identity,
                provider_event_id,
                source_provider,
                scheduled_at_ms,
                ingested_at_ms,
                payload_json
            FROM structured_event_observations
            WHERE scheduled_at_ms >= ?
              AND scheduled_at_ms <= ?
              AND ingested_at_ms <= ?
            ORDER BY scheduled_at_ms, event_identity
            """,
            (window_start_ms, window_end_ms, observed_at_ms),
        ).fetchall()
        matched: list[EventSourceCalendarEventTruth] = []
        for row in event_rows:
            identity = str(row["event_identity"])
            if identity not in trusted_event_ids:
                continue
            event = _calendar_event_truth(
                row,
                observed_at_ms=observed_at_ms,
            )
            if normalized_categories and event.category not in normalized_categories:
                continue
            if (
                normalized_asset is not None
                and event.affected_assets
                and normalized_asset not in event.affected_assets
            ):
                continue
            matched.append(event)

    ordered = tuple(
        sorted(
            matched,
            key=lambda item: (item.scheduled_at_ms, item.event_identity),
        )
    )
    coverage_tuple = tuple(
        sorted(
            coverage_truths,
            key=lambda item: (
                item.source_provider,
                item.coverage_start_ms,
                item.coverage_end_ms,
                item.coverage_identity,
            ),
        )
    )
    return EventSourceCalendarRailTruth(
        observed_at_ms=observed_at_ms,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        asset=normalized_asset,
        categories=normalized_categories,
        events=ordered[:limit],
        total_matching_events=len(ordered),
        coverages=coverage_tuple,
        coverage_status=_calendar_coverage_status(
            coverage_tuple,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            categories=normalized_categories,
        ),
        latest_calendar_fetches=latest_fetches,
    )


def _detached_sqlite_bytes(path: Path) -> bytes:
    database_bytes = path.read_bytes()
    if not database_bytes:
        raise ValueError("event source runtime database is empty")
    if len(database_bytes) > _MAX_PRODUCT_DB_BYTES:
        raise ValueError(
            "event source runtime database exceeds Product read bound"
        )
    if len(database_bytes) < 100 or not database_bytes.startswith(
        b"SQLite format 3\x00"
    ):
        raise ValueError("event source runtime SQLite header invalid")

    detached = bytearray(database_bytes)
    write_version = detached[18]
    read_version = detached[19]
    if write_version != read_version or write_version not in {1, 2}:
        raise ValueError("event source runtime SQLite format version invalid")
    if write_version == 2:
        detached[18] = 1
        detached[19] = 1
    return bytes(detached)


def _verify_schema(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            """SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
        ).fetchall()
    }
    if not _REQUIRED_TABLES.issubset(tables):
        raise ValueError("event source required table missing")

    fetch_columns = {
        str(row[1])
        for row in connection.execute(
            "PRAGMA table_info(event_source_fetches)"
        ).fetchall()
    }
    missing = _REQUIRED_FETCH_COLUMNS - fetch_columns
    if missing:
        raise ValueError(
            "event source fetch columns missing: "
            + ",".join(sorted(missing))
        )

    schema_row = connection.execute(
        """SELECT value FROM event_source_runtime_meta
        WHERE key='schema_version'"""
    ).fetchone()
    if schema_row is None or str(schema_row[0]) != _EVENT_SOURCE_SCHEMA:
        raise ValueError("event source schema version mismatch")


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise ValueError(f"event source count unavailable: {table}")
    return int(row[0])


def _provider_truth_from_row(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    observed_at_ms: int,
) -> EventSourceProviderRuntimeTruth:
    fetch_identity = str(row["fetch_identity"])
    payload_json = str(row["payload_json"])
    _verify_payload_identity(fetch_identity, payload_json, "event source fetch")
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("event source fetch payload must be object")

    for key in ("source_provider", "source_kind", "outcome"):
        if str(payload.get(key)) != str(row[key]):
            raise ValueError(f"event source row/payload mismatch: {key}")
    fetched_at_ms = int(payload["fetched_at_ms"])
    if fetched_at_ms != int(row["fetched_at_ms"]):
        raise ValueError("event source row/payload fetch time mismatch")
    if fetched_at_ms > observed_at_ms:
        raise ValueError("event source contains future fetch evidence")
    if str(payload.get("schema_version")) != _EVENT_SOURCE_SCHEMA:
        raise ValueError("event source fetch schema mismatch")
    if bool(payload.get("production_authority")):
        raise ValueError("event source fetch grants production authority")
    if int(payload.get("real_capital", -1)) != 0:
        raise ValueError("event source fetch real capital mismatch")

    item_identities = _identity_list(payload.get("item_identities"))
    raw_sha = _optional_text(payload.get("raw_payload_sha256"))
    raw_bytes = _optional_int(payload.get("raw_payload_bytes"))
    if raw_sha is not None:
        _verify_raw_payload(
            connection,
            payload_sha256=raw_sha,
            expected_bytes=raw_bytes,
        )

    source_kind = str(payload["source_kind"])
    outcome = str(payload["outcome"])
    coverage_identity = _optional_text(payload.get("coverage_identity"))
    item_categories: tuple[str, ...] = ()
    coverage_categories: tuple[str, ...] = ()
    if outcome == "success":
        if source_kind == "calendar":
            if coverage_identity is None:
                raise ValueError("calendar fetch coverage identity missing")
            coverage_categories = _verify_coverage(
                connection,
                coverage_identity=coverage_identity,
                source_provider=str(payload["source_provider"]),
            )
            item_categories = _verify_items(
                connection,
                table="structured_event_observations",
                identity_column="event_identity",
                identities=item_identities,
                source_provider=str(payload["source_provider"]),
            )
        elif source_kind == "news":
            if coverage_identity is not None:
                raise ValueError("news fetch cannot carry calendar coverage")
            item_categories = _verify_items(
                connection,
                table="news_event_observations",
                identity_column="news_identity",
                identities=item_identities,
                source_provider=str(payload["source_provider"]),
            )
        else:
            raise ValueError("event source kind invalid")

    return EventSourceProviderRuntimeTruth(
        fetch_identity=fetch_identity,
        source_provider=str(payload["source_provider"]),
        source_kind=source_kind,
        fetched_at_ms=fetched_at_ms,
        fetch_age_ms=observed_at_ms - fetched_at_ms,
        source_timestamp_ms=_optional_int(
            payload.get("source_timestamp_ms")
        ),
        source_timestamp_basis=_optional_text(
            payload.get("source_timestamp_basis")
        ),
        http_status=_optional_int(payload.get("http_status")),
        outcome=outcome,
        raw_payload_sha256=raw_sha,
        raw_payload_bytes=raw_bytes,
        item_count=len(item_identities),
        item_categories=item_categories,
        coverage_identity=coverage_identity,
        coverage_categories=coverage_categories,
        reason_code=_optional_text(payload.get("reason_code")),
        adapter_version=str(payload["adapter_version"]),
    )


def _calendar_coverage_truth(
    connection: sqlite3.Connection,
    *,
    coverage_identity: str,
    source_provider: str,
    observed_at_ms: int,
) -> EventSourceCalendarCoverageTruth:
    _require_sha256(coverage_identity, "calendar coverage identity")
    row = connection.execute(
        """
        SELECT source_provider, observed_at_ms, payload_json
        FROM event_calendar_coverages
        WHERE coverage_identity=?
        """,
        (coverage_identity,),
    ).fetchone()
    if row is None:
        raise ValueError("event source calendar coverage missing")
    if str(row["source_provider"]) != source_provider:
        raise ValueError("event source calendar coverage provider mismatch")
    payload_json = str(row["payload_json"])
    _verify_payload_identity(
        coverage_identity,
        payload_json,
        "event source calendar coverage",
    )
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("event source coverage payload must be object")
    if str(payload.get("schema_version")) != _EVENT_CALENDAR_COVERAGE_SCHEMA:
        raise ValueError("event source calendar coverage schema mismatch")
    if str(payload.get("source_provider")) != source_provider:
        raise ValueError("event source calendar coverage payload provider mismatch")
    payload_observed = int(payload.get("observed_at_ms", -1))
    if payload_observed != int(row["observed_at_ms"]):
        raise ValueError("event source calendar coverage observed-time mismatch")
    if payload_observed > observed_at_ms:
        raise ValueError("event source contains future calendar coverage")
    categories_raw = payload.get("categories")
    if not isinstance(categories_raw, list):
        raise TypeError("event source coverage categories must be array")
    categories = tuple(str(value) for value in categories_raw)
    if categories != tuple(sorted(set(categories))):
        raise ValueError("event source coverage categories not canonical")
    return EventSourceCalendarCoverageTruth(
        coverage_identity=coverage_identity,
        source_provider=source_provider,
        coverage_start_ms=int(payload.get("coverage_start_ms", -1)),
        coverage_end_ms=int(payload.get("coverage_end_ms", -1)),
        categories=categories,
        source_quality=str(payload.get("source_quality", "")),
        source=str(payload.get("source", "")),
        observed_at_ms=payload_observed,
        adapter_version=str(payload.get("adapter_version", "")),
    )


def _calendar_event_truth(
    row: sqlite3.Row,
    *,
    observed_at_ms: int,
) -> EventSourceCalendarEventTruth:
    identity = str(row["event_identity"])
    payload_json = str(row["payload_json"])
    _verify_payload_identity(identity, payload_json, "event source calendar event")
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("event source calendar event payload must be object")
    if str(payload.get("schema_version")) != _STRUCTURED_EVENT_SCHEMA:
        raise ValueError("event source calendar event schema mismatch")
    row_pairs = (
        ("provider_event_id", str(row["provider_event_id"])),
        ("source_provider", str(row["source_provider"])),
        ("scheduled_at_ms", int(row["scheduled_at_ms"])),
        ("ingested_at_ms", int(row["ingested_at_ms"])),
    )
    for key, expected in row_pairs:
        actual = payload.get(key)
        if isinstance(expected, int):
            if _required_non_negative_int(actual, key) != expected:
                raise ValueError(f"event source calendar event row mismatch: {key}")
        elif str(actual) != expected:
            raise ValueError(f"event source calendar event row mismatch: {key}")

    source_timestamp_ms = int(payload.get("source_timestamp_ms", -1))
    ingested_at_ms = int(payload.get("ingested_at_ms", -1))
    if ingested_at_ms > observed_at_ms:
        raise ValueError("event source contains future-ingested calendar event")
    assets_raw = payload.get("affected_assets")
    if not isinstance(assets_raw, list):
        raise TypeError("event source calendar event assets must be array")
    assets = tuple(str(value) for value in assets_raw)
    if assets != tuple(sorted(set(assets))):
        raise ValueError("event source calendar event assets not canonical")
    return EventSourceCalendarEventTruth(
        event_identity=identity,
        provider_event_id=str(payload.get("provider_event_id", "")),
        title=str(payload.get("title", "")),
        category=str(payload.get("category", "")),
        scheduled_at_ms=int(payload.get("scheduled_at_ms", -1)),
        affected_assets=assets,
        source_provider=str(payload.get("source_provider", "")),
        source_quality=str(payload.get("source_quality", "")),
        source=str(payload.get("source", "")),
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=str(payload.get("adapter_version", "")),
    )


def _calendar_coverage_status(
    coverages: tuple[EventSourceCalendarCoverageTruth, ...],
    *,
    window_start_ms: int,
    window_end_ms: int,
    categories: tuple[str, ...],
) -> str:
    if not coverages:
        return "UNAVAILABLE"
    if not categories:
        return "SOURCE_SCOPED_ONLY"
    covered = {
        category
        for category in categories
        if any(
            item.coverage_start_ms <= window_start_ms
            and item.coverage_end_ms >= window_end_ms
            and category in item.categories
            for item in coverages
        )
    }
    return "COMPLETE" if covered == set(categories) else "INCOMPLETE"


def _verify_raw_payload(
    connection: sqlite3.Connection,
    *,
    payload_sha256: str,
    expected_bytes: int | None,
) -> None:
    _require_sha256(payload_sha256, "event source raw payload identity")
    if expected_bytes is None or expected_bytes <= 0:
        raise ValueError("event source raw payload byte count missing")
    row = connection.execute(
        """
        SELECT content_bytes, payload_blob
        FROM event_source_raw_payloads
        WHERE payload_sha256=?
        """,
        (payload_sha256,),
    ).fetchone()
    if row is None:
        raise ValueError("event source raw payload missing")
    payload_bytes = bytes(row["payload_blob"])
    if int(row["content_bytes"]) != expected_bytes:
        raise ValueError("event source raw payload byte mismatch")
    if len(payload_bytes) != expected_bytes:
        raise ValueError("event source raw payload stored size mismatch")
    if hashlib.sha256(payload_bytes).hexdigest() != payload_sha256:
        raise ValueError("event source raw payload hash mismatch")


def _verify_coverage(
    connection: sqlite3.Connection,
    *,
    coverage_identity: str,
    source_provider: str,
) -> tuple[str, ...]:
    _require_sha256(coverage_identity, "event source coverage identity")
    row = connection.execute(
        """
        SELECT source_provider, payload_json
        FROM event_calendar_coverages
        WHERE coverage_identity=?
        """,
        (coverage_identity,),
    ).fetchone()
    if row is None:
        raise ValueError("event source calendar coverage missing")
    if str(row["source_provider"]) != source_provider:
        raise ValueError("event source calendar coverage provider mismatch")
    payload_json = str(row["payload_json"])
    _verify_payload_identity(
        coverage_identity,
        payload_json,
        "event source calendar coverage",
    )
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("event source coverage payload must be object")
    if str(payload.get("source_provider")) != source_provider:
        raise ValueError("event source coverage payload provider mismatch")
    categories = payload.get("categories")
    if not isinstance(categories, list):
        raise TypeError("event source coverage categories must be array")
    result = tuple(sorted({str(value) for value in categories}))
    if not result:
        raise ValueError("event source coverage categories missing")
    return result


def _verify_items(
    connection: sqlite3.Connection,
    *,
    table: str,
    identity_column: str,
    identities: tuple[str, ...],
    source_provider: str,
) -> tuple[str, ...]:
    if not identities:
        raise ValueError("event source success item identities missing")
    categories: set[str] = set()
    for identity in identities:
        _require_sha256(identity, "event source item identity")
        row = connection.execute(
            f"""SELECT source_provider, payload_json
            FROM {table}
            WHERE {identity_column}=?""",
            (identity,),
        ).fetchone()
        if row is None:
            raise ValueError("event source normalized item missing")
        if str(row["source_provider"]) != source_provider:
            raise ValueError("event source normalized item provider mismatch")
        payload_json = str(row["payload_json"])
        _verify_payload_identity(identity, payload_json, "event source item")
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise TypeError("event source item payload must be object")
        if str(payload.get("source_provider")) != source_provider:
            raise ValueError("event source item payload provider mismatch")
        category = str(payload.get("category", "")).strip()
        if not category:
            raise ValueError("event source item category missing")
        categories.add(category)
    return tuple(sorted(categories))


def _verify_payload_identity(
    identity: str,
    payload_json: str,
    label: str,
) -> None:
    _require_sha256(identity, label)
    parsed = json.loads(payload_json)
    canonical = json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    if hashlib.sha256(canonical.encode()).hexdigest() != identity:
        raise ValueError(f"{label} identity mismatch")


def _identity_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError("event source item identities must be array")
    result = tuple(str(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise ValueError("event source item identities must be canonical")
    return result


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _required_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be a non-negative integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    else:
        raise TypeError(f"{label} must be a non-negative integer")
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
