#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import sqlite3
import sys
import time
from pathlib import Path

from crypto_signal.paper.activation_init import (
    PaperActivationInitError,
    initialize_paper_activation_watermark,
)
from crypto_signal.paper.ledger import PaperLedgerConflictError

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_PAPER_LEDGER = BASE / "runtime" / "paper" / "paper_fund.sqlite3"
DEFAULT_SIGNAL_LEDGER = BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
LOCK_PATH = BASE / "runtime" / "paper" / "paper_activation_init.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ledger", type=Path, default=DEFAULT_PAPER_LEDGER)
    parser.add_argument("--signal-ledger", type=Path, default=DEFAULT_SIGNAL_LEDGER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("PAPER_ACTIVATION_INIT_ALREADY_RUNNING", flush=True)
            return 0
        try:
            result = initialize_paper_activation_watermark(
                paper_ledger_path=args.paper_ledger,
                signal_ledger_path=args.signal_ledger,
                activated_at_ms=time.time_ns() // 1_000_000,
            )
        except (
            OSError,
            PaperActivationInitError,
            PaperLedgerConflictError,
            sqlite3.Error,
            ValueError,
        ) as exc:
            print(
                f"PAPER_ACTIVATION_INIT_ERROR={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            return 1

        activation = result.activation
        print(
            "PAPER_ACTIVATION_INIT_OK "
            f"write={result.disposition.value} "
            f"activation={activation.activation_identity} "
            f"activated_at_ms={activation.activated_at_ms} "
            f"cutoff_ms={activation.activation_cutoff_ms} "
            f"baseline_freezes={result.baseline.freeze_count} "
            f"baseline_latest={result.baseline.latest_signal_freeze_identity or '-'} "
            f"baseline_latest_frozen_at_ms={result.baseline.latest_frozen_at_ms if result.baseline.latest_frozen_at_ms is not None else '-'} "
            "trade_policy=NOT_ACTIVATED "
            "REAL_CAPITAL=0",
            flush=True,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
