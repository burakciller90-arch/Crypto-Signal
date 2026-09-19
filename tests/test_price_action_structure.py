from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.price_action.models import (
    StructureBreakKind,
    StructureDirection,
    SwingRelation,
)
from crypto_signal.methodologies.price_action.structure import (
    analyze_structure,
    detect_structure_breaks,
    label_swings,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind


def candle(index: int, close: int = 105, high: int = 120, low: int = 80) -> Candle:
    open_time_ms = index * 900_000
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(100),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_500,
        ingested_at_ms=open_time_ms + 901_000,
        adapter_version="test/1",
    )


def pivot(kind: PivotKind, index: int, price: int, confirm_index: int) -> ConfirmedPivot:
    source = candle(index)
    confirmation = candle(confirm_index)
    return ConfirmedPivot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        kind=kind,
        candle_index=index,
        open_time_ms=source.open_time_ms,
        price=Decimal(price),
        left_bars=1,
        right_bars=confirm_index - index,
        market_confirmed_at_ms=confirmation.close_time_ms,
        observed_at_ms=confirmation.ingested_at_ms,
        source_candle_identity=source.identity,
        confirmation_candle_identity=confirmation.identity,
    )


def test_swing_relations_are_structured() -> None:
    swings = [
        pivot(PivotKind.HIGH, 1, 100, 2),
        pivot(PivotKind.LOW, 2, 90, 3),
        pivot(PivotKind.HIGH, 3, 105, 4),
        pivot(PivotKind.LOW, 4, 92, 5),
        pivot(PivotKind.HIGH, 5, 103, 6),
        pivot(PivotKind.LOW, 6, 88, 7),
        pivot(PivotKind.HIGH, 7, 103, 8),
        pivot(PivotKind.LOW, 8, 88, 9),
    ]

    relations = [item.relation for item in label_swings(swings)]

    assert relations == [
        SwingRelation.UNCLASSIFIED,
        SwingRelation.UNCLASSIFIED,
        SwingRelation.HIGHER_HIGH,
        SwingRelation.HIGHER_LOW,
        SwingRelation.LOWER_HIGH,
        SwingRelation.LOWER_LOW,
        SwingRelation.EQUAL_HIGH,
        SwingRelation.EQUAL_LOW,
    ]


def test_structure_breaks_classify_bos_then_choch() -> None:
    series = [candle(index) for index in range(10)]
    series[5] = candle(5, close=111, high=115, low=95)
    series[9] = candle(9, close=99, high=110, low=95)
    swings = [
        pivot(PivotKind.HIGH, 2, 110, 4),
        pivot(PivotKind.LOW, 6, 100, 8),
    ]

    events, direction = detect_structure_breaks(series, swings)

    assert len(events) == 2
    assert events[0].kind is StructureBreakKind.BOS
    assert events[0].direction is StructureDirection.BULLISH
    assert events[0].broken_pivot == swings[0]
    assert events[1].kind is StructureBreakKind.CHOCH_MSB
    assert events[1].direction is StructureDirection.BEARISH
    assert events[1].broken_pivot == swings[1]
    assert direction is StructureDirection.BEARISH


def test_wick_only_penetration_is_not_structure_break() -> None:
    series = [candle(index) for index in range(6)]
    series[5] = candle(5, close=109, high=115, low=95)
    swings = [pivot(PivotKind.HIGH, 2, 110, 4)]

    events, direction = detect_structure_breaks(series, swings)

    assert events == ()
    assert direction is StructureDirection.UNKNOWN


def test_top_level_analysis_does_not_see_unconfirmed_pivot() -> None:
    highs = [100, 102, 110, 103, 101]
    lows = [90, 91, 92, 93, 94]
    series = [
        candle(index, close=(high + low) // 2, high=high, low=low)
        for index, (high, low) in enumerate(zip(highs, lows, strict=True))
    ]

    before_confirmation = analyze_structure(
        series,
        left_bars=2,
        right_bars=2,
        as_of_ms=series[3].ingested_at_ms,
    )
    after_confirmation = analyze_structure(
        series,
        left_bars=2,
        right_bars=2,
        as_of_ms=series[4].ingested_at_ms,
    )

    assert before_confirmation.confirmed_pivots == ()
    assert len(after_confirmation.confirmed_pivots) == 1
    assert after_confirmation.confirmed_pivots[0].kind is PivotKind.HIGH
