from __future__ import annotations

from dataclasses import dataclass

WEEK_ANCHOR_MS = 4 * 24 * 60 * 60_000  # Monday 1970-01-05 00:00 UTC.


@dataclass(frozen=True, slots=True)
class TimeframeSpec:
    canonical: str
    duration_ms: int
    bybit_interval: str
    binance_interval: str
    grid_anchor_ms: int = 0


SPECS: dict[str, TimeframeSpec] = {
    "15m": TimeframeSpec("15m", 15 * 60_000, "15", "15m"),
    "1h": TimeframeSpec("1h", 60 * 60_000, "60", "1h"),
    "4h": TimeframeSpec("4h", 4 * 60 * 60_000, "240", "4h"),
    "1D": TimeframeSpec("1D", 24 * 60 * 60_000, "D", "1d"),
    "1W": TimeframeSpec(
        "1W",
        7 * 24 * 60 * 60_000,
        "W",
        "1w",
        grid_anchor_ms=WEEK_ANCHOR_MS,
    ),
}


def spec(timeframe: str) -> TimeframeSpec:
    try:
        return SPECS[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported V1 timeframe: {timeframe}") from exc


def is_aligned_open(open_time_ms: int, timeframe: str) -> bool:
    timeframe_spec = spec(timeframe)
    return (
        open_time_ms - timeframe_spec.grid_anchor_ms
    ) % timeframe_spec.duration_ms == 0


def bucket_open_ms(open_time_ms: int, timeframe: str) -> int:
    timeframe_spec = spec(timeframe)
    anchor_ms = timeframe_spec.grid_anchor_ms
    return anchor_ms + (
        (open_time_ms - anchor_ms) // timeframe_spec.duration_ms
    ) * timeframe_spec.duration_ms
