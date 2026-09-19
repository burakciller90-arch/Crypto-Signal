from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.data.periodic_opens import PeriodicOpen
from crypto_signal.data.timeframes import spec
from crypto_signal.methodologies.price_action.levels import HighLowRangeEvidence
from crypto_signal.methodologies.price_action.models import StructureDirection

METHODOLOGY_VERSION = "price-action-level-interactions/1"


class LevelInteractionKind(StrEnum):
    BULLISH_RECLAIM = "bullish_reclaim"
    BEARISH_RECLAIM = "bearish_reclaim"
    BULLISH_REJECTION = "bullish_rejection"
    BEARISH_REJECTION = "bearish_rejection"
    AMBIGUOUS_TWO_SIDED = "ambiguous_two_sided"


@dataclass(frozen=True, slots=True)
class ReferenceLevel:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    label: str
    price: Decimal
    available_at_market_ms: int
    observed_at_ms: int
    source_description: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("reference level label must be non-empty")
        if self.price <= 0:
            raise ValueError("reference level price must be positive")
        if self.observed_at_ms < self.available_at_market_ms:
            raise ValueError("reference level cannot be observed before market availability")


@dataclass(frozen=True, slots=True)
class LevelInteractionEvent:
    level: ReferenceLevel
    kind: LevelInteractionKind
    implication_direction: StructureDirection
    previous_candle_identity: tuple[str, str, str, str, int]
    candle_identity: tuple[str, str, str, str, int]
    candle_high: Decimal
    candle_low: Decimal
    candle_close: Decimal
    high_excursion_bps: Decimal
    low_excursion_bps: Decimal
    close_offset_bps: Decimal
    market_confirmed_at_ms: int
    observed_at_ms: int


@dataclass(frozen=True, slots=True)
class LevelInteractionAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    levels: tuple[ReferenceLevel, ...]
    events: tuple[LevelInteractionEvent, ...]


def reference_levels_from_range(
    evidence: HighLowRangeEvidence,
) -> tuple[ReferenceLevel, ...]:
    if not evidence.complete:
        return ()
    if (
        evidence.high is None
        or evidence.low is None
        or evidence.observed_at_ms is None
    ):
        raise ValueError("complete range evidence is missing numeric truth")

    return (
        ReferenceLevel(
            exchange=evidence.exchange,
            market_type=evidence.market_type,
            symbol=evidence.symbol,
            timeframe=evidence.timeframe,
            label=f"{evidence.label}:high",
            price=evidence.high,
            available_at_market_ms=evidence.market_complete_at_ms,
            observed_at_ms=evidence.observed_at_ms,
            source_description=evidence.label,
        ),
        ReferenceLevel(
            exchange=evidence.exchange,
            market_type=evidence.market_type,
            symbol=evidence.symbol,
            timeframe=evidence.timeframe,
            label=f"{evidence.label}:low",
            price=evidence.low,
            available_at_market_ms=evidence.market_complete_at_ms,
            observed_at_ms=evidence.observed_at_ms,
            source_description=evidence.label,
        ),
    )


def reference_level_from_periodic_open(value: PeriodicOpen) -> ReferenceLevel:
    exchange, market_type, symbol, timeframe, _ = value.source_candle_identity
    return ReferenceLevel(
        exchange=Exchange(exchange),
        market_type=MarketType(market_type),
        symbol=symbol,
        timeframe=timeframe,
        label=f"{value.period.value}_open",
        price=value.price,
        available_at_market_ms=value.market_available_from_ms,
        observed_at_ms=value.observed_at_ms,
        source_description=f"{value.period.value}_open",
    )


def _validate_candles(candles: Sequence[Candle]) -> None:
    if not candles:
        return

    first = candles[0]
    duration_ms = spec(first.timeframe).duration_ms
    previous_open_ms: int | None = None
    for candle in candles:
        if not candle.is_closed:
            raise ValueError("level interaction analysis requires closed candles")
        if (
            candle.exchange != first.exchange
            or candle.market_type != first.market_type
            or candle.symbol != first.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("level interaction analysis cannot mix candle semantics")
        if candle.open_time_ms % duration_ms != 0:
            raise ValueError("level interaction candle is off canonical timeframe grid")
        if previous_open_ms is not None and candle.open_time_ms - previous_open_ms != duration_ms:
            raise ValueError("level interaction analysis requires gapless chronological candles")
        previous_open_ms = candle.open_time_ms


def _event_for_pair(
    previous: Candle,
    current: Candle,
    level: ReferenceLevel,
) -> LevelInteractionEvent | None:
    price = level.price
    trades_level = current.low <= price <= current.high

    bullish_reclaim = previous.close < price and trades_level and current.close > price
    bearish_reclaim = previous.close > price and trades_level and current.close < price
    bullish_rejection = (
        previous.close >= price
        and current.low < price
        and current.close >= price
    )
    bearish_rejection = (
        previous.close <= price
        and current.high > price
        and current.close <= price
    )

    candidates = [
        bullish_reclaim,
        bearish_reclaim,
        bullish_rejection,
        bearish_rejection,
    ]
    match_count = sum(candidates)
    if match_count == 0:
        return None

    if match_count > 1:
        kind = LevelInteractionKind.AMBIGUOUS_TWO_SIDED
        direction = StructureDirection.UNKNOWN
    elif bullish_reclaim:
        kind = LevelInteractionKind.BULLISH_RECLAIM
        direction = StructureDirection.BULLISH
    elif bearish_reclaim:
        kind = LevelInteractionKind.BEARISH_RECLAIM
        direction = StructureDirection.BEARISH
    elif bullish_rejection:
        kind = LevelInteractionKind.BULLISH_REJECTION
        direction = StructureDirection.BULLISH
    else:
        kind = LevelInteractionKind.BEARISH_REJECTION
        direction = StructureDirection.BEARISH

    return LevelInteractionEvent(
        level=level,
        kind=kind,
        implication_direction=direction,
        previous_candle_identity=previous.identity,
        candle_identity=current.identity,
        candle_high=current.high,
        candle_low=current.low,
        candle_close=current.close,
        high_excursion_bps=max(
            Decimal(0),
            ((current.high - price) / price) * Decimal(10_000),
        ),
        low_excursion_bps=max(
            Decimal(0),
            ((price - current.low) / price) * Decimal(10_000),
        ),
        close_offset_bps=((current.close - price) / price) * Decimal(10_000),
        market_confirmed_at_ms=current.close_time_ms,
        observed_at_ms=current.ingested_at_ms,
    )


def detect_level_interactions(
    candles: Sequence[Candle],
    levels: Sequence[ReferenceLevel],
) -> tuple[LevelInteractionEvent, ...]:
    _validate_candles(candles)
    if not candles or not levels:
        return ()

    first = candles[0]
    events: list[LevelInteractionEvent] = []
    for level in levels:
        if (
            level.exchange != first.exchange
            or level.market_type != first.market_type
            or level.symbol != first.symbol
            or level.timeframe != first.timeframe
        ):
            raise ValueError("reference level does not match candle semantics")

        for previous, current in pairwise(candles):
            if current.close_time_ms <= level.available_at_market_ms:
                continue
            if current.ingested_at_ms < level.observed_at_ms:
                continue
            event = _event_for_pair(previous, current, level)
            if event is not None:
                events.append(event)

    events.sort(
        key=lambda event: (
            event.market_confirmed_at_ms,
            event.level.label,
            event.kind.value,
        )
    )
    return tuple(events)


def analyze_level_interactions(
    candles: Sequence[Candle],
    levels: Sequence[ReferenceLevel],
    *,
    as_of_ms: int | None = None,
) -> LevelInteractionAnalysisResult:
    if not candles:
        raise ValueError("level interaction analysis requires candles")

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

    available_levels = tuple(
        level
        for level in levels
        if level.available_at_market_ms <= effective_as_of_ms
        and level.observed_at_ms <= effective_as_of_ms
    )
    events = detect_level_interactions(observed, available_levels)
    first = observed[0]
    return LevelInteractionAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        levels=available_levels,
        events=events,
    )
