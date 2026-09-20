#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from crypto_signal.paper.log_retention import (
    PaperLogRotationError,
    rotate_single_backup_log,
)

BASE = Path("/Users/crypto-signal-agent/Crypto-Signal")
PAPER = Path("/Users/crypto-signal-agent/Crypto-Signal-Paper")
RUNTIME = BASE / "runtime" / "paper"
OUT_LOG = RUNTIME / "paper_dry_run_clock.out.log"
ERR_LOG = RUNTIME / "paper_dry_run_clock.err.log"
MAX_LOG_BYTES = 5 * 1024 * 1024


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    try:
        out_rotation = rotate_single_backup_log(
            OUT_LOG,
            max_bytes=MAX_LOG_BYTES,
        )
        err_rotation = rotate_single_backup_log(
            ERR_LOG,
            max_bytes=MAX_LOG_BYTES,
        )
    except PaperLogRotationError as exc:
        print(f"PAPER_DRY_RUN_CLOCK_ERROR={exc}", file=sys.stderr, flush=True)
        return 1

    with OUT_LOG.open("a", buffering=1) as out_handle, ERR_LOG.open(
        "a",
        buffering=1,
    ) as err_handle:
        os.dup2(out_handle.fileno(), 1)
        os.dup2(err_handle.fileno(), 2)
        print(
            "PAPER_DRY_RUN_LOG_RETENTION "
            f"out_rotated={'YES' if out_rotation.rotated else 'NO'} "
            f"out_previous_bytes={out_rotation.previous_size_bytes} "
            f"err_rotated={'YES' if err_rotation.rotated else 'NO'} "
            f"err_previous_bytes={err_rotation.previous_size_bytes} "
            f"max_bytes={MAX_LOG_BYTES}",
            flush=True,
        )
        python = PAPER / ".venv" / "bin" / "python"
        script = PAPER / "ops" / "run_paper_activation_dry_run.py"
        argv = [
            str(python),
            str(script),
            "--paper-ledger",
            str(BASE / "runtime" / "paper" / "paper_fund.sqlite3"),
            "--signal-ledger",
            str(BASE / "runtime" / "ledger" / "live_signal_ledger.sqlite3"),
            "--candle-cache",
            str(BASE / "runtime" / "data" / "live_base_15m_cache.sqlite3"),
            "--max-events",
            "100",
        ]
        os.execv(str(python), argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
