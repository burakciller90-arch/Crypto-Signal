from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from crypto_signal.data.event_risk import (
    EventCategory,
    EventSourceQuality,
    build_event_calendar_coverage,
    build_structured_event_observation,
)
from crypto_signal.data.event_source_runtime import (
    EventSourceFetchOutcome,
    EventSourceKind,
    EventSourceRuntimeStore,
    EventSourceTimestampBasis,
    build_event_source_fetch_observation,
    build_event_source_raw_payload,
)
from crypto_signal.data.models import DataSource
from crypto_signal.intelligence.event_risk import (
    DEFAULT_REQUIRED_EVENT_CATEGORIES,
)
from crypto_signal.product.event_source_runtime import (
    read_event_source_runtime_truth,
)


def _seed(path: Path) -> EventSourceRuntimeStore:
    store = EventSourceRuntimeStore(path)
    raw = build_event_source_raw_payload(
        payload_bytes=b"official-calendar",
        content_type="text/calendar; charset=utf-8",
        text_encoding="utf-8",
    )
    coverage = build_event_calendar_coverage(
        coverage_start_ms=2_000,
        coverage_end_ms=4_000,
        categories=(
            EventCategory.EMPLOYMENT,
            EventCategory.INFLATION,
        ),
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        observed_at_ms=1_000,
        adapter_version="bls-test/1",
    )
    event = build_structured_event_observation(
        provider_event_id="cpi-1",
        title="Consumer Price Index",
        category=EventCategory.INFLATION,
        scheduled_at_ms=3_000,
        affected_assets=(),
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        source_timestamp_ms=900,
        ingested_at_ms=1_000,
        adapter_version="bls-test/1",
    )
    fetch = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=1_000,
        source_timestamp_ms=900,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=(event.event_identity,),
        coverage_identity=coverage.coverage_identity,
        adapter_version="bls-test/1",
    )
    store.append_calendar_snapshot(
        raw_payload=raw,
        coverage=coverage,
        events=(event,),
        fetch=fetch,
    )
    return store


def test_event_source_product_reader_verifies_exact_lineage_read_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed(path)
    before = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }

    snapshot = read_event_source_runtime_truth(
        path,
        observed_at_ms=1_500,
    )

    assert snapshot.schema_version == "event-source-runtime-v1/2"
    assert dict(snapshot.counts) == {
        "calendar_coverages": 1,
        "fetches": 1,
        "news_events": 0,
        "raw_payloads": 1,
        "structured_events": 1,
    }
    assert len(snapshot.latest_fetches) == 1
    fetch = snapshot.latest_fetches[0]
    assert fetch.source_provider == "bls.gov"
    assert fetch.outcome == "success"
    assert fetch.fetch_age_ms == 500
    assert fetch.raw_payload_sha256 is not None
    assert fetch.item_count == 1
    assert snapshot.online_status == "NOT_ASSERTED"
    assert snapshot.runtime_status == "PERSISTED_EVIDENCE_ONLY"
    assert snapshot.read_only_verified is True
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0

    after = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }
    assert after == before


def test_event_source_product_reports_partial_calendar_coverage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed(path)

    snapshot = read_event_source_runtime_truth(
        path,
        observed_at_ms=3_000,
    )

    coverage = snapshot.latest_calendar_coverage
    assert coverage is not None
    assert coverage.categories == ("employment", "inflation")
    assert coverage.coverage_relation == "WITHIN_WINDOW"
    assert coverage.completeness_status == "PARTIAL"
    required = tuple(
        sorted(item.value for item in DEFAULT_REQUIRED_EVENT_CATEGORIES)
    )
    assert coverage.required_categories == required
    assert set(coverage.missing_required_categories) == (
        set(required) - {"employment", "inflation"}
    )


def test_event_source_product_does_not_call_future_fetches_current(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed(path)

    snapshot = read_event_source_runtime_truth(
        path,
        observed_at_ms=500,
    )

    assert snapshot.latest_fetches == ()
    assert snapshot.latest_calendar_coverage is None


def test_event_source_product_detects_raw_tamper(tmp_path: Path) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER event_source_raw_payload_no_update")
        db.execute(
            "UPDATE event_source_raw_payloads SET payload_blob=?",
            (b"tampered",),
        )

    with pytest.raises(ValueError, match="stored size mismatch|hash mismatch"):
        read_event_source_runtime_truth(path, observed_at_ms=1_500)


def test_event_source_product_detects_fetch_payload_tamper(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER event_source_fetch_no_update")
        row = db.execute(
            "SELECT sequence_id, payload_json FROM event_source_fetches"
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[1]))
        payload["http_status"] = 201
        db.execute(
            "UPDATE event_source_fetches SET payload_json=? "
            "WHERE sequence_id=?",
            (json.dumps(payload), int(row[0])),
        )

    with pytest.raises(ValueError, match="fetch identity mismatch"):
        read_event_source_runtime_truth(path, observed_at_ms=1_500)


def test_event_source_missing_runtime_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(ValueError, match="missing"):
        read_event_source_runtime_truth(path, observed_at_ms=1_500)

    assert not path.exists()
