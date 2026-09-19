from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from crypto_signal.data.models import Candle
from crypto_signal.data.timeframes import spec
from crypto_signal.primitives.models import (
    AlternatingSwingResult,
    ConfirmedPivot,
    PivotKind,
)


def _validate_series(candles: Sequence[Candle]) -> None:
    if not candles:
        return

    first = candles[0]
    duration_ms = spec(first.timeframe).duration_ms
    previous_open: int | None = None

    for candle in candles:
        if not candle.is_closed:
            raise ValueError("swing detection requires closed candles")
        if (
            candle.exchange != first.exchange
            or candle.market_type != first.market_type
            or candle.symbol != first.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("swing detection cannot mix candle semantics")
        if candle.open_time_ms % duration_ms != 0:
            raise ValueError("candle is off the canonical timeframe grid")
        if previous_open is not None and candle.open_time_ms - previous_open != duration_ms:
            raise ValueError("swing detection requires a gapless chronological series")
        previous_open = candle.open_time_ms
def detect_fractal_pivots(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
) -> tuple[ConfirmedPivot, ...]:
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be positive")

    _validate_series(candles)
    if len(candles) < left_bars + right_bars + 1:
        return ()

    pivots: list[ConfirmedPivot] = []
    first = candles[0]

    for index in range(left_bars, len(candles) - right_bars):
        candidate = candles[index]
        neighbors = (
            *candles[index - left_bars : index],
            *candles[index + 1 : index + right_bars + 1],
        )
        is_high = all(candidate.high > candle.high for candle in neighbors)
        is_low = all(candidate.low < candle.low for candle in neighbors)
        if not is_high and not is_low:
            continue

        confirmation = candles[index + right_bars]
        observed_at_ms = max(
            candle.ingested_at_ms
            for candle in candles[index - left_bars : index + right_bars + 1]
        )
        ambiguous = is_high and is_low

        if is_high:
            pivots.append(
                ConfirmedPivot(
                    exchange=first.exchange,
                    market_type=first.market_type,
                    symbol=first.symbol,
                    timeframe=first.timeframe,
                    kind=PivotKind.HIGH,
                    candle_index=index,
                    open_time_ms=candidate.open_time_ms,
                    price=candidate.high,
                    left_bars=left_bars,
                    right_bars=right_bars,
                    market_confirmed_at_ms=confirmation.close_time_ms,
                    observed_at_ms=observed_at_ms,
                    source_candle_identity=candidate.identity,
                    confirmation_candle_identity=confirmation.identity,
                    same_bar_ambiguity=ambiguous,
                )
            )
        if is_low:
            pivots.append(
                ConfirmedPivot(
                    exchange=first.exchange,
                    market_type=first.market_type,
                    symbol=first.symbol,
                    timeframe=first.timeframe,
                    kind=PivotKind.LOW,
                    candle_index=index,
                    open_time_ms=candidate.open_time_ms,
                    price=candidate.low,
                    left_bars=left_bars,
                    right_bars=right_bars,
                    market_confirmed_at_ms=confirmation.close_time_ms,
                    observed_at_ms=observed_at_ms,
                    source_candle_identity=candidate.identity,
                    confirmation_candle_identity=confirmation.identity,
                    same_bar_ambiguity=ambiguous,
                )
            )

    return tuple(pivots)


def compress_alternating_pivots(
    pivots: Sequence[ConfirmedPivot],
) -> AlternatingSwingResult:
    if not pivots:
        return AlternatingSwingResult(swings=(), ambiguous_source_indices=())

    first = pivots[0]
    grouped: dict[int, list[ConfirmedPivot]] = defaultdict(list)
    for pivot in pivots:
        if (
            pivot.exchange != first.exchange
            or pivot.market_type != first.market_type
            or pivot.symbol != first.symbol
            or pivot.timeframe != first.timeframe
        ):
            raise ValueError("alternating compression cannot mix pivot semantics")
        grouped[pivot.candle_index].append(pivot)

    ambiguous_indices: list[int] = []
    ordered: list[ConfirmedPivot] = []
    for candle_index in sorted(grouped):
        group = grouped[candle_index]
        kinds = {pivot.kind for pivot in group}
        if len(kinds) != len(group):
            raise ValueError("duplicate same-kind pivot at one source candle")
        if len(kinds) > 1 or any(pivot.same_bar_ambiguity for pivot in group):
            ambiguous_indices.append(candle_index)
            continue
        ordered.append(group[0])

    swings: list[ConfirmedPivot] = []
    for pivot in ordered:
        if not swings or swings[-1].kind is not pivot.kind:
            swings.append(pivot)
            continue

        previous = swings[-1]
        more_extreme = (
            pivot.price > previous.price
            if pivot.kind is PivotKind.HIGH
            else pivot.price < previous.price
        )
        if more_extreme:
            swings[-1] = pivot

    return AlternatingSwingResult(
        swings=tuple(swings),
        ambiguous_source_indices=tuple(ambiguous_indices),
    )
