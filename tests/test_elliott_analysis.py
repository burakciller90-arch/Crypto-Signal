from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.elliott.analysis import analyze_elliott

CENTERS = (
    105,
    102,
    100,
    106,
    110,
    107,
    105,
    113,
    120,
    116,
    113,
    119,
    125,
    122,
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


def test_wave5_candidate_appears_only_after_final_pivot_confirmation() -> None:
    candles = series()

    before = analyze_elliott(
        candles,
        left_bars=1,
        right_bars=1,
        as_of_ms=candles[12].ingested_at_ms,
    )
    after = analyze_elliott(
        candles,
        left_bars=1,
        right_bars=1,
        as_of_ms=candles[13].ingested_at_ms,
    )

    assert not any(candidate.complete for candidate in before.impulse_candidates)
    completed = [
        candidate
        for candidate in after.impulse_candidates
        if candidate.complete and candidate.valid_so_far
    ]
    assert completed
    assert all(
        candidate.market_available_at_ms <= after.as_of_ms
        and candidate.observed_at_ms <= after.as_of_ms
        for candidate in completed
    )


def test_future_candles_do_not_change_prior_as_of_elliott_result() -> None:
    candles = series()
    as_of_ms = candles[13].ingested_at_ms
    future = [
        candle(14, 118),
        candle(15, 115),
        candle(16, 121),
    ]

    left = analyze_elliott(
        candles,
        left_bars=1,
        right_bars=1,
        as_of_ms=as_of_ms,
    )
    right = analyze_elliott(
        [*candles, *future],
        left_bars=1,
        right_bars=1,
        as_of_ms=as_of_ms,
    )

    assert left == right


def test_analysis_preserves_competing_counts_and_abc_candidates() -> None:
    result = analyze_elliott(
        series(),
        left_bars=1,
        right_bars=1,
    )

    assert result.impulse_candidates
    assert result.abc_candidates
    assert result.ambiguity
    assert any(item.candidate_count > 1 for item in result.ambiguity)
