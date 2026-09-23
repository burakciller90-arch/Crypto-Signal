from __future__ import annotations

import sqlite3

import pytest

from crypto_signal.data.market_tape_collector_runtime import (
    CollectorRuntimeConflictError,
    CollectorStartKind,
    MarketTapeCollectorRuntimeStore,
    build_collector_heartbeat,
    build_collector_instance,
)


def test_collector_runtime_persists_start_restart_and_heartbeat(tmp_path) -> None:
    store = MarketTapeCollectorRuntimeStore(tmp_path / "collector.sqlite3")
    first = build_collector_instance(
        provider="bybit",
        source="market_tape_stream",
        symbols=("SOLUSDT", "BTCUSDT", "ETHUSDT"),
        started_at_ms=1_000,
        process_id=101,
        runtime_nonce="boot-a",
    )
    store.append_instance(first)
    store.append_instance(first)

    heartbeat = build_collector_heartbeat(
        instance_identity=first.instance_identity,
        sequence_no=1,
        observed_at_ms=1_200,
        last_successful_ingestion_ms=1_190,
        observed_messages_total=7,
        normalized_rows_total=5,
        raw_rows_total=7,
    )
    store.append_heartbeat(heartbeat)
    store.append_heartbeat(heartbeat)

    second = build_collector_instance(
        provider="bybit",
        source="market_tape_stream",
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        started_at_ms=2_000,
        process_id=202,
        runtime_nonce="boot-b",
        previous_instance_identity=first.instance_identity,
    )
    store.append_instance(second)

    assert first.start_kind is CollectorStartKind.START
    assert second.start_kind is CollectorStartKind.RESTART
    assert second.previous_instance_identity == first.instance_identity
    assert store.latest_instance(
        provider="bybit",
        source="market_tape_stream",
    ) == second
    assert store.latest_heartbeat(first.instance_identity) == heartbeat
    assert store.latest_heartbeat(second.instance_identity) is None
    assert store.quick_check() is True

    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM collector_instances").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM collector_heartbeats").fetchone()[0] == 1


def test_collector_heartbeat_fails_closed_on_regression_and_unknown_parent(
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
    first = build_collector_heartbeat(
        instance_identity=instance.instance_identity,
        sequence_no=2,
        observed_at_ms=2_000,
        last_successful_ingestion_ms=1_900,
        observed_messages_total=10,
        normalized_rows_total=8,
        raw_rows_total=10,
    )
    store.append_heartbeat(first)

    regressed = build_collector_heartbeat(
        instance_identity=instance.instance_identity,
        sequence_no=3,
        observed_at_ms=2_100,
        last_successful_ingestion_ms=1_800,
        observed_messages_total=11,
        normalized_rows_total=9,
        raw_rows_total=11,
    )
    with pytest.raises(ValueError, match="ingestion time regressed"):
        store.append_heartbeat(regressed)

    unknown = build_collector_heartbeat(
        instance_identity="f" * 64,
        sequence_no=1,
        observed_at_ms=2_100,
        last_successful_ingestion_ms=2_000,
        observed_messages_total=1,
        normalized_rows_total=1,
        raw_rows_total=1,
    )
    with pytest.raises(ValueError, match="unknown instance"):
        store.append_heartbeat(unknown)


def test_collector_heartbeat_same_sequence_conflict_is_rejected(tmp_path) -> None:
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
    first = build_collector_heartbeat(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        observed_at_ms=1_100,
        last_successful_ingestion_ms=1_090,
        observed_messages_total=1,
        normalized_rows_total=1,
        raw_rows_total=1,
    )
    conflict = build_collector_heartbeat(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        observed_at_ms=1_200,
        last_successful_ingestion_ms=1_190,
        observed_messages_total=2,
        normalized_rows_total=2,
        raw_rows_total=2,
    )
    store.append_heartbeat(first)
    with pytest.raises(CollectorRuntimeConflictError, match="sequence conflict"):
        store.append_heartbeat(conflict)
