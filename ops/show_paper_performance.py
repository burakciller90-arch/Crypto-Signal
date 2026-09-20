#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.performance import (
    PaperTradePerformanceError,
    read_paper_trade_performance,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--observed-at-ms", type=int)
    return parser.parse_args()


def _render(value: object | None) -> str:
    return "-" if value is None else str(value)


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_PERFORMANCE_ERROR=REAL_CAPITAL", file=sys.stderr, flush=True)
        return 1
    observed_at_ms = (
        time.time_ns() // 1_000_000
        if args.observed_at_ms is None
        else args.observed_at_ms
    )
    try:
        snapshot = read_paper_trade_performance(
            paper_ledger_path=args.paper_ledger,
            observed_at_ms=observed_at_ms,
        )
    except (OSError, PaperTradePerformanceError, ValueError) as exc:
        print(
            f"PAPER_PERFORMANCE_ERROR={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    for trade in snapshot.closed_trades:
        print(
            "PAPER_PERFORMANCE_TRADE "
            f"trade={trade.trade_identity} "
            f"symbol={trade.symbol.value} "
            f"quantity={trade.quantity} "
            f"entry_fill={trade.entry_fill_identity} "
            f"exit_fill={trade.exit_fill_identity} "
            f"entry_price={trade.entry_fill_price} "
            f"exit_price={trade.exit_fill_price} "
            f"net_pnl_usdt={trade.net_pnl_usdt} "
            f"return_fraction={trade.return_fraction} "
            f"execution_cost_usdt={trade.explicit_execution_cost_usdt} "
            f"outcome={trade.outcome.value} "
            "REAL_CAPITAL=0",
            flush=True,
        )

    trade_success = (
        "NOT_YET_MEASURED"
        if snapshot.status.value == "not_yet_measured"
        else "AVAILABLE"
    )
    open_symbols = (
        "-"
        if not snapshot.open_trade_symbols
        else ",".join(item.value for item in snapshot.open_trade_symbols)
    )
    print(
        "PAPER_PERFORMANCE_OK "
        f"snapshot={snapshot.snapshot_identity} "
        f"observed_at_ms={snapshot.observed_at_ms} "
        f"status={snapshot.status.value} "
        f"closed_trades={snapshot.closed_trade_count} "
        f"open_trades={snapshot.open_trade_count} "
        f"open_symbols={open_symbols} "
        f"wins={snapshot.win_count} "
        f"losses={snapshot.loss_count} "
        f"breakevens={snapshot.breakeven_count} "
        f"win_rate_fraction={_render(snapshot.win_rate_fraction)} "
        f"closed_net_pnl_usdt={_render(snapshot.total_closed_trade_net_pnl_usdt)} "
        f"average_trade_pnl_usdt={_render(snapshot.average_closed_trade_net_pnl_usdt)} "
        f"average_trade_return_fraction={_render(snapshot.average_closed_trade_return_fraction)} "
        f"gross_profit_usdt={_render(snapshot.gross_profit_usdt)} "
        f"gross_loss_usdt={_render(snapshot.gross_loss_usdt)} "
        f"profit_factor={_render(snapshot.profit_factor)} "
        f"execution_cost_usdt={_render(snapshot.total_explicit_execution_cost_usdt)} "
        f"trade_success={trade_success} "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
