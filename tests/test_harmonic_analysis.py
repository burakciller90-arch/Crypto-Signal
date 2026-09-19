from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.harmonic.models import HarmonicPatternKind

CENTERS = (
    1050,
    1025,
    1000,
    1033,
    1066,
    1100,
    1080,
    1060,
    1040,
    1055,
    1070,
    1080,
    1060,
    1040,
    1020,
    1030,
)


def candle(index: int, center: int) -> Candle:
    open_time_ms = index * 900_000
    price = Decimal(center)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=price,
        high=price + Decimal(1),
        low=price - Decimal(1),
        close=price,
        volume=Decimal(1),
        quote_volume=Decimal(1000),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_000,
        ingested_at_ms=open_time_ms + 900_999,
        adapter_version="test/1",
    )


def series() -> list[Candle]:
    return [candle(index, center) for index, center in enumerate(CENTERS)]


def test_candidate_does_not_exist_before_right_bar_confirmation() -> None:
    candles = series()

    before = analyze_harmonics(
        candles,
        left_bars=1,
        right_bars=1,
        as_of_ms=candles[14].ingested_at_ms,
    )
    after = analyze_harmonics(
        candles,
        left_bars=1,
        right_bars=1,
        as_of_ms=candles[15].ingested_at_ms,
    )
    assert before.candidates == ()
    assert before.valid_matches == ()

    assert len(after.candidates) == 1
    valid_patterns = {match.pattern for match in after.valid_matches}
    assert HarmonicPatternKind.GARTLEY in valid_patterns
    assert all(
        match.candidate.market_available_at_ms <= after.as_of_ms
        and match.candidate.observed_at_ms <= after.as_of_ms
        for match in after.matches
    )


def test_future_input_does_not_change_past_as_of_result() -> None:
    candles = series()
    as_of_ms = candles[15].ingested_at_ms
    future = [
        candle(16, 1050),
        candle(17, 1070),
        candle(18, 1030),
    ]

    left = analyze_harmonics(
        candles,
        left_bars=1,
        right_bars=1,
        as_of_ms=as_of_ms,
    )
    right = analyze_harmonics(
        [*candles, *future],
        left_bars=1,
        right_bars=1,
        as_of_ms=as_of_ms,
    )

    assert left == right
