from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_signal.data.event_risk import EventCategory, EventSourceQuality
from crypto_signal.data.event_source_adapters import (
    BLS_CALENDAR_ADAPTER_VERSION,
    FED_MONETARY_RSS_ADAPTER_VERSION,
    FRED_CALENDAR_ADAPTER_VERSION,
    FRED_CPI_PROVIDER,
    FRED_CPI_RELEASE_ID,
    FRED_EMPLOYMENT_PROVIDER,
    FRED_EMPLOYMENT_RELEASE_ID,
    fred_release_calendar_endpoint,
    parse_bls_calendar_ics,
    parse_fed_monetary_rss,
    parse_fred_release_calendar_html,
)
from crypto_signal.data.models import DataSource

BLS_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:cpi-2026-10@bls.gov
DTSTART;TZID=America/New_York:20261013T083000
SUMMARY:Consumer Price Index - September 2026
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:jobs-2026-10@bls.gov
DTSTART;TZID=America/New_York:20261002T083000
SUMMARY:Employment Situation - September 2026
DESCRIPTION:Official BLS release\ncontinued
END:VEVENT
BEGIN:VEVENT
UID:cancelled@bls.gov
DTSTART;TZID=America/New_York:20261009T083000
SUMMARY:Cancelled Test Release
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""

FRED_CPI_HTML = """<html><body>
<h1>Release Calendar</h1>
<div>Tuesday January 13, 2026 Updated</div>
<div>7:30 am</div><div>Consumer Price Index</div>
<div>Wednesday October 14, 2026</div>
<div>7:30 am</div><div>Consumer Price Index</div>
<div>Thursday December 10, 2026</div>
<div>7:30 am</div><div>Consumer Price Index</div>
<p>All times are US Central Time.</p>
<script>Friday January 01, 2026 1:00 am Consumer Price Index</script>
</body></html>"""

FRED_EMPLOYMENT_HTML = """<html><body>
<h1>Release Calendar</h1>
<div>Friday January 09, 2026 Updated</div>
<div>7:30 am</div><div>Employment Situation</div>
<div>Friday October 02, 2026</div>
<div>7:30 am</div><div>Employment Situation</div>
<div>Friday December 04, 2026</div>
<div>7:30 am</div><div>Employment Situation</div>
<p>All times are US Central Time.</p>
</body></html>"""


FED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FRB: Press Release - Monetary Policy</title>
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm</link>
      <guid>fed-2026-09-16-a</guid>
      <pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Minutes of the Federal Open Market Committee</title>
      <link>https://www.federalreserve.gov/monetarypolicy/fomcminutes20260729.htm</link>
      <guid>fed-minutes-2026-08-19</guid>
      <pubDate>Wed, 19 Aug 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(UTC).timestamp() * 1000)


def test_bls_ics_parser_preserves_official_schedule_and_categories() -> None:
    fetched_at_ms = _ms("2026-09-24T04:00:00+00:00")
    source_timestamp_ms = _ms("2026-09-23T18:00:00+00:00")

    parsed = parse_bls_calendar_ics(
        BLS_ICS,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
    )

    assert tuple(event.provider_event_id for event in parsed.events) == (
        "jobs-2026-10@bls.gov",
        "cpi-2026-10@bls.gov",
    )
    assert tuple(event.category for event in parsed.events) == (
        EventCategory.EMPLOYMENT,
        EventCategory.INFLATION,
    )
    assert all(event.affected_assets == () for event in parsed.events)
    assert all(
        event.source_quality is EventSourceQuality.OFFICIAL
        for event in parsed.events
    )
    assert all(event.source is DataSource.REST for event in parsed.events)
    assert all(
        event.adapter_version == BLS_CALENDAR_ADAPTER_VERSION
        for event in parsed.events
    )
    assert parsed.coverage.source_provider == "bls.gov"
    assert parsed.coverage.categories == (
        EventCategory.EMPLOYMENT,
        EventCategory.INFLATION,
    )
    assert parsed.coverage.coverage_start_ms == _ms(
        "2026-10-02T08:30:00-04:00"
    )
    assert parsed.coverage.coverage_end_ms == _ms(
        "2026-10-13T08:30:00-04:00"
    )


def test_bls_ics_parser_fails_closed_on_duplicate_uid() -> None:
    duplicate = BLS_ICS.replace(
        "UID:jobs-2026-10@bls.gov",
        "UID:cpi-2026-10@bls.gov",
    )

    with pytest.raises(ValueError, match="duplicate event UID"):
        parse_bls_calendar_ics(
            duplicate,
            fetched_at_ms=_ms("2026-09-24T04:00:00+00:00"),
            source_timestamp_ms=_ms("2026-09-23T18:00:00+00:00"),
        )


def test_fed_monetary_rss_parser_persists_official_non_directional_news() -> None:
    fetched_at_ms = _ms("2026-09-24T04:00:00+00:00")
    source_timestamp_ms = _ms("2026-09-23T18:00:00+00:00")

    items = parse_fed_monetary_rss(
        FED_RSS,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
    )

    assert tuple(item.provider_article_id for item in items) == (
        "fed-minutes-2026-08-19",
        "fed-2026-09-16-a",
    )
    assert all(item.category is EventCategory.CENTRAL_BANK for item in items)
    assert all(item.affected_assets == () for item in items)
    assert all(
        item.source_quality is EventSourceQuality.OFFICIAL for item in items
    )
    assert all(item.source is DataSource.REST for item in items)
    assert all(
        item.extraction_method == "official-monetary-policy-rss-channel"
        for item in items
    )
    assert all(
        item.extraction_version == FED_MONETARY_RSS_ADAPTER_VERSION
        for item in items
    )
    assert all(
        item.relevance_confidence_0_1 == 1
        for item in items
    )


def test_fed_monetary_rss_rejects_missing_identity_or_publication() -> None:
    broken = FED_RSS.replace(
        "<guid>fed-2026-09-16-a</guid>",
        "",
    ).replace(
        "<link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm</link>",
        "<link></link>",
        1,
    )

    with pytest.raises(ValueError, match="missing title/id/pubDate"):
        parse_fed_monetary_rss(
            broken,
            fetched_at_ms=_ms("2026-09-24T04:00:00+00:00"),
            source_timestamp_ms=_ms("2026-09-23T18:00:00+00:00"),
        )



def test_fred_cpi_calendar_is_secondary_and_central_time() -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")
    parsed = parse_fred_release_calendar_html(
        FRED_CPI_HTML,
        release_id=FRED_CPI_RELEASE_ID,
        year=2026,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=fetched_at_ms - 1_000,
    )

    assert len(parsed.events) == 3
    assert parsed.events[0].scheduled_at_ms == _ms(
        "2026-01-13T07:30:00-06:00"
    )
    assert parsed.events[1].scheduled_at_ms == _ms(
        "2026-10-14T07:30:00-05:00"
    )
    assert all(
        event.category is EventCategory.INFLATION
        for event in parsed.events
    )
    assert all(
        event.source_quality is EventSourceQuality.SECONDARY_AGGREGATOR
        for event in parsed.events
    )
    assert all(
        event.source_provider == FRED_CPI_PROVIDER
        for event in parsed.events
    )
    assert all(event.affected_assets == () for event in parsed.events)
    assert all(
        event.adapter_version == FRED_CALENDAR_ADAPTER_VERSION
        for event in parsed.events
    )
    assert parsed.coverage.categories == (EventCategory.INFLATION,)
    assert (
        parsed.coverage.source_quality
        is EventSourceQuality.SECONDARY_AGGREGATOR
    )
    assert parsed.coverage.source_provider == FRED_CPI_PROVIDER


def test_fred_employment_calendar_is_separate_secondary_channel() -> None:
    fetched_at_ms = _ms("2026-09-24T05:00:00+00:00")
    parsed = parse_fred_release_calendar_html(
        FRED_EMPLOYMENT_HTML,
        release_id=FRED_EMPLOYMENT_RELEASE_ID,
        year=2026,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=fetched_at_ms - 1_000,
    )

    assert len(parsed.events) == 3
    assert all(
        event.category is EventCategory.EMPLOYMENT
        for event in parsed.events
    )
    assert all(
        event.source_provider == FRED_EMPLOYMENT_PROVIDER
        for event in parsed.events
    )
    assert parsed.coverage.categories == (EventCategory.EMPLOYMENT,)
    assert parsed.coverage.source_provider == FRED_EMPLOYMENT_PROVIDER


def test_fred_calendar_fails_closed_without_central_time_contract() -> None:
    broken = FRED_CPI_HTML.replace(
        "All times are US Central Time.",
        "Time zone unavailable.",
    )

    with pytest.raises(ValueError, match="Central Time contract"):
        parse_fred_release_calendar_html(
            broken,
            release_id=FRED_CPI_RELEASE_ID,
            year=2026,
            fetched_at_ms=_ms("2026-09-24T05:00:00+00:00"),
            source_timestamp_ms=_ms("2026-09-24T04:59:00+00:00"),
        )


def test_fred_calendar_endpoints_are_release_scoped() -> None:
    assert fred_release_calendar_endpoint(
        release_id=FRED_CPI_RELEASE_ID,
        year=2026,
    ) == "https://fred.stlouisfed.org/releases/calendar?rid=10&y=2026"
    assert fred_release_calendar_endpoint(
        release_id=FRED_EMPLOYMENT_RELEASE_ID,
        year=2026,
    ) == "https://fred.stlouisfed.org/releases/calendar?rid=50&y=2026"

    with pytest.raises(ValueError, match="unsupported FRED"):
        fred_release_calendar_endpoint(release_id=999, year=2026)
