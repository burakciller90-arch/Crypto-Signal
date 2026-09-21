from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.bybit_derivatives import (
    BybitLinearDerivativesAdapter,
)
from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.models import DataSource, Exchange


def test_bybit_derivatives_normalizes_public_ticker_and_open_interest() -> None:
    oi_payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "symbol": "BTCUSDT",
            "list": [
                {"openInterest": "110", "timestamp": "1710000900000"},
                {"openInterest": "100", "timestamp": "1710000000000"},
            ],
        },
        "time": 1710001000000,
    }
    ticker_payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "101",
                    "indexPrice": "100",
                    "openInterest": "115",
                    "fundingRate": "0.0008",
                    "fundingIntervalHour": "8",
                }
            ],
        },
        "time": 1710001000000,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "X-BAPI-API-KEY" not in request.headers
        assert request.url.params["category"] == "linear"
        assert request.url.params["symbol"] == "BTCUSDT"
        if request.url.path.endswith("/open-interest"):
            assert request.url.params["intervalTime"] == "15min"
            assert request.url.params["limit"] == "8"
            return httpx.Response(200, json=oi_payload)
        assert request.url.path.endswith("/tickers")
        return httpx.Response(200, json=ticker_payload)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BybitLinearDerivativesAdapter(client).fetch_observations(
                symbol="BTCUSDT"
            )

    observations = asyncio.run(run())

    assert len(observations) == 3
    assert [item.event_at_ms for item in observations] == [
        1710000000000,
        1710000900000,
        1710001000000,
    ]
    latest = observations[-1]
    assert latest.exchange is Exchange.BYBIT
    assert latest.instrument_type is DerivativesInstrumentType.LINEAR_PERPETUAL
    assert latest.source is DataSource.REST
    assert latest.funding_rate == Decimal("0.0008")
    assert latest.open_interest == Decimal(115)
    assert latest.mark_price == Decimal(101)
    assert latest.index_price == Decimal(100)
    assert latest.funding_interval_hours == 8


def test_bybit_derivatives_end_time_is_forwarded_only_to_oi() -> None:
    seen: list[tuple[str, str | None]] = []
    oi_payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "symbol": "BTCUSDT",
            "list": [
                {"openInterest": "100", "timestamp": "1710000000000"},
                {"openInterest": "101", "timestamp": "1710000900000"},
            ],
        },
        "time": 1710001000000,
    }
    ticker_payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "100",
                    "indexPrice": "100",
                    "openInterest": "101",
                    "fundingRate": "0",
                    "fundingIntervalHour": "8",
                }
            ],
        },
        "time": 1710001000000,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.url.params.get("endTime")))
        if request.url.path.endswith("/open-interest"):
            return httpx.Response(200, json=oi_payload)
        return httpx.Response(200, json=ticker_payload)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await BybitLinearDerivativesAdapter(client).fetch_observations(
                symbol="BTCUSDT",
                end_ms=1710000900000,
            )

    asyncio.run(run())
    assert ("/v5/market/open-interest", "1710000900000") in seen
    assert ("/v5/market/tickers", None) in seen


def test_bybit_derivatives_exchange_error_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/open-interest"):
            return httpx.Response(
                200,
                json={"retCode": 10001, "retMsg": "bad request"},
            )
        return httpx.Response(
            200,
            json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {"category": "linear", "list": []},
                "time": 1710001000000,
            },
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await BybitLinearDerivativesAdapter(client).fetch_observations(
                symbol="BTCUSDT"
            )

    with pytest.raises(ValueError, match="open-interest API error"):
        asyncio.run(run())


@pytest.mark.parametrize("limit", [0, 1, 201])
def test_bybit_derivatives_oi_limit_is_bounded(limit: int) -> None:
    adapter = BybitLinearDerivativesAdapter()
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(
            adapter.fetch_observations(
                symbol="BTCUSDT",
                oi_limit=limit,
            )
        )


def test_bybit_derivatives_rejects_missing_matching_ticker() -> None:
    oi_payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "symbol": "BTCUSDT",
            "list": [
                {"openInterest": "100", "timestamp": "1710000000000"},
                {"openInterest": "101", "timestamp": "1710000900000"},
            ],
        },
        "time": 1710001000000,
    }
    ticker_payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [{"symbol": "ETHUSDT"}],
        },
        "time": 1710001000000,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=(
                oi_payload
                if request.url.path.endswith("/open-interest")
                else ticker_payload
            ),
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await BybitLinearDerivativesAdapter(client).fetch_observations(
                symbol="BTCUSDT"
            )

    with pytest.raises(ValueError, match="exactly one matching symbol"):
        asyncio.run(run())
