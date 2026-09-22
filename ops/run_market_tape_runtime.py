#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotMicrostructureStream,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_retention import (
    DEFAULT_MARKET_TAPE_RETENTION_POLICY,
    MarketTapeRetentionPolicy,
    active_generation_bytes,
    enforce_generation_retention,
    list_sealed_generations,
    reclaim_for_capacity,
    seal_active_generation,
)
from crypto_signal.data.market_tape_runtime import (
    DEFAULT_MARKET_TAPE_CAPACITY_POLICY,
    MarketTapeCapacityPolicy,
    measure_market_tape_capacity,
)
from crypto_signal.data.market_tape_wire_collection import (
    persist_bybit_wire_stream,
)
from crypto_signal.data.raw_market_tape import RawMarketTapeStore

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
VOLUME = Path("/Volumes/Crypto-504")
TAPE_DIR = ROOT / "Development/runtime/market_tape"
DB = TAPE_DIR / "market_tape.sqlite3"
RAW_DB = TAPE_DIR / "raw_market_tape.sqlite3"
LOCK = TAPE_DIR / "market_tape_stream.lock"
STATUS = TAPE_DIR / "runtime_status.json"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--depth", type=int, default=50)
    parser.add_argument(
        "--orderbook-snapshot-interval-ms",
        type=int,
        default=1_000,
    )
    parser.add_argument(
        "--chunk-messages",
        type=int,
        default=DEFAULT_MARKET_TAPE_CAPACITY_POLICY.chunk_messages,
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="0 means continuous; positive values are bounded acceptance runs",
    )
    return parser.parse_args()


async def _collect_chunk(
    *,
    symbols: tuple[str, ...],
    depth: int,
    snapshot_interval_ms: int,
    chunk_messages: int,
):
    store = MarketTapeStore(DB)
    raw_store = RawMarketTapeStore(RAW_DB)
    if not store.quick_check() or not raw_store.quick_check():
        raise RuntimeError("Market Tape quick_check failed before collection")

    stream = BybitSpotMicrostructureStream()
    result = await persist_bybit_wire_stream(
        store=store,
        raw_store=raw_store,
        events=stream.stream_wire_events(symbols=symbols, depth=depth),
        orderbook_snapshot_interval_ms=snapshot_interval_ms,
        max_messages=chunk_messages,
    )

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

    symbols = tuple(dict.fromkeys(str(value).upper() for value in args.symbols))
    if not symbols or any(not value for value in symbols):
        raise ValueError("Market Tape runtime symbols must be non-empty")
    return symbols


def _install_signal_handlers() -> None:
    def stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def main() -> int:
    args = parse_args()
    _install_signal_handlers()

    try:
        symbols = _validate_args(args)
    except (RuntimeError, ValueError) as exc:
        print(f"MARKET_TAPE_RUNTIME_STARTUP_BLOCKED error={exc}", file=sys.stderr)
        return 75

    capacity_policy = MarketTapeCapacityPolicy(
        max_tape_bytes=DEFAULT_MARKET_TAPE_CAPACITY_POLICY.max_tape_bytes,
        min_free_bytes=DEFAULT_MARKET_TAPE_CAPACITY_POLICY.min_free_bytes,
        chunk_messages=args.chunk_messages,
        guard_sleep_seconds=(
            DEFAULT_MARKET_TAPE_CAPACITY_POLICY.guard_sleep_seconds
        ),
    )
    retention_policy: MarketTapeRetentionPolicy = (
        DEFAULT_MARKET_TAPE_RETENTION_POLICY
    )

    TAPE_DIR.mkdir(parents=True, exist_ok=True)
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
                removed_by_count = enforce_generation_retention(
                    market_tape_dir=TAPE_DIR,
                    policy=retention_policy,
                )

                active_bytes = active_generation_bytes(TAPE_DIR)
                sealed_id: str | None = None
                if (
                    active_bytes
                    >= retention_policy.active_generation_max_bytes
                ):
                    sealed = seal_active_generation(market_tape_dir=TAPE_DIR)
                    sealed_id = sealed.generation_id
                    removed_by_count = (
                        *removed_by_count,
                        *enforce_generation_retention(
                            market_tape_dir=TAPE_DIR,
                            policy=retention_policy,
                        ),
                    )

                capacity, removed_for_capacity = reclaim_for_capacity(
                    market_tape_dir=TAPE_DIR,
                    volume_path=VOLUME,
                    capacity_policy=capacity_policy,
                    retention_policy=retention_policy,
                )
                if not capacity.can_collect:
                    _write_status(
                        {
                            "state": "guarded",
                            "decision": capacity.decision.value,
                            "tape_bytes": capacity.tape_bytes,
                            "free_bytes": capacity.free_bytes,
                            "active_generation_bytes": active_generation_bytes(
                                TAPE_DIR
                            ),
                            "sealed_generations": len(
                                list_sealed_generations(TAPE_DIR)
                            ),
                            "sealed_generation": sealed_id,
                            "removed_generations": [
                                *removed_by_count,
                                *removed_for_capacity,
                            ],
                        }
                    )
                    print(
                        "MARKET_TAPE_RUNTIME_GUARDED "
                        f"decision={capacity.decision.value} "
                        f"tape_bytes={capacity.tape_bytes} "
                        f"free_bytes={capacity.free_bytes} "
                        "REAL_CAPITAL=0",
                        flush=True,
                    )
                    if args.max_cycles:
                        return 3
                    time.sleep(capacity_policy.guard_sleep_seconds)
                    continue

                try:
                    result = asyncio.run(
                        _collect_chunk(
                            symbols=symbols,
                            depth=args.depth,
                            snapshot_interval_ms=(
                                args.orderbook_snapshot_interval_ms
                            ),
                            chunk_messages=capacity_policy.chunk_messages,
                        )
                    )
                except (OSError, sqlite3.Error, TimeoutError, ValueError) as exc:
                    _write_status(
                        {
                            "state": "retryable_error",
                            "error": f"{type(exc).__name__}:{exc}",
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
                post_capacity = measure_market_tape_capacity(
                    market_tape_dir=TAPE_DIR,
                    volume_path=VOLUME,
                    policy=capacity_policy,
                )
                sealed_count = len(list_sealed_generations(TAPE_DIR))
                _write_status(
                    {
                        "state": "collecting",
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
                        "tape_bytes": post_capacity.tape_bytes,
                        "free_bytes": post_capacity.free_bytes,
                        "capacity_decision": post_capacity.decision.value,
                        "active_generation_bytes": active_generation_bytes(
                            TAPE_DIR
                        ),
                        "sealed_generations": sealed_count,
                        "sealed_generation": sealed_id,
                        "removed_generations": [
                            *removed_by_count,
                            *removed_for_capacity,
                        ],
                    }
                )
                print(
                    "MARKET_TAPE_RUNTIME_CHUNK_PASS "
                    f"cycle={cycles} "
                    f"observed={result.observed_messages} "
                    f"raw_inserted={result.raw_inserted} "
                    f"orderbooks_inserted={result.orderbooks_inserted} "
                    f"trades_inserted={result.trades_inserted} "
                    f"tape_bytes={post_capacity.tape_bytes} "
                    f"free_bytes={post_capacity.free_bytes} "
                    f"sealed={sealed_count} "
                    "REAL_CAPITAL=0",
                    flush=True,
                )

                if args.max_cycles and cycles >= args.max_cycles:
                    return 0
        except KeyboardInterrupt:
            _write_status({"state": "stopped"})
            print("MARKET_TAPE_RUNTIME_STOPPED REAL_CAPITAL=0", flush=True)
            return 0
        except RuntimeError as exc:
            _write_status(
                {
                    "state": "integrity_error",
                    "error": f"{type(exc).__name__}:{exc}",
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
