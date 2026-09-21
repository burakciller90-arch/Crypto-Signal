from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.cboe_vix import CboeVixDailyAdapter
from crypto_signal.data.adapters.treasury_yields import Treasury10YDailyAdapter
from crypto_signal.data.cross_market import CrossMarketSeries


def test_cboe_vix_adapter_normalizes_public_daily_sessions() -> None:
    csv_text = """DATE,OPEN,HIGH,LOW,CLOSE
09/14/2026,15,16,14,15.5
09/15/2026,16,17,15,16.5
09/16/2026,17,18,16,17.5
09/17/2026,18,19,17,18.5
09/18/2026,19,20,18,19.5
"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "Authorization" not in request.headers
        assert request.headers["User-Agent"].startswith("Crypto-Signal/")
        return httpx.Response(200, text=csv_text)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await CboeVixDailyAdapter(client).fetch_window(
                sessions=3,
                end_date=date(2026, 9, 18),
            )

    observation = asyncio.run(run())

    assert observation.series is CrossMarketSeries.CBOE_VIX_CLOSE
    assert len(observation.records) == 3
    assert [item.value for item in observation.records] == [
        Decimal("17.5"),
        Decimal("18.5"),
        Decimal("19.5"),
    ]
    assert observation.records[0].day_start_ms < observation.records[-1].day_start_ms


def test_cboe_vix_adapter_rejects_insufficient_or_duplicate_sessions() -> None:
    async def fetch(text: str):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await CboeVixDailyAdapter(client).fetch_window(sessions=3)

    with pytest.raises(ValueError, match="insufficient"):
        asyncio.run(
            fetch(
                """DATE,CLOSE
09/17/2026,18.5
09/18/2026,19.5
"""
            )
        )

    with pytest.raises(ValueError, match="duplicate"):
        asyncio.run(
            fetch(
                """DATE,CLOSE
09/16/2026,17.5
09/17/2026,18.5
09/17/2026,18.6
09/18/2026,19.5
"""
            )
        )


def test_treasury_adapter_normalizes_actual_g_new_date_schema() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<QR_BC_CM>
  <LIST_G_NEW_DATE>
    <G_NEW_DATE><NEW_DATE>09-14-2026</NEW_DATE><BC_10YEAR>4.80</BC_10YEAR></G_NEW_DATE>
    <G_NEW_DATE><NEW_DATE>09-15-2026</NEW_DATE><BC_10YEAR>4.85</BC_10YEAR></G_NEW_DATE>
    <G_NEW_DATE><NEW_DATE>09-16-2026</NEW_DATE><BC_10YEAR>4.90</BC_10YEAR></G_NEW_DATE>
    <G_NEW_DATE><NEW_DATE>09-17-2026</NEW_DATE><BC_10YEAR>4.95</BC_10YEAR></G_NEW_DATE>
    <G_NEW_DATE><NEW_DATE>09-18-2026</NEW_DATE><BC_10YEAR>5.01</BC_10YEAR></G_NEW_DATE>
  </LIST_G_NEW_DATE>
</QR_BC_CM>
"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "Authorization" not in request.headers
        assert request.headers["User-Agent"].startswith("Crypto-Signal/")
        return httpx.Response(200, content=xml.encode())

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await Treasury10YDailyAdapter(client).fetch_window(
                sessions=3,
                end_date=date(2026, 9, 18),
            )

    observation = asyncio.run(run())

    assert observation.series is CrossMarketSeries.US_TREASURY_10Y_YIELD
    assert len(observation.records) == 3
    assert [item.value for item in observation.records] == [
        Decimal("4.90"),
        Decimal("4.95"),
        Decimal("5.01"),
    ]


def test_treasury_adapter_supports_namespaced_nested_schema() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<root xmlns:d="urn:data">
  <d:G_NEW_DATE><d:BID_CURVE_DATE>09/16/2026</d:BID_CURVE_DATE><d:BC_10YEAR>4.90</d:BC_10YEAR></d:G_NEW_DATE>
  <d:G_NEW_DATE><d:BID_CURVE_DATE>09/17/2026</d:BID_CURVE_DATE><d:BC_10YEAR>4.95</d:BC_10YEAR></d:G_NEW_DATE>
  <d:G_NEW_DATE><d:BID_CURVE_DATE>09/18/2026</d:BID_CURVE_DATE><d:BC_10YEAR>5.01</d:BC_10YEAR></d:G_NEW_DATE>
</root>
"""

    async def run():
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, content=xml.encode())
        )
        async with httpx.AsyncClient(transport=transport) as client:
            return await Treasury10YDailyAdapter(client).fetch_window(sessions=3)

    observation = asyncio.run(run())

    latest = observation.records[-1]
    expected = int(
        datetime(2026, 9, 18, tzinfo=UTC).timestamp() * 1000
    )
    assert latest.day_start_ms == expected
    assert latest.value == Decimal("5.01")


def test_treasury_adapter_rejects_insufficient_history() -> None:
    xml = """<QR_BC_CM>
<G_NEW_DATE><NEW_DATE>09-17-2026</NEW_DATE><BC_10YEAR>4.95</BC_10YEAR></G_NEW_DATE>
<G_NEW_DATE><NEW_DATE>09-18-2026</NEW_DATE><BC_10YEAR>5.01</BC_10YEAR></G_NEW_DATE>
</QR_BC_CM>"""

    async def run():
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, content=xml.encode())
        )
        async with httpx.AsyncClient(transport=transport) as client:
            await Treasury10YDailyAdapter(client).fetch_window(sessions=3)

    with pytest.raises(ValueError, match="insufficient"):
        asyncio.run(run())


@pytest.mark.parametrize("sessions", [2, 65])
def test_macro_adapter_session_bounds(sessions: int) -> None:
    with pytest.raises(ValueError, match="sessions"):
        asyncio.run(CboeVixDailyAdapter().fetch_window(sessions=sessions))
    with pytest.raises(ValueError, match="sessions"):
        asyncio.run(Treasury10YDailyAdapter().fetch_window(sessions=sessions))
