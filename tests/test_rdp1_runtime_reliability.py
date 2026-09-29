from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from crypto_signal.data.market_data_gap_ledger import MarketDataGapLedger
from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_heartbeat,
    build_collector_instance,
)
from ops.run_market_tape_stream import (
    _is_transient_sqlite_lock,
    _restart_seed_events,
    monitor_ingestion_time,
)


def test_monitor_ingestion_time_preserves_monotonic_runtime_floor() -> None:
    assert monitor_ingestion_time(None, 1_000) == (1_000, False)
    assert monitor_ingestion_time(1_000, 1_050) == (1_050, False)
    assert monitor_ingestion_time(1_050, 1_040) == (1_050, True)


def test_monitor_ingestion_time_rejects_negative_raw_time() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        monitor_ingestion_time(1_000, -1)


def test_collector_runtime_preserves_journal_contract_and_initializes_once(
    tmp_path,
) -> None:
    store = MarketTapeCollectorRuntimeStore(tmp_path / "collector.sqlite3")
    instance = build_collector_instance(
        provider="bybit",
        source="market_tape_stream",
        symbols=("BTCUSDT",),
        started_at_ms=1_000,
        process_id=101,
        runtime_nonce="boot-a",
    )
    store.append_instance(instance)

    heartbeat = build_collector_heartbeat(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        observed_at_ms=1_200,
        last_successful_ingestion_ms=1_190,
        observed_messages_total=1,
        normalized_rows_total=1,
        raw_rows_total=1,
    )
    store.append_heartbeat(heartbeat)

    with sqlite3.connect(store.path) as db:
        mode = str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        count = int(
            db.execute("SELECT COUNT(*) FROM collector_heartbeats").fetchone()[0]
        )

    assert mode == "delete"
    assert count == 1
    assert store._initialized is True


def test_existing_runtime_schema_initialization_is_read_only_under_reader(
    tmp_path,
) -> None:
    collector_path = tmp_path / "collector.sqlite3"
    store = MarketTapeCollectorRuntimeStore(collector_path)
    instance = build_collector_instance(
        provider="bybit",
        source="market_tape_stream",
        symbols=("BTCUSDT",),
        started_at_ms=2_000,
        process_id=202,
        runtime_nonce="boot-b",
    )
    store.append_instance(instance)
    before = collector_path.read_bytes()

    reader = sqlite3.connect(collector_path, timeout=1.0)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM collector_instances").fetchone()
        restarted = MarketTapeCollectorRuntimeStore(collector_path)
        restarted.initialize()
        assert restarted._initialized is True
    finally:
        reader.rollback()
        reader.close()

    assert collector_path.read_bytes() == before


def test_existing_gap_schema_initialization_is_read_only_under_reader(
    tmp_path,
) -> None:
    gap_path = tmp_path / "gaps.sqlite3"
    initial = MarketDataGapLedger(gap_path)
    initial.initialize()
    before = gap_path.read_bytes()

    reader = sqlite3.connect(gap_path, timeout=1.0)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM market_data_gap_events").fetchone()
        restarted = MarketDataGapLedger(gap_path)
        restarted.initialize()
        assert restarted._initialized is True
    finally:
        reader.rollback()
        reader.close()

    assert gap_path.read_bytes() == before


def test_market_tape_runner_keeps_environment_aware_websocket_proxy() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_market_tape_stream.py"
    )
    text = runner.read_text(encoding="utf-8")

    assert "proxy=None" not in text
    assert (
        "BybitSpotMicrostructureStream(\n"
        "        url=args.bybit_ws_url,\n"
        "    )"
    ) in text


def test_restart_seed_events_reads_only_latest_indexed_context(tmp_path) -> None:
    raw = tmp_path / "raw.sqlite3"
    with sqlite3.connect(raw) as db:
        db.execute(
            """
            CREATE TABLE raw_market_events (
                event_identity TEXT PRIMARY KEY,
                exchange TEXT NOT NULL,
                channel TEXT NOT NULL,
                symbol TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                source_timestamp_ms INTEGER NOT NULL,
                event_at_ms INTEGER NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                update_id INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE INDEX idx_raw_market_events_context
            ON raw_market_events(
                exchange, channel, symbol, event_at_ms, sequence, update_id
            )
            """
        )
        rows = [
            ("1" * 64, "bybit", "orderbook.50", "BTCUSDT", "snapshot", 100, 100, 101, 1, 1, "{}"),
            ("2" * 64, "bybit", "orderbook.50", "BTCUSDT", "delta", 200, 200, 201, 2, 2, "{}"),
            ("3" * 64, "bybit", "publicTrade", "BTCUSDT", "trade_batch", 150, 150, 151, 3, 0, "{}"),
        ]
        db.executemany(
            """
            INSERT INTO raw_market_events(
                event_identity, exchange, channel, symbol, event_kind,
                source_timestamp_ms, event_at_ms, ingested_at_ms,
                sequence, update_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    events = _restart_seed_events(
        raw,
        symbols=("BTCUSDT",),
        depth=50,
    )

    assert {(event.channel, event.event_at_ms) for event in events} == {
        ("orderbook.50", 200),
        ("publicTrade", 150),
    }


def test_restart_path_prefers_previous_heartbeat_before_heavy_counts() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_market_tape_stream.py"
    ).read_text(encoding="utf-8")

    assert "previous_heartbeat = (" in runner
    assert "baseline_normalized_rows_total = (" in runner
    assert "previous_heartbeat.normalized_rows_total" in runner
    assert "previous_heartbeat.raw_rows_total" in runner
    assert "if previous_heartbeat is None:" in runner


def test_market_tape_snapshot_hot_path_avoids_full_db_scans() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_market_tape_snapshot.py"
    ).read_text(encoding="utf-8")

    assert "store.counts()" not in runner
    assert "store.quick_check()" not in runner
    assert "FULL_DB_INTEGRITY_DELEGATED=YES" in runner
    assert "--bybit-base-url" in runner


def test_runtime_supervisor_binds_snapshot_to_regional_bybit_rest() -> None:
    supervisor = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "ssd_runtime_supervisor.sh"
    ).read_text(encoding="utf-8")

    assert '--bybit-base-url "$BYBIT_REST_BASE_URL"' in supervisor



def test_transient_sqlite_lock_classifier_is_narrow() -> None:
    assert _is_transient_sqlite_lock(
        sqlite3.OperationalError("database is locked")
    )
    assert _is_transient_sqlite_lock(
        sqlite3.OperationalError("database table is locked")
    )
    assert _is_transient_sqlite_lock(
        sqlite3.OperationalError("database is busy")
    )
    assert not _is_transient_sqlite_lock(
        sqlite3.OperationalError("no such table: collector_heartbeats")
    )


def test_collector_runtime_rejects_nonpositive_sqlite_timeout(tmp_path) -> None:
    store = MarketTapeCollectorRuntimeStore(tmp_path / "collector.sqlite3")

    with pytest.raises(ValueError, match="timeout must be positive"):
        store._connect(timeout_seconds=0)


def test_heartbeat_loop_retries_transient_lock_without_killing_stream() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_market_tape_stream.py"
    ).read_text(encoding="utf-8")

    assert "HEARTBEAT_DB_TIMEOUT_SECONDS = 1.0" in runner
    assert "HEARTBEAT_DB_RETRY_ATTEMPTS = 3" in runner
    assert "await asyncio.to_thread(" in runner
    assert "runtime_store.append_heartbeat," in runner
    assert "MARKET_TAPE_HEARTBEAT_DB_LOCK" in runner
    assert "MARKET_TAPE_HEARTBEAT_DB_DEFERRED" in runner
    assert "MARKET_TAPE_GAP_HEARTBEAT_DB_DEFERRED" in runner
    assert "await emit_heartbeat()" in runner
