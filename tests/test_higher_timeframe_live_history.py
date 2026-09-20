from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.store import CandleStore
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.higher_timeframe import (
    plan_higher_timeframe_history,
    prepare_higher_timeframe_history,
)

BASE_MS = 900_000


def context(*, target_count: int = 3) -> LiveCoverageContext:
    return LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="1h",
        source_strategy=(
            LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
        ),
        freeze_limit=target_count,
        minimum_closed_candles=min(2, target_count),
        enabled=False,
    )


def candle(open_time_ms: int) -> Candle:
    base = Decimal(100 + open_time_ms // BASE_MS)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + BASE_MS - 1,
        open=base,
        high=base + Decimal(3),
        low=base - Decimal(2),
        close=base + Decimal(1),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=5,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + BASE_MS + 10,
        ingested_at_ms=open_time_ms + BASE_MS + 20,
        adapter_version="fake/1",
    )


class FakeAdapter:
    def __init__(self, candles: tuple[Candle, ...]) -> None:
        self.candles = candles
        self.calls: list[tuple[str, int, int, int]] = []

    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[Candle, ...]:
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert start_ms is not None and end_ms is not None
        self.calls.append((timeframe, start_ms, end_ms, limit))
        return tuple(
            item
            for item in self.candles
            if start_ms <= item.open_time_ms <= end_ms
        )[:limit]


def base_series(
    *,
    missing_open_ms: int | None = None,
) -> tuple[Candle, ...]:
    return tuple(
        candle(index * BASE_MS)
        for index in range(12)
        if index * BASE_MS != missing_open_ms
    )


def test_plan_uses_latest_fully_completed_target_bucket() -> None:
    full = plan_higher_timeframe_history(
        context(),
        base_source_cutoff_open_ms=11 * BASE_MS,
    )
    assert full.first_target_open_ms == 0
    assert full.last_target_open_ms == 2 * 3_600_000
    assert full.base_start_open_ms == 0
    assert full.base_end_open_ms == 11 * BASE_MS
    assert full.expected_base_count == 12

    partial = plan_higher_timeframe_history(
        context(target_count=2),
        base_source_cutoff_open_ms=9 * BASE_MS,
    )
    assert partial.first_target_open_ms == 0
    assert partial.last_target_open_ms == 3_600_000
    assert partial.base_end_open_ms == 7 * BASE_MS
    assert partial.expected_base_count == 8


def test_prepare_paginates_missing_base_and_aggregates(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter(base_series())
    store = CandleStore(tmp_path / "base-cache.sqlite3")

    result = asyncio.run(
        prepare_higher_timeframe_history(
            adapter,
            store,
            context(),
            base_source_cutoff_open_ms=11 * BASE_MS,
            page_limit=5,
        )
    )

    assert result.complete is True
    assert result.missing_base_open_times_ms == ()
    assert len(result.fetch_reports) == 1
    assert result.fetch_reports[0].complete is True
    assert len(adapter.calls) == 3
    assert all(call[0] == "15m" for call in adapter.calls)
    assert len(result.base_candles) == 12
    assert len(result.aggregation.candles) == 3
    assert result.aggregation.incomplete == ()
    assert all(
        item.timeframe == "1h"
        and item.source is DataSource.AGGREGATED
        and item.is_closed
        for item in result.aggregation.candles
    )


def test_second_prepare_uses_complete_cache_without_api_calls(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter(base_series())
    store = CandleStore(tmp_path / "base-cache.sqlite3")

    first = asyncio.run(
        prepare_higher_timeframe_history(
            adapter,
            store,
            context(),
            base_source_cutoff_open_ms=11 * BASE_MS,
            page_limit=5,
        )
    )
    calls_after_first = len(adapter.calls)
    second = asyncio.run(
        prepare_higher_timeframe_history(
            adapter,
            store,
            context(),
            base_source_cutoff_open_ms=11 * BASE_MS,
            page_limit=5,
        )
    )

    assert first.complete is True
    assert second.complete is True
    assert second.fetch_reports == ()
    assert len(adapter.calls) == calls_after_first
    assert second.aggregation == first.aggregation


def test_missing_base_remains_explicit_and_target_is_incomplete(
    tmp_path: Path,
) -> None:
    missing = 5 * BASE_MS
    adapter = FakeAdapter(base_series(missing_open_ms=missing))
    store = CandleStore(tmp_path / "base-cache.sqlite3")

    result = asyncio.run(
        prepare_higher_timeframe_history(
            adapter,
            store,
            context(),
            base_source_cutoff_open_ms=11 * BASE_MS,
            page_limit=5,
        )
    )

    assert result.complete is False
    assert result.missing_base_open_times_ms == (missing,)
    assert len(result.aggregation.candles) == 2
    assert len(result.aggregation.incomplete) == 1
    incomplete = result.aggregation.incomplete[0]
    assert incomplete.timeframe == "1h"
    assert incomplete.bucket_open_ms == 3_600_000
    assert incomplete.missing_open_times_ms == (missing,)


def test_cached_partial_history_fetches_only_missing_contiguous_range(
    tmp_path: Path,
) -> None:
    items = base_series()
    adapter = FakeAdapter(items)
    store = CandleStore(tmp_path / "base-cache.sqlite3")
    for item in items[:8]:
        store.upsert(item)

    result = asyncio.run(
        prepare_higher_timeframe_history(
            adapter,
            store,
            context(),
            base_source_cutoff_open_ms=11 * BASE_MS,
            page_limit=1000,
        )
    )

    assert result.complete is True
    assert len(result.fetch_reports) == 1
    assert len(adapter.calls) == 1
    _, start_ms, end_ms, limit = adapter.calls[0]
    assert start_ms == 8 * BASE_MS
    assert end_ms == 12 * BASE_MS - 1
    assert limit == 4
