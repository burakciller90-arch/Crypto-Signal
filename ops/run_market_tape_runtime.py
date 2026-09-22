from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotMicrostructureStream,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_hotcold import (
    DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
    MarketTapeHotColdDecision,
    MarketTapeHotColdPolicy,
    evaluate_archive_headroom,
    measure_hotcold_capacity,
)
from crypto_signal.data.market_tape_wire_collection import (
    MarketTapeWireCollectionResult,
    persist_bybit_wire_stream,
)
from crypto_signal.data.raw_market_tape import RawMarketTapeStore

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
VOLUME = Path("/Volumes/Crypto-504")
STABLE = ROOT / "MarketTape"
TAPE_DIR = ROOT / "Development/runtime/market_tape"
COLD_DIR = ROOT / "MarketTapeCold"
COLD_PYTHON = ROOT / "RuntimeEnvs/market-tape-cold/bin/python"
COLD_ARCHIVER = STABLE / "ops/market_tape/archive_hot_to_parquet.py"
DB = TAPE_DIR / "market_tape.sqlite3"
RAW_DB = TAPE_DIR / "raw_market_tape.sqlite3"
LOCK = TAPE_DIR / "market_tape_stream.lock"
STATUS = TAPE_DIR / "runtime_status.json"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
RUNTIME_HEARTBEAT_SECONDS = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--depth", type=int, default=50)
    parser.add_argument(
        "--orderbook-snapshot-interval-ms",
        type=int,
        default=1_000,
    )
    parser.add_argument("--chunk-messages", type=int, default=100_000)
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="0 means continuous; positive values are bounded acceptance runs",
    )
    return parser.parse_args()


async def _collection_heartbeat(
    payload: dict[str, object],
) -> None:
    while True:
        await asyncio.sleep(RUNTIME_HEARTBEAT_SECONDS)
        _write_status(
            {
                **payload,
                "state": "collecting_chunk",
                "process_pid": os.getpid(),
                "heartbeat": True,
            }
        )


async def _collect_chunk(
    *,
    symbols: tuple[str, ...],
    depth: int,
    snapshot_interval_ms: int,
    chunk_messages: int,
    heartbeat_payload: dict[str, object],
) -> MarketTapeWireCollectionResult:
    store = MarketTapeStore(DB)
    raw_store = RawMarketTapeStore(RAW_DB)
    if not store.quick_check() or not raw_store.quick_check():
        raise RuntimeError("Market Tape quick_check failed before collection")

    stream = BybitSpotMicrostructureStream()
    heartbeat_task = asyncio.create_task(
        _collection_heartbeat(heartbeat_payload)
    )
    try:
        result = await persist_bybit_wire_stream(
            store=store,
            raw_store=raw_store,
            events=stream.stream_wire_events(symbols=symbols, depth=depth),
            orderbook_snapshot_interval_ms=snapshot_interval_ms,
            max_messages=chunk_messages,
        )
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    if not store.quick_check() or not raw_store.quick_check():
        raise RuntimeError("Market Tape quick_check failed after collection")
    return result


def _write_status(payload: dict[str, object]) -> None:
    TAPE_DIR.mkdir(parents=True, exist_ok=True)
    complete = {
        **payload,
        "updated_at_epoch": int(time.time()),
        "real_capital": 0,
    }
    temporary = STATUS.with_suffix(".tmp")
    encoded = (
        json.dumps(complete, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    with temporary.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, STATUS)


def _validate_args(args: argparse.Namespace) -> tuple[str, ...]:
    if not VOLUME.is_dir() or not ROOT.is_dir():
        raise RuntimeError("canonical Crypto-504 SSD root is unavailable")
    if args.depth not in {1, 50, 200, 1000}:
        raise ValueError("Bybit spot orderbook depth must be one of 1,50,200,1000")
    if args.orderbook_snapshot_interval_ms <= 0:
        raise ValueError("snapshot interval must be positive")
    if args.chunk_messages <= 0:
        raise ValueError("chunk messages must be positive")
    if args.max_cycles < 0:
        raise ValueError("max cycles cannot be negative")

    for required in (STABLE / "src/crypto_signal", COLD_PYTHON, COLD_ARCHIVER):
        if not required.exists():
            raise RuntimeError(f"Market Tape runtime dependency missing: {required}")
    if not os.access(COLD_PYTHON, os.X_OK):
        raise RuntimeError("Market Tape cold archive Python is not executable")

    symbols = tuple(dict.fromkeys(str(value).upper() for value in args.symbols))
    if not symbols or any(not value for value in symbols):
        raise ValueError("Market Tape runtime symbols must be non-empty")
    return symbols


def _install_signal_handlers() -> None:
    def stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def _capacity_payload(
    *,
    policy: MarketTapeHotColdPolicy,
) -> tuple[dict[str, object], MarketTapeHotColdDecision]:
    snapshot = measure_hotcold_capacity(
        hot_dir=TAPE_DIR,
        cold_dir=COLD_DIR,
        volume_path=VOLUME,
        policy=policy,
    )
    return (
        {
            "hot_bytes": snapshot.hot_bytes,
            "cold_bytes": snapshot.cold_bytes,
            "tape_bytes": snapshot.hot_bytes + snapshot.cold_bytes,
            "free_bytes": snapshot.free_bytes,
            "capacity_decision": snapshot.decision.value,
        },
        snapshot.decision,
    )


def _run_cold_archive() -> dict[str, object]:
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": "/Users/crypto-signal-agent",
            "PYTHONPATH": str(STABLE / "src"),
        }
    )
    completed = subprocess.run(
        [
            str(COLD_PYTHON),
            str(COLD_ARCHIVER),
            "--hot-dir",
            str(TAPE_DIR),
            "--cold-dir",
            str(COLD_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
        env=environment,
    )
    if completed.stdout:
        print(completed.stdout, end="", flush=True)
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr, flush=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"cold archive process failed with rc={completed.returncode}"
        )

    prefix = "MARKET_TAPE_COLD_ARCHIVE_RESULT="
    line = next(
        (
            value
            for value in completed.stdout.splitlines()
            if value.startswith(prefix)
        ),
        None,
    )
    if line is None:
        raise RuntimeError("cold archive result marker missing")
    payload = json.loads(line.removeprefix(prefix))
    if not isinstance(payload, dict):
        raise TypeError("cold archive result must be a JSON object")
    if int(payload.get("real_capital", -1)) != 0:
        raise ValueError("cold archive real-capital boundary mismatch")
    return {str(key): value for key, value in payload.items()}


def _archive_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"cold archive {key} must be an integer")
    return value


def _archive_partition_count(payload: dict[str, object]) -> int:
    value = payload.get("partitions", [])
    if not isinstance(value, list):
        raise TypeError("cold archive partitions must be a list")
    return len(value)


def _guard_or_none(
    *,
    policy: MarketTapeHotColdPolicy,
) -> tuple[dict[str, object], MarketTapeHotColdDecision | None]:
    snapshot = measure_hotcold_capacity(
        hot_dir=TAPE_DIR,
        cold_dir=COLD_DIR,
        volume_path=VOLUME,
        policy=policy,
    )
    payload: dict[str, object] = {
        "hot_bytes": snapshot.hot_bytes,
        "cold_bytes": snapshot.cold_bytes,
        "tape_bytes": snapshot.hot_bytes + snapshot.cold_bytes,
        "free_bytes": snapshot.free_bytes,
        "capacity_decision": snapshot.decision.value,
    }
    if not snapshot.can_collect:
        return payload, snapshot.decision

    archive_decision = evaluate_archive_headroom(
        snapshot=snapshot,
        policy=policy,
    )
    payload["archive_headroom_decision"] = archive_decision.value
    if archive_decision is not MarketTapeHotColdDecision.COLLECT:
        return payload, archive_decision
    return payload, None


def main() -> int:
    args = parse_args()
    _install_signal_handlers()

    try:
        symbols = _validate_args(args)
    except (RuntimeError, ValueError) as exc:
        print(
            f"MARKET_TAPE_RUNTIME_STARTUP_BLOCKED error={exc}",
            file=sys.stderr,
        )
        return 75

    policy = DEFAULT_MARKET_TAPE_HOTCOLD_POLICY
    TAPE_DIR.mkdir(parents=True, exist_ok=True)
    COLD_DIR.mkdir(parents=True, exist_ok=True)

    with LOCK.open("a+") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("MARKET_TAPE_RUNTIME_ALREADY_RUNNING", flush=True)
            return 0

        cycles = 0
        try:
            while True:
                capacity, guard = _guard_or_none(policy=policy)
                if guard is not None:
                    _write_status(
                        {
                            "state": "guarded",
                            "decision": guard.value,
                            **capacity,
                        }
                    )
                    print(
                        "MARKET_TAPE_RUNTIME_GUARDED "
                        f"decision={guard.value} "
                        f"hot_bytes={capacity['hot_bytes']} "
                        f"cold_bytes={capacity['cold_bytes']} "
                        f"free_bytes={capacity['free_bytes']} "
                        "REAL_CAPITAL=0",
                        flush=True,
                    )
                    if args.max_cycles:
                        return 3
                    time.sleep(300)
                    continue

                try:
                    archive = _run_cold_archive()
                except (
                    json.JSONDecodeError,
                    OSError,
                    subprocess.SubprocessError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                ) as exc:
                    _write_status(
                        {
                            "state": "archive_error",
                            "error": f"{type(exc).__name__}:{exc}",
                            **capacity,
                        }
                    )
                    print(
                        "MARKET_TAPE_RUNTIME_ARCHIVE_ERROR "
                        f"error={type(exc).__name__}:{exc} REAL_CAPITAL=0",
                        file=sys.stderr,
                        flush=True,
                    )
                    if args.max_cycles:
                        return 6
                    time.sleep(300)
                    continue

                post_archive, guard = _guard_or_none(policy=policy)
                if guard is not None:
                    _write_status(
                        {
                            "state": "guarded_after_archive",
                            "decision": guard.value,
                            "archived_rows": _archive_int(archive, "archived_rows"),
                            "pruned_rows": _archive_int(archive, "pruned_rows"),
                            **post_archive,
                        }
                    )
                    if args.max_cycles:
                        return 3
                    time.sleep(300)
                    continue

                _write_status(
                    {
                        "state": "collecting_chunk",
                        "cycle": cycles + 1,
                        "process_pid": os.getpid(),
                        "target_messages": args.chunk_messages,
                        "archived_rows": _archive_int(archive, "archived_rows"),
                        "pruned_rows": _archive_int(archive, "pruned_rows"),
                        "archived_partitions": _archive_partition_count(archive),
                        **post_archive,
                    }
                )

                try:
                    result = asyncio.run(
                        _collect_chunk(
                            symbols=symbols,
                            depth=args.depth,
                            snapshot_interval_ms=(
                                args.orderbook_snapshot_interval_ms
                            ),
                            chunk_messages=args.chunk_messages,
                            heartbeat_payload={
                                "cycle": cycles + 1,
                                "target_messages": args.chunk_messages,
                                "archived_rows": _archive_int(
                                    archive,
                                    "archived_rows",
                                ),
                                "pruned_rows": _archive_int(
                                    archive,
                                    "pruned_rows",
                                ),
                                "archived_partitions": (
                                    _archive_partition_count(archive)
                                ),
                                **post_archive,
                            },
                        )
                    )
                except (OSError, sqlite3.Error, TimeoutError, ValueError) as exc:
                    _write_status(
                        {
                            "state": "retryable_error",
                            "error": f"{type(exc).__name__}:{exc}",
                            **post_archive,
                        }
                    )
                    print(
                        "MARKET_TAPE_RUNTIME_RETRYABLE_ERROR "
                        f"error={type(exc).__name__}:{exc} REAL_CAPITAL=0",
                        file=sys.stderr,
                        flush=True,
                    )
                    if args.max_cycles:
                        return 4
                    time.sleep(30)
                    continue

                cycles += 1
                post_collect, decision = _capacity_payload(policy=policy)
                state = (
                    "collecting"
                    if decision is MarketTapeHotColdDecision.COLLECT
                    else "guarded_after_chunk"
                )
                _write_status(
                    {
                        "state": state,
                        "cycle": cycles,
                        "observed_messages": result.observed_messages,
                        "raw_inserted": result.raw_inserted,
                        "raw_unchanged": result.raw_unchanged,
                        "orderbooks_inserted": result.orderbooks_inserted,
                        "orderbooks_unchanged": result.orderbooks_unchanged,
                        "orderbooks_skipped_by_cadence": (
                            result.orderbooks_skipped_by_cadence
                        ),
                        "trades_inserted": result.trades_inserted,
                        "trades_unchanged": result.trades_unchanged,
                        "archived_rows": _archive_int(archive, "archived_rows"),
                        "pruned_rows": _archive_int(archive, "pruned_rows"),
                        "archived_partitions": _archive_partition_count(archive),
                        **post_collect,
                    }
                )
                print(
                    "MARKET_TAPE_RUNTIME_CHUNK_PASS "
                    f"cycle={cycles} "
                    f"observed={result.observed_messages} "
                    f"raw_inserted={result.raw_inserted} "
                    f"orderbooks_inserted={result.orderbooks_inserted} "
                    f"trades_inserted={result.trades_inserted} "
                    f"archived_rows={archive.get('archived_rows', 0)} "
                    f"hot_bytes={post_collect['hot_bytes']} "
                    f"cold_bytes={post_collect['cold_bytes']} "
                    f"free_bytes={post_collect['free_bytes']} "
                    f"decision={decision.value} "
                    "REAL_CAPITAL=0",
                    flush=True,
                )

                if decision is not MarketTapeHotColdDecision.COLLECT:
                    if args.max_cycles:
                        return 3
                    time.sleep(300)
                    continue
                if args.max_cycles and cycles >= args.max_cycles:
                    return 0
        except KeyboardInterrupt:
            capacity, _decision = _capacity_payload(policy=policy)
            _write_status({"state": "stopped", **capacity})
            print("MARKET_TAPE_RUNTIME_STOPPED REAL_CAPITAL=0", flush=True)
            return 0
        except RuntimeError as exc:
            capacity, _decision = _capacity_payload(policy=policy)
            _write_status(
                {
                    "state": "integrity_error",
                    "error": f"{type(exc).__name__}:{exc}",
                    **capacity,
                }
            )
            print(
                f"MARKET_TAPE_RUNTIME_INTEGRITY_ERROR error={exc}",
                file=sys.stderr,
                flush=True,
            )
            return 5


if __name__ == "__main__":
    raise SystemExit(main())
