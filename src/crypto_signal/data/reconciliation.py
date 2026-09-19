from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.models import Candle, Exchange


@dataclass(frozen=True, slots=True)
class CloseSpread:
    open_time_ms: int
    left_exchange: Exchange
    right_exchange: Exchange
    spread_bps: Decimal


@dataclass(frozen=True, slots=True)
class GridReconciliation:
    overlap_count: int
    left_only_open_times_ms: tuple[int, ...]
    right_only_open_times_ms: tuple[int, ...]
    spreads: tuple[CloseSpread, ...]


def reconcile_candle_grids(
    left: Sequence[Candle],
    right: Sequence[Candle],
) -> GridReconciliation:
    if not left or not right:
        return GridReconciliation(
            overlap_count=0,
            left_only_open_times_ms=tuple(c.open_time_ms for c in left),
            right_only_open_times_ms=tuple(c.open_time_ms for c in right),
            spreads=(),
        )
    left_first = left[0]
    right_first = right[0]
    if (
        left_first.market_type != right_first.market_type
        or left_first.symbol != right_first.symbol
        or left_first.timeframe != right_first.timeframe
    ):
        raise ValueError("candle grids are not semantically comparable")

    left_map = {c.open_time_ms: c for c in left}
    right_map = {c.open_time_ms: c for c in right}
    if len(left_map) != len(left) or len(right_map) != len(right):
        raise ValueError("duplicate open time in reconciliation input")

    left_opens = set(left_map)
    right_opens = set(right_map)
    overlap = sorted(left_opens & right_opens)
    spreads: list[CloseSpread] = []
    ten_thousand = Decimal(10_000)
    two = Decimal(2)

    for open_time_ms in overlap:
        left_candle = left_map[open_time_ms]
        right_candle = right_map[open_time_ms]
        midpoint = (left_candle.close + right_candle.close) / two
        spread_bps = Decimal(0) if midpoint == 0 else (
            (left_candle.close - right_candle.close) / midpoint
        ) * ten_thousand
        spreads.append(
            CloseSpread(
                open_time_ms=open_time_ms,
                left_exchange=left_candle.exchange,
                right_exchange=right_candle.exchange,
                spread_bps=spread_bps,
            )
        )
    return GridReconciliation(
        overlap_count=len(overlap),
        left_only_open_times_ms=tuple(sorted(left_opens - right_opens)),
        right_only_open_times_ms=tuple(sorted(right_opens - left_opens)),
        spreads=tuple(spreads),
    )
