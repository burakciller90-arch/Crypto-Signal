from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.reconciliation import reconcile_candle_grids


def candle(exchange: Exchange, open_time_ms: int, close: str) -> Candle:
    value = Decimal(close)
    return Candle(
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=value,
        high=value + Decimal(10),
        low=value - Decimal(10),
        close=value,
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=1,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 1_000_000,
        ingested_at_ms=open_time_ms + 1_000_001,
        adapter_version="test/1",
    )


def test_reconciliation_reports_overlap_missing_and_spread() -> None:
    left = [
        candle(Exchange.BYBIT, 0, "100"),
        candle(Exchange.BYBIT, 900_000, "101"),
    ]
    right = [
        candle(Exchange.BINANCE, 900_000, "100"),
        candle(Exchange.BINANCE, 1_800_000, "102"),
    ]

    result = reconcile_candle_grids(left, right)

    assert result.overlap_count == 1
    assert result.left_only_open_times_ms == (0,)
    assert result.right_only_open_times_ms == (1_800_000,)
    assert len(result.spreads) == 1
    assert result.spreads[0].spread_bps > 0


def test_reconciliation_rejects_incompatible_semantics() -> None:
    left = [candle(Exchange.BYBIT, 0, "100")]
    right = [replace(candle(Exchange.BINANCE, 0, "100"), symbol="ETHUSDT")]

    with pytest.raises(ValueError, match="not semantically comparable"):
        reconcile_candle_grids(left, right)
