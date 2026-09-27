from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.store import CandleConflictError, CandleStore
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import LiveFreezeStatus
from crypto_signal.ledger.live_coverage import freeze_coverage_context
from crypto_signal.ledger.store import ImmutableSignalLedger

BASE_MS = 900_000
START_MS = int(datetime(2026, 9, 10, tzinfo=UTC).timestamp() * 1000)


def _candles(*, closed_count: int = 120) -> tuple[Candle, ...]:
    items: list[Candle] = []
    for index in range(closed_count):
        open_ms = START_MS + index * BASE_MS
        base = Decimal(1000 + index)
        close = base + (Decimal(2) if index % 2 == 0 else Decimal(-2))
        items.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                open_time_ms=open_ms,
                close_time_ms=open_ms + BASE_MS - 1,
                open=base,
                high=max(base, close) + Decimal(3),
                low=min(base, close) - Decimal(3),
                close=close,
                volume=Decimal(10),
                quote_volume=Decimal(10000),
                trade_count=10,
                is_closed=True,
                source=DataSource.REST,
                source_timestamp_ms=open_ms + BASE_MS + 10,
                ingested_at_ms=open_ms + BASE_MS + 20,
                adapter_version="rdp1-test/1",
            )
        )
    open_ms = START_MS + closed_count * BASE_MS
    items.append(
        Candle(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
            open_time_ms=open_ms,
            close_time_ms=open_ms + BASE_MS - 1,
            open=Decimal(1200),
            high=Decimal(1205),
            low=Decimal(1195),
            close=Decimal(1201),
            volume=Decimal(5),
            quote_volume=Decimal(6000),
            trade_count=5,
            is_closed=False,
            source=DataSource.REST,
            source_timestamp_ms=open_ms + 100,
            ingested_at_ms=open_ms + 100,
            adapter_version="rdp1-test/1",
        )
    )
    return tuple(items)


class _Adapter:
    def __init__(self, items: tuple[Candle, ...]) -> None:
        self.items = items
        self.calls = 0

    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[Candle, ...]:
        self.calls += 1
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert limit == len(self.items)
        assert start_ms is None
        assert end_ms is None
        return self.items


def _context(limit: int) -> LiveCoverageContext:
    return LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        source_strategy=LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M,
        freeze_limit=limit,
        minimum_closed_candles=100,
        enabled=False,
    )


def test_direct_15m_caches_exact_single_fetch_before_freeze(
    tmp_path: Path,
) -> None:
    items = _candles()
    adapter = _Adapter(items)
    cache = CandleStore(tmp_path / "cache.sqlite3")
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")

    result = asyncio.run(
        freeze_coverage_context(
            context=_context(len(items)),
            adapter=adapter,
            ledger=ledger,
            candle_store=cache,
        )
    )

    assert adapter.calls == 1
    assert result.status is LiveFreezeStatus.FROZEN
    persisted = cache.list_candles_read_only(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )
    assert persisted == items
    assert result.bundle is not None
    assert result.bundle.candles == tuple(
        item for item in items if item.is_closed
    )


def test_direct_15m_cache_advances_even_when_cutoff_already_frozen(
    tmp_path: Path,
) -> None:
    first_items = _candles()
    adapter = _Adapter(first_items)
    cache = CandleStore(tmp_path / "cache.sqlite3")
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    context = _context(len(first_items))

    first = asyncio.run(
        freeze_coverage_context(
            context=context,
            adapter=adapter,
            ledger=ledger,
            candle_store=cache,
        )
    )
    assert first.status is LiveFreezeStatus.FROZEN

    second = asyncio.run(
        freeze_coverage_context(
            context=context,
            adapter=adapter,
            ledger=ledger,
            candle_store=cache,
        )
    )
    assert second.status is LiveFreezeStatus.ALREADY_FROZEN
    assert adapter.calls == 2
    assert cache.list_candles_read_only(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    ) == first_items


def test_direct_15m_cache_conflict_fails_before_new_freeze(
    tmp_path: Path,
) -> None:
    items = _candles()
    cache = CandleStore(tmp_path / "cache.sqlite3")
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    original = items[60]
    conflicting = Candle(
        exchange=original.exchange,
        market_type=original.market_type,
        symbol=original.symbol,
        timeframe=original.timeframe,
        open_time_ms=original.open_time_ms,
        close_time_ms=original.close_time_ms,
        open=original.open,
        high=original.high + Decimal(10),
        low=original.low,
        close=original.close,
        volume=original.volume,
        quote_volume=original.quote_volume,
        trade_count=original.trade_count,
        is_closed=True,
        source=original.source,
        source_timestamp_ms=original.source_timestamp_ms + 1,
        ingested_at_ms=original.ingested_at_ms + 1,
        adapter_version=original.adapter_version,
    )
    cache.upsert(conflicting)

    with pytest.raises(CandleConflictError, match="finalized candle conflict"):
        asyncio.run(
            freeze_coverage_context(
                context=_context(len(items)),
                adapter=_Adapter(items),
                ledger=ledger,
                candle_store=cache,
            )
        )

    assert ledger.count_freezes() == 0
    assert cache.count() == 1
