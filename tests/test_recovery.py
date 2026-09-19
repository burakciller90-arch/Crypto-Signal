import asyncio
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.recovery import BackfillReport, backfill_range
from crypto_signal.data.store import CandleStore, WriteDisposition


def candle(open_time_ms: int) -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(100),
        high=Decimal(110),
        low=Decimal(90),
        close=Decimal(105),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 1_000_000,
        ingested_at_ms=open_time_ms + 1_000_001,
        adapter_version="fake/1",
    )
class FakeAdapter:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.calls: list[tuple[int | None, int | None, int]] = []

    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[Candle, ...]:
        self.calls.append((start_ms, end_ms, limit))
        assert start_ms is not None and end_ms is not None
        return tuple(
            item
            for item in self.candles
            if start_ms <= item.open_time_ms <= end_ms
        )[:limit]


def test_backfill_is_paginated_complete_and_idempotent(tmp_path: Path) -> None:
    items = [candle(index * 900_000) for index in range(5)]
    adapter = FakeAdapter(items)
    store = CandleStore(tmp_path / "runtime" / "recovery.sqlite3")

    async def run() -> BackfillReport:
        return await backfill_range(
            adapter,
            store,
            symbol="BTCUSDT",
            timeframe="15m",
            start_open_ms=0,
            end_open_ms=3_600_000,
            page_limit=2,
        )

    first = asyncio.run(run())
    second = asyncio.run(run())

    assert first.complete is True
    assert first.expected_count == 5
    assert first.received_count == 5
    assert first.count(WriteDisposition.INSERTED) == 5
    assert second.count(WriteDisposition.UNCHANGED) == 5
    assert store.count() == 5
    assert len(adapter.calls) == 6


def test_backfill_reports_missing_without_synthesizing(tmp_path: Path) -> None:
    items = [candle(index * 900_000) for index in (0, 1, 3, 4)]
    adapter = FakeAdapter(items)
    store = CandleStore(tmp_path / "runtime" / "recovery.sqlite3")

    report = asyncio.run(
        backfill_range(
            adapter,
            store,
            symbol="BTCUSDT",
            timeframe="15m",
            start_open_ms=0,
            end_open_ms=3_600_000,
            page_limit=5,
        )
    )

    assert report.complete is False
    assert report.expected_count == 5
    assert report.received_count == 4
    assert report.missing_open_times_ms == (1_800_000,)
    assert store.count() == 4
