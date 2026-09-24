from __future__ import annotations
from pathlib import Path

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.provider_divergence import ProviderDivergenceStore
from crypto_signal.data.store import CandleStore
from ops.run_provider_divergence import collect_provider_divergence

from decimal import Decimal


def _seed(
    store: CandleStore,
    *,
    exchange: Exchange,
    symbol: str,
    open_time_ms: int,
    close: str,
) -> None:
    value = Decimal(close)
    close_time_ms = open_time_ms + 899_999
    store.upsert(
        Candle(
            exchange=exchange,
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe="15m",
            open_time_ms=open_time_ms,
            close_time_ms=close_time_ms,
            open=value,
            high=value + Decimal(1),
            low=value - Decimal(1),
            close=value,
            volume=Decimal(1),
            quote_volume=Decimal(100),
            trade_count=1 if exchange is Exchange.BINANCE else None,
            is_closed=True,
            source=DataSource.REST,
            source_timestamp_ms=close_time_ms + 10,
            ingested_at_ms=close_time_ms + 20,
            adapter_version=f"{exchange.value}-test/1",
        )
    )


def test_provider_divergence_cycle_reads_source_and_persists_separate_evidence(
    tmp_path: Path,
) -> None:
    candle_db = tmp_path / "candles.sqlite3"
    divergence_db = tmp_path / "provider-divergence.sqlite3"
    store = CandleStore(candle_db)

    for symbol in ("BTCUSDT", "ETHUSDT"):
        _seed(
            store,
            exchange=Exchange.BINANCE,
            symbol=symbol,
            open_time_ms=0,
            close="100",
        )
        _seed(
            store,
            exchange=Exchange.BYBIT,
            symbol=symbol,
            open_time_ms=0,
            close="100.1",
        )

    source_before = candle_db.read_bytes()
    result = collect_provider_divergence(
        candle_db=candle_db,
        divergence_db=divergence_db,
        symbols=("BTCUSDT", "ETHUSDT"),
        timeframe="15m",
        lookback=96,
        observed_at_ms=1_000_000,
    )

    assert tuple(item.symbol for item in result.snapshots) == (
        "BTCUSDT",
        "ETHUSDT",
    )
    assert all(item.overlap_count == 1 for item in result.snapshots)
    assert candle_db.read_bytes() == source_before

    evidence = ProviderDivergenceStore(divergence_db)
    assert evidence.count() == 2
    assert evidence.quick_check() is True


def test_provider_divergence_cycle_is_idempotent_at_same_observation(
    tmp_path: Path,
) -> None:
    candle_db = tmp_path / "candles.sqlite3"
    divergence_db = tmp_path / "provider-divergence.sqlite3"
    store = CandleStore(candle_db)
    _seed(
        store,
        exchange=Exchange.BINANCE,
        symbol="BTCUSDT",
        open_time_ms=0,
        close="100",
    )
    _seed(
        store,
        exchange=Exchange.BYBIT,
        symbol="BTCUSDT",
        open_time_ms=0,
        close="100.1",
    )

    kwargs = {
        "candle_db": candle_db,
        "divergence_db": divergence_db,
        "symbols": ("BTCUSDT",),
        "timeframe": "15m",
        "lookback": 96,
        "observed_at_ms": 1_000_000,
    }
    first = collect_provider_divergence(**kwargs)
    second = collect_provider_divergence(**kwargs)

    assert first == second
    assert ProviderDivergenceStore(divergence_db).count() == 1
