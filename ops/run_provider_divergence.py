from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.data.provider_divergence import (
    ProviderDivergenceSnapshot,
    ProviderDivergenceStore,
    build_provider_divergence_snapshot,
    read_candles_read_only,
)

DEFAULT_CANDLE_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/data/"
    "live_base_15m_cache.sqlite3"
)
DEFAULT_DIVERGENCE_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/data/"
    "provider_divergence.sqlite3"
)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DEFAULT_TIMEFRAME = "15m"
DEFAULT_LOOKBACK = 96


@dataclass(frozen=True, slots=True)
class ProviderDivergenceCycleResult:
    observed_at_ms: int
    snapshots: tuple[ProviderDivergenceSnapshot, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candle-db", type=Path, default=DEFAULT_CANDLE_DB)
    parser.add_argument(
        "--divergence-db",
        type=Path,
        default=DEFAULT_DIVERGENCE_DB,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
    )
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK)
    parser.add_argument("--observed-at-ms", type=int)
    return parser.parse_args()


def collect_provider_divergence(
    *,
    candle_db: Path,
    divergence_db: Path,
    symbols: tuple[str, ...],
    timeframe: str,
    lookback: int,
    observed_at_ms: int,
) -> ProviderDivergenceCycleResult:
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms cannot be negative")
    if not symbols or tuple(sorted(set(symbols))) != symbols:
        raise ValueError("symbols must be unique and sorted")
    if any(not symbol or symbol != symbol.upper() for symbol in symbols):
        raise ValueError("symbols must be uppercase")
    if not timeframe.strip():
        raise ValueError("timeframe must be non-empty")
    if lookback <= 0 or lookback > 10_000:
        raise ValueError("lookback must be inside 1..10000")

    output = ProviderDivergenceStore(divergence_db)
    output.initialize()
    snapshots: list[ProviderDivergenceSnapshot] = []
    for symbol in symbols:
        binance = read_candles_read_only(
            candle_db,
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe=timeframe,
        )
        bybit = read_candles_read_only(
            candle_db,
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe=timeframe,
        )
        snapshot = build_provider_divergence_snapshot(
            market_type=MarketType.SPOT,
            symbol=symbol,
            timeframe=timeframe,
            observed_at_ms=observed_at_ms,
            left_exchange=Exchange.BINANCE,
            right_exchange=Exchange.BYBIT,
            left_candles=binance,
            right_candles=bybit,
            lookback_limit=lookback,
        )
        output.append(snapshot)
        snapshots.append(snapshot)

    return ProviderDivergenceCycleResult(
        observed_at_ms=observed_at_ms,
        snapshots=tuple(snapshots),
    )


def run(args: argparse.Namespace) -> int:
    for label, path in (
        ("candle_db", args.candle_db),
        ("divergence_db", args.divergence_db),
    ):
        if not str(path).startswith("/Volumes/Crypto-504/"):
            print(
                f"PROVIDER_DIVERGENCE_ERROR=NON_CANONICAL_PATH field={label}",
                file=sys.stderr,
                flush=True,
            )
            return 2

    try:
        symbols = tuple(
            sorted(
                set(str(value).upper() for value in args.symbols)
            )
        )
        observed_at_ms = (
            time.time_ns() // 1_000_000
            if args.observed_at_ms is None
            else int(args.observed_at_ms)
        )
        result = collect_provider_divergence(
            candle_db=args.candle_db,
            divergence_db=args.divergence_db,
            symbols=symbols,
            timeframe=str(args.timeframe),
            lookback=int(args.lookback),
            observed_at_ms=observed_at_ms,
        )
    except (OSError, ValueError) as exc:
        print(
            "PROVIDER_DIVERGENCE_ERROR "
            f"error={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 3

    for snapshot in result.snapshots:
        print(
            "PROVIDER_DIVERGENCE_SNAPSHOT "
            f"symbol={snapshot.symbol} "
            f"timeframe={snapshot.timeframe} "
            f"grid_state={snapshot.grid_state.value} "
            f"overlap={snapshot.overlap_count} "
            f"binance_available={'YES' if snapshot.left_quality.available else 'NO'} "
            f"bybit_available={'YES' if snapshot.right_quality.available else 'NO'} "
            f"binance_stale={'YES' if snapshot.left_quality.stale else 'NO'} "
            f"bybit_stale={'YES' if snapshot.right_quality.stale else 'NO'} "
            f"latest_spread_bps={snapshot.latest_close_spread_bps} "
            f"median_abs_spread_bps={snapshot.median_absolute_close_spread_bps} "
            f"max_abs_spread_bps={snapshot.max_absolute_close_spread_bps} "
            f"snapshot={snapshot.snapshot_identity}",
            flush=True,
        )
    print(
        "PROVIDER_DIVERGENCE_COMPLETE "
        f"observed_at_ms={result.observed_at_ms} "
        f"snapshots={len(result.snapshots)} "
        "CONSENSUS_NOT_INFERRED=YES "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
