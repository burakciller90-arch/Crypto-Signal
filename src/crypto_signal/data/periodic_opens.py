from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Candle


class Period(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass(frozen=True, slots=True)
class PeriodicOpen:
    period: Period
    period_start_ms: int
    price: Decimal
    market_available_from_ms: int
    observed_at_ms: int
    source_candle_identity: tuple[str, str, str, str, int]


def period_start_ms(period: Period, as_of_ms: int) -> int:
    if as_of_ms < 0:
        raise ValueError("as_of_ms must be non-negative")

    current = datetime.fromtimestamp(as_of_ms / 1000, tz=UTC)
    day = current.replace(hour=0, minute=0, second=0, microsecond=0)

    if period is Period.DAILY:
        start = day
    elif period is Period.WEEKLY:
        start = day - timedelta(days=day.weekday())
    elif period is Period.MONTHLY:
        start = day.replace(day=1)
    elif period is Period.YEARLY:
        start = day.replace(month=1, day=1)
    else:
        raise ValueError(f"unsupported period: {period}")

    return int(start.timestamp()) * 1000


def resolve_periodic_open(
    candles: Sequence[Candle],
    *,
    period: Period,
    as_of_ms: int,
    require_observed: bool = True,
) -> PeriodicOpen | None:
    start_ms = period_start_ms(period, as_of_ms)
    candidates = [
        candle
        for candle in candles
        if candle.timeframe == "15m"
        and candle.open_time_ms == start_ms
        and candle.open_time_ms <= as_of_ms
        and (not require_observed or candle.ingested_at_ms <= as_of_ms)
    ]
    if len(candidates) > 1:
        raise ValueError("duplicate source candle for periodic open")
    if not candidates:
        return None

    candle = candidates[0]
    return PeriodicOpen(
        period=period,
        period_start_ms=start_ms,
        price=candle.open,
        market_available_from_ms=start_ms,
        observed_at_ms=candle.ingested_at_ms,
        source_candle_identity=candle.identity,
    )
