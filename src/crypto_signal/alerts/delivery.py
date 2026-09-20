from __future__ import annotations

from typing import Protocol

from crypto_signal.alerts.models import (
    AlertDeliveryAttempt,
    DeliveryAttemptStatus,
    DeliveryResult,
)
from crypto_signal.alerts.presentation import (
    NotificationMessage,
    render_notification,
)
from crypto_signal.alerts.store import AlertOutbox


class AlertSinkError(RuntimeError):
    """Expected provider delivery failure safe to record and retry."""


class AlertSink(Protocol):
    @property
    def sink_id(self) -> str: ...

    def deliver(
        self,
        notification: NotificationMessage,
        *,
        idempotency_key: str,
    ) -> DeliveryResult: ...


class LocalNoopSink:
    def __init__(self, sink_id: str = "local-noop/1") -> None:
        if not sink_id.strip():
            raise ValueError("alert sink id must be non-empty")
        self._sink_id = sink_id
        self._receipts: dict[str, str] = {}

    @property
    def sink_id(self) -> str:
        return self._sink_id

    def deliver(
        self,
        notification: NotificationMessage,
        *,
        idempotency_key: str,
    ) -> DeliveryResult:
        if idempotency_key != notification.event_identity:
            raise ValueError(
                "alert sink idempotency key must equal event identity"
            )
        if notification.idempotency_key != idempotency_key:
            raise ValueError(
                "notification and sink idempotency keys must match"
            )
        receipt = self._receipts.setdefault(
            idempotency_key,
            f"local-noop:{idempotency_key}",
        )
        return DeliveryResult(
            status=DeliveryAttemptStatus.DELIVERED,
            receipt=receipt,
        )

    @property
    def unique_delivery_count(self) -> int:
        return len(self._receipts)


def dispatch_pending(
    outbox: AlertOutbox,
    sink: AlertSink,
    *,
    limit: int = 100,
    attempted_at_ms: int | None = None,
) -> tuple[AlertDeliveryAttempt, ...]:
    events = outbox.pending_events(sink.sink_id, limit=limit)
    attempts: list[AlertDeliveryAttempt] = []

    for event in events:
        notification = render_notification(event)
        try:
            result = sink.deliver(
                notification,
                idempotency_key=event.event_identity,
            )
        except AlertSinkError:
            result = DeliveryResult(
                status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
                error_code="sink_exception",
                error_message="sink raised an exception",
            )
        attempt = outbox.record_delivery_attempt(
            event.event_identity,
            sink.sink_id,
            result,
            attempted_at_ms=attempted_at_ms,
        )
        attempts.append(attempt)

    return tuple(attempts)
