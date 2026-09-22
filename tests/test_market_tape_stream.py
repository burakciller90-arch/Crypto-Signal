from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal

from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_stream import capture_public_trade_stream
from crypto_signal.data.microstructure import (
    AggressorSide,
    PublicTradeObservation,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType


def trade(*, ingested_at_ms: int) -> PublicTradeObservation:
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id="stable-exec",
        sequence=42,
        aggressor_side=AggressorSide.BUY,
        price=Decimal("67250.5"),
        size=Decimal("0.125"),
        event_at_ms=1_000,
        source_timestamp_ms=1_010,
        ingested_at_ms=ingested_at_ms,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.WEBSOCKET,
        adapter_version="test-public-trade-ws/1",
    )


class FakeTradeStream:
    def stream_trades(
        self,
        *,
        symbol: str,
    ) -> AsyncIterator[PublicTradeObservation]:
        assert symbol == "BTCUSDT"

        async def generator() -> AsyncIterator[PublicTradeObservation]:
            yield trade(ingested_at_ms=1_020)
            yield trade(ingested_at_ms=1_030)

        return generator()


def test_capture_public_trade_stream_is_replay_safe(tmp_path) -> None:
    async def run() -> tuple[int, int, int, int]:
        store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
        result = await capture_public_trade_stream(
            store=store,
            adapter=FakeTradeStream(),
            symbol="BTCUSDT",
            max_trades=2,
        )
        counts = store.counts()
        return (
            result.seen,
            result.inserted,
            result.unchanged,
            counts.trades,
        )

    seen, inserted, unchanged, trade_count = asyncio.run(run())

    assert seen == 2
    assert inserted == 1
    assert unchanged == 1
    assert trade_count == 1


def test_capture_public_trade_stream_rejects_invalid_limit(tmp_path) -> None:
    async def run() -> None:
        store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
        try:
            await capture_public_trade_stream(
                store=store,
                adapter=FakeTradeStream(),
                symbol="BTCUSDT",
                max_trades=0,
            )
        except ValueError as exc:
            assert "max_trades" in str(exc)
        else:
            raise AssertionError("non-positive max_trades must fail closed")

    asyncio.run(run())
