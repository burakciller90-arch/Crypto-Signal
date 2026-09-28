from __future__ import annotations

from typing import cast

from crypto_signal.data.adapters.base import (
    MarketDataAdapter,
    SourceAwareMarketDataAdapter,
)
from crypto_signal.data.candle_source_contract import (
    persist_candle_source_snapshot,
)
from crypto_signal.data.source_contract import SourceContractStore
from crypto_signal.data.store import CandleStore
from crypto_signal.ledger.coverage import (
    BASE_TIMEFRAME,
    LiveCoverageContext,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.higher_timeframe import prepare_higher_timeframe_history
from crypto_signal.ledger.live_clock import (
    LiveFreezeResult,
    freeze_live_candles,
    freeze_live_provider,
)
from crypto_signal.ledger.store import ImmutableSignalLedger


async def _latest_closed_base_cutoff(
    adapter: MarketDataAdapter,
    context: LiveCoverageContext,
    *,
    candle_store: CandleStore,
    source_store: SourceContractStore | None = None,
) -> int:
    if source_store is not None:
        if not hasattr(adapter, "fetch_source_candles"):
            raise TypeError(
                "source-aware cutoff probe requires source-aware adapter"
            )
        snapshot = await cast(
            SourceAwareMarketDataAdapter,
            adapter,
        ).fetch_source_candles(
            symbol=context.symbol,
            timeframe=BASE_TIMEFRAME,
            limit=2,
        )
        persist_candle_source_snapshot(
            candle_store=candle_store,
            source_store=source_store,
            snapshot=snapshot,
        )
        latest = snapshot.candles
    else:
        latest = tuple(
            await adapter.fetch_candles(
                symbol=context.symbol,
                timeframe=BASE_TIMEFRAME,
                limit=2,
            )
        )
    eligible = tuple(
        candle
        for candle in latest
        if candle.is_closed
        and candle.exchange is context.exchange
        and candle.market_type is context.market_type
        and candle.symbol == context.symbol
        and candle.timeframe == BASE_TIMEFRAME
    )
    if not eligible:
        raise ValueError(
            "no canonical closed 15m candle available for higher timeframe"
        )
    return max(candle.open_time_ms for candle in eligible)


async def freeze_coverage_context(
    *,
    context: LiveCoverageContext,
    adapter: MarketDataAdapter,
    ledger: ImmutableSignalLedger,
    candle_store: CandleStore,
    source_store: SourceContractStore | None = None,
) -> LiveFreezeResult:
    if (
        context.source_strategy
        is LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
    ):
        return await freeze_live_provider(
            adapter=adapter,
            ledger=ledger,
            candle_store=candle_store,
            source_store=source_store,
            symbol=context.symbol,
            timeframe=context.timeframe,
            limit=context.freeze_limit,
            minimum_closed_candles=context.minimum_closed_candles,
        )

    if (
        context.source_strategy
        is not LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
    ):
        raise ValueError("unsupported live coverage source strategy")

    base_cutoff = await _latest_closed_base_cutoff(
        adapter,
        context,
        candle_store=candle_store,
        source_store=source_store,
    )
    prepared = await prepare_higher_timeframe_history(
        adapter,
        candle_store,
        context,
        base_source_cutoff_open_ms=base_cutoff,
        source_store=source_store,
    )
    if not prepared.complete:
        raise ValueError(
            "higher-timeframe preparation incomplete: "
            f"missing_base={len(prepared.missing_base_open_times_ms)} "
            f"incomplete_buckets={len(prepared.aggregation.incomplete)}"
        )

    return freeze_live_candles(
        candles=prepared.aggregation.candles,
        ledger=ledger,
        minimum_closed_candles=context.minimum_closed_candles,
    )
