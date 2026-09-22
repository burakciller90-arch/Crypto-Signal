#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import sys
import time
from pathlib import Path

from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.paper.write_authority import PaperWriteAuthorityError
from crypto_signal.paper.write_tick import (
    PaperWriteTickError,
    run_paper_write_tick,
    summarize_write_tick_statuses,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_SIGNAL_LEDGER = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
DEFAULT_CANDLE_CACHE = BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"
LOCK_PATH = BASE / "runtime" / "paper" / "paper_write_tick.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--signal-ledger", type=Path, default=DEFAULT_SIGNAL_LEDGER)
    parser.add_argument("--candle-cache", type=Path, default=DEFAULT_CANDLE_CACHE)
    parser.add_argument("--max-events", type=int, default=10)
    parser.add_argument(
        "--active-learning",
        action="store_true",
        help="also process the bounded 1h exploration lane",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if REAL_CAPITAL != 0:
        print("PAPER_WRITE_TICK_ERROR=REAL_CAPITAL", file=sys.stderr, flush=True)
        return 1
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("PAPER_WRITE_TICK_ALREADY_RUNNING", flush=True)
            return 0
        try:
            result = run_paper_write_tick(
                paper_ledger_path=args.paper_ledger,
                signal_ledger_path=args.signal_ledger,
                candle_cache_path=args.candle_cache,
                evaluated_at_ms=time.time_ns() // 1_000_000,
                max_events=args.max_events,
                include_active_learning=args.active_learning,
            )
            for event in result.event_results:
                print(
                    "PAPER_WRITE_TICK_EVENT "
                    f"event={event.event_identity} "
                    f"status={event.status.value} "
                    f"disposition={event.disposition.value} "
                    f"reason={event.reason_code} "
                    f"records={','.join(event.record_identities) or '-'} "
                    "REAL_CAPITAL=0",
                    flush=True,
                )
            statuses = ",".join(
                f"{name}:{count}"
                for name, count in summarize_write_tick_statuses(result)
            ) or "-"
            print(
                "PAPER_WRITE_TICK_OK "
                f"authority={'-' if result.authority_event_identity is None else result.authority_event_identity} "
                f"enabled={'YES' if result.authority_enabled else 'NO'} "
                f"active_learning={'YES' if args.active_learning else 'NO'} "
                f"candidates={result.scanned_candidate_count} "
                f"processed_skips={result.processed_skip_count} "
                f"terminal_no_action={result.terminal_no_action_count} "
                f"committed_trades={result.committed_trade_count} "
                f"retryable={result.retryable_count} "
                f"statuses={statuses} "
                "REAL_CAPITAL=0",
                flush=True,
            )
            return 0
        except (
            OSError,
            PaperWriteAuthorityError,
            PaperWriteTickError,
            ValueError,
        ) as exc:
            print(
                f"PAPER_WRITE_TICK_ERROR={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
