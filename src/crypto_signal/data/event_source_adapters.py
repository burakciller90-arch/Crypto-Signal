from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from crypto_signal.data.event_risk import (
    EventCalendarCoverage,
    EventCategory,
    EventSourceQuality,
    StructuredEventObservation,
    build_event_calendar_coverage,
    build_structured_event_observation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.news_events import (
    NewsEventObservation,
    build_news_event_observation,
)

BLS_CALENDAR_ENDPOINT = "https://www.bls.gov/schedule/news_release/bls.ics"
FED_MONETARY_RSS_ENDPOINT = (
    "https://www.federalreserve.gov/feeds/press_monetary.xml"
)
BLS_CALENDAR_ADAPTER_VERSION = "bls-calendar-ics-v1/1"
FED_MONETARY_RSS_ADAPTER_VERSION = "fed-monetary-rss-v1/1"


@dataclass(frozen=True, slots=True)
class ParsedBlsCalendar:
    coverage: EventCalendarCoverage
    events: tuple[StructuredEventObservation, ...]


def parse_bls_calendar_ics(
    payload: str,
    *,
    fetched_at_ms: int,
    source_timestamp_ms: int,
) -> ParsedBlsCalendar:
    if fetched_at_ms < 0 or source_timestamp_ms < 0:
        raise ValueError("BLS calendar timestamps cannot be negative")
    if source_timestamp_ms > fetched_at_ms:
        raise ValueError("BLS source timestamp cannot postdate fetch")
    lines = _unfold_ics_lines(payload)
    raw_events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            if current is not None:
                raise ValueError("nested BLS VEVENT is invalid")
            current = {}
            continue
        if line == "END:VEVENT":
            if current is None:
                raise ValueError("BLS VEVENT end without start")
            raw_events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key] = value
    if current is not None:
        raise ValueError("unterminated BLS VEVENT")
    if not raw_events:
        raise ValueError("BLS calendar contains no events")

    parsed: list[StructuredEventObservation] = []
    for raw in raw_events:
        status = _first_ics_value(raw, "STATUS")
        if status is not None and status.upper() == "CANCELLED":
            continue
        uid = _required_ics_value(raw, "UID")
        summary = _unescape_ics_text(_required_ics_value(raw, "SUMMARY"))
        dt_key, dt_value = _required_ics_property(raw, "DTSTART")
        scheduled_at_ms = _parse_ics_datetime_ms(dt_key, dt_value)
        category = _bls_category(summary)
        parsed.append(
            build_structured_event_observation(
                provider_event_id=uid,
                title=summary,
                category=category,
                scheduled_at_ms=scheduled_at_ms,
                affected_assets=(),
                source_provider="bls.gov",
                source_quality=EventSourceQuality.OFFICIAL,
                source=DataSource.REST,
                source_timestamp_ms=source_timestamp_ms,
                ingested_at_ms=fetched_at_ms,
                adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
            )
        )

    if not parsed:
        raise ValueError("BLS calendar has no active events")
    events = tuple(
        sorted(
            parsed,
            key=lambda item: (
                item.scheduled_at_ms,
                item.provider_event_id,
                item.event_identity,
            ),
        )
    )
    provider_ids = tuple(item.provider_event_id for item in events)
    if len(set(provider_ids)) != len(provider_ids):
        raise ValueError("BLS calendar contains duplicate event UID")

    categories = tuple(
        sorted({item.category for item in events}, key=lambda item: item.value)
    )
    coverage = build_event_calendar_coverage(
        coverage_start_ms=min(item.scheduled_at_ms for item in events),
        coverage_end_ms=max(item.scheduled_at_ms for item in events),
        categories=categories,
        source_provider="bls.gov",
        source_quality=EventSourceQuality.OFFICIAL,
        source=DataSource.REST,
        observed_at_ms=fetched_at_ms,
        adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
    )
    return ParsedBlsCalendar(coverage=coverage, events=events)


def parse_fed_monetary_rss(
    payload: str,
    *,
    fetched_at_ms: int,
    source_timestamp_ms: int,
) -> tuple[NewsEventObservation, ...]:
    if fetched_at_ms < 0 or source_timestamp_ms < 0:
        raise ValueError("Fed RSS timestamps cannot be negative")
    if source_timestamp_ms > fetched_at_ms:
        raise ValueError("Fed source timestamp cannot postdate fetch")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("Fed RSS XML is invalid") from exc

    observations: list[NewsEventObservation] = []
    for item in _rss_items(root):
        title = _rss_text(item, "title")
        link = _rss_text(item, "link")
        guid = _rss_text(item, "guid")
        published = _rss_text(item, "pubDate")
        provider_article_id = guid or link
        if not title or not provider_article_id or not published:
            raise ValueError("Fed RSS item missing title/id/pubDate")
        published_at_ms = _parse_rfc2822_ms(published)
        observations.append(
            build_news_event_observation(
                provider_article_id=provider_article_id,
                event_cluster_key=provider_article_id,
                headline=title,
                category=EventCategory.CENTRAL_BANK,
                affected_assets=(),
                published_at_ms=published_at_ms,
                source_provider="federalreserve.gov",
                source_quality=EventSourceQuality.OFFICIAL,
                source=DataSource.REST,
                source_timestamp_ms=max(
                    published_at_ms,
                    source_timestamp_ms,
                ),
                ingested_at_ms=fetched_at_ms,
                extraction_method="official-monetary-policy-rss-channel",
                extraction_version=FED_MONETARY_RSS_ADAPTER_VERSION,
                relevance_confidence_0_1=Decimal(1),
                adapter_version=FED_MONETARY_RSS_ADAPTER_VERSION,
            )
        )

    if not observations:
        raise ValueError("Fed monetary RSS contains no items")
    result = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.published_at_ms,
                item.provider_article_id,
                item.news_identity,
            ),
        )
    )
    ids = tuple(item.provider_article_id for item in result)
    if len(set(ids)) != len(ids):
        raise ValueError("Fed monetary RSS contains duplicate article identity")
    return result


def _bls_category(summary: str) -> EventCategory:
    normalized = " ".join(summary.casefold().split())
    inflation_terms = (
        "consumer price index",
        "producer price index",
        "import and export price",
        "consumer prices",
        "producer prices",
    )
    employment_terms = (
        "employment situation",
        "job openings",
        "labor turnover",
        "unemployment",
        "employment cost index",
        "real earnings",
    )
    if any(term in normalized for term in inflation_terms):
        return EventCategory.INFLATION
    if any(term in normalized for term in employment_terms):
        return EventCategory.EMPLOYMENT
    return EventCategory.OTHER


def _unfold_ics_lines(payload: str) -> tuple[str, ...]:
    physical = payload.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    logical: list[str] = []
    for line in physical:
        if not line:
            continue
        if line[0] in {" ", "\t"}:
            if not logical:
                raise ValueError("BLS ICS starts with folded continuation")
            logical[-1] += line[1:]
        else:
            logical.append(line)
    return tuple(logical)


def _required_ics_value(raw: dict[str, str], name: str) -> str:
    value = _first_ics_value(raw, name)
    if value is None or not value.strip():
        raise ValueError(f"BLS ICS missing {name}")
    return value.strip()


def _required_ics_property(
    raw: dict[str, str],
    name: str,
) -> tuple[str, str]:
    for key, value in raw.items():
        if key == name or key.startswith(f"{name};"):
            if not value.strip():
                break
            return key, value.strip()
    raise ValueError(f"BLS ICS missing {name}")


def _first_ics_value(raw: dict[str, str], name: str) -> str | None:
    for key, value in raw.items():
        if key == name or key.startswith(f"{name};"):
            return value.strip()
    return None


def _parse_ics_datetime_ms(key: str, value: str) -> int:
    parameters = {
        part.split("=", 1)[0].upper(): part.split("=", 1)[1]
        for part in key.split(";")[1:]
        if "=" in part
    }
    if len(value) == 8 and value.isdigit():
        dt = datetime.strptime(value, "%Y%m%d").replace(
            tzinfo=ZoneInfo(parameters.get("TZID", "America/New_York"))
        )
    elif value.endswith("Z"):
        body = value[:-1]
        fmt = "%Y%m%dT%H%M%S" if len(body) == 15 else "%Y%m%dT%H%M"
        dt = datetime.strptime(body, fmt).replace(tzinfo=UTC)
    else:
        fmt = "%Y%m%dT%H%M%S" if len(value) == 15 else "%Y%m%dT%H%M"
        dt = datetime.strptime(value, fmt).replace(
            tzinfo=ZoneInfo(parameters.get("TZID", "America/New_York"))
        )
    return int(dt.timestamp() * 1000)


def _unescape_ics_text(value: str) -> str:
    return (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _rss_items(root: ET.Element) -> tuple[ET.Element, ...]:
    return tuple(
        element
        for element in root.iter()
        if _local_name(element.tag) == "item"
    )


def _rss_text(item: ET.Element, name: str) -> str:
    for child in item:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_rfc2822_ms(value: str) -> int:
    dt = email.utils.parsedate_to_datetime(value)
    if dt is None:
        raise ValueError("RSS pubDate cannot be parsed")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)
