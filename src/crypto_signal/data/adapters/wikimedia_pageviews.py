from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import cast
from urllib.parse import quote

import httpx

from crypto_signal.data.models import DataSource
from crypto_signal.data.sentiment_attention import (
    PageviewWindowObservation,
    build_pageview_daily_record,
    build_pageview_window_observation,
)


class WikimediaBitcoinPageviewsAdapter:
    BASE_URL = "https://wikimedia.org/api/rest_v1"
    ADAPTER_VERSION = "wikimedia-pageviews-bitcoin-daily/1"
    PROJECT = "en.wikipedia.org"
    ARTICLE = "Bitcoin"
    ACCESS = "all-access"
    AGENT = "user"
    USER_AGENT = (
        "Crypto-Signal/1.0 "
        "(public market intelligence; github.com/burakciller90-arch/Crypto-Signal)"
    )

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_daily_window(
        self,
        *,
        days: int = 14,
        end_date: date | None = None,
    ) -> PageviewWindowObservation:
        if not 10 <= days <= 30:
            raise ValueError("Wikimedia pageview days must be between 10 and 30")

        today_utc = datetime.now(timezone.utc).date()
        latest_complete_date = today_utc - timedelta(days=1)
        selected_end = (
            today_utc - timedelta(days=2) if end_date is None else end_date
        )
        if selected_end > latest_complete_date:
            raise ValueError("Wikimedia pageview end_date must be a completed UTC day")
        selected_start = selected_end - timedelta(days=days - 1)

        article = quote(self.ARTICLE, safe="")
        url = (
            f"{self.BASE_URL}/metrics/pageviews/per-article/"
            f"{self.PROJECT}/{self.ACCESS}/{self.AGENT}/{article}/daily/"
            f"{selected_start:%Y%m%d}/{selected_end:%Y%m%d}"
        )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.USER_AGENT,
                },
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            observed_at_ms = time.time_ns() // 1_000_000
        finally:
            if owns_client:
                await client.aclose()

        raw_rows = cast(list[dict[str, object]], payload.get("items", []))
        if len(raw_rows) != days:
            raise ValueError(
                "Wikimedia pageview response must contain every requested day"
            )

        records = []
        for row in raw_rows:
            if row.get("article") != self.ARTICLE:
                raise ValueError("Wikimedia pageview article mismatch")
            if row.get("granularity") != "daily":
                raise ValueError("Wikimedia pageview granularity mismatch")
            if row.get("access") != self.ACCESS or row.get("agent") != self.AGENT:
                raise ValueError("Wikimedia pageview access/agent mismatch")
            response_project = str(row.get("project", ""))
            if response_project not in {"en.wikipedia", self.PROJECT}:
                raise ValueError("Wikimedia pageview project mismatch")

            timestamp = str(row["timestamp"])
            if len(timestamp) != 10 or not timestamp.endswith("00"):
                raise ValueError("Wikimedia pageview timestamp must be YYYYMMDD00")
            try:
                day_start = datetime.strptime(timestamp, "%Y%m%d%H").replace(
                    tzinfo=timezone.utc
                )
            except ValueError as exc:
                raise ValueError("invalid Wikimedia pageview timestamp") from exc
            day_start_ms = int(day_start.timestamp() * 1000)
            records.append(
                build_pageview_daily_record(
                    project=self.PROJECT,
                    article=self.ARTICLE,
                    day_start_ms=day_start_ms,
                    views=int(cast(int | str, row["views"])),
                    access=self.ACCESS,
                    agent=self.AGENT,
                )
            )

        records.sort(key=lambda item: (item.day_start_ms, item.record_identity))
        return build_pageview_window_observation(
            project=self.PROJECT,
            article=self.ARTICLE,
            observed_at_ms=observed_at_ms,
            records=tuple(records),
            source=DataSource.REST,
            adapter_version=self.ADAPTER_VERSION,
        )
