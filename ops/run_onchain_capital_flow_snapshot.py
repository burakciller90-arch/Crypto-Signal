from __future__ import annotations

import argparse
import asyncio
import fcntl
import sqlite3
import sys
from pathlib import Path

import httpx

from crypto_signal.data.adapters.defillama_stablecoins import (
    DefiLlamaStablecoinsAdapter,
)
from crypto_signal.data.onchain_capital_flow_store import (
    OnchainCapitalFlowStore,
)
from crypto_signal.data.source_contract import SourceContractStore
from crypto_signal.data.stablecoin_source_contract import (
    persist_defillama_stablecoin_snapshot,
)

DEFAULT_ONCHAIN_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "onchain/onchain_capital_flow.sqlite3"
)
DEFAULT_SOURCE_CONTRACT_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "onchain/source_contract.sqlite3"
)
DEFAULT_LOCK = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/"
    "onchain/onchain_capital_flow_snapshot.lock"
)
DEFAULT_DEFILLAMA_BASE_URL = "https://stablecoins.llama.fi"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--onchain-db",
        type=Path,
        default=DEFAULT_ONCHAIN_DB,
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
        "--defillama-base-url",
        default=DEFAULT_DEFILLAMA_BASE_URL,
    )
    return parser.parse_args()


def _require_canonical_path(path: Path, *, label: str) -> None:
    if not str(path).startswith("/Volumes/Crypto-504/"):
        raise ValueError(f"{label} must use canonical SSD path")


async def run(args: argparse.Namespace) -> int:
    try:
        _require_canonical_path(args.onchain_db, label="onchain db")
        _require_canonical_path(
            args.source_contract_db,
            label="source contract db",
        )
        _require_canonical_path(args.lock_path, label="lock path")
    except ValueError as exc:
        print(
            f"RDP7_ONCHAIN_SNAPSHOT_ERROR={exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    if not str(args.defillama_base_url).startswith("https://"):
        print(
            "RDP7_ONCHAIN_SNAPSHOT_ERROR=INVALID_DEFILLAMA_URL",
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
                "RDP7_ONCHAIN_SNAPSHOT_SKIPPED=LOCK_HELD REAL_CAPITAL=0",
                flush=True,
            )
            return 0

        onchain_store = OnchainCapitalFlowStore(args.onchain_db)
        source_store = SourceContractStore(args.source_contract_db)
        adapter = DefiLlamaStablecoinsAdapter(
            base_url=args.defillama_base_url
        )
        try:
            snapshot = await adapter.fetch_snapshot()
            persisted = persist_defillama_stablecoin_snapshot(
                snapshot=snapshot,
                onchain_store=onchain_store,
                source_store=source_store,
            )
        except (
            httpx.HTTPError,
            sqlite3.Error,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            print(
                "RDP7_ONCHAIN_SNAPSHOT_ERROR "
                f"error={type(exc).__name__}:{exc} "
                "FAIL_CLOSED=YES REAL_CAPITAL=0",
                file=sys.stderr,
                flush=True,
            )
            return 1

    for item in persisted:
        print(
            "RDP7_STABLECOIN_SNAPSHOT_OK "
            f"symbol={item.symbol} "
            f"raw={item.raw_identity} "
            f"envelope={item.envelope_identity} "
            f"coverage={item.coverage_event_identity} "
            f"observation={item.observation_identity}",
            flush=True,
        )

    counts = onchain_store.counts()
    print(
        "RDP7_ONCHAIN_SNAPSHOT_COMPLETE "
        f"stablecoin_observations="
        f"{counts.stablecoin_supply_observations} "
        "SOURCE=DEFILLAMA_PUBLIC_NO_AUTH "
        "EXCHANGE_FLOW_PROVIDER=UNAVAILABLE_EXPLICIT "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
