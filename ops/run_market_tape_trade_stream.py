#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotPublicTradeStream,
)
from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)

DEFAULT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape.sqlite3"
)
DEFAULT_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape_trade_stream.lock"
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
    parser.add_argument("--log-every", type=int, default=250)
    return parser.parse_args()


async def run_symbol(
    *,
    store: MarketTapeStore,
    symbol: str,
    log_every: int,
) -> None:
    stream = BybitSpotPublicTradeStream()
    seen = 0
    inserted = 0
    unchanged = 0

    async for trade in stream.stream_trades(symbol=symbol):
        disposition = store.append_trade(trade)
        seen += 1
        if disposition is MarketTapeWriteDisposition.INSERTED:
            inserted += 1
        else:
            unchanged += 1

        if seen % log_every == 0:
            print(
                "MARKET_TAPE_TRADE_STREAM_PROGRESS "
                f"symbol={symbol} "
                f"seen={seen} "
                f"inserted={inserted} "
                f"unchanged={unchanged} "
                f"latest_event_at_ms={store.latest_event_at_ms() or '-'} "
                "REAL_CAPITAL=0",
                flush=True,
            )


async def run(args: argparse.Namespace) -> int:
    if not str(args.db).startswith("/Volumes/Crypto-504/"):
        print(
            "MARKET_TAPE_ERROR=NON_CANONICAL_DB_PATH",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.log_every <= 0:
        print(
            "MARKET_TAPE_ERROR=INVALID_LOG_EVERY",
            file=sys.stderr,
            flush=True,
        )
        return 2

    symbols = tuple(dict.fromkeys(str(value).upper() for value in args.symbols))
    if not symbols or any(not symbol for symbol in symbols):
        print(
            "MARKET_TAPE_ERROR=INVALID_SYMBOLS",
            file=sys.stderr,
            flush=True,
        )
        return 2

    store = MarketTapeStore(args.db)
    store.initialize()
    if not store.quick_check():
        print(
            "MARKET_TAPE_ERROR=SQLITE_QUICK_CHECK_FAIL",
            file=sys.stderr,
            flush=True,
        )
        return 3

    print(
        "MARKET_TAPE_TRADE_STREAM_START "
        f"symbols={','.join(symbols)} "
        f"db={args.db} "
        "source=BYBIT_SPOT_PUBLIC_TRADE_WS "
        "REAL_CAPITAL=0",
        flush=True,
    )

    try:
        async with asyncio.TaskGroup() as group:
            for symbol in symbols:
                group.create_task(
                    run_symbol(
                        store=store,
                        symbol=symbol,
                        log_every=args.log_every,
                    )
                )
    except* (OSError, sqlite3.Error, ValueError) as group_error:
        print(
            "MARKET_TAPE_TRADE_STREAM_ERROR "
            f"errors={len(group_error.exceptions)} "
            "REAL_CAPITAL=0",
            file=sys.stderr,
            flush=True,
        )
        return 4

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
            print("MARKET_TAPE_TRADE_STREAM_ALREADY_RUNNING", flush=True)
            return 0
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
