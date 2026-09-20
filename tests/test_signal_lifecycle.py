from decimal import Decimal

import pytest

from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.confluence.models import (
    EvidenceDirection,
    EvidenceValidity,
    InvalidationTrigger,
    MethodologyEvidence,
    MethodologyKind,
    NamedPrice,
    PriceZone,
)
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.signals.lifecycle import evaluate_signal_lifecycle
from crypto_signal.signals.models import (
    LifecycleEvaluationStatus,
    LifecycleTransitionReason,
    SignalDecision,
    SignalDirection,
    SignalState,
)
from crypto_signal.signals.semantics import build_signal_decision

DURATION = 900_000
DECISION_AS_OF = 10_000_000
FIRST_FULL_OPEN = 10_800_000
SECOND_FULL_OPEN = FIRST_FULL_OPEN + DURATION


def evidence(
    methodology: MethodologyKind,
    direction: EvidenceDirection,
    *,
    evidence_id: str,
    market_time: int,
    geometry: bool = False,
    trigger: InvalidationTrigger = InvalidationTrigger.TOUCH_OR_CROSS,
) -> MethodologyEvidence:
    targets: tuple[NamedPrice, ...]
    if geometry:
        if direction is EvidenceDirection.BULLISH:
            invalidation = Decimal(90)
            targets = (
                NamedPrice("target_1", Decimal(110)),
                NamedPrice("target_2", Decimal(120)),
            )
        else:
            invalidation = Decimal(112)
            targets = (
                NamedPrice("target_1", Decimal(90)),
                NamedPrice("target_2", Decimal(80)),
            )
        zone = PriceZone(Decimal(100), Decimal(102))
        invalidation_trigger = trigger
    else:
        invalidation = None
        targets = ()
        zone = None
        invalidation_trigger = None

    return MethodologyEvidence(
        methodology=methodology,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=DECISION_AS_OF,
        methodology_version=f"{methodology.value}/test",
        evidence_id=evidence_id,
        setup_type=(
            "gartley"
            if methodology is MethodologyKind.HARMONIC
            else "market_structure"
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
        invalidation_price=invalidation,
        invalidation_trigger=invalidation_trigger,
        targets=targets,
        key_levels=(),
        metrics=(),
        ambiguity_flags=(),
        contradiction_flags=(),
        evidence_summary=(),
    )


def signal(
    direction: EvidenceDirection = EvidenceDirection.BULLISH,
    *,
    trigger: InvalidationTrigger = InvalidationTrigger.TOUCH_OR_CROSS,
    active: bool = True,
) -> SignalDecision:
    items = [
        evidence(
            MethodologyKind.PRICE_ACTION,
            direction,
            evidence_id="pa",
            market_time=1_000_000,
        ),
    ]
    if active:
        items.append(
            evidence(
                MethodologyKind.HARMONIC,
                direction,
                evidence_id="harmonic",
                market_time=2_000_000,
                geometry=True,
                trigger=trigger,
            )
        )
    result = analyze_confluence(
        items,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=DECISION_AS_OF,
    )
    return build_signal_decision(result)


def candle(
    open_time_ms: int,
    *,
    high: str = "105",
    low: str = "95",
    close: str = "100",
    ingested_at_ms: int | None = None,
    symbol: str = "BTCUSDT",
) -> Candle:
    close_time_ms = open_time_ms + DURATION - 1
    close_value = Decimal(close)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=close_value,
        high=Decimal(high),
        low=Decimal(low),
        close=close_value,
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=close_time_ms + 1,
        ingested_at_ms=(
            close_time_ms + 1
            if ingested_at_ms is None
            else ingested_at_ms
        ),
        adapter_version="test/1",
    )


def test_no_completed_full_post_decision_candle_means_no_new_evidence() -> None:
    decision = signal()
    result = evaluate_signal_lifecycle(
        decision,
        (),
        as_of_ms=10_500_000,
    )

    assert result.status is LifecycleEvaluationStatus.NO_NEW_EVIDENCE
    assert result.current_state is SignalState.ACTIVE
    assert result.transition is None
    assert result.skipped_partial_decision_bucket is True


def test_partial_decision_candle_is_ignored_for_touch_invalidation() -> None:
    decision = signal()
    partial = candle(
        9_900_000,
        high="105",
        low="80",
        close="100",
    )
    safe = candle(FIRST_FULL_OPEN)
    result = evaluate_signal_lifecycle(
        decision,
        (partial, safe),
        as_of_ms=safe.ingested_at_ms,
    )

    assert result.status is LifecycleEvaluationStatus.COMPLETE
    assert result.current_state is SignalState.ACTIVE
    assert result.transition is None
    assert result.missing_open_times_ms == ()
    assert result.skipped_partial_decision_bucket is True


def test_bullish_touch_invalidation_creates_append_only_transition() -> None:
    decision = signal()
    breach = candle(
        FIRST_FULL_OPEN,
        high="105",
        low="89",
        close="100",
    )

    result = evaluate_signal_lifecycle(
        decision,
        (breach,),
        as_of_ms=breach.ingested_at_ms,
    )
    repeat = evaluate_signal_lifecycle(
        decision,
        (breach,),
        as_of_ms=breach.ingested_at_ms,
    )

    assert result == repeat
    assert decision.state is SignalState.ACTIVE
    assert result.current_state is SignalState.INVALIDATED
    assert result.status is LifecycleEvaluationStatus.COMPLETE
    assert result.transition is not None
    assert (
        result.transition.reason
        is LifecycleTransitionReason.INVALIDATION_TOUCH_OR_CROSS
    )
    assert result.transition.from_state is SignalState.ACTIVE
    assert result.transition.to_state is SignalState.INVALIDATED
    assert result.transition.first_trigger_candle_certain is True


def test_bearish_touch_invalidation_is_symmetric() -> None:
    decision = signal(EvidenceDirection.BEARISH)
    assert decision.direction is SignalDirection.BEARISH
    breach = candle(
        FIRST_FULL_OPEN,
        high="113",
        low="100",
        close="105",
    )

    result = evaluate_signal_lifecycle(
        decision,
        (breach,),
        as_of_ms=breach.ingested_at_ms,
    )

    assert result.current_state is SignalState.INVALIDATED
    assert result.transition is not None


def test_close_trigger_does_not_invalidate_on_wick_only_breach() -> None:
    decision = signal(
        trigger=InvalidationTrigger.CLOSE_AT_OR_BEYOND,
    )
    wick_only = candle(
        FIRST_FULL_OPEN,
        high="105",
        low="85",
        close="95",
    )
    first = evaluate_signal_lifecycle(
        decision,
        (wick_only,),
        as_of_ms=wick_only.ingested_at_ms,
    )
    assert first.current_state is SignalState.ACTIVE
    assert first.transition is None

    close_breach = candle(
        SECOND_FULL_OPEN,
        high="100",
        low="85",
        close="89",
    )
    second = evaluate_signal_lifecycle(
        decision,
        (wick_only, close_breach),
        as_of_ms=close_breach.ingested_at_ms,
    )
    assert second.current_state is SignalState.INVALIDATED
    assert second.transition is not None
    assert (
        second.transition.reason
        is LifecycleTransitionReason.INVALIDATION_CLOSE_AT_OR_BEYOND
    )


def test_gap_without_breach_is_incomplete_not_proof_of_validity() -> None:
    decision = signal()
    second = candle(SECOND_FULL_OPEN)

    result = evaluate_signal_lifecycle(
        decision,
        (second,),
        as_of_ms=second.ingested_at_ms,
    )

    assert result.status is LifecycleEvaluationStatus.INCOMPLETE_GAPS
    assert result.missing_open_times_ms == (FIRST_FULL_OPEN,)
    assert result.current_state is SignalState.ACTIVE
    assert result.transition is None


def test_gap_before_observed_breach_invalidates_but_first_trigger_is_uncertain() -> None:
    decision = signal()
    second_breach = candle(
        SECOND_FULL_OPEN,
        high="105",
        low="89",
        close="100",
    )

    result = evaluate_signal_lifecycle(
        decision,
        (second_breach,),
        as_of_ms=second_breach.ingested_at_ms,
    )

    assert result.status is LifecycleEvaluationStatus.INCOMPLETE_GAPS
    assert result.current_state is SignalState.INVALIDATED
    assert result.transition is not None
    assert result.transition.first_trigger_candle_certain is False


def test_unobserved_expected_candle_is_reported_missing() -> None:
    decision = signal()
    future_observation = candle(
        FIRST_FULL_OPEN,
        high="105",
        low="89",
        close="100",
        ingested_at_ms=12_000_000,
    )

    result = evaluate_signal_lifecycle(
        decision,
        (future_observation,),
        as_of_ms=11_900_000,
    )

    assert result.status is LifecycleEvaluationStatus.INCOMPLETE_GAPS
    assert result.missing_open_times_ms == (FIRST_FULL_OPEN,)
    assert result.transition is None


def test_watch_without_geometry_cannot_invalidate() -> None:
    decision = signal(active=False)
    assert decision.state is SignalState.WATCH
    assert decision.geometry is None
    breach_like = candle(
        FIRST_FULL_OPEN,
        high="1000",
        low="1",
        close="50",
    )

    result = evaluate_signal_lifecycle(
        decision,
        (breach_like,),
        as_of_ms=breach_like.ingested_at_ms,
    )

    assert result.status is LifecycleEvaluationStatus.COMPLETE
    assert result.current_state is SignalState.WATCH
    assert result.transition is None


def test_lifecycle_rejects_mismatched_market_context() -> None:
    decision = signal()
    wrong = candle(
        FIRST_FULL_OPEN,
        symbol="ETHUSDT",
    )

    with pytest.raises(ValueError, match="market context"):
        evaluate_signal_lifecycle(
            decision,
            (wrong,),
            as_of_ms=wrong.ingested_at_ms,
        )
