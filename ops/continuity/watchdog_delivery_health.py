"""Read-only classification of rolling wake delivery progress for GitHub watchdog.

This intentionally cannot submit, reset, clear, or regenerate a wake event.
A live heartbeat is not evidence that ChatGPT accepted the pending message.
Compatible with macOS /usr/bin/python3 (3.9).
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Mapping

HEALTHY = "HEALTHY"
PENDING = "PENDING"
STALLED = "STALLED"
WAITING_FOR_RUNTIME = "WAITING_FOR_RUNTIME"
INCONSISTENT = "INCONSISTENT"

STALL_FAILURE_THRESHOLD = 12
STALL_OVERDUE_SECONDS = 120
RUNNING_OVERDUE_GRACE_SECONDS = 60


def _nonnegative_int(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def classify_rolling_delivery(status: Mapping[str, str], now_epoch: int) -> str:
    """Classify progress without changing timer ownership or event identity."""
    state = status.get("state", "")
    interval = _nonnegative_int(status.get("interval_seconds", ""))
    failures = _nonnegative_int(status.get("failure_count", ""))
    next_due = _nonnegative_int(status.get("next_due_epoch", ""))
    pending = status.get("pending_event_id", "")
    if (
        now_epoch < 0
        or interval != 1200
        or failures is None
        or next_due is None
    ):
        return INCONSISTENT
    overdue = now_epoch - next_due

    if state == "RETRYING":
        if not pending:
            return INCONSISTENT
        if failures >= STALL_FAILURE_THRESHOLD and overdue >= STALL_OVERDUE_SECONDS:
            return STALLED
        return PENDING

    if state == "RUNNING":
        if pending:
            # The event can become pending between heartbeat/status reads.
            if failures >= STALL_FAILURE_THRESHOLD and overdue >= STALL_OVERDUE_SECONDS:
                return STALLED
            return PENDING
        if failures or overdue > RUNNING_OVERDUE_GRACE_SECONDS:
            return INCONSISTENT
        return HEALTHY

    if state == "WAITING_FOR_RUNTIME":
        # SSD or script missing: process is alive, delivery is unavailable.
        return WAITING_FOR_RUNTIME
    # A PAUSED timer without an explicit pause latch (checked by workflow)
    # and unknown states must not be called healthy.
    return INCONSISTENT


def parse_status(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in content.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in result:
            result[key] = value.strip()
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("USAGE: watchdog_delivery_health.py status_file now_epoch", file=sys.stderr)
        return 64
    try:
        content = Path(args[0]).read_text()
        now = int(args[1])
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"DELIVERY_STATE_ERROR={type(exc).__name__}", file=sys.stderr)
        return 66
    print(classify_rolling_delivery(parse_status(content), now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
