import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.ingestion import CandleIngestor
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.store import CandleStore, WriteDisposition


def candle(*, is_closed: bool, close: str, source_timestamp_ms: int) -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=1_710_000_000_000,
        close_time_ms=1_710_000_899_999,
        open=Decimal(100),
        high=Decimal(110),
        low=Decimal(90),
        close=Decimal(close),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=None,
        is_closed=is_closed,
        source=DataSource.WEBSOCKET,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=source_timestamp_ms + 1,
        adapter_version="test-ws/1",
    )


def test_ingestor_persists_open_to_closed_transition(tmp_path: Path) -> None:
    async def source() -> AsyncIterator[Candle]:
        yield candle(is_closed=False, close="103", source_timestamp_ms=1000)
        yield candle(is_closed=True, close="105", source_timestamp_ms=2000)

    async def run() -> list[WriteDisposition]:
        store = CandleStore(tmp_path / "runtime" / "live.sqlite3")
        ingestor = CandleIngestor(store)
        results = [result async for result in ingestor.ingest(source())]
        loaded = store.list_candles(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        assert loaded[0].is_closed is True
        assert loaded[0].close == Decimal(105)
        return [result.disposition for result in results]

    assert asyncio.run(run()) == [WriteDisposition.INSERTED, WriteDisposition.UPDATED]
