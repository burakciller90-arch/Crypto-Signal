from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

from crypto_signal.data.adapters.bybit_liquidation_ws import (
    BybitLinearLiquidationStream,
)
from crypto_signal.data.liquidation_wire_collection import (
    persist_bybit_liquidation_wire_stream,
)
from crypto_signal.data.market_tape import MarketTapeStore
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
    "market_tape/liquidation_development_collector.lock"
)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--raw-db", type=Path, default=DEFAULT_RAW_DB)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--max-messages",
        type=int,
        default=0,
        help=(
            "Required positive bound for development collection. "
            "Continuous collection is deliberately unsupported in this slice."
        ),
    )
    parser.add_argument(
        "--enable-development-collector",
        action="store_true",
        help=(
            "Explicit development-only enable latch. This does not grant "
            "production/runtime activation."
        ),
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if not args.enable_development_collector:
        print(
            "LIQUIDATION_COLLECTOR_DISABLED_BY_DEFAULT=YES REAL_CAPITAL=0",
            flush=True,
        )
        return 0
    if args.max_messages <= 0:
        print(
            "LIQUIDATION_COLLECTOR_ERROR=BOUNDED_MAX_MESSAGES_REQUIRED",
            file=sys.stderr,
            flush=True,
        )
        return 2

    for label, path in (("db", args.db), ("raw_db", args.raw_db)):
        if not str(path).startswith("/Volumes/Crypto-504/"):
            print(
                "LIQUIDATION_COLLECTOR_ERROR=NON_CANONICAL_DB_PATH "
                f"field={label}",
                file=sys.stderr,
                flush=True,
            )
            return 2

    symbols = tuple(dict.fromkeys(str(value).upper() for value in args.symbols))
    if not symbols or any(not value for value in symbols):
        print(
            "LIQUIDATION_COLLECTOR_ERROR=INVALID_SYMBOLS",
            file=sys.stderr,
            flush=True,
        )
        return 2

    store = MarketTapeStore(args.db)
    raw_store = RawMarketTapeStore(args.raw_db)
    if not store.quick_check() or not raw_store.quick_check():
        print(
            "LIQUIDATION_COLLECTOR_ERROR=SQLITE_QUICK_CHECK_FAIL",
            file=sys.stderr,
            flush=True,
        )
        return 3

    stream = BybitLinearLiquidationStream()
    try:
        result = await persist_bybit_liquidation_wire_stream(
            store=store,
            raw_store=raw_store,
            batches=stream.stream_wire_batches(symbols=symbols),
            max_messages=args.max_messages,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(
            "LIQUIDATION_COLLECTOR_ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 4

    counts = store.counts()
    print(
        "LIQUIDATION_DEVELOPMENT_COLLECTION_COMPLETE "
        f"observed_messages={result.observed_messages} "
        f"raw_inserted={result.raw_inserted} "
        f"raw_unchanged={result.raw_unchanged} "
        f"liquidation_inserted={result.liquidation_inserted} "
        f"liquidation_unchanged={result.liquidation_unchanged} "
        f"coverage_inserted={result.coverage_inserted} "
        f"coverage_unchanged={result.coverage_unchanged} "
        f"normalized_total_rows={counts.total} "
        f"raw_total_rows={raw_store.count()} "
        f"normalized_quick_check={'YES' if store.quick_check() else 'NO'} "
        f"raw_quick_check={'YES' if raw_store.quick_check() else 'NO'} "
        "PRODUCTION_ACTIVATION=NO REAL_CAPITAL=0",
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
            print("LIQUIDATION_DEVELOPMENT_COLLECTOR_ALREADY_RUNNING", flush=True)
            return 0
        try:
            return asyncio.run(run(args))
        except KeyboardInterrupt:
            print(
                "LIQUIDATION_DEVELOPMENT_COLLECTOR_STOPPED_BY_OPERATOR",
                flush=True,
            )
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
