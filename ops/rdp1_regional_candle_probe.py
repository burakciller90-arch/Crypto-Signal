from __future__ import annotations

import argparse
import asyncio
import time

from crypto_signal.data.adapters.binance import BinanceSpotAdapter
from crypto_signal.data.adapters.bybit import BybitSpotAdapter

REAL_CAPITAL = 0
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TIMEFRAMES = ("15m", "1h", "4h")
TIMEFRAME_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only RDP1 regional candle-source freshness probe."
    )
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


async def _probe_provider(
    *,
    name: str,
    adapter: BybitSpotAdapter | BinanceSpotAdapter,
    limit: int,
) -> int:
    failures = 0
    now_ms = time.time_ns() // 1_000_000
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            try:
                candles = await adapter.fetch_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit,
                )
                closed = [candle for candle in candles if candle.is_closed]
                if not closed:
                    print(
                        "RDP1_CANDLE "
                        f"provider={name} symbol={symbol} timeframe={timeframe} "
                        "status=NO_CLOSED_CANDLE",
                        flush=True,
                    )
                    failures += 1
                    continue
                latest = max(closed, key=lambda candle: candle.close_time_ms)
                age_ms = now_ms - latest.close_time_ms
                threshold_ms = TIMEFRAME_MS[timeframe] + 120_000
                status = "PASS" if 0 <= age_ms <= threshold_ms else "STALE"
                if status != "PASS":
                    failures += 1
                print(
                    "RDP1_CANDLE "
                    f"provider={name} symbol={symbol} timeframe={timeframe} "
                    f"status={status} close_ms={latest.close_time_ms} "
                    f"age_ms={age_ms} source_ms={latest.source_timestamp_ms} "
                    f"ingested_ms={latest.ingested_at_ms} "
                    f"adapter={latest.adapter_version}",
                    flush=True,
                )
            except Exception as exc:
                failures += 1
                print(
                    "RDP1_CANDLE "
                    f"provider={name} symbol={symbol} timeframe={timeframe} "
                    f"status=ERROR error={type(exc).__name__}:{exc}",
                    flush=True,
                )
    return failures


async def run(limit: int) -> int:
    if limit <= 0:
        raise ValueError("limit must be positive")

    bybit = BybitSpotAdapter(base_url="https://api.bybit.tr")
    binance = BinanceSpotAdapter(
        base_url="https://api.binance.me",
        api_variant="tr_main",
    )

    bybit_failures, binance_failures = await asyncio.gather(
        _probe_provider(name="bybit_tr", adapter=bybit, limit=limit),
        _probe_provider(name="binance_tr", adapter=binance, limit=limit),
    )
    failures = bybit_failures + binance_failures
    print(f"RDP1_CANDLE_FAILURES={failures}", flush=True)
    print("REAL_CAPITAL=0", flush=True)
    if failures:
        print("RDP1_REGIONAL_CANDLE_PROBE_PASS=NO", flush=True)
        return 2
    print("RDP1_REGIONAL_CANDLE_PROBE_PASS=YES", flush=True)
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(run(args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
