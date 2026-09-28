from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from crypto_signal.data.cross_market import (
    CrossMarketSeries,
    CrossMarketUnit,
    CrossMarketWindowObservation,
    build_cross_market_daily_record,
    build_cross_market_window_observation,
)
from crypto_signal.data.cross_market_source_contract import (
    TREASURY_10Y_CHANNEL,
    TREASURY_10Y_PROVIDER,
    TREASURY_10Y_SOURCE,
    TREASURY_10Y_SYMBOL,
    CrossMarketSourceSnapshot,
)
from crypto_signal.data.models import DataSource


class Treasury10YDailyAdapter:
    URL = "https://home.treasury.gov/sites/default/files/interest-rates/yield.xml"
    ADAPTER_VERSION = "us-treasury-10y-daily/2"
    USER_AGENT = (
        "Crypto-Signal/1.0 "
        "(public market intelligence; github.com/burakciller90-arch/Crypto-Signal)"
    )

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_window(
        self,
        *,
        sessions: int = 10,
        end_date: date | None = None,
    ) -> CrossMarketWindowObservation:
        snapshot = await self.fetch_source_snapshot(
            sessions=sessions,
            end_date=end_date,
        )
        return snapshot.observation

    async def fetch_source_snapshot(
        self,
        *,
        sessions: int = 10,
        end_date: date | None = None,
    ) -> CrossMarketSourceSnapshot:
        if not 3 <= sessions <= 64:
            raise ValueError("Treasury 10Y sessions must be between 3 and 64")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.get(
                self.URL,
                headers={
                    "Accept": "application/xml,text/xml,*/*",
                    "User-Agent": self.USER_AGENT,
                },
                follow_redirects=True,
            )
            response.raise_for_status()
            payload_bytes = response.content
            root = ET.fromstring(payload_bytes)
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        parsed: list[tuple[date, Decimal]] = []
        for group in root.iter():
            if _local_name(group.tag) != "G_NEW_DATE":
                continue
            values: dict[str, str] = {}
            for node in group.iter():
                local = _local_name(node.tag)
                text = (node.text or "").strip()
                if text:
                    values[local] = text
            raw_day = values.get("NEW_DATE") or values.get("BID_CURVE_DATE")
            raw_10y = values.get("BC_10YEAR")
            if not raw_day or not raw_10y:
                continue
            day = _parse_day(raw_day)
            if end_date is not None and day > end_date:
                continue
            parsed.append((day, Decimal(raw_10y)))

        parsed.sort(key=lambda item: item[0])
        if len(parsed) < sessions:
            raise ValueError("Treasury 10Y response has insufficient session history")
        if len({day for day, _ in parsed}) != len(parsed):
            raise ValueError("Treasury 10Y response contains duplicate session dates")

        records = tuple(
            build_cross_market_daily_record(
                series=CrossMarketSeries.US_TREASURY_10Y_YIELD,
                unit=CrossMarketUnit.PERCENT,
                day_start_ms=_day_start_ms(day),
                value=value,
            )
            for day, value in parsed[-sessions:]
        )
        observation = build_cross_market_window_observation(
            series=CrossMarketSeries.US_TREASURY_10Y_YIELD,
            unit=CrossMarketUnit.PERCENT,
            observed_at_ms=observed_at_ms,
            records=records,
            source=DataSource.REST,
            adapter_version=self.ADAPTER_VERSION,
        )
        return CrossMarketSourceSnapshot(
            provider=TREASURY_10Y_PROVIDER,
            source=TREASURY_10Y_SOURCE,
            channel=TREASURY_10Y_CHANNEL,
            symbol=TREASURY_10Y_SYMBOL,
            requested_url=self.URL,
            response_url=str(response.url),
            http_status=response.status_code,
            content_type=response.headers.get(
                "content-type",
                "application/xml",
            ),
            payload_bytes=payload_bytes,
            observation=observation,
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_day(raw: str) -> date:
    parsers: tuple[Callable[[], date], ...] = (
        lambda: datetime.fromisoformat(raw).date(),
        lambda: datetime.strptime(raw + " +0000", "%m/%d/%Y %z").date(),
        lambda: datetime.strptime(raw + " +0000", "%m-%d-%Y %z").date(),
        lambda: datetime.strptime(raw + " +0000", "%d-%b-%y %z").date(),
        lambda: datetime.strptime(raw + " +0000", "%Y-%m-%d %z").date(),
    )
    for parser in parsers:
        try:
            return parser()
        except ValueError:
            pass
    raise ValueError(f"unsupported Treasury date: {raw!r}")


def _day_start_ms(day: date) -> int:
    return int(
        datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000
    )
