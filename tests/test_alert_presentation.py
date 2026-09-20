from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.alerts.models import (
    ALERT_SCHEMA_VERSION,
    AlertEvent,
    AlertSourceKind,
)
from crypto_signal.alerts.presentation import (
    AlertSinkConfiguration,
    CredentialReferenceKind,
    NotificationMessage,
    preview_outbox,
    render_notification,
)
from crypto_signal.alerts.store import AlertOutbox
from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.signals.models import (
    ProbabilityStatus,
    SignalDirection,
    SignalState,
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def event(
    seed: str,
    *,
    state: SignalState = SignalState.ACTIVE,
    source_kind: AlertSourceKind = AlertSourceKind.INITIAL_SIGNAL,
) -> AlertEvent:
    lifecycle_identity = (
        None
        if source_kind is AlertSourceKind.INITIAL_SIGNAL
        else digest(f"lifecycle-{seed}")
    )
    transition_identity = (
        None
        if source_kind is AlertSourceKind.INITIAL_SIGNAL
        else digest(f"transition-{seed}")
    )
    draft = AlertEvent(
        event_identity="0" * 64,
        schema_version=ALERT_SCHEMA_VERSION,
        policy_version="alerts-v1-default/1",
        source_kind=source_kind,
        signal_freeze_identity=digest(f"signal-{seed}"),
        lifecycle_evaluation_identity=lifecycle_identity,
        transition_identity=transition_identity,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        signal_state=state,
        direction=SignalDirection.BULLISH,
        setup_type="gartley",
        decision_as_of_ms=1_000,
        source_evaluated_as_of_ms=(
            1_000
            if source_kind is AlertSourceKind.INITIAL_SIGNAL
            else 3_000
        ),
        confluence_score=Decimal("66.67"),
        confluence_score_semantic=(
            ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        uncertainty_flags=("partial_methodology_coverage",),
    )
    from crypto_signal.alerts.planner import alert_event_identity

    return replace(
        draft,
        event_identity=alert_event_identity(draft),
    )


def _logical_outbox_snapshot(path: Path) -> tuple[tuple[object, ...], ...]:
    """Compare logical SQLite truth, not WAL/SHM housekeeping bytes."""
    connection = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    connection.execute("PRAGMA query_only=ON")
    try:
        events = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT
                    event_identity,
                    signal_freeze_identity,
                    source_kind,
                    policy_version,
                    signal_state,
                    event_json,
                    appended_at_ms
                FROM alert_events
                ORDER BY event_identity
                """
            ).fetchall()
        )
        attempts = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT
                    attempt_identity,
                    event_identity,
                    sink_id,
                    attempt_number,
                    attempted_at_ms,
                    status,
                    receipt,
                    error_code,
                    error_message
                FROM alert_delivery_attempts
                ORDER BY attempt_identity
                """
            ).fetchall()
        )
        schema = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
        )
    finally:
        connection.close()
    return events + attempts + schema


def test_active_notification_is_deterministic_and_not_probability() -> None:
    item = event("active")

    first = render_notification(item)
    second = render_notification(item)

    assert first == second
    assert first.event_identity == item.event_identity
    assert first.idempotency_key == item.event_identity
    assert first.title == "Crypto Signal · ACTIVE · BTCUSDT 15m"
    assert "Agreement index: 66.67 (not probability)" in first.body
    assert "Probability status: not_calibrated" in first.body
    assert "Source: initial signal" in first.body
    assert f"Alert ID: {item.event_identity}" in first.body


def test_invalidated_notification_preserves_lifecycle_semantics() -> None:
    item = event(
        "invalidated",
        state=SignalState.INVALIDATED,
        source_kind=AlertSourceKind.LIFECYCLE_TRANSITION,
    )

    message = render_notification(item)

    assert message.title == "Crypto Signal · INVALIDATED · BTCUSDT 15m"
    assert "State: invalidated" in message.body
    assert "Source: lifecycle transition" in message.body
    assert "not probability" in message.body


def test_sink_configuration_references_secret_source_not_secret() -> None:
    config = AlertSinkConfiguration(
        sink_id="provider:primary",
        provider="future-provider",
        destination_alias="primary-alerts",
        credential_reference_kind=CredentialReferenceKind.ENVIRONMENT,
        credential_reference="CRYPTO_SIGNAL_ALERT_CREDENTIAL",
        enabled=False,
    )

    assert config.enabled is False
    assert config.credential_reference == "CRYPTO_SIGNAL_ALERT_CREDENTIAL"


@pytest.mark.parametrize(
    "value",
    (
        "token=abc",
        "PASSWORD=hunter2",
        "secret=embedded",
        "api_key=embedded",
    ),
)
def test_sink_configuration_rejects_embedded_secret_markers(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="must name a secret source"):
        AlertSinkConfiguration(
            sink_id="provider:primary",
            provider="future-provider",
            destination_alias="primary-alerts",
            credential_reference_kind=CredentialReferenceKind.ENVIRONMENT,
            credential_reference=value,
        )


def test_preview_outbox_is_read_only_and_does_not_create_attempts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "alerts.sqlite3"
    outbox = AlertOutbox(path)
    item = event("preview")
    outbox.append_event(item, appended_at_ms=2_000)
    before = _logical_outbox_snapshot(path)

    messages = preview_outbox(path)

    after = _logical_outbox_snapshot(path)
    assert len(messages) == 1
    assert messages[0] == render_notification(item)
    assert outbox.count_attempts() == 0
    assert before == after


def test_preview_missing_outbox_returns_empty_without_creating_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.sqlite3"

    assert preview_outbox(path) == ()
    assert not path.exists()


def test_notification_message_rejects_different_idempotency_key() -> None:
    identity = digest("message")
    with pytest.raises(ValueError, match="must equal event identity"):
        NotificationMessage(
            event_identity=identity,
            idempotency_key=digest("different"),
            title="title",
            body="body",
        )
