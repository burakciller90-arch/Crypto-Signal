#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from crypto_signal.product.intelligence_stream_family_sources import (
    build_market_tape_family_snapshots,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
)

DEFAULT_MARKET_TAPE = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "market_tape/market_tape.sqlite3"
)
DEFAULT_STREAM_LEDGER = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "stream/intelligence_stream.sqlite3"
)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-tape", type=Path, default=DEFAULT_MARKET_TAPE)
    parser.add_argument("--stream-ledger", type=Path, default=DEFAULT_STREAM_LEDGER)
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
    )
    return parser.parse_args()


def run(
    *,
    market_tape_path: Path,
    stream_ledger_path: Path,
    symbols: tuple[str, ...],
    observed_at_ms: int,
) -> int:
    if observed_at_ms < 0:
        raise ValueError("Stream family clock observed_at_ms must be non-negative")
    if not market_tape_path.is_file():
        raise FileNotFoundError(f"market tape missing: {market_tape_path}")
    if not stream_ledger_path.is_file():
        raise FileNotFoundError(f"Stream ledger missing: {stream_ledger_path}")

    normalized_symbols = tuple(
        sorted({value.upper() for value in symbols if value.strip()})
    )
    if not normalized_symbols:
        raise ValueError("Stream family clock requires at least one symbol")

    stream_runtime = IntelligenceStreamForwardRuntime(stream_ledger_path)
    stream_runtime.ensure_activated(activated_at_ms=observed_at_ms)
    projector = IntelligenceStreamProductionProjector(stream_ledger_path)
    snapshots = build_market_tape_family_snapshots(
        market_tape_path,
        symbols=normalized_symbols,
        as_of_ms=observed_at_ms,
    )

    dispositions: Counter[str] = Counter()
    projectors: Counter[str] = Counter()
    for snapshot in snapshots:
        result = projector.project_family(
            snapshot,
            activated_at_ms=observed_at_ms,
        )
        dispositions[result.disposition.value] += 1
        projectors[result.projector_id] += 1
        print(
            f"stream_family projector={result.projector_id} "
            f"symbol={snapshot.symbol} timeframe={snapshot.timeframe} "
            f"state={snapshot.state_label} "
            f"status={result.disposition.value} "
            f"source={result.source_event_identity} "
            f"narrative={result.narrative_identity or '-'} "
            "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            flush=True,
        )

    projector_summary = ",".join(
        f"{key}:{value}" for key, value in sorted(projectors.items())
    ) or "-"
    disposition_summary = ",".join(
        f"{key}:{value}" for key, value in sorted(dispositions.items())
    ) or "-"
    print(
        "stream_family status=SUMMARY "
        f"snapshots={len(snapshots)} "
        f"projectors={projector_summary} "
        f"dispositions={disposition_summary} "
        "ONCHAIN_STANDALONE=DEFERRED_SOURCE "
        "HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run(
            market_tape_path=args.market_tape,
            stream_ledger_path=args.stream_ledger,
            symbols=tuple(str(value) for value in args.symbols),
            observed_at_ms=time.time_ns() // 1_000_000,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, sqlite3.Error) as exc:
        print(
            "STREAM_FAMILY_CLOCK_ERROR "
            f"error={type(exc).__name__}:{exc} "
            "FAIL_CLOSED=YES HISTORICAL_BACKFILL=NO REAL_CAPITAL=0",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
