#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import sys
from pathlib import Path

from crypto_signal.alerts.clock import (
    AlertClockSourceError,
    materialize_alert_events,
)
from crypto_signal.alerts.delivery import LocalNoopSink, dispatch_pending
from crypto_signal.alerts.store import AlertOutbox, AlertOutboxConflictError

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
DEFAULT_SIGNAL_LEDGER = (
    BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
)
DEFAULT_ALERT_OUTBOX = (
    BASE / "runtime" / "alerts" / "alert_outbox.sqlite3"
)
LOCK_PATH = BASE / "runtime" / "alerts" / "alert_clock.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--signal-ledger",
        type=Path,
        default=DEFAULT_SIGNAL_LEDGER,
    )
    parser.add_argument(
        "--outbox",
        type=Path,
        default=DEFAULT_ALERT_OUTBOX,
    )
    parser.add_argument(
        "--dispatch-local-noop",
        action="store_true",
        help=(
            "acceptance-only local sink; performs no external delivery"
        ),
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
            print("ALERT_CLOCK_ALREADY_RUNNING", flush=True)
            return 0

        outbox = AlertOutbox(args.outbox)
        try:
            result = materialize_alert_events(
                args.signal_ledger,
                outbox,
            )
        except (
            AlertClockSourceError,
            AlertOutboxConflictError,
            OSError,
            ValueError,
        ) as exc:
            print(
                f"ALERT_CLOCK_ERROR={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            return 1

        print(
            "ALERT_CLOCK_MATERIALIZED "
            f"signals={result.signal_rows} "
            f"lifecycle={result.lifecycle_rows} "
            f"eligible={result.eligible_events} "
            f"inserted={result.inserted_events} "
            f"unchanged={result.unchanged_events}",
            flush=True,
        )

        if args.dispatch_local_noop:
            sink = LocalNoopSink()
            attempts = dispatch_pending(outbox, sink)
            print(
                "ALERT_CLOCK_LOCAL_NOOP "
                f"attempts={len(attempts)} "
                f"unique={sink.unique_delivery_count}",
                flush=True,
            )

        print(
            "ALERT_CLOCK_OUTBOX "
            f"events={outbox.count_events()} "
            f"attempts={outbox.count_attempts()}",
            flush=True,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
