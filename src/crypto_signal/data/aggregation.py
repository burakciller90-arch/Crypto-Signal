from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource
from crypto_signal.data.timeframes import spec

BASE_TIMEFRAME = "15m"
AGGREGATOR_VERSION = "aggregate-15m/1"
WEEK_ANCHOR_MS = 4 * 24 * 60 * 60_000  # Monday 1970-01-05 00:00 UTC.


@dataclass(frozen=True, slots=True)
class IncompleteBucket:
    timeframe: str
    bucket_open_ms: int
    expected_count: int
    actual_count: int
    missing_open_times_ms: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AggregationResult:
    candles: tuple[Candle, ...]
    incomplete: tuple[IncompleteBucket, ...]


def bucket_open_ms(open_time_ms: int, timeframe: str) -> int:
    target = spec(timeframe)
    if timeframe == BASE_TIMEFRAME:
        return open_time_ms
    anchor_ms = WEEK_ANCHOR_MS if timeframe == "1W" else 0
    return anchor_ms + ((open_time_ms - anchor_ms) // target.duration_ms) * target.duration_ms


def aggregate_closed_15m(
    candles: Sequence[Candle],
    *,
    target_timeframe: str,
) -> AggregationResult:
    if target_timeframe not in {"1h", "4h", "1D", "1W"}:
        raise ValueError("target timeframe must be one of 1h, 4h, 1D, 1W")
    if not candles:
        return AggregationResult((), ())

    base = spec(BASE_TIMEFRAME)
    target = spec(target_timeframe)
    expected_count = target.duration_ms // base.duration_ms

    first = candles[0]
    for candle in candles:
        if candle.timeframe != BASE_TIMEFRAME:
            raise ValueError("aggregation requires canonical 15m candles")
        if not candle.is_closed:
            raise ValueError("aggregation requires closed 15m candles")
        if candle.exchange != first.exchange or candle.market_type != first.market_type:
            raise ValueError("aggregation cannot mix exchanges or market types")
        if candle.symbol != first.symbol:
            raise ValueError("aggregation cannot mix symbols")
        if candle.open_time_ms % base.duration_ms != 0:
            raise ValueError("15m candle is off the canonical UTC grid")

    by_bucket: dict[int, list[Candle]] = defaultdict(list)
    for candle in candles:
        by_bucket[bucket_open_ms(candle.open_time_ms, target_timeframe)].append(candle)

    output: list[Candle] = []
    incomplete: list[IncompleteBucket] = []
    for bucket_start in sorted(by_bucket):
        items = sorted(by_bucket[bucket_start], key=lambda candle: candle.open_time_ms)
        actual_opens = [candle.open_time_ms for candle in items]
        if len(set(actual_opens)) != len(actual_opens):
            raise ValueError("duplicate 15m candle in aggregation input")

        expected_opens = tuple(
            bucket_start + index * base.duration_ms for index in range(expected_count)
        )
        missing = tuple(open_ms for open_ms in expected_opens if open_ms not in set(actual_opens))
        if missing or len(items) != expected_count:
            incomplete.append(
                IncompleteBucket(
                    timeframe=target_timeframe,
                    bucket_open_ms=bucket_start,
                    expected_count=expected_count,
                    actual_count=len(items),
                    missing_open_times_ms=missing,
                )
            )
            continue

        quote_volume = (
            sum((item.quote_volume for item in items if item.quote_volume is not None), Decimal(0))
            if all(item.quote_volume is not None for item in items)
            else None
        )
        trade_count = (
            sum(item.trade_count for item in items if item.trade_count is not None)
            if all(item.trade_count is not None for item in items)
            else None
        )
        output.append(
            Candle(
                exchange=first.exchange,
                market_type=first.market_type,
                symbol=first.symbol,
                timeframe=target_timeframe,
                open_time_ms=bucket_start,
                close_time_ms=bucket_start + target.duration_ms - 1,
                open=items[0].open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=items[-1].close,
                volume=sum((item.volume for item in items), Decimal(0)),
                quote_volume=quote_volume,
                trade_count=trade_count,
                is_closed=True,
                source=DataSource.AGGREGATED,
                source_timestamp_ms=max(item.source_timestamp_ms for item in items),
                ingested_at_ms=max(item.ingested_at_ms for item in items),
                adapter_version=AGGREGATOR_VERSION,
            )
        )

    return AggregationResult(tuple(output), tuple(incomplete))
