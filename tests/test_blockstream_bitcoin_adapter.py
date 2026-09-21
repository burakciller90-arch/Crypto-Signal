from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest

from crypto_signal.data.adapters.blockstream_bitcoin import (
    BlockstreamBitcoinNetworkAdapter,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.onchain import BitcoinNetwork


def _hash(height: int) -> str:
    return f"{height:064x}"


def _blocks(start_height: int = 1_000) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for offset in range(10):
        height = start_height - offset
        timestamp = 1_700_000_000 + height * 600
        rows.append(
            {
                "id": _hash(height),
                "height": height,
                "version": 1,
                "timestamp": timestamp,
                "bits": 1,
                "nonce": 1,
                "difficulty": 123456.789,
                "merkle_root": "a" * 64,
                "tx_count": 2_000 + offset,
                "size": 1_500_000 + offset,
                "weight": 3_000_000 + offset,
                "previousblockhash": _hash(height - 1),
                "mediantime": timestamp - 300,
            }
        )
    return rows


def test_blockstream_adapter_normalizes_public_block_window() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "Authorization" not in request.headers
        seen.append(request.url.path)
        if request.url.path.endswith("/blocks/tip/height"):
            return httpx.Response(200, text="1000")
        if request.url.path.endswith("/blocks/1000"):
            return httpx.Response(200, json=_blocks())
        raise AssertionError(f"unexpected path: {request.url.path}")

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BlockstreamBitcoinNetworkAdapter(client).fetch_block_window()

    observation = asyncio.run(run())

    assert observation.network is BitcoinNetwork.MAINNET
    assert observation.source is DataSource.REST
    assert observation.tip_height == 1_000
    assert observation.tip_hash == _hash(1_000)
    assert len(observation.blocks) == 10
    assert observation.blocks[0].difficulty == Decimal("123456.789")
    assert observation.blocks[0].header_timestamp_ms == (
        1_700_000_000 + 1_000 * 600
    ) * 1000
    assert observation.blocks[0].median_time_ms == (
        1_700_000_000 + 1_000 * 600 - 300
    ) * 1000
    assert len(observation.observation_identity) == 64
    assert "/api/blocks/tip/height" in seen
    assert "/api/blocks/1000" in seen


def test_blockstream_adapter_can_fetch_explicit_historical_height() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/blocks/900"):
            return httpx.Response(200, json=_blocks(900))
        raise AssertionError(f"unexpected path: {request.url.path}")

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BlockstreamBitcoinNetworkAdapter(client).fetch_block_window(
                start_height=900
            )

    observation = asyncio.run(run())

    assert observation.tip_height == 900
    assert seen == ["/api/blocks/900"]


def test_blockstream_adapter_rejects_empty_or_wrong_height_window() -> None:
    async def fetch(payload: object):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/blocks/1000"):
                return httpx.Response(200, json=payload)
            raise AssertionError(f"unexpected path: {request.url.path}")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await BlockstreamBitcoinNetworkAdapter(client).fetch_block_window(
                start_height=1_000
            )

    with pytest.raises(ValueError, match="empty"):
        asyncio.run(fetch([]))

    with pytest.raises(ValueError, match="does not start"):
        asyncio.run(fetch(_blocks(999)))


def test_blockstream_adapter_rejects_negative_start_height() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        asyncio.run(
            BlockstreamBitcoinNetworkAdapter().fetch_block_window(
                start_height=-1
            )
        )
