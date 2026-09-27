from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

CONTEXTS = (
    ("bybit", "BTCUSDT"),
    ("bybit", "ETHUSDT"),
    ("bybit", "SOLUSDT"),
    ("binance", "BTCUSDT"),
    ("binance", "ETHUSDT"),
    ("binance", "SOLUSDT"),
)
TIMEFRAME = "15m"
MAX_AVAILABILITY_LAG_MS = 90_000
MAX_LATEST_CLOSED_AGE_MS = 15 * 60 * 1000 + MAX_AVAILABILITY_LAG_MS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only RDP1 closed-candle cache SLO acceptance."
    )
    parser.add_argument("--cache", type=Path, required=True)
    return parser.parse_args()


def run(cache: Path) -> int:
    if not cache.is_file():
        print("RDP1_CANDLE_SLO_CACHE_MISSING=YES", flush=True)
        return 2

    now_ms = time.time_ns() // 1_000_000
    uri = f"{cache.resolve().as_uri()}?mode=ro"
    failures = 0
    with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        for exchange, symbol in CONTEXTS:
            row = db.execute(
                """
                SELECT open_time_ms, close_time_ms, source_timestamp_ms,
                       ingested_at_ms, adapter_version
                FROM candles
                WHERE exchange=?
                  AND market_type='spot'
                  AND symbol=?
                  AND timeframe=?
                  AND is_closed=1
                ORDER BY close_time_ms DESC
                LIMIT 1
                """,
                (exchange, symbol, TIMEFRAME),
            ).fetchone()
            if row is None:
                failures += 1
                print(
                    "RDP1_CANDLE_SLO "
                    f"exchange={exchange} symbol={symbol} "
                    "status=MISSING_CLOSED_CANDLE",
                    flush=True,
                )
                continue

            close_ms = int(row["close_time_ms"])
            source_ms = int(row["source_timestamp_ms"])
            ingested_ms = int(row["ingested_at_ms"])
            age_ms = now_ms - close_ms
            availability_lag_ms = ingested_ms - close_ms
            source_lag_ms = source_ms - close_ms
            status = "PASS"
            if close_ms > now_ms:
                status = "FUTURE_CLOSED_CANDLE"
            elif age_ms > MAX_LATEST_CLOSED_AGE_MS:
                status = "LATEST_CLOSED_STALE"
            elif not (0 <= availability_lag_ms <= MAX_AVAILABILITY_LAG_MS):
                status = "AVAILABILITY_SLO_MISS"
            if status != "PASS":
                failures += 1
            print(
                "RDP1_CANDLE_SLO "
                f"exchange={exchange} symbol={symbol} status={status} "
                f"open_ms={int(row['open_time_ms'])} "
                f"close_ms={close_ms} age_ms={age_ms} "
                f"source_lag_ms={source_lag_ms} "
                f"availability_lag_ms={availability_lag_ms} "
                f"adapter={row['adapter_version']}",
                flush=True,
            )

    print(f"RDP1_CANDLE_SLO_FAILURES={failures}", flush=True)
    print("REAL_CAPITAL=0", flush=True)
    if failures:
        print("RDP1_CLOSED_CANDLE_SLO_PASS=NO", flush=True)
        return 2
    print("RDP1_CLOSED_CANDLE_SLO_PASS=YES", flush=True)
    return 0


def main() -> int:
    args = parse_args()
    return run(args.cache)


if __name__ == "__main__":
    raise SystemExit(main())
