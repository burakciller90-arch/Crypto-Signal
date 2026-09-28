from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from crypto_signal.data.adapters.bybit_liquidation_ws import (
    BybitLiquidationWireBatch,
    LiquidationTransportEvent,
    LiquidationTransportEventKind,
    build_bybit_liquidation_wire_batch,
)
from crypto_signal.data.liquidation_runtime import (
    LiquidationConnectionRuntimeStore,
    LiquidationConnectionState,
    LiquidationRuntimeConflictError,
    build_liquidation_connection_coverage,
)
from crypto_signal.data.liquidation_wire_collection import (
    LiquidationWireCollectionResult,
    persist_bybit_liquidation_wire_stream,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_instance,
)
from crypto_signal.data.raw_market_tape import RawMarketTapeStore


def _instance(runtime: MarketTapeCollectorRuntimeStore):
    instance = build_collector_instance(
        provider="bybit",
        source="liquidation_stream",
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        started_at_ms=1_000,
        process_id=50401,
        runtime_nonce="rdp5-a",
    )
    runtime.append_instance(instance)
    return instance


def _coverage(
    *,
    instance_identity: str,
    sequence_no: int,
    state: LiquidationConnectionState,
    observed_at_ms: int,
    connected_since_ms: int | None = 1_000,
    last_transport_activity_ms: int | None = 1_000,
    last_liquidation_ingestion_ms: int | None = None,
):
    if state is LiquidationConnectionState.DISCONNECTED:
        connected_since_ms = None
    return build_liquidation_connection_coverage(
        instance_identity=instance_identity,
        sequence_no=sequence_no,
        state=state,
        observed_at_ms=observed_at_ms,
        connected_since_ms=connected_since_ms,
        last_transport_activity_ms=last_transport_activity_ms,
        last_liquidation_ingestion_ms=last_liquidation_ingestion_ms,
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        reason_codes=(f"state_{state.value}",),
    )


def test_connection_runtime_is_parent_bound_append_only_and_monotonic(
    tmp_path,
) -> None:
    path = tmp_path / "liquidation-runtime.sqlite3"
    runtime = MarketTapeCollectorRuntimeStore(path)
    instance = _instance(runtime)
    connection = LiquidationConnectionRuntimeStore(path)

    first = _coverage(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        state=LiquidationConnectionState.CONNECTED,
        observed_at_ms=1_100,
        last_transport_activity_ms=1_090,
    )
    second = _coverage(
        instance_identity=instance.instance_identity,
        sequence_no=2,
        state=LiquidationConnectionState.STALE,
        observed_at_ms=1_200,
        last_transport_activity_ms=1_090,
    )

    connection.append(first)
    connection.append(first)
    connection.append(second)

    assert connection.latest(instance.instance_identity) == second
    assert connection.quick_check() is True
    assert first.production_authority is False
    assert first.real_capital == 0

    conflicting = _coverage(
        instance_identity=instance.instance_identity,
        sequence_no=2,
        state=LiquidationConnectionState.CONNECTED,
        observed_at_ms=1_200,
        last_transport_activity_ms=1_190,
    )
    with pytest.raises(
        LiquidationRuntimeConflictError,
        match="sequence conflict",
    ):
        connection.append(conflicting)

    regressed = _coverage(
        instance_identity=instance.instance_identity,
        sequence_no=3,
        state=LiquidationConnectionState.CONNECTED,
        observed_at_ms=1_050,
        last_transport_activity_ms=1_050,
    )
    with pytest.raises(ValueError, match="observation time regressed"):
        connection.append(regressed)

    unknown = _coverage(
        instance_identity="f" * 64,
        sequence_no=1,
        state=LiquidationConnectionState.CONNECTED,
        observed_at_ms=1_100,
        last_transport_activity_ms=1_090,
    )
    with pytest.raises(ValueError, match="unknown instance"):
        connection.append(unknown)


def test_connection_runtime_cannot_erase_liquidation_ingestion_evidence(
    tmp_path,
) -> None:
    path = tmp_path / "liquidation-runtime.sqlite3"
    runtime = MarketTapeCollectorRuntimeStore(path)
    instance = _instance(runtime)
    connection = LiquidationConnectionRuntimeStore(path)

    first = _coverage(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        state=LiquidationConnectionState.CONNECTED,
        observed_at_ms=2_100,
        last_transport_activity_ms=2_090,
        last_liquidation_ingestion_ms=2_080,
    )
    connection.append(first)

    with pytest.raises(ValueError, match="cannot disappear"):
        connection.append(
            _coverage(
                instance_identity=instance.instance_identity,
                sequence_no=2,
                state=LiquidationConnectionState.CONNECTED,
                observed_at_ms=2_200,
                last_transport_activity_ms=2_190,
                last_liquidation_ingestion_ms=None,
            )
        )

    with pytest.raises(ValueError, match="ingestion time regressed"):
        connection.append(
            _coverage(
                instance_identity=instance.instance_identity,
                sequence_no=2,
                state=LiquidationConnectionState.CONNECTED,
                observed_at_ms=2_200,
                last_transport_activity_ms=2_190,
                last_liquidation_ingestion_ms=2_070,
            )
        )


def test_connection_coverage_table_is_sql_immutable(tmp_path) -> None:
    path = tmp_path / "liquidation-runtime.sqlite3"
    runtime = MarketTapeCollectorRuntimeStore(path)
    instance = _instance(runtime)
    connection = LiquidationConnectionRuntimeStore(path)
    coverage = _coverage(
        instance_identity=instance.instance_identity,
        sequence_no=1,
        state=LiquidationConnectionState.CONNECTED,
        observed_at_ms=1_100,
        last_transport_activity_ms=1_090,
    )
    connection.append(coverage)

    with sqlite3.connect(path) as db:
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable",
        ):
            db.execute(
                """
                UPDATE liquidation_connection_coverage
                SET state='stale'
                WHERE coverage_identity=?
                """,
                (coverage.coverage_identity,),
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable",
        ):
            db.execute(
                """
                DELETE FROM liquidation_connection_coverage
                WHERE coverage_identity=?
                """,
                (coverage.coverage_identity,),
            )


def test_disconnected_coverage_cannot_claim_active_session() -> None:
    with pytest.raises(ValueError, match="cannot claim active session"):
        build_liquidation_connection_coverage(
            instance_identity="a" * 64,
            sequence_no=1,
            state=LiquidationConnectionState.DISCONNECTED,
            observed_at_ms=1_100,
            connected_since_ms=1_000,
            last_transport_activity_ms=1_090,
            last_liquidation_ingestion_ms=None,
            symbols=("BTCUSDT",),
            reason_codes=("transport_disconnected",),
        )


def _payload(
    *,
    ts: int = 2_000,
    symbol: str = "BTCUSDT",
) -> dict[str, object]:
    return {
        "topic": f"allLiquidation.{symbol}",
        "type": "snapshot",
        "ts": ts,
        "data": [
            {
                "T": ts - 100,
                "s": symbol,
                "S": "Buy",
                "v": "0.25",
                "p": "100.5",
            }
        ],
    }


async def _batches() -> AsyncIterator[BybitLiquidationWireBatch]:
    yield build_bybit_liquidation_wire_batch(
        _payload(),
        expected_symbol="BTCUSDT",
        ingested_at_ms=2_010,
    )


def test_liquidation_progress_callback_runs_after_raw_and_normalized_persistence(
    tmp_path,
) -> None:
    market = MarketTapeStore(tmp_path / "market.sqlite3")
    raw = RawMarketTapeStore(tmp_path / "raw.sqlite3")
    calls: list[LiquidationWireCollectionResult] = []

    def callback(batch, progress: LiquidationWireCollectionResult) -> None:
        assert raw.count() == 1
        assert market.counts().liquidations == 1
        assert market.counts().liquidation_coverage == 1
        assert batch.coverage.coverage_identity
        calls.append(progress)

    result = asyncio.run(
        persist_bybit_liquidation_wire_stream(
            store=market,
            raw_store=raw,
            batches=_batches(),
            max_messages=1,
            collection_progress_callback=callback,
        )
    )

    assert calls == [result]
    assert result.observed_messages == 1
    assert result.normalized_inserted_total == 2


def test_transport_event_model_is_separate_from_liquidation_event_coverage() -> None:
    connected = LiquidationTransportEvent(
        kind=LiquidationTransportEventKind.CONNECTED,
        observed_at_ms=5_000,
    )
    subscribed = LiquidationTransportEvent(
        kind=LiquidationTransportEventKind.SUBSCRIBED,
        observed_at_ms=5_010,
    )
    activity = LiquidationTransportEvent(
        kind=LiquidationTransportEventKind.ACTIVITY,
        observed_at_ms=5_020,
    )

    assert connected.kind is LiquidationTransportEventKind.CONNECTED
    assert subscribed.kind is LiquidationTransportEventKind.SUBSCRIBED
    assert activity.kind is LiquidationTransportEventKind.ACTIVITY
    assert not hasattr(connected, "coverage_start_ms")


def test_liquidation_adapter_exposes_transport_liveness_without_zero_events() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "crypto_signal"
        / "data"
        / "adapters"
        / "bybit_liquidation_ws.py"
    ).read_text(encoding="utf-8")

    assert "LiquidationTransportEventKind.CONNECTED" in source
    assert "LiquidationTransportEventKind.SUBSCRIBED" in source
    assert "LiquidationTransportEventKind.ACTIVITY" in source
    assert "LiquidationTransportEventKind.DISCONNECTED" in source
    assert "Bybit liquidation subscription rejected" in source
    assert "silence is not converted into zero-event coverage" in source


def test_runner_is_continuous_by_default_without_zero_event_fabrication() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "run_liquidation_market_tape_stream.py"
    ).read_text(encoding="utf-8")

    assert '"--max-messages"' in source
    assert "default=0" in source
    assert "None if args.max_messages == 0 else args.max_messages" in source
    assert "LIQUIDATION_CONNECTION_COVERAGE" in source
    assert "ZERO_EVENT_COVERAGE_INVENTED=NO" in source
    assert "PRODUCTION_RUNTIME=YES REAL_CAPITAL=0" in source
    assert "LIQUIDATION_COLLECTOR_DISABLED_BY_DEFAULT" not in source
    assert "BOUNDED_MAX_MESSAGES_REQUIRED" not in source


def test_supervisor_owns_exact_continuous_liquidation_runtime() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "ssd_runtime_supervisor.sh"
    ).read_text(encoding="utf-8")

    assert "liquidation_pid_is_expected()" in source
    assert "liquidation_pid_is_healthy()" in source
    assert "adopt_liquidation_stream()" in source
    assert "start_liquidation_stream()" in source
    assert 'local runner="$DEV/ops/run_liquidation_market_tape_stream.py"' in source
    assert 'local lock="$runtime/liquidation_stream.lock"' in source
    assert (
        'local collector_runtime="$runtime/liquidation_collector_runtime.sqlite3"'
        in source
    )
    assert '--bybit-ws-url "$BYBIT_LIQUIDATION_WS_URL"' in source
    assert "--heartbeat-interval-ms 10000" in source
    assert "--max-transport-silence-ms 45000" in source
    assert "--max-messages 0" in source
    assert 'echo "$pid" > "$ROOT/liquidation-stream.pid"' in source
    assert 'str(coverage_payload["state"]) != "connected"' in source
    assert (
        "start_liquidation_stream\n"
        "  start_market_tape_stream\n"
        "  now="
    ) in source
    assert "liquidation_started pid=$pid REAL_CAPITAL=0" in source


def test_supervisor_liquidation_owner_check_avoids_bsd_awk_parser() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "ssd_runtime_supervisor.sh"
    ).read_text(encoding="utf-8")

    start = source.index("liquidation_pid_is_expected()")
    end = source.index("liquidation_pid_is_healthy()", start)
    owner_check = source[start:end]

    assert "/usr/bin/awk" not in owner_check
    assert "/bin/ps -p" in owner_check
    assert "/usr/bin/grep -F" in owner_check
    assert "--bybit-ws-url $BYBIT_LIQUIDATION_WS_URL" in owner_check
    assert "--max-messages 0" in owner_check
    assert "--heartbeat-interval-ms 10000" in owner_check
    assert "--max-transport-silence-ms 45000" in owner_check


def test_supervisor_health_does_not_require_liquidation_event_ingestion() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "ssd_runtime_supervisor.sh"
    ).read_text(encoding="utf-8")

    start = source.index("liquidation_pid_is_healthy()")
    end = source.index("stop_liquidation_pid()", start)
    health = source[start:end]

    assert "liquidation_connection_coverage" in health
    assert 'coverage_payload["state"]' in health
    assert "last_successful_ingestion_ms" not in health
    assert "liquidation event" not in health.lower()
