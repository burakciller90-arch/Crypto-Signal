from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from crypto_signal.data.adapters.alternative_fear_greed import (
    AlternativeFearGreedAdapter,
)
from crypto_signal.data.adapters.wikimedia_pageviews import (
    WikimediaBitcoinPageviewsAdapter,
)
from crypto_signal.data.sentiment_attention import SentimentClassification


def test_alternative_fear_greed_adapter_normalizes_public_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/fng/"
        assert request.url.params["limit"] == "1"
        assert request.url.params["format"] == "json"
        assert "Authorization" not in request.headers
        assert request.headers["User-Agent"].startswith("Crypto-Signal/")
        return httpx.Response(
            200,
            json={
                "name": "Fear and Greed Index",
                "data": [
                    {
                        "value": "23",
                        "value_classification": "Extreme Fear",
                        "timestamp": "1700000000",
                        "time_until_update": "100",
                    }
                ],
                "metadata": {"error": None},
            },
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await AlternativeFearGreedAdapter(client).fetch_snapshot()

    snapshot = asyncio.run(run())

    assert snapshot.value == 23
    assert snapshot.classification is SentimentClassification.EXTREME_FEAR
    assert snapshot.provider_timestamp_ms == 1_700_000_000_000
    assert snapshot.observed_at_ms >= snapshot.provider_timestamp_ms
    assert snapshot.attribution == "alternative.me"


def test_alternative_fear_greed_adapter_rejects_provider_error_or_unknown_class() -> None:
    async def fetch(payload: dict[str, object]):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await AlternativeFearGreedAdapter(client).fetch_snapshot()

    with pytest.raises(ValueError, match="API error"):
        asyncio.run(
            fetch(
                {
                    "data": [],
                    "metadata": {"error": "unavailable"},
                }
            )
        )

    with pytest.raises(ValueError, match="classification"):
        asyncio.run(
            fetch(
                {
                    "data": [
                        {
                            "value": "50",
                            "value_classification": "Unknown",
                            "timestamp": "1700000000",
                        }
                    ],
                    "metadata": {"error": None},
                }
            )
        )


def test_wikimedia_adapter_normalizes_daily_bitcoin_attention_window() -> None:
    end = date(2026, 9, 19)
    start = end - timedelta(days=9)
    rows = []
    for offset in range(10):
        current = start + timedelta(days=offset)
        rows.append(
            {
                "project": "en.wikipedia",
                "article": "Bitcoin",
                "granularity": "daily",
                "timestamp": current.strftime("%Y%m%d00"),
                "access": "all-access",
                "agent": "user",
                "views": 10_000 + offset,
            }
        )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "Authorization" not in request.headers
        assert request.headers["User-Agent"].startswith("Crypto-Signal/")
        assert request.url.path.endswith(
            "/en.wikipedia.org/all-access/user/Bitcoin/daily/"
            "20260910/20260919"
        )
        return httpx.Response(200, json={"items": rows})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await WikimediaBitcoinPageviewsAdapter(client).fetch_daily_window(
                days=10,
                end_date=end,
            )

    observation = asyncio.run(run())

    assert observation.project == "en.wikipedia.org"
    assert observation.article == "Bitcoin"
    assert len(observation.records) == 10
    assert observation.records[0].views == 10_000
    assert observation.records[-1].views == 10_009
    assert observation.records[0].day_start_ms < observation.records[-1].day_start_ms


def test_wikimedia_adapter_rejects_incomplete_or_mismatched_response() -> None:
    end = date(2026, 9, 19)
    start = end - timedelta(days=8)
    rows = [
        {
            "project": "en.wikipedia",
            "article": "Bitcoin",
            "granularity": "daily",
            "timestamp": (start + timedelta(days=offset)).strftime("%Y%m%d00"),
            "access": "all-access",
            "agent": "user",
            "views": 1_000,
        }
        for offset in range(9)
    ]

    async def fetch(payload: object):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await WikimediaBitcoinPageviewsAdapter(client).fetch_daily_window(
                days=10,
                end_date=end,
            )

    with pytest.raises(ValueError, match="every requested day"):
        asyncio.run(fetch({"items": rows}))

    full_rows = rows + [
        {
            "project": "en.wikipedia",
            "article": "Ethereum",
            "granularity": "daily",
            "timestamp": end.strftime("%Y%m%d00"),
            "access": "all-access",
            "agent": "user",
            "views": 1_000,
        }
    ]
    with pytest.raises(ValueError, match="article mismatch"):
        asyncio.run(fetch({"items": full_rows}))


def test_wikimedia_adapter_rejects_unbounded_or_incomplete_date_requests() -> None:
    adapter = WikimediaBitcoinPageviewsAdapter()

    with pytest.raises(ValueError, match="between 10 and 30"):
        asyncio.run(adapter.fetch_daily_window(days=9))

    with pytest.raises(ValueError, match="completed UTC day"):
        asyncio.run(
            adapter.fetch_daily_window(
                days=10,
                end_date=datetime.now(UTC).date() + timedelta(days=1),
            )
        )
