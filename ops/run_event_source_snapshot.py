from __future__ import annotations

import argparse
import email.utils
import fcntl
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from crypto_signal.data.event_source_adapters import (
    BLS_CALENDAR_ADAPTER_VERSION,
    BLS_CALENDAR_ENDPOINT,
    FED_MONETARY_RSS_ADAPTER_VERSION,
    FED_MONETARY_RSS_ENDPOINT,
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
from crypto_signal.data.event_source_runtime import (
    EventSourceFetchObservation,
    EventSourceFetchOutcome,
    EventSourceKind,
    EventSourceRawPayload,
    EventSourceRuntimeStore,
    EventSourceTimestampBasis,
    build_event_source_fetch_observation,
    build_event_source_raw_payload,
)

DEFAULT_EVENT_SOURCE_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/events/"
    "event_source.sqlite3"
)
DEFAULT_EVENT_SOURCE_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/events/"
    "event_source_snapshot.lock"
)
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "Crypto-Signal/1.1 EventSourceRuntime (+https://github.com/burakciller90-arch)"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class EventSourceCycleResult:
    fetches: tuple[EventSourceFetchObservation, ...]

    @property
    def failure_count(self) -> int:
        return sum(
            fetch.outcome is EventSourceFetchOutcome.FAILURE
            for fetch in self.fetches
        )

    @property
    def required_calendar_coverage_satisfied(self) -> bool:
        successful_calendar_providers = {
            fetch.source_provider
            for fetch in self.fetches
            if (
                fetch.source_kind is EventSourceKind.CALENDAR
                and fetch.outcome is EventSourceFetchOutcome.SUCCESS
            )
        }
        return (
            "bls.gov" in successful_calendar_providers
            or {
                FRED_CPI_PROVIDER,
                FRED_EMPLOYMENT_PROVIDER,
            }.issubset(successful_calendar_providers)
        )

    @property
    def required_news_coverage_satisfied(self) -> bool:
        return any(
            fetch.source_provider == "federalreserve.gov"
            and fetch.source_kind is EventSourceKind.NEWS
            and fetch.outcome is EventSourceFetchOutcome.SUCCESS
            for fetch in self.fetches
        )

    @property
    def required_coverage_satisfied(self) -> bool:
        return (
            self.required_calendar_coverage_satisfied
            and self.required_news_coverage_satisfied
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_EVENT_SOURCE_DB,
        help="append-only Event Source runtime SQLite path",
    )
    parser.add_argument(
        "--lock-path",
        type=Path,
        default=DEFAULT_EVENT_SOURCE_LOCK,
        help="single-writer lock for the canonical Event Source snapshot clock",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    return parser.parse_args()


def collect_event_source_cycle(
    *,
    store: EventSourceRuntimeStore,
    client: httpx.Client,
    fetched_at_ms: int | None = None,
) -> EventSourceCycleResult:
    observation_ms = (
        time.time_ns() // 1_000_000
        if fetched_at_ms is None
        else fetched_at_ms
    )
    if observation_ms < 0:
        raise ValueError("event source observation time cannot be negative")

    bls_fetch = _collect_bls_calendar(
        store=store,
        client=client,
        fetched_at_ms=observation_ms,
    )
    calendar_fallbacks: tuple[EventSourceFetchObservation, ...] = ()
    if bls_fetch.outcome is EventSourceFetchOutcome.FAILURE:
        year = datetime.fromtimestamp(
            observation_ms / 1000,
            tz=UTC,
        ).year
        calendar_fallbacks = (
            _collect_fred_calendar(
                store=store,
                client=client,
                fetched_at_ms=observation_ms,
                release_id=FRED_CPI_RELEASE_ID,
                year=year,
            ),
            _collect_fred_calendar(
                store=store,
                client=client,
                fetched_at_ms=observation_ms,
                release_id=FRED_EMPLOYMENT_RELEASE_ID,
                year=year,
            ),
        )
    fed_fetch = _collect_fed_monetary_news(
        store=store,
        client=client,
        fetched_at_ms=observation_ms,
    )
    return EventSourceCycleResult(
        fetches=(bls_fetch, *calendar_fallbacks, fed_fetch)
    )


def _collect_bls_calendar(
    *,
    store: EventSourceRuntimeStore,
    client: httpx.Client,
    fetched_at_ms: int,
) -> EventSourceFetchObservation:
    try:
        response = client.get(BLS_CALENDAR_ENDPOINT)
    except httpx.HTTPError:
        fetch = _failure_fetch(
            provider="bls.gov",
            kind=EventSourceKind.CALENDAR,
            endpoint=BLS_CALENDAR_ENDPOINT,
            adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=None,
            reason_code="network_error",
        )
        store.append_failed_fetch(fetch=fetch)
        return fetch

    raw = _raw_payload_or_none(response)
    source_timestamp_ms, basis = _source_timestamp(
        response,
        fetched_at_ms=fetched_at_ms,
    )
    if response.status_code != 200:
        fetch = _failure_fetch(
            provider="bls.gov",
            kind=EventSourceKind.CALENDAR,
            endpoint=BLS_CALENDAR_ENDPOINT,
            adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=response.status_code,
            reason_code=f"http_status_{response.status_code}",
            raw_payload=raw,
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch, raw_payload=raw)
        return fetch
    if raw is None:
        fetch = _failure_fetch(
            provider="bls.gov",
            kind=EventSourceKind.CALENDAR,
            endpoint=BLS_CALENDAR_ENDPOINT,
            adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=200,
            reason_code="empty_or_invalid_text_payload",
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch)
        return fetch

    try:
        parsed = parse_bls_calendar_ics(
            raw.payload_bytes.decode(raw.text_encoding),
            fetched_at_ms=fetched_at_ms,
            source_timestamp_ms=source_timestamp_ms,
        )
    except (UnicodeError, ValueError):
        fetch = _failure_fetch(
            provider="bls.gov",
            kind=EventSourceKind.CALENDAR,
            endpoint=BLS_CALENDAR_ENDPOINT,
            adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=200,
            reason_code="parse_error",
            raw_payload=raw,
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch, raw_payload=raw)
        return fetch

    fetch = build_event_source_fetch_observation(
        source_provider="bls.gov",
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url=BLS_CALENDAR_ENDPOINT,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source_timestamp_basis=basis,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=tuple(
            event.event_identity for event in parsed.events
        ),
        coverage_identity=parsed.coverage.coverage_identity,
        adapter_version=BLS_CALENDAR_ADAPTER_VERSION,
    )
    store.append_calendar_snapshot(
        raw_payload=raw,
        coverage=parsed.coverage,
        events=parsed.events,
        fetch=fetch,
    )
    return fetch


def _collect_fred_calendar(
    *,
    store: EventSourceRuntimeStore,
    client: httpx.Client,
    fetched_at_ms: int,
    release_id: int,
    year: int,
) -> EventSourceFetchObservation:
    if release_id == FRED_CPI_RELEASE_ID:
        provider = FRED_CPI_PROVIDER
    elif release_id == FRED_EMPLOYMENT_RELEASE_ID:
        provider = FRED_EMPLOYMENT_PROVIDER
    else:
        raise ValueError("unsupported FRED fallback release")
    endpoint = fred_release_calendar_endpoint(
        release_id=release_id,
        year=year,
    )
    try:
        response = client.get(endpoint)
    except httpx.HTTPError:
        fetch = _failure_fetch(
            provider=provider,
            kind=EventSourceKind.CALENDAR,
            endpoint=endpoint,
            adapter_version=FRED_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=None,
            reason_code="network_error",
        )
        store.append_failed_fetch(fetch=fetch)
        return fetch

    raw = _raw_payload_or_none(response)
    source_timestamp_ms, basis = _source_timestamp(
        response,
        fetched_at_ms=fetched_at_ms,
    )
    if response.status_code != 200:
        fetch = _failure_fetch(
            provider=provider,
            kind=EventSourceKind.CALENDAR,
            endpoint=endpoint,
            adapter_version=FRED_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=response.status_code,
            reason_code=f"http_status_{response.status_code}",
            raw_payload=raw,
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch, raw_payload=raw)
        return fetch
    if raw is None:
        fetch = _failure_fetch(
            provider=provider,
            kind=EventSourceKind.CALENDAR,
            endpoint=endpoint,
            adapter_version=FRED_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=200,
            reason_code="empty_or_invalid_text_payload",
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch)
        return fetch

    try:
        parsed = parse_fred_release_calendar_html(
            raw.payload_bytes.decode(raw.text_encoding),
            release_id=release_id,
            year=year,
            fetched_at_ms=fetched_at_ms,
            source_timestamp_ms=source_timestamp_ms,
        )
    except (UnicodeError, ValueError):
        fetch = _failure_fetch(
            provider=provider,
            kind=EventSourceKind.CALENDAR,
            endpoint=endpoint,
            adapter_version=FRED_CALENDAR_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=200,
            reason_code="parse_error",
            raw_payload=raw,
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch, raw_payload=raw)
        return fetch

    fetch = build_event_source_fetch_observation(
        source_provider=provider,
        source_kind=EventSourceKind.CALENDAR,
        endpoint_url=endpoint,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source_timestamp_basis=basis,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=tuple(
            event.event_identity for event in parsed.events
        ),
        coverage_identity=parsed.coverage.coverage_identity,
        adapter_version=FRED_CALENDAR_ADAPTER_VERSION,
    )
    store.append_calendar_snapshot(
        raw_payload=raw,
        coverage=parsed.coverage,
        events=parsed.events,
        fetch=fetch,
    )
    return fetch


def _collect_fed_monetary_news(
    *,
    store: EventSourceRuntimeStore,
    client: httpx.Client,
    fetched_at_ms: int,
) -> EventSourceFetchObservation:
    try:
        response = client.get(FED_MONETARY_RSS_ENDPOINT)
    except httpx.HTTPError:
        fetch = _failure_fetch(
            provider="federalreserve.gov",
            kind=EventSourceKind.NEWS,
            endpoint=FED_MONETARY_RSS_ENDPOINT,
            adapter_version=FED_MONETARY_RSS_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=None,
            reason_code="network_error",
        )
        store.append_failed_fetch(fetch=fetch)
        return fetch

    raw = _raw_payload_or_none(response)
    source_timestamp_ms, basis = _source_timestamp(
        response,
        fetched_at_ms=fetched_at_ms,
    )
    if response.status_code != 200:
        fetch = _failure_fetch(
            provider="federalreserve.gov",
            kind=EventSourceKind.NEWS,
            endpoint=FED_MONETARY_RSS_ENDPOINT,
            adapter_version=FED_MONETARY_RSS_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=response.status_code,
            reason_code=f"http_status_{response.status_code}",
            raw_payload=raw,
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch, raw_payload=raw)
        return fetch
    if raw is None:
        fetch = _failure_fetch(
            provider="federalreserve.gov",
            kind=EventSourceKind.NEWS,
            endpoint=FED_MONETARY_RSS_ENDPOINT,
            adapter_version=FED_MONETARY_RSS_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=200,
            reason_code="empty_or_invalid_text_payload",
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch)
        return fetch

    try:
        events = parse_fed_monetary_rss(
            raw.payload_bytes.decode(raw.text_encoding),
            fetched_at_ms=fetched_at_ms,
            source_timestamp_ms=source_timestamp_ms,
        )
    except (UnicodeError, ValueError):
        fetch = _failure_fetch(
            provider="federalreserve.gov",
            kind=EventSourceKind.NEWS,
            endpoint=FED_MONETARY_RSS_ENDPOINT,
            adapter_version=FED_MONETARY_RSS_ADAPTER_VERSION,
            fetched_at_ms=fetched_at_ms,
            http_status=200,
            reason_code="parse_error",
            raw_payload=raw,
            source_timestamp_ms=source_timestamp_ms,
            source_timestamp_basis=basis,
        )
        store.append_failed_fetch(fetch=fetch, raw_payload=raw)
        return fetch

    fetch = build_event_source_fetch_observation(
        source_provider="federalreserve.gov",
        source_kind=EventSourceKind.NEWS,
        endpoint_url=FED_MONETARY_RSS_ENDPOINT,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source_timestamp_basis=basis,
        http_status=200,
        outcome=EventSourceFetchOutcome.SUCCESS,
        raw_payload_sha256=raw.payload_sha256,
        raw_payload_bytes=raw.content_bytes,
        item_identities=tuple(event.news_identity for event in events),
        adapter_version=FED_MONETARY_RSS_ADAPTER_VERSION,
    )
    store.append_news_snapshot(
        raw_payload=raw,
        events=events,
        fetch=fetch,
    )
    return fetch


def _raw_payload_or_none(
    response: httpx.Response,
) -> EventSourceRawPayload | None:
    if not response.content:
        return None
    encoding = response.encoding or "utf-8"
    content_type = response.headers.get(
        "content-type",
        "application/octet-stream",
    )
    try:
        return build_event_source_raw_payload(
            payload_bytes=response.content,
            content_type=content_type,
            text_encoding=encoding,
        )
    except ValueError:
        return None


def _source_timestamp(
    response: httpx.Response,
    *,
    fetched_at_ms: int,
) -> tuple[int, EventSourceTimestampBasis]:
    for header, basis in (
        (
            "last-modified",
            EventSourceTimestampBasis.HTTP_LAST_MODIFIED,
        ),
        ("date", EventSourceTimestampBasis.HTTP_DATE),
    ):
        value = response.headers.get(header)
        parsed = _parse_http_timestamp_ms(value)
        if parsed is not None and 0 <= parsed <= fetched_at_ms:
            return parsed, basis
    return fetched_at_ms, EventSourceTimestampBasis.FETCH_TIME_FALLBACK


def _parse_http_timestamp_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)


def _failure_fetch(
    *,
    provider: str,
    kind: EventSourceKind,
    endpoint: str,
    adapter_version: str,
    fetched_at_ms: int,
    http_status: int | None,
    reason_code: str,
    raw_payload: EventSourceRawPayload | None = None,
    source_timestamp_ms: int | None = None,
    source_timestamp_basis: EventSourceTimestampBasis | None = None,
) -> EventSourceFetchObservation:
    return build_event_source_fetch_observation(
        source_provider=provider,
        source_kind=kind,
        endpoint_url=endpoint,
        fetched_at_ms=fetched_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        source_timestamp_basis=source_timestamp_basis,
        http_status=http_status,
        outcome=EventSourceFetchOutcome.FAILURE,
        raw_payload_sha256=(
            None if raw_payload is None else raw_payload.payload_sha256
        ),
        raw_payload_bytes=(
            None if raw_payload is None else raw_payload.content_bytes
        ),
        reason_code=reason_code,
        adapter_version=adapter_version,
    )


def _require_canonical_path(path: Path, *, label: str) -> None:
    if not str(path).startswith("/Volumes/Crypto-504/"):
        raise ValueError(f"{label} must use canonical SSD path")


def run(args: argparse.Namespace) -> int:
    try:
        _require_canonical_path(args.db, label="event source db")
        _require_canonical_path(args.lock_path, label="event source lock")
    except ValueError as exc:
        print(
            f"EVENT_SOURCE_ERROR={exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.timeout_seconds <= 0 or args.timeout_seconds > 120:
        print(
            "EVENT_SOURCE_ERROR=INVALID_TIMEOUT",
            file=sys.stderr,
            flush=True,
        )
        return 2

    args.lock_path.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print(
                "RDP8_EVENT_SOURCE_SNAPSHOT_SKIPPED=LOCK_HELD "
                "REAL_CAPITAL=0",
                flush=True,
            )
            return 0

        store = EventSourceRuntimeStore(args.db)
        with httpx.Client(
            timeout=args.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/calendar, text/html, application/xhtml+xml, "
                    "application/rss+xml, application/xml, text/xml"
                ),
            },
        ) as client:
            try:
                result = collect_event_source_cycle(
                    store=store,
                    client=client,
                )
            except (OSError, sqlite3.Error, ValueError) as exc:
                print(
                    "EVENT_SOURCE_ERROR "
                    f"error={type(exc).__name__}:{exc} "
                    "FAIL_CLOSED=YES REAL_CAPITAL=0",
                    file=sys.stderr,
                    flush=True,
                )
                return 3

    for fetch in result.fetches:
        print(
            "EVENT_SOURCE_FETCH "
            f"provider={fetch.source_provider} "
            f"kind={fetch.source_kind.value} "
            f"outcome={fetch.outcome.value} "
            f"http_status={fetch.http_status} "
            f"items={len(fetch.item_identities)} "
            f"timestamp_basis={(
                fetch.source_timestamp_basis.value
                if fetch.source_timestamp_basis is not None
                else 'none'
            )} "
            f"fetch={fetch.fetch_identity}",
            flush=True,
        )
    print(
        "EVENT_SOURCE_CYCLE_COMPLETE "
        f"source_failures={result.failure_count} "
        "required_calendar_coverage="
        f"{'YES' if result.required_calendar_coverage_satisfied else 'NO'} "
        "required_news_coverage="
        f"{'YES' if result.required_news_coverage_satisfied else 'NO'} "
        f"quick_check={'YES' if store.quick_check() else 'NO'} "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0 if result.required_coverage_satisfied else 1


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
