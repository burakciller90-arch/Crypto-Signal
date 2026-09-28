from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from decimal import DecimalException
from pathlib import Path

import httpx

from crypto_signal.data.adapters.cboe_vix import CboeVixDailyAdapter
from crypto_signal.data.adapters.treasury_yields import Treasury10YDailyAdapter
from crypto_signal.data.cross_market import CrossMarketSeries
from crypto_signal.data.cross_market_runtime_store import CrossMarketRuntimeStore
from crypto_signal.data.cross_market_source_contract import (
    persist_cross_market_source_snapshot,
    persist_cross_market_unavailable,
)
from crypto_signal.data.source_contract import SourceContractStore

DEFAULT_CROSS_MARKET_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "cross_market/cross_market.sqlite3"
)
DEFAULT_SOURCE_CONTRACT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "cross_market/source_contract.sqlite3"
)
DEFAULT_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "cross_market/cross_market_snapshot.lock"
)
DEFAULT_SESSIONS = 10
REAL_CAPITAL = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cross-market-db",
        type=Path,
        default=DEFAULT_CROSS_MARKET_DB,
    )
    parser.add_argument(
        "--source-contract-db",
        type=Path,
        default=DEFAULT_SOURCE_CONTRACT_DB,
    )
    parser.add_argument(
        "--lock-path",
        type=Path,
        default=DEFAULT_LOCK,
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=DEFAULT_SESSIONS,
    )
    return parser.parse_args()


def _require_canonical_path(path: Path, *, label: str) -> None:
    if not str(path).startswith("/Volumes/Crypto-504/"):
        raise ValueError(f"{label} must use canonical SSD path")


def _reason_code(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return "http_status_error"
    if isinstance(exc, httpx.HTTPError):
        return "network_error"
    if isinstance(exc, ET.ParseError):
        return "parse_error"
    if isinstance(exc, (DecimalException, TypeError, ValueError)):
        return "invalid_payload"
    if isinstance(exc, sqlite3.Error):
        return "persistence_error"
    return "runtime_error"


async def run(args: argparse.Namespace) -> int:
    try:
        for label, path in (
            ("cross-market db", args.cross_market_db),
            ("source contract db", args.source_contract_db),
            ("cross-market lock", args.lock_path),
        ):
            _require_canonical_path(path, label=label)
    except ValueError as exc:
        print(
            f"RDP8_CROSS_MARKET_ERROR={exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.sessions < 3 or args.sessions > 64:
        print(
            "RDP8_CROSS_MARKET_ERROR=INVALID_SESSIONS",
            file=sys.stderr,
            flush=True,
        )
        return 2

    args.lock_path.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print(
                "RDP8_CROSS_MARKET_SNAPSHOT_SKIPPED=LOCK_HELD "
                "REAL_CAPITAL=0",
                flush=True,
            )
            return 0

        runtime_store = CrossMarketRuntimeStore(args.cross_market_db)
        source_store = SourceContractStore(args.source_contract_db)
        runtime_store.initialize()
        source_store.initialize()

        adapters = (
            (
                CrossMarketSeries.CBOE_VIX_CLOSE,
                "VIX",
                CboeVixDailyAdapter(),
            ),
            (
                CrossMarketSeries.US_TREASURY_10Y_YIELD,
                "US10Y",
                Treasury10YDailyAdapter(),
            ),
        )
        failures = 0
        for series, label, adapter in adapters:
            try:
                snapshot = await adapter.fetch_source_snapshot(
                    sessions=args.sessions
                )
                persisted = persist_cross_market_source_snapshot(
                    snapshot=snapshot,
                    runtime_store=runtime_store,
                    source_store=source_store,
                )
            except (
                DecimalException,
                ET.ParseError,
                httpx.HTTPError,
                sqlite3.Error,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                failures += 1
                observed_at_ms = time.time_ns() // 1_000_000
                reason = _reason_code(exc)
                try:
                    coverage = persist_cross_market_unavailable(
                        series=series,
                        observed_at_ms=observed_at_ms,
                        reason_code=reason,
                        source_store=source_store,
                    )
                    coverage_identity = coverage.coverage_event_identity
                except (sqlite3.Error, OSError, TypeError, ValueError):
                    coverage_identity = "UNAVAILABLE"
                print(
                    "RDP8_CROSS_MARKET_SOURCE_ERROR "
                    f"series={label} reason={reason} "
                    f"coverage={coverage_identity} "
                    f"error={type(exc).__name__}:{exc} "
                    "FAIL_CLOSED=YES REAL_CAPITAL=0",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            latest = snapshot.observation.records[-1]
            print(
                "RDP8_CROSS_MARKET_SOURCE_OK "
                f"series={label} "
                f"latest_day_start_ms={latest.day_start_ms} "
                f"value={latest.value} "
                f"raw={persisted.raw_identity} "
                f"envelope={persisted.envelope_identity} "
                f"coverage={persisted.coverage_event_identity} "
                f"observation={persisted.observation_identity} "
                f"inserted={'YES' if persisted.inserted_observation else 'NO'}",
                flush=True,
            )

    counts = runtime_store.counts()
    print(
        "RDP8_CROSS_MARKET_SNAPSHOT_COMPLETE "
        f"vix_observations={counts.vix_observations} "
        f"treasury_10y_observations={counts.treasury_10y_observations} "
        f"failures={failures} "
        f"quick_check={'YES' if runtime_store.quick_check() else 'NO'} "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 1 if failures else 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
