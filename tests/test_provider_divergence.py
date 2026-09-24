from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.provider_divergence import (
    ProviderDivergenceStore,
    ProviderGridState,
    build_provider_divergence_snapshot,
    candle_evidence_identity,
    read_candles_read_only,
)
from crypto_signal.data.store import CandleStore


def _candle(
    exchange: Exchange,
    open_time_ms: int,
    close: str,
    *,
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
    is_closed: bool = True,
) -> Candle:
    value = Decimal(close)
    close_time_ms = open_time_ms + 899_999
    return Candle(
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=value,
        high=value + Decimal(1),
        low=value - Decimal(1),
        close=value,
        volume=Decimal(2),
        quote_volume=Decimal(200),
        trade_count=10 if exchange is Exchange.BINANCE else None,
        is_closed=is_closed,
        source=DataSource.REST,
        source_timestamp_ms=(
            close_time_ms + 10
            if source_timestamp_ms is None
            else source_timestamp_ms
        ),
        ingested_at_ms=(
            close_time_ms + 20
            if ingested_at_ms is None
            else ingested_at_ms
        ),
        adapter_version=f"{exchange.value}-test/1",
    )


def test_provider_divergence_preserves_separate_provider_truth() -> None:
    bybit = (
        _candle(Exchange.BYBIT, 0, "100"),
        _candle(Exchange.BYBIT, 900_000, "101"),
        _candle(Exchange.BYBIT, 1_800_000, "102"),
    )
    binance = (
        _candle(Exchange.BINANCE, 0, "100.1"),
        _candle(Exchange.BINANCE, 900_000, "100.8"),
        _candle(Exchange.BINANCE, 1_800_000, "102.2"),
    )

    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=2_800_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=bybit,
        lookback_limit=96,
    )

    assert snapshot.grid_state is ProviderGridState.FULL_OVERLAP
    assert snapshot.overlap_count == 3
    assert snapshot.left_only_open_times_ms == ()
    assert snapshot.right_only_open_times_ms == ()
    assert len(snapshot.spread_points) == 3
    assert snapshot.latest_overlap_open_time_ms == 1_800_000
    assert snapshot.latest_close_spread_bps is not None
    assert snapshot.median_absolute_close_spread_bps is not None
    assert snapshot.max_absolute_close_spread_bps is not None
    assert snapshot.left_quality.exchange is Exchange.BINANCE
    assert snapshot.right_quality.exchange is Exchange.BYBIT
    assert len(snapshot.left_source_evidence_identities) == 3
    assert len(snapshot.right_source_evidence_identities) == 3
    assert snapshot.left_source_evidence_identities[0] == candle_evidence_identity(
        binance[0]
    )
    assert snapshot.right_source_evidence_identities[0] == candle_evidence_identity(
        bybit[0]
    )
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0

    replay = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=2_800_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=bybit,
        lookback_limit=96,
    )
    assert replay == snapshot


def test_provider_divergence_reports_partial_grid_and_quality() -> None:
    bybit = (
        _candle(Exchange.BYBIT, 0, "100"),
        _candle(Exchange.BYBIT, 1_800_000, "102"),
    )
    binance = (
        _candle(Exchange.BINANCE, 900_000, "101"),
        _candle(Exchange.BINANCE, 1_800_000, "102.1"),
    )

    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=2_800_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=bybit,
    )

    assert snapshot.grid_state is ProviderGridState.PARTIAL_OVERLAP
    assert snapshot.overlap_count == 1
    assert snapshot.left_only_open_times_ms == (900_000,)
    assert snapshot.right_only_open_times_ms == (0,)
    assert snapshot.right_quality.gap_count == 1
    assert snapshot.right_quality.gap_missing_candles == 1


def test_provider_divergence_missing_provider_fails_closed_without_consensus() -> None:
    binance = (_candle(Exchange.BINANCE, 0, "100"),)

    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=1_000_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=binance,
        right_candles=(),
    )

    assert snapshot.grid_state is ProviderGridState.NO_OVERLAP
    assert snapshot.overlap_count == 0
    assert snapshot.right_quality.available is False
    assert snapshot.right_quality.stale is True
    assert snapshot.right_quality.freshness_reasons == ("no_candles",)
    assert snapshot.latest_close_spread_bps is None
    assert snapshot.median_absolute_close_spread_bps is None
    assert snapshot.max_absolute_close_spread_bps is None


def test_provider_divergence_excludes_future_late_and_open_candles() -> None:
    base = _candle(Exchange.BINANCE, 0, "100")
    future_source = replace(
        _candle(Exchange.BINANCE, 900_000, "101"),
        source_timestamp_ms=9_000_000,
    )
    late_ingest = replace(
        _candle(Exchange.BINANCE, 1_800_000, "102"),
        ingested_at_ms=9_000_000,
    )
    open_candle = _candle(
        Exchange.BINANCE,
        2_700_000,
        "103",
        is_closed=False,
    )

    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=3_700_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=(base, future_source, late_ingest, open_candle),
        right_candles=(),
    )

    assert snapshot.left_quality.consumed_closed_candles == 1
    assert snapshot.left_source_evidence_identities == (
        candle_evidence_identity(base),
    )


def test_provider_divergence_store_is_append_only_and_replay_safe(
    tmp_path,
) -> None:
    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=1_000_000,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=(_candle(Exchange.BINANCE, 0, "100"),),
        right_candles=(_candle(Exchange.BYBIT, 0, "100.1"),),
    )
    store = ProviderDivergenceStore(tmp_path / "provider-divergence.sqlite3")

    store.append(snapshot)
    store.append(snapshot)

    assert store.count() == 1
    assert store.latest(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    ) == snapshot
    assert store.quick_check() is True

    with sqlite3.connect(store.path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "UPDATE provider_divergence_snapshots "
                "SET symbol='ETHUSDT'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM provider_divergence_snapshots")


def test_read_candles_read_only_preserves_source_database_bytes(tmp_path) -> None:
    path = tmp_path / "candles.sqlite3"
    writable = CandleStore(path)
    candle = _candle(Exchange.BINANCE, 0, "100")
    writable.upsert(candle)
    before = path.read_bytes()

    rows = read_candles_read_only(
        path,
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
    )

    assert rows == (candle,)
    assert path.read_bytes() == before


def test_read_candles_read_only_missing_source_creates_nothing(tmp_path) -> None:
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(ValueError, match="missing"):
        read_candles_read_only(
            path,
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
        )

    assert not path.exists()
