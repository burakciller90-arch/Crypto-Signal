from __future__ import annotations

import asyncio
from pathlib import Path

from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.health import assess_freshness, detect_gaps
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.store import CandleStore, WriteDisposition

DB = Path("runtime/phase1-slice2-smoke.sqlite3")


def cleanup() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DB}{suffix}").unlink(missing_ok=True)


async def main() -> None:
    cleanup()
    try:
        candles = await BybitSpotAdapter().fetch_candles(
            symbol="BTCUSDT",
            timeframe="15m",
            limit=10,
        )
        store = CandleStore(DB)
        first = [store.upsert(candle) for candle in candles]
        second = [store.upsert(candle) for candle in candles]

        loaded = store.list_candles(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        gaps = detect_gaps(loaded, "15m")
        now_ms = max(candle.source_timestamp_ms for candle in candles)
        freshness = assess_freshness(loaded, timeframe="15m", now_ms=now_ms)

        assert len(loaded) == 10
        assert store.count() == 10
        assert first.count(WriteDisposition.INSERTED) == 10
        for candle, disposition in zip(candles, second):
            if candle.is_closed:
                assert disposition is WriteDisposition.UNCHANGED
        assert gaps == ()
        assert freshness.stale is False

        print("rows", store.count())
        print("first", [item.value for item in first])
        print("second", [item.value for item in second])
        print("gaps", gaps)
        print("freshness", freshness)
    finally:
        cleanup()


if __name__ == "__main__":
    asyncio.run(main())
