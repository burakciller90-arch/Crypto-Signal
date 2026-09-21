from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.bybit_microstructure import (
    BybitSpotMicrostructureAdapter,
)
from crypto_signal.data.microstructure import AggressorSide
from crypto_signal.data.models import DataSource, Exchange, MarketType


def _book_payload() -> dict[str, object]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "s": "BTCUSDT",
            "b": [["100", "2"], ["99", "1"]],
            "a": [["101", "1"], ["102", "2"]],
            "ts": 1710001000010,
            "u": 230704,
            "seq": 1432604333,
            "cts": 1710001000005,
        },
        "retExtInfo": {},
        "time": 1710001000020,
    }


def _trade_payload() -> dict[str, object]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "spot",
            "list": [
                {
                    "execId": "trade-2",
                    "symbol": "BTCUSDT",
                    "price": "100.5",
                    "size": "0.4",
                    "side": "Sell",
                    "time": "1710001000002",
                    "isBlockTrade": False,
                    "isRPITrade": False,
                    "seq": "1432604332",
                },
                {
                    "execId": "trade-1",
                    "symbol": "BTCUSDT",
                    "price": "100.6",
                    "size": "0.5",
                    "side": "Buy",
                    "time": "1710001000001",
                    "isBlockTrade": False,
                    "isRPITrade": True,
                    "seq": "1432604331",
                },
            ],
        },
        "retExtInfo": {},
        "time": 1710001000020,
    }


def test_bybit_microstructure_normalizes_public_book_and_trades() -> None:
    seen: list[tuple[str, str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "X-BAPI-API-KEY" not in request.headers
        assert "Authorization" not in request.headers
        seen.append(
            (
                request.url.path,
                str(request.url.params["category"]),
                str(request.url.params["symbol"]),
                str(request.url.params["limit"]),
            )
        )
        if request.url.path.endswith("/orderbook"):
            return httpx.Response(200, json=_book_payload())
        assert request.url.path.endswith("/recent-trade")
        return httpx.Response(200, json=_trade_payload())

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BybitSpotMicrostructureAdapter(client).fetch_snapshot(
                symbol="BTCUSDT",
                book_depth=2,
                trade_limit=2,
            )

    book, trades = asyncio.run(run())

    assert book.exchange is Exchange.BYBIT
    assert book.market_type is MarketType.SPOT
    assert book.source is DataSource.REST
    assert book.event_at_ms == 1710001000005
    assert book.source_timestamp_ms == 1710001000010
    assert book.response_time_ms == 1710001000020
    assert book.update_id == 230704
    assert book.sequence == 1432604333
    assert book.bids[0].price == Decimal(100)
    assert book.asks[0].price == Decimal(101)
    assert len(book.snapshot_identity) == 64

    assert [item.exec_id for item in trades] == ["trade-1", "trade-2"]
    assert trades[0].aggressor_side is AggressorSide.BUY
    assert trades[0].is_rpi_trade is True
    assert trades[0].book_eligible is False
    assert trades[1].aggressor_side is AggressorSide.SELL
    assert trades[1].book_eligible is True
    assert trades[1].notional == Decimal("40.20")
    assert all(len(item.trade_identity) == 64 for item in trades)

    assert ("/v5/market/orderbook", "spot", "BTCUSDT", "2") in seen
    assert ("/v5/market/recent-trade", "spot", "BTCUSDT", "2") in seen


@pytest.mark.parametrize(
    ("book_depth", "trade_limit"),
    [(0, 10), (1001, 10), (10, 0), (10, 61)],
)
def test_bybit_microstructure_limits_are_bounded(
    book_depth: int,
    trade_limit: int,
) -> None:
    adapter = BybitSpotMicrostructureAdapter()
    with pytest.raises(ValueError, match="depth|limit"):
        asyncio.run(
            adapter.fetch_snapshot(
                symbol="BTCUSDT",
                book_depth=book_depth,
                trade_limit=trade_limit,
            )
        )


def test_bybit_microstructure_rejects_exchange_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orderbook"):
            return httpx.Response(
                200,
                json={"retCode": 10001, "retMsg": "bad request"},
            )
        return httpx.Response(200, json=_trade_payload())

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await BybitSpotMicrostructureAdapter(client).fetch_snapshot(
                symbol="BTCUSDT"
            )

    with pytest.raises(ValueError, match="orderbook API error"):
        asyncio.run(run())


def test_bybit_microstructure_rejects_duplicate_trade_ids() -> None:
    payload = _trade_payload()
    result = payload["result"]
    assert isinstance(result, dict)
    rows = result["list"]
    assert isinstance(rows, list)
    duplicate = dict(rows[0])
    rows.append(duplicate)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orderbook"):
            return httpx.Response(200, json=_book_payload())
        return httpx.Response(200, json=payload)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await BybitSpotMicrostructureAdapter(client).fetch_snapshot(
                symbol="BTCUSDT"
            )

    with pytest.raises(ValueError, match="duplicate execId"):
        asyncio.run(run())


def test_bybit_microstructure_rejects_unknown_trade_side() -> None:
    payload = _trade_payload()
    result = payload["result"]
    assert isinstance(result, dict)
    rows = result["list"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    row["side"] = "Unknown"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orderbook"):
            return httpx.Response(200, json=_book_payload())
        return httpx.Response(200, json=payload)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await BybitSpotMicrostructureAdapter(client).fetch_snapshot(
                symbol="BTCUSDT"
            )

    with pytest.raises(ValueError, match="side"):
        asyncio.run(run())
