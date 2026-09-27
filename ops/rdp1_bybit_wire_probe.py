from __future__ import annotations

import argparse
import asyncio

from crypto_signal.data.adapters.bybit_microstructure_ws import (
    BybitSpotMicrostructureStream,
)

REAL_CAPITAL = 0
DEFAULT_URL = "wss://stream.bybit.tr/v5/public/spot"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only RDP1 Bybit TR wire-event probe."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--depth", type=int, default=50)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    stream = BybitSpotMicrostructureStream(url=args.url, proxy=None)
    required = {
        (symbol, channel)
        for symbol in DEFAULT_SYMBOLS
        for channel in (f"orderbook.{args.depth}", "publicTrade")
    }
    seen: set[tuple[str, str]] = set()
    count = 0

    try:
        async with asyncio.timeout(args.timeout_seconds):
            async for event in stream.stream_wire_events(
                symbols=DEFAULT_SYMBOLS,
                depth=args.depth,
            ):
                count += 1
                key = (event.symbol, event.channel)
                seen.add(key)
                print(
                    "RDP1_WIRE_EVENT "
                    f"count={count} "
                    f"symbol={event.symbol} "
                    f"channel={event.channel} "
                    f"kind={event.event_kind} "
                    f"source_ms={event.source_timestamp_ms} "
                    f"ingested_ms={event.ingested_at_ms}",
                    flush=True,
                )
                if required.issubset(seen):
                    break
    except TimeoutError:
        pass

    missing = sorted(required - seen)
    print(f"RDP1_WIRE_SEEN={sorted(seen)}", flush=True)
    print(f"RDP1_WIRE_MISSING={missing}", flush=True)
    print(f"RDP1_WIRE_EVENT_COUNT={count}", flush=True)
    print("REAL_CAPITAL=0", flush=True)
    if missing:
        print("RDP1_BYBIT_TR_WIRE_PROBE_PASS=NO", flush=True)
        return 2
    print("RDP1_BYBIT_TR_WIRE_PROBE_PASS=YES", flush=True)
    return 0


def main() -> int:
    args = _parse_args()
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
