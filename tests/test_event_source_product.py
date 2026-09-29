from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
from crypto_signal.data.news_events import build_news_event_observation
from crypto_signal.product.event_source_runtime import (
    read_event_source_calendar_rail,
    read_event_source_runtime_truth,
)
from crypto_signal.product.web import create_app


def _seed_successes(path: Path, *, fetched_at_ms: int = 900) -> None:
    store = EventSourceRuntimeStore(path)

    calendar_raw = build_event_source_raw_payload(
        payload_bytes=b"calendar-source",
        content_type="text/calendar; charset=utf-8",
        text_encoding="utf-8",
    )
    coverage = build_event_calendar_coverage(
        coverage_start_ms=1_000,
        coverage_end_ms=5_000,
        categories=(
            EventCategory.EMPLOYMENT,
            EventCategory.INFLATION,
        ),
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        observed_at_ms=fetched_at_ms,
        adapter_version="bls-calendar-ics-v1/1",
    )
    event = build_structured_event_observation(
        provider_event_id="cpi-1",
        title="Consumer Price Index",
        category=EventCategory.INFLATION,
        scheduled_at_ms=2_000,
        affected_assets=(),
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        source_timestamp_ms=fetched_at_ms - 100,
        ingested_at_ms=fetched_at_ms,
        adapter_version="bls-calendar-ics-v1/1",
    )
    calendar_fetch = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=fetched_at_ms - 100,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_LAST_MODIFIED,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=calendar_raw.payload_sha256,
        raw_payload_bytes=calendar_raw.content_bytes,
        item_identities=(event.event_identity,),
        coverage_identity=coverage.coverage_identity,
        adapter_version="bls-calendar-ics-v1/1",
    )
    store.append_calendar_snapshot(
        raw_payload=calendar_raw,
        coverage=coverage,
        events=(event,),
        fetch=calendar_fetch,
    )

    news_raw = build_event_source_raw_payload(
        payload_bytes=b"fed-news-source",
        content_type="application/rss+xml; charset=utf-8",
        text_encoding="utf-8",
    )
    news = build_news_event_observation(
        provider_article_id="fed-1",
        event_cluster_key="fed-1",
        headline="Federal Reserve issues FOMC statement",
        category=EventCategory.CENTRAL_BANK,
        affected_assets=(),
        published_at_ms=fetched_at_ms - 200,
        source_provider="federalreserve.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        source_timestamp_ms=fetched_at_ms - 100,
        ingested_at_ms=fetched_at_ms,
        extraction_method="official-monetary-policy-rss-channel",
        extraction_version="fed-monetary-rss-v1/1",
        relevance_confidence_0_1=Decimal(1),
        adapter_version="fed-monetary-rss-v1/1",
    )
    news_fetch = build_event_source_fetch_observation(
        source_provider="federalreserve.gov",
        source_kind=EventSourceKind.NEWS,
        endpoint_url="https://www.federalreserve.gov/feeds/press_monetary.xml",
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=fetched_at_ms - 100,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=news_raw.payload_sha256,
        raw_payload_bytes=news_raw.content_bytes,
        item_identities=(news.news_identity,),
        adapter_version="fed-monetary-rss-v1/1",
    )
    store.append_news_snapshot(
        raw_payload=news_raw,
        events=(news,),
        fetch=news_fetch,
    )


def test_event_source_product_reader_verifies_exact_persisted_lineage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    before = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }

    snapshot = read_event_source_runtime_truth(
        path,
        observed_at_ms=1_000,
    )

    assert snapshot.schema_version == "event-source-runtime-v1/2"
    assert snapshot.raw_payload_count == 2
    assert snapshot.calendar_coverage_count == 1
    assert snapshot.structured_event_count == 1
    assert snapshot.news_event_count == 1
    assert snapshot.fetch_count == 2
    assert snapshot.latest_successful_fetch_at_ms == 900
    assert snapshot.latest_successful_fetch_age_ms == 100
    assert snapshot.runtime_status == "PERSISTED_EVIDENCE_ONLY"
    assert snapshot.online_status == "NOT_ASSERTED"
    assert snapshot.process_status == "NOT_MEASURED"
    assert snapshot.coverage_claim == "SOURCE_SCOPED_ONLY"
    assert snapshot.read_only_verified is True
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0
    assert len(snapshot.latest_fetches) == 2

    calendar, news = snapshot.latest_fetches
    assert calendar.source_provider == "bls.gov"
    assert calendar.source_kind == "calendar"
    assert calendar.outcome == "success"
    assert calendar.fetch_age_ms == 100
    assert calendar.coverage_categories == ("employment", "inflation")
    assert calendar.item_categories == ("inflation",)
    assert news.source_provider == "federalreserve.gov"
    assert news.source_kind == "news"
    assert news.outcome == "success"
    assert news.item_categories == ("central_bank",)
    after = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }
    assert after == before


def test_event_source_product_reader_is_point_in_time(tmp_path: Path) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    store = EventSourceRuntimeStore(path)
    failed = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=2_000,
        source_timestamp_ms=None,
        source_timestamp_basis=None,
        http_status=503,
        outcome=EventSourceFetchOutcome.FAILURE,
        reason_code="http_status_503",
        adapter_version="bls-calendar-ics-v1/1",
    )
    store.append_failed_fetch(fetch=failed)

    historical = read_event_source_runtime_truth(
        path,
        observed_at_ms=1_500,
    )
    current = read_event_source_runtime_truth(
        path,
        observed_at_ms=2_500,
    )

    historical_bls = next(
        item
        for item in historical.latest_fetches
        if item.source_provider == "bls.gov"
    )
    current_bls = next(
        item
        for item in current.latest_fetches
        if item.source_provider == "bls.gov"
    )
    assert historical_bls.outcome == "success"
    assert historical_bls.fetched_at_ms == 900
    assert current_bls.outcome == "failure"
    assert current_bls.fetched_at_ms == 2_000
    assert current_bls.reason_code == "http_status_503"
    assert current.latest_successful_fetch_at_ms == 900


def test_event_source_product_reader_fails_closed_on_raw_tamper(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)

    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER event_source_raw_payload_no_update")
        row = db.execute(
            "SELECT payload_sha256 FROM event_source_raw_payloads "
            "ORDER BY payload_sha256 LIMIT 1"
        ).fetchone()
        assert row is not None
        db.execute(
            "UPDATE event_source_raw_payloads "
            "SET payload_blob=? WHERE payload_sha256=?",
            (b"tampered-source", str(row[0])),
        )
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    with pytest.raises(ValueError, match="raw payload"):
        read_event_source_runtime_truth(
            path,
            observed_at_ms=1_000,
        )


def test_event_source_product_endpoint_exposes_persisted_not_online(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    before = path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            event_source_runtime_path=path,
        )
    )

    response = client.get(
        "/api/event-source-runtime/status?observed_at_ms=1000"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database_filename"] == "event_source.sqlite3"
    assert body["runtime_status"] == "PERSISTED_EVIDENCE_ONLY"
    assert body["online_status"] == "NOT_ASSERTED"
    assert body["process_status"] == "NOT_MEASURED"
    assert body["coverage_claim"] == "SOURCE_SCOPED_ONLY"
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert body["snapshot"]["fetch_count"] == 2
    assert len(body["snapshot"]["latest_fetches"]) == 2
    assert path.read_bytes() == before
    assert client.post("/api/event-source-runtime/status").status_code == 405


def test_event_source_product_missing_runtime_creates_nothing(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "event-source-missing.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            event_source_runtime_path=missing,
        )
    )

    body = client.get("/api/event-source-runtime/status").json()

    assert body["status"] == "unavailable"
    assert body["reason"] == "event_source_runtime_evidence_missing"
    assert body["runtime_status"] == "NOT_EXPOSED"
    assert body["online_status"] == "NOT_ASSERTED"
    assert body["process_status"] == "NOT_MEASURED"
    assert body["coverage_claim"] == "SOURCE_SCOPED_ONLY"
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert not missing.exists()


def test_galactech_system_exposes_event_source_without_online_claim(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    html = client.get("/galactech").text
    js = client.get("/galactech-static/app.js").text

    assert 'id="systemEventSource"' in html
    assert 'id="systemEventSourceNote"' in html
    assert "OLAY KAYNAĞI ÇALIŞMA DURUMU" in html
    assert 'eventSourceStatus: "/api/event-source-runtime/status"' in js
    assert '"eventSourceStatus"' in js
    assert '"systemEventSource"' in js
    assert "ÇEVRİMİÇİ OLDUĞU İDDİA EDİLMEZ" in js
    assert "Olay kaynağı çalışma zamanı kanıtı kullanılamıyor." in js


def test_event_source_product_reader_fails_closed_on_nonempty_wal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    wal = Path(f"{path}-wal")
    wal.write_bytes(b"uncheckpointed")

    with pytest.raises(ValueError, match="uncheckpointed WAL"):
        read_event_source_runtime_truth(
            path,
            observed_at_ms=1_000,
        )

    assert wal.read_bytes() == b"uncheckpointed"


def test_event_source_product_reader_does_not_create_sqlite_sidecars(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    wal = Path(f"{path}-wal")
    shm = Path(f"{path}-shm")
    wal.unlink(missing_ok=True)
    shm.unlink(missing_ok=True)
    before = path.read_bytes()

    snapshot = read_event_source_runtime_truth(
        path,
        observed_at_ms=1_000,
    )

    assert snapshot.read_only_verified is True
    assert path.read_bytes() == before
    assert not wal.exists()
    assert not shm.exists()


def test_event_source_product_reader_preserves_existing_empty_sidecars(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    wal = Path(f"{path}-wal")
    shm = Path(f"{path}-shm")
    wal.write_bytes(b"")
    shm.write_bytes(b"existing-shm-evidence")
    before = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }

    snapshot = read_event_source_runtime_truth(
        path,
        observed_at_ms=1_000,
    )

    after = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }
    assert snapshot.read_only_verified is True
    assert after == before


def _append_calendar_snapshot(
    path: Path,
    *,
    provider: str,
    fetched_at_ms: int,
    coverage_start_ms: int,
    coverage_end_ms: int,
    coverage_categories: tuple[EventCategory, ...],
    events: tuple[object, ...],
    suffix: str,
) -> None:
    store = EventSourceRuntimeStore(path)
    raw = build_event_source_raw_payload(
        payload_bytes=f"calendar-{provider}-{suffix}".encode(),
        content_type="text/calendar; charset=utf-8",
        text_encoding="utf-8",
    )
    coverage = build_event_calendar_coverage(
        coverage_start_ms=coverage_start_ms,
        coverage_end_ms=coverage_end_ms,
        categories=coverage_categories,
        source_provider=provider,
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        observed_at_ms=fetched_at_ms,
        adapter_version=f"calendar-{suffix}/1",
    )
    identities = tuple(
        sorted(str(getattr(item, "event_identity")) for item in events)
    )
    fetch = build_event_source_fetch_observation(
        source_provider=provider,
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url=f"https://{provider}/calendar",
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=max(0, fetched_at_ms - 10),
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=identities,
        coverage_identity=coverage.coverage_identity,
        adapter_version=f"calendar-{suffix}/1",
    )
    store.append_calendar_snapshot(
        raw_payload=raw,
        coverage=coverage,
        events=events,
        fetch=fetch,
    )


def _rail_event(
    event_id: str,
    *,
    scheduled_at_ms: int,
    ingested_at_ms: int,
    assets: tuple[str, ...] = (),
    category: EventCategory = EventCategory.INFLATION,
    provider: str = "calendar-provider",
):
    return build_structured_event_observation(
        provider_event_id=event_id,
        title=f"Event {event_id}",
        category=category,
        scheduled_at_ms=scheduled_at_ms,
        affected_assets=assets,
        source_provider=provider,
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        source_timestamp_ms=max(0, ingested_at_ms - 10),
        ingested_at_ms=ingested_at_ms,
        adapter_version="rail-test/1",
    )


def test_calendar_rail_reads_verified_scheduled_events_and_excludes_news(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event_source.sqlite3"
    _seed_successes(path)
    before = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }

    rail = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
        limit=10,
    )

    assert rail.coverage_status == "COMPLETE"
    assert rail.total_matching_events == 1
    assert len(rail.events) == 1
    event = rail.events[0]
    assert event.title == "Consumer Price Index"
    assert event.category == "inflation"
    assert event.scheduled_at_ms == 2_000
    assert event.source_provider == "bls.gov"
    assert event.source_quality == "official"
    assert all(item.source_kind == "calendar" for item in rail.latest_calendar_fetches)
    assert rail.coverages[0].categories == ("employment", "inflation")
    after = {
        item.name: item.read_bytes()
        for item in tmp_path.iterdir()
        if item.is_file()
    }
    assert after == before


def test_calendar_rail_asset_filter_includes_global_and_exact_asset_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "asset-rail.sqlite3"
    global_event = _rail_event(
        "global",
        scheduled_at_ms=2_000,
        ingested_at_ms=900,
    )
    btc_event = _rail_event(
        "btc",
        scheduled_at_ms=2_100,
        ingested_at_ms=900,
        assets=("BTC",),
    )
    eth_event = _rail_event(
        "eth",
        scheduled_at_ms=2_200,
        ingested_at_ms=900,
        assets=("ETH",),
    )
    _append_calendar_snapshot(
        path,
        provider="calendar-provider",
        fetched_at_ms=950,
        coverage_start_ms=1_000,
        coverage_end_ms=5_000,
        coverage_categories=(EventCategory.INFLATION,),
        events=(global_event, btc_event, eth_event),
        suffix="assets",
    )

    rail = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        asset="btc",
        categories=("inflation",),
    )

    assert rail.asset == "BTC"
    assert [item.provider_event_id for item in rail.events] == [
        "global",
        "btc",
    ]


def test_calendar_rail_excludes_orphan_and_late_ingested_events(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pit-rail.sqlite3"
    accepted = _rail_event(
        "accepted",
        scheduled_at_ms=2_000,
        ingested_at_ms=900,
    )
    late = _rail_event(
        "late",
        scheduled_at_ms=2_100,
        ingested_at_ms=1_100,
    )
    _append_calendar_snapshot(
        path,
        provider="calendar-provider",
        fetched_at_ms=950,
        coverage_start_ms=1_000,
        coverage_end_ms=5_000,
        coverage_categories=(EventCategory.INFLATION,),
        events=(accepted, late),
        suffix="pit",
    )
    orphan = _rail_event(
        "orphan",
        scheduled_at_ms=2_200,
        ingested_at_ms=900,
    )
    EventSourceRuntimeStore(path).append_structured_event(orphan)

    rail = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
    )

    assert [item.provider_event_id for item in rail.events] == ["accepted"]


def test_calendar_rail_latest_failed_fetch_removes_current_coverage_claim(
    tmp_path: Path,
) -> None:
    path = tmp_path / "failure-rail.sqlite3"
    _seed_successes(path, fetched_at_ms=900)
    failed = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=1_200,
        source_timestamp_ms=None,
        source_timestamp_basis=None,
        http_status=503,
        outcome=EventSourceFetchOutcome.FAILURE,
        reason_code="http_status_503",
        adapter_version="bls-calendar-ics-v1/1",
    )
    EventSourceRuntimeStore(path).append_failed_fetch(fetch=failed)

    rail = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_500,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
    )

    assert rail.coverage_status == "UNAVAILABLE"
    assert rail.coverages == ()
    assert rail.events
    assert rail.latest_calendar_fetches[0].outcome == "failure"


def test_calendar_rail_distinguishes_complete_incomplete_and_source_scoped_coverage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coverage-rail.sqlite3"
    _seed_successes(path)

    complete = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
    )
    incomplete = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("central_bank",),
    )
    unscoped = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
    )

    assert complete.coverage_status == "COMPLETE"
    assert incomplete.coverage_status == "INCOMPLETE"
    assert incomplete.events == ()
    assert unscoped.coverage_status == "SOURCE_SCOPED_ONLY"


def test_calendar_rail_ignores_future_fetch_and_coverage_at_point_in_time(
    tmp_path: Path,
) -> None:
    path = tmp_path / "future-coverage-rail.sqlite3"
    first = _rail_event(
        "first",
        scheduled_at_ms=2_000,
        ingested_at_ms=900,
    )
    _append_calendar_snapshot(
        path,
        provider="calendar-provider",
        fetched_at_ms=950,
        coverage_start_ms=1_000,
        coverage_end_ms=3_000,
        coverage_categories=(EventCategory.INFLATION,),
        events=(first,),
        suffix="first",
    )
    future = _rail_event(
        "future",
        scheduled_at_ms=4_000,
        ingested_at_ms=1_900,
    )
    _append_calendar_snapshot(
        path,
        provider="calendar-provider",
        fetched_at_ms=2_000,
        coverage_start_ms=1_000,
        coverage_end_ms=5_000,
        coverage_categories=(EventCategory.INFLATION,),
        events=(first, future),
        suffix="future",
    )

    rail = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_500,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
    )

    assert rail.coverage_status == "INCOMPLETE"
    assert [item.provider_event_id for item in rail.events] == ["first"]
    assert rail.latest_calendar_fetches[0].fetched_at_ms == 950


def test_calendar_rail_is_deterministic_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "bounded-rail.sqlite3"
    events = tuple(
        _rail_event(
            f"event-{index}",
            scheduled_at_ms=2_000,
            ingested_at_ms=900,
        )
        for index in range(3)
    )
    _append_calendar_snapshot(
        path,
        provider="calendar-provider",
        fetched_at_ms=950,
        coverage_start_ms=1_000,
        coverage_end_ms=5_000,
        coverage_categories=(EventCategory.INFLATION,),
        events=events,
        suffix="bounded",
    )

    rail = read_event_source_calendar_rail(
        path,
        observed_at_ms=1_000,
        window_start_ms=1_000,
        window_end_ms=5_000,
        categories=("inflation",),
        limit=2,
    )

    assert rail.total_matching_events == 3
    assert len(rail.events) == 2
    assert tuple(item.event_identity for item in rail.events) == tuple(
        sorted(item.event_identity for item in events)[:2]
    )


def test_calendar_rail_fails_closed_on_nonempty_wal_and_creates_nothing(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-rail.sqlite3"
    with pytest.raises(ValueError, match="database missing"):
        read_event_source_calendar_rail(
            missing,
            observed_at_ms=1_000,
            window_start_ms=1_000,
            window_end_ms=2_000,
            categories=("inflation",),
        )
    assert not missing.exists()

    path = tmp_path / "wal-rail.sqlite3"
    _seed_successes(path)
    wal = Path(f"{path}-wal")
    wal.write_bytes(b"uncheckpointed")
    with pytest.raises(ValueError, match="uncheckpointed WAL"):
        read_event_source_calendar_rail(
            path,
            observed_at_ms=1_000,
            window_start_ms=1_000,
            window_end_ms=5_000,
            categories=("inflation",),
        )
    assert wal.read_bytes() == b"uncheckpointed"
