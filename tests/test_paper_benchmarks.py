from __future__ import annotations

import hashlib
import sqlite3
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.data.store import CandleStore
from crypto_signal.paper.benchmarks import (
    PAPER_BENCHMARK_VERSION,
    PaperBenchmarkAvailability,
    PaperBenchmarkKind,
    compare_paper_return_to_benchmarks,
    read_paper_benchmark_snapshot,
)
from crypto_signal.paper.models import PaperSymbol


def _candle(
    *,
    symbol: str,
    open_time_ms: int,
    close: str,
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
) -> Candle:
    close_time_ms = open_time_ms + 899_999
    source_ms = close_time_ms if source_timestamp_ms is None else source_timestamp_ms
    ingested_ms = source_ms if ingested_at_ms is None else ingested_at_ms
    return Candle(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal(1),
        quote_volume=Decimal(close),
        trade_count=1,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingested_ms,
        adapter_version="benchmark-test/1",
    )


def _seed_complete_cache(path: Path) -> None:
    store = CandleStore(path)
    start_open = 900_000
    end_open = 2_700_000
    for symbol, start_price, end_price in (
        ("BTCUSDT", "100", "110"),
        ("ETHUSDT", "50", "40"),
        ("SOLUSDT", "20", "30"),
    ):
        store.upsert(
            _candle(
                symbol=symbol,
                open_time_ms=start_open,
                close=start_price,
            )
        )
        store.upsert(
            _candle(
                symbol=symbol,
                open_time_ms=end_open,
                close=end_price,
            )
        )


def test_benchmarks_share_activation_start_and_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "candles.sqlite3"
    _seed_complete_cache(path)

    first = read_paper_benchmark_snapshot(
        candle_cache_path=path,
        start_at_ms=1_800_000,
        observed_at_ms=3_600_000,
    )
    second = read_paper_benchmark_snapshot(
        candle_cache_path=path,
        start_at_ms=1_800_000,
        observed_at_ms=3_600_000,
    )

    assert first == second
    assert first.snapshot_identity == second.snapshot_identity
    assert first.version == PAPER_BENCHMARK_VERSION
    assert first.real_capital == 0
    assert [item.kind for item in first.results] == [
        PaperBenchmarkKind.CASH,
        PaperBenchmarkKind.BTC_BUY_HOLD,
        PaperBenchmarkKind.BTC_ETH_SOL_EQUAL_WEIGHT,
    ]

    cash, btc, equal = first.results
    assert cash.total_return_fraction == Decimal(0)
    assert cash.nav_usdt == Decimal("100.00")

    assert btc.availability is PaperBenchmarkAvailability.AVAILABLE
    assert btc.nav_usdt == Decimal("110.00")
    assert btc.total_return_fraction == Decimal("0.10")
    assert btc.positions[0].symbol is PaperSymbol.BTCUSDT

    assert equal.availability is PaperBenchmarkAvailability.AVAILABLE
    expected_nav = sum(
        (item.ending_value_usdt for item in equal.positions),
        start=Decimal(0),
    )
    assert equal.nav_usdt == expected_nav
    assert equal.total_return_fraction == (
        expected_nav - Decimal("100.00")
    ) / Decimal("100.00")
    assert sum(
        (item.allocation_usdt for item in equal.positions),
        start=Decimal(0),
    ) == Decimal("100.00")


def test_benchmark_marks_are_point_in_time_safe(tmp_path: Path) -> None:
    path = tmp_path / "candles.sqlite3"
    _seed_complete_cache(path)
    store = CandleStore(path)
    store.upsert(
        _candle(
            symbol="BTCUSDT",
            open_time_ms=1_800_000,
            close="999",
            source_timestamp_ms=3_700_000,
            ingested_at_ms=3_700_000,
        )
    )

    snapshot = read_paper_benchmark_snapshot(
        candle_cache_path=path,
        start_at_ms=1_800_000,
        observed_at_ms=3_600_000,
    )

    btc = snapshot.results[1]
    assert btc.positions[0].start_mark.price == Decimal(100)
    assert btc.positions[0].end_mark.price == Decimal(110)
    assert btc.positions[0].end_mark.ingested_at_ms <= 3_600_000


def test_missing_benchmark_mark_fails_closed_without_fabricated_return(
    tmp_path: Path,
) -> None:
    path = tmp_path / "candles.sqlite3"
    store = CandleStore(path)
    for symbol in ("BTCUSDT", "ETHUSDT"):
        store.upsert(
            _candle(
                symbol=symbol,
                open_time_ms=900_000,
                close="100",
            )
        )
        store.upsert(
            _candle(
                symbol=symbol,
                open_time_ms=2_700_000,
                close="110",
            )
        )

    snapshot = read_paper_benchmark_snapshot(
        candle_cache_path=path,
        start_at_ms=1_800_000,
        observed_at_ms=3_600_000,
    )

    cash, btc, equal = snapshot.results
    assert cash.availability is PaperBenchmarkAvailability.AVAILABLE
    assert btc.availability is PaperBenchmarkAvailability.AVAILABLE
    assert equal.availability is PaperBenchmarkAvailability.MISSING_MARKS
    assert equal.missing_start_symbols == (PaperSymbol.SOLUSDT,)
    assert equal.missing_end_symbols == (PaperSymbol.SOLUSDT,)
    assert equal.nav_usdt is None
    assert equal.total_return_fraction is None
    assert equal.positions == ()


def _logical_candle_cache_snapshot(path: Path) -> tuple[object, ...]:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        schema = tuple(
            connection.execute(
                """
                SELECT type, name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
        )
        rows = tuple(
            connection.execute(
                """
                SELECT *
                FROM candles
                ORDER BY exchange, market_type, symbol, timeframe, open_time_ms
                """
            ).fetchall()
        )
    return schema, rows


def test_benchmark_reader_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "candles.sqlite3"
    _seed_complete_cache(path)
    before = _logical_candle_cache_snapshot(path)

    read_paper_benchmark_snapshot(
        candle_cache_path=path,
        start_at_ms=1_800_000,
        observed_at_ms=3_600_000,
    )

    after = _logical_candle_cache_snapshot(path)
    assert after == before

def test_benchmark_relative_return_is_backend_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "candles.sqlite3"
    _seed_complete_cache(path)
    snapshot = read_paper_benchmark_snapshot(
        candle_cache_path=path,
        start_at_ms=1_800_000,
        observed_at_ms=3_600_000,
    )

    comparisons = compare_paper_return_to_benchmarks(
        snapshot,
        paper_total_return_fraction=Decimal("0.05"),
    )

    cash, btc, equal = comparisons
    assert cash.relative_return_fraction == Decimal("0.05")
    assert btc.benchmark_total_return_fraction == Decimal("0.10")
    assert btc.relative_return_fraction == Decimal("-0.05")
    assert equal.relative_return_fraction == (
        Decimal("0.05") - snapshot.results[2].total_return_fraction
    )

    unavailable = compare_paper_return_to_benchmarks(
        snapshot,
        paper_total_return_fraction=None,
    )
    assert all(item.relative_return_fraction is None for item in unavailable)

