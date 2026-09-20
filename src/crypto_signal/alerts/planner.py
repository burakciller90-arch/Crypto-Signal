from __future__ import annotations

from dataclasses import replace

from crypto_signal.alerts.models import (
    ALERT_SCHEMA_VERSION,
    AlertEvent,
    AlertPolicy,
    AlertSourceKind,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.signals.models import (
    SignalDecision,
    SignalLifecycleEvaluation,
    SignalState,
)


def alert_event_identity(event: AlertEvent) -> str:
    payload = {
        "schema_version": event.schema_version,
        "policy_version": event.policy_version,
        "source_kind": event.source_kind,
        "signal_freeze_identity": event.signal_freeze_identity,
        "lifecycle_evaluation_identity": (
            event.lifecycle_evaluation_identity
        ),
        "transition_identity": event.transition_identity,
        "signal_state": event.signal_state,
    }
    return canonical_sha256(payload)


def verify_alert_event_identity(event: AlertEvent) -> None:
    if event.event_identity != alert_event_identity(event):
        raise ValueError("alert event identity mismatch")


def _base_event(
    decision: SignalDecision,
    *,
    policy: AlertPolicy,
    source_kind: AlertSourceKind,
    lifecycle_evaluation_identity: str | None,
    transition_identity: str | None,
    source_evaluated_as_of_ms: int,
    signal_state: SignalState,
) -> AlertEvent:
    draft = AlertEvent(
        event_identity="0" * 64,
        schema_version=ALERT_SCHEMA_VERSION,
        policy_version=policy.version,
        source_kind=source_kind,
        signal_freeze_identity=decision.freeze_identity,
        lifecycle_evaluation_identity=lifecycle_evaluation_identity,
        transition_identity=transition_identity,
        exchange=decision.exchange,
        market_type=decision.market_type,
        symbol=decision.symbol,
        timeframe=decision.timeframe,
        signal_state=signal_state,
        direction=decision.direction,
        setup_type=decision.setup_type,
        decision_as_of_ms=decision.as_of_ms,
        source_evaluated_as_of_ms=source_evaluated_as_of_ms,
        confluence_score=decision.agreement.confluence_score,
        confluence_score_semantic=decision.agreement.score_semantic,
        probability_status=decision.probability_status,
        uncertainty_flags=decision.uncertainty_flags,
    )
    return replace(
        draft,
        event_identity=alert_event_identity(draft),
    )


def plan_initial_alert(
    decision: SignalDecision,
    *,
    policy: AlertPolicy | None = None,
) -> AlertEvent | None:
    selected = AlertPolicy.default_v1() if policy is None else policy
    if decision.state not in selected.initial_states:
        return None
    return _base_event(
        decision,
        policy=selected,
        source_kind=AlertSourceKind.INITIAL_SIGNAL,
        lifecycle_evaluation_identity=None,
        transition_identity=None,
        source_evaluated_as_of_ms=decision.as_of_ms,
        signal_state=decision.state,
    )


def plan_lifecycle_alert(
    decision: SignalDecision,
    evaluation: SignalLifecycleEvaluation,
    *,
    policy: AlertPolicy | None = None,
) -> AlertEvent | None:
    selected = AlertPolicy.default_v1() if policy is None else policy
    if evaluation.signal_freeze_identity != decision.freeze_identity:
        raise ValueError("lifecycle evaluation does not belong to signal")
    if evaluation.transition is None:
        return None
    if evaluation.current_state not in selected.transition_states:
        return None
    if evaluation.transition.to_state is not evaluation.current_state:
        raise ValueError(
            "lifecycle transition target does not match current state"
        )

    lifecycle_identity = canonical_sha256(evaluation)
    return _base_event(
        decision,
        policy=selected,
        source_kind=AlertSourceKind.LIFECYCLE_TRANSITION,
        lifecycle_evaluation_identity=lifecycle_identity,
        transition_identity=evaluation.transition.transition_identity,
        source_evaluated_as_of_ms=evaluation.evaluated_as_of_ms,
        signal_state=evaluation.current_state,
    )
