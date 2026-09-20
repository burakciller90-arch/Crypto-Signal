#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import sqlite3
import sys
import time
from pathlib import Path

from crypto_signal.paper.ledger import PaperLedgerConflictError
from crypto_signal.paper.runtime import PaperRuntimeError, run_paper_runtime_tick

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_SIGNAL_LEDGER = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
LOCK_PATH = BASE / "runtime" / "paper" / "paper_clock.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paper-ledger",
        type=Path,
        default=DEFAULT_PAPER_LEDGER,
    )
    parser.add_argument(
        "--signal-ledger",
        type=Path,
        default=DEFAULT_SIGNAL_LEDGER,
    )
    return parser.parse_args()


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
            print("PAPER_CLOCK_ALREADY_RUNNING", flush=True)
            return 0

        try:
            snapshot = run_paper_runtime_tick(
                paper_ledger_path=args.paper_ledger,
                signal_ledger_path=args.signal_ledger,
                created_at_ms=time.time_ns() // 1_000_000,
            )
        except (
            OSError,
            PaperLedgerConflictError,
            PaperRuntimeError,
            sqlite3.Error,
            ValueError,
        ) as exc:
            print(
                f"PAPER_CLOCK_ERROR={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            return 1

        observation = snapshot.signal_observation
        print(
            "PAPER_CLOCK_OK "
            f"bootstrap={snapshot.bootstrap_status.value} "
            f"fund={snapshot.fund_state.fund_identity} "
            f"records={snapshot.fund_state.replayed_record_count} "
            f"cash={snapshot.fund_state.cash_usdt} "
            f"positions={len(snapshot.fund_state.positions)} "
            f"signal_freezes={observation.freeze_count} "
            f"lifecycle={observation.lifecycle_count} "
            f"outcomes={observation.outcome_count} "
            f"latest_signal={observation.latest_signal_freeze_identity or '-'} "
            f"latest_state={observation.latest_signal_state or '-'} "
            f"latest_symbol={observation.latest_symbol or '-'} "
            "trade_policy=NOT_ACTIVATED "
            "REAL_CAPITAL=0",
            flush=True,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
