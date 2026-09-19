from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.store import CandleConflictError, CandleStore, WriteDisposition


def candle(
    *,
    open_time_ms: int = 1_710_000_000_000,
    close: str = "105",
    high: str = "110",
    is_closed: bool = False,
    source_timestamp_ms: int = 1_710_000_100_000,
) -> Candle:
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(100),
        high=Decimal(high),
        low=Decimal(90),
        close=Decimal(close),
        volume=Decimal("12.5"),
        quote_volume=Decimal(1250),
        trade_count=None,
        is_closed=is_closed,
        source=DataSource.REST,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=source_timestamp_ms + 1,
        adapter_version="test/1",
    )


def store(tmp_path: Path) -> CandleStore:
    return CandleStore(tmp_path / "runtime" / "test.sqlite3")
def test_insert_and_read_preserve_decimal_truth(tmp_path: Path) -> None:
    db = store(tmp_path)
    item = candle(is_closed=True)

    assert db.upsert(item) is WriteDisposition.INSERTED
    loaded = db.list_candles(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )

    assert loaded == (item,)
    assert db.count() == 1


def test_duplicate_delivery_is_idempotent(tmp_path: Path) -> None:
    db = store(tmp_path)
    item = candle(is_closed=True)
    duplicate = candle(is_closed=True, source_timestamp_ms=item.source_timestamp_ms + 5_000)

    assert db.upsert(item) is WriteDisposition.INSERTED
    assert db.upsert(duplicate) is WriteDisposition.UNCHANGED
    assert db.count() == 1


def test_newer_open_update_wins_and_stale_update_is_ignored(tmp_path: Path) -> None:
    db = store(tmp_path)
    first = candle(close="101", source_timestamp_ms=1000)
    newer = candle(close="103", source_timestamp_ms=3000)
    stale = candle(close="99", source_timestamp_ms=2000)

    assert db.upsert(first) is WriteDisposition.INSERTED
    assert db.upsert(newer) is WriteDisposition.UPDATED
    assert db.upsert(stale) is WriteDisposition.IGNORED_STALE
    loaded = db.list_candles(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )
    assert loaded[0].close == Decimal(103)


def test_open_candle_can_finalize(tmp_path: Path) -> None:
    db = store(tmp_path)
    assert db.upsert(candle(close="101", source_timestamp_ms=1000)) is WriteDisposition.INSERTED
    result = db.upsert(candle(close="104", is_closed=True, source_timestamp_ms=2000))

    assert result is WriteDisposition.UPDATED
    loaded = db.list_candles(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )
    assert loaded[0].is_closed is True
    assert loaded[0].close == Decimal(104)


def test_finalized_candle_cannot_reopen_or_silently_change(tmp_path: Path) -> None:
    db = store(tmp_path)
    finalized = candle(close="104", is_closed=True, source_timestamp_ms=2000)
    assert db.upsert(finalized) is WriteDisposition.INSERTED

    reopened = candle(close="105", is_closed=False, source_timestamp_ms=3000)
    assert db.upsert(reopened) is WriteDisposition.IGNORED_FINALIZED

    conflicting = candle(close="106", high="112", is_closed=True, source_timestamp_ms=4000)
    with pytest.raises(CandleConflictError, match="finalized candle conflict"):
        db.upsert(conflicting)
