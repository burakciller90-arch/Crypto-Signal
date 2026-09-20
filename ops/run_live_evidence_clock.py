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
from crypto_signal.ledger.coverage import (
    LiveCoveragePlan,
    LiveCoverageSourceStrategy,
)
from crypto_signal.ledger.live_clock import freeze_live_provider
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerConflictError,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_DB = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
LOCK_PATH = BASE / "runtime" / "ledger" / "live_clock.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="immutable ledger SQLite path",
    )
    return parser.parse_args()


async def run(db_path: Path) -> int:
    ledger = ImmutableSignalLedger(db_path)
    failures = 0
    plan = LiveCoveragePlan.current_pilot()
    adapters: dict[Exchange, MarketDataAdapter] = {
        Exchange.BYBIT: BybitSpotAdapter(),
        Exchange.BINANCE: BinanceSpotAdapter(),
    }

    for context in plan.enabled_contexts:
        name = context.exchange.value
        adapter = adapters[context.exchange]
        try:
            if (
                context.source_strategy
                is not LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
            ):
                raise ValueError(
                    "enabled higher-timeframe live coverage requires "
                    "canonical aggregation implementation"
                )
            result = await freeze_live_provider(
                adapter=adapter,
                ledger=ledger,
                symbol=context.symbol,
                timeframe=context.timeframe,
                limit=context.freeze_limit,
                minimum_closed_candles=context.minimum_closed_candles,
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
        return asyncio.run(run(args.db))


if __name__ == "__main__":
    raise SystemExit(main())
