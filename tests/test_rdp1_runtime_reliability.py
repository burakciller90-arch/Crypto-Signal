from __future__ import annotations

import sqlite3

import pytest

from ops.run_market_tape_stream import monitor_ingestion_time
from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_heartbeat,
    build_collector_instance,
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
