from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise

from crypto_signal.data.adapters.bybit import BybitSpotAdapter


async def main() -> None:
    candles = await BybitSpotAdapter().fetch_candles(
        symbol="BTCUSDT",
        timeframe="15m",
        limit=5,
    )
    assert len(candles) == 5
    assert len({c.identity for c in candles}) == 5
    assert all(isinstance(c.open, Decimal) for c in candles)
    deltas = [b.open_time_ms - a.open_time_ms for a, b in pairwise(candles)]
    assert deltas == [900_000] * 4
    assert any(c.is_closed for c in candles)

    for candle in candles:
        opened = datetime.fromtimestamp(candle.open_time_ms / 1000, tz=UTC).isoformat()
        print(
            candle.symbol,
            candle.timeframe,
            opened,
            f"O={candle.open}",
            f"H={candle.high}",
            f"L={candle.low}",
            f"C={candle.close}",
            f"closed={candle.is_closed}",
        )


if __name__ == "__main__":
    asyncio.run(main())
