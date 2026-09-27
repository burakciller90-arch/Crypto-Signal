from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotMicrostructureStream,
)
from crypto_signal.data.market_tape import MarketTapeStore
from crypto_signal.data.market_tape_wire_collection import (
    persist_bybit_wire_stream,
)
from crypto_signal.data.raw_market_tape import RawMarketTapeStore

REAL_CAPITAL = 0
URL = "wss://stream.bybit.tr/v5/public/spot"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RDP1 temp-DB Market Tape persistence probe."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-messages", type=int, default=200)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)

    store = MarketTapeStore(args.output_dir / "market.sqlite3")
    raw_store = RawMarketTapeStore(args.output_dir / "raw.sqlite3")
    stream = BybitSpotMicrostructureStream(url=URL, proxy=None)

    async with asyncio.timeout(args.timeout_seconds):
        result = await persist_bybit_wire_stream(
            store=store,
            raw_store=raw_store,
            events=stream.stream_wire_events(symbols=SYMBOLS, depth=50),
            orderbook_snapshot_interval_ms=1_000,
            max_messages=args.max_messages,
        )

    counts = store.counts()
    raw_count = raw_store.count()
    print(f"RDP1_TEMP_OBSERVED_MESSAGES={result.observed_messages}")
    print(f"RDP1_TEMP_RAW_INSERTED={result.raw_inserted}")
    print(f"RDP1_TEMP_RAW_ROWS={raw_count}")
    print(f"RDP1_TEMP_ORDERBOOKS={counts.orderbooks}")
    print(f"RDP1_TEMP_TRADES={counts.trades}")
    print(f"RDP1_TEMP_NORMALIZED_TOTAL={counts.total}")
    print("REAL_CAPITAL=0")

    if result.observed_messages != args.max_messages:
        print("RDP1_TEMP_PERSISTENCE_PASS=NO")
        return 2
    if raw_count <= 0 or counts.orderbooks <= 0:
        print("RDP1_TEMP_PERSISTENCE_PASS=NO")
        return 3
    print("RDP1_TEMP_PERSISTENCE_PASS=YES")
    return 0


def main() -> int:
    args = _parse_args()
    if args.max_messages <= 0 or args.timeout_seconds <= 0:
        raise ValueError("probe limits must be positive")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
