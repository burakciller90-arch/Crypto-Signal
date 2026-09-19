from __future__ import annotations

import asyncio
from pathlib import Path

from crypto_signal.data.adapters.bybit_ws import BybitSpotKlineStream
from crypto_signal.data.models import DataSource
from crypto_signal.data.store import CandleStore, WriteDisposition

DB = Path("runtime/phase1-slice3-ws-smoke.sqlite3")


def cleanup() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DB}{suffix}").unlink(missing_ok=True)


async def main() -> None:
    cleanup()
    stream = BybitSpotKlineStream().stream_candles(symbol="BTCUSDT", timeframe="15m")
    try:
        async with asyncio.timeout(30):
            first = await anext(stream)
        async with asyncio.timeout(30):
            second = await anext(stream)

        assert first.source is DataSource.WEBSOCKET
        assert second.source is DataSource.WEBSOCKET
        assert second.source_timestamp_ms >= first.source_timestamp_ms

        store = CandleStore(DB)
        first_result = store.upsert(first)
        second_result = store.upsert(second)

        assert first_result is WriteDisposition.INSERTED
        assert second_result in {
            WriteDisposition.INSERTED,
            WriteDisposition.UPDATED,
            WriteDisposition.UNCHANGED,
        }
        assert store.count() in {1, 2}

        print("first_identity", first.identity)
        print("first_closed", first.is_closed)
        print("first_result", first_result.value)
        print("second_identity", second.identity)
        print("second_closed", second.is_closed)
        print("second_result", second_result.value)
        print("rows", store.count())
    finally:
        await stream.aclose()
        cleanup()


if __name__ == "__main__":
    asyncio.run(main())
