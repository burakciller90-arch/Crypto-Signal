from datetime import UTC, datetime
from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.price_action.analysis import analyze_price_action

BASE_MS = 900_000


def ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def make_series(start_ms: int, count: int) -> list[Candle]:
    output: list[Candle] = []
    for index in range(count):
        open_time_ms = start_ms + index * BASE_MS
        block = index % 12
        center = Decimal(1000 + (index // 12) * 2)
        if block in {2, 3}:
            center += Decimal(20)
        elif block in {8, 9}:
            center -= Decimal(20)

        open_price = center
        close_price = center + (Decimal(6) if index % 2 == 0 else Decimal(-6))
        high = max(open_price, close_price) + Decimal(4)
        low = min(open_price, close_price) - Decimal(4)

        output.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                open_time_ms=open_time_ms,
                close_time_ms=open_time_ms + BASE_MS - 1,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=Decimal(1),
                quote_volume=Decimal(1000),
                trade_count=None,
                is_closed=True,
                source=DataSource.REST,
                source_timestamp_ms=open_time_ms + BASE_MS,
                ingested_at_ms=open_time_ms + BASE_MS + 1,
                adapter_version="test/1",
            )
        )
    return output


def test_integrated_pa_uses_one_as_of_and_only_available_levels() -> None:
    start = ms(2026, 9, 18)
    candles = make_series(start, 240)
    as_of = candles[-1].ingested_at_ms

    result = analyze_price_action(candles, as_of_ms=as_of)

    assert result.as_of_ms == as_of
    assert {
        result.structure.as_of_ms,
        result.imbalances.as_of_ms,
        result.liquidity.as_of_ms,
        result.levels.as_of_ms,
        result.displacement.as_of_ms,
        result.level_interactions.as_of_ms,
    } == {as_of}

    labels = {level.label for level in result.reference_levels}
    assert "previous_day:high" in labels
    assert "previous_day:low" in labels
    assert "daily_open" in labels
    assert "previous_week:high" not in labels
    assert "previous_week:low" not in labels
    assert "previous_month:high" not in labels
    assert "previous_month:low" not in labels

    summary = result.summary
    assert summary.structure_break_count == len(result.structure.structure_breaks)
    assert summary.fair_value_gap_count == len(result.imbalances.fair_value_gaps)
    assert summary.balanced_price_range_count == len(
        result.imbalances.balanced_price_ranges
    )
    assert summary.liquidity_pool_count == len(result.liquidity.pools)
    assert summary.displacement_count == len(result.displacement.events)
    assert summary.reference_level_count == len(result.reference_levels)
    assert summary.level_interaction_count == len(result.level_interactions.events)


def test_future_input_candles_do_not_change_past_as_of_result() -> None:
    start = ms(2026, 9, 18)
    prefix = make_series(start, 220)
    extended = make_series(start, 240)
    as_of = prefix[-1].ingested_at_ms

    left = analyze_price_action(prefix, as_of_ms=as_of)
    right = analyze_price_action(extended, as_of_ms=as_of)

    assert left == right
