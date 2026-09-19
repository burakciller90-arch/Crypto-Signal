from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.methodologies.price_action.displacement import (
    DEFAULT_DISPLACEMENT_CONFIG,
    DisplacementAnalysisResult,
    DisplacementConfig,
    analyze_displacement,
)
from crypto_signal.methodologies.price_action.imbalances import (
    ImbalanceAnalysisResult,
    analyze_imbalances,
)
from crypto_signal.methodologies.price_action.interactions import (
    LevelInteractionAnalysisResult,
    ReferenceLevel,
    analyze_level_interactions,
    reference_level_from_periodic_open,
    reference_levels_from_range,
)
from crypto_signal.methodologies.price_action.levels import (
    PeriodSessionLevelsResult,
    SessionSpec,
    analyze_period_session_levels,
)
from crypto_signal.methodologies.price_action.liquidity import (
    DEFAULT_EQUAL_TOLERANCE_BPS,
    LiquidityAnalysisResult,
    LiquidityEventKind,
    analyze_liquidity,
)
from crypto_signal.methodologies.price_action.models import (
    PriceActionStructureResult,
    StructureDirection,
)
from crypto_signal.methodologies.price_action.structure import analyze_structure

METHODOLOGY_VERSION = "price-action-v1/1"


@dataclass(frozen=True, slots=True)
class PriceActionEvidenceSummary:
    current_structure_direction: StructureDirection
    structure_break_count: int
    fair_value_gap_count: int
    balanced_price_range_count: int
    liquidity_pool_count: int
    sfp_rejection_count: int
    displacement_count: int
    reference_level_count: int
    level_interaction_count: int


@dataclass(frozen=True, slots=True)
class PriceActionAnalysisResult:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    timeframe: str
    as_of_ms: int
    methodology_version: str
    structure: PriceActionStructureResult
    imbalances: ImbalanceAnalysisResult
    liquidity: LiquidityAnalysisResult
    levels: PeriodSessionLevelsResult
    displacement: DisplacementAnalysisResult
    level_interactions: LevelInteractionAnalysisResult
    reference_levels: tuple[ReferenceLevel, ...]
    summary: PriceActionEvidenceSummary


def _build_reference_levels(
    structure: PriceActionStructureResult,
    levels: PeriodSessionLevelsResult,
) -> tuple[ReferenceLevel, ...]:
    output: list[ReferenceLevel] = []

    for _, evidence in levels.previous_periods:
        output.extend(reference_levels_from_range(evidence))
    for evidence in levels.sessions:
        output.extend(reference_levels_from_range(evidence))
    for periodic_open in structure.periodic_opens:
        output.append(reference_level_from_periodic_open(periodic_open))

    identities = [
        (
            level.label,
            level.price,
            level.available_at_market_ms,
            level.observed_at_ms,
        )
        for level in output
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("integrated PA produced duplicate reference levels")

    output.sort(
        key=lambda level: (
            level.available_at_market_ms,
            level.observed_at_ms,
            level.label,
            level.price,
        )
    )
    return tuple(output)


def analyze_price_action(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    equal_tolerance_bps: Decimal = DEFAULT_EQUAL_TOLERANCE_BPS,
    displacement_config: DisplacementConfig = DEFAULT_DISPLACEMENT_CONFIG,
    sessions: Sequence[SessionSpec] = (),
    as_of_ms: int | None = None,
) -> PriceActionAnalysisResult:
    if not candles:
        raise ValueError("integrated price-action analysis requires candles")

    effective_as_of_ms = (
        max(candle.ingested_at_ms for candle in candles)
        if as_of_ms is None
        else as_of_ms
    )

    structure = analyze_structure(
        candles,
        left_bars=left_bars,
        right_bars=right_bars,
        as_of_ms=effective_as_of_ms,
    )
    imbalances = analyze_imbalances(
        candles,
        as_of_ms=effective_as_of_ms,
    )
    liquidity = analyze_liquidity(
        candles,
        left_bars=left_bars,
        right_bars=right_bars,
        equal_tolerance_bps=equal_tolerance_bps,
        as_of_ms=effective_as_of_ms,
    )
    levels = analyze_period_session_levels(
        candles,
        sessions=sessions,
        as_of_ms=effective_as_of_ms,
    )
    displacement = analyze_displacement(
        candles,
        config=displacement_config,
        as_of_ms=effective_as_of_ms,
    )

    reference_levels = _build_reference_levels(structure, levels)
    level_interactions = analyze_level_interactions(
        candles,
        reference_levels,
        as_of_ms=effective_as_of_ms,
    )

    nested_as_of = {
        structure.as_of_ms,
        imbalances.as_of_ms,
        liquidity.as_of_ms,
        levels.as_of_ms,
        displacement.as_of_ms,
        level_interactions.as_of_ms,
    }
    if nested_as_of != {effective_as_of_ms}:
        raise ValueError("integrated PA component as-of drift detected")
    first = candles[0]
    summary = PriceActionEvidenceSummary(
        current_structure_direction=structure.current_direction,
        structure_break_count=len(structure.structure_breaks),
        fair_value_gap_count=len(imbalances.fair_value_gaps),
        balanced_price_range_count=len(imbalances.balanced_price_ranges),
        liquidity_pool_count=len(liquidity.pools),
        sfp_rejection_count=sum(
            pool.event is not None
            and pool.event.kind is LiquidityEventKind.SFP_REJECTION
            for pool in liquidity.pools
        ),
        displacement_count=len(displacement.events),
        reference_level_count=len(reference_levels),
        level_interaction_count=len(level_interactions.events),
    )
    return PriceActionAnalysisResult(
        exchange=first.exchange,
        market_type=first.market_type,
        symbol=first.symbol,
        timeframe=first.timeframe,
        as_of_ms=effective_as_of_ms,
        methodology_version=METHODOLOGY_VERSION,
        structure=structure,
        imbalances=imbalances,
        liquidity=liquidity,
        levels=levels,
        displacement=displacement,
        level_interactions=level_interactions,
        reference_levels=reference_levels,
        summary=summary,
    )
