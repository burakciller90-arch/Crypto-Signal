from __future__ import annotations

import csv
import io
import time
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
    CBOE_VIX_CHANNEL,
    CBOE_VIX_PROVIDER,
    CBOE_VIX_SOURCE,
    CBOE_VIX_SYMBOL,
    CrossMarketSourceSnapshot,
)
from crypto_signal.data.models import DataSource


class CboeVixDailyAdapter:
    URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    ADAPTER_VERSION = "cboe-vix-daily/2"
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
            raise ValueError("Cboe VIX sessions must be between 3 and 64")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.get(
                self.URL,
                headers={
                    "Accept": "text/csv,*/*",
                    "User-Agent": self.USER_AGENT,
                },
                follow_redirects=True,
            )
            response.raise_for_status()
            payload_bytes = response.content
            text = response.text.lstrip("\ufeff")
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        parsed: list[tuple[date, Decimal]] = []
        for row in csv.DictReader(io.StringIO(text)):
            raw_date = (row.get("DATE") or row.get("Date") or "").strip()
            raw_close = (row.get("CLOSE") or row.get("Close") or "").strip()
            if not raw_date or not raw_close:
                continue
            day = datetime.strptime(raw_date + " +0000", "%m/%d/%Y %z").date()
            if end_date is not None and day > end_date:
                continue
            parsed.append((day, Decimal(raw_close)))

        parsed.sort(key=lambda item: item[0])
        if len(parsed) < sessions:
            raise ValueError("Cboe VIX response has insufficient session history")
        if len({day for day, _ in parsed}) != len(parsed):
            raise ValueError("Cboe VIX response contains duplicate session dates")

        records = tuple(
            build_cross_market_daily_record(
                series=CrossMarketSeries.CBOE_VIX_CLOSE,
                unit=CrossMarketUnit.INDEX_POINTS,
                day_start_ms=_day_start_ms(day),
                value=value,
            )
            for day, value in parsed[-sessions:]
        )
        observation = build_cross_market_window_observation(
            series=CrossMarketSeries.CBOE_VIX_CLOSE,
            unit=CrossMarketUnit.INDEX_POINTS,
            observed_at_ms=observed_at_ms,
            records=records,
            source=DataSource.REST,
            adapter_version=self.ADAPTER_VERSION,
        )
        return CrossMarketSourceSnapshot(
            provider=CBOE_VIX_PROVIDER,
            source=CBOE_VIX_SOURCE,
            channel=CBOE_VIX_CHANNEL,
            symbol=CBOE_VIX_SYMBOL,
            requested_url=self.URL,
            response_url=str(response.url),
            http_status=response.status_code,
            content_type=response.headers.get("content-type", "text/csv"),
            payload_bytes=payload_bytes,
            observation=observation,
        )


def _day_start_ms(day: date) -> int:
    return int(
        datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000
    )
