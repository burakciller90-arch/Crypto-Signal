from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from crypto_signal.data.models import Candle
from crypto_signal.data.periodic_opens import Period, resolve_periodic_open
from crypto_signal.methodologies.price_action.models import (
    LabeledSwing,
    PriceActionStructureResult,
    StructureBreak,
    StructureBreakKind,
    StructureDirection,
    SwingRelation,
)
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind
from crypto_signal.primitives.swings import (
    compress_alternating_pivots,
    detect_fractal_pivots,
)

METHODOLOGY_VERSION = "price-action-structure/1"


def label_swings(swings: Sequence[ConfirmedPivot]) -> tuple[LabeledSwing, ...]:
    previous_high: ConfirmedPivot | None = None
    previous_low: ConfirmedPivot | None = None
    labeled: list[LabeledSwing] = []
    for pivot in swings:
        if pivot.kind is PivotKind.HIGH:
            relation = SwingRelation.UNCLASSIFIED
            if previous_high is not None:
                if pivot.price > previous_high.price:
                    relation = SwingRelation.HIGHER_HIGH
                elif pivot.price < previous_high.price:
                    relation = SwingRelation.LOWER_HIGH
                else:
                    relation = SwingRelation.EQUAL_HIGH
            previous_high = pivot
        else:
            relation = SwingRelation.UNCLASSIFIED
            if previous_low is not None:
                if pivot.price > previous_low.price:
                    relation = SwingRelation.HIGHER_LOW
                elif pivot.price < previous_low.price:
                    relation = SwingRelation.LOWER_LOW
                else:
                    relation = SwingRelation.EQUAL_LOW
            previous_low = pivot
        labeled.append(LabeledSwing(pivot=pivot, relation=relation))

    return tuple(labeled)


def _pivot_key(pivot: ConfirmedPivot) -> tuple[PivotKind, tuple[str, str, str, str, int]]:
    return pivot.kind, pivot.source_candle_identity
def detect_structure_breaks(
    candles: Sequence[Candle],
    swings: Sequence[ConfirmedPivot],
) -> tuple[tuple[StructureBreak, ...], StructureDirection]:
    if not candles:
        return (), StructureDirection.UNKNOWN

    broken: set[tuple[PivotKind, tuple[str, str, str, str, int]]] = set()
    events: list[StructureBreak] = []
    regime = StructureDirection.UNKNOWN
    ten_thousand = Decimal(10_000)

    for candle in candles:
        available = [
            pivot
            for pivot in swings
            if pivot.market_confirmed_at_ms <= candle.close_time_ms
            and pivot.open_time_ms < candle.open_time_ms
            and _pivot_key(pivot) not in broken
        ]
        highs = [pivot for pivot in available if pivot.kind is PivotKind.HIGH]
        lows = [pivot for pivot in available if pivot.kind is PivotKind.LOW]
        latest_high = max(highs, key=lambda pivot: pivot.candle_index, default=None)
        latest_low = max(lows, key=lambda pivot: pivot.candle_index, default=None)

        bullish_break = latest_high is not None and candle.close > latest_high.price
        bearish_break = latest_low is not None and candle.close < latest_low.price
        if bullish_break and bearish_break:
            raise ValueError("simultaneous opposing structure break is ambiguous")
        if not bullish_break and not bearish_break:
            continue
        direction = (
            StructureDirection.BULLISH if bullish_break else StructureDirection.BEARISH
        )
        broken_pivot = latest_high if bullish_break else latest_low
        if broken_pivot is None:
            raise AssertionError("break direction requires a broken pivot")

        kind = (
            StructureBreakKind.BOS
            if regime in {StructureDirection.UNKNOWN, direction}
            else StructureBreakKind.CHOCH_MSB
        )
        distance_bps = (
            abs(candle.close - broken_pivot.price) / broken_pivot.price
        ) * ten_thousand

        events.append(
            StructureBreak(
                kind=kind,
                direction=direction,
                broken_pivot=broken_pivot,
                break_candle_identity=candle.identity,
                break_close=candle.close,
                level_price=broken_pivot.price,
                distance_bps=distance_bps,
                market_confirmed_at_ms=candle.close_time_ms,
                observed_at_ms=candle.ingested_at_ms,
            )
        )
        broken.add(_pivot_key(broken_pivot))
        regime = direction

    return tuple(events), regime
def analyze_structure(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    as_of_ms: int | None = None,
) -> PriceActionStructureResult:
    if not candles:
        raise ValueError("price-action structure analysis requires candles")

    effective_as_of_ms = (
        max(candle.ingested_at_ms for candle in candles)
        if as_of_ms is None
        else as_of_ms
    )
    observed = tuple(
        candle
        for candle in candles
        if candle.close_time_ms <= effective_as_of_ms
        and candle.ingested_at_ms <= effective_as_of_ms
    )
    if not observed:
        raise ValueError("no candles were both closed and observed by as_of_ms")

    pivots = detect_fractal_pivots(
        observed,
        left_bars=left_bars,
        right_bars=right_bars,
    )
    alternating = compress_alternating_pivots(pivots)
    labeled = label_swings(alternating.swings)
    breaks, current_direction = detect_structure_breaks(observed, alternating.swings)

    periodic = []
    for period in Period:
        value = resolve_periodic_open(
            observed,
            period=period,
            as_of_ms=effective_as_of_ms,
        )
        if value is not None:
            periodic.append(value)
    first = observed[0]
    return PriceActionStructureResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        confirmed_pivots=pivots,
        labeled_swings=labeled,
        structure_breaks=breaks,
        current_direction=current_direction,
        periodic_opens=tuple(periodic),
        ambiguous_swing_source_indices=alternating.ambiguous_source_indices,
    )
