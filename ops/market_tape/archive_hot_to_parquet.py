from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from crypto_signal.data.market_tape_cold_archive import (
    archive_due_hot_partitions,
)
from crypto_signal.data.market_tape_hotcold import (
    DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
)

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal")
DEFAULT_HOT_DIR = ROOT / "Development/runtime/market_tape"
DEFAULT_COLD_DIR = ROOT / "MarketTapeCold"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hot-dir", type=Path, default=DEFAULT_HOT_DIR)
    parser.add_argument("--cold-dir", type=Path, default=DEFAULT_COLD_DIR)
    parser.add_argument("--now-ms", type=int)
    return parser.parse_args()


def _require_ssd_path(path: Path, label: str) -> None:
    root = str(ROOT) + "/"
    if not str(path).startswith(root):
        raise ValueError(f"{label} must stay on canonical Crypto-504 SSD")


def main() -> int:
    args = parse_args()
    _require_ssd_path(args.hot_dir, "hot-dir")
    _require_ssd_path(args.cold_dir, "cold-dir")
    if not ROOT.is_dir():
        raise RuntimeError("canonical Crypto-504 SSD root is unavailable")

    now_ms = (
        time.time_ns() // 1_000_000
        if args.now_ms is None
        else args.now_ms
    )
    if now_ms < 0:
        raise ValueError("now-ms cannot be negative")

    result = archive_due_hot_partitions(
        hot_dir=args.hot_dir,
        cold_dir=args.cold_dir,
        now_ms=now_ms,
        policy=DEFAULT_MARKET_TAPE_HOTCOLD_POLICY,
    )
    payload = {
        "archive_before_ms": result.archive_before_ms,
        "archived_rows": result.archived_rows,
        "cold_bytes": result.cold_bytes,
        "partitions": [
            {
                "archived_rows": item.archived_rows,
                "cold_bytes": item.cold_bytes,
                "partition_id": item.partition_id,
                "pruned_rows": item.pruned_rows,
                "reused_existing_partition": item.reused_existing_partition,
                "window_end_ms": item.window_end_ms,
                "window_start_ms": item.window_start_ms,
            }
            for item in result.partitions
        ],
        "pruned_rows": result.pruned_rows,
        "real_capital": 0,
    }
    print(
        "MARKET_TAPE_COLD_ARCHIVE_RESULT="
        + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        flush=True,
    )
    print("MARKET_TAPE_COLD_ARCHIVE_PASS=YES REAL_CAPITAL=0", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
