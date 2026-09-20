from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.store import CandleStore
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import LiveFreezeStatus
from crypto_signal.ledger.live_coverage import freeze_coverage_context
from crypto_signal.ledger.store import ImmutableSignalLedger

BASE_MS = 900_000


def context() -> LiveCoverageContext:
    return LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="1h",
        source_strategy=LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M,
        freeze_limit=3,
        minimum_closed_candles=2,
        enabled=True,
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
    def __init__(self, items: tuple[Candle, ...]) -> None:
        self.items = items
        self.latest_calls = 0
        self.range_calls = 0

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
        if start_ms is None and end_ms is None:
            self.latest_calls += 1
            return self.items[-limit:]
        assert start_ms is not None and end_ms is not None
        self.range_calls += 1
        return tuple(
            item
            for item in self.items
            if start_ms <= item.open_time_ms <= end_ms
        )[:limit]


def base_series(*, missing: int | None = None) -> tuple[Candle, ...]:
    return tuple(
        candle(index * BASE_MS)
        for index in range(12)
        if index * BASE_MS != missing
    )


def test_aggregate_coverage_path_prepares_then_freezes_idempotently(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter(base_series())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    store = CandleStore(tmp_path / "cache.sqlite3")

    first = asyncio.run(
        freeze_coverage_context(
            context=context(),
            adapter=adapter,
            ledger=ledger,
            candle_store=store,
        )
    )
    second = asyncio.run(
        freeze_coverage_context(
            context=context(),
            adapter=adapter,
            ledger=ledger,
            candle_store=store,
        )
    )

    assert first.status is LiveFreezeStatus.FROZEN
    assert second.status is LiveFreezeStatus.ALREADY_FROZEN
    assert ledger.list_freezes()[0].timeframe == "1h"
    assert ledger.count_freezes() == 1
    assert store.count() == 12
    assert adapter.latest_calls == 2
    assert adapter.range_calls == 1


def test_aggregate_coverage_path_fails_closed_on_missing_base(
    tmp_path: Path,
) -> None:
    missing = 5 * BASE_MS
    adapter = FakeAdapter(base_series(missing=missing))
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    store = CandleStore(tmp_path / "cache.sqlite3")

    with pytest.raises(ValueError, match="preparation incomplete"):
        asyncio.run(
            freeze_coverage_context(
                context=context(),
                adapter=adapter,
                ledger=ledger,
                candle_store=store,
            )
        )

    assert ledger.count_freezes() == 0
