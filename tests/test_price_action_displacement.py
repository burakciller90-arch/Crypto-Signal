from decimal import Decimal

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.price_action.displacement import (
    DisplacementConfig,
    analyze_displacement,
    detect_displacement,
)
from crypto_signal.methodologies.price_action.models import StructureDirection


def candle(
    index: int,
    *,
    open_: str = "100",
    high: str = "101.5",
    low: str = "99.5",
    close: str = "101",
) -> Candle:
    open_time_ms = index * 900_000
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_000,
        ingested_at_ms=open_time_ms + 900_999,
        adapter_version="test/1",
    )


def baseline() -> list[Candle]:
    return [candle(index) for index in range(20)]


def test_bullish_displacement_uses_prior_baseline_only() -> None:
    series = baseline() + [
        candle(20, open_="100", high="104.5", low="99.5", close="104")
    ]

    events = detect_displacement(series)

    assert len(events) == 1
    event = events[0]
    assert event.direction is StructureDirection.BULLISH
    assert event.body == Decimal(4)
    assert event.total_range == Decimal(5)
    assert event.body_fraction == Decimal("0.8")
    assert event.baseline_median_body == Decimal(1)
    assert event.baseline_median_range == Decimal(2)
    assert event.observed_body_multiple == Decimal(4)
    assert event.observed_range_multiple == Decimal("2.5")
    assert event.baseline_last_candle_identity == series[19].identity


def test_bearish_displacement_is_symmetric() -> None:
    series = baseline() + [
        candle(20, open_="104", high="104.5", low="99.5", close="100")
    ]
    events = detect_displacement(series)

    assert len(events) == 1
    assert events[0].direction is StructureDirection.BEARISH


def test_large_wick_with_small_body_is_not_displacement() -> None:
    series = baseline() + [
        candle(20, open_="100", high="106", low="94", close="101")
    ]
    assert detect_displacement(series) == ()


def test_future_candle_cannot_change_prior_displacement_classification() -> None:
    core = baseline() + [
        candle(20, open_="100", high="104.5", low="99.5", close="104")
    ]
    first = detect_displacement(core)
    extended = detect_displacement(
        core + [candle(21, open_="100", high="120", low="80", close="119")]
    )

    assert first
    assert extended[0] == first[0]


def test_as_of_hides_displacement_until_candle_is_observed() -> None:
    series = baseline() + [
        candle(20, open_="100", high="104.5", low="99.5", close="104")
    ]

    before = analyze_displacement(
        series,
        as_of_ms=series[19].ingested_at_ms,
    )
    after = analyze_displacement(
        series,
        as_of_ms=series[20].ingested_at_ms,
    )

    assert before.events == ()
    assert len(after.events) == 1


def test_displacement_config_is_explicitly_validated() -> None:
    with pytest.raises(ValueError, match="lookback"):
        DisplacementConfig(lookback_bars=1)

    with pytest.raises(ValueError, match="min_body_fraction"):
        DisplacementConfig(min_body_fraction=Decimal("1.1"))
