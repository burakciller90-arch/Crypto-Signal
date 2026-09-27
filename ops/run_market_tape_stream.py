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

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitMicrostructureWireEvent,
    BybitSpotMicrostructureStream,
)
from crypto_signal.data.market_data_gap_ledger import (
    IngestionSilenceGapMonitor,
    MarketDataGapLedger,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collector_runtime import (
    MarketTapeCollectorRuntimeStore,
    build_collector_heartbeat,
    build_collector_instance,
)
from crypto_signal.data.market_tape_wire_collection import (
    MarketTapeWireCollectionResult,
    persist_bybit_wire_stream,
)
from crypto_signal.data.models import Exchange
from crypto_signal.data.raw_market_tape import (
    RawMarketEvent,
    RawMarketTapeStore,
)

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
    "market_tape/market_tape_stream.lock"
)
DEFAULT_RUNTIME_STATUS_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/collector_runtime.sqlite3"
)
DEFAULT_GAP_LEDGER_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_data_gaps.sqlite3"
)
DEFAULT_MAX_INGESTION_SILENCE_MS = 60_000
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


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
    parser.add_argument(
        "--gap-ledger-db",
        type=Path,
        default=DEFAULT_GAP_LEDGER_DB,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
    )
    parser.add_argument(
        "--bybit-ws-url",
        default=None,
        help=(
            "explicit Bybit public spot WebSocket URL for the deployment "
            "region; defaults to the adapter global endpoint"
        ),
    )
    parser.add_argument("--depth", type=int, default=50)
    parser.add_argument(
        "--orderbook-snapshot-interval-ms",
        type=int,
        default=1_000,
    )
    parser.add_argument(
        "--heartbeat-interval-ms",
        type=int,
        default=10_000,
    )
    parser.add_argument(
        "--max-ingestion-silence-ms",
        type=int,
        default=DEFAULT_MAX_INGESTION_SILENCE_MS,
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="0 means run continuously; otherwise bounds wire messages",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    for label, path in (
        ("db", args.db),
        ("raw_db", args.raw_db),
        ("runtime_status_db", args.runtime_status_db),
        ("gap_ledger_db", args.gap_ledger_db),
    ):
        if not str(path).startswith("/Volumes/Crypto-504/"):
            print(
                "MARKET_TAPE_STREAM_ERROR=NON_CANONICAL_DB_PATH "
                f"field={label}",
                file=sys.stderr,
                flush=True,
            )
            return 2

    if args.bybit_ws_url is not None and not str(
        args.bybit_ws_url
    ).startswith("wss://"):
        print(
            "MARKET_TAPE_STREAM_ERROR=INVALID_BYBIT_WS_URL",
            file=sys.stderr,
            flush=True,
        )
        return 2

    if args.max_events < 0:
        print(
            "MARKET_TAPE_STREAM_ERROR=NEGATIVE_MAX_EVENTS",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.orderbook_snapshot_interval_ms <= 0:
        print(
            "MARKET_TAPE_STREAM_ERROR=INVALID_SNAPSHOT_INTERVAL",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.heartbeat_interval_ms <= 0:
        print(
            "MARKET_TAPE_STREAM_ERROR=INVALID_HEARTBEAT_INTERVAL",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.max_ingestion_silence_ms <= 0:
        print(
            "MARKET_TAPE_STREAM_ERROR=INVALID_GAP_SILENCE_POLICY",
            file=sys.stderr,
            flush=True,
        )
        return 2

    symbols = tuple(dict.fromkeys(str(value).upper() for value in args.symbols))
    if not symbols or any(not symbol for symbol in symbols):
        print(
            "MARKET_TAPE_STREAM_ERROR=INVALID_SYMBOLS",
            file=sys.stderr,
            flush=True,
        )
        return 2

    store = MarketTapeStore(args.db)
    raw_store = RawMarketTapeStore(args.raw_db)
    if not store.quick_check() or not raw_store.quick_check():
        print(
            "MARKET_TAPE_STREAM_ERROR=SQLITE_QUICK_CHECK_FAIL",
            file=sys.stderr,
            flush=True,
        )
        return 3
    baseline_normalized_rows_total = store.counts().total
    baseline_raw_rows_total = raw_store.count()

    runtime_store = MarketTapeCollectorRuntimeStore(args.runtime_status_db)
    gap_ledger = MarketDataGapLedger(args.gap_ledger_db)
    gap_ledger.initialize()
    gap_monitor = IngestionSilenceGapMonitor(
        ledger=gap_ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=args.max_ingestion_silence_ms,
    )
    seed_events = raw_store.latest_by_context(exchange=Exchange.BYBIT)
    seed_ingestion_floor_ms: int | None = None
    for raw_event in seed_events:
        gap_monitor.seed_persisted_event(
            channel=raw_event.channel,
            symbol=raw_event.symbol,
            ingested_at_ms=raw_event.ingested_at_ms,
            source_evidence_identities=(raw_event.event_identity,),
        )
        seed_ingestion_floor_ms = max(
            raw_event.ingested_at_ms,
            seed_ingestion_floor_ms or raw_event.ingested_at_ms,
        )

    previous = runtime_store.latest_instance(
        provider="bybit",
        source="market_tape_stream",
    )
    instance = build_collector_instance(
        provider="bybit",
        source="market_tape_stream",
        symbols=tuple(sorted(symbols)),
        started_at_ms=int(time.time() * 1000),
        process_id=os.getpid(),
        runtime_nonce=secrets.token_hex(16),
        previous_instance_identity=(
            None if previous is None else previous.instance_identity
        ),
    )
    runtime_store.append_instance(instance)
    heartbeat_sequence = 0
    last_ingestion_ms: int | None = seed_ingestion_floor_ms
    last_observed_messages = 0
    ingestion_clock_regressions = 0
    runtime_clock_floor_ms = max(
        time.time_ns() // 1_000_000,
        last_ingestion_ms or 0,
    )
    normalized_rows_total = baseline_normalized_rows_total
    raw_rows_total = baseline_raw_rows_total
    heartbeat_stop = asyncio.Event()

    def runtime_now_ms() -> int:
        nonlocal runtime_clock_floor_ms
        runtime_clock_floor_ms = max(
            runtime_clock_floor_ms,
            time.time_ns() // 1_000_000,
            last_ingestion_ms or 0,
        )
        return runtime_clock_floor_ms

    def emit_heartbeat() -> None:
        nonlocal heartbeat_sequence
        observed_at_ms = runtime_now_ms()
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
        runtime_store.append_heartbeat(heartbeat)
        gap_monitor.check_silence(
            observed_at_ms=observed_at_ms,
            source_evidence_identities=(heartbeat.heartbeat_identity,),
        )

    async def heartbeat_loop() -> None:
        interval_seconds = args.heartbeat_interval_ms / 1_000
        while True:
            try:
                await asyncio.wait_for(
                    heartbeat_stop.wait(),
                    timeout=interval_seconds,
                )
            except TimeoutError:
                emit_heartbeat()
                continue
            return

    def persist_collection_progress(
        progress: MarketTapeWireCollectionResult,
    ) -> None:
        nonlocal normalized_rows_total
        nonlocal raw_rows_total
        normalized_rows_total = (
            baseline_normalized_rows_total
            + progress.normalized_inserted_total
        )
        raw_rows_total = baseline_raw_rows_total + progress.raw_inserted

    def persist_progress(
        event: BybitMicrostructureWireEvent,
        observed_messages: int,
    ) -> None:
        nonlocal last_observed_messages
        last_observed_messages = observed_messages

    def persist_raw_event(
        raw_event: RawMarketEvent,
        observed_messages: int,
    ) -> None:
        nonlocal last_ingestion_ms
        nonlocal last_observed_messages
        nonlocal ingestion_clock_regressions
        effective_ingestion_ms = raw_event.ingested_at_ms
        if (
            last_ingestion_ms is not None
            and effective_ingestion_ms < last_ingestion_ms
        ):
            ingestion_clock_regressions += 1
            print(
                "MARKET_TAPE_INGESTION_CLOCK_REGRESSION "
                f"raw_ingested_at_ms={raw_event.ingested_at_ms} "
                f"monitor_floor_ms={last_ingestion_ms} "
                f"channel={raw_event.channel} "
                f"symbol={raw_event.symbol} "
                "RAW_EVENT_PRESERVED=YES",
                file=sys.stderr,
                flush=True,
            )
            effective_ingestion_ms = last_ingestion_ms
        last_ingestion_ms = effective_ingestion_ms
        last_observed_messages = observed_messages
        gap_monitor.observe_persisted_event(
            channel=raw_event.channel,
            symbol=raw_event.symbol,
            ingested_at_ms=effective_ingestion_ms,
            source_evidence_identities=(raw_event.event_identity,),
        )

    emit_heartbeat()
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    stream = BybitSpotMicrostructureStream(
        url=args.bybit_ws_url,
        proxy=None,
    )
    try:
        result = await persist_bybit_wire_stream(
            store=store,
            raw_store=raw_store,
            events=stream.stream_wire_events(
                symbols=symbols,
                depth=args.depth,
            ),
            orderbook_snapshot_interval_ms=(
                args.orderbook_snapshot_interval_ms
            ),
            max_messages=(None if args.max_events == 0 else args.max_events),
            progress_callback=persist_progress,
            persisted_event_callback=persist_raw_event,
            collection_progress_callback=persist_collection_progress,
        )
        emit_heartbeat()
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(
            "MARKET_TAPE_STREAM_ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 4
    finally:
        heartbeat_stop.set()
        await heartbeat_task

    counts = store.counts()
    print(
        "MARKET_TAPE_STREAM_COMPLETE "
        f"observed_messages={result.observed_messages} "
        f"raw_inserted={result.raw_inserted} "
        f"raw_unchanged={result.raw_unchanged} "
        f"orderbooks_inserted={result.orderbooks_inserted} "
        f"orderbooks_unchanged={result.orderbooks_unchanged} "
        f"orderbooks_skipped_by_cadence={result.orderbooks_skipped_by_cadence} "
        f"trades_inserted={result.trades_inserted} "
        f"trades_unchanged={result.trades_unchanged} "
        f"normalized_total_rows={counts.total} "
        f"raw_total_rows={raw_store.count()} "
        f"latest_event_at_ms={store.latest_event_at_ms() or '-'} "
        f"raw_latest_event_at_ms={raw_store.latest_event_at_ms() or '-'} "
        f"normalized_quick_check={'YES' if store.quick_check() else 'NO'} "
        f"raw_quick_check={'YES' if raw_store.quick_check() else 'NO'} "
        f"collector_instance={instance.instance_identity} "
        f"collector_start_kind={instance.start_kind.value} "
        f"collector_heartbeat_seq={heartbeat_sequence} "
        f"collector_runtime_quick_check={'YES' if runtime_store.quick_check() else 'NO'} "
        f"gap_ledger_events={len(gap_ledger.events())} "
        f"gap_ledger_quick_check={'YES' if gap_ledger.quick_check() else 'NO'} "
        f"gap_silence_policy_ms={args.max_ingestion_silence_ms} "
        f"ingestion_clock_regressions={ingestion_clock_regressions} "
        "REAL_CAPITAL=0",
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
            print("MARKET_TAPE_STREAM_ALREADY_RUNNING", flush=True)
            return 0
        try:
            return asyncio.run(run(args))
        except KeyboardInterrupt:
            print("MARKET_TAPE_STREAM_STOPPED_BY_OPERATOR", flush=True)
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
