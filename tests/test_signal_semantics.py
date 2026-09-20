from decimal import Decimal

import pytest

from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.confluence.models import (
    ConfluenceAnalysisResult,
    EvidenceDirection,
    EvidenceValidity,
    InvalidationTrigger,
    MethodologyEvidence,
    MethodologyKind,
    NamedPrice,
    PriceZone,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.signals.models import (
    HistoricalStatsStatus,
    ProbabilityStatus,
    SignalDirection,
    SignalState,
)
from crypto_signal.signals.semantics import build_signal_decision

AS_OF = 10_000


def evidence(
    methodology: MethodologyKind,
    direction: EvidenceDirection,
    *,
    evidence_id: str,
    market_time: int,
    geometry: bool = False,
    invalidation_price: Decimal | None = None,
    entry_low: Decimal = Decimal(100),
    entry_high: Decimal = Decimal(102),
    targets: tuple[Decimal, ...] = (Decimal(110), Decimal(120)),
) -> MethodologyEvidence:
    if geometry:
        if invalidation_price is None:
            invalidation_price = (
                Decimal(90)
                if direction is EvidenceDirection.BULLISH
                else Decimal(112)
            )
        zone = PriceZone(entry_low, entry_high)
        target_values = tuple(
            NamedPrice(f"target_{index + 1}", value)
            for index, value in enumerate(targets)
        )
        trigger = InvalidationTrigger.TOUCH_OR_CROSS
    else:
        zone = None
        target_values = ()
        trigger = None
        invalidation_price = None

    return MethodologyEvidence(
        methodology=methodology,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=AS_OF,
        methodology_version=f"{methodology.value}/test",
        evidence_id=evidence_id,
        setup_type=(
            "gartley"
            if methodology is MethodologyKind.HARMONIC
            else "test_setup"
        ),
        direction=direction,
        validity=(
            EvidenceValidity.CONTEXT
            if methodology is MethodologyKind.PRICE_ACTION
            else EvidenceValidity.VALID
        ),
        market_available_at_ms=market_time,
        observed_at_ms=market_time + 1,
        entry_zone=zone,
        invalidation_price=invalidation_price,
        invalidation_trigger=trigger,
        targets=target_values,
        key_levels=(),
        metrics=(),
        ambiguity_flags=(),
        contradiction_flags=(),
        evidence_summary=(),
    )


def confluence(items: list[MethodologyEvidence]) -> ConfluenceAnalysisResult:
    return analyze_confluence(
        items,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=AS_OF,
    )


def test_no_directional_evidence_creates_no_signal() -> None:
    decision = build_signal_decision(confluence([]))

    assert decision.state is SignalState.NO_SIGNAL
    assert decision.direction is SignalDirection.NONE
    assert decision.geometry is None
    assert decision.probability_status is ProbabilityStatus.NOT_CALIBRATED
    assert (
        decision.historical_stats_status
        is HistoricalStatsStatus.NOT_EVALUATED
    )


def test_directional_tie_creates_neutral() -> None:
    decision = build_signal_decision(
        confluence(
            [
                evidence(
                    MethodologyKind.PRICE_ACTION,
                    EvidenceDirection.BULLISH,
                    evidence_id="pa",
                    market_time=100,
                ),
                evidence(
                    MethodologyKind.ELLIOTT,
                    EvidenceDirection.BEARISH,
                    evidence_id="elliott",
                    market_time=200,
                ),
            ]
        )
    )

    assert decision.state is SignalState.NEUTRAL
    assert decision.direction is SignalDirection.NONE
    assert decision.geometry is None


def test_single_method_direction_creates_watch() -> None:
    decision = build_signal_decision(
        confluence(
            [
                evidence(
                    MethodologyKind.PRICE_ACTION,
                    EvidenceDirection.BULLISH,
                    evidence_id="pa",
                    market_time=100,
                ),
            ]
        )
    )

    assert decision.state is SignalState.WATCH
    assert decision.direction is SignalDirection.BULLISH
    assert decision.geometry is None
    assert "insufficient_independent_support" in decision.uncertainty_flags
    assert "no_complete_geometry" in decision.uncertainty_flags


def test_two_independent_supporters_plus_one_geometry_create_active() -> None:
    decision = build_signal_decision(
        confluence(
            [
                evidence(
                    MethodologyKind.PRICE_ACTION,
                    EvidenceDirection.BULLISH,
                    evidence_id="pa",
                    market_time=100,
                ),
                evidence(
                    MethodologyKind.HARMONIC,
                    EvidenceDirection.BULLISH,
                    evidence_id="harmonic",
                    market_time=200,
                    geometry=True,
                ),
            ]
        )
    )

    assert decision.state is SignalState.ACTIVE
    assert decision.direction is SignalDirection.BULLISH
    assert decision.setup_type == "gartley"
    assert decision.geometry is not None
    assert decision.geometry.source_evidence_id == "harmonic"
    assert decision.geometry.entry_reference_price == Decimal(101)
    assert decision.geometry.invalidation_price == Decimal(90)
    assert [item.target_price for item in decision.geometry.targets] == [
        Decimal(110),
        Decimal(120),
    ]
    assert all(item.reference_rr > 0 for item in decision.geometry.targets)
    assert decision.agreement.confluence_score == Decimal("66.67")
    assert decision.agreement.opposing_method_count == 0


def test_opposing_vote_keeps_complete_geometry_but_state_is_watch() -> None:
    decision = build_signal_decision(
        confluence(
            [
                evidence(
                    MethodologyKind.PRICE_ACTION,
                    EvidenceDirection.BULLISH,
                    evidence_id="pa",
                    market_time=100,
                ),
                evidence(
                    MethodologyKind.HARMONIC,
                    EvidenceDirection.BULLISH,
                    evidence_id="harmonic",
                    market_time=200,
                    geometry=True,
                ),
                evidence(
                    MethodologyKind.ELLIOTT,
                    EvidenceDirection.BEARISH,
                    evidence_id="elliott",
                    market_time=300,
                ),
            ]
        )
    )

    assert decision.state is SignalState.WATCH
    assert decision.direction is SignalDirection.BULLISH
    assert decision.geometry is not None
    assert "opposing_methodology_vote" in decision.uncertainty_flags
    assert decision.agreement.confluence_score == Decimal("33.33")


def test_multiple_geometry_candidates_are_not_silently_ranked() -> None:
    decision = build_signal_decision(
        confluence(
            [
                evidence(
                    MethodologyKind.PRICE_ACTION,
                    EvidenceDirection.BULLISH,
                    evidence_id="pa",
                    market_time=100,
                ),
                evidence(
                    MethodologyKind.HARMONIC,
                    EvidenceDirection.BULLISH,
                    evidence_id="harmonic-a",
                    market_time=200,
                    geometry=True,
                ),
                evidence(
                    MethodologyKind.HARMONIC,
                    EvidenceDirection.BULLISH,
                    evidence_id="harmonic-b",
                    market_time=200,
                    geometry=True,
                    entry_low=Decimal(101),
                    entry_high=Decimal(103),
                ),
            ]
        )
    )

    assert decision.state is SignalState.WATCH
    assert decision.direction is SignalDirection.BULLISH
    assert decision.geometry is None
    assert (
        "multiple_complete_geometry_candidates"
        in decision.uncertainty_flags
    )


def test_freeze_identity_is_input_order_independent() -> None:
    items = [
        evidence(
            MethodologyKind.PRICE_ACTION,
            EvidenceDirection.BULLISH,
            evidence_id="pa",
            market_time=100,
        ),
        evidence(
            MethodologyKind.HARMONIC,
            EvidenceDirection.BULLISH,
            evidence_id="harmonic",
            market_time=200,
            geometry=True,
        ),
    ]

    first = build_signal_decision(confluence(items))
    second = build_signal_decision(confluence(list(reversed(items))))

    assert first == second
    assert len(first.freeze_identity) == 64


def test_inconsistent_geometry_risk_is_rejected() -> None:
    bad = evidence(
        MethodologyKind.HARMONIC,
        EvidenceDirection.BULLISH,
        evidence_id="harmonic",
        market_time=200,
        geometry=True,
        invalidation_price=Decimal(105),
    )
    result = confluence(
        [
            evidence(
                MethodologyKind.PRICE_ACTION,
                EvidenceDirection.BULLISH,
                evidence_id="pa",
                market_time=100,
            ),
            bad,
        ]
    )

    with pytest.raises(ValueError, match="non-positive reference risk"):
        build_signal_decision(result)
