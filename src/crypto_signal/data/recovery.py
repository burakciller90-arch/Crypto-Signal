from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import cast

from crypto_signal.data.adapters.base import (
    MarketDataAdapter,
    SourceAwareMarketDataAdapter,
)
from crypto_signal.data.candle_source_contract import (
    persist_candle_source_snapshot,
)
from crypto_signal.data.models import Candle
from crypto_signal.data.source_contract import SourceContractStore
from crypto_signal.data.store import CandleStore, WriteDisposition
from crypto_signal.data.timeframes import is_aligned_open, spec


@dataclass(frozen=True, slots=True)
class BackfillReport:
    symbol: str
    timeframe: str
    start_open_ms: int
    end_open_ms: int
    expected_count: int
    received_count: int
    missing_open_times_ms: tuple[int, ...]
    dispositions: tuple[tuple[WriteDisposition, int], ...]

    @property
    def complete(self) -> bool:
        return not self.missing_open_times_ms and self.received_count == self.expected_count

    def count(self, disposition: WriteDisposition) -> int:
        return dict(self.dispositions).get(disposition, 0)


async def backfill_range(
    adapter: MarketDataAdapter,
    store: CandleStore,
    *,
    symbol: str,
    timeframe: str,
    start_open_ms: int,
    end_open_ms: int,
    page_limit: int = 1000,
    require_closed: bool = True,
    source_store: SourceContractStore | None = None,
) -> BackfillReport:
    tf = spec(timeframe)
    duration_ms = tf.duration_ms
    if start_open_ms < 0 or end_open_ms < start_open_ms:
        raise ValueError("invalid backfill range")
    if not is_aligned_open(start_open_ms, timeframe) or not is_aligned_open(
        end_open_ms, timeframe
    ):
        raise ValueError("backfill range must align to the timeframe grid")
    if not 1 <= page_limit <= 1000:
        raise ValueError("page_limit must be between 1 and 1000")

    expected_opens = tuple(
        range(start_open_ms, end_open_ms + duration_ms, duration_ms)
    )
    collected: dict[int, Candle] = {}
    counts: Counter[WriteDisposition] = Counter()

    current_open_ms = start_open_ms
    while current_open_ms <= end_open_ms:
        remaining = ((end_open_ms - current_open_ms) // duration_ms) + 1
        limit = min(page_limit, remaining)
        page_last_open_ms = current_open_ms + (limit - 1) * duration_ms
        page_end_ms = page_last_open_ms + duration_ms - 1

        source_snapshot = None
        if source_store is not None:
            if not hasattr(adapter, "fetch_source_candles"):
                raise TypeError(
                    "source-aware backfill requires source-aware adapter"
                )
            source_snapshot = await cast(
                SourceAwareMarketDataAdapter,
                adapter,
            ).fetch_source_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                start_ms=current_open_ms,
                end_ms=page_end_ms,
            )
            page = source_snapshot.candles
        else:
            page = await adapter.fetch_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                start_ms=current_open_ms,
                end_ms=page_end_ms,
            )
        for candle in page:
            if candle.symbol != symbol or candle.timeframe != timeframe:
                raise ValueError("adapter returned mismatched candle semantics")
            if not current_open_ms <= candle.open_time_ms <= page_last_open_ms:
                raise ValueError("adapter returned candle outside requested page")
            if not is_aligned_open(candle.open_time_ms, timeframe):
                raise ValueError("adapter returned off-grid candle")
            if require_closed and not candle.is_closed:
                raise ValueError("historical recovery received an open candle")

            existing = collected.get(candle.open_time_ms)
            if existing is not None and existing != candle:
                raise ValueError("adapter returned conflicting duplicate candle")
            collected[candle.open_time_ms] = candle

        if source_snapshot is not None:
            assert source_store is not None
            persistence = persist_candle_source_snapshot(
                candle_store=store,
                source_store=source_store,
                snapshot=source_snapshot,
            )
            for disposition, count in persistence.dispositions:
                counts[disposition] += count

        current_open_ms = page_last_open_ms + duration_ms

    missing = tuple(open_ms for open_ms in expected_opens if open_ms not in collected)
    if source_store is None:
        for open_ms in sorted(collected):
            counts[store.upsert(collected[open_ms])] += 1

    dispositions = tuple(sorted(counts.items(), key=lambda item: item[0].value))
    return BackfillReport(
        symbol=symbol,
        timeframe=timeframe,
        start_open_ms=start_open_ms,
        end_open_ms=end_open_ms,
        expected_count=len(expected_opens),
        received_count=len(collected),
        missing_open_times_ms=missing,
        dispositions=dispositions,
    )
