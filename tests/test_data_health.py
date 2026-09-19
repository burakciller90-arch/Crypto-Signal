from decimal import Decimal

import pytest

from crypto_signal.data.health import assess_freshness, detect_gaps
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType


def candle(open_time_ms: int, *, source_timestamp_ms: int, is_closed: bool = True) -> Candle:
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
        is_closed=is_closed,
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=source_timestamp_ms + 1,
        adapter_version="test/1",
    )


def test_gap_detector_reports_exact_missing_grid() -> None:
    first = candle(0, source_timestamp_ms=3_000_000)
    third = candle(1_800_000, source_timestamp_ms=3_000_000)

    gaps = detect_gaps([third, first], "15m")

    assert len(gaps) == 1
    assert gaps[0].first_missing_open_ms == 900_000
    assert gaps[0].last_missing_open_ms == 900_000
    assert gaps[0].missing_count == 1


def test_gap_detector_rejects_off_grid_sequence() -> None:
    with pytest.raises(ValueError, match="not aligned"):
        detect_gaps(
            [candle(0, source_timestamp_ms=1), candle(900_001, source_timestamp_ms=1)],
            "15m",
        )


def test_freshness_is_fresh_with_recent_source_and_closed_candle() -> None:
    items = [
        candle(0, source_timestamp_ms=1_700_000),
        candle(900_000, source_timestamp_ms=1_700_000, is_closed=False),
    ]

    result = assess_freshness(items, timeframe="15m", now_ms=1_800_000)

    assert result.stale is False
    assert result.reasons == ()


def test_freshness_surfaces_source_and_closed_staleness() -> None:
    items = [candle(0, source_timestamp_ms=1_000_000)]

    result = assess_freshness(items, timeframe="15m", now_ms=3_000_000)

    assert result.stale is True
    assert "source_stale" in result.reasons
    assert "closed_candle_stale" in result.reasons


def test_freshness_without_data_is_explicit() -> None:
    result = assess_freshness([], timeframe="15m", now_ms=3_000_000)

    assert result.stale is True
    assert result.reasons == ("no_candles",)
