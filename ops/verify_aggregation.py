from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.aggregation import aggregate_closed_15m
from crypto_signal.data.models import Candle
from crypto_signal.data.periodic_opens import Period, resolve_periodic_open


def previous_full_week() -> tuple[int, int]:
    now = datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    this_week = day - timedelta(days=day.weekday())
    start = this_week - timedelta(days=7)
    end = this_week
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def assert_market_equal(derived: Candle, native: Candle) -> None:
    assert derived.open_time_ms == native.open_time_ms
    assert derived.close_time_ms == native.close_time_ms
    assert derived.open == native.open
    assert derived.high == native.high
    assert derived.low == native.low
    assert derived.close == native.close
    assert derived.volume == native.volume
    assert derived.quote_volume == native.quote_volume


async def verify_timeframes(adapter: BybitSpotAdapter, base: tuple[Candle, ...]) -> None:
    week_start = base[0].open_time_ms
    week_end_exclusive = base[-1].close_time_ms + 1
    expected_counts = {"1h": 168, "4h": 42, "1D": 7, "1W": 1}

    for timeframe, expected_count in expected_counts.items():
        derived = aggregate_closed_15m(base, target_timeframe=timeframe)
        assert derived.incomplete == ()
        assert len(derived.candles) == expected_count

        native = await adapter.fetch_candles(
            symbol="BTCUSDT",
            timeframe=timeframe,
            limit=expected_count,
            start_ms=week_start,
            end_ms=week_end_exclusive - 1,
        )
        assert len(native) == expected_count

        for left, right in zip(derived.candles, native, strict=True):
            assert_market_equal(left, right)

        print(timeframe, "reconciled", expected_count)


async def verify_periodic_opens(adapter: BybitSpotAdapter) -> None:
    now = datetime.now(UTC)
    starts = {
        Period.DAILY: now.replace(hour=0, minute=0, second=0, microsecond=0),
        Period.WEEKLY: (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=now.weekday())
        ),
        Period.MONTHLY: now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        Period.YEARLY: now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
    }

    boundary_candles: list[Candle] = []
    expected: dict[Period, Decimal] = {}
    for period, start in starts.items():
        start_ms = int(start.timestamp() * 1000)
        items = await adapter.fetch_candles(
            symbol="BTCUSDT",
            timeframe="15m",
            limit=1,
            start_ms=start_ms,
            end_ms=start_ms + 899_999,
        )
        assert len(items) == 1
        assert items[0].open_time_ms == start_ms
        boundary_candles.append(items[0])
        expected[period] = items[0].open

    now_ms = max(
        int(datetime.now(UTC).timestamp() * 1000),
        max(candle.ingested_at_ms for candle in boundary_candles),
    )
    for period, expected_open in expected.items():
        value = resolve_periodic_open(
            boundary_candles,
            period=period,
            as_of_ms=now_ms,
        )
        assert value is not None
        assert value.price == expected_open
        print(period.value, "open", value.price)


async def main() -> None:
    adapter = BybitSpotAdapter()
    week_start, week_end = previous_full_week()
    base = await adapter.fetch_candles(
        symbol="BTCUSDT",
        timeframe="15m",
        limit=672,
        start_ms=week_start,
        end_ms=week_end - 1,
    )

    assert len(base) == 672
    assert all(candle.is_closed for candle in base)
    assert base[0].open_time_ms == week_start
    assert base[-1].close_time_ms == week_end - 1
    print("base_15m", len(base), datetime.fromtimestamp(week_start / 1000, tz=UTC).date())

    await verify_timeframes(adapter, base)
    await verify_periodic_opens(adapter)


if __name__ == "__main__":
    asyncio.run(main())
