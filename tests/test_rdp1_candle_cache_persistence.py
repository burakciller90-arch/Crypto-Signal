from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import cast

from crypto_signal.data.adapters.base import MarketDataAdapter
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
from crypto_signal.ledger.live_clock import LiveFreezeStatus
from crypto_signal.ledger.live_coverage import freeze_coverage_context
from crypto_signal.ledger.store import ImmutableSignalLedger


class _StaticAdapter:
    def __init__(self, candles: tuple[Candle, ...]) -> None:
        self._candles = candles

    async def fetch_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        **_: object,
    ) -> tuple[Candle, ...]:
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert limit >= len(self._candles)
        return self._candles


class _AlreadyFrozenLedger:
    def has_source_cutoff(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        source_cutoff_open_time_ms: int,
    ) -> bool:
        assert exchange == "bybit"
        assert market_type == "spot"
        assert symbol == "BTCUSDT"
        assert timeframe == "15m"
        assert source_cutoff_open_time_ms == 900_000
        return True


def _candle(open_time_ms: int, close: str) -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(100),
        high=Decimal(102),
        low=Decimal(99),
        close=Decimal(close),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=100,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_000,
        ingested_at_ms=open_time_ms + 900_001,
        adapter_version="test/1",
    )


def test_direct_15m_cache_advances_even_when_signal_cutoff_already_frozen(
    tmp_path: Path,
) -> None:
    candles = (
        _candle(0, "101"),
        _candle(900_000, "101.5"),
    )
    adapter = cast(MarketDataAdapter, _StaticAdapter(candles))
    ledger = cast(ImmutableSignalLedger, _AlreadyFrozenLedger())
    store = CandleStore(tmp_path / "candles.sqlite3")
    context = LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        source_strategy=LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M,
        freeze_limit=2,
        minimum_closed_candles=1,
    )

    result = asyncio.run(
        freeze_coverage_context(
            context=context,
            adapter=adapter,
            ledger=ledger,
            candle_store=store,
        )
    )

    assert result.status is LiveFreezeStatus.ALREADY_FROZEN
    cached = store.list_candles(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )
    assert [candle.open_time_ms for candle in cached] == [0, 900_000]
    assert cached[-1].close == Decimal("101.5")
