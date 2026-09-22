#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotMicrostructureStream,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collection import persist_market_tape_stream

DEFAULT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape.sqlite3"
)
DEFAULT_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape_stream.lock"
)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
    )
    parser.add_argument("--depth", type=int, default=50)
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="0 means run continuously",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if not str(args.db).startswith("/Volumes/Crypto-504/"):
        print(
            "MARKET_TAPE_STREAM_ERROR=NON_CANONICAL_DB_PATH",
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

    symbols = tuple(str(value).upper() for value in args.symbols)
    store = MarketTapeStore(args.db)
    if not store.quick_check():
        print(
            "MARKET_TAPE_STREAM_ERROR=SQLITE_QUICK_CHECK_FAIL",
            file=sys.stderr,
            flush=True,
        )
        return 3

    stream = BybitSpotMicrostructureStream()
    try:
        result = await persist_market_tape_stream(
            store=store,
            events=stream.stream_events(
                symbols=symbols,
                depth=args.depth,
            ),
            max_events=(None if args.max_events == 0 else args.max_events),
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(
            "MARKET_TAPE_STREAM_ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 4

    counts = store.counts()
    print(
        "MARKET_TAPE_STREAM_COMPLETE "
        f"observed_events={result.observed_events} "
        f"orderbooks_inserted={result.orderbooks_inserted} "
        f"orderbooks_unchanged={result.orderbooks_unchanged} "
        f"trades_inserted={result.trades_inserted} "
        f"trades_unchanged={result.trades_unchanged} "
        f"total_rows={counts.total} "
        f"latest_event_at_ms={store.latest_event_at_ms() or '-'} "
        f"quick_check={'YES' if store.quick_check() else 'NO'} "
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
