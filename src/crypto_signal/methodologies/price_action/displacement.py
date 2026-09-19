from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.data.timeframes import is_aligned_open, spec
from crypto_signal.methodologies.price_action.models import StructureDirection

METHODOLOGY_VERSION = "price-action-displacement/1"


@dataclass(frozen=True, slots=True)
class DisplacementConfig:
    lookback_bars: int = 20
    body_multiple: Decimal = Decimal("2.0")
    range_multiple: Decimal = Decimal("1.5")
    min_body_fraction: Decimal = Decimal("0.60")

    def __post_init__(self) -> None:
        if self.lookback_bars < 2:
            raise ValueError("displacement lookback must be at least 2")
        if self.body_multiple <= 0 or self.range_multiple <= 0:
            raise ValueError("displacement multiples must be positive")
        if not Decimal(0) < self.min_body_fraction <= Decimal(1):
            raise ValueError("min_body_fraction must be in (0, 1]")


DEFAULT_DISPLACEMENT_CONFIG = DisplacementConfig()


@dataclass(frozen=True, slots=True)
class DisplacementEvent:
    direction: StructureDirection
    candle_identity: tuple[str, str, str, str, int]
    body: Decimal
    total_range: Decimal
    body_fraction: Decimal
    baseline_median_body: Decimal
    baseline_median_range: Decimal
    observed_body_multiple: Decimal | None
    observed_range_multiple: Decimal | None
    baseline_first_candle_identity: tuple[str, str, str, str, int]
    baseline_last_candle_identity: tuple[str, str, str, str, int]
    market_confirmed_at_ms: int
    observed_at_ms: int


@dataclass(frozen=True, slots=True)
class DisplacementAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    config: DisplacementConfig
    events: tuple[DisplacementEvent, ...]


def _validate_candles(candles: Sequence[Candle]) -> None:
    if not candles:
        return
    first = candles[0]
    duration_ms = spec(first.timeframe).duration_ms
    previous_open_ms: int | None = None
    for candle in candles:
        if not candle.is_closed:
            raise ValueError("displacement analysis requires closed candles")
        if (
            candle.exchange != first.exchange
            or candle.market_type != first.market_type
            or candle.symbol != first.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("displacement analysis cannot mix candle semantics")
        if not is_aligned_open(candle.open_time_ms, first.timeframe):
            raise ValueError("displacement candle is off canonical timeframe grid")
        if previous_open_ms is not None and candle.open_time_ms - previous_open_ms != duration_ms:
            raise ValueError("displacement analysis requires gapless chronological candles")
        previous_open_ms = candle.open_time_ms


def _body(candle: Candle) -> Decimal:
    return abs(candle.close - candle.open)


def _range(candle: Candle) -> Decimal:
    return candle.high - candle.low


def detect_displacement(
    candles: Sequence[Candle],
    *,
    config: DisplacementConfig = DEFAULT_DISPLACEMENT_CONFIG,
) -> tuple[DisplacementEvent, ...]:
    _validate_candles(candles)
    if len(candles) <= config.lookback_bars:
        return ()

    events: list[DisplacementEvent] = []
    for index in range(config.lookback_bars, len(candles)):
        current = candles[index]
        body = _body(current)
        total_range = _range(current)
        if body == 0 or total_range <= 0:
            continue

        baseline = candles[index - config.lookback_bars : index]
        median_body = median([_body(candle) for candle in baseline])
        median_range = median([_range(candle) for candle in baseline])
        body_fraction = body / total_range

        if body < median_body * config.body_multiple:
            continue
        if total_range < median_range * config.range_multiple:
            continue
        if body_fraction < config.min_body_fraction:
            continue

        direction = (
            StructureDirection.BULLISH
            if current.close > current.open
            else StructureDirection.BEARISH
        )
        events.append(
            DisplacementEvent(
                direction=direction,
                candle_identity=current.identity,
                body=body,
                total_range=total_range,
                body_fraction=body_fraction,
                baseline_median_body=median_body,
                baseline_median_range=median_range,
                observed_body_multiple=(
                    None if median_body == 0 else body / median_body
                ),
                observed_range_multiple=(
                    None if median_range == 0 else total_range / median_range
                ),
                baseline_first_candle_identity=baseline[0].identity,
                baseline_last_candle_identity=baseline[-1].identity,
                market_confirmed_at_ms=current.close_time_ms,
                observed_at_ms=current.ingested_at_ms,
            )
        )

    return tuple(events)


def analyze_displacement(
    candles: Sequence[Candle],
    *,
    config: DisplacementConfig = DEFAULT_DISPLACEMENT_CONFIG,
    as_of_ms: int | None = None,
) -> DisplacementAnalysisResult:
    if not candles:
        raise ValueError("displacement analysis requires candles")

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

    events = detect_displacement(observed, config=config)
    first = observed[0]
    return DisplacementAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        config=config,
        events=events,
    )
