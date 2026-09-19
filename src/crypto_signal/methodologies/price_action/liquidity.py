from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.data.timeframes import is_aligned_open, spec
from crypto_signal.methodologies.price_action.models import StructureDirection
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind
from crypto_signal.primitives.swings import (
    compress_alternating_pivots,
    detect_fractal_pivots,
)

DEFAULT_EQUAL_TOLERANCE_BPS = Decimal(5)
METHODOLOGY_VERSION = "price-action-liquidity/1"


class LiquidityPoolKind(StrEnum):
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"


class LiquidityPoolStatus(StrEnum):
    AVAILABLE = "available"
    SWEPT_SFP = "swept_sfp"
    BROKEN_CLOSE = "broken_close"


class LiquidityEventKind(StrEnum):
    SFP_REJECTION = "sfp_rejection"
    CLOSE_THROUGH = "close_through"


LiquidityPoolIdentity = tuple[str, str, str, str, str, int, int]


@dataclass(frozen=True, slots=True)
class LiquidityEvent:
    kind: LiquidityEventKind
    implication_direction: StructureDirection
    candle_identity: tuple[str, str, str, str, int]
    boundary_price: Decimal
    extreme_price: Decimal
    close_price: Decimal
    excursion_bps: Decimal
    close_recovery_bps: Decimal
    market_confirmed_at_ms: int
    observed_at_ms: int


@dataclass(frozen=True, slots=True)
class LiquidityPool:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    kind: LiquidityPoolKind
    first_anchor: ConfirmedPivot
    second_anchor: ConfirmedPivot
    zone_low: Decimal
    zone_high: Decimal
    level_price: Decimal
    equal_tolerance_bps: Decimal
    pair_distance_bps: Decimal
    formed_at_market_ms: int
    formed_observed_at_ms: int
    status: LiquidityPoolStatus = LiquidityPoolStatus.AVAILABLE
    event: LiquidityEvent | None = None

    def __post_init__(self) -> None:
        if self.zone_low <= 0 or self.zone_high < self.zone_low:
            raise ValueError("liquidity pool zone is invalid")
        if self.equal_tolerance_bps < 0:
            raise ValueError("equal tolerance must be non-negative")
        if self.pair_distance_bps < 0:
            raise ValueError("pair distance must be non-negative")
        if self.pair_distance_bps > self.equal_tolerance_bps:
            raise ValueError("pool anchors exceed configured tolerance")
        if self.formed_observed_at_ms < self.formed_at_market_ms:
            raise ValueError("pool cannot be observed before market formation")

    @property
    def identity(self) -> LiquidityPoolIdentity:
        return (
            self.exchange.value,
            self.market_type.value,
            self.symbol,
            self.timeframe,
            self.kind.value,
            self.first_anchor.open_time_ms,
            self.second_anchor.open_time_ms,
        )


@dataclass(frozen=True, slots=True)
class LiquidityAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    equal_tolerance_bps: Decimal
    pools: tuple[LiquidityPool, ...]
    ambiguous_swing_source_indices: tuple[int, ...]


def _validate_candles(candles: Sequence[Candle]) -> None:
    if not candles:
        return

    first = candles[0]
    duration_ms = spec(first.timeframe).duration_ms
    previous_open_ms: int | None = None

    for candle in candles:
        if not candle.is_closed:
            raise ValueError("liquidity analysis requires closed candles")
        if (
            candle.exchange != first.exchange
            or candle.market_type != first.market_type
            or candle.symbol != first.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("liquidity analysis cannot mix candle semantics")
        if not is_aligned_open(candle.open_time_ms, first.timeframe):
            raise ValueError("liquidity candle is off canonical timeframe grid")
        if previous_open_ms is not None and candle.open_time_ms - previous_open_ms != duration_ms:
            raise ValueError("liquidity analysis requires gapless chronological candles")
        previous_open_ms = candle.open_time_ms


def _distance_bps(left: Decimal, right: Decimal) -> Decimal:
    midpoint = (left + right) / Decimal(2)
    return (abs(left - right) / midpoint) * Decimal(10_000)


def _validate_swings(swings: Sequence[ConfirmedPivot]) -> None:
    if not swings:
        return

    first = swings[0]
    previous_index = -1
    for pivot in swings:
        if (
            pivot.exchange != first.exchange
            or pivot.market_type != first.market_type
            or pivot.symbol != first.symbol
            or pivot.timeframe != first.timeframe
        ):
            raise ValueError("liquidity pool detection cannot mix pivot semantics")
        if pivot.candle_index <= previous_index:
            raise ValueError("liquidity pivots must be chronological and unique")
        previous_index = pivot.candle_index


def detect_liquidity_pools(
    swings: Sequence[ConfirmedPivot],
    *,
    equal_tolerance_bps: Decimal = DEFAULT_EQUAL_TOLERANCE_BPS,
) -> tuple[LiquidityPool, ...]:
    if equal_tolerance_bps < 0:
        raise ValueError("equal_tolerance_bps must be non-negative")
    _validate_swings(swings)
    if not swings:
        return ()

    first = swings[0]
    output: list[LiquidityPool] = []

    for pivot_kind, pool_kind in (
        (PivotKind.HIGH, LiquidityPoolKind.EQUAL_HIGHS),
        (PivotKind.LOW, LiquidityPoolKind.EQUAL_LOWS),
    ):
        same_kind = [pivot for pivot in swings if pivot.kind is pivot_kind]
        for left, right in pairwise(same_kind):
            distance = _distance_bps(left.price, right.price)
            if distance > equal_tolerance_bps:
                continue

            zone_low = min(left.price, right.price)
            zone_high = max(left.price, right.price)
            output.append(
                LiquidityPool(
                    exchange=first.exchange,
                    market_type=first.market_type,
                    symbol=first.symbol,
                    timeframe=first.timeframe,
                    kind=pool_kind,
                    first_anchor=left,
                    second_anchor=right,
                    zone_low=zone_low,
                    zone_high=zone_high,
                    level_price=(left.price + right.price) / Decimal(2),
                    equal_tolerance_bps=equal_tolerance_bps,
                    pair_distance_bps=distance,
                    formed_at_market_ms=right.market_confirmed_at_ms,
                    formed_observed_at_ms=right.observed_at_ms,
                )
            )

    output.sort(
        key=lambda pool: (
            pool.formed_at_market_ms,
            pool.second_anchor.candle_index,
            pool.kind.value,
        )
    )
    return tuple(output)


def evaluate_liquidity_pool(
    pool: LiquidityPool,
    candles: Sequence[Candle],
) -> LiquidityPool:
    _validate_candles(candles)
    if not candles:
        return pool

    first = candles[0]
    if (
        pool.exchange != first.exchange
        or pool.market_type != first.market_type
        or pool.symbol != first.symbol
        or pool.timeframe != first.timeframe
    ):
        raise ValueError("liquidity lifecycle cannot mix candle semantics")

    for candle in candles:
        if candle.close_time_ms <= pool.formed_at_market_ms:
            continue

        if pool.kind is LiquidityPoolKind.EQUAL_HIGHS:
            boundary = pool.zone_high
            if candle.high <= boundary:
                continue

            sfp = candle.close <= boundary
            event = LiquidityEvent(
                kind=(
                    LiquidityEventKind.SFP_REJECTION
                    if sfp
                    else LiquidityEventKind.CLOSE_THROUGH
                ),
                implication_direction=(
                    StructureDirection.BEARISH
                    if sfp
                    else StructureDirection.BULLISH
                ),
                candle_identity=candle.identity,
                boundary_price=boundary,
                extreme_price=candle.high,
                close_price=candle.close,
                excursion_bps=((candle.high - boundary) / boundary) * Decimal(10_000),
                close_recovery_bps=((boundary - candle.close) / boundary) * Decimal(10_000),
                market_confirmed_at_ms=candle.close_time_ms,
                observed_at_ms=candle.ingested_at_ms,
            )
        else:
            boundary = pool.zone_low
            if candle.low >= boundary:
                continue

            sfp = candle.close >= boundary
            event = LiquidityEvent(
                kind=(
                    LiquidityEventKind.SFP_REJECTION
                    if sfp
                    else LiquidityEventKind.CLOSE_THROUGH
                ),
                implication_direction=(
                    StructureDirection.BULLISH
                    if sfp
                    else StructureDirection.BEARISH
                ),
                candle_identity=candle.identity,
                boundary_price=boundary,
                extreme_price=candle.low,
                close_price=candle.close,
                excursion_bps=((boundary - candle.low) / boundary) * Decimal(10_000),
                close_recovery_bps=((candle.close - boundary) / boundary) * Decimal(10_000),
                market_confirmed_at_ms=candle.close_time_ms,
                observed_at_ms=candle.ingested_at_ms,
            )

        return replace(
            pool,
            status=(
                LiquidityPoolStatus.SWEPT_SFP
                if event.kind is LiquidityEventKind.SFP_REJECTION
                else LiquidityPoolStatus.BROKEN_CLOSE
            ),
            event=event,
        )

    return pool


def analyze_liquidity(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    equal_tolerance_bps: Decimal = DEFAULT_EQUAL_TOLERANCE_BPS,
    as_of_ms: int | None = None,
) -> LiquidityAnalysisResult:
    if not candles:
        raise ValueError("liquidity analysis requires candles")

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

    _validate_candles(observed)
    pivots = detect_fractal_pivots(
        observed,
        left_bars=left_bars,
        right_bars=right_bars,
    )
    alternating = compress_alternating_pivots(pivots)
    raw_pools = detect_liquidity_pools(
        alternating.swings,
        equal_tolerance_bps=equal_tolerance_bps,
    )
    pools = tuple(evaluate_liquidity_pool(pool, observed) for pool in raw_pools)

    first = observed[0]
    return LiquidityAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        equal_tolerance_bps=equal_tolerance_bps,
        pools=pools,
        ambiguous_swing_source_indices=alternating.ambiguous_source_indices,
    )
