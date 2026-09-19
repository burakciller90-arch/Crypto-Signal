from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.binance_ws import BinanceSpotKlineStream
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.reconciliation import reconcile_candle_grids
from crypto_signal.data.store import CandleStore, WriteDisposition

DB = Path("runtime/phase1-slice5-binance-smoke.sqlite3")


def cleanup() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DB}{suffix}").unlink(missing_ok=True)


async def verify_rest_and_grid() -> None:
    binance, bybit = BinanceSpotAdapter(), BybitSpotAdapter()
    binance_candles, bybit_candles = await asyncio.gather(
        binance.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=20),
        bybit.fetch_candles(symbol="BTCUSDT", timeframe="15m", limit=20),
    )
    assert len(binance_candles) == 20
    assert len(bybit_candles) == 20
    assert all(c.close_time_ms == c.open_time_ms + 899_999 for c in binance_candles)

    result = reconcile_candle_grids(bybit_candles, binance_candles)
    assert result.overlap_count >= 19
    absolute_spreads = [abs(item.spread_bps) for item in result.spreads]
    assert absolute_spreads
    assert max(absolute_spreads) < Decimal(500)

    print("grid_overlap", result.overlap_count)
    print("bybit_only", result.left_only_open_times_ms)
    print("binance_only", result.right_only_open_times_ms)
    print("close_spread_bps_median", median(absolute_spreads))
    print("close_spread_bps_max", max(absolute_spreads))

    weekly = await binance.fetch_candles(symbol="BTCUSDT", timeframe="1W", limit=4)
    for candle in weekly:
        opened = datetime.fromtimestamp(candle.open_time_ms / 1000, tz=UTC)
        assert opened.weekday() == 0
        assert opened.hour == 0 and opened.minute == 0
    print("binance_weekly_alignment", [c.open_time_ms for c in weekly])
async def verify_ws() -> None:
    cleanup()
    stream = BinanceSpotKlineStream().stream_candles(symbol="BTCUSDT", timeframe="15m")
    try:
        async with asyncio.timeout(30):
            first = await anext(stream)
        async with asyncio.timeout(30):
            second = await anext(stream)

        assert second.source_timestamp_ms >= first.source_timestamp_ms
        store = CandleStore(DB)
        first_result = store.upsert(first)
        second_result = store.upsert(second)

        assert first_result is WriteDisposition.INSERTED
        assert second_result in {
            WriteDisposition.UPDATED,
            WriteDisposition.UNCHANGED,
            WriteDisposition.INSERTED,
        }
        assert store.count() in {1, 2}

        print("ws_first", first.identity, first.is_closed, first_result.value)
        print("ws_second", second.identity, second.is_closed, second_result.value)
        print("ws_rows", store.count())
    finally:
        await stream.aclose()
        cleanup()


async def main() -> None:
    await verify_rest_and_grid()
    await verify_ws()


if __name__ == "__main__":
    asyncio.run(main())
