import asyncio
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.models import Candle, DataSource, Exchange


def test_bybit_rest_normalizes_and_sorts_candles() -> None:
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "spot",
            "symbol": "BTCUSDT",
            "list": [
                ["1710000900000", "101", "104", "100", "103", "2.5", "255"],
                ["1710000000000", "100.1", "102.2", "99.9", "101.5", "3.25", "328.75"],
            ],
        },
        "time": 1710001000000,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["category"] == "spot"
        assert request.url.params["interval"] == "15"
        assert request.url.params["limit"] == "2"
        return httpx.Response(200, json=payload)

    async def run() -> tuple[Candle, ...]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = BybitSpotAdapter(client)
            return await adapter.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=2)

    candles = asyncio.run(run())
    assert [item.open_time_ms for item in candles] == [1710000000000, 1710000900000]
    assert candles[0].open == Decimal("100.1")
    assert candles[0].quote_volume == Decimal("328.75")
    assert candles[0].exchange is Exchange.BYBIT
    assert candles[0].source is DataSource.REST
    assert candles[0].is_closed is True
    assert candles[1].is_closed is False


def test_bybit_rest_rejects_exchange_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "bad request"})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = BybitSpotAdapter(client)
            await adapter.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=1)

    with pytest.raises(ValueError, match="Bybit API error"):
        asyncio.run(run())


@pytest.mark.parametrize("limit", [0, 1001])
def test_bybit_limit_is_bounded(limit: int) -> None:
    adapter = BybitSpotAdapter()
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(adapter.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=limit))
