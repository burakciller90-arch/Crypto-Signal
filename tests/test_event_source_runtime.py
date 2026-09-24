from __future__ import annotations

import sqlite3
from decimal import Decimal

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
from crypto_signal.data.news_events import build_news_event_observation


def _coverage():
    return build_event_calendar_coverage(
        coverage_start_ms=1_000,
        coverage_end_ms=2_000,
        categories=(EventCategory.INFLATION,),
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        observed_at_ms=900,
        adapter_version="test/1",
    )


def _event():
    return build_structured_event_observation(
        provider_event_id="event-1",
        title="Consumer Price Index",
        category=EventCategory.INFLATION,
        scheduled_at_ms=1_500,
        affected_assets=(),
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        source_timestamp_ms=800,
        ingested_at_ms=900,
        adapter_version="test/1",
    )


def _news():
    return build_news_event_observation(
        provider_article_id="fed-1",
        event_cluster_key="fed-1",
        headline="Federal Reserve issues FOMC statement",
        category=EventCategory.CENTRAL_BANK,
        affected_assets=(),
        published_at_ms=700,
        source_provider="federalreserve.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        source_timestamp_ms=800,
        ingested_at_ms=900,
        extraction_method="official-feed",
        extraction_version="test/1",
        relevance_confidence_0_1=Decimal(1),
        adapter_version="test/1",
    )


def _raw(text: str):
    return build_event_source_raw_payload(
        payload_bytes=text.encode("utf-8"),
        content_type="text/plain; charset=utf-8",
        text_encoding="utf-8",
    )


def test_event_source_store_is_append_only_and_replay_safe(tmp_path) -> None:
    store = EventSourceRuntimeStore(tmp_path / "event-sources.sqlite3")
    coverage = _coverage()
    event = _event()
    news = _news()
    calendar_raw = _raw("calendar-payload")
    news_raw = _raw("news-payload")
    calendar_fetch = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=900,
        source_timestamp_ms=800,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_LAST_MODIFIED,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=calendar_raw.payload_sha256,
        raw_payload_bytes=calendar_raw.content_bytes,
        item_identities=(event.event_identity,),
        coverage_identity=coverage.coverage_identity,
        adapter_version="test/1",
    )
    news_fetch = build_event_source_fetch_observation(
        source_provider="federalreserve.gov",
        source_kind=EventSourceKind.NEWS,
        endpoint_url="https://www.federalreserve.gov/feeds/press_monetary.xml",
        fetched_at_ms=900,
        source_timestamp_ms=800,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=news_raw.payload_sha256,
        raw_payload_bytes=news_raw.content_bytes,
        item_identities=(news.news_identity,),
        adapter_version="test/1",
    )

    for _ in range(2):
        store.append_raw_payload(calendar_raw)
        store.append_raw_payload(news_raw)
        store.append_calendar_coverage(coverage)
        store.append_structured_event(event)
        store.append_news_event(news)
        store.append_fetch(calendar_fetch)
        store.append_fetch(news_fetch)

    assert store.counts() == {
        "raw_payloads": 2,
        "calendar_coverages": 1,
        "structured_events": 1,
        "news_events": 1,
        "fetches": 2,
    }
    assert store.quick_check() is True

    with sqlite3.connect(store.path) as db:
        for table in (
            "event_source_raw_payloads",
            "event_calendar_coverages",
            "structured_event_observations",
            "news_event_observations",
            "event_source_fetches",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(f"DELETE FROM {table}")


def test_event_source_store_records_failure_without_fake_items(tmp_path) -> None:
    store = EventSourceRuntimeStore(tmp_path / "event-sources.sqlite3")
    failed = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=1_000,
        source_timestamp_ms=None,
        source_timestamp_basis=None,
        http_status=503,
        outcome=EventSourceFetchOutcome.FAILURE,
        reason_code="http_status_503",
        adapter_version="test/1",
    )

    store.append_fetch(failed)

    assert store.counts() == {
        "raw_payloads": 0,
        "calendar_coverages": 0,
        "structured_events": 0,
        "news_events": 0,
        "fetches": 1,
    }


def test_successful_calendar_fetch_requires_exact_coverage_identity() -> None:
    with pytest.raises(ValueError, match="coverage identity"):
        build_event_source_fetch_observation(
            source_provider="bls.gov",
            source_kind=EventSourceKind.CALENDAR,
            endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
            fetched_at_ms=1_000,
            source_timestamp_ms=900,
            source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
            http_status=200,
            outcome=EventSourceFetchOutcome.SUCCESS,
            raw_payload_sha256="a" * 64,
            raw_payload_bytes=1,
            item_identities=("b" * 64,),
            adapter_version="test/1",
        )


def test_failed_fetch_cannot_claim_items() -> None:
    with pytest.raises(ValueError, match="cannot claim persisted items"):
        build_event_source_fetch_observation(
            source_provider="federalreserve.gov",
            source_kind=EventSourceKind.NEWS,
            endpoint_url="https://www.federalreserve.gov/feeds/press_monetary.xml",
            fetched_at_ms=1_000,
            source_timestamp_ms=None,
            source_timestamp_basis=None,
            http_status=None,
            outcome=EventSourceFetchOutcome.FAILURE,
            item_identities=("a" * 64,),
            reason_code="network_error",
            adapter_version="test/1",
        )


def test_event_source_raw_payload_is_exact_and_bounded() -> None:
    raw = _raw("exact-source")

    assert len(raw.payload_sha256) == 64
    assert raw.content_bytes == len("exact-source".encode())

    with pytest.raises(ValueError, match="byte count mismatch"):
        type(raw)(
            payload_sha256=raw.payload_sha256,
            content_bytes=raw.content_bytes + 1,
            content_type=raw.content_type,
            text_encoding=raw.text_encoding,
            payload_bytes=raw.payload_bytes,
        )


def test_success_fetch_rejects_dangling_raw_or_item_lineage(tmp_path) -> None:
    store = EventSourceRuntimeStore(tmp_path / "event-sources.sqlite3")
    raw = _raw("calendar-payload")
    coverage = _coverage()
    event = _event()
    fetch = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=900,
        source_timestamp_ms=800,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_LAST_MODIFIED,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=(event.event_identity,),
        coverage_identity=coverage.coverage_identity,
        adapter_version="test/1",
    )

    with pytest.raises(ValueError, match="unknown raw payload"):
        store.append_fetch(fetch)

    store.append_raw_payload(raw)
    with pytest.raises(ValueError, match="unknown coverage"):
        store.append_fetch(fetch)

    store.append_calendar_coverage(coverage)
    with pytest.raises(ValueError, match="unknown item"):
        store.append_fetch(fetch)

    store.append_structured_event(event)
    store.append_fetch(fetch)
    assert store.counts()["fetches"] == 1


def test_failed_parse_can_retain_raw_payload_without_fake_items(tmp_path) -> None:
    store = EventSourceRuntimeStore(tmp_path / "event-sources.sqlite3")
    raw = _raw("malformed-source")
    store.append_raw_payload(raw)
    failed = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=1_000,
        source_timestamp_ms=900,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
        http_status=200,
        outcome=EventSourceFetchOutcome.FAILURE,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        reason_code="parse_error",
        adapter_version="test/1",
    )

    store.append_fetch(failed)

    assert store.counts() == {
        "raw_payloads": 1,
        "calendar_coverages": 0,
        "structured_events": 0,
        "news_events": 0,
        "fetches": 1,
    }


def test_atomic_calendar_snapshot_rolls_back_on_lineage_error(tmp_path) -> None:
    store = EventSourceRuntimeStore(tmp_path / "event-sources.sqlite3")
    raw = _raw("calendar-payload")
    coverage = _coverage()
    event = _event()
    bad_fetch = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url="https://www.bls.gov/schedule/news_release/bls.ics",
        fetched_at_ms=900,
        source_timestamp_ms=800,
        source_timestamp_basis=EventSourceTimestampBasis.HTTP_DATE,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=("f" * 64,),
        coverage_identity=coverage.coverage_identity,
        adapter_version="test/1",
    )

    with pytest.raises(ValueError, match="item identity mismatch"):
        store.append_calendar_snapshot(
            raw_payload=raw,
            coverage=coverage,
            events=(event,),
            fetch=bad_fetch,
        )

    assert store.counts() == {
        "raw_payloads": 0,
        "calendar_coverages": 0,
        "structured_events": 0,
        "news_events": 0,
        "fetches": 0,
    }
