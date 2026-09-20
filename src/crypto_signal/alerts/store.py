from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.alerts.models import (
    ALERT_SCHEMA_VERSION,
    AlertDeliveryAttempt,
    AlertDeliveryState,
    AlertEvent,
    AlertSourceKind,
    DeliveryAttemptStatus,
    DeliveryResult,
)
from crypto_signal.alerts.planner import verify_alert_event_identity
from crypto_signal.confluence.models import ScoreSemantic
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.signals.models import (
    ProbabilityStatus,
    SignalDirection,
    SignalState,
)


class AlertWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


class AlertOutboxConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AlertEventRecord:
    event: AlertEvent
    appended_at_ms: int


class AlertOutbox:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_events (
                    event_identity TEXT PRIMARY KEY,
                    signal_freeze_identity TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    signal_state TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    appended_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_delivery_attempts (
                    attempt_identity TEXT PRIMARY KEY,
                    event_identity TEXT NOT NULL,
                    sink_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    attempted_at_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    receipt TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    UNIQUE (event_identity, sink_id, attempt_number),
                    FOREIGN KEY (event_identity)
                        REFERENCES alert_events(event_identity)
                )
                """
            )
            self._install_immutability_triggers(connection)

    def append_event(
        self,
        event: AlertEvent,
        *,
        appended_at_ms: int | None = None,
    ) -> AlertWriteDisposition:
        verify_alert_event_identity(event)
        canonical_event = canonical_json(event)
        inserted_at = (
            int(time.time() * 1000)
            if appended_at_ms is None
            else appended_at_ms
        )
        if inserted_at < event.source_evaluated_as_of_ms:
            raise ValueError(
                "alert append time cannot precede source evaluation"
            )

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT event_json
                FROM alert_events
                WHERE event_identity = ?
                """,
                (event.event_identity,),
            ).fetchone()
            if row is not None:
                if str(row["event_json"]) == canonical_event:
                    return AlertWriteDisposition.UNCHANGED
                raise AlertOutboxConflictError(
                    "immutable alert event conflict"
                )

            connection.execute(
                """
                INSERT INTO alert_events (
                    event_identity,
                    signal_freeze_identity,
                    source_kind,
                    policy_version,
                    signal_state,
                    event_json,
                    appended_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.signal_freeze_identity,
                    event.source_kind.value,
                    event.policy_version,
                    event.signal_state.value,
                    canonical_event,
                    inserted_at,
                ),
            )
        return AlertWriteDisposition.INSERTED

    def record_delivery_attempt(
        self,
        event_identity: str,
        sink_id: str,
        result: DeliveryResult,
        *,
        attempted_at_ms: int | None = None,
    ) -> AlertDeliveryAttempt:
        if not sink_id.strip():
            raise ValueError("alert sink id must be non-empty")
        attempted_at = (
            int(time.time() * 1000)
            if attempted_at_ms is None
            else attempted_at_ms
        )
        if attempted_at < 0:
            raise ValueError("alert attempt time must be non-negative")

        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            event_row = connection.execute(
                """
                SELECT event_identity
                FROM alert_events
                WHERE event_identity = ?
                """,
                (event_identity,),
            ).fetchone()
            if event_row is None:
                raise AlertOutboxConflictError(
                    "delivery attempt references unknown alert event"
                )

            latest = connection.execute(
                """
                SELECT attempt_number, status
                FROM alert_delivery_attempts
                WHERE event_identity = ? AND sink_id = ?
                ORDER BY attempt_number DESC
                LIMIT 1
                """,
                (event_identity, sink_id),
            ).fetchone()
            if latest is not None:
                latest_status = DeliveryAttemptStatus(str(latest["status"]))
                if latest_status in {
                    DeliveryAttemptStatus.DELIVERED,
                    DeliveryAttemptStatus.PERMANENT_FAILURE,
                }:
                    raise AlertOutboxConflictError(
                        "terminal alert delivery cannot be attempted again"
                    )
                attempt_number = int(latest["attempt_number"]) + 1
            else:
                attempt_number = 1

            attempt_identity = canonical_sha256(
                {
                    "event_identity": event_identity,
                    "sink_id": sink_id,
                    "attempt_number": attempt_number,
                    "attempted_at_ms": attempted_at,
                    "status": result.status,
                    "receipt": result.receipt,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                }
            )
            attempt = AlertDeliveryAttempt(
                attempt_identity=attempt_identity,
                event_identity=event_identity,
                sink_id=sink_id,
                attempt_number=attempt_number,
                attempted_at_ms=attempted_at,
                status=result.status,
                receipt=result.receipt,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            connection.execute(
                """
                INSERT INTO alert_delivery_attempts (
                    attempt_identity,
                    event_identity,
                    sink_id,
                    attempt_number,
                    attempted_at_ms,
                    status,
                    receipt,
                    error_code,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.attempt_identity,
                    attempt.event_identity,
                    attempt.sink_id,
                    attempt.attempt_number,
                    attempt.attempted_at_ms,
                    attempt.status.value,
                    attempt.receipt,
                    attempt.error_code,
                    attempt.error_message,
                ),
            )
        return attempt

    def list_events(self) -> tuple[AlertEventRecord, ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json, appended_at_ms
                FROM alert_events
                ORDER BY appended_at_ms ASC, event_identity ASC
                """
            ).fetchall()
        return tuple(
            AlertEventRecord(
                event=_parse_alert_event(str(row["event_json"])),
                appended_at_ms=int(row["appended_at_ms"]),
            )
            for row in rows
        )

    def pending_events(
        self,
        sink_id: str,
        *,
        limit: int = 100,
    ) -> tuple[AlertEvent, ...]:
        if not sink_id.strip():
            raise ValueError("alert sink id must be non-empty")
        if limit <= 0:
            raise ValueError("alert pending limit must be positive")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.event_json
                FROM alert_events AS e
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM alert_delivery_attempts AS a
                    WHERE a.event_identity = e.event_identity
                      AND a.sink_id = ?
                      AND a.status IN ('delivered', 'permanent_failure')
                )
                ORDER BY e.appended_at_ms ASC, e.event_identity ASC
                LIMIT ?
                """,
                (sink_id, limit),
            ).fetchall()
        return tuple(
            _parse_alert_event(str(row["event_json"]))
            for row in rows
        )

    def delivery_state(
        self,
        event_identity: str,
        sink_id: str,
    ) -> AlertDeliveryState:
        if not sink_id.strip():
            raise ValueError("alert sink id must be non-empty")
        self.initialize()
        with self._connect() as connection:
            event_row = connection.execute(
                """
                SELECT event_identity
                FROM alert_events
                WHERE event_identity = ?
                """,
                (event_identity,),
            ).fetchone()
            if event_row is None:
                raise AlertOutboxConflictError("unknown alert event")
            rows = connection.execute(
                """
                SELECT *
                FROM alert_delivery_attempts
                WHERE event_identity = ? AND sink_id = ?
                ORDER BY attempt_number ASC
                """,
                (event_identity, sink_id),
            ).fetchall()

        if not rows:
            return AlertDeliveryState(
                event_identity=event_identity,
                sink_id=sink_id,
                attempts=0,
                terminal=False,
                delivered=False,
                latest_status=None,
                latest_receipt=None,
            )

        latest = rows[-1]
        status = DeliveryAttemptStatus(str(latest["status"]))
        return AlertDeliveryState(
            event_identity=event_identity,
            sink_id=sink_id,
            attempts=len(rows),
            terminal=status in {
                DeliveryAttemptStatus.DELIVERED,
                DeliveryAttemptStatus.PERMANENT_FAILURE,
            },
            delivered=status is DeliveryAttemptStatus.DELIVERED,
            latest_status=status,
            latest_receipt=(
                None
                if latest["receipt"] is None
                else str(latest["receipt"])
            ),
        )

    def count_events(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM alert_events"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def count_attempts(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM alert_delivery_attempts"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _install_immutability_triggers(
        connection: sqlite3.Connection,
    ) -> None:
        for table in ("alert_events", "alert_delivery_attempts"):
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'immutable alert outbox rejects UPDATE'
                    );
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'immutable alert outbox rejects DELETE'
                    );
                END
                """
            )


def _parse_alert_event(value: str) -> AlertEvent:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AlertOutboxConflictError(
            "stored alert event JSON is invalid"
        ) from exc
    if not isinstance(raw, dict):
        raise AlertOutboxConflictError(
            "stored alert event JSON must be mapping"
        )
    try:
        flags_raw = raw["uncertainty_flags"]
        if not isinstance(flags_raw, list):
            raise TypeError("uncertainty flags must be list")
        event = AlertEvent(
            event_identity=str(raw["event_identity"]),
            schema_version=str(raw["schema_version"]),
            policy_version=str(raw["policy_version"]),
            source_kind=AlertSourceKind(str(raw["source_kind"])),
            signal_freeze_identity=str(raw["signal_freeze_identity"]),
            lifecycle_evaluation_identity=(
                None
                if raw["lifecycle_evaluation_identity"] is None
                else str(raw["lifecycle_evaluation_identity"])
            ),
            transition_identity=(
                None
                if raw["transition_identity"] is None
                else str(raw["transition_identity"])
            ),
            exchange=Exchange(str(raw["exchange"])),
            market_type=MarketType(str(raw["market_type"])),
            symbol=str(raw["symbol"]),
            timeframe=str(raw["timeframe"]),
            signal_state=SignalState(str(raw["signal_state"])),
            direction=SignalDirection(str(raw["direction"])),
            setup_type=str(raw["setup_type"]),
            decision_as_of_ms=int(raw["decision_as_of_ms"]),
            source_evaluated_as_of_ms=int(
                raw["source_evaluated_as_of_ms"]
            ),
            confluence_score=Decimal(str(raw["confluence_score"])),
            confluence_score_semantic=ScoreSemantic(
                str(raw["confluence_score_semantic"])
            ),
            probability_status=ProbabilityStatus(
                str(raw["probability_status"])
            ),
            uncertainty_flags=tuple(str(item) for item in flags_raw),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AlertOutboxConflictError(
            "stored alert event is semantically invalid"
        ) from exc
    verify_alert_event_identity(event)
    if event.schema_version != ALERT_SCHEMA_VERSION:
        raise AlertOutboxConflictError(
            "stored alert event schema is unsupported"
        )
    return event
