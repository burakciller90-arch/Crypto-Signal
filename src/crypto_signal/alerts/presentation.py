from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from crypto_signal.alerts.models import AlertEvent, AlertSourceKind
from crypto_signal.alerts.store import parse_alert_event_json
from crypto_signal.signals.models import SignalState


class CredentialReferenceKind(StrEnum):
    ENVIRONMENT = "environment"
    KEYCHAIN = "keychain"


@dataclass(frozen=True, slots=True)
class AlertSinkConfiguration:
    sink_id: str
    provider: str
    destination_alias: str
    credential_reference_kind: CredentialReferenceKind
    credential_reference: str
    enabled: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.sink_id, "sink id"),
            (self.provider, "provider"),
            (self.destination_alias, "destination alias"),
            (self.credential_reference, "credential reference"),
        ):
            if not value.strip():
                raise ValueError(
                    f"alert {label} must be non-empty"
                )
        forbidden = ("token=", "password=", "secret=", "api_key=")
        lowered = self.credential_reference.lower()
        if any(marker in lowered for marker in forbidden):
            raise ValueError(
                "credential reference must name a secret source, "
                "not embed a secret"
            )


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    event_identity: str
    idempotency_key: str
    title: str
    body: str

    def __post_init__(self) -> None:
        if len(self.event_identity) != 64:
            raise ValueError(
                "notification event identity must be SHA256"
            )
        if self.idempotency_key != self.event_identity:
            raise ValueError(
                "notification idempotency key must equal event identity"
            )
        if not self.title.strip() or not self.body.strip():
            raise ValueError(
                "notification title/body must be non-empty"
            )


def _utc_iso(ms: int) -> str:
    return datetime.fromtimestamp(
        ms / 1000,
        tz=UTC,
    ).isoformat(timespec="seconds")


def render_notification(event: AlertEvent) -> NotificationMessage:
    if event.signal_state is SignalState.ACTIVE:
        state_label = "ACTIVE"
    elif event.signal_state is SignalState.INVALIDATED:
        state_label = "INVALIDATED"
    else:
        state_label = event.signal_state.value.upper()

    source_label = (
        "initial signal"
        if event.source_kind is AlertSourceKind.INITIAL_SIGNAL
        else "lifecycle transition"
    )
    uncertainty = (
        ", ".join(event.uncertainty_flags)
        if event.uncertainty_flags
        else "none"
    )

    title = (
        f"Crypto Signal · {state_label} · "
        f"{event.symbol} {event.timeframe}"
    )
    body = "\n".join(
        (
            (
                f"Market: {event.exchange.value.upper()} "
                f"{event.market_type.value} · {event.symbol} "
                f"· {event.timeframe}"
            ),
            (
                f"State: {event.signal_state.value} · "
                f"Direction: {event.direction.value} · "
                f"Setup: {event.setup_type}"
            ),
            (
                f"Agreement index: {event.confluence_score} "
                "(not probability)"
            ),
            f"Probability status: {event.probability_status.value}",
            (
                f"Source: {source_label} · "
                f"as-of {_utc_iso(event.source_evaluated_as_of_ms)}"
            ),
            f"Uncertainty: {uncertainty}",
            f"Alert ID: {event.event_identity}",
        )
    )
    return NotificationMessage(
        event_identity=event.event_identity,
        idempotency_key=event.event_identity,
        title=title,
        body=body,
    )


def preview_outbox(
    path: Path,
    *,
    limit: int = 100,
) -> tuple[NotificationMessage, ...]:
    if limit <= 0:
        raise ValueError("notification preview limit must be positive")
    if not path.exists():
        return ()

    connection = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        table = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='alert_events'
            """
        ).fetchone()
        if table is None:
            return ()
        rows = connection.execute(
            """
            SELECT event_json
            FROM alert_events
            ORDER BY appended_at_ms DESC, event_identity DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    messages: list[NotificationMessage] = []
    for row in rows:
        event = parse_alert_event_json(str(row["event_json"]))
        messages.append(render_notification(event))
    return tuple(messages)
