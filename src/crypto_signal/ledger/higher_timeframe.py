from __future__ import annotations

from dataclasses import dataclass

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.aggregation import AggregationResult, aggregate_closed_15m
from crypto_signal.data.models import Candle
from crypto_signal.data.recovery import BackfillReport, backfill_range
from crypto_signal.data.source_contract import SourceContractStore
from crypto_signal.data.store import CandleStore
from crypto_signal.data.timeframes import (
    bucket_open_ms,
    is_aligned_open,
    spec,
)
from crypto_signal.ledger.coverage import (
    BASE_TIMEFRAME,
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)


@dataclass(frozen=True, slots=True)
class HigherTimeframeHistoryPlan:
    target_timeframe: str
    target_count: int
    first_target_open_ms: int
    last_target_open_ms: int
    base_start_open_ms: int
    base_end_open_ms: int
    expected_base_count: int

    def __post_init__(self) -> None:
        if self.target_timeframe == BASE_TIMEFRAME:
            raise ValueError("higher-timeframe plan cannot target 15m")
        if self.target_count <= 0 or self.expected_base_count <= 0:
            raise ValueError("higher-timeframe plan counts must be positive")
        if self.first_target_open_ms > self.last_target_open_ms:
            raise ValueError("invalid target window")
        if self.base_start_open_ms > self.base_end_open_ms:
            raise ValueError("invalid base window")


@dataclass(frozen=True, slots=True)
class HigherTimeframePreparation:
    plan: HigherTimeframeHistoryPlan
    fetch_reports: tuple[BackfillReport, ...]
    base_candles: tuple[Candle, ...]
    aggregation: AggregationResult
    missing_base_open_times_ms: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return (
            not self.missing_base_open_times_ms
            and not self.aggregation.incomplete
            and len(self.aggregation.candles) == self.plan.target_count
        )


def plan_higher_timeframe_history(
    context: LiveCoverageContext,
    *,
    base_source_cutoff_open_ms: int,
) -> HigherTimeframeHistoryPlan:
    if (
        context.source_strategy
        is not LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
    ):
        raise ValueError(
            "higher-timeframe history requires canonical aggregation strategy"
        )
    if context.timeframe == BASE_TIMEFRAME:
        raise ValueError("higher-timeframe history cannot target 15m")
    if not is_aligned_open(base_source_cutoff_open_ms, BASE_TIMEFRAME):
        raise ValueError("base source cutoff must align to canonical 15m grid")

    base = spec(BASE_TIMEFRAME)
    target = spec(context.timeframe)
    ratio = target.duration_ms // base.duration_ms
    current_bucket = bucket_open_ms(
        base_source_cutoff_open_ms,
        context.timeframe,
    )
    current_bucket_last_base_open = (
        current_bucket + target.duration_ms - base.duration_ms
    )
    if base_source_cutoff_open_ms >= current_bucket_last_base_open:
        last_target_open = current_bucket
    else:
        last_target_open = current_bucket - target.duration_ms

    if last_target_open < 0:
        raise ValueError("insufficient history before first complete target bucket")

    first_target_open = (
        last_target_open
        - (context.freeze_limit - 1) * target.duration_ms
    )
    if first_target_open < 0:
        raise ValueError("target history window starts before epoch")

    base_start = first_target_open
    base_end = (
        last_target_open + target.duration_ms - base.duration_ms
    )
    return HigherTimeframeHistoryPlan(
        target_timeframe=context.timeframe,
        target_count=context.freeze_limit,
        first_target_open_ms=first_target_open,
        last_target_open_ms=last_target_open,
        base_start_open_ms=base_start,
        base_end_open_ms=base_end,
        expected_base_count=context.freeze_limit * ratio,
    )


def expected_base_open_times(
    plan: HigherTimeframeHistoryPlan,
) -> tuple[int, ...]:
    duration_ms = spec(BASE_TIMEFRAME).duration_ms
    return tuple(
        range(
            plan.base_start_open_ms,
            plan.base_end_open_ms + duration_ms,
            duration_ms,
        )
    )


def _missing_ranges(
    missing_open_times_ms: tuple[int, ...],
) -> tuple[tuple[int, int], ...]:
    if not missing_open_times_ms:
        return ()
    duration_ms = spec(BASE_TIMEFRAME).duration_ms
    ranges: list[tuple[int, int]] = []
    start = missing_open_times_ms[0]
    previous = start
    for open_time_ms in missing_open_times_ms[1:]:
        if open_time_ms != previous + duration_ms:
            ranges.append((start, previous))
            start = open_time_ms
        previous = open_time_ms
    ranges.append((start, previous))
    return tuple(ranges)


def _cached_closed_window(
    store: CandleStore,
    context: LiveCoverageContext,
    plan: HigherTimeframeHistoryPlan,
) -> tuple[Candle, ...]:
    return tuple(
        candle
        for candle in store.list_candles(
            exchange=context.exchange,
            market_type=context.market_type,
            symbol=context.symbol,
            timeframe=BASE_TIMEFRAME,
        )
        if (
            plan.base_start_open_ms
            <= candle.open_time_ms
            <= plan.base_end_open_ms
            and candle.is_closed
        )
    )


async def prepare_higher_timeframe_history(
    adapter: MarketDataAdapter,
    store: CandleStore,
    context: LiveCoverageContext,
    *,
    base_source_cutoff_open_ms: int,
    page_limit: int = 1000,
    source_store: SourceContractStore | None = None,
) -> HigherTimeframePreparation:
    plan = plan_higher_timeframe_history(
        context,
        base_source_cutoff_open_ms=base_source_cutoff_open_ms,
    )
    expected = expected_base_open_times(plan)

    cached = _cached_closed_window(store, context, plan)
    cached_by_open = {candle.open_time_ms: candle for candle in cached}
    missing_before = tuple(
        open_time_ms
        for open_time_ms in expected
        if open_time_ms not in cached_by_open
    )

    reports: list[BackfillReport] = []
    for start_open_ms, end_open_ms in _missing_ranges(missing_before):
        reports.append(
            await backfill_range(
                adapter,
                store,
                symbol=context.symbol,
                timeframe=BASE_TIMEFRAME,
                start_open_ms=start_open_ms,
                end_open_ms=end_open_ms,
                page_limit=page_limit,
                require_closed=True,
                source_store=source_store,
            )
        )

    base_candles = _cached_closed_window(store, context, plan)
    for candle in base_candles:
        if candle.exchange is not context.exchange:
            raise ValueError("cached base candle exchange mismatch")
        if candle.market_type is not context.market_type:
            raise ValueError("cached base candle market type mismatch")
        if candle.symbol != context.symbol:
            raise ValueError("cached base candle symbol mismatch")
        if candle.timeframe != BASE_TIMEFRAME:
            raise ValueError("cached base candle timeframe mismatch")

    by_open = {candle.open_time_ms: candle for candle in base_candles}
    missing_after = tuple(
        open_time_ms
        for open_time_ms in expected
        if open_time_ms not in by_open
    )
    ordered_base = tuple(
        by_open[open_time_ms]
        for open_time_ms in expected
        if open_time_ms in by_open
    )
    aggregation = aggregate_closed_15m(
        ordered_base,
        target_timeframe=context.timeframe,
    )
    return HigherTimeframePreparation(
        plan=plan,
        fetch_reports=tuple(reports),
        base_candles=ordered_base,
        aggregation=aggregation,
        missing_base_open_times_ms=missing_after,
    )
