from decimal import Decimal

import pytest

from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.confluence.models import (
    ConfluenceAnalysisResult,
    EvidenceDirection,
    EvidenceValidity,
    MethodologyEvidence,
    MethodologyKind,
    PairRelation,
    ScoreSemantic,
)
from crypto_signal.confluence.selection import select_latest_for_methodology
from crypto_signal.data.models import Exchange, MarketType

AS_OF = 10_000


def evidence(
    methodology: MethodologyKind,
    direction: EvidenceDirection,
    *,
    market_time: int,
    evidence_id: str,
    symbol: str = "BTCUSDT",
) -> MethodologyEvidence:
    return MethodologyEvidence(
        methodology=methodology,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="15m",
        as_of_ms=AS_OF,
        methodology_version=f"{methodology.value}/test",
        evidence_id=evidence_id,
        setup_type="test_setup",
        direction=direction,
        validity=EvidenceValidity.VALID,
        market_available_at_ms=market_time,
        observed_at_ms=market_time + 1,
        entry_zone=None,
        invalidation_price=None,
        targets=(),
        key_levels=(),
        metrics=(),
        ambiguity_flags=(),
        contradiction_flags=(),
        evidence_summary=(),
    )


def analyze(items: list[MethodologyEvidence]) -> ConfluenceAnalysisResult:
    return analyze_confluence(
        items,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=AS_OF,
    )


def test_selection_uses_latest_market_time_and_preserves_tied_alternatives() -> None:
    items = [
        evidence(
            MethodologyKind.HARMONIC,
            EvidenceDirection.BULLISH,
            market_time=100,
            evidence_id="old",
        ),
        evidence(
            MethodologyKind.HARMONIC,
            EvidenceDirection.BULLISH,
            market_time=200,
            evidence_id="new-a",
        ),
        evidence(
            MethodologyKind.HARMONIC,
            EvidenceDirection.BULLISH,
            market_time=200,
            evidence_id="new-b",
        ),
    ]

    selection = select_latest_for_methodology(
        items,
        MethodologyKind.HARMONIC,
    )

    assert selection.source_count == 3
    assert [item.evidence_id for item in selection.selected] == [
        "new-a",
        "new-b",
    ]
    assert selection.latest_market_available_at_ms == 200
    assert selection.resolved_direction is EvidenceDirection.BULLISH
    assert selection.has_internal_direction_conflict is False


def test_three_method_agreement_scores_100() -> None:
    result = analyze(
        [
            evidence(
                MethodologyKind.PRICE_ACTION,
                EvidenceDirection.BULLISH,
                market_time=100,
                evidence_id="pa",
            ),
            evidence(
                MethodologyKind.HARMONIC,
                EvidenceDirection.BULLISH,
                market_time=200,
                evidence_id="harmonic",
            ),
            evidence(
                MethodologyKind.ELLIOTT,
                EvidenceDirection.BULLISH,
                market_time=300,
                evidence_id="elliott",
            ),
        ]
    )

    assert result.dominant_direction is EvidenceDirection.BULLISH
    assert result.score.value == Decimal("100.00")
    assert result.score.support_method_count == 3
    assert result.score.opposing_method_count == 0
    assert result.score.resolved_method_count == 3
    assert result.score.semantic is ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY
    assert {item.relation for item in result.pairwise_relations} == {
        PairRelation.AGREE
    }
    assert result.flags == ()


def test_two_support_one_opposition_scores_33_33() -> None:
    result = analyze(
        [
            evidence(
                MethodologyKind.PRICE_ACTION,
                EvidenceDirection.BULLISH,
                market_time=100,
                evidence_id="pa",
            ),
            evidence(
                MethodologyKind.HARMONIC,
                EvidenceDirection.BULLISH,
                market_time=200,
                evidence_id="harmonic",
            ),
            evidence(
                MethodologyKind.ELLIOTT,
                EvidenceDirection.BEARISH,
                market_time=300,
                evidence_id="elliott",
            ),
        ]
    )

    assert result.dominant_direction is EvidenceDirection.BULLISH
    assert result.score.value == Decimal("33.33")
    assert result.score.support_method_count == 2
    assert result.score.opposing_method_count == 1
    relations = [item.relation for item in result.pairwise_relations]
    assert relations.count(PairRelation.AGREE) == 1
    assert relations.count(PairRelation.CONTRADICT) == 2


def test_two_support_and_one_missing_scores_66_67() -> None:
    result = analyze(
        [
            evidence(
                MethodologyKind.PRICE_ACTION,
                EvidenceDirection.BEARISH,
                market_time=100,
                evidence_id="pa",
            ),
            evidence(
                MethodologyKind.HARMONIC,
                EvidenceDirection.BEARISH,
                market_time=200,
                evidence_id="harmonic",
            ),
        ]
    )

    assert result.dominant_direction is EvidenceDirection.BEARISH
    assert result.score.value == Decimal("66.67")
    assert result.score.resolved_method_count == 2
    assert "partial_methodology_coverage" in result.flags
    assert "no_resolved_direction:elliott" in result.flags
    assert sum(
        item.relation is PairRelation.INSUFFICIENT
        for item in result.pairwise_relations
    ) == 2


def test_directional_tie_scores_zero() -> None:
    result = analyze(
        [
            evidence(
                MethodologyKind.PRICE_ACTION,
                EvidenceDirection.BULLISH,
                market_time=100,
                evidence_id="pa",
            ),
            evidence(
                MethodologyKind.HARMONIC,
                EvidenceDirection.BEARISH,
                market_time=200,
                evidence_id="harmonic",
            ),
        ]
    )

    assert result.dominant_direction is EvidenceDirection.UNRESOLVED
    assert result.score.value == Decimal("0.00")
    assert result.score.support_method_count == 0
    assert result.score.opposing_method_count == 2
    assert result.score.resolved_method_count == 2
    assert "directional_tie" in result.flags


def test_internal_direction_conflict_casts_no_method_vote() -> None:
    result = analyze(
        [
            evidence(
                MethodologyKind.HARMONIC,
                EvidenceDirection.BULLISH,
                market_time=200,
                evidence_id="harmonic-bull",
            ),
            evidence(
                MethodologyKind.HARMONIC,
                EvidenceDirection.BEARISH,
                market_time=200,
                evidence_id="harmonic-bear",
            ),
            evidence(
                MethodologyKind.PRICE_ACTION,
                EvidenceDirection.BULLISH,
                market_time=100,
                evidence_id="pa",
            ),
        ]
    )

    harmonic = next(
        item
        for item in result.selections
        if item.methodology is MethodologyKind.HARMONIC
    )
    assert harmonic.has_internal_direction_conflict is True
    assert harmonic.resolved_direction is EvidenceDirection.UNRESOLVED
    assert result.dominant_direction is EvidenceDirection.BULLISH
    assert result.score.value == Decimal("33.33")
    assert "internal_direction_conflict:harmonic" in result.flags
    assert any(
        relation.relation is PairRelation.INTERNAL_AMBIGUITY
        for relation in result.pairwise_relations
    )


def test_context_mismatch_is_rejected() -> None:
    item = evidence(
        MethodologyKind.PRICE_ACTION,
        EvidenceDirection.BULLISH,
        market_time=100,
        evidence_id="wrong-symbol",
        symbol="ETHUSDT",
    )

    with pytest.raises(ValueError, match="context mismatch"):
        analyze([item])
