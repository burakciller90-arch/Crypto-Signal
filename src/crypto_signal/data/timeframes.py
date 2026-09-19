from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimeframeSpec:
    canonical: str
    duration_ms: int
    bybit_interval: str
    binance_interval: str


SPECS: dict[str, TimeframeSpec] = {
    "15m": TimeframeSpec("15m", 15 * 60_000, "15", "15m"),
    "1h": TimeframeSpec("1h", 60 * 60_000, "60", "1h"),
    "4h": TimeframeSpec("4h", 4 * 60 * 60_000, "240", "4h"),
    "1D": TimeframeSpec("1D", 24 * 60 * 60_000, "D", "1d"),
    "1W": TimeframeSpec("1W", 7 * 24 * 60 * 60_000, "W", "1w"),
}


def spec(timeframe: str) -> TimeframeSpec:
    try:
        return SPECS[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported V1 timeframe: {timeframe}") from exc
