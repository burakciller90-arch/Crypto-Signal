#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

from crypto_signal.paper.models import REAL_CAPITAL, PaperSymbol
from crypto_signal.paper.venue_rules import (
    PaperVenueRuleError,
    PaperVenueRuleStore,
    fetch_binance_spot_venue_rules,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
LOCK_PATH = BASE / "runtime" / "paper" / "paper_venue_rules.lock"
DEFAULT_SYMBOLS = (
    PaperSymbol.BTCUSDT,
    PaperSymbol.ETHUSDT,
    PaperSymbol.SOLUSDT,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paper-ledger",
        type=Path,
        default=DEFAULT_PAPER_LEDGER,
    )
    return parser.parse_args()


def _assert_no_trade_invariant(path: Path) -> None:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
        expected = {
            "paper_fund_creations": 1,
            "paper_decision_intents": 0,
            "paper_simulated_fills": 0,
            "paper_position_cash_mutations": 0,
            "paper_nav_snapshots": 0,
            "paper_replay_index": 1,
        }
        for table, expected_count in expected.items():
            row = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()
            if row is None or int(row[0]) != expected_count:
                raise RuntimeError(
                    f"paper no-trade invariant failed: {table}={row}"
                )


async def _refresh(path: Path) -> int:
    store = PaperVenueRuleStore(path)
    for symbol in DEFAULT_SYMBOLS:
        snapshot = await fetch_binance_spot_venue_rules(symbol=symbol)
        disposition = store.append(snapshot)
        print(
            "PAPER_VENUE_RULE_REFRESH_OK "
            f"symbol={symbol.value} "
            f"snapshot={snapshot.snapshot_identity} "
            f"observed_at_ms={snapshot.observed_at_ms} "
            f"step={snapshot.quantity_step} "
            f"min_qty={snapshot.min_quantity} "
            f"max_qty={snapshot.max_quantity} "
            f"min_notional={snapshot.min_notional_usdt} "
            f"tick_size={snapshot.tick_size} "
            f"cost_policy={snapshot.cost_policy_version} "
            f"write={disposition.value} "
            "trade_policy=NOT_ACTIVATED "
            "REAL_CAPITAL=0",
            flush=True,
        )
    return 0


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_VENUE_RULE_REFRESH_ERROR=REAL_CAPITAL", file=sys.stderr)
        return 1
    if not args.paper_ledger.exists():
        print(
            "PAPER_VENUE_RULE_REFRESH_ERROR=paper ledger missing",
            file=sys.stderr,
            flush=True,
        )
        return 1

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("PAPER_VENUE_RULE_REFRESH_ALREADY_RUNNING", flush=True)
            return 0

        try:
            _assert_no_trade_invariant(args.paper_ledger)
            result = asyncio.run(_refresh(args.paper_ledger))
            _assert_no_trade_invariant(args.paper_ledger)
            return result
        except (
            OSError,
            PaperVenueRuleError,
            RuntimeError,
            sqlite3.Error,
            ValueError,
        ) as exc:
            print(
                f"PAPER_VENUE_RULE_REFRESH_ERROR={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
