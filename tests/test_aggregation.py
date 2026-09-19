from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from crypto_signal.data.aggregation import aggregate_closed_15m
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.timeframes import bucket_open_ms


def candle(open_time_ms: int, index: int = 0) -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(100 + index),
        high=Decimal(105 + index),
        low=Decimal(95 - index),
        close=Decimal(101 + index),
        volume=Decimal(1 + index),
        quote_volume=Decimal(10 + index),
        trade_count=10 + index,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_100,
        ingested_at_ms=open_time_ms + 900_200,
        adapter_version="test/1",
    )


def test_aggregate_four_closed_15m_into_one_hour() -> None:
    items = [candle(index * 900_000, index) for index in range(4)]

    result = aggregate_closed_15m(items, target_timeframe="1h")

    assert result.incomplete == ()
    assert len(result.candles) == 1
    aggregate = result.candles[0]
    assert aggregate.open == Decimal(100)
    assert aggregate.high == Decimal(108)
    assert aggregate.low == Decimal(92)
    assert aggregate.close == Decimal(104)
    assert aggregate.volume == Decimal(10)
    assert aggregate.quote_volume == Decimal(46)
    assert aggregate.trade_count == 46
    assert aggregate.source is DataSource.AGGREGATED
def test_incomplete_bucket_is_reported_and_not_emitted() -> None:
    items = [candle(0), candle(900_000, 1), candle(2_700_000, 3)]

    result = aggregate_closed_15m(items, target_timeframe="1h")

    assert result.candles == ()
    assert len(result.incomplete) == 1
    gap = result.incomplete[0]
    assert gap.expected_count == 4
    assert gap.actual_count == 3
    assert gap.missing_open_times_ms == (1_800_000,)


def test_open_input_is_rejected() -> None:
    open_item = replace(candle(0), is_closed=False)
    with pytest.raises(ValueError, match="closed 15m"):
        aggregate_closed_15m([open_item], target_timeframe="1h")


def test_week_bucket_is_monday_utc() -> None:
    wednesday = datetime(2026, 9, 16, 12, 30, tzinfo=UTC)
    monday = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)

    assert bucket_open_ms(int(wednesday.timestamp() * 1000), "1W") == int(
        monday.timestamp() * 1000
    )
