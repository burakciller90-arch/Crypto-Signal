from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.event_risk import (
    EventCalendarCoverage,
    StructuredEventObservation,
    event_calendar_coverage_payload,
    structured_event_payload,
)
from crypto_signal.data.news_events import (
    NewsEventObservation,
    news_event_payload,
)
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

EVENT_SOURCE_RUNTIME_SCHEMA_VERSION = "event-source-runtime-v1/2"
MAX_EVENT_SOURCE_PAYLOAD_BYTES = 4 * 1024 * 1024
REAL_CAPITAL = 0


class EventSourceKind(StrEnum):
    CALENDAR = "calendar"
    NEWS = "news"


class EventSourceFetchOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class EventSourceTimestampBasis(StrEnum):
    HTTP_LAST_MODIFIED = "http_last_modified"
    HTTP_DATE = "http_date"
    FETCH_TIME_FALLBACK = "fetch_time_fallback"


@dataclass(frozen=True, slots=True)
class EventSourceRawPayload:
    payload_sha256: str
    content_bytes: int
    content_type: str
    text_encoding: str
    payload_bytes: bytes
    schema_version: str = EVENT_SOURCE_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.payload_sha256, "event source raw payload")
        if self.schema_version != EVENT_SOURCE_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported event-source runtime schema")
        if self.content_bytes <= 0:
            raise ValueError("event source raw payload must be non-empty")
        if self.content_bytes > MAX_EVENT_SOURCE_PAYLOAD_BYTES:
            raise ValueError("event source raw payload exceeds bounded size")
        if not self.content_type.strip():
            raise ValueError("event source raw payload content type is required")
        if not self.text_encoding.strip():
            raise ValueError("event source raw payload encoding is required")
        if len(self.payload_bytes) != self.content_bytes:
            raise ValueError("event source raw payload byte count mismatch")
        if hashlib.sha256(self.payload_bytes).hexdigest() != self.payload_sha256:
            raise ValueError("event source raw payload SHA256 mismatch")
        try:
            self.payload_bytes.decode(self.text_encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            raise ValueError("event source raw payload decoding failed") from exc


def build_event_source_raw_payload(
    *,
    payload_bytes: bytes,
    content_type: str,
    text_encoding: str,
) -> EventSourceRawPayload:
    return EventSourceRawPayload(
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        content_bytes=len(payload_bytes),
        content_type=content_type,
        text_encoding=text_encoding,
        payload_bytes=payload_bytes,
    )


@dataclass(frozen=True, slots=True)
class EventSourceFetchObservation:
    fetch_identity: str
    source_provider: str
    source_kind: EventSourceKind
    endpoint_url: str
    fetched_at_ms: int
    source_timestamp_ms: int | None
    source_timestamp_basis: EventSourceTimestampBasis | None
    http_status: int | None
    outcome: EventSourceFetchOutcome
    raw_payload_sha256: str | None
    raw_payload_bytes: int | None
    item_identities: tuple[str, ...]
    coverage_identity: str | None
    reason_code: str | None
    adapter_version: str
    schema_version: str = EVENT_SOURCE_RUNTIME_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.fetch_identity, "event source fetch identity")
        if self.schema_version != EVENT_SOURCE_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported event-source runtime schema")
        for value, label in (
            (self.source_provider, "source_provider"),
            (self.endpoint_url, "endpoint_url"),
            (self.adapter_version, "adapter_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.fetched_at_ms < 0:
            raise ValueError("event source fetched_at_ms cannot be negative")
        if self.source_timestamp_ms is not None:
            if self.source_timestamp_ms < 0:
                raise ValueError("event source timestamp cannot be negative")
            if self.source_timestamp_ms > self.fetched_at_ms:
                raise ValueError("event source timestamp cannot postdate fetch")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("event source HTTP status is invalid")
        if self.raw_payload_sha256 is not None:
            _require_sha256(
                self.raw_payload_sha256,
                "event source raw payload identity",
            )
        if self.raw_payload_bytes is not None and self.raw_payload_bytes <= 0:
            raise ValueError("event source raw payload bytes must be positive")
        if (self.source_timestamp_ms is None) != (
            self.source_timestamp_basis is None
        ):
            raise ValueError(
                "event source timestamp and timestamp basis must be paired"
            )
        if (self.raw_payload_sha256 is None) != (
            self.raw_payload_bytes is None
        ):
            raise ValueError(
                "event source raw payload identity and bytes must be paired"
            )
        if tuple(sorted(set(self.item_identities))) != self.item_identities:
            raise ValueError("event source item identities must be canonical")
        for identity in self.item_identities:
            _require_sha256(identity, "event source item identity")
        if self.coverage_identity is not None:
            _require_sha256(
                self.coverage_identity,
                "event source coverage identity",
            )

        if self.outcome is EventSourceFetchOutcome.SUCCESS:
            if self.http_status != 200:
                raise ValueError("successful event source fetch requires HTTP 200")
            if self.source_timestamp_ms is None:
                raise ValueError("successful event source fetch requires source timestamp")
            if self.source_timestamp_basis is None:
                raise ValueError(
                    "successful event source fetch requires timestamp basis"
                )
            if self.raw_payload_sha256 is None or self.raw_payload_bytes is None:
                raise ValueError(
                    "successful event source fetch requires exact raw payload"
                )
            if not self.item_identities:
                raise ValueError(
                    "successful event source fetch requires persisted items"
                )
            if self.reason_code is not None:
                raise ValueError("successful event source fetch cannot carry failure reason")
            if (
                self.source_kind is EventSourceKind.CALENDAR
                and self.coverage_identity is None
            ):
                raise ValueError("calendar fetch success requires coverage identity")
            if (
                self.source_kind is EventSourceKind.NEWS
                and self.coverage_identity is not None
            ):
                raise ValueError("news fetch cannot carry calendar coverage")
        else:
            if self.reason_code is None or not self.reason_code.strip():
                raise ValueError("failed event source fetch requires reason code")
            if self.item_identities or self.coverage_identity is not None:
                raise ValueError("failed event source fetch cannot claim persisted items")

        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("event source runtime cannot grant authority")
        if self.fetch_identity != canonical_sha256(_fetch_payload(self)):
            raise ValueError("event source fetch identity mismatch")


def build_event_source_fetch_observation(
    *,
    source_provider: str,
    source_kind: EventSourceKind,
    endpoint_url: str,
    fetched_at_ms: int,
    source_timestamp_ms: int | None,
    source_timestamp_basis: EventSourceTimestampBasis | None,
    http_status: int | None,
    outcome: EventSourceFetchOutcome,
    raw_payload_sha256: str | None = None,
    raw_payload_bytes: int | None = None,
    item_identities: tuple[str, ...] = (),
    coverage_identity: str | None = None,
    reason_code: str | None = None,
    adapter_version: str,
) -> EventSourceFetchObservation:
    identities = tuple(sorted(set(item_identities)))
    values = {
        "source_provider": source_provider,
        "source_kind": source_kind,
        "endpoint_url": endpoint_url,
        "fetched_at_ms": fetched_at_ms,
        "source_timestamp_ms": source_timestamp_ms,
        "source_timestamp_basis": source_timestamp_basis,
        "http_status": http_status,
        "outcome": outcome,
        "raw_payload_sha256": raw_payload_sha256,
        "raw_payload_bytes": raw_payload_bytes,
        "item_identities": identities,
        "coverage_identity": coverage_identity,
        "reason_code": reason_code,
        "adapter_version": adapter_version,
        "schema_version": EVENT_SOURCE_RUNTIME_SCHEMA_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return EventSourceFetchObservation(
        fetch_identity=canonical_sha256(values),
        source_provider=source_provider,
        source_kind=source_kind,
        endpoint_url=endpoint_url,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source_timestamp_basis=source_timestamp_basis,
        http_status=http_status,
        outcome=outcome,
        raw_payload_sha256=raw_payload_sha256,
        raw_payload_bytes=raw_payload_bytes,
        item_identities=identities,
        coverage_identity=coverage_identity,
        reason_code=reason_code,
        adapter_version=adapter_version,
        schema_version=EVENT_SOURCE_RUNTIME_SCHEMA_VERSION,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


class EventSourceRuntimeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS event_source_runtime_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_source_raw_payloads (
                    payload_sha256 TEXT PRIMARY KEY,
                    content_bytes INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    text_encoding TEXT NOT NULL,
                    payload_blob BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_calendar_coverages (
                    coverage_identity TEXT PRIMARY KEY,
                    source_provider TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS structured_event_observations (
                    event_identity TEXT PRIMARY KEY,
                    provider_event_id TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    scheduled_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_event_observations (
                    news_identity TEXT PRIMARY KEY,
                    provider_article_id TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    published_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_source_fetches (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fetch_identity TEXT UNIQUE NOT NULL,
                    source_provider TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    fetched_at_ms INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS event_calendar_provider_time
                    ON event_calendar_coverages(source_provider, observed_at_ms);
                CREATE INDEX IF NOT EXISTS structured_event_provider_time
                    ON structured_event_observations(
                        source_provider, scheduled_at_ms, ingested_at_ms
                    );
                CREATE INDEX IF NOT EXISTS news_event_provider_time
                    ON news_event_observations(
                        source_provider, published_at_ms, ingested_at_ms
                    );
                CREATE INDEX IF NOT EXISTS event_source_fetch_provider_time
                    ON event_source_fetches(
                        source_provider, source_kind, fetched_at_ms
                    );

                CREATE TRIGGER IF NOT EXISTS event_source_raw_payload_no_update
                BEFORE UPDATE ON event_source_raw_payloads
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS event_source_raw_payload_no_delete
                BEFORE DELETE ON event_source_raw_payloads
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS event_calendar_no_update
                BEFORE UPDATE ON event_calendar_coverages
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS event_calendar_no_delete
                BEFORE DELETE ON event_calendar_coverages
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS structured_event_no_update
                BEFORE UPDATE ON structured_event_observations
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS structured_event_no_delete
                BEFORE DELETE ON structured_event_observations
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS news_event_no_update
                BEFORE UPDATE ON news_event_observations
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS news_event_no_delete
                BEFORE DELETE ON news_event_observations
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS event_source_fetch_no_update
                BEFORE UPDATE ON event_source_fetches
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS event_source_fetch_no_delete
                BEFORE DELETE ON event_source_fetches
                BEGIN
                    SELECT RAISE(ABORT, 'event-source runtime is append-only');
                END;
                """
            )
            row = db.execute(
                "SELECT value FROM event_source_runtime_meta "
                "WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO event_source_runtime_meta(key, value) "
                    "VALUES (?, ?)",
                    ("schema_version", EVENT_SOURCE_RUNTIME_SCHEMA_VERSION),
                )
            elif str(row[0]) != EVENT_SOURCE_RUNTIME_SCHEMA_VERSION:
                raise ValueError("event-source runtime schema mismatch")

    def append_raw_payload(self, payload: EventSourceRawPayload) -> None:
        self.initialize()
        with sqlite3.connect(self.path) as db:
            self._append_raw_payload_db(db, payload)

    def append_calendar_coverage(self, coverage: EventCalendarCoverage) -> None:
        self._append_identity_payload(
            table="event_calendar_coverages",
            identity_column="coverage_identity",
            identity=coverage.coverage_identity,
            payload=event_calendar_coverage_payload(coverage),
            columns=(
                "coverage_identity",
                "source_provider",
                "observed_at_ms",
                "payload_json",
            ),
            values=(
                coverage.coverage_identity,
                coverage.source_provider,
                coverage.observed_at_ms,
            ),
        )

    def append_structured_event(self, event: StructuredEventObservation) -> None:
        self._append_identity_payload(
            table="structured_event_observations",
            identity_column="event_identity",
            identity=event.event_identity,
            payload=structured_event_payload(event),
            columns=(
                "event_identity",
                "provider_event_id",
                "source_provider",
                "scheduled_at_ms",
                "ingested_at_ms",
                "payload_json",
            ),
            values=(
                event.event_identity,
                event.provider_event_id,
                event.source_provider,
                event.scheduled_at_ms,
                event.ingested_at_ms,
            ),
        )

    def append_news_event(self, event: NewsEventObservation) -> None:
        self._append_identity_payload(
            table="news_event_observations",
            identity_column="news_identity",
            identity=event.news_identity,
            payload=news_event_payload(event),
            columns=(
                "news_identity",
                "provider_article_id",
                "source_provider",
                "published_at_ms",
                "ingested_at_ms",
                "payload_json",
            ),
            values=(
                event.news_identity,
                event.provider_article_id,
                event.source_provider,
                event.published_at_ms,
                event.ingested_at_ms,
            ),
        )

    def append_fetch(self, fetch: EventSourceFetchObservation) -> None:
        self.initialize()
        with sqlite3.connect(self.path) as db:
            self._validate_fetch_references_db(db, fetch)
            self._append_fetch_db(db, fetch)

    def append_calendar_snapshot(
        self,
        *,
        raw_payload: EventSourceRawPayload,
        coverage: EventCalendarCoverage,
        events: tuple[StructuredEventObservation, ...],
        fetch: EventSourceFetchObservation,
    ) -> None:
        if fetch.outcome is not EventSourceFetchOutcome.SUCCESS:
            raise ValueError("calendar snapshot requires successful fetch")
        if fetch.source_kind is not EventSourceKind.CALENDAR:
            raise ValueError("calendar snapshot fetch kind mismatch")
        if fetch.raw_payload_sha256 != raw_payload.payload_sha256:
            raise ValueError("calendar snapshot raw payload mismatch")
        if fetch.raw_payload_bytes != raw_payload.content_bytes:
            raise ValueError("calendar snapshot raw payload bytes mismatch")
        if fetch.coverage_identity != coverage.coverage_identity:
            raise ValueError("calendar snapshot coverage mismatch")
        event_identities = tuple(
            sorted(event.event_identity for event in events)
        )
        if not events or fetch.item_identities != event_identities:
            raise ValueError("calendar snapshot item identity mismatch")
        if coverage.source_provider != fetch.source_provider:
            raise ValueError("calendar snapshot provider mismatch")
        if any(
            event.source_provider != fetch.source_provider
            for event in events
        ):
            raise ValueError("calendar snapshot event provider mismatch")

        self.initialize()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            self._append_raw_payload_db(db, raw_payload)
            self._append_identity_payload_db(
                db,
                table="event_calendar_coverages",
                identity_column="coverage_identity",
                identity=coverage.coverage_identity,
                payload=event_calendar_coverage_payload(coverage),
                columns=(
                    "coverage_identity",
                    "source_provider",
                    "observed_at_ms",
                    "payload_json",
                ),
                values=(
                    coverage.coverage_identity,
                    coverage.source_provider,
                    coverage.observed_at_ms,
                ),
            )
            for event in events:
                self._append_identity_payload_db(
                    db,
                    table="structured_event_observations",
                    identity_column="event_identity",
                    identity=event.event_identity,
                    payload=structured_event_payload(event),
                    columns=(
                        "event_identity",
                        "provider_event_id",
                        "source_provider",
                        "scheduled_at_ms",
                        "ingested_at_ms",
                        "payload_json",
                    ),
                    values=(
                        event.event_identity,
                        event.provider_event_id,
                        event.source_provider,
                        event.scheduled_at_ms,
                        event.ingested_at_ms,
                    ),
                )
            self._validate_fetch_references_db(db, fetch)
            self._append_fetch_db(db, fetch)

    def append_news_snapshot(
        self,
        *,
        raw_payload: EventSourceRawPayload,
        events: tuple[NewsEventObservation, ...],
        fetch: EventSourceFetchObservation,
    ) -> None:
        if fetch.outcome is not EventSourceFetchOutcome.SUCCESS:
            raise ValueError("news snapshot requires successful fetch")
        if fetch.source_kind is not EventSourceKind.NEWS:
            raise ValueError("news snapshot fetch kind mismatch")
        if fetch.raw_payload_sha256 != raw_payload.payload_sha256:
            raise ValueError("news snapshot raw payload mismatch")
        if fetch.raw_payload_bytes != raw_payload.content_bytes:
            raise ValueError("news snapshot raw payload bytes mismatch")
        event_identities = tuple(
            sorted(event.news_identity for event in events)
        )
        if not events or fetch.item_identities != event_identities:
            raise ValueError("news snapshot item identity mismatch")
        if any(
            event.source_provider != fetch.source_provider
            for event in events
        ):
            raise ValueError("news snapshot event provider mismatch")

        self.initialize()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            self._append_raw_payload_db(db, raw_payload)
            for event in events:
                self._append_identity_payload_db(
                    db,
                    table="news_event_observations",
                    identity_column="news_identity",
                    identity=event.news_identity,
                    payload=news_event_payload(event),
                    columns=(
                        "news_identity",
                        "provider_article_id",
                        "source_provider",
                        "published_at_ms",
                        "ingested_at_ms",
                        "payload_json",
                    ),
                    values=(
                        event.news_identity,
                        event.provider_article_id,
                        event.source_provider,
                        event.published_at_ms,
                        event.ingested_at_ms,
                    ),
                )
            self._validate_fetch_references_db(db, fetch)
            self._append_fetch_db(db, fetch)

    def append_failed_fetch(
        self,
        *,
        fetch: EventSourceFetchObservation,
        raw_payload: EventSourceRawPayload | None = None,
    ) -> None:
        if fetch.outcome is not EventSourceFetchOutcome.FAILURE:
            raise ValueError("failed fetch append requires failure outcome")
        if raw_payload is None:
            if fetch.raw_payload_sha256 is not None:
                raise ValueError("failed fetch raw payload evidence missing")
        else:
            if fetch.raw_payload_sha256 != raw_payload.payload_sha256:
                raise ValueError("failed fetch raw payload mismatch")
            if fetch.raw_payload_bytes != raw_payload.content_bytes:
                raise ValueError("failed fetch raw payload bytes mismatch")

        self.initialize()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if raw_payload is not None:
                self._append_raw_payload_db(db, raw_payload)
            self._validate_fetch_references_db(db, fetch)
            self._append_fetch_db(db, fetch)

    def counts(self) -> dict[str, int]:
        if not self.path.is_file():
            return {
                "raw_payloads": 0,
                "calendar_coverages": 0,
                "structured_events": 0,
                "news_events": 0,
                "fetches": 0,
            }
        with sqlite3.connect(self.path) as db:
            return {
                "raw_payloads": int(
                    db.execute(
                        "SELECT COUNT(*) FROM event_source_raw_payloads"
                    ).fetchone()[0]
                ),
                "calendar_coverages": int(
                    db.execute(
                        "SELECT COUNT(*) FROM event_calendar_coverages"
                    ).fetchone()[0]
                ),
                "structured_events": int(
                    db.execute(
                        "SELECT COUNT(*) FROM structured_event_observations"
                    ).fetchone()[0]
                ),
                "news_events": int(
                    db.execute(
                        "SELECT COUNT(*) FROM news_event_observations"
                    ).fetchone()[0]
                ),
                "fetches": int(
                    db.execute(
                        "SELECT COUNT(*) FROM event_source_fetches"
                    ).fetchone()[0]
                ),
            }

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with sqlite3.connect(self.path) as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"

    def _append_identity_payload(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        payload: dict[str, object],
        columns: tuple[str, ...],
        values: tuple[object, ...],
    ) -> None:
        self.initialize()
        with sqlite3.connect(self.path) as db:
            self._append_identity_payload_db(
                db,
                table=table,
                identity_column=identity_column,
                identity=identity,
                payload=payload,
                columns=columns,
                values=values,
            )

    def _append_identity_payload_db(
        self,
        db: sqlite3.Connection,
        *,
        table: str,
        identity_column: str,
        identity: str,
        payload: dict[str, object],
        columns: tuple[str, ...],
        values: tuple[object, ...],
    ) -> None:
        payload_json = canonical_json(payload)
        existing = db.execute(
            f"SELECT payload_json FROM {table} WHERE {identity_column}=?",
            (identity,),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != payload_json:
                raise ValueError(f"{table} identity conflict")
            return
        placeholders = ",".join("?" for _ in columns)
        db.execute(
            f"INSERT INTO {table}({','.join(columns)}) "
            f"VALUES ({placeholders})",
            (*values, payload_json),
        )

    def _append_raw_payload_db(
        self,
        db: sqlite3.Connection,
        payload: EventSourceRawPayload,
    ) -> None:
        existing = db.execute(
            "SELECT content_bytes, content_type, text_encoding, payload_blob "
            "FROM event_source_raw_payloads WHERE payload_sha256=?",
            (payload.payload_sha256,),
        ).fetchone()
        values = (
            payload.content_bytes,
            payload.content_type,
            payload.text_encoding,
            payload.payload_bytes,
        )
        if existing is not None:
            if tuple(existing) != values:
                raise ValueError("event source raw payload identity conflict")
            return
        db.execute(
            """
            INSERT INTO event_source_raw_payloads(
                payload_sha256, content_bytes, content_type,
                text_encoding, payload_blob
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (payload.payload_sha256, *values),
        )

    def _validate_fetch_references_db(
        self,
        db: sqlite3.Connection,
        fetch: EventSourceFetchObservation,
    ) -> None:
        if fetch.raw_payload_sha256 is not None:
            raw = db.execute(
                "SELECT content_bytes FROM event_source_raw_payloads "
                "WHERE payload_sha256=?",
                (fetch.raw_payload_sha256,),
            ).fetchone()
            if raw is None:
                raise ValueError(
                    "event source fetch references unknown raw payload"
                )
            if int(raw[0]) != fetch.raw_payload_bytes:
                raise ValueError(
                    "event source fetch raw payload byte mismatch"
                )

        if fetch.outcome is not EventSourceFetchOutcome.SUCCESS:
            return

        if fetch.source_kind is EventSourceKind.CALENDAR:
            coverage = db.execute(
                "SELECT 1 FROM event_calendar_coverages "
                "WHERE coverage_identity=?",
                (fetch.coverage_identity,),
            ).fetchone()
            if coverage is None:
                raise ValueError("calendar fetch references unknown coverage")
            table = "structured_event_observations"
            identity_column = "event_identity"
        else:
            table = "news_event_observations"
            identity_column = "news_identity"

        for identity in fetch.item_identities:
            row = db.execute(
                f"SELECT 1 FROM {table} WHERE {identity_column}=?",
                (identity,),
            ).fetchone()
            if row is None:
                raise ValueError("event source fetch references unknown item")

    def _append_fetch_db(
        self,
        db: sqlite3.Connection,
        fetch: EventSourceFetchObservation,
    ) -> None:
        self._append_identity_payload_db(
            db,
            table="event_source_fetches",
            identity_column="fetch_identity",
            identity=fetch.fetch_identity,
            payload=_fetch_payload(fetch),
            columns=(
                "fetch_identity",
                "source_provider",
                "source_kind",
                "fetched_at_ms",
                "outcome",
                "payload_json",
            ),
            values=(
                fetch.fetch_identity,
                fetch.source_provider,
                fetch.source_kind.value,
                fetch.fetched_at_ms,
                fetch.outcome.value,
            ),
        )


def _fetch_payload(
    fetch: EventSourceFetchObservation,
) -> dict[str, object]:
    return {
        "source_provider": fetch.source_provider,
        "source_kind": fetch.source_kind,
        "endpoint_url": fetch.endpoint_url,
        "fetched_at_ms": fetch.fetched_at_ms,
        "source_timestamp_ms": fetch.source_timestamp_ms,
        "source_timestamp_basis": fetch.source_timestamp_basis,
        "http_status": fetch.http_status,
        "outcome": fetch.outcome,
        "raw_payload_sha256": fetch.raw_payload_sha256,
        "raw_payload_bytes": fetch.raw_payload_bytes,
        "item_identities": fetch.item_identities,
        "coverage_identity": fetch.coverage_identity,
        "reason_code": fetch.reason_code,
        "adapter_version": fetch.adapter_version,
        "schema_version": fetch.schema_version,
        "production_authority": fetch.production_authority,
        "real_capital": fetch.real_capital,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
