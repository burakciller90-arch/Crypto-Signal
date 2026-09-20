#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

import httpx

from crypto_signal.data.adapters.base import MarketDataAdapter
from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter
from crypto_signal.data.models import Exchange
from crypto_signal.data.store import CandleStore
from crypto_signal.ledger.coverage import (
    LiveCoveragePlan,
)
from crypto_signal.ledger.live_coverage import freeze_coverage_context
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerConflictError,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_DB = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"
LOCK_PATH = BASE / "runtime" / "ledger" / "live_clock.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="immutable ledger SQLite path",
    )
    parser.add_argument(
        "--candle-cache",
        type=Path,
        default=DEFAULT_CANDLE_CACHE,
        help="canonical 15m cache used for higher-timeframe preparation",
    )
    return parser.parse_args()


async def run(
    db_path: Path,
    *,
    plan: LiveCoveragePlan | None = None,
    candle_cache_path: Path = DEFAULT_CANDLE_CACHE,
) -> int:
    ledger = ImmutableSignalLedger(db_path)
    candle_store = CandleStore(candle_cache_path)
    failures = 0
    selected_plan = LiveCoveragePlan.current_pilot() if plan is None else plan
    adapters: dict[Exchange, MarketDataAdapter] = {
        Exchange.BYBIT: BybitSpotAdapter(),
        Exchange.BINANCE: BinanceSpotAdapter(),
    }

    for context in selected_plan.enabled_contexts:
        name = context.exchange.value
        adapter = adapters[context.exchange]
        try:
            result = await freeze_coverage_context(
                context=context,
                adapter=adapter,
                ledger=ledger,
                candle_store=candle_store,
            )
        except (
            LedgerConflictError,
            OSError,
            ValueError,
            httpx.HTTPError,
            sqlite3.Error,
        ) as exc:
            failures += 1
            print(
                f"provider={name} symbol={context.symbol} "
                f"timeframe={context.timeframe} status=ERROR "
                f"error={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            continue

        print(
            f"provider={name} symbol={context.symbol} "
            f"timeframe={context.timeframe} status={result.status.value} "
            f"cutoff={result.source_cutoff_open_time_ms} "
            f"signal={result.signal_freeze_identity or '-'} "
            f"bundle={result.bundle_identity or '-'} "
            f"state={result.signal_state.value if result.signal_state else '-'} "
            f"score={result.confluence_score or '-'} "
            f"lifecycle={result.lifecycle_disposition.value if result.lifecycle_disposition else '-'}",
            flush=True,
        )

    return 1 if failures else 0


def main() -> int:
    args = parse_args()
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("LIVE_CLOCK_ALREADY_RUNNING", flush=True)
            return 0
        return asyncio.run(
            run(
                args.db,
                candle_cache_path=args.candle_cache,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
