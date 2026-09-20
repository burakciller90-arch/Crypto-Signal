from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.alerts.delivery import (
    AlertSinkError,
    LocalNoopSink,
    dispatch_pending,
)
from crypto_signal.alerts.models import (
    AlertPolicy,
    AlertSourceKind,
    DeliveryAttemptStatus,
    DeliveryResult,
)
from crypto_signal.alerts.planner import (
    alert_event_identity,
    plan_initial_alert,
    plan_lifecycle_alert,
)
from crypto_signal.alerts.presentation import NotificationMessage
from crypto_signal.alerts.store import (
    AlertOutbox,
    AlertOutboxConflictError,
    AlertWriteDisposition,
)
from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    LifecycleEvaluationStatus,
    LifecycleTransitionReason,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalLifecycleEvaluation,
    SignalState,
    SignalStateTransition,
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def signal(
    seed: str,
    *,
    state: SignalState = SignalState.ACTIVE,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> SignalDecision:
    geometry: SignalGeometry | None
    if state is SignalState.ACTIVE:
        geometry = SignalGeometry(
            source_evidence_id=f"harmonic-{seed}",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(Decimal(100), Decimal(102)),
            entry_reference_price=Decimal(101),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=Decimal(90),
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(
                RiskRewardTarget(
                    label="target_1",
                    target_price=Decimal(110),
                    reference_rr=Decimal(1),
                ),
            ),
        )
    else:
        geometry = None

    return SignalDecision(
        freeze_identity=digest(f"signal-{seed}"),
        signal_version="signal-v1/1",
        state=state,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=1_000,
        direction=direction,
        setup_type=(
            "gartley" if state is SignalState.ACTIVE else "confluence_watch"
        ),
        geometry=geometry,
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"evidence-{seed}",),
        methodology_versions=(
            MethodologyVersionRef(
                methodology=MethodologyKind.HARMONIC,
                version="harmonic-v1/1",
            ),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("partial_methodology_coverage",),
        evidence_summary=(),
    )


def invalidated_lifecycle(
    decision: SignalDecision,
    *,
    evaluated_as_of_ms: int = 3_000,
) -> SignalLifecycleEvaluation:
    transition = SignalStateTransition(
        transition_identity=digest(
            f"transition-{decision.freeze_identity}-{evaluated_as_of_ms}"
        ),
        signal_freeze_identity=decision.freeze_identity,
        from_state=decision.state,
        to_state=SignalState.INVALIDATED,
        reason=LifecycleTransitionReason.INVALIDATION_TOUCH_OR_CROSS,
        trigger_candle_identity=(
            "bybit",
            "spot",
            "BTCUSDT",
            "15m",
            1_800,
        ),
        market_confirmed_at_ms=2_699,
        observed_at_ms=2_700,
        evaluated_as_of_ms=evaluated_as_of_ms,
        first_trigger_candle_certain=True,
    )
    return SignalLifecycleEvaluation(
        signal_freeze_identity=decision.freeze_identity,
        evaluated_as_of_ms=evaluated_as_of_ms,
        current_state=SignalState.INVALIDATED,
        status=LifecycleEvaluationStatus.COMPLETE,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=True,
        transition=transition,
    )


def test_default_policy_alerts_active_but_not_watch() -> None:
    active = signal("active")
    watch = signal("watch", state=SignalState.WATCH)

    active_event = plan_initial_alert(active)
    watch_event = plan_initial_alert(watch)

    assert active_event is not None
    assert active_event.source_kind is AlertSourceKind.INITIAL_SIGNAL
    assert active_event.signal_state is SignalState.ACTIVE
    assert active_event.probability_status is ProbabilityStatus.NOT_CALIBRATED
    assert active_event.confluence_score_semantic is (
        ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY
    )
    assert watch_event is None


def test_custom_policy_can_explicitly_alert_watch() -> None:
    watch = signal("watch-custom", state=SignalState.WATCH)
    policy = AlertPolicy(
        version="watch-policy/1",
        initial_states=(SignalState.WATCH,),
        transition_states=(SignalState.INVALIDATED,),
    )

    event = plan_initial_alert(watch, policy=policy)

    assert event is not None
    assert event.policy_version == "watch-policy/1"
    assert event.signal_state is SignalState.WATCH


def test_same_source_and_policy_have_deterministic_identity() -> None:
    decision = signal("deterministic")

    first = plan_initial_alert(decision)
    second = plan_initial_alert(decision)

    assert first is not None and second is not None
    assert first == second
    assert first.event_identity == alert_event_identity(first)


def test_policy_version_participates_in_event_identity() -> None:
    decision = signal("policy-version")
    first = plan_initial_alert(
        decision,
        policy=AlertPolicy(
            version="policy/1",
            initial_states=(SignalState.ACTIVE,),
            transition_states=(SignalState.INVALIDATED,),
        ),
    )
    second = plan_initial_alert(
        decision,
        policy=AlertPolicy(
            version="policy/2",
            initial_states=(SignalState.ACTIVE,),
            transition_states=(SignalState.INVALIDATED,),
        ),
    )

    assert first is not None and second is not None
    assert first.event_identity != second.event_identity


def test_lifecycle_transition_alert_is_bound_to_transition() -> None:
    decision = signal("invalidated")
    evaluation = invalidated_lifecycle(decision)

    event = plan_lifecycle_alert(decision, evaluation)

    assert event is not None
    assert event.source_kind is AlertSourceKind.LIFECYCLE_TRANSITION
    assert event.signal_state is SignalState.INVALIDATED
    assert evaluation.transition is not None
    assert event.transition_identity == evaluation.transition.transition_identity
    assert event.lifecycle_evaluation_identity is not None
    assert event.source_evaluated_as_of_ms == evaluation.evaluated_as_of_ms


def test_lifecycle_without_transition_does_not_alert() -> None:
    decision = signal("no-transition")
    evaluation = SignalLifecycleEvaluation(
        signal_freeze_identity=decision.freeze_identity,
        evaluated_as_of_ms=3_000,
        current_state=SignalState.ACTIVE,
        status=LifecycleEvaluationStatus.NO_NEW_EVIDENCE,
        missing_open_times_ms=(),
        skipped_partial_decision_bucket=True,
        transition=None,
    )

    assert plan_lifecycle_alert(decision, evaluation) is None


def test_lifecycle_signal_mismatch_is_rejected() -> None:
    decision = signal("parent")
    other = signal("other")
    evaluation = invalidated_lifecycle(other)

    with pytest.raises(ValueError, match="does not belong"):
        plan_lifecycle_alert(decision, evaluation)


def test_outbox_event_append_is_idempotent(tmp_path: Path) -> None:
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    event = plan_initial_alert(signal("append"))
    assert event is not None

    first = outbox.append_event(event, appended_at_ms=2_000)
    second = outbox.append_event(event, appended_at_ms=2_100)

    assert first is AlertWriteDisposition.INSERTED
    assert second is AlertWriteDisposition.UNCHANGED
    assert outbox.count_events() == 1
    assert outbox.list_events()[0].event == event


def test_tampered_event_identity_is_rejected(tmp_path: Path) -> None:
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    event = plan_initial_alert(signal("tamper"))
    assert event is not None
    tampered = replace(event, event_identity="0" * 64)

    with pytest.raises(ValueError, match="identity mismatch"):
        outbox.append_event(tampered, appended_at_ms=2_000)


def test_retryable_failure_remains_pending_then_delivery_is_terminal(
    tmp_path: Path,
) -> None:
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    event = plan_initial_alert(signal("retry"))
    assert event is not None
    outbox.append_event(event, appended_at_ms=2_000)

    first = outbox.record_delivery_attempt(
        event.event_identity,
        "sink/test",
        DeliveryResult(
            status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
            error_code="timeout",
            error_message="provider timeout",
        ),
        attempted_at_ms=2_100,
    )

    assert first.attempt_number == 1
    assert outbox.pending_events("sink/test") == (event,)
    state = outbox.delivery_state(event.event_identity, "sink/test")
    assert state.terminal is False
    assert state.attempts == 1

    second = outbox.record_delivery_attempt(
        event.event_identity,
        "sink/test",
        DeliveryResult(
            status=DeliveryAttemptStatus.DELIVERED,
            receipt="receipt-1",
        ),
        attempted_at_ms=2_200,
    )

    assert second.attempt_number == 2
    assert outbox.pending_events("sink/test") == ()
    state = outbox.delivery_state(event.event_identity, "sink/test")
    assert state.terminal is True
    assert state.delivered is True
    assert state.latest_receipt == "receipt-1"

    with pytest.raises(
        AlertOutboxConflictError,
        match="terminal alert delivery",
    ):
        outbox.record_delivery_attempt(
            event.event_identity,
            "sink/test",
            DeliveryResult(
                status=DeliveryAttemptStatus.DELIVERED,
                receipt="duplicate",
            ),
            attempted_at_ms=2_300,
        )


def test_permanent_failure_is_terminal_for_one_sink_only(tmp_path: Path) -> None:
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    event = plan_initial_alert(signal("permanent"))
    assert event is not None
    outbox.append_event(event, appended_at_ms=2_000)

    outbox.record_delivery_attempt(
        event.event_identity,
        "sink/a",
        DeliveryResult(
            status=DeliveryAttemptStatus.PERMANENT_FAILURE,
            error_code="invalid_destination",
            error_message="destination is invalid",
        ),
        attempted_at_ms=2_100,
    )

    assert outbox.pending_events("sink/a") == ()
    assert outbox.pending_events("sink/b") == (event,)


def test_local_noop_dispatch_is_exactly_once_per_outbox_state(
    tmp_path: Path,
) -> None:
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    event = plan_initial_alert(signal("noop"))
    assert event is not None
    outbox.append_event(event, appended_at_ms=2_000)
    sink = LocalNoopSink()

    first = dispatch_pending(
        outbox,
        sink,
        attempted_at_ms=2_100,
    )
    second = dispatch_pending(
        outbox,
        sink,
        attempted_at_ms=2_200,
    )

    assert len(first) == 1
    assert first[0].status is DeliveryAttemptStatus.DELIVERED
    assert first[0].receipt == f"local-noop:{event.event_identity}"
    assert second == ()
    assert sink.unique_delivery_count == 1
    assert outbox.count_attempts() == 1


class FlakySink:
    sink_id = "flaky/1"

    def __init__(self) -> None:
        self.calls = 0
        self.keys: list[str] = []

    def deliver(
        self,
        event: NotificationMessage,
        *,
        idempotency_key: str,
    ) -> DeliveryResult:
        self.calls += 1
        self.keys.append(idempotency_key)
        if self.calls == 1:
            raise AlertSinkError("temporary provider problem")
        return DeliveryResult(
            status=DeliveryAttemptStatus.DELIVERED,
            receipt=f"flaky:{event.event_identity}",
        )


def test_dispatch_retry_reuses_event_identity_as_idempotency_key(
    tmp_path: Path,
) -> None:
    outbox = AlertOutbox(tmp_path / "alerts.sqlite3")
    event = plan_initial_alert(signal("flaky"))
    assert event is not None
    outbox.append_event(event, appended_at_ms=2_000)
    sink = FlakySink()

    first = dispatch_pending(outbox, sink, attempted_at_ms=2_100)
    second = dispatch_pending(outbox, sink, attempted_at_ms=2_200)

    assert first[0].status is DeliveryAttemptStatus.RETRYABLE_FAILURE
    assert second[0].status is DeliveryAttemptStatus.DELIVERED
    assert sink.keys == [event.event_identity, event.event_identity]
    assert outbox.delivery_state(
        event.event_identity,
        sink.sink_id,
    ).delivered is True


def test_alert_outbox_sql_tables_are_immutable(tmp_path: Path) -> None:
    path = tmp_path / "alerts.sqlite3"
    outbox = AlertOutbox(path)
    event = plan_initial_alert(signal("immutable"))
    assert event is not None
    outbox.append_event(event, appended_at_ms=2_000)
    outbox.record_delivery_attempt(
        event.event_identity,
        "sink/test",
        DeliveryResult(
            status=DeliveryAttemptStatus.DELIVERED,
            receipt="receipt",
        ),
        attempted_at_ms=2_100,
    )

    with sqlite3.connect(path) as connection:
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable alert outbox",
        ):
            connection.execute(
                "UPDATE alert_events SET policy_version='mutated'"
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable alert outbox",
        ):
            connection.execute("DELETE FROM alert_delivery_attempts")
