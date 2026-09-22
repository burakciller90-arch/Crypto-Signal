from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("pyarrow")

from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_cold_archive import (
    archive_due_hot_partitions,
    verify_cold_partition,
)
from crypto_signal.data.market_tape_hotcold import MarketTapeHotColdPolicy
from crypto_signal.data.raw_market_tape import RawMarketTapeStore

HOUR_MS = 60 * 60 * 1000


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


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


def _initialize(hot: Path) -> tuple[Path, Path]:
    normalized = hot / "market_tape.sqlite3"
    raw = hot / "raw_market_tape.sqlite3"
    MarketTapeStore(normalized).initialize()
    RawMarketTapeStore(raw).initialize()
    return normalized, raw


def _insert_partition(
    hot: Path,
    *,
    start_ms: int,
    label: str,
) -> tuple[str, str, str]:
    normalized, raw = _initialize(hot)
    raw_identity = _sha(f"raw:{label}")
    book_identity = _sha(f"book:{label}")
    trade_identity = _sha(f"trade:{label}")
    event_ms = start_ms + 10_000

    with sqlite3.connect(raw) as connection:
        connection.execute(
            """
            INSERT INTO raw_market_events(
                event_identity, exchange, channel, symbol, event_kind,
                source_timestamp_ms, event_at_ms, ingested_at_ms,
                sequence, update_id, payload_json
            )
            VALUES (?, 'bybit', 'orderbook.50.BTCUSDT', 'BTCUSDT',
                    'delta', ?, ?, ?, 1, 1, ?)
            """,
            (
                raw_identity,
                event_ms + 2,
                event_ms,
                event_ms + 3,
                '{"topic":"orderbook.50.BTCUSDT","type":"delta"}',
            ),
        )

    with sqlite3.connect(normalized) as connection:
        connection.execute(
            """
            INSERT INTO market_tape_orderbooks(
                snapshot_identity, exchange, market_type, symbol,
                event_at_ms, source_timestamp_ms, ingested_at_ms,
                update_id, sequence, source, adapter_version, payload_json
            )
            VALUES (?, 'bybit', 'spot', 'BTCUSDT', ?, ?, ?,
                    1, 1, 'websocket', 'test/1', ?)
            """,
            (
                book_identity,
                event_ms,
                event_ms + 2,
                event_ms + 3,
                '{"kind":"orderbook"}',
            ),
        )
        connection.execute(
            """
            INSERT INTO market_tape_trades(
                trade_identity, exchange, market_type, symbol,
                event_at_ms, source_timestamp_ms, ingested_at_ms,
                exec_id, sequence, aggressor_side, source,
                adapter_version, payload_json
            )
            VALUES (?, 'bybit', 'spot', 'BTCUSDT', ?, ?, ?,
                    ?, 1, 'buy', 'websocket', 'test/1', ?)
            """,
            (
                trade_identity,
                event_ms + 1,
                event_ms + 2,
                event_ms + 3,
                f"exec-{label}",
                '{"kind":"trade"}',
            ),
        )

    return raw_identity, book_identity, trade_identity


def _count_window(db: Path, table: str, start_ms: int, end_ms: int) -> int:
    with sqlite3.connect(db) as connection:
        return int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE event_at_ms >= ? AND event_at_ms < ?",
                (start_ms, end_ms),
            ).fetchone()[0]
        )


def test_verified_hourly_parquet_is_written_before_hot_prune(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    hot.mkdir()
    old_start = 10 * HOUR_MS
    fresh_start = 20 * HOUR_MS
    _insert_partition(hot, start_ms=old_start, label="old")
    _insert_partition(hot, start_ms=fresh_start, label="fresh")

    result = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    assert len(result.partitions) == 1
    partition = result.partitions[0]
    assert partition.window_start_ms == old_start
    assert partition.window_end_ms == old_start + HOUR_MS
    assert partition.archived_rows == 3
    assert partition.pruned_rows == 3
    assert partition.reused_existing_partition is False

    path = cold / "year=1970/month=01/day=01/hour=10"
    manifest = verify_cold_partition(path)
    assert manifest["partition_id"] == "19700101T100000Z"
    assert manifest["compression"] == "zstd"
    assert manifest["tables"]["raw"]["rows"] == 1
    assert manifest["tables"]["orderbooks"]["rows"] == 1
    assert manifest["tables"]["trades"]["rows"] == 1
    assert manifest["tables"]["derivatives"]["rows"] == 0

    normalized = hot / "market_tape.sqlite3"
    raw = hot / "raw_market_tape.sqlite3"
    assert _count_window(raw, "raw_market_events", old_start, old_start + HOUR_MS) == 0
    assert _count_window(
        normalized,
        "market_tape_orderbooks",
        old_start,
        old_start + HOUR_MS,
    ) == 0
    assert _count_window(
        normalized,
        "market_tape_trades",
        old_start,
        old_start + HOUR_MS,
    ) == 0

    assert _count_window(
        raw,
        "raw_market_events",
        fresh_start,
        fresh_start + HOUR_MS,
    ) == 1
    assert sqlite3.connect(raw).execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert (
        sqlite3.connect(normalized).execute("PRAGMA quick_check").fetchone()[0]
        == "ok"
    )


def test_existing_verified_partition_can_finish_interrupted_hot_prune(
    tmp_path: Path,
) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    hot.mkdir()
    start = 10 * HOUR_MS
    identities = _insert_partition(hot, start_ms=start, label="recover")

    first = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )
    assert first.pruned_rows == 3

    _insert_partition(hot, start_ms=start, label="recover")
    second = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    assert len(second.partitions) == 1
    assert second.partitions[0].reused_existing_partition is True
    assert second.partitions[0].pruned_rows == 3
    assert all(len(value) == 64 for value in identities)


def test_late_row_absent_from_immutable_cold_partition_fails_closed(
    tmp_path: Path,
) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    hot.mkdir()
    start = 10 * HOUR_MS
    _insert_partition(hot, start_ms=start, label="original")
    archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    normalized, raw = _initialize(hot)
    late_identity = _sha("raw:late")
    event_ms = start + 20_000
    with sqlite3.connect(raw) as connection:
        connection.execute(
            """
            INSERT INTO raw_market_events(
                event_identity, exchange, channel, symbol, event_kind,
                source_timestamp_ms, event_at_ms, ingested_at_ms,
                sequence, update_id, payload_json
            )
            VALUES (?, 'bybit', 'publicTrade.BTCUSDT', 'BTCUSDT',
                    'trade', ?, ?, ?, 2, 2, ?)
            """,
            (
                late_identity,
                event_ms + 1,
                event_ms,
                event_ms + 2,
                '{"topic":"publicTrade.BTCUSDT","late":true}',
            ),
        )

    with pytest.raises(ValueError, match="late hot row absent"):
        archive_due_hot_partitions(
            hot_dir=hot,
            cold_dir=cold,
            now_ms=40 * HOUR_MS,
            policy=_policy(),
        )

    assert _count_window(
        raw,
        "raw_market_events",
        start,
        start + HOUR_MS,
    ) == 1
    assert _count_window(
        normalized,
        "market_tape_orderbooks",
        start,
        start + HOUR_MS,
    ) == 0


def test_tampered_parquet_fails_verification(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    hot.mkdir()
    start = 10 * HOUR_MS
    _insert_partition(hot, start_ms=start, label="tamper")
    archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    path = cold / "year=1970/month=01/day=01/hour=10"
    with (path / "raw.parquet").open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(ValueError, match="file hash mismatch"):
        verify_cold_partition(path)


def test_not_due_hot_rows_are_not_archived(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    cold = tmp_path / "cold"
    hot.mkdir()
    start = 30 * HOUR_MS
    _insert_partition(hot, start_ms=start, label="young")

    result = archive_due_hot_partitions(
        hot_dir=hot,
        cold_dir=cold,
        now_ms=40 * HOUR_MS,
        policy=_policy(),
    )

    assert result.partitions == ()
    assert _count_window(
        hot / "raw_market_tape.sqlite3",
        "raw_market_events",
        start,
        start + HOUR_MS,
    ) == 1
