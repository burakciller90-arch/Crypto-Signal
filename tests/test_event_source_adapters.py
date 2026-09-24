from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_signal.data.event_source_adapters import (
    BLS_CALENDAR_ADAPTER_VERSION,
    FED_MONETARY_RSS_ADAPTER_VERSION,
    parse_bls_calendar_ics,
    parse_fed_monetary_rss,
)
from crypto_signal.data.event_risk import EventCategory, EventSourceQuality
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
