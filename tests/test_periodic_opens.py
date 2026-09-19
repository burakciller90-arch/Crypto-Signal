from datetime import UTC, datetime
from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.periodic_opens import Period, period_start_ms, resolve_periodic_open


def candle(open_time_ms: int, *, price: str, ingested_at_ms: int) -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(price),
        high=Decimal(price) + Decimal(10),
        low=Decimal(price) - Decimal(10),
        close=Decimal(price) + Decimal(1),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=ingested_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version="test/1",
    )


def ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def test_period_boundaries_are_utc_and_week_starts_monday() -> None:
    as_of = ms(2026, 9, 19, 23, 5)

    assert period_start_ms(Period.DAILY, as_of) == ms(2026, 9, 19)
    assert period_start_ms(Period.WEEKLY, as_of) == ms(2026, 9, 14)
    assert period_start_ms(Period.MONTHLY, as_of) == ms(2026, 9, 1)
    assert period_start_ms(Period.YEARLY, as_of) == ms(2026, 1, 1)
def test_resolve_periodic_opens_uses_exact_boundary_candles() -> None:
    as_of = ms(2026, 9, 19, 23, 5)
    items = [
        candle(ms(2026, 9, 19), price="900", ingested_at_ms=ms(2026, 9, 19, 0, 1)),
        candle(ms(2026, 9, 14), price="800", ingested_at_ms=ms(2026, 9, 14, 0, 1)),
        candle(ms(2026, 9, 1), price="700", ingested_at_ms=ms(2026, 9, 1, 0, 1)),
        candle(ms(2026, 1, 1), price="600", ingested_at_ms=ms(2026, 1, 1, 0, 1)),
    ]

    daily = resolve_periodic_open(items, period=Period.DAILY, as_of_ms=as_of)
    weekly = resolve_periodic_open(items, period=Period.WEEKLY, as_of_ms=as_of)
    monthly = resolve_periodic_open(items, period=Period.MONTHLY, as_of_ms=as_of)
    yearly = resolve_periodic_open(items, period=Period.YEARLY, as_of_ms=as_of)

    assert daily is not None and daily.price == Decimal(900)
    assert weekly is not None and weekly.price == Decimal(800)
    assert monthly is not None and monthly.price == Decimal(700)
    assert yearly is not None and yearly.price == Decimal(600)


def test_point_in_time_requires_candle_to_have_been_observed() -> None:
    boundary = ms(2026, 9, 19)
    delayed = candle(boundary, price="900", ingested_at_ms=boundary + 10 * 60_000)
    as_of = boundary + 5 * 60_000

    assert resolve_periodic_open([delayed], period=Period.DAILY, as_of_ms=as_of) is None

    market_truth = resolve_periodic_open(
        [delayed],
        period=Period.DAILY,
        as_of_ms=as_of,
        require_observed=False,
    )
    assert market_truth is not None
    assert market_truth.market_available_from_ms == boundary
    assert market_truth.observed_at_ms == boundary + 10 * 60_000


def test_missing_boundary_candle_returns_none() -> None:
    as_of = ms(2026, 9, 19, 12)
    assert resolve_periodic_open([], period=Period.DAILY, as_of_ms=as_of) is None
