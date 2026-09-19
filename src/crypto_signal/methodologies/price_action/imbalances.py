from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.data.timeframes import spec


class FVGDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class FVGStatus(StrEnum):
    OPEN = "open"
    MITIGATED = "mitigated"
    FILLED = "filled"


class BPRStatus(StrEnum):
    OPEN = "open"
    MITIGATED = "mitigated"
    TRAVERSED = "traversed"


FVGIdentity = tuple[str, str, str, str, int, str]


@dataclass(frozen=True, slots=True)
class FairValueGap:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    direction: FVGDirection
    confirmation_index: int
    first_candle_identity: tuple[str, str, str, str, int]
    middle_candle_identity: tuple[str, str, str, str, int]
    confirmation_candle_identity: tuple[str, str, str, str, int]
    zone_low: Decimal
    zone_high: Decimal
    size_bps: Decimal
    created_at_market_ms: int
    observed_at_ms: int
    status: FVGStatus = FVGStatus.OPEN
    first_touch_candle_identity: tuple[str, str, str, str, int] | None = None
    first_touch_market_ms: int | None = None
    first_touch_observed_at_ms: int | None = None
    filled_candle_identity: tuple[str, str, str, str, int] | None = None
    filled_at_market_ms: int | None = None
    filled_observed_at_ms: int | None = None
    max_fill_fraction: Decimal = Decimal(0)
    gap_through_ambiguity: bool = False

    def __post_init__(self) -> None:
        if self.confirmation_index < 2:
            raise ValueError("FVG confirmation index must be at least 2")
        if self.zone_low <= 0 or self.zone_high <= self.zone_low:
            raise ValueError("FVG zone must have positive width")
        if self.size_bps <= 0:
            raise ValueError("FVG size_bps must be positive")
        if not Decimal(0) <= self.max_fill_fraction <= Decimal(1):
            raise ValueError("FVG fill fraction must be between 0 and 1")
        if self.observed_at_ms < self.created_at_market_ms:
            raise ValueError("FVG cannot be observed before market creation")

    @property
    def identity(self) -> FVGIdentity:
        return (
            self.exchange.value,
            self.market_type.value,
            self.symbol,
            self.timeframe,
            self.confirmation_candle_identity[-1],
            self.direction.value,
        )


@dataclass(frozen=True, slots=True)
class BalancedPriceRange:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    bullish_fvg_identity: FVGIdentity
    bearish_fvg_identity: FVGIdentity
    later_confirmation_index: int
    zone_low: Decimal
    zone_high: Decimal
    size_bps: Decimal
    created_at_market_ms: int
    observed_at_ms: int
    status: BPRStatus = BPRStatus.OPEN
    first_touch_candle_identity: tuple[str, str, str, str, int] | None = None
    first_touch_market_ms: int | None = None
    first_touch_observed_at_ms: int | None = None
    traversed_candle_identity: tuple[str, str, str, str, int] | None = None
    traversed_at_market_ms: int | None = None
    traversed_observed_at_ms: int | None = None

    def __post_init__(self) -> None:
        if self.zone_low <= 0 or self.zone_high <= self.zone_low:
            raise ValueError("BPR zone must have positive width")
        if self.size_bps <= 0:
            raise ValueError("BPR size_bps must be positive")
        if self.observed_at_ms < self.created_at_market_ms:
            raise ValueError("BPR cannot be observed before market creation")


@dataclass(frozen=True, slots=True)
class ImbalanceAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    fair_value_gaps: tuple[FairValueGap, ...]
    balanced_price_ranges: tuple[BalancedPriceRange, ...]


METHODOLOGY_VERSION = "price-action-imbalances/1"


def _validate_series(candles: Sequence[Candle]) -> None:
    if not candles:
        return

    first = candles[0]
    duration_ms = spec(first.timeframe).duration_ms
    previous_open_ms: int | None = None

    for candle in candles:
        if not candle.is_closed:
            raise ValueError("FVG analysis requires closed candles")
        if (
            candle.exchange != first.exchange
            or candle.market_type != first.market_type
            or candle.symbol != first.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("FVG analysis cannot mix candle semantics")
        if candle.open_time_ms % duration_ms != 0:
            raise ValueError("FVG candle is off the canonical timeframe grid")
        if candle.close_time_ms != candle.open_time_ms + duration_ms - 1:
            raise ValueError("FVG candle bounds do not match timeframe duration")
        if previous_open_ms is not None and candle.open_time_ms - previous_open_ms != duration_ms:
            raise ValueError("FVG analysis requires a gapless chronological series")
        previous_open_ms = candle.open_time_ms


def _size_bps(zone_low: Decimal, zone_high: Decimal) -> Decimal:
    midpoint = (zone_low + zone_high) / Decimal(2)
    return ((zone_high - zone_low) / midpoint) * Decimal(10_000)


def detect_fvg_formations(candles: Sequence[Candle]) -> tuple[FairValueGap, ...]:
    _validate_series(candles)
    if len(candles) < 3:
        return ()

    formations: list[FairValueGap] = []
    first_semantic = candles[0]

    for index in range(2, len(candles)):
        first = candles[index - 2]
        middle = candles[index - 1]
        confirmation = candles[index]
        observed_at_ms = max(first.ingested_at_ms, middle.ingested_at_ms, confirmation.ingested_at_ms)

        direction: FVGDirection | None = None
        zone_low: Decimal | None = None
        zone_high: Decimal | None = None
        if first.high < confirmation.low:
            direction = FVGDirection.BULLISH
            zone_low = first.high
            zone_high = confirmation.low
        elif first.low > confirmation.high:
            direction = FVGDirection.BEARISH
            zone_low = confirmation.high
            zone_high = first.low

        if direction is None or zone_low is None or zone_high is None:
            continue

        formations.append(
            FairValueGap(
                exchange=first_semantic.exchange,
                market_type=first_semantic.market_type,
                symbol=first_semantic.symbol,
                timeframe=first_semantic.timeframe,
                direction=direction,
                confirmation_index=index,
                first_candle_identity=first.identity,
                middle_candle_identity=middle.identity,
                confirmation_candle_identity=confirmation.identity,
                zone_low=zone_low,
                zone_high=zone_high,
                size_bps=_size_bps(zone_low, zone_high),
                created_at_market_ms=confirmation.close_time_ms,
                observed_at_ms=observed_at_ms,
            )
        )

    return tuple(formations)


def _overlaps(candle: Candle, zone_low: Decimal, zone_high: Decimal) -> bool:
    return candle.high >= zone_low and candle.low <= zone_high


def evaluate_fvg_lifecycle(
    fvg: FairValueGap,
    candles: Sequence[Candle],
) -> FairValueGap:
    _validate_series(candles)
    if not candles:
        return fvg

    first = candles[0]
    if (
        fvg.exchange != first.exchange
        or fvg.market_type != first.market_type
        or fvg.symbol != first.symbol
        or fvg.timeframe != first.timeframe
    ):
        raise ValueError("FVG lifecycle cannot mix candle semantics")
    if fvg.confirmation_index >= len(candles):
        raise ValueError("FVG confirmation index is outside candle series")
    if candles[fvg.confirmation_index].identity != fvg.confirmation_candle_identity:
        raise ValueError("FVG confirmation identity does not match candle series")

    width = fvg.zone_high - fvg.zone_low
    first_touch_identity = fvg.first_touch_candle_identity
    first_touch_market_ms = fvg.first_touch_market_ms
    first_touch_observed_at_ms = fvg.first_touch_observed_at_ms
    filled_identity = fvg.filled_candle_identity
    filled_market_ms = fvg.filled_at_market_ms
    filled_observed_at_ms = fvg.filled_observed_at_ms
    max_fill_fraction = fvg.max_fill_fraction
    gap_through_ambiguity = fvg.gap_through_ambiguity

    for candle in candles[fvg.confirmation_index + 1 :]:
        if filled_identity is not None:
            break

        if fvg.direction is FVGDirection.BULLISH:
            if candle.high < fvg.zone_low:
                gap_through_ambiguity = True
            if not _overlaps(candle, fvg.zone_low, fvg.zone_high):
                continue

            if first_touch_identity is None:
                first_touch_identity = candle.identity
                first_touch_market_ms = candle.close_time_ms
                first_touch_observed_at_ms = candle.ingested_at_ms

            deepest = max(candle.low, fvg.zone_low)
            fraction = (fvg.zone_high - deepest) / width
            max_fill_fraction = max(max_fill_fraction, fraction)

            if candle.low <= fvg.zone_low <= candle.high:
                filled_identity = candle.identity
                filled_market_ms = candle.close_time_ms
                filled_observed_at_ms = candle.ingested_at_ms
                max_fill_fraction = Decimal(1)
        else:
            if candle.low > fvg.zone_high:
                gap_through_ambiguity = True
            if not _overlaps(candle, fvg.zone_low, fvg.zone_high):
                continue

            if first_touch_identity is None:
                first_touch_identity = candle.identity
                first_touch_market_ms = candle.close_time_ms
                first_touch_observed_at_ms = candle.ingested_at_ms

            deepest = min(candle.high, fvg.zone_high)
            fraction = (deepest - fvg.zone_low) / width
            max_fill_fraction = max(max_fill_fraction, fraction)

            if candle.low <= fvg.zone_high <= candle.high:
                filled_identity = candle.identity
                filled_market_ms = candle.close_time_ms
                filled_observed_at_ms = candle.ingested_at_ms
                max_fill_fraction = Decimal(1)

    status = (
        FVGStatus.FILLED
        if filled_identity is not None
        else FVGStatus.MITIGATED
        if first_touch_identity is not None
        else FVGStatus.OPEN
    )
    return replace(
        fvg,
        status=status,
        first_touch_candle_identity=first_touch_identity,
        first_touch_market_ms=first_touch_market_ms,
        first_touch_observed_at_ms=first_touch_observed_at_ms,
        filled_candle_identity=filled_identity,
        filled_at_market_ms=filled_market_ms,
        filled_observed_at_ms=filled_observed_at_ms,
        max_fill_fraction=max_fill_fraction,
        gap_through_ambiguity=gap_through_ambiguity,
    )


def _evaluate_bpr_lifecycle(
    bpr: BalancedPriceRange,
    candles: Sequence[Candle],
) -> BalancedPriceRange:
    first_touch_identity = bpr.first_touch_candle_identity
    first_touch_market_ms = bpr.first_touch_market_ms
    first_touch_observed_at_ms = bpr.first_touch_observed_at_ms
    traversed_identity = bpr.traversed_candle_identity
    traversed_market_ms = bpr.traversed_at_market_ms
    traversed_observed_at_ms = bpr.traversed_observed_at_ms

    for candle in candles[bpr.later_confirmation_index + 1 :]:
        if traversed_identity is not None:
            break
        if not _overlaps(candle, bpr.zone_low, bpr.zone_high):
            continue

        if first_touch_identity is None:
            first_touch_identity = candle.identity
            first_touch_market_ms = candle.close_time_ms
            first_touch_observed_at_ms = candle.ingested_at_ms

        if candle.low <= bpr.zone_low and candle.high >= bpr.zone_high:
            traversed_identity = candle.identity
            traversed_market_ms = candle.close_time_ms
            traversed_observed_at_ms = candle.ingested_at_ms

    status = (
        BPRStatus.TRAVERSED
        if traversed_identity is not None
        else BPRStatus.MITIGATED
        if first_touch_identity is not None
        else BPRStatus.OPEN
    )
    return replace(
        bpr,
        status=status,
        first_touch_candle_identity=first_touch_identity,
        first_touch_market_ms=first_touch_market_ms,
        first_touch_observed_at_ms=first_touch_observed_at_ms,
        traversed_candle_identity=traversed_identity,
        traversed_at_market_ms=traversed_market_ms,
        traversed_observed_at_ms=traversed_observed_at_ms,
    )


def detect_balanced_price_ranges(
    fvgs: Sequence[FairValueGap],
    candles: Sequence[Candle],
) -> tuple[BalancedPriceRange, ...]:
    _validate_series(candles)
    if not fvgs:
        return ()

    identities = [fvg.identity for fvg in fvgs]
    if len(set(identities)) != len(identities):
        raise ValueError("BPR detection received duplicate FVG identities")

    ordered = sorted(
        fvgs,
        key=lambda item: (
            item.created_at_market_ms,
            item.confirmation_index,
            item.direction.value,
        ),
    )
    output: list[BalancedPriceRange] = []
    for later_index, later in enumerate(ordered):
        for earlier in ordered[:later_index]:
            if earlier.direction is later.direction:
                continue
            if earlier.created_at_market_ms == later.created_at_market_ms:
                continue
            if (
                earlier.exchange != later.exchange
                or earlier.market_type != later.market_type
                or earlier.symbol != later.symbol
                or earlier.timeframe != later.timeframe
            ):
                raise ValueError("BPR detection cannot mix FVG semantics")

            overlap_low = max(earlier.zone_low, later.zone_low)
            overlap_high = min(earlier.zone_high, later.zone_high)
            if overlap_low >= overlap_high:
                continue

            if (
                earlier.filled_at_market_ms is not None
                and earlier.filled_at_market_ms <= later.created_at_market_ms
            ):
                continue

            bullish = (
                earlier if earlier.direction is FVGDirection.BULLISH else later
            )
            bearish = (
                earlier if earlier.direction is FVGDirection.BEARISH else later
            )
            created_at_market_ms = later.created_at_market_ms
            observed_at_ms = max(earlier.observed_at_ms, later.observed_at_ms)

            raw = BalancedPriceRange(
                exchange=later.exchange,
                market_type=later.market_type,
                symbol=later.symbol,
                timeframe=later.timeframe,
                bullish_fvg_identity=bullish.identity,
                bearish_fvg_identity=bearish.identity,
                later_confirmation_index=later.confirmation_index,
                zone_low=overlap_low,
                zone_high=overlap_high,
                size_bps=_size_bps(overlap_low, overlap_high),
                created_at_market_ms=created_at_market_ms,
                observed_at_ms=observed_at_ms,
            )
            output.append(_evaluate_bpr_lifecycle(raw, candles))

    return tuple(output)


def analyze_imbalances(
    candles: Sequence[Candle],
    *,
    as_of_ms: int | None = None,
) -> ImbalanceAnalysisResult:
    if not candles:
        raise ValueError("imbalance analysis requires candles")

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

    _validate_series(observed)
    formations = detect_fvg_formations(observed)
    fvgs = tuple(evaluate_fvg_lifecycle(fvg, observed) for fvg in formations)
    bprs = detect_balanced_price_ranges(fvgs, observed)

    first = observed[0]
    return ImbalanceAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        fair_value_gaps=fvgs,
        balanced_price_ranges=bprs,
    )
