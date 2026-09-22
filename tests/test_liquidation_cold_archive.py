from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("pyarrow")

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    build_liquidation_feed_coverage,
    build_liquidation_observation,
)
from crypto_signal.data.market_tape import (
    MarketTapeConflictError,
    MarketTapeStore,
)
from crypto_signal.data.market_tape_cold_archive import (
    COLD_ARCHIVE_SCHEMA_VERSION,
    archive_due_hot_partitions,
    cold_liquidation_replay,
    verify_cold_partition,
)
from crypto_signal.data.market_tape_hotcold import MarketTapeHotColdPolicy
from crypto_signal.data.models import DataSource, Exchange

HOUR_MS = 60 * 60 * 1000


def _policy() -> MarketTapeHotColdPolicy:
    return MarketTapeHotColdPolicy(
        hot_retention_ms=24 * HOUR_MS,
        late_arrival_grace_ms=2 * HOUR_MS,
        partition_ms=HOUR_MS,
        hot_emergency_max_bytes=25 * 1024**3,
        cold_max_bytes=600 * 1024**3,
        min_free_bytes=1,
        max_archive_partitions_per_cycle=6,
    )


def _event(
    *,
    event_at_ms: int,
    row_index: int = 0,
    side: LiquidatedPositionSide = LiquidatedPositionSide.LONG,
    size: str = "2",
    price: str = "100",
):
    return build_liquidation_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        liquidated_position_side=side,
        size=Decimal(size),
        bankruptcy_price=Decimal(price),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 10,
        ingested_at_ms=event_at_ms + 20,
        source_row_index=row_index,
        source=DataSource.WEBSOCKET,
        adapter_version="cold-liquidation-test/1",
    )


def _coverage(
    *,
    start_ms: int,
    end_ms: int,
    observed_at_ms: int | None = None,
):
    observed = end_ms + 20 if observed_at_ms is None else observed_at_ms
    return build_liquidation_feed_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        coverage_start_ms=start_ms,
        coverage_end_ms=end_ms,
        observed_at_ms=observed,
        source=DataSource.WEBSOCKET,
        adapter_version="cold-liquidation-test/1",
    )


def _store(hot: Path) -> MarketTapeStore:
    hot.mkdir(parents=True, exist_ok=True)
    store = MarketTapeStore(hot / "market_tape.sqlite3")
    store.initialize()
    return store


def test_liquidation_and_coverage_archive_only_after_verified_cold_write(
    tmp_path: Path,
) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    store = _store(hot)
    event_ms = 10 * HOUR_MS + 10_000
    event = _event(event_at_ms=event_ms)
    coverage = _coverage(
        start_ms=event_ms - 1_000,
        end_ms=event_ms + 1_000,
    )
    store.append_liquidation(event)
    store.append_liquidation_coverage(coverage)

    result = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    assert len(result.partitions) == 1
    assert result.archived_rows == 2
    assert result.pruned_rows == 2

    partition = cold / "year=1970/month=01/day=01/hour=10"
    manifest = verify_cold_partition(partition)
    assert manifest["schema_version"] == COLD_ARCHIVE_SCHEMA_VERSION
    assert manifest["tables"]["liquidations"]["rows"] == 1
    assert manifest["tables"]["liquidations"]["filename"] == "liquidations.parquet"
    assert manifest["tables"]["liquidations"]["time_column"] == "event_at_ms"
    assert manifest["tables"]["liquidation_coverage"]["rows"] == 1
    assert (
        manifest["tables"]["liquidation_coverage"]["filename"]
        == "liquidation_coverage.parquet"
    )
    assert (
        manifest["tables"]["liquidation_coverage"]["time_column"]
        == "coverage_end_ms"
    )

    assert store.recent_liquidations(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    ) == ()
    assert store.recent_liquidation_coverage(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    ) == ()
    assert store.quick_check() is True

    replay = cold_liquidation_replay(
        cold_dir=cold,
        coverage_identity=coverage.coverage_identity,
        as_of_ms=coverage.observed_at_ms,
    )
    assert replay.coverage == coverage
    assert replay.events == (event,)


def test_observed_zero_event_coverage_survives_hot_prune_and_cold_replay(
    tmp_path: Path,
) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    store = _store(hot)
    start = 10 * HOUR_MS + 5_000
    coverage = _coverage(start_ms=start, end_ms=start + 20_000)
    store.append_liquidation_coverage(coverage)

    result = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    assert result.archived_rows == 1
    assert result.pruned_rows == 1
    replay = cold_liquidation_replay(
        cold_dir=cold,
        coverage_identity=coverage.coverage_identity,
        as_of_ms=coverage.observed_at_ms,
    )
    assert replay.coverage == coverage
    assert replay.events == ()


def test_cross_hour_coverage_replay_composes_liquidations_from_both_partitions(
    tmp_path: Path,
) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    store = _store(hot)

    first = _event(
        event_at_ms=10 * HOUR_MS + 59 * 60 * 1000 + 50_000,
        row_index=0,
        side=LiquidatedPositionSide.LONG,
    )
    second = _event(
        event_at_ms=11 * HOUR_MS + 10_000,
        row_index=1,
        side=LiquidatedPositionSide.SHORT,
        price="101",
    )
    coverage = _coverage(
        start_ms=first.event_at_ms - 5_000,
        end_ms=second.event_at_ms + 5_000,
    )
    store.append_liquidation(first)
    store.append_liquidation(second)
    store.append_liquidation_coverage(coverage)

    result = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    assert len(result.partitions) == 2
    assert result.archived_rows == 3
    assert result.pruned_rows == 3

    hour10 = verify_cold_partition(
        cold / "year=1970/month=01/day=01/hour=10"
    )
    hour11 = verify_cold_partition(
        cold / "year=1970/month=01/day=01/hour=11"
    )
    assert hour10["tables"]["liquidations"]["rows"] == 1
    assert hour10["tables"]["liquidation_coverage"]["rows"] == 0
    assert hour11["tables"]["liquidations"]["rows"] == 1
    assert hour11["tables"]["liquidation_coverage"]["rows"] == 1

    replay = cold_liquidation_replay(
        cold_dir=cold,
        coverage_identity=coverage.coverage_identity,
        as_of_ms=coverage.observed_at_ms,
    )
    assert replay.events == (first, second)


def test_legacy_v1_1_partition_remains_verifiable_but_rejects_late_liquidation(
    tmp_path: Path,
) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    store = _store(hot)
    start = 10 * HOUR_MS
    event_ms = start + 10_000

    with sqlite3.connect(hot / "market_tape.sqlite3") as connection:
        connection.execute(
            """
            INSERT INTO market_tape_orderbooks(
                snapshot_identity, exchange, market_type, symbol,
                event_at_ms, source_timestamp_ms, ingested_at_ms,
                update_id, sequence, source, adapter_version, payload_json
            )
            VALUES (?, 'bybit', 'spot', 'BTCUSDT', ?, ?, ?,
                    1, 1, 'websocket', 'legacy-cold-test/1', ?)
            """,
            (
                "a" * 64,
                event_ms,
                event_ms + 1,
                event_ms + 2,
                '{"kind":"legacy-orderbook"}',
            ),
        )

    archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    partition = cold / "year=1970/month=01/day=01/hour=10"
    manifest_path = partition / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = "market-tape-cold-parquet-v1/1"
    manifest["tables"].pop("liquidations", None)
    manifest["tables"].pop("liquidation_coverage", None)
    for meta in manifest["tables"].values():
        meta.pop("time_column", None)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    )

    legacy = verify_cold_partition(partition)
    assert legacy["schema_version"] == "market-tape-cold-parquet-v1/1"

    late = _event(event_at_ms=event_ms + 5_000)
    store.append_liquidation(late)

    with pytest.raises(
        ValueError,
        match="late hot rows absent from legacy cold archive: liquidations",
    ):
        archive_due_hot_partitions(
            hot_dir=hot,
            cold_dir=cold,
            now_ms=40 * HOUR_MS,
            policy=_policy(),
        )

    assert store.recent_liquidations(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    ) == (late,)


def test_unknown_cold_schema_fails_closed(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    store = _store(hot)
    event = _event(event_at_ms=10 * HOUR_MS + 1_000)
    coverage = _coverage(
        start_ms=event.event_at_ms,
        end_ms=event.event_at_ms + 1_000,
    )
    store.append_liquidation(event)
    store.append_liquidation_coverage(coverage)
    archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    partition = cold / "year=1970/month=01/day=01/hour=10"
    manifest_path = partition / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = "market-tape-cold-parquet-unknown"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="unsupported cold archive schema"):
        verify_cold_partition(partition)


def test_cold_replay_rejects_future_coverage(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    store = _store(hot)
    event_ms = 10 * HOUR_MS + 10_000
    event = _event(event_at_ms=event_ms)
    coverage = _coverage(
        start_ms=event_ms,
        end_ms=event_ms + 1_000,
        observed_at_ms=event_ms + 5_000,
    )
    store.append_liquidation(event)
    store.append_liquidation_coverage(coverage)
    archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    with pytest.raises(
        MarketTapeConflictError,
        match="cold liquidation replay coverage is future evidence",
    ):
        cold_liquidation_replay(
            cold_dir=cold,
            coverage_identity=coverage.coverage_identity,
            as_of_ms=coverage.observed_at_ms - 1,
        )
