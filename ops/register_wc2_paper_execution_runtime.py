#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_execution_protocol import (
    WC2PaperExecutionProtocolStore,
)
from crypto_signal.evaluation.untouched_forward_execution_runtime import (
    WC2PaperExecutionRuntimeStore,
    build_wc2_execution_runtime_activation,
)

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
DEFAULT_PROTOCOL_DB = (
    ROOT / "runtime/wc2/wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"
)
DEFAULT_RUNTIME_DB = (
    ROOT / "runtime/wc2/wc2_paper_execution.wc2-paper-execution-runtime.sqlite3"
)
FIFTEEN_MINUTES_MS = 900_000
START_BUCKETS_AHEAD = 2
REAL_CAPITAL = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-protocol-db", type=Path, default=DEFAULT_PROTOCOL_DB)
    parser.add_argument("--runtime-db", type=Path, default=DEFAULT_RUNTIME_DB)
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    for path in (args.execution_protocol_db, args.runtime_db):
        if not str(path).startswith("/Volumes/Crypto-504/"):
            print("WC2_EXECUTION_RUNTIME_ERROR=NON_CANONICAL_PATH", file=sys.stderr)
            return 2
    protocol = WC2PaperExecutionProtocolStore(args.execution_protocol_db).latest()
    if protocol is None:
        print("WC2_EXECUTION_RUNTIME_ERROR=PROTOCOL_MISSING", file=sys.stderr)
        return 3
    store = WC2PaperExecutionRuntimeStore(args.runtime_db)
    existing = store.latest()
    if existing is not None:
        if existing.execution_protocol_identity != protocol.protocol_identity:
            print("WC2_EXECUTION_RUNTIME_ERROR=PROTOCOL_LINEAGE_MISMATCH", file=sys.stderr)
            return 4
        activation = existing
        inserted = False
    else:
        now_ms = time.time_ns() // 1_000_000
        source = max(now_ms, protocol.execution_start_ms)
        collection_start_ms = (
            (source // FIFTEEN_MINUTES_MS) + START_BUCKETS_AHEAD
        ) * FIFTEEN_MINUTES_MS
        activation = build_wc2_execution_runtime_activation(
            protocol=protocol,
            registered_at_ms=now_ms,
            collection_start_ms=collection_start_ms,
        )
        inserted = store.append(activation)
    print(
        "WC2_EXECUTION_RUNTIME_REGISTRATION "
        f"status={'INSERTED' if inserted else 'REUSED'} "
        f"activation={activation.activation_identity} "
        f"protocol={activation.execution_protocol_identity} "
        f"registered_at_ms={activation.registered_at_ms} "
        f"collection_start_ms={activation.collection_start_ms} "
        f"maximum_decision_delay_ms={activation.maximum_decision_delay_ms}",
        flush=True,
    )
    print(
        "WC2_EXECUTION_RUNTIME_FORWARD_ONLY_PASS=YES "
        "WC2_EXECUTION_RUNTIME_HISTORICAL_BACKFILL=NO "
        "WC2_EXECUTION_RUNTIME_PRODUCTION_AUTHORITY=NO "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
