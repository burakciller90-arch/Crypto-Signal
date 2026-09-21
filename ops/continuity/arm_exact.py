#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
STATE = BASE / "runtime" / "continuity"
SOURCES = STATE / "lease_sources"
ARM = BASE / "ops" / "continuity" / "continuation_arm.sh"


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def main() -> int:
    if len(sys.argv) < 3:
        print("USAGE: arm_exact.py task_id delay_seconds [frontier_note]", file=sys.stderr)
        return 64

    task = sys.argv[1]
    delay = sys.argv[2]
    note = sys.argv[3] if len(sys.argv) >= 4 else ""
    SOURCES.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    safe = subprocess.check_output(
        ["shasum", "-a", "256"],
        input=task,
        text=True,
    ).split()[0][:20]
    source = SOURCES / f"{safe}-{now}.md"
    head = run("git", "-C", str(BASE), "rev-parse", "HEAD")
    status = (BASE / "CURRENT_STATUS.md").read_text()
    chronicle_lines = (BASE / "PROJECT_CHRONICLE.md").read_text().splitlines()
    chronicle_tail = "\n".join(chronicle_lines[-100:])

    source.write_text(
        "# Crypto Signal Exact Continuation Checkpoint\n\n"
        f"task_id={task}\n"
        f"created_epoch={now}\n"
        f"git_head={head}\n"
        f"frontier_note={note}\n"
        "REAL_CAPITAL=0\n\n"
        "## Resume rule\n"
        "Read READ_FIRST_CRYPTO_SIGNAL.md, CURRENT_STATUS.md, latest Chronicle, "
        "this checkpoint, and current Git/worker/wake/lease state first. "
        "Resume only if this exact task remains current and incomplete. "
        "Completed/stale/superseded tasks must NOOP/reconcile, never replay.\n\n"
        "## CURRENT_STATUS snapshot\n"
        f"{status}\n\n"
        "## Chronicle tail snapshot\n"
        f"{chronicle_tail}\n"
    )
    source.chmod(0o600)
    proc = subprocess.run(
        [str(ARM), task, delay, str(source)],
        text=True,
        capture_output=True,
        check=False,
    )
    source.unlink(missing_ok=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
