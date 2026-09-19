from datetime import UTC, datetime, time
from decimal import Decimal

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.price_action.levels import (
    PreviousPeriodKind,
    SessionSpec,
    latest_completed_session_window,
    resolve_latest_completed_session,
    resolve_previous_periods,
)

BASE = 900_000


def ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def candle(open_time_ms: int, index: int, *, ingested_at_ms: int | None = None) -> Candle:
    high = Decimal(10_000 + index)
    low = Decimal(5_000 + (index % 10))
    midpoint = (high + low) / Decimal(2)
    close_time_ms = open_time_ms + BASE - 1
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=midpoint,
        high=high,
        low=low,
        close=midpoint,
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=close_time_ms + 1,
        ingested_at_ms=(
            close_time_ms + 2
            if ingested_at_ms is None
            else ingested_at_ms
        ),
        adapter_version="test/1",
    )


def candles_between(start_ms: int, end_ms: int) -> list[Candle]:
    return [
        candle(open_ms, index)
        for index, open_ms in enumerate(range(start_ms, end_ms, BASE))
    ]


def test_previous_day_week_month_require_complete_15m_grids() -> None:
    as_of = ms(2026, 9, 20, 12)
    source = candles_between(ms(2026, 8, 1), as_of)

    result = dict(resolve_previous_periods(source, as_of_ms=as_of))

    day = result[PreviousPeriodKind.DAY]
    week = result[PreviousPeriodKind.WEEK]
    month = result[PreviousPeriodKind.MONTH]

    assert day.complete is True
    assert day.expected_count == 96
    assert day.observed_count == 96
    assert day.high is not None and day.low is not None

    assert week.complete is True
    assert week.expected_count == 7 * 96
    assert week.observed_count == 7 * 96
    assert week.high is not None and week.low is not None

    assert month.complete is True
    assert month.expected_count == 31 * 96
    assert month.observed_count == 31 * 96
    assert month.high is not None and month.low is not None


def test_missing_previous_day_candle_suppresses_numeric_truth() -> None:
    as_of = ms(2026, 9, 20, 12)
    source = candles_between(ms(2026, 9, 18), as_of)
    missing_open = ms(2026, 9, 19, 12)
    source = [item for item in source if item.open_time_ms != missing_open]

    result = dict(resolve_previous_periods(source, as_of_ms=as_of))
    day = result[PreviousPeriodKind.DAY]

    assert day.complete is False
    assert day.observed_count == 95
    assert day.missing_open_times_ms == (missing_open,)
    assert day.high is None
    assert day.low is None
    assert day.high_candle_identity is None
    assert day.low_candle_identity is None


def test_late_ingest_is_missing_at_earlier_as_of() -> None:
    as_of = ms(2026, 9, 20, 12)
    source = candles_between(ms(2026, 9, 19), as_of)
    delayed_open = ms(2026, 9, 19, 10)
    source = [
        candle(
            item.open_time_ms,
            index,
            ingested_at_ms=(
                as_of + 1
                if item.open_time_ms == delayed_open
                else item.ingested_at_ms
            ),
        )
        for index, item in enumerate(source)
    ]

    day = dict(resolve_previous_periods(source, as_of_ms=as_of))[PreviousPeriodKind.DAY]

    assert day.complete is False
    assert delayed_open in day.missing_open_times_ms
    assert day.high is None
    assert day.low is None


def test_session_timezone_resolves_latest_completed_window() -> None:
    session = SessionSpec(
        name="explicit_istanbul_morning",
        timezone="Europe/Istanbul",
        start_local=time(9, 0),
        end_local=time(11, 0),
    )
    as_of = ms(2026, 9, 20, 12)

    start_ms, end_ms = latest_completed_session_window(
        session=session,
        as_of_ms=as_of,
    )

    assert start_ms == ms(2026, 9, 20, 6)
    assert end_ms == ms(2026, 9, 20, 8)

    source = candles_between(ms(2026, 9, 20), as_of)
    evidence = resolve_latest_completed_session(
        source,
        session=session,
        as_of_ms=as_of,
    )

    assert evidence.complete is True
    assert evidence.expected_count == 8
    assert evidence.observed_count == 8
    assert evidence.label == "session:explicit_istanbul_morning"


def test_cross_midnight_session_resolves_previous_completed_window() -> None:
    session = SessionSpec(
        name="explicit_cross_midnight",
        timezone="UTC",
        start_local=time(22, 0),
        end_local=time(2, 0),
    )
    as_of = ms(2026, 9, 20, 3)

    start_ms, end_ms = latest_completed_session_window(
        session=session,
        as_of_ms=as_of,
    )

    assert start_ms == ms(2026, 9, 19, 22)
    assert end_ms == ms(2026, 9, 20, 2)


def test_session_boundary_must_align_to_15m() -> None:
    with pytest.raises(ValueError, match="15-minute"):
        SessionSpec(
            name="bad",
            timezone="UTC",
            start_local=time(9, 7),
            end_local=time(10, 0),
        )
