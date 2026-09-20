#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.portfolio import (
    PaperPortfolioError,
    read_paper_portfolio_snapshot,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--candle-cache", type=Path, default=DEFAULT_CANDLE_CACHE)
    parser.add_argument("--observed-at-ms", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_PORTFOLIO_ERROR=REAL_CAPITAL", file=sys.stderr, flush=True)
        return 1
    observed_at_ms = (
        time.time_ns() // 1_000_000
        if args.observed_at_ms is None
        else args.observed_at_ms
    )
    try:
        snapshot = read_paper_portfolio_snapshot(
            paper_ledger_path=args.paper_ledger,
            candle_cache_path=args.candle_cache,
            observed_at_ms=observed_at_ms,
        )
    except (OSError, PaperPortfolioError, ValueError) as exc:
        print(
            f"PAPER_PORTFOLIO_ERROR={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    for position in snapshot.positions:
        mark = position.mark
        print(
            "PAPER_PORTFOLIO_POSITION "
            f"symbol={position.symbol.value} "
            f"quantity={position.quantity} "
            f"mark={'-' if mark is None else mark.price} "
            f"mark_identity={'-' if mark is None else mark.mark_identity} "
            f"mark_candle_close_ms={'-' if mark is None else mark.source_candle_close_time_ms} "
            f"marked_value_usdt={'-' if position.marked_value_usdt is None else position.marked_value_usdt} "
            "REAL_CAPITAL=0",
            flush=True,
        )

    missing = (
        "-"
        if not snapshot.missing_mark_symbols
        else ",".join(item.value for item in snapshot.missing_mark_symbols)
    )
    print(
        "PAPER_PORTFOLIO_OK "
        f"snapshot={snapshot.snapshot_identity} "
        f"observed_at_ms={snapshot.observed_at_ms} "
        f"availability={snapshot.availability.value} "
        f"cash_usdt={snapshot.cash_usdt} "
        f"positions={len(snapshot.positions)} "
        f"missing_marks={missing} "
        f"marked_positions_value_usdt={'-' if snapshot.marked_positions_value_usdt is None else snapshot.marked_positions_value_usdt} "
        f"nav_usdt={'-' if snapshot.nav_usdt is None else snapshot.nav_usdt} "
        f"pnl_usdt={'-' if snapshot.pnl_usdt is None else snapshot.pnl_usdt} "
        f"total_return_fraction={'-' if snapshot.total_return_fraction is None else snapshot.total_return_fraction} "
        f"decisions={snapshot.decision_count} "
        f"fills={snapshot.simulated_fill_count} "
        f"nav_records={snapshot.nav_snapshot_count} "
        f"replayed_records={snapshot.replayed_record_count} "
        "trade_success=NOT_YET_MEASURED "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
