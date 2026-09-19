from dataclasses import replace
from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.periodic_opens import Period, PeriodicOpen
from crypto_signal.methodologies.price_action.interactions import (
    LevelInteractionKind,
    ReferenceLevel,
    analyze_level_interactions,
    detect_level_interactions,
    reference_level_from_periodic_open,
    reference_levels_from_range,
)
from crypto_signal.methodologies.price_action.levels import HighLowRangeEvidence
from crypto_signal.methodologies.price_action.models import StructureDirection


def candle(
    index: int,
    *,
    high: str,
    low: str,
    close: str,
) -> Candle:
    open_time_ms = index * 900_000
    close_value = Decimal(close)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=close_value,
        high=Decimal(high),
        low=Decimal(low),
        close=close_value,
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_000,
        ingested_at_ms=open_time_ms + 900_999,
        adapter_version="test/1",
    )


def level(*, available_index: int = 0, observed_index: int = 0) -> ReferenceLevel:
    available = candle(available_index, high="101", low="99", close="100")
    observed = candle(observed_index, high="101", low="99", close="100")
    return ReferenceLevel(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        label="test_level",
        price=Decimal(100),
        available_at_market_ms=available.close_time_ms,
        observed_at_ms=observed.ingested_at_ms,
        source_description="test",
    )


def test_bullish_reclaim_requires_trade_and_close_back_above() -> None:
    series = [
        candle(0, high="100", low="98", close="99"),
        candle(1, high="102", low="99.5", close="101"),
    ]
    events = detect_level_interactions(series, [level()])

    assert len(events) == 1
    event = events[0]
    assert event.kind is LevelInteractionKind.BULLISH_RECLAIM
    assert event.implication_direction is StructureDirection.BULLISH
    assert event.close_offset_bps > 0


def test_bearish_reclaim_is_symmetric() -> None:
    series = [
        candle(0, high="102", low="100", close="101"),
        candle(1, high="100.5", low="98", close="99"),
    ]
    events = detect_level_interactions(series, [level()])

    assert len(events) == 1
    assert events[0].kind is LevelInteractionKind.BEARISH_RECLAIM
    assert events[0].implication_direction is StructureDirection.BEARISH
    assert events[0].close_offset_bps < 0


def test_bullish_and_bearish_rejections_are_distinct() -> None:
    bullish_series = [
        candle(0, high="102", low="100", close="101"),
        candle(1, high="102", low="99", close="100.5"),
    ]
    bearish_series = [
        candle(0, high="100", low="98", close="99"),
        candle(1, high="101", low="98", close="99.5"),
    ]

    bullish = detect_level_interactions(bullish_series, [level()])
    bearish = detect_level_interactions(bearish_series, [level()])

    assert bullish[0].kind is LevelInteractionKind.BULLISH_REJECTION
    assert bullish[0].implication_direction is StructureDirection.BULLISH
    assert bearish[0].kind is LevelInteractionKind.BEARISH_REJECTION
    assert bearish[0].implication_direction is StructureDirection.BEARISH


def test_exact_on_level_two_sided_rejection_is_ambiguous() -> None:
    series = [
        candle(0, high="101", low="99", close="100"),
        candle(1, high="102", low="98", close="100"),
    ]

    event = detect_level_interactions(series, [level()])[0]

    assert event.kind is LevelInteractionKind.AMBIGUOUS_TWO_SIDED
    assert event.implication_direction is StructureDirection.UNKNOWN


def test_level_cannot_generate_event_before_market_or_local_availability() -> None:
    series = [
        candle(0, high="100", low="98", close="99"),
        candle(1, high="102", low="99.5", close="101"),
        candle(2, high="101", low="99", close="100"),
    ]

    market_late = level(available_index=2, observed_index=2)
    assert detect_level_interactions(series, [market_late]) == ()

    local_late = replace(
        level(available_index=0, observed_index=2),
        observed_at_ms=series[2].ingested_at_ms + 1,
    )
    assert detect_level_interactions(series, [local_late]) == ()


def test_top_level_as_of_filters_future_level_availability() -> None:
    series = [
        candle(0, high="100", low="98", close="99"),
        candle(1, high="102", low="99.5", close="101"),
        candle(2, high="101", low="99", close="100"),
    ]
    future_level = level(available_index=0, observed_index=2)

    before = analyze_level_interactions(
        series,
        [future_level],
        as_of_ms=series[1].ingested_at_ms,
    )
    after = analyze_level_interactions(
        series,
        [future_level],
        as_of_ms=series[2].ingested_at_ms,
    )

    assert before.levels == ()
    assert before.events == ()
    assert after.levels == (future_level,)


def test_range_reference_levels_require_complete_numeric_truth() -> None:
    incomplete = HighLowRangeEvidence(
        label="previous_day",
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        start_ms=0,
        end_exclusive_ms=86_400_000,
        expected_count=96,
        observed_count=95,
        missing_open_times_ms=(900_000,),
        complete=False,
        high=None,
        low=None,
        high_candle_identity=None,
        low_candle_identity=None,
        market_complete_at_ms=86_399_999,
        observed_at_ms=None,
    )
    assert reference_levels_from_range(incomplete) == ()

    complete = replace(
        incomplete,
        observed_count=96,
        missing_open_times_ms=(),
        complete=True,
        high=Decimal(110),
        low=Decimal(90),
        high_candle_identity=("bybit", "spot", "BTCUSDT", "15m", 0),
        low_candle_identity=("bybit", "spot", "BTCUSDT", "15m", 900_000),
        observed_at_ms=86_400_001,
    )
    levels = reference_levels_from_range(complete)

    assert [item.label for item in levels] == ["previous_day:high", "previous_day:low"]
    assert [item.price for item in levels] == [Decimal(110), Decimal(90)]
    assert all(item.available_at_market_ms == 86_399_999 for item in levels)


def test_periodic_open_reference_level_preserves_pit_availability() -> None:
    value = PeriodicOpen(
        period=Period.DAILY,
        period_start_ms=0,
        price=Decimal(100),
        market_available_from_ms=0,
        observed_at_ms=1_000,
        source_candle_identity=("bybit", "spot", "BTCUSDT", "15m", 0),
    )

    converted = reference_level_from_periodic_open(value)

    assert converted.label == "daily_open"
    assert converted.price == Decimal(100)
    assert converted.available_at_market_ms == 0
    assert converted.observed_at_ms == 1_000
