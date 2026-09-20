from datetime import UTC, datetime
from decimal import Decimal

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
from crypto_signal.outcomes.evaluator import evaluate_outcome
from crypto_signal.outcomes.models import (
    EvidenceClass,
    OutcomeAmbiguityReason,
    OutcomeCoverageStatus,
    OutcomeEvaluation,
    OutcomeNotEvaluableReason,
    OutcomeResolutionStatus,
    OutcomeState,
)
from crypto_signal.signals.models import SignalDecision, SignalState
from crypto_signal.signals.semantics import build_signal_decision

BASE_MS = 900_000
BASE_OPEN = int(datetime(2026, 9, 20, tzinfo=UTC).timestamp() * 1000)
DECISION_AS_OF = BASE_OPEN + 5 * 60_000
FIRST_FULL_OPEN = BASE_OPEN + BASE_MS


def evidence(
    methodology: MethodologyKind,
    direction: EvidenceDirection,
    *,
    evidence_id: str,
    geometry: bool = False,
    trigger: InvalidationTrigger = InvalidationTrigger.TOUCH_OR_CROSS,
    target_prices: tuple[str, ...] = ("110", "120", "130"),
) -> MethodologyEvidence:
    if geometry:
        zone = PriceZone(Decimal(100), Decimal(102))
        invalidation = (
            Decimal(90)
            if direction is EvidenceDirection.BULLISH
            else Decimal(112)
        )
        targets = tuple(
            NamedPrice(f"target_{index + 1}", Decimal(price))
            for index, price in enumerate(target_prices)
        )
        invalidation_trigger = trigger
    else:
        zone = None
        invalidation = None
        targets = ()
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
        market_available_at_ms=DECISION_AS_OF - 2_000,
        observed_at_ms=DECISION_AS_OF - 1_000,
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
    active: bool = True,
    trigger: InvalidationTrigger = InvalidationTrigger.TOUCH_OR_CROSS,
    target_prices: tuple[str, ...] | None = None,
) -> SignalDecision:
    items = [
        evidence(
            MethodologyKind.PRICE_ACTION,
            direction,
            evidence_id="pa",
        )
    ]
    if active:
        targets = target_prices
        if targets is None:
            targets = (
                ("110", "120", "130")
                if direction is EvidenceDirection.BULLISH
                else ("92", "82", "72")
            )
        items.append(
            evidence(
                MethodologyKind.HARMONIC,
                direction,
                evidence_id="harmonic",
                geometry=True,
                trigger=trigger,
                target_prices=targets,
            )
        )

    confluence = analyze_confluence(
        items,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=DECISION_AS_OF,
    )
    return build_signal_decision(confluence)


def candle(
    index: int,
    *,
    high: str,
    low: str,
    close: str,
    ingested_at_ms: int | None = None,
) -> Candle:
    open_time_ms = FIRST_FULL_OPEN + index * BASE_MS
    close_time_ms = open_time_ms + BASE_MS - 1
    close_value = Decimal(close)
    high_value = Decimal(high)
    low_value = Decimal(low)
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=close_value,
        high=high_value,
        low=low_value,
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


def evaluate(
    decision: SignalDecision,
    items: tuple[Candle, ...],
    *,
    max_holding_bars: int = 4,
    evidence_class: EvidenceClass = EvidenceClass.RETROSPECTIVE,
) -> OutcomeEvaluation:
    as_of_ms = (
        DECISION_AS_OF
        if not items
        else max(item.ingested_at_ms for item in items)
    )
    return evaluate_outcome(
        decision,
        items,
        as_of_ms=as_of_ms,
        evidence_class=evidence_class,
        max_holding_bars=max_holding_bars,
    )


def test_watch_signal_is_not_evaluable() -> None:
    decision = signal(active=False)
    assert decision.state is SignalState.WATCH

    result = evaluate(decision, ())

    assert result.resolution_status is OutcomeResolutionStatus.NOT_EVALUABLE
    assert result.outcome_state is OutcomeState.NOT_EVALUABLE
    assert result.not_evaluable_reason is OutcomeNotEvaluableReason.SIGNAL_NOT_ACTIVE


def test_active_signal_without_post_decision_bar_is_pending() -> None:
    decision = signal()

    result = evaluate(decision, ())

    assert result.resolution_status is OutcomeResolutionStatus.PENDING
    assert result.outcome_state is None
    assert result.coverage_status is OutcomeCoverageStatus.NO_NEW_EVIDENCE
    assert result.skipped_partial_decision_bucket is True


def test_invalidation_before_entry_is_invalidated() -> None:
    decision = signal()
    pre_entry_stop = candle(0, high="99", low="89", close="95")

    result = evaluate(decision, (pre_entry_stop,))

    assert result.resolution_status is OutcomeResolutionStatus.RESOLVED
    assert result.outcome_state is OutcomeState.INVALIDATED
    assert result.entry_observed is False
    assert result.outcome_candle_identity == pre_entry_stop.identity


def test_entry_and_stop_same_candle_is_ambiguous() -> None:
    decision = signal()
    both = candle(0, high="103", low="89", close="100")

    result = evaluate(decision, (both,))

    assert result.outcome_state is OutcomeState.AMBIGUOUS
    assert (
        result.ambiguity_reason
        is OutcomeAmbiguityReason.ENTRY_AND_INVALIDATION_SAME_CANDLE
    )
    assert result.entry_observed is True


def test_entry_and_target_same_candle_is_ambiguous() -> None:
    decision = signal()
    both = candle(0, high="111", low="100", close="104")

    result = evaluate(decision, (both,))

    assert result.outcome_state is OutcomeState.AMBIGUOUS
    assert (
        result.ambiguity_reason
        is OutcomeAmbiguityReason.ENTRY_AND_TARGET_SAME_CANDLE
    )


def test_stop_after_separate_entry_is_fail_sl() -> None:
    decision = signal()
    entry = candle(0, high="104", low="99", close="101")
    stop = candle(1, high="104", low="89", close="95")

    result = evaluate(decision, (entry, stop))

    assert result.outcome_state is OutcomeState.FAIL_SL
    assert result.entry_candle_identity == entry.identity
    assert result.outcome_candle_identity == stop.identity


def test_tp1_then_stop_retains_proven_tp1_success() -> None:
    decision = signal()
    entry = candle(0, high="104", low="99", close="101")
    tp1 = candle(1, high="111", low="100", close="108")
    stop = candle(2, high="106", low="89", close="95")

    result = evaluate(decision, (entry, tp1, stop))

    assert result.outcome_state is OutcomeState.SUCCESS_TP1
    assert result.highest_target_index == 1
    assert result.outcome_candle_identity == tp1.identity


def test_highest_target_hit_is_success_tp3() -> None:
    decision = signal()
    entry = candle(0, high="104", low="99", close="101")
    target = candle(1, high="131", low="100", close="125")

    result = evaluate(decision, (entry, target))

    assert result.outcome_state is OutcomeState.SUCCESS_TP3
    assert result.highest_target_index == 3
    assert result.outcome_candle_identity == target.identity


def test_stop_and_new_target_same_candle_after_entry_is_ambiguous() -> None:
    decision = signal()
    entry = candle(0, high="104", low="99", close="101")
    both = candle(1, high="111", low="89", close="100")

    result = evaluate(decision, (entry, both))

    assert result.outcome_state is OutcomeState.AMBIGUOUS
    assert (
        result.ambiguity_reason
        is OutcomeAmbiguityReason.INVALIDATION_AND_NEW_TARGET_SAME_CANDLE
    )


def test_complete_horizon_without_event_times_out() -> None:
    decision = signal()
    entry = candle(0, high="104", low="99", close="101")
    quiet = candle(1, high="105", low="95", close="100")

    result = evaluate(
        decision,
        (entry, quiet),
        max_holding_bars=2,
    )

    assert result.coverage_status is OutcomeCoverageStatus.COMPLETE
    assert result.outcome_state is OutcomeState.TIMEOUT
    assert result.entry_observed is True


def test_complete_horizon_without_entry_times_out() -> None:
    decision = signal()
    first = candle(0, high="99", low="95", close="97")
    second = candle(1, high="99", low="95", close="98")

    result = evaluate(
        decision,
        (first, second),
        max_holding_bars=2,
    )

    assert result.outcome_state is OutcomeState.TIMEOUT
    assert result.entry_observed is False


def test_gap_before_later_event_is_not_evaluable() -> None:
    decision = signal()
    later = candle(1, high="131", low="100", close="125")

    result = evaluate(
        decision,
        (later,),
        max_holding_bars=2,
    )

    assert result.coverage_status is OutcomeCoverageStatus.INCOMPLETE_GAPS
    assert result.outcome_state is OutcomeState.NOT_EVALUABLE
    assert result.not_evaluable_reason is OutcomeNotEvaluableReason.DATA_GAPS
    assert result.missing_open_times_ms == (FIRST_FULL_OPEN,)


def test_close_trigger_ignores_wick_until_close_breach() -> None:
    decision = signal(
        trigger=InvalidationTrigger.CLOSE_AT_OR_BEYOND,
    )
    entry = candle(0, high="104", low="99", close="101")
    wick = candle(1, high="105", low="85", close="95")
    close_stop = candle(2, high="96", low="85", close="89")

    pending = evaluate(
        decision,
        (entry, wick),
        max_holding_bars=4,
    )
    assert pending.resolution_status is OutcomeResolutionStatus.PENDING
    assert pending.outcome_state is None

    failed = evaluate(
        decision,
        (entry, wick, close_stop),
        max_holding_bars=4,
    )
    assert failed.outcome_state is OutcomeState.FAIL_SL


def test_bearish_direction_is_symmetric() -> None:
    decision = signal(EvidenceDirection.BEARISH)
    entry = candle(0, high="103", low="99", close="101")
    tp1 = candle(1, high="105", low="91", close="95")

    result = evaluate(decision, (entry, tp1))

    assert result.outcome_state is OutcomeState.SUCCESS_TP1
    assert result.highest_target_index == 1


def test_evidence_class_is_explicit_and_changes_snapshot_identity() -> None:
    decision = signal()
    entry = candle(0, high="104", low="99", close="101")

    retrospective = evaluate(
        decision,
        (entry,),
        evidence_class=EvidenceClass.RETROSPECTIVE,
    )
    live = evaluate(
        decision,
        (entry,),
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
    )

    assert retrospective.evidence_class is EvidenceClass.RETROSPECTIVE
    assert live.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
    assert retrospective.outcome_identity != live.outcome_identity
