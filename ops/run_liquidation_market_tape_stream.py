from __future__ import annotations

import argparse
import asyncio
import fcntl
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path

from crypto_signal.data.adapters.bybit_liquidation_ws import (
    BybitLinearLiquidationStream,
    BybitLiquidationWireBatch,
    LiquidationTransportEvent,
    LiquidationTransportEventKind,
)
from crypto_signal.data.liquidation_runtime import (
    LiquidationConnectionRuntimeStore,
    LiquidationConnectionState,
    build_liquidation_connection_coverage,
)
from crypto_signal.data.liquidation_wire_collection import (
    LiquidationWireCollectionResult,
    persist_bybit_liquidation_wire_stream,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_heartbeat,
    build_collector_instance,
)
from crypto_signal.data.raw_market_tape import RawMarketTapeStore

DEFAULT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape.sqlite3"
)
DEFAULT_RAW_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/raw_market_tape.sqlite3"
)
DEFAULT_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/liquidation_stream.lock"
)
DEFAULT_RUNTIME_STATUS_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/liquidation_collector_runtime.sqlite3"
)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DEFAULT_HEARTBEAT_INTERVAL_MS = 10_000
DEFAULT_MAX_TRANSPORT_SILENCE_MS = 45_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--raw-db", type=Path, default=DEFAULT_RAW_DB)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--runtime-status-db",
        type=Path,
        default=DEFAULT_RUNTIME_STATUS_DB,
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--bybit-ws-url",
        default=None,
        help="optional explicit Bybit public linear WebSocket URL",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=0,
        help="0 means run continuously; positive values bound diagnostics",
    )
    parser.add_argument(
        "--heartbeat-interval-ms",
        type=int,
        default=DEFAULT_HEARTBEAT_INTERVAL_MS,
    )
    parser.add_argument(
        "--max-transport-silence-ms",
        type=int,
        default=DEFAULT_MAX_TRANSPORT_SILENCE_MS,
    )
    parser.add_argument(
        "--enable-development-collector",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    for label, path in (
        ("db", args.db),
        ("raw_db", args.raw_db),
        ("runtime_status_db", args.runtime_status_db),
    ):
        if not str(path).startswith("/Volumes/Crypto-504/"):
            print(
                "LIQUIDATION_COLLECTOR_ERROR=NON_CANONICAL_DB_PATH "
                f"field={label}",
                file=sys.stderr,
                flush=True,
            )
            return 2
    if (
        args.bybit_ws_url is not None
        and not str(args.bybit_ws_url).startswith("wss://")
    ):
        print(
            "LIQUIDATION_COLLECTOR_ERROR=INVALID_BYBIT_WS_URL",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.max_messages < 0:
        print(
            "LIQUIDATION_COLLECTOR_ERROR=NEGATIVE_MAX_MESSAGES",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.heartbeat_interval_ms <= 0:
        print(
            "LIQUIDATION_COLLECTOR_ERROR=INVALID_HEARTBEAT_INTERVAL",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if (
        args.max_transport_silence_ms
        <= args.heartbeat_interval_ms
    ):
        print(
            "LIQUIDATION_COLLECTOR_ERROR=INVALID_TRANSPORT_SILENCE_POLICY",
            file=sys.stderr,
            flush=True,
        )
        return 2

    symbols = tuple(
        dict.fromkeys(str(value).upper() for value in args.symbols)
    )
    if not symbols or any(not value for value in symbols):
        print(
            "LIQUIDATION_COLLECTOR_ERROR=INVALID_SYMBOLS",
            file=sys.stderr,
            flush=True,
        )
        return 2

    store = MarketTapeStore(args.db)
    raw_store = RawMarketTapeStore(args.raw_db)
    runtime_store = MarketTapeCollectorRuntimeStore(args.runtime_status_db)

    previous = runtime_store.latest_instance(
        provider="bybit",
        source="liquidation_stream",
    )
    previous_heartbeat = (
        None
        if previous is None
        else runtime_store.latest_heartbeat(previous.instance_identity)
    )
    if previous_heartbeat is None:
        if not store.quick_check() or not raw_store.quick_check():
            print(
                "LIQUIDATION_COLLECTOR_ERROR=SQLITE_QUICK_CHECK_FAIL",
                file=sys.stderr,
                flush=True,
            )
            return 3
        counts = store.counts()
        baseline_normalized_rows_total = (
            counts.liquidations + counts.liquidation_coverage
        )
        baseline_raw_rows_total = raw_store.count()
    else:
        baseline_normalized_rows_total = (
            previous_heartbeat.normalized_rows_total
        )
        baseline_raw_rows_total = previous_heartbeat.raw_rows_total

    instance = build_collector_instance(
        provider="bybit",
        source="liquidation_stream",
        symbols=tuple(sorted(symbols)),
        started_at_ms=time.time_ns() // 1_000_000,
        process_id=os.getpid(),
        runtime_nonce=secrets.token_hex(16),
        previous_instance_identity=(
            None if previous is None else previous.instance_identity
        ),
    )
    runtime_store.append_instance(instance)
    connection_store = LiquidationConnectionRuntimeStore(
        args.runtime_status_db
    )
    connection_store.initialize()

    heartbeat_sequence = 0
    last_ingestion_ms = (
        None
        if previous_heartbeat is None
        else previous_heartbeat.last_successful_ingestion_ms
    )
    last_observed_messages = 0
    normalized_rows_total = baseline_normalized_rows_total
    raw_rows_total = baseline_raw_rows_total
    transport_connected = False
    subscription_confirmed = False
    connected_since_ms: int | None = None
    last_transport_activity_ms: int | None = None
    transport_clock_regressions = 0
    ingestion_clock_regressions = 0
    runtime_clock_floor_ms = max(
        time.time_ns() // 1_000_000,
        last_ingestion_ms or 0,
    )
    heartbeat_stop = asyncio.Event()
    heartbeat_kick = asyncio.Event()

    def monotonic_runtime_time(*values: int | None) -> int:
        nonlocal runtime_clock_floor_ms
        runtime_clock_floor_ms = max(
            runtime_clock_floor_ms,
            time.time_ns() // 1_000_000,
            *(value or 0 for value in values),
        )
        return runtime_clock_floor_ms

    def persist_transport_event(
        event: LiquidationTransportEvent,
    ) -> None:
        nonlocal transport_connected
        nonlocal subscription_confirmed
        nonlocal connected_since_ms
        nonlocal last_transport_activity_ms
        nonlocal transport_clock_regressions

        effective = event.observed_at_ms
        if (
            last_transport_activity_ms is not None
            and effective < last_transport_activity_ms
        ):
            transport_clock_regressions += 1
            effective = last_transport_activity_ms
        if event.kind is LiquidationTransportEventKind.CONNECTED:
            transport_connected = True
            subscription_confirmed = False
            connected_since_ms = effective
            last_transport_activity_ms = effective
        elif event.kind is LiquidationTransportEventKind.SUBSCRIBED:
            transport_connected = True
            subscription_confirmed = True
            connected_since_ms = connected_since_ms or effective
            last_transport_activity_ms = effective
        elif event.kind is LiquidationTransportEventKind.ACTIVITY:
            last_transport_activity_ms = effective
        else:
            transport_connected = False
            subscription_confirmed = False
            connected_since_ms = None
            last_transport_activity_ms = effective
        heartbeat_kick.set()

    def persist_collection_progress(
        batch: BybitLiquidationWireBatch,
        progress: LiquidationWireCollectionResult,
    ) -> None:
        nonlocal last_ingestion_ms
        nonlocal last_observed_messages
        nonlocal normalized_rows_total
        nonlocal raw_rows_total
        nonlocal ingestion_clock_regressions

        incoming = batch.ingested_at_ms
        if last_ingestion_ms is not None and incoming < last_ingestion_ms:
            ingestion_clock_regressions += 1
            incoming = last_ingestion_ms
        last_ingestion_ms = incoming
        last_observed_messages = progress.observed_messages
        normalized_rows_total = (
            baseline_normalized_rows_total
            + progress.normalized_inserted_total
        )
        raw_rows_total = baseline_raw_rows_total + progress.raw_inserted
        heartbeat_kick.set()

    def connection_state(
        observed_at_ms: int,
    ) -> tuple[LiquidationConnectionState, tuple[str, ...]]:
        if not transport_connected:
            return (
                LiquidationConnectionState.DISCONNECTED,
                ("transport_disconnected",),
            )
        if not subscription_confirmed:
            return (
                LiquidationConnectionState.DISCONNECTED,
                ("subscription_not_confirmed",),
            )
        if last_transport_activity_ms is None:
            return (
                LiquidationConnectionState.DISCONNECTED,
                ("transport_activity_unavailable",),
            )
        age_ms = observed_at_ms - last_transport_activity_ms
        if age_ms > args.max_transport_silence_ms:
            return (
                LiquidationConnectionState.STALE,
                (
                    "subscription_confirmed",
                    "transport_activity_stale",
                ),
            )
        return (
            LiquidationConnectionState.CONNECTED,
            (
                "subscription_confirmed",
                "transport_activity_fresh",
            ),
        )

    async def emit_heartbeat() -> None:
        nonlocal heartbeat_sequence
        observed_at_ms = monotonic_runtime_time(
            last_transport_activity_ms,
            last_ingestion_ms,
        )
        heartbeat_sequence += 1
        heartbeat = build_collector_heartbeat(
            instance_identity=instance.instance_identity,
            sequence_no=heartbeat_sequence,
            observed_at_ms=observed_at_ms,
            last_successful_ingestion_ms=last_ingestion_ms,
            observed_messages_total=last_observed_messages,
            normalized_rows_total=normalized_rows_total,
            raw_rows_total=raw_rows_total,
        )
        await asyncio.to_thread(
            runtime_store.append_heartbeat,
            heartbeat,
        )
        state, reasons = connection_state(observed_at_ms)
        connection = build_liquidation_connection_coverage(
            instance_identity=instance.instance_identity,
            sequence_no=heartbeat_sequence,
            state=state,
            observed_at_ms=observed_at_ms,
            connected_since_ms=(
                connected_since_ms
                if state is not LiquidationConnectionState.DISCONNECTED
                else None
            ),
            last_transport_activity_ms=last_transport_activity_ms,
            last_liquidation_ingestion_ms=last_ingestion_ms,
            symbols=tuple(sorted(symbols)),
            reason_codes=reasons,
        )
        await asyncio.to_thread(connection_store.append, connection)
        print(
            "LIQUIDATION_CONNECTION_COVERAGE "
            f"sequence={heartbeat_sequence} "
            f"state={state.value} "
            f"observed_at_ms={observed_at_ms} "
            f"last_transport_activity_ms={last_transport_activity_ms} "
            f"last_liquidation_ingestion_ms={last_ingestion_ms} "
            "ZERO_EVENT_COVERAGE_INVENTED=NO REAL_CAPITAL=0",
            flush=True,
        )

    async def heartbeat_loop() -> None:
        interval_seconds = args.heartbeat_interval_ms / 1_000
        while not heartbeat_stop.is_set():
            try:
                await asyncio.wait_for(
                    heartbeat_kick.wait(),
                    timeout=interval_seconds,
                )
            except TimeoutError:
                pass
            heartbeat_kick.clear()
            if heartbeat_stop.is_set():
                return
            await emit_heartbeat()

    stream = BybitLinearLiquidationStream(
        url=args.bybit_ws_url,
    )
    await emit_heartbeat()
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        result = await persist_bybit_liquidation_wire_stream(
            store=store,
            raw_store=raw_store,
            batches=stream.stream_wire_batches(
                symbols=symbols,
                transport_event_callback=persist_transport_event,
            ),
            max_messages=(
                None if args.max_messages == 0 else args.max_messages
            ),
            collection_progress_callback=persist_collection_progress,
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        print(
            "LIQUIDATION_COLLECTOR_ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 4
    finally:
        heartbeat_stop.set()
        heartbeat_kick.set()
        try:
            await heartbeat_task
        except (sqlite3.Error, ValueError) as heartbeat_exc:
            print(
                "LIQUIDATION_HEARTBEAT_ERROR "
                f"error={type(heartbeat_exc).__name__}:{heartbeat_exc}",
                file=sys.stderr,
                flush=True,
            )

    counts = store.counts()
    print(
        "LIQUIDATION_COLLECTION_COMPLETE "
        f"observed_messages={result.observed_messages} "
        f"raw_inserted={result.raw_inserted} "
        f"raw_unchanged={result.raw_unchanged} "
        f"liquidation_inserted={result.liquidation_inserted} "
        f"liquidation_unchanged={result.liquidation_unchanged} "
        f"coverage_inserted={result.coverage_inserted} "
        f"coverage_unchanged={result.coverage_unchanged} "
        f"liquidation_total_rows={counts.liquidations} "
        f"coverage_total_rows={counts.liquidation_coverage} "
        f"transport_clock_regressions={transport_clock_regressions} "
        f"ingestion_clock_regressions={ingestion_clock_regressions} "
        f"runtime_quick_check={'YES' if runtime_store.quick_check() else 'NO'} "
        f"connection_quick_check={'YES' if connection_store.quick_check() else 'NO'} "
        "ZERO_EVENT_COVERAGE_INVENTED=NO "
        "PRODUCTION_RUNTIME=YES REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    args = parse_args()
    args.lock_path.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_path.open("a+") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("LIQUIDATION_COLLECTOR_ALREADY_RUNNING", flush=True)
            return 0
        try:
            return asyncio.run(run(args))
        except KeyboardInterrupt:
            print(
                "LIQUIDATION_COLLECTOR_STOPPED_BY_OPERATOR",
                flush=True,
            )
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
