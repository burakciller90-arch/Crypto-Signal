from __future__ import annotations

import asyncio
from itertools import pairwise

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import detect_gaps
from crypto_signal.primitives.models import PivotKind
from crypto_signal.primitives.swings import (
    compress_alternating_pivots,
    detect_fractal_pivots,
)


async def verify_provider(name: str, adapter: BybitSpotAdapter | BinanceSpotAdapter) -> None:
    recent = await adapter.fetch_candles(
        symbol="BTCUSDT",
        timeframe="15m",
        limit=202,
    )
    closed = [candle for candle in recent if candle.is_closed][-200:]
    assert len(closed) == 200
    assert detect_gaps(closed, "15m") == ()

    pivots = detect_fractal_pivots(closed, left_bars=2, right_bars=2)
    repeat = detect_fractal_pivots(closed, left_bars=2, right_bars=2)
    assert pivots == repeat
    assert len(pivots) > 10
    assert all(pivot.market_confirmed_at_ms <= pivot.observed_at_ms for pivot in pivots)
    result = compress_alternating_pivots(pivots)
    assert len(result.swings) > 5
    assert all(left.kind is not right.kind for left, right in pairwise(result.swings))

    highs = sum(pivot.kind is PivotKind.HIGH for pivot in pivots)
    lows = sum(pivot.kind is PivotKind.LOW for pivot in pivots)
    print(
        name,
        "closed=200",
        f"pivots={len(pivots)}",
        f"highs={highs}",
        f"lows={lows}",
        f"alternating={len(result.swings)}",
        f"ambiguous={len(result.ambiguous_source_indices)}",
    )
    for pivot in result.swings[-5:]:
        print(
            name,
            pivot.kind.value,
            pivot.open_time_ms,
            pivot.price,
            "market_confirmed",
            pivot.market_confirmed_at_ms,
            "observed",
            pivot.observed_at_ms,
        )


async def main() -> None:
    await verify_provider("bybit", BybitSpotAdapter())
    await verify_provider("binance", BinanceSpotAdapter())


if __name__ == "__main__":
    asyncio.run(main())
