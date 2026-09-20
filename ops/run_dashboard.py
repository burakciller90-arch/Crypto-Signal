#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from crypto_signal.product.web import (
    DEFAULT_ALERT_OUTBOX_PATH,
    DEFAULT_LEDGER_PATH,
    create_app,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=48700)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument(
        "--alert-outbox",
        type=Path,
        default=DEFAULT_ALERT_OUTBOX_PATH,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    app = create_app(args.ledger, args.alert_outbox)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
