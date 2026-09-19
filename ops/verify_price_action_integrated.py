from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, time

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.methodologies.price_action.levels import SessionSpec
from crypto_signal.methodologies.price_action.models import StructureDirection

BASE_MS = 900_000


async def fetch_range(
    adapter: MarketDataAdapter,
    *,
    start_ms: int,
    end_exclusive_ms: int,
) -> tuple[Candle, ...]:
    output: list[Candle] = []
    current = start_ms
    while current < end_exclusive_ms:
        remaining = (end_exclusive_ms - current) // BASE_MS
        limit = min(1000, remaining)
        page_end = current + limit * BASE_MS - 1
        page = await adapter.fetch_candles(
            symbol="BTCUSDT",
            timeframe="15m",
            limit=limit,
            start_ms=current,
            end_ms=page_end,
        )
        output.extend(page)
        current += limit * BASE_MS

    output.sort(key=lambda candle: candle.open_time_ms)
    assert output
    assert len({candle.open_time_ms for candle in output}) == len(output)
    assert detect_gaps(output, "15m") == ()
    assert all(candle.is_closed for candle in output)
    return tuple(output)


async def verify_provider(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
) -> None:
    wall_now = datetime.now(UTC)
    current_open = wall_now.replace(
        minute=(wall_now.minute // 15) * 15,
        second=0,
        microsecond=0,
    )
    end_exclusive_ms = int(current_open.timestamp() * 1000)
    start_ms = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp() * 1000)

    candles = await fetch_range(
        adapter,
        start_ms=start_ms,
        end_exclusive_ms=end_exclusive_ms,
    )
    as_of_ms = max(
        int(datetime.now(UTC).timestamp() * 1000),
        max(candle.ingested_at_ms for candle in candles),
    )
    session = SessionSpec(
        name="verification_istanbul_09_11",
        timezone="Europe/Istanbul",
        start_local=time(9, 0),
        end_local=time(11, 0),
    )

    result = analyze_price_action(
        candles,
        sessions=(session,),
        as_of_ms=as_of_ms,
    )
    repeat = analyze_price_action(
        candles,
        sessions=(session,),
        as_of_ms=as_of_ms,
    )
    assert result == repeat

    nested_as_of = {
        result.structure.as_of_ms,
        result.imbalances.as_of_ms,
        result.liquidity.as_of_ms,
        result.levels.as_of_ms,
        result.displacement.as_of_ms,
        result.level_interactions.as_of_ms,
    }
    assert nested_as_of == {as_of_ms}
    assert result.as_of_ms == as_of_ms

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

    assert summary.structure_break_count > 20
    assert summary.fair_value_gap_count > 50
    assert summary.liquidity_pool_count > 10
    assert summary.displacement_count > 20
    assert summary.reference_level_count >= 8
    assert summary.level_interaction_count > 20
    assert summary.current_structure_direction is not StructureDirection.UNKNOWN
    level_labels = {level.label for level in result.reference_levels}
    assert "previous_day:high" in level_labels
    assert "previous_day:low" in level_labels
    assert "previous_week:high" in level_labels
    assert "previous_week:low" in level_labels
    assert "previous_month:high" in level_labels
    assert "previous_month:low" in level_labels
    assert "daily_open" in level_labels

    interaction_kinds = Counter(
        event.kind.value for event in result.level_interactions.events
    )
    liquidity_statuses = Counter(
        pool.status.value for pool in result.liquidity.pools
    )
    fvg_statuses = Counter(
        fvg.status.value for fvg in result.imbalances.fair_value_gaps
    )

    print(
        name,
        f"candles={len(candles)}",
        f"direction={summary.current_structure_direction.value}",
        f"breaks={summary.structure_break_count}",
        f"fvgs={summary.fair_value_gap_count}",
        f"bprs={summary.balanced_price_range_count}",
        f"liquidity_pools={summary.liquidity_pool_count}",
        f"sfp={summary.sfp_rejection_count}",
        f"displacements={summary.displacement_count}",
        f"levels={summary.reference_level_count}",
        f"interactions={summary.level_interaction_count}",
    )
    print(name, "fvg_statuses", dict(fvg_statuses))
    print(name, "liquidity_statuses", dict(liquidity_statuses))
    print(name, "interaction_kinds", dict(interaction_kinds))
    print(name, "level_labels", sorted(level_labels))


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
