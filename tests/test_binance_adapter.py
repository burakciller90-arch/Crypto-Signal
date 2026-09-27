import asyncio
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.models import Candle, DataSource, Exchange


def test_binance_rest_normalizes_candles() -> None:
    rows = [
        [
            1710000000000,
            "100.1",
            "102.2",
            "99.9",
            "101.5",
            "3.25",
            1710000899999,
            "328.75",
            42,
            "0",
            "0",
            "0",
        ]
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/v3/time"):
            return httpx.Response(200, json={"serverTime": 1710001000000})
        assert request.url.params["symbol"] == "BTCUSDT"
        assert request.url.params["interval"] == "15m"
        assert request.url.params["limit"] == "1"
        return httpx.Response(200, json=rows)
    async def run() -> tuple[Candle, ...]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = BinanceSpotAdapter(client)
            return await adapter.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=1)

    candles = asyncio.run(run())
    assert len(candles) == 1
    candle = candles[0]
    assert candle.exchange is Exchange.BINANCE
    assert candle.source is DataSource.REST
    assert candle.open == Decimal("100.1")
    assert candle.quote_volume == Decimal("328.75")
    assert candle.trade_count == 42
    assert candle.is_closed is True


@pytest.mark.parametrize("limit", [0, 1001])
def test_binance_limit_is_bounded(limit: int) -> None:
    adapter = BinanceSpotAdapter()
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(adapter.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=limit))


def test_binance_open_candle_is_not_finalized() -> None:
    rows = [[1710000000000, "100", "101", "99", "100.5", "1", 1710000899999, "100", 1, "0", "0", "0"]]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/v3/time"):
            return httpx.Response(200, json={"serverTime": 1710000500000})
        return httpx.Response(200, json=rows)
    async def run() -> tuple[Candle, ...]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BinanceSpotAdapter(client).fetch_candles(
                symbol="BTCUSDT",
                timeframe="15m",
                limit=1,
            )

    candles = asyncio.run(run())
    assert candles[0].is_closed is False


def test_binance_tr_main_rest_normalizes_wrapped_candles() -> None:
    rows = [
        [
            1710000000000,
            "100.1",
            "102.2",
            "99.9",
            "101.5",
            "3.25",
            1710000899999,
            "328.75",
            42,
            "0",
            "0",
            "0",
        ]
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.binance.me"
        assert request.url.path == "/api/v1/klines"
        assert request.url.params["symbol"] == "BTCUSDT"
        assert request.url.params["interval"] == "15m"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": rows,
                "timestamp": 1710001000000,
            },
        )

    async def run() -> tuple[Candle, ...]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = BinanceSpotAdapter(
                client,
                base_url="https://api.binance.me/",
                api_variant="tr_main",
            )
            return await adapter.fetch_candles(
                symbol="BTCUSDT",
                timeframe="15m",
                limit=1,
            )

    candles = asyncio.run(run())
    assert len(candles) == 1
    candle = candles[0]
    assert candle.exchange is Exchange.BINANCE
    assert candle.is_closed is True
    assert candle.adapter_version == "binance-tr-main-market-data/1"


def test_binance_rest_rejects_invalid_variant_and_non_https_base_url() -> None:
    with pytest.raises(ValueError, match="unsupported Binance API variant"):
        BinanceSpotAdapter(api_variant="unknown")
    with pytest.raises(ValueError, match="must use https"):
        BinanceSpotAdapter(
            base_url="http://api.binance.me",
            api_variant="tr_main",
        )


def test_binance_tr_main_rejects_exchange_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 400001,
                "msg": "bad request",
                "data": [],
                "timestamp": 1710001000000,
            },
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = BinanceSpotAdapter(
                client,
                base_url="https://api.binance.me",
                api_variant="tr_main",
            )
            await adapter.fetch_candles(
                symbol="BTCUSDT",
                timeframe="15m",
                limit=1,
            )

    with pytest.raises(ValueError, match="Binance TR API error"):
        asyncio.run(run())
