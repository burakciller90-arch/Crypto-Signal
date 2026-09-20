from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.alerts.models import AlertPolicy
from crypto_signal.alerts.planner import (
    plan_initial_alert,
    plan_lifecycle_alert,
)
from crypto_signal.alerts.store import (
    AlertOutbox,
    AlertWriteDisposition,
)
from crypto_signal.ledger.deserialization import (
    LedgerDeserializationError,
    parse_lifecycle_evaluation,
    parse_signal_decision,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.signals.models import SignalDecision


class AlertClockSourceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AlertClockResult:
    signal_rows: int
    lifecycle_rows: int
    eligible_events: int
    inserted_events: int
    unchanged_events: int

    def __post_init__(self) -> None:
        values = (
            self.signal_rows,
            self.lifecycle_rows,
            self.eligible_events,
            self.inserted_events,
            self.unchanged_events,
        )
        if any(value < 0 for value in values):
            raise ValueError("alert clock counts must be non-negative")
        if self.eligible_events != (
            self.inserted_events + self.unchanged_events
        ):
            raise ValueError(
                "eligible alert count must equal inserted + unchanged"
            )


def _connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AlertClockSourceError("signal ledger does not exist")
    connection = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _require_table(
    connection: sqlite3.Connection,
    table: str,
) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table,),
    ).fetchone()
    if row is None:
        raise AlertClockSourceError(
            f"signal ledger missing required table: {table}"
        )


def _parse_signal_row(row: sqlite3.Row) -> SignalDecision:
    try:
        root = json.loads(str(row["bundle_json"]))
        if not isinstance(root, dict):
            raise AlertClockSourceError(
                "signal bundle JSON must be mapping"
            )
        decision = parse_signal_decision(root.get("signal_decision"))
    except (
        json.JSONDecodeError,
        LedgerDeserializationError,
    ) as exc:
        raise AlertClockSourceError(
            "signal freeze cannot be reconstructed"
        ) from exc

    if decision.freeze_identity != str(row["signal_freeze_identity"]):
        raise AlertClockSourceError(
            "signal freeze identity mismatch"
        )
    if decision.as_of_ms != int(row["as_of_ms"]):
        raise AlertClockSourceError("signal as-of mismatch")
    if decision.state.value != str(row["signal_state"]):
        raise AlertClockSourceError("signal state mismatch")
    return decision


def materialize_alert_events(
    signal_ledger_path: Path,
    outbox: AlertOutbox,
    *,
    policy: AlertPolicy | None = None,
) -> AlertClockResult:
    selected_policy = (
        AlertPolicy.default_v1()
        if policy is None
        else policy
    )
    decisions: dict[str, SignalDecision] = {}
    signal_rows_count = 0
    lifecycle_rows_count = 0
    eligible = 0
    inserted = 0
    unchanged = 0

    with _connect_read_only(signal_ledger_path) as connection:
        _require_table(connection, "signal_freezes")
        _require_table(connection, "lifecycle_evaluations")

        signal_rows = connection.execute(
            """
            SELECT *
            FROM signal_freezes
            ORDER BY frozen_at_ms ASC, signal_freeze_identity ASC
            """
        ).fetchall()
        signal_rows_count = len(signal_rows)

        for row in signal_rows:
            decision = _parse_signal_row(row)
            decisions[decision.freeze_identity] = decision
            event = plan_initial_alert(
                decision,
                policy=selected_policy,
            )
            if event is None:
                continue
            eligible += 1
            disposition = outbox.append_event(
                event,
                appended_at_ms=int(row["frozen_at_ms"]),
            )
            if disposition is AlertWriteDisposition.INSERTED:
                inserted += 1
            else:
                unchanged += 1

        lifecycle_rows = connection.execute(
            """
            SELECT *
            FROM lifecycle_evaluations
            ORDER BY appended_at_ms ASC, evaluation_identity ASC
            """
        ).fetchall()
        lifecycle_rows_count = len(lifecycle_rows)

        for row in lifecycle_rows:
            signal_identity = str(row["signal_freeze_identity"])
            parent_decision = decisions.get(signal_identity)
            if parent_decision is None:
                raise AlertClockSourceError(
                    "lifecycle evaluation references missing signal"
                )
            try:
                raw = json.loads(str(row["evaluation_json"]))
                evaluation = parse_lifecycle_evaluation(raw)
            except (
                json.JSONDecodeError,
                LedgerDeserializationError,
            ) as exc:
                raise AlertClockSourceError(
                    "lifecycle evaluation cannot be reconstructed"
                ) from exc

            expected_identity = canonical_sha256(evaluation)
            if expected_identity != str(row["evaluation_identity"]):
                raise AlertClockSourceError(
                    "lifecycle evaluation identity mismatch"
                )
            if evaluation.signal_freeze_identity != signal_identity:
                raise AlertClockSourceError(
                    "lifecycle signal identity mismatch"
                )
            if evaluation.evaluated_as_of_ms != int(
                row["evaluated_as_of_ms"]
            ):
                raise AlertClockSourceError(
                    "lifecycle evaluated-as-of mismatch"
                )
            if evaluation.current_state.value != str(
                row["current_state"]
            ):
                raise AlertClockSourceError(
                    "lifecycle current-state mismatch"
                )
            if evaluation.status.value != str(row["status"]):
                raise AlertClockSourceError(
                    "lifecycle status mismatch"
                )

            event = plan_lifecycle_alert(
                parent_decision,
                evaluation,
                policy=selected_policy,
            )
            if event is None:
                continue
            eligible += 1
            disposition = outbox.append_event(
                event,
                appended_at_ms=int(row["appended_at_ms"]),
            )
            if disposition is AlertWriteDisposition.INSERTED:
                inserted += 1
            else:
                unchanged += 1

    return AlertClockResult(
        signal_rows=signal_rows_count,
        lifecycle_rows=lifecycle_rows_count,
        eligible_events=eligible,
        inserted_events=inserted,
        unchanged_events=unchanged,
    )
