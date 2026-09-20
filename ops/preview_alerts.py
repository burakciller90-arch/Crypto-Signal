#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from crypto_signal.alerts.presentation import preview_outbox

DEFAULT_OUTBOX = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "alerts"
    / "alert_outbox.sqlite3"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--outbox",
        type=Path,
        default=DEFAULT_OUTBOX,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    messages = preview_outbox(
        args.outbox,
        limit=args.limit,
    )
    print(f"ALERT_PREVIEW_COUNT={len(messages)}")
    for index, message in enumerate(messages, start=1):
        print(f"--- ALERT_PREVIEW_{index} ---")
        print(message.title)
        print(message.body)
        print(f"IDEMPOTENCY_KEY={message.idempotency_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
