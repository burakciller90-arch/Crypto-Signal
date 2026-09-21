from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_signal.runtime_recovery import bound_log_directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--keep-bytes", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args()

    bounded = bound_log_directory(
        args.log_dir,
        max_bytes=args.max_bytes,
        keep_bytes=args.keep_bytes,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "log_dir": str(args.log_dir),
                "bounded": [
                    {"name": name, "before": before, "after": after}
                    for name, before, after in bounded
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
