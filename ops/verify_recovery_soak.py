from __future__ import annotations

import asyncio
from pathlib import Path

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.binance_ws import BinanceSpotKlineStream
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.adapters.bybit_ws import BybitSpotKlineStream
from crypto_signal.data.health import detect_gaps
from crypto_signal.data.ingestion import CandleIngestor
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.recovery import backfill_range
from crypto_signal.data.store import CandleStore, WriteDisposition

RUNTIME = Path("runtime")


def cleanup(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


async def verify_recovery(
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
    exchange: Exchange,
) -> None:
    db = RUNTIME / f"phase1-slice6-{name}-recovery.sqlite3"
    cleanup(db)
    try:
        recent = await adapter.fetch_candles(
            symbol="BTCUSDT",
            timeframe="15m",
            limit=32,
        )
        closed = [candle for candle in recent if candle.is_closed][-30:]
        assert len(closed) == 30
        assert detect_gaps(closed, "15m") == ()

        store = CandleStore(db)
        omitted_index = 15
        for index, candle in enumerate(closed):
            if index != omitted_index:
                store.upsert(candle)

        before = store.list_candles(
            exchange=exchange,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        gaps_before = detect_gaps(before, "15m")
        assert len(gaps_before) == 1
        assert gaps_before[0].missing_count == 1

        first = await backfill_range(
            adapter,
            store,
            symbol="BTCUSDT",
            timeframe="15m",
            start_open_ms=closed[0].open_time_ms,
            end_open_ms=closed[-1].open_time_ms,
            page_limit=10,
        )
        assert first.complete is True
        assert first.count(WriteDisposition.INSERTED) == 1
        assert first.count(WriteDisposition.UNCHANGED) == 29

        after = store.list_candles(
            exchange=exchange,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        assert len(after) == 30
        assert detect_gaps(after, "15m") == ()

        second = await backfill_range(
            adapter,
            store,
            symbol="BTCUSDT",
            timeframe="15m",
            start_open_ms=closed[0].open_time_ms,
            end_open_ms=closed[-1].open_time_ms,
            page_limit=10,
        )
        assert second.complete is True
        assert second.count(WriteDisposition.UNCHANGED) == 30
        print(name, "recovery", "gap=1->0", "second_unchanged=30")
    finally:
        cleanup(db)
async def consume_updates(
    store: CandleStore,
    stream,
    count: int,
) -> list[WriteDisposition]:
    ingestor = CandleIngestor(store)
    results: list[WriteDisposition] = []
    async with asyncio.timeout(30):
        async for result in ingestor.ingest(stream):
            results.append(result.disposition)
            if len(results) >= count:
                break
    await stream.aclose()
    return results


async def verify_dual_feed_soak() -> None:
    db = RUNTIME / "phase1-slice6-dual-feed.sqlite3"
    cleanup(db)
    try:
        store = CandleStore(db)
        bybit_stream = BybitSpotKlineStream().stream_candles(
            symbol="BTCUSDT",
            timeframe="15m",
        )
        binance_stream = BinanceSpotKlineStream().stream_candles(
            symbol="BTCUSDT",
            timeframe="15m",
        )
        bybit_results, binance_results = await asyncio.gather(
            consume_updates(store, bybit_stream, 5),
            consume_updates(store, binance_stream, 5),
        )

        bybit_rows = store.list_candles(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        binance_rows = store.list_candles(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        assert bybit_rows
        assert binance_rows
        assert all(row.exchange is Exchange.BYBIT for row in bybit_rows)
        assert all(row.exchange is Exchange.BINANCE for row in binance_rows)

        print("dual_feed_bybit", [item.value for item in bybit_results], "rows", len(bybit_rows))
        print(
            "dual_feed_binance",
            [item.value for item in binance_results],
            "rows",
            len(binance_rows),
        )
    finally:
        cleanup(db)
async def main() -> None:
    await verify_recovery("bybit", BybitSpotAdapter(), Exchange.BYBIT)
    await verify_recovery("binance", BinanceSpotAdapter(), Exchange.BINANCE)
    await verify_dual_feed_soak()


if __name__ == "__main__":
    asyncio.run(main())
