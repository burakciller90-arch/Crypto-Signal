from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

from crypto_signal.confluence.models import (
    ConfluenceAnalysisResult,
    ConfluenceScore,
    EvidenceDirection,
    MethodologyEvidence,
    MethodologyPairRelation,
    MethodologySelection,
    PairRelation,
)
from crypto_signal.confluence.selection import build_methodology_selections
from crypto_signal.data.models import Exchange, MarketType

_SCORE_QUANTUM = Decimal("0.01")


def _validate_context(
    evidence: Sequence[MethodologyEvidence],
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    timeframe: str,
    as_of_ms: int,
) -> None:
    if not symbol.strip() or not timeframe.strip():
        raise ValueError("confluence context symbol/timeframe must be non-empty")
    if as_of_ms < 0:
        raise ValueError("confluence as_of_ms must be non-negative")

    for item in evidence:
        if (
            item.exchange != exchange
            or item.market_type != market_type
            or item.symbol != symbol
            or item.timeframe != timeframe
            or item.as_of_ms != as_of_ms
        ):
            raise ValueError("confluence evidence context mismatch")


def _pair_relation(
    left: MethodologySelection,
    right: MethodologySelection,
) -> MethodologyPairRelation:
    if (
        left.has_internal_direction_conflict
        or right.has_internal_direction_conflict
    ):
        relation = PairRelation.INTERNAL_AMBIGUITY
    elif (
        left.resolved_direction is EvidenceDirection.UNRESOLVED
        or right.resolved_direction is EvidenceDirection.UNRESOLVED
    ):
        relation = PairRelation.INSUFFICIENT
    elif left.resolved_direction is right.resolved_direction:
        relation = PairRelation.AGREE
    else:
        relation = PairRelation.CONTRADICT

    return MethodologyPairRelation(
        left=left.methodology,
        right=right.methodology,
        relation=relation,
        left_direction=left.resolved_direction,
        right_direction=right.resolved_direction,
    )


def build_pairwise_relations(
    selections: Sequence[MethodologySelection],
) -> tuple[MethodologyPairRelation, ...]:
    return tuple(
        _pair_relation(left, right)
        for left, right in combinations(selections, 2)
    )


def _score(
    selections: Sequence[MethodologySelection],
) -> tuple[EvidenceDirection, ConfluenceScore]:
    votes = Counter(
        selection.resolved_direction
        for selection in selections
        if selection.resolved_direction
        in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}
    )
    bullish = votes[EvidenceDirection.BULLISH]
    bearish = votes[EvidenceDirection.BEARISH]
    resolved = bullish + bearish
    total = len(selections)

    if bullish == bearish:
        dominant = EvidenceDirection.UNRESOLVED
        support = 0
        opposition = resolved
        value = Decimal(0)
    else:
        dominant = (
            EvidenceDirection.BULLISH
            if bullish > bearish
            else EvidenceDirection.BEARISH
        )
        support = max(bullish, bearish)
        opposition = min(bullish, bearish)
        value = (
            (Decimal(support - opposition) / Decimal(total))
            * Decimal(100)
        ).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)

    return dominant, ConfluenceScore(
        value=value,
        support_method_count=support,
        opposing_method_count=opposition,
        resolved_method_count=resolved,
        total_methodology_slots=total,
    )


def analyze_confluence(
    evidence: Sequence[MethodologyEvidence],
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    timeframe: str,
    as_of_ms: int,
) -> ConfluenceAnalysisResult:
    _validate_context(
        evidence,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
    )
    selections = build_methodology_selections(evidence)
    pairwise = build_pairwise_relations(selections)
    dominant, score = _score(selections)

    flags: list[str] = []
    for selection in selections:
        if selection.has_internal_direction_conflict:
            flags.append(
                f"internal_direction_conflict:{selection.methodology.value}"
            )
        elif selection.resolved_direction is EvidenceDirection.UNRESOLVED:
            flags.append(
                f"no_resolved_direction:{selection.methodology.value}"
            )

    if score.resolved_method_count < score.total_methodology_slots:
        flags.append("partial_methodology_coverage")
    if score.resolved_method_count == 0:
        flags.append("no_directional_evidence")
    elif dominant is EvidenceDirection.UNRESOLVED:
        flags.append("directional_tie")

    return ConfluenceAnalysisResult(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        as_of_ms=as_of_ms,
        selections=selections,
        pairwise_relations=pairwise,
        dominant_direction=dominant,
        score=score,
        flags=tuple(flags),
    )
