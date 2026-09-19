from __future__ import annotations

import asyncio
from collections import Counter

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.periodic_opens import Period
from crypto_signal.methodologies.price_action.models import StructureDirection
from crypto_signal.methodologies.price_action.structure import analyze_structure


async def verify_provider(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
) -> None:
    recent = await adapter.fetch_candles(
        symbol="BTCUSDT",
        timeframe="15m",
        limit=702,
    )
    closed = [candle for candle in recent if candle.is_closed][-700:]
    assert len(closed) == 700
    assert detect_gaps(closed, "15m") == ()

    result = analyze_structure(closed, left_bars=2, right_bars=2)
    assert len(result.confirmed_pivots) > 50
    assert len(result.labeled_swings) > 30
    assert len(result.structure_breaks) > 3
    assert result.current_direction is not StructureDirection.UNKNOWN
    assert all(
        event.broken_pivot.market_confirmed_at_ms <= event.market_confirmed_at_ms
        for event in result.structure_breaks
    )
    assert all(
        event.market_confirmed_at_ms <= event.observed_at_ms
        for event in result.structure_breaks
    )
    broken_keys = [
        (event.broken_pivot.kind, event.broken_pivot.source_candle_identity)
        for event in result.structure_breaks
    ]
    assert len(broken_keys) == len(set(broken_keys))

    relation_counts = Counter(item.relation.value for item in result.labeled_swings)
    break_counts = Counter(event.kind.value for event in result.structure_breaks)
    periodic = {item.period: item.price for item in result.periodic_opens}
    assert Period.DAILY in periodic

    print(
        name,
        f"pivots={len(result.confirmed_pivots)}",
        f"swings={len(result.labeled_swings)}",
        f"breaks={len(result.structure_breaks)}",
        f"direction={result.current_direction.value}",
        f"ambiguous={len(result.ambiguous_swing_source_indices)}",
    )
    print(name, "relations", dict(relation_counts))
    print(name, "break_kinds", dict(break_counts))
    print(name, "periodic", {key.value: str(value) for key, value in periodic.items()})
    for event in result.structure_breaks[-5:]:
        print(
            name,
            event.kind.value,
            event.direction.value,
            "level",
            event.level_price,
            "close",
            event.break_close,
            "distance_bps",
            event.distance_bps,
        )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
