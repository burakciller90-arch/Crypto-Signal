from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_signal.intelligence.event_risk import (
    DEFAULT_REQUIRED_EVENT_CATEGORIES,
)
from crypto_signal.ledger.serialization import canonical_sha256

EVENT_SOURCE_RUNTIME_SCHEMA_VERSION = "event-source-runtime-v1/2"

_REQUIRED_COLUMNS = {
    "event_source_raw_payloads": frozenset(
        {
            "payload_sha256",
            "content_bytes",
            "content_type",
            "text_encoding",
            "payload_blob",
        }
    ),
    "event_calendar_coverages": frozenset(
        {
            "coverage_identity",
            "source_provider",
            "observed_at_ms",
            "payload_json",
        }
    ),
    "structured_event_observations": frozenset(
        {
            "event_identity",
            "provider_event_id",
            "source_provider",
            "scheduled_at_ms",
            "ingested_at_ms",
            "payload_json",
        }
    ),
    "news_event_observations": frozenset(
        {
            "news_identity",
            "provider_article_id",
            "source_provider",
            "published_at_ms",
            "ingested_at_ms",
            "payload_json",
        }
    ),
    "event_source_fetches": frozenset(
        {
            "sequence_id",
            "fetch_identity",
            "source_provider",
            "source_kind",
            "fetched_at_ms",
            "outcome",
            "payload_json",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class EventSourceFetchRuntimeTruth:
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
    coverage_identity: str | None
    reason_code: str | None
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.fetch_identity, "event source fetch")
        if self.source_kind not in {"calendar", "news"}:
            raise ValueError("unsupported event source kind")
        if self.outcome not in {"success", "failure"}:
            raise ValueError("unsupported event source outcome")
        if self.fetched_at_ms < 0 or self.fetch_age_ms < 0:
            raise ValueError("event source fetch time is invalid")
        if (self.source_timestamp_ms is None) != (
            self.source_timestamp_basis is None
        ):
            raise ValueError("event source timestamp lineage mismatch")
        if self.source_timestamp_ms is not None:
            if self.source_timestamp_ms < 0:
                raise ValueError("event source timestamp cannot be negative")
            if self.source_timestamp_ms > self.fetched_at_ms:
                raise ValueError("event source timestamp postdates fetch")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("event source HTTP status is invalid")
        if (self.raw_payload_sha256 is None) != (
            self.raw_payload_bytes is None
        ):
            raise ValueError("event source raw payload lineage mismatch")
        if self.raw_payload_sha256 is not None:
            _require_sha256(
                self.raw_payload_sha256,
                "event source raw payload",
            )
        if self.raw_payload_bytes is not None and self.raw_payload_bytes <= 0:
            raise ValueError("event source raw payload bytes must be positive")
        if self.item_count < 0:
            raise ValueError("event source item count cannot be negative")
        if self.coverage_identity is not None:
            _require_sha256(
                self.coverage_identity,
                "event source coverage",
            )
        if not self.adapter_version.strip():
            raise ValueError("event source adapter version missing")


@dataclass(frozen=True, slots=True)
class EventCalendarCoverageRuntimeTruth:
    coverage_identity: str
    source_provider: str
    observed_at_ms: int
    coverage_start_ms: int
    coverage_end_ms: int
    categories: tuple[str, ...]
    required_categories: tuple[str, ...]
    missing_required_categories: tuple[str, ...]
    coverage_relation: str
    completeness_status: str

    def __post_init__(self) -> None:
        _require_sha256(self.coverage_identity, "event calendar coverage")
        if min(
            self.observed_at_ms,
            self.coverage_start_ms,
            self.coverage_end_ms,
        ) < 0:
            raise ValueError("event calendar coverage time is invalid")
        if self.coverage_end_ms < self.coverage_start_ms:
            raise ValueError("event calendar coverage window is invalid")
        for values in (
            self.categories,
            self.required_categories,
            self.missing_required_categories,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("event calendar categories must be canonical")
        if self.coverage_relation not in {
            "BEFORE_WINDOW",
            "WITHIN_WINDOW",
            "AFTER_WINDOW",
        }:
            raise ValueError("event calendar coverage relation is invalid")
        if self.completeness_status not in {
            "COMPLETE",
            "PARTIAL",
        }:
            raise ValueError("event calendar completeness status is invalid")
        if self.completeness_status == "COMPLETE":
            if self.missing_required_categories:
                raise ValueError("complete calendar cannot miss categories")
            if self.coverage_relation != "WITHIN_WINDOW":
                raise ValueError(
                    "complete calendar must cover observation time"
                )


@dataclass(frozen=True, slots=True)
class EventSourceRuntimeTruth:
    schema_version: str
    counts: tuple[tuple[str, int], ...]
    latest_fetches: tuple[EventSourceFetchRuntimeTruth, ...]
    latest_calendar_coverage: EventCalendarCoverageRuntimeTruth | None
    runtime_status: str = "PERSISTED_EVIDENCE_ONLY"
    online_status: str = "NOT_ASSERTED"
    read_only_verified: bool = True
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SOURCE_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported Event Source runtime schema")
        if self.counts != tuple(sorted(self.counts)):
            raise ValueError("Event Source counts must be canonical")
        if any(value < 0 for _, value in self.counts):
            raise ValueError("Event Source counts cannot be negative")
        if self.latest_fetches != tuple(
            sorted(
                self.latest_fetches,
                key=lambda item: (
                    item.source_provider,
                    item.source_kind,
                ),
            )
        ):
            raise ValueError("Event Source latest fetches must be canonical")
        if self.runtime_status != "PERSISTED_EVIDENCE_ONLY":
            raise ValueError("Event Source runtime status overclaims evidence")
        if self.online_status != "NOT_ASSERTED":
            raise ValueError("Event Source Product Truth cannot assert ONLINE")
        if not self.read_only_verified:
            raise ValueError("Event Source Product Truth must be read-only")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("Event Source Product Truth cannot grant authority")


def read_event_source_runtime_truth(
    path: Path,
    *,
    observed_at_ms: int,
) -> EventSourceRuntimeTruth:
    if observed_at_ms < 0:
        raise ValueError("Event Source observation time cannot be negative")
    if not path.is_file():
        raise ValueError("Event Source runtime database missing")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        quick = db.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("Event Source SQLite quick_check failed")
        _verify_schema(db)

        counts = tuple(
            sorted(
                (
                    ("calendar_coverages", _count(db, "event_calendar_coverages")),
                    ("fetches", _count(db, "event_source_fetches")),
                    ("news_events", _count(db, "news_event_observations")),
                    ("raw_payloads", _count(db, "event_source_raw_payloads")),
                    (
                        "structured_events",
                        _count(db, "structured_event_observations"),
                    ),
                )
            )
        )

        fetch_rows = db.execute(
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
            WHERE fetched_at_ms <= ?
            ORDER BY fetched_at_ms DESC, sequence_id DESC
            """,
            (observed_at_ms,),
        ).fetchall()

        latest_by_source: dict[tuple[str, str], sqlite3.Row] = {}
        latest_successful_calendar: sqlite3.Row | None = None
        for row in fetch_rows:
            key = (str(row["source_provider"]), str(row["source_kind"]))
            latest_by_source.setdefault(key, row)
            if (
                latest_successful_calendar is None
                and str(row["source_kind"]) == "calendar"
                and str(row["outcome"]) == "success"
            ):
                latest_successful_calendar = row

        latest_fetches = tuple(
            sorted(
                (
                    _fetch_truth_from_row(
                        db,
                        row,
                        observed_at_ms=observed_at_ms,
                    )
                    for row in latest_by_source.values()
                ),
                key=lambda item: (
                    item.source_provider,
                    item.source_kind,
                ),
            )
        )
        coverage = (
            None
            if latest_successful_calendar is None
            else _coverage_truth_from_fetch(
                db,
                latest_successful_calendar,
                observed_at_ms=observed_at_ms,
            )
        )

    return EventSourceRuntimeTruth(
        schema_version=EVENT_SOURCE_RUNTIME_SCHEMA_VERSION,
        counts=counts,
        latest_fetches=latest_fetches,
        latest_calendar_coverage=coverage,
    )


def _verify_schema(db: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in db.execute(
            """SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
        ).fetchall()
    }
    required_tables = {
        "event_source_runtime_meta",
        *_REQUIRED_COLUMNS.keys(),
    }
    missing_tables = required_tables - tables
    if missing_tables:
        raise ValueError(
            "Event Source required table missing: "
            + ",".join(sorted(missing_tables))
        )

    meta = db.execute(
        "SELECT value FROM event_source_runtime_meta "
        "WHERE key='schema_version'"
    ).fetchone()
    if meta is None or str(meta[0]) != EVENT_SOURCE_RUNTIME_SCHEMA_VERSION:
        raise ValueError("Event Source schema version mismatch")

    for table, required in _REQUIRED_COLUMNS.items():
        columns = {
            str(row[1])
            for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        missing = required - columns
        if missing:
            raise ValueError(
                f"Event Source required columns missing: {table}:"
                + ",".join(sorted(missing))
            )


def _fetch_truth_from_row(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    observed_at_ms: int,
) -> EventSourceFetchRuntimeTruth:
    fetch_identity = str(row["fetch_identity"])
    payload = _payload_object(str(row["payload_json"]))
    if canonical_sha256(payload) != fetch_identity:
        raise ValueError("Event Source fetch identity mismatch")
    for key in ("source_provider", "source_kind", "outcome"):
        if str(payload[key]) != str(row[key]):
            raise ValueError(f"Event Source fetch row mismatch: {key}")
    fetched_at_ms = int(payload["fetched_at_ms"])
    if fetched_at_ms != int(row["fetched_at_ms"]):
        raise ValueError("Event Source fetch timestamp row mismatch")
    if fetched_at_ms > observed_at_ms:
        raise ValueError("Event Source fetch comes from the future")
    if payload["schema_version"] != EVENT_SOURCE_RUNTIME_SCHEMA_VERSION:
        raise ValueError("Event Source fetch schema mismatch")
    if bool(payload["production_authority"]):
        raise ValueError("Event Source fetch grants production authority")
    if int(payload["real_capital"]) != 0:
        raise ValueError("Event Source fetch real capital mismatch")

    item_ids = _string_tuple(payload["item_identities"])
    raw_sha = _optional_str(payload["raw_payload_sha256"])
    raw_bytes = _optional_int(payload["raw_payload_bytes"])
    if raw_sha is not None:
        _verify_raw_payload(
            db,
            payload_sha256=raw_sha,
            expected_bytes=raw_bytes,
        )

    outcome = str(payload["outcome"])
    kind = str(payload["source_kind"])
    coverage_identity = _optional_str(payload["coverage_identity"])
    if outcome == "success":
        if not item_ids:
            raise ValueError("successful Event Source fetch has no items")
        if kind == "calendar":
            if coverage_identity is None:
                raise ValueError(
                    "successful calendar fetch lacks coverage identity"
                )
            _verify_identity_payload(
                db,
                table="event_calendar_coverages",
                identity_column="coverage_identity",
                identity=coverage_identity,
            )
            item_table = "structured_event_observations"
            item_column = "event_identity"
        else:
            if coverage_identity is not None:
                raise ValueError("news fetch unexpectedly carries coverage")
            item_table = "news_event_observations"
            item_column = "news_identity"
        for identity in item_ids:
            _verify_identity_payload(
                db,
                table=item_table,
                identity_column=item_column,
                identity=identity,
            )
    else:
        if item_ids or coverage_identity is not None:
            raise ValueError("failed Event Source fetch claims items")

    return EventSourceFetchRuntimeTruth(
        fetch_identity=fetch_identity,
        source_provider=str(payload["source_provider"]),
        source_kind=kind,
        fetched_at_ms=fetched_at_ms,
        fetch_age_ms=observed_at_ms - fetched_at_ms,
        source_timestamp_ms=_optional_int(payload["source_timestamp_ms"]),
        source_timestamp_basis=_optional_str(
            payload["source_timestamp_basis"]
        ),
        http_status=_optional_int(payload["http_status"]),
        outcome=outcome,
        raw_payload_sha256=raw_sha,
        raw_payload_bytes=raw_bytes,
        item_count=len(item_ids),
        coverage_identity=coverage_identity,
        reason_code=_optional_str(payload["reason_code"]),
        adapter_version=str(payload["adapter_version"]),
    )


def _coverage_truth_from_fetch(
    db: sqlite3.Connection,
    fetch_row: sqlite3.Row,
    *,
    observed_at_ms: int,
) -> EventCalendarCoverageRuntimeTruth:
    fetch_payload = _payload_object(str(fetch_row["payload_json"]))
    coverage_identity = _optional_str(fetch_payload["coverage_identity"])
    if coverage_identity is None:
        raise ValueError("calendar success fetch lacks coverage")
    row = db.execute(
        "SELECT source_provider, observed_at_ms, payload_json "
        "FROM event_calendar_coverages WHERE coverage_identity=?",
        (coverage_identity,),
    ).fetchone()
    if row is None:
        raise ValueError("Event Source calendar coverage missing")
    payload = _payload_object(str(row["payload_json"]))
    if canonical_sha256(payload) != coverage_identity:
        raise ValueError("Event Source calendar coverage identity mismatch")
    if str(payload["source_provider"]) != str(row["source_provider"]):
        raise ValueError("Event Source calendar coverage provider mismatch")
    if int(payload["observed_at_ms"]) != int(row["observed_at_ms"]):
        raise ValueError("Event Source calendar coverage time mismatch")

    categories = tuple(
        sorted(str(value) for value in _list_value(payload["categories"]))
    )
    required = tuple(
        sorted(item.value for item in DEFAULT_REQUIRED_EVENT_CATEGORIES)
    )
    missing = tuple(sorted(set(required) - set(categories)))
    start = int(payload["coverage_start_ms"])
    end = int(payload["coverage_end_ms"])
    if observed_at_ms < start:
        relation = "BEFORE_WINDOW"
    elif observed_at_ms > end:
        relation = "AFTER_WINDOW"
    else:
        relation = "WITHIN_WINDOW"
    complete = not missing and relation == "WITHIN_WINDOW"

    return EventCalendarCoverageRuntimeTruth(
        coverage_identity=coverage_identity,
        source_provider=str(payload["source_provider"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        coverage_start_ms=start,
        coverage_end_ms=end,
        categories=categories,
        required_categories=required,
        missing_required_categories=missing,
        coverage_relation=relation,
        completeness_status="COMPLETE" if complete else "PARTIAL",
    )


def _verify_raw_payload(
    db: sqlite3.Connection,
    *,
    payload_sha256: str,
    expected_bytes: int | None,
) -> None:
    _require_sha256(payload_sha256, "Event Source raw payload")
    if expected_bytes is None or expected_bytes <= 0:
        raise ValueError("Event Source raw payload bytes missing")
    row = db.execute(
        "SELECT content_bytes, text_encoding, payload_blob "
        "FROM event_source_raw_payloads WHERE payload_sha256=?",
        (payload_sha256,),
    ).fetchone()
    if row is None:
        raise ValueError("Event Source raw payload missing")
    payload_blob = bytes(row["payload_blob"])
    if int(row["content_bytes"]) != expected_bytes:
        raise ValueError("Event Source raw payload byte mismatch")
    if len(payload_blob) != expected_bytes:
        raise ValueError("Event Source raw payload stored size mismatch")
    if hashlib.sha256(payload_blob).hexdigest() != payload_sha256:
        raise ValueError("Event Source raw payload hash mismatch")
    encoding = str(row["text_encoding"])
    try:
        payload_blob.decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError("Event Source raw payload decode mismatch") from exc


def _verify_identity_payload(
    db: sqlite3.Connection,
    *,
    table: str,
    identity_column: str,
    identity: str,
) -> None:
    _require_sha256(identity, f"Event Source {table} identity")
    row = db.execute(
        f"SELECT payload_json FROM {table} WHERE {identity_column}=?",
        (identity,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Event Source lineage missing: {table}")
    payload = _payload_object(str(row["payload_json"]))
    if canonical_sha256(payload) != identity:
        raise ValueError(f"Event Source lineage identity mismatch: {table}")


def _count(db: sqlite3.Connection, table: str) -> int:
    row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise ValueError(f"Event Source count failed: {table}")
    return int(row[0])


def _payload_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("Event Source payload must be object")
    return parsed


def _list_value(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError("Event Source array payload expected")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _list_value(value))


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
