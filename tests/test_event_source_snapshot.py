from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from crypto_signal.data.event_source_adapters import (
    BLS_CALENDAR_ENDPOINT,
    FED_MONETARY_RSS_ENDPOINT,
    FRED_CPI_PROVIDER,
    FRED_CPI_RELEASE_ID,
    FRED_EMPLOYMENT_PROVIDER,
    FRED_EMPLOYMENT_RELEASE_ID,
    fred_release_calendar_endpoint,
)
from crypto_signal.data.event_source_runtime import (
    EventSourceFetchOutcome,
    EventSourceRuntimeStore,
    EventSourceTimestampBasis,
)
from ops.run_event_source_snapshot import USER_AGENT, collect_event_source_cycle

BLS_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:cpi-2026-10@bls.gov
DTSTART;TZID=America/New_York:20261014T083000
SUMMARY:Consumer Price Index - September 2026
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:jobs-2026-10@bls.gov
DTSTART;TZID=America/New_York:20261002T083000
SUMMARY:Employment Situation - September 2026
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""

FRED_CPI_HTML = """<html><body>
<div>Tuesday January 13, 2026 Updated</div>
<div>7:30 am</div><div>Consumer Price Index</div>
<div>Wednesday October 14, 2026</div>
<div>7:30 am</div><div>Consumer Price Index</div>
<p>All times are US Central Time.</p>
</body></html>"""

FRED_EMPLOYMENT_HTML = """<html><body>
<div>Friday January 09, 2026 Updated</div>
<div>7:30 am</div><div>Employment Situation</div>
<div>Friday October 02, 2026</div>
<div>7:30 am</div><div>Employment Situation</div>
<p>All times are US Central Time.</p>
</body></html>"""


FED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FRB: Press Release - Monetary Policy</title>
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://www.federalreserve.gov/example-a.htm</link>
      <guid>fed-2026-09-16-a</guid>
      <pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Minutes of the Federal Open Market Committee</title>
      <link>https://www.federalreserve.gov/example-b.htm</link>
      <guid>fed-2026-08-19-b</guid>
      <pubDate>Wed, 19 Aug 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _ms(value: str) -> int:
    return int(
        datetime.fromisoformat(value)
        .astimezone(UTC)
        .timestamp()
        * 1000
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def test_event_source_cycle_persists_bls_and_fed_atomically(
    tmp_path: Path,
) -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == BLS_CALENDAR_ENDPOINT:
            return httpx.Response(
                200,
                content=BLS_ICS.encode(),
                headers={
                    "Content-Type": "text/calendar; charset=utf-8",
                    "Last-Modified": "Wed, 23 Sep 2026 18:00:00 GMT",
                },
                request=request,
            )
        if str(request.url) == FED_MONETARY_RSS_ENDPOINT:
            return httpx.Response(
                200,
                content=FED_RSS.encode(),
                headers={
                    "Content-Type": "application/rss+xml; charset=utf-8",
                    "Date": "Thu, 24 Sep 2026 04:59:00 GMT",
                },
                request=request,
            )
        raise AssertionError(f"unexpected URL {request.url}")

    store = EventSourceRuntimeStore(tmp_path / "event_source.sqlite3")
    with _client(handler) as client:
        first = collect_event_source_cycle(
            store=store,
            client=client,
            fetched_at_ms=fetched_at_ms,
        )
        second = collect_event_source_cycle(
            store=store,
            client=client,
            fetched_at_ms=fetched_at_ms,
        )

    assert first == second
    assert first.failure_count == 0
    assert tuple(fetch.outcome for fetch in first.fetches) == (
        EventSourceFetchOutcome.SUCCESS,
        EventSourceFetchOutcome.SUCCESS,
    )
    assert first.fetches[0].source_timestamp_basis is (
        EventSourceTimestampBasis.HTTP_LAST_MODIFIED
    )
    assert first.fetches[1].source_timestamp_basis is (
        EventSourceTimestampBasis.HTTP_DATE
    )
    assert store.counts() == {
        "raw_payloads": 2,
        "calendar_coverages": 1,
        "structured_events": 2,
        "news_events": 2,
        "fetches": 2,
    }
    assert store.quick_check() is True


def test_event_source_cycle_keeps_other_source_when_bls_is_down(
    tmp_path: Path,
) -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == BLS_CALENDAR_ENDPOINT:
            return httpx.Response(
                503,
                content=b"temporarily unavailable",
                headers={"Content-Type": "text/plain; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_CPI_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_CPI_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_EMPLOYMENT_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_EMPLOYMENT_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == FED_MONETARY_RSS_ENDPOINT:
            return httpx.Response(
                200,
                content=FED_RSS.encode(),
                headers={
                    "Content-Type": "application/rss+xml; charset=utf-8"
                },
                request=request,
            )
        raise AssertionError(f"unexpected URL {request.url}")

    store = EventSourceRuntimeStore(tmp_path / "event_source.sqlite3")
    with _client(handler) as client:
        result = collect_event_source_cycle(
            store=store,
            client=client,
            fetched_at_ms=fetched_at_ms,
        )

    assert result.failure_count == 1
    assert result.required_calendar_coverage_satisfied is True
    assert result.required_news_coverage_satisfied is True
    assert result.required_coverage_satisfied is True
    assert result.fetches[0].outcome is EventSourceFetchOutcome.FAILURE
    assert result.fetches[0].reason_code == "http_status_503"
    assert tuple(fetch.source_provider for fetch in result.fetches[1:3]) == (
        FRED_CPI_PROVIDER,
        FRED_EMPLOYMENT_PROVIDER,
    )
    assert all(
        fetch.outcome is EventSourceFetchOutcome.SUCCESS
        for fetch in result.fetches[1:]
    )
    assert result.fetches[-1].source_timestamp_basis is (
        EventSourceTimestampBasis.FETCH_TIME_FALLBACK
    )
    assert store.counts() == {
        "raw_payloads": 4,
        "calendar_coverages": 2,
        "structured_events": 4,
        "news_events": 2,
        "fetches": 4,
    }


def test_event_source_parse_failure_retains_exact_raw_without_items(
    tmp_path: Path,
) -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")
    broken = b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nBROKEN\n"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == BLS_CALENDAR_ENDPOINT:
            return httpx.Response(
                200,
                content=broken,
                headers={"Content-Type": "text/calendar; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_CPI_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_CPI_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_EMPLOYMENT_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_EMPLOYMENT_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == FED_MONETARY_RSS_ENDPOINT:
            return httpx.Response(
                200,
                content=FED_RSS.encode(),
                headers={
                    "Content-Type": "application/rss+xml; charset=utf-8"
                },
                request=request,
            )
        raise AssertionError(f"unexpected URL {request.url}")

    store = EventSourceRuntimeStore(tmp_path / "event_source.sqlite3")
    with _client(handler) as client:
        result = collect_event_source_cycle(
            store=store,
            client=client,
            fetched_at_ms=fetched_at_ms,
        )

    failed = result.fetches[0]
    assert failed.outcome is EventSourceFetchOutcome.FAILURE
    assert failed.reason_code == "parse_error"
    assert failed.raw_payload_sha256 is not None
    assert failed.raw_payload_bytes == len(broken)
    assert failed.item_identities == ()
    assert failed.coverage_identity is None
    assert result.failure_count == 1
    assert result.required_calendar_coverage_satisfied is True
    assert result.required_news_coverage_satisfied is True
    assert result.required_coverage_satisfied is True
    assert store.counts() == {
        "raw_payloads": 4,
        "calendar_coverages": 2,
        "structured_events": 4,
        "news_events": 2,
        "fetches": 4,
    }


def test_event_source_network_failure_does_not_fabricate_payload(
    tmp_path: Path,
) -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == BLS_CALENDAR_ENDPOINT:
            raise httpx.ConnectError("offline", request=request)
        if url == fred_release_calendar_endpoint(
            release_id=FRED_CPI_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_CPI_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_EMPLOYMENT_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_EMPLOYMENT_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == FED_MONETARY_RSS_ENDPOINT:
            return httpx.Response(
                200,
                content=FED_RSS.encode(),
                headers={
                    "Content-Type": "application/rss+xml; charset=utf-8"
                },
                request=request,
            )
        raise AssertionError(f"unexpected URL {request.url}")

    store = EventSourceRuntimeStore(tmp_path / "event_source.sqlite3")
    with _client(handler) as client:
        result = collect_event_source_cycle(
            store=store,
            client=client,
            fetched_at_ms=fetched_at_ms,
        )

    failed = result.fetches[0]
    assert failed.outcome is EventSourceFetchOutcome.FAILURE
    assert failed.reason_code == "network_error"
    assert failed.http_status is None
    assert failed.raw_payload_sha256 is None
    assert failed.source_timestamp_ms is None
    assert result.required_calendar_coverage_satisfied is True
    assert result.required_coverage_satisfied is True
    assert store.counts()["raw_payloads"] == 3



def test_event_source_user_agent_includes_owner_contact_url() -> None:
    assert USER_AGENT.startswith("Crypto-Signal/1.1 EventSourceRuntime")
    assert "https://github.com/burakciller90-arch" in USER_AGENT



def test_fred_fallback_requires_both_calendar_channels(tmp_path: Path) -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == BLS_CALENDAR_ENDPOINT:
            return httpx.Response(
                403,
                content=b"blocked",
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_CPI_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                200,
                content=FRED_CPI_HTML.encode(),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        if url == fred_release_calendar_endpoint(
            release_id=FRED_EMPLOYMENT_RELEASE_ID,
            year=2026,
        ):
            return httpx.Response(
                503,
                content=b"unavailable",
                headers={"Content-Type": "text/plain; charset=utf-8"},
                request=request,
            )
        if url == FED_MONETARY_RSS_ENDPOINT:
            return httpx.Response(
                200,
                content=FED_RSS.encode(),
                headers={
                    "Content-Type": "application/rss+xml; charset=utf-8"
                },
                request=request,
            )
        raise AssertionError(f"unexpected URL {request.url}")

    store = EventSourceRuntimeStore(tmp_path / "event_source.sqlite3")
    with _client(handler) as client:
        result = collect_event_source_cycle(
            store=store,
            client=client,
            fetched_at_ms=fetched_at_ms,
        )

    assert result.failure_count == 2
    assert result.required_calendar_coverage_satisfied is False
    assert result.required_news_coverage_satisfied is True
    assert result.required_coverage_satisfied is False
    assert store.counts()["calendar_coverages"] == 1
    assert store.counts()["structured_events"] == 2
