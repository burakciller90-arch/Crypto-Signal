from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

import httpx

from crypto_signal.data.adapters.bybit_derivatives import (
    BybitLinearDerivativesAdapter,
)
from crypto_signal.data.adapters.bybit_microstructure import (
    BybitSpotMicrostructureAdapter,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_collection import (
    collect_bybit_market_tape_snapshot,
)

DEFAULT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape.sqlite3"
)
DEFAULT_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape_snapshot.lock"
)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--bybit-base-url",
        default="https://api.bybit.tr",
        help="explicit regional Bybit REST base URL",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
    )
    parser.add_argument("--book-depth", type=int, default=50)
    parser.add_argument("--trade-limit", type=int, default=60)
    parser.add_argument("--oi-interval", default="15min")
    parser.add_argument("--oi-limit", type=int, default=16)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if not str(args.db).startswith("/Volumes/Crypto-504/"):
        print(
            "MARKET_TAPE_ERROR=NON_CANONICAL_DB_PATH",
            file=sys.stderr,
            flush=True,
        )
        return 2

    store = MarketTapeStore(args.db)
    failures = 0
    if not str(args.bybit_base_url).startswith("https://"):
        print(
            "MARKET_TAPE_ERROR=INVALID_BYBIT_REST_URL",
            file=sys.stderr,
            flush=True,
        )
        return 2

    microstructure = BybitSpotMicrostructureAdapter(
        base_url=args.bybit_base_url,
    )
    derivatives = BybitLinearDerivativesAdapter(
        base_url=args.bybit_base_url,
    )
    cycle_orderbook_inserted = 0
    cycle_trade_inserted = 0
    cycle_trade_unchanged = 0
    cycle_derivatives_inserted = 0
    cycle_derivatives_unchanged = 0
    successful_symbols = 0

    for symbol in tuple(str(value).upper() for value in args.symbols):
        try:
            result = await collect_bybit_market_tape_snapshot(
                store=store,
                microstructure_adapter=microstructure,
                derivatives_adapter=derivatives,
                symbol=symbol,
                book_depth=args.book_depth,
                trade_limit=args.trade_limit,
                oi_interval=args.oi_interval,
                oi_limit=args.oi_limit,
            )
        except (
            httpx.HTTPError,
            sqlite3.Error,
            OSError,
            ValueError,
        ) as exc:
            failures += 1
            print(
                "MARKET_TAPE_SYMBOL_ERROR "
                f"symbol={symbol} "
                f"error={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            continue

        successful_symbols += 1
        cycle_orderbook_inserted += int(
            result.orderbook_disposition.value == "inserted"
        )
        cycle_trade_inserted += result.trade_inserted
        cycle_trade_unchanged += result.trade_unchanged
        cycle_derivatives_inserted += result.derivatives_inserted
        cycle_derivatives_unchanged += result.derivatives_unchanged
        print(
            "MARKET_TAPE_SYMBOL_OK "
            f"symbol={result.symbol} "
            f"orderbook={result.orderbook_disposition.value} "
            f"trades_inserted={result.trade_inserted} "
            f"trades_unchanged={result.trade_unchanged} "
            f"derivatives_inserted={result.derivatives_inserted} "
            f"derivatives_unchanged={result.derivatives_unchanged}",
            flush=True,
        )

    print(
        "MARKET_TAPE_SNAPSHOT_COMPLETE "
        f"successful_symbols={successful_symbols} "
        f"failed_symbols={failures} "
        f"cycle_orderbooks_inserted={cycle_orderbook_inserted} "
        f"cycle_trades_inserted={cycle_trade_inserted} "
        f"cycle_trades_unchanged={cycle_trade_unchanged} "
        f"cycle_derivatives_inserted={cycle_derivatives_inserted} "
        f"cycle_derivatives_unchanged={cycle_derivatives_unchanged} "
        "FULL_DB_INTEGRITY_DELEGATED=YES "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 1 if failures else 0


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
            print("MARKET_TAPE_SNAPSHOT_ALREADY_RUNNING", flush=True)
            return 0
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
