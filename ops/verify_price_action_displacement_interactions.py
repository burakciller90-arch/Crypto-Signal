from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, time

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.models import Candle
from crypto_signal.data.periodic_opens import Period, resolve_periodic_open
from crypto_signal.methodologies.price_action.displacement import analyze_displacement
from crypto_signal.methodologies.price_action.interactions import (
    analyze_level_interactions,
    reference_level_from_periodic_open,
    reference_levels_from_range,
)
from crypto_signal.methodologies.price_action.levels import (
    SessionSpec,
    analyze_period_session_levels,
)

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
    assert len({candle.open_time_ms for candle in output}) == len(output)
    assert detect_gaps(output, "15m") == ()
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

    displacement_source = candles[-900:]
    displacement = analyze_displacement(displacement_source, as_of_ms=as_of_ms)
    displacement_repeat = analyze_displacement(
        displacement_source,
        as_of_ms=as_of_ms,
    )
    assert displacement == displacement_repeat
    assert len(displacement.events) > 5
    assert all(
        event.market_confirmed_at_ms <= event.observed_at_ms
        for event in displacement.events
    )

    session = SessionSpec(
        name="verification_istanbul_09_11",
        timezone="Europe/Istanbul",
        start_local=time(9, 0),
        end_local=time(11, 0),
    )
    level_ranges = analyze_period_session_levels(
        candles,
        sessions=(session,),
        as_of_ms=as_of_ms,
    )

    levels = []
    for _, evidence in level_ranges.previous_periods:
        levels.extend(reference_levels_from_range(evidence))
    for evidence in level_ranges.sessions:
        levels.extend(reference_levels_from_range(evidence))
    for period in Period:
        value = resolve_periodic_open(
            candles,
            period=period,
            as_of_ms=as_of_ms,
        )
        if value is not None:
            levels.append(reference_level_from_periodic_open(value))

    assert len(levels) >= 8

    interactions = analyze_level_interactions(
        candles,
        levels,
        as_of_ms=as_of_ms,
    )
    interactions_repeat = analyze_level_interactions(
        candles,
        levels,
        as_of_ms=as_of_ms,
    )
    assert interactions == interactions_repeat
    assert len(interactions.events) > 0
    assert all(
        event.market_confirmed_at_ms > event.level.available_at_market_ms
        for event in interactions.events
    )
    assert all(
        event.observed_at_ms >= event.level.observed_at_ms
        for event in interactions.events
    )

    displacement_directions = Counter(
        event.direction.value for event in displacement.events
    )
    interaction_kinds = Counter(
        event.kind.value for event in interactions.events
    )
    interactions_by_level = Counter(
        event.level.label for event in interactions.events
    )

    print(
        name,
        f"candles={len(candles)}",
        f"displacements={len(displacement.events)}",
        f"levels={len(levels)}",
        f"interactions={len(interactions.events)}",
    )
    print(name, "displacement_directions", dict(displacement_directions))
    print(name, "interaction_kinds", dict(interaction_kinds))
    print(name, "interactions_by_level", dict(interactions_by_level))


    for event in displacement.events[-5:]:
        print(
            name,
            "DISPLACEMENT",
            event.direction.value,
            f"body_fraction={event.body_fraction}",
            f"body_x={event.observed_body_multiple}",
            f"range_x={event.observed_range_multiple}",
        )
    for event in interactions.events[-5:]:
        print(
            name,
            "INTERACTION",
            event.level.label,
            event.kind.value,
            f"close_offset_bps={event.close_offset_bps}",
        )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
