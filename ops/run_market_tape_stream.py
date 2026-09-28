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
from crypto_signal.data.market_tape_source_contract import (
    persist_bybit_wire_source_contract,
    persist_open_gap_coverage,
    register_bybit_market_tape_capabilities,
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
from crypto_signal.data.source_contract import SourceContractStore

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
DEFAULT_SOURCE_CONTRACT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/source_contract.sqlite3"
)
DEFAULT_MAX_INGESTION_SILENCE_MS = 60_000
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HEARTBEAT_DB_TIMEOUT_SECONDS = 1.0
HEARTBEAT_DB_RETRY_ATTEMPTS = 3
HEARTBEAT_DB_RETRY_DELAY_SECONDS = 0.25


def _is_transient_sqlite_lock(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def monitor_ingestion_time(
    previous_ms: int | None,
    raw_ingested_at_ms: int,
) -> tuple[int, bool]:
    if raw_ingested_at_ms < 0:
        raise ValueError("raw ingestion time cannot be negative")
    if previous_ms is None or raw_ingested_at_ms >= previous_ms:
        return raw_ingested_at_ms, False
    return previous_ms, True


def _restart_seed_events(
    raw_db: Path,
    *,
    symbols: tuple[str, ...],
    depth: int,
) -> tuple[RawMarketEvent, ...]:
    if not raw_db.is_file():
        return ()
    uri = f"{raw_db.resolve().as_uri()}?mode=ro"
    events: list[RawMarketEvent] = []
    with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        for symbol in symbols:
            for channel in (f"orderbook.{depth}", "publicTrade"):
                row = db.execute(
                    """
                    SELECT event_identity, channel, symbol, event_kind,
                           source_timestamp_ms, event_at_ms, ingested_at_ms,
                           sequence, update_id, payload_json
                    FROM raw_market_events
                    WHERE exchange=? AND channel=? AND symbol=?
                    ORDER BY event_at_ms DESC, sequence DESC, update_id DESC
                    LIMIT 1
                    """,
                    (Exchange.BYBIT.value, channel, symbol),
                ).fetchone()
                if row is None:
                    continue
                events.append(
                    RawMarketEvent(
                        event_identity=str(row["event_identity"]),
                        exchange=Exchange.BYBIT,
                        channel=str(row["channel"]),
                        symbol=str(row["symbol"]),
                        event_kind=str(row["event_kind"]),
                        source_timestamp_ms=int(row["source_timestamp_ms"]),
                        event_at_ms=int(row["event_at_ms"]),
                        ingested_at_ms=int(row["ingested_at_ms"]),
                        sequence=int(row["sequence"]),
                        update_id=int(row["update_id"]),
                        payload_json=str(row["payload_json"]),
                    )
                )
    return tuple(
        sorted(events, key=lambda event: (event.channel, event.symbol))
    )


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
        "--source-contract-db",
        type=Path,
        default=DEFAULT_SOURCE_CONTRACT_DB,
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
        ("source_contract_db", args.source_contract_db),
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
    runtime_store = MarketTapeCollectorRuntimeStore(args.runtime_status_db)
    source_contract_store = SourceContractStore(args.source_contract_db)
    source_capabilities = register_bybit_market_tape_capabilities(
        store=source_contract_store,
        symbols=tuple(sorted(symbols)),
        depth=args.depth,
    )

    previous = runtime_store.latest_instance(
        provider="bybit",
        source="market_tape_stream",
    )
    previous_heartbeat = (
        None
        if previous is None
        else runtime_store.latest_heartbeat(previous.instance_identity)
    )
    if previous_heartbeat is None:
        if not store.quick_check() or not raw_store.quick_check():
            print(
                "MARKET_TAPE_STREAM_ERROR=SQLITE_QUICK_CHECK_FAIL",
                file=sys.stderr,
                flush=True,
            )
            return 3
        baseline_normalized_rows_total = store.counts().total
        baseline_raw_rows_total = raw_store.count()
    else:
        baseline_normalized_rows_total = (
            previous_heartbeat.normalized_rows_total
        )
        baseline_raw_rows_total = previous_heartbeat.raw_rows_total

    gap_ledger = MarketDataGapLedger(args.gap_ledger_db)
    gap_ledger.initialize()
    gap_monitor = IngestionSilenceGapMonitor(
        ledger=gap_ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=args.max_ingestion_silence_ms,
    )
    seed_events = _restart_seed_events(
        args.raw_db,
        symbols=symbols,
        depth=args.depth,
    )
    seed_ingestion_floor_ms: int | None = (
        None
        if previous_heartbeat is None
        else previous_heartbeat.last_successful_ingestion_ms
    )
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
    heartbeat_db_retries = 0
    heartbeat_db_deferrals = 0
    gap_heartbeat_db_deferrals = 0
    source_contract_envelopes_total = 0
    source_contract_coverage_events_total = 0
    source_contract_gap_events_total = 0

    def runtime_now_ms() -> int:
        nonlocal runtime_clock_floor_ms
        runtime_clock_floor_ms = max(
            runtime_clock_floor_ms,
            time.time_ns() // 1_000_000,
            last_ingestion_ms or 0,
        )
        return runtime_clock_floor_ms

    async def emit_heartbeat() -> bool:
        nonlocal heartbeat_sequence
        nonlocal heartbeat_db_retries
        nonlocal heartbeat_db_deferrals
        nonlocal gap_heartbeat_db_deferrals
        nonlocal source_contract_coverage_events_total
        nonlocal source_contract_gap_events_total

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

        persisted = False
        for attempt in range(1, HEARTBEAT_DB_RETRY_ATTEMPTS + 1):
            try:
                await asyncio.to_thread(
                    runtime_store.append_heartbeat,
                    heartbeat,
                    timeout_seconds=HEARTBEAT_DB_TIMEOUT_SECONDS,
                )
                persisted = True
                break
            except sqlite3.OperationalError as exc:
                if not _is_transient_sqlite_lock(exc):
                    raise
                heartbeat_db_retries += 1
                print(
                    "MARKET_TAPE_HEARTBEAT_DB_LOCK "
                    f"sequence={heartbeat.sequence_no} "
                    f"attempt={attempt} "
                    f"error={type(exc).__name__}:{exc}",
                    file=sys.stderr,
                    flush=True,
                )
                if attempt < HEARTBEAT_DB_RETRY_ATTEMPTS:
                    await asyncio.sleep(HEARTBEAT_DB_RETRY_DELAY_SECONDS)

        if not persisted:
            heartbeat_db_deferrals += 1
            print(
                "MARKET_TAPE_HEARTBEAT_DB_DEFERRED "
                f"sequence={heartbeat.sequence_no} "
                f"attempts={HEARTBEAT_DB_RETRY_ATTEMPTS}",
                file=sys.stderr,
                flush=True,
            )
            return False

        try:
            gap_monitor.check_silence(
                observed_at_ms=observed_at_ms,
                source_evidence_identities=(heartbeat.heartbeat_identity,),
            )
            gap_coverage = persist_open_gap_coverage(
                store=source_contract_store,
                capabilities=source_capabilities,
                gaps=gap_ledger.open_gaps(
                    provider="bybit",
                    source="market_tape_stream",
                ),
                observed_at_ms=observed_at_ms,
            )
            source_contract_coverage_events_total += len(gap_coverage)
            source_contract_gap_events_total += len(gap_coverage)
        except sqlite3.OperationalError as exc:
            if not _is_transient_sqlite_lock(exc):
                raise
            gap_heartbeat_db_deferrals += 1
            print(
                "MARKET_TAPE_GAP_HEARTBEAT_DB_DEFERRED "
                f"sequence={heartbeat.sequence_no} "
                f"error={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
        return True

    async def heartbeat_loop() -> None:
        interval_seconds = args.heartbeat_interval_ms / 1_000
        while True:
            try:
                await asyncio.wait_for(
                    heartbeat_stop.wait(),
                    timeout=interval_seconds,
                )
            except TimeoutError:
                await emit_heartbeat()
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
        effective_ingestion_ms, regressed = monitor_ingestion_time(
            last_ingestion_ms,
            raw_event.ingested_at_ms,
        )
        if regressed:
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
        last_ingestion_ms = effective_ingestion_ms
        last_observed_messages = observed_messages
        gap_monitor.observe_persisted_event(
            channel=raw_event.channel,
            symbol=raw_event.symbol,
            ingested_at_ms=effective_ingestion_ms,
            source_evidence_identities=(raw_event.event_identity,),
        )

    def persist_source_contract(
        event: BybitMicrostructureWireEvent,
        raw_event: RawMarketEvent,
        orderbook_normalized_persisted: bool,
    ) -> None:
        nonlocal source_contract_envelopes_total
        nonlocal source_contract_coverage_events_total
        write = persist_bybit_wire_source_contract(
            store=source_contract_store,
            capabilities=source_capabilities,
            wire_event=event,
            raw_event=raw_event,
            orderbook_normalized_persisted=orderbook_normalized_persisted,
            coverage_observed_at_ms=runtime_now_ms(),
        )
        source_contract_envelopes_total += write.envelope_count
        if write.coverage_event is not None:
            source_contract_coverage_events_total += 1

    await emit_heartbeat()
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    stream = BybitSpotMicrostructureStream(
        url=args.bybit_ws_url,
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
            persisted_wire_callback=persist_source_contract,
            collection_progress_callback=persist_collection_progress,
        )
        await emit_heartbeat()
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
        f"heartbeat_db_retries={heartbeat_db_retries} "
        f"heartbeat_db_deferrals={heartbeat_db_deferrals} "
        f"gap_heartbeat_db_deferrals={gap_heartbeat_db_deferrals} "
        f"source_contract_envelopes={source_contract_envelopes_total} "
        f"source_contract_coverage_events={source_contract_coverage_events_total} "
        f"source_contract_gap_events={source_contract_gap_events_total} "
        f"source_contract_quick_check={'YES' if source_contract_store.quick_check() else 'NO'} "
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
