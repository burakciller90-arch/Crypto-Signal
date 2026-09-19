from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind
from crypto_signal.primitives.swings import (
    compress_alternating_pivots,
    detect_fractal_pivots,
)


def candles(highs: list[int], lows: list[int]) -> list[Candle]:
    assert len(highs) == len(lows)
    result: list[Candle] = []
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        open_time_ms = index * 900_000
        result.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                open_time_ms=open_time_ms,
                close_time_ms=open_time_ms + 899_999,
                open=Decimal(high + low) / Decimal(2),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(high + low) / Decimal(2),
                volume=Decimal(1),
                quote_volume=Decimal(100),
                trade_count=None,
                is_closed=True,
                source=DataSource.REST,
                source_timestamp_ms=open_time_ms + 1_000_000,
                ingested_at_ms=open_time_ms + 1_001_000,
                adapter_version="test/1",
            )
        )
    return result


def test_pivot_requires_right_side_confirmation() -> None:
    series = candles([100, 102, 110, 103, 101], [90, 91, 92, 93, 94])

    assert detect_fractal_pivots(series[:4], left_bars=2, right_bars=2) == ()

    pivots = detect_fractal_pivots(series, left_bars=2, right_bars=2)
    highs = [pivot for pivot in pivots if pivot.kind is PivotKind.HIGH]
    assert len(highs) == 1
    pivot = highs[0]
    assert pivot.candle_index == 2
    assert pivot.price == Decimal(110)
    assert pivot.market_confirmed_at_ms == series[4].close_time_ms
    assert pivot.observed_at_ms == series[4].ingested_at_ms
    assert pivot.confirmation_candle_identity == series[4].identity


def test_strict_tie_does_not_create_pivot() -> None:
    series = candles([100, 110, 110, 100], [90, 91, 92, 93])
    pivots = detect_fractal_pivots(series, left_bars=1, right_bars=1)
    assert all(pivot.kind is not PivotKind.HIGH for pivot in pivots)
def test_gap_and_open_candle_are_rejected() -> None:
    series = candles([100, 102, 110, 103, 101], [90, 91, 92, 93, 94])
    with pytest.raises(ValueError, match="closed candles"):
        detect_fractal_pivots(
            [*series[:-1], replace(series[-1], is_closed=False)],
            left_bars=2,
            right_bars=2,
        )

    with pytest.raises(ValueError, match="gapless chronological"):
        detect_fractal_pivots(
            [series[0], series[1], series[3], series[4]],
            left_bars=1,
            right_bars=1,
        )


def test_outside_bar_is_explicitly_ambiguous() -> None:
    series = candles([100, 101, 110, 102, 99], [90, 89, 80, 88, 91])
    pivots = detect_fractal_pivots(series, left_bars=2, right_bars=2)

    center = [pivot for pivot in pivots if pivot.candle_index == 2]
    assert {pivot.kind for pivot in center} == {PivotKind.HIGH, PivotKind.LOW}
    assert all(pivot.same_bar_ambiguity for pivot in center)

    compressed = compress_alternating_pivots(pivots)
    assert compressed.ambiguous_source_indices == (2,)
    assert compressed.swings == ()


def pivot(kind: PivotKind, index: int, price: int) -> ConfirmedPivot:
    open_time_ms = index * 900_000
    return ConfirmedPivot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        kind=kind,
        candle_index=index,
        open_time_ms=open_time_ms,
        price=Decimal(price),
        left_bars=1,
        right_bars=1,
        market_confirmed_at_ms=open_time_ms + 1_799_999,
        observed_at_ms=open_time_ms + 1_800_999,
        source_candle_identity=("bybit", "spot", "BTCUSDT", "15m", open_time_ms),
        confirmation_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            open_time_ms + 900_000,
        ),
    )


def test_alternating_compression_keeps_more_extreme_same_kind() -> None:
    result = compress_alternating_pivots(
        [
            pivot(PivotKind.HIGH, 1, 100),
            pivot(PivotKind.HIGH, 2, 105),
            pivot(PivotKind.LOW, 3, 90),
            pivot(PivotKind.LOW, 4, 85),
            pivot(PivotKind.HIGH, 5, 110),
        ]
    )

    assert [(item.kind, item.candle_index, item.price) for item in result.swings] == [
        (PivotKind.HIGH, 2, Decimal(105)),
        (PivotKind.LOW, 4, Decimal(85)),
        (PivotKind.HIGH, 5, Decimal(110)),
    ]
    assert result.ambiguous_source_indices == ()

def test_alternating_compression_rejects_mixed_or_duplicate_pivots() -> None:
    first = pivot(PivotKind.HIGH, 1, 100)

    with pytest.raises(ValueError, match="mix pivot semantics"):
        compress_alternating_pivots([first, replace(first, symbol="ETHUSDT", candle_index=2)])

    with pytest.raises(ValueError, match="duplicate same-kind"):
        compress_alternating_pivots([first, first])
