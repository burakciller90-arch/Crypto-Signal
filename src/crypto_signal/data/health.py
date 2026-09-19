from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from crypto_signal.data.models import Candle
from crypto_signal.data.timeframes import spec


@dataclass(frozen=True, slots=True)
class CandleGap:
    first_missing_open_ms: int
    last_missing_open_ms: int
    missing_count: int


@dataclass(frozen=True, slots=True)
class Freshness:
    source_age_ms: int | None
    closed_age_ms: int | None
    stale: bool
    reasons: tuple[str, ...]


def detect_gaps(candles: Sequence[Candle], timeframe: str) -> tuple[CandleGap, ...]:
    if not candles:
        return ()

    duration_ms = spec(timeframe).duration_ms
    ordered = sorted(candles, key=lambda candle: candle.open_time_ms)
    opens = [candle.open_time_ms for candle in ordered]
    if len(set(opens)) != len(opens):
        raise ValueError("duplicate candle open time")

    gaps: list[CandleGap] = []
    for left, right in pairwise(ordered):
        delta = right.open_time_ms - left.open_time_ms
        if delta <= 0 or delta % duration_ms != 0:
            raise ValueError("candle sequence is not aligned to timeframe spacing")
        if delta > duration_ms:
            gaps.append(
                CandleGap(
                    first_missing_open_ms=left.open_time_ms + duration_ms,
                    last_missing_open_ms=right.open_time_ms - duration_ms,
                    missing_count=(delta // duration_ms) - 1,
                )
            )
    return tuple(gaps)


def assess_freshness(
    candles: Sequence[Candle],
    *,
    timeframe: str,
    now_ms: int,
    max_source_age_ms: int | None = None,
    max_closed_age_ms: int | None = None,
) -> Freshness:
    if not candles:
        return Freshness(None, None, True, ("no_candles",))

    duration_ms = spec(timeframe).duration_ms
    source_limit = max_source_age_ms if max_source_age_ms is not None else 2 * duration_ms
    closed_limit = max_closed_age_ms if max_closed_age_ms is not None else 2 * duration_ms

    latest_source_ms = max(candle.source_timestamp_ms for candle in candles)
    source_age_ms = now_ms - latest_source_ms
    closed = [candle for candle in candles if candle.is_closed]
    latest_closed_ms = max((candle.close_time_ms for candle in closed), default=None)
    closed_age_ms = None if latest_closed_ms is None else now_ms - latest_closed_ms

    reasons: list[str] = []
    if source_age_ms > source_limit:
        reasons.append("source_stale")
    if closed_age_ms is None:
        reasons.append("no_closed_candle")
    elif closed_age_ms > closed_limit:
        reasons.append("closed_candle_stale")

    return Freshness(source_age_ms, closed_age_ms, bool(reasons), tuple(reasons))
