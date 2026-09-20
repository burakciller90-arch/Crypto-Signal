"""Strictly read-only dry-run composition for one scanned paper event.

This module composes already-accepted paper policies against immutable/cached
production data. It never persists a processed event, decision, fill, mutation,
NAV record, venue snapshot, or activation row. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.activation import PaperActivationState
from crypto_signal.paper.autonomy import (
    PaperAutonomyDecision,
    evaluate_autonomy_policy,
)
from crypto_signal.paper.event_scanner import PaperSignalEventCandidate
from crypto_signal.paper.execution_input import (
    FrozenPaperExecutionInput,
    PaperExecutionInputStatus,
    freeze_execution_input_from_cache,
)
from crypto_signal.paper.ledger import (
    PaperLedgerEntry,
    PaperRecordKind,
    deserialize_paper_record,
)
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    DecisionIntentRecord,
    PaperAction,
    PaperSymbol,
)
from crypto_signal.paper.sizing import (
    PaperPositionSizingDecision,
    PaperPositionSizingStatus,
    size_paper_candidate,
)
from crypto_signal.paper.state import (
    PaperFundState,
    reconstruct_paper_fund_state_from_entries,
)
from crypto_signal.paper.venue_rules import (
    PaperVenueBoundPretrade,
    prepare_authoritative_paper_trade_plan,
    read_latest_binance_spot_venue_rules,
)

__all__ = [
    "PAPER_ACTIVATION_DRY_RUN_VERSION",
    "PAPER_DECISION_TRACE_VERSION",
    "REAL_CAPITAL",
    "PaperActivationDryRunError",
    "PaperActivationDryRunResult",
    "PaperActivationDryRunStatus",
    "PaperDecisionTrace",
    "PaperDecisionTraceStage",
    "PaperDecisionTraceStep",
    "PaperDecisionTraceStepState",
    "evaluate_paper_activation_dry_run",
    "explain_paper_activation_dry_run",
    "read_paper_activation_read_only",
]

PAPER_ACTIVATION_DRY_RUN_VERSION = "paper_activation_dry_run.v1"
PAPER_DECISION_TRACE_VERSION = "paper_decision_trace.v1"
_TABLE_BY_KIND = {
    PaperRecordKind.FUND_CREATION: "paper_fund_creations",
    PaperRecordKind.DECISION_INTENT: "paper_decision_intents",
    PaperRecordKind.SIMULATED_FILL: "paper_simulated_fills",
    PaperRecordKind.POSITION_CASH_MUTATION: "paper_position_cash_mutations",
    PaperRecordKind.NAV_SNAPSHOT: "paper_nav_snapshots",
}


class PaperActivationDryRunError(RuntimeError):
    """Raised when dry-run production truth cannot be reconciled safely."""


class PaperActivationDryRunStatus(StrEnum):
    HOLD_CASH = "hold_cash"
    WAITING_EXECUTION_INPUT = "waiting_execution_input"
    WAITING_VENUE_RULES = "waiting_venue_rules"
    SIZING_REJECTED = "sizing_rejected"
    PRETRADE_REJECTED = "pretrade_rejected"
    PRETRADE_READY = "pretrade_ready"


class PaperDecisionTraceStage(StrEnum):
    AUTONOMY = "autonomy"
    EXECUTION_INPUT = "execution_input"
    VENUE_RULES = "venue_rules"
    SIZING = "sizing"
    PRETRADE = "pretrade"


class PaperDecisionTraceStepState(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    NOT_REACHED = "not_reached"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class PaperDecisionTraceStep:
    stage: PaperDecisionTraceStage
    state: PaperDecisionTraceStepState
    code: str
    source_detail: str | None = None
    evidence_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("decision trace step code must be non-empty")
        if self.source_detail is not None and not self.source_detail.strip():
            raise ValueError("decision trace source_detail must be non-empty when set")
        if self.evidence_identity is not None:
            _require_sha256(self.evidence_identity, "decision trace evidence identity")


@dataclass(frozen=True, slots=True)
class PaperDecisionTrace:
    trace_identity: str
    version: str
    event_identity: str
    terminal_status: PaperActivationDryRunStatus
    candidate_action: PaperAction
    steps: tuple[PaperDecisionTraceStep, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != PAPER_DECISION_TRACE_VERSION:
            raise ValueError("unsupported paper decision trace version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.trace_identity, "decision trace identity")
        _require_sha256(self.event_identity, "event_identity")
        expected_stages = tuple(PaperDecisionTraceStage)
        if tuple(step.stage for step in self.steps) != expected_stages:
            raise ValueError("decision trace must contain every stage exactly once")
        expected = canonical_sha256(
            {
                "candidate_action": self.candidate_action.value,
                "event_identity": self.event_identity,
                "steps": [
                    {
                        "code": step.code,
                        "evidence_identity": step.evidence_identity,
                        "source_detail": step.source_detail,
                        "stage": step.stage.value,
                        "state": step.state.value,
                    }
                    for step in self.steps
                ],
                "terminal_status": self.terminal_status.value,
                "version": self.version,
            }
        )
        if self.trace_identity != expected:
            raise ValueError("decision trace identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperActivationDryRunObservationSummary:
    total_events: int
    status_counts: tuple[tuple[str, int], ...]
    ready_event_identities: tuple[str, ...]
    attention_required: bool

    def __post_init__(self) -> None:
        if self.total_events < 0:
            raise ValueError("dry-run observation total cannot be negative")
        if any(count <= 0 for _, count in self.status_counts):
            raise ValueError("dry-run status counts must be positive")
        if self.status_counts != tuple(sorted(self.status_counts)):
            raise ValueError("dry-run status counts must be sorted")
        if self.ready_event_identities != tuple(sorted(self.ready_event_identities)):
            raise ValueError("ready event identities must be sorted")
        if len(set(self.ready_event_identities)) != len(
            self.ready_event_identities
        ):
            raise ValueError("ready event identities must be unique")
        for identity in self.ready_event_identities:
            _require_sha256(identity, "ready event identity")
        if self.attention_required != bool(self.ready_event_identities):
            raise ValueError("attention flag must match ready event presence")
        if sum(count for _, count in self.status_counts) != self.total_events:
            raise ValueError("dry-run status counts must cover all events")


@dataclass(frozen=True, slots=True)
class PaperActivationDryRunResult:
    version: str
    status: PaperActivationDryRunStatus
    event_identity: str
    autonomy: PaperAutonomyDecision
    execution_input: FrozenPaperExecutionInput | None
    venue_rule_snapshot_identity: str | None
    sizing: PaperPositionSizingDecision | None
    venue_bound_pretrade: PaperVenueBoundPretrade | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.version != PAPER_ACTIVATION_DRY_RUN_VERSION:
            raise ValueError("unsupported paper activation dry-run version")
        _require_sha256(self.event_identity, "event_identity")
        if self.autonomy.real_capital != REAL_CAPITAL:
            raise ValueError("autonomy dry-run must remain REAL_CAPITAL=0")
        if self.execution_input is not None and self.execution_input.real_capital != REAL_CAPITAL:
            raise ValueError("execution input must remain REAL_CAPITAL=0")
        if self.sizing is not None and self.sizing.real_capital != REAL_CAPITAL:
            raise ValueError("sizing must remain REAL_CAPITAL=0")
        if (
            self.venue_bound_pretrade is not None
            and self.venue_bound_pretrade.real_capital != REAL_CAPITAL
        ):
            raise ValueError("pretrade must remain REAL_CAPITAL=0")

        if self.status is PaperActivationDryRunStatus.HOLD_CASH:
            if self.autonomy.candidate_action is not PaperAction.HOLD_CASH:
                raise ValueError("HOLD_CASH dry-run requires HOLD autonomy")
            if any(
                item is not None
                for item in (
                    self.execution_input,
                    self.venue_rule_snapshot_identity,
                    self.sizing,
                    self.venue_bound_pretrade,
                )
            ):
                raise ValueError("HOLD_CASH dry-run cannot carry downstream trade truth")
        elif self.status is PaperActivationDryRunStatus.WAITING_EXECUTION_INPUT:
            if self.execution_input is not None:
                raise ValueError("waiting execution input cannot carry frozen input")
        elif self.status is PaperActivationDryRunStatus.WAITING_VENUE_RULES:
            if self.execution_input is None or self.venue_rule_snapshot_identity is not None:
                raise ValueError("waiting venue rules has invalid lineage")
        elif self.status is PaperActivationDryRunStatus.SIZING_REJECTED:
            if (
                self.execution_input is None
                or self.venue_rule_snapshot_identity is None
                or self.sizing is None
                or self.sizing.status is not PaperPositionSizingStatus.REJECTED
                or self.venue_bound_pretrade is not None
            ):
                raise ValueError("sizing-rejected dry-run has invalid lineage")
        elif self.status in {
            PaperActivationDryRunStatus.PRETRADE_REJECTED,
            PaperActivationDryRunStatus.PRETRADE_READY,
        }:
            if (
                self.execution_input is None
                or self.venue_rule_snapshot_identity is None
                or self.sizing is None
                or self.venue_bound_pretrade is None
            ):
                raise ValueError("pretrade dry-run requires complete downstream lineage")
            planned = self.venue_bound_pretrade.pretrade.status.value == "planned"
            if (
                self.status is PaperActivationDryRunStatus.PRETRADE_READY
                and not planned
            ):
                raise ValueError("PRETRADE_READY requires planned pretrade")
            if (
                self.status is PaperActivationDryRunStatus.PRETRADE_REJECTED
                and planned
            ):
                raise ValueError("PRETRADE_REJECTED cannot carry planned pretrade")


def explain_paper_activation_dry_run(
    result: PaperActivationDryRunResult,
) -> PaperDecisionTrace:
    """Project one dry-run result into a deterministic factual decision trace."""
    steps: list[PaperDecisionTraceStep] = []
    autonomy_passed = result.autonomy.candidate_action is not PaperAction.HOLD_CASH
    steps.append(
        PaperDecisionTraceStep(
            stage=PaperDecisionTraceStage.AUTONOMY,
            state=(
                PaperDecisionTraceStepState.PASSED
                if autonomy_passed
                else PaperDecisionTraceStepState.BLOCKED
            ),
            code=result.autonomy.reason_code.value,
            source_detail=result.autonomy.reason,
        )
    )

    if result.execution_input is not None:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.EXECUTION_INPUT,
                state=PaperDecisionTraceStepState.PASSED,
                code="frozen",
                evidence_identity=result.execution_input.input_identity,
            )
        )
    elif result.status is PaperActivationDryRunStatus.WAITING_EXECUTION_INPUT:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.EXECUTION_INPUT,
                state=PaperDecisionTraceStepState.BLOCKED,
                code=PaperExecutionInputStatus.WAITING_FOR_NEXT_CLOSED_CANDLE.value,
            )
        )
    else:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.EXECUTION_INPUT,
                state=PaperDecisionTraceStepState.NOT_REACHED,
                code="upstream_not_trade_candidate",
            )
        )

    if result.venue_rule_snapshot_identity is not None:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.VENUE_RULES,
                state=PaperDecisionTraceStepState.PASSED,
                code="authoritative_snapshot_selected",
                evidence_identity=result.venue_rule_snapshot_identity,
            )
        )
    elif result.status is PaperActivationDryRunStatus.WAITING_VENUE_RULES:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.VENUE_RULES,
                state=PaperDecisionTraceStepState.BLOCKED,
                code="no_authoritative_snapshot_asof_execution_input",
            )
        )
    else:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.VENUE_RULES,
                state=PaperDecisionTraceStepState.NOT_REACHED,
                code="upstream_not_ready",
            )
        )

    if result.sizing is not None:
        sizing_blocked = result.sizing.status is PaperPositionSizingStatus.REJECTED
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.SIZING,
                state=(
                    PaperDecisionTraceStepState.BLOCKED
                    if sizing_blocked
                    else PaperDecisionTraceStepState.PASSED
                ),
                code=result.sizing.reason_code.value,
                evidence_identity=result.sizing.sizing_identity,
            )
        )
    else:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.SIZING,
                state=PaperDecisionTraceStepState.NOT_REACHED,
                code="upstream_not_ready",
            )
        )

    if result.venue_bound_pretrade is not None:
        pretrade = result.venue_bound_pretrade.pretrade
        ready = result.status is PaperActivationDryRunStatus.PRETRADE_READY
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.PRETRADE,
                state=(
                    PaperDecisionTraceStepState.READY
                    if ready
                    else PaperDecisionTraceStepState.BLOCKED
                ),
                code=pretrade.reason_code.value,
                source_detail=pretrade.rejection_detail,
                evidence_identity=pretrade.pretrade_identity,
            )
        )
    else:
        steps.append(
            PaperDecisionTraceStep(
                stage=PaperDecisionTraceStage.PRETRADE,
                state=PaperDecisionTraceStepState.NOT_REACHED,
                code="upstream_not_ready",
            )
        )

    steps_tuple = tuple(steps)
    identity = canonical_sha256(
        {
            "candidate_action": result.autonomy.candidate_action.value,
            "event_identity": result.event_identity,
            "steps": [
                {
                    "code": step.code,
                    "evidence_identity": step.evidence_identity,
                    "source_detail": step.source_detail,
                    "stage": step.stage.value,
                    "state": step.state.value,
                }
                for step in steps_tuple
            ],
            "terminal_status": result.status.value,
            "version": PAPER_DECISION_TRACE_VERSION,
        }
    )
    return PaperDecisionTrace(
        trace_identity=identity,
        version=PAPER_DECISION_TRACE_VERSION,
        event_identity=result.event_identity,
        terminal_status=result.status,
        candidate_action=result.autonomy.candidate_action,
        steps=steps_tuple,
        real_capital=REAL_CAPITAL,
    )


def read_paper_activation_read_only(path: Path) -> PaperActivationState:
    """Load the immutable activation singleton without initializing or mutating DB."""
    if not path.exists():
        raise PaperActivationDryRunError("paper ledger does not exist")
    uri = f"file:{path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "paper_activation_state", "paper ledger")
            row = connection.execute(
                """
                SELECT activation_identity, payload_json, activated_at_ms
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise PaperActivationDryRunError(
            f"failed to read paper activation: {exc}"
        ) from exc
    if row is None:
        raise PaperActivationDryRunError("paper activation is not initialized")

    try:
        raw = json.loads(str(row["payload_json"]))
        activation = PaperActivationState(
            activation_identity=str(raw["activation_identity"]),
            schema_version=str(raw["schema_version"]),
            fund_identity=str(raw["fund_identity"]),
            activated_at_ms=int(raw["activated_at_ms"]),
            activation_cutoff_ms=int(raw["activation_cutoff_ms"]),
            baseline_signal_freeze_count=int(raw["baseline_signal_freeze_count"]),
            baseline_latest_signal_freeze_identity=(
                None
                if raw["baseline_latest_signal_freeze_identity"] is None
                else str(raw["baseline_latest_signal_freeze_identity"])
            ),
            baseline_latest_frozen_at_ms=(
                None
                if raw["baseline_latest_frozen_at_ms"] is None
                else int(raw["baseline_latest_frozen_at_ms"])
            ),
            real_capital=int(raw["real_capital"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PaperActivationDryRunError(
            "persistent paper activation payload is invalid"
        ) from exc
    if activation.activation_identity != str(row["activation_identity"]):
        raise PaperActivationDryRunError(
            "persistent activation identity/payload mismatch"
        )
    if activation.activated_at_ms != int(row["activated_at_ms"]):
        raise PaperActivationDryRunError(
            "persistent activation timestamp/payload mismatch"
        )
    return activation


def summarize_paper_activation_dry_runs(
    results: tuple[PaperActivationDryRunResult, ...],
) -> PaperActivationDryRunObservationSummary:
    status_counts: dict[str, int] = {}
    ready: list[str] = []
    for result in results:
        key = result.status.value
        status_counts[key] = status_counts.get(key, 0) + 1
        if result.status is PaperActivationDryRunStatus.PRETRADE_READY:
            ready.append(result.event_identity)
    return PaperActivationDryRunObservationSummary(
        total_events=len(results),
        status_counts=tuple(sorted(status_counts.items())),
        ready_event_identities=tuple(sorted(ready)),
        attention_required=bool(ready),
    )


def evaluate_paper_activation_dry_run(
    *,
    event: PaperSignalEventCandidate,
    activation: PaperActivationState,
    paper_ledger_path: Path,
    candle_cache_path: Path,
    evaluated_at_ms: int,
) -> PaperActivationDryRunResult:
    """Evaluate one unprocessed scanner event through pretrade without writes."""
    if event.real_capital != REAL_CAPITAL or activation.real_capital != REAL_CAPITAL:
        raise PaperActivationDryRunError("REAL_CAPITAL must remain 0")
    if event.activation_identity != activation.activation_identity:
        raise PaperActivationDryRunError("event/activation identity mismatch")
    if evaluated_at_ms < event.signal_as_of_ms:
        raise PaperActivationDryRunError("dry-run evaluation cannot predate signal as-of")

    state, last_actions = _read_paper_state_and_actions(
        path=paper_ledger_path,
        activation=activation,
        event_identity=event.event_identity,
    )
    mark_prices = _read_mark_prices(
        candle_cache_path=candle_cache_path,
        state=state,
        observed_at_ms=evaluated_at_ms,
    )
    autonomy = evaluate_autonomy_policy(
        state=state,
        signals=event.signals,
        evaluated_at_ms=evaluated_at_ms,
        activation_cutoff_ms=activation.activation_cutoff_ms,
        mark_prices=mark_prices,
        last_action_at_ms=last_actions,
    )
    if autonomy.candidate_action is PaperAction.HOLD_CASH:
        return _result(
            status=PaperActivationDryRunStatus.HOLD_CASH,
            event=event,
            autonomy=autonomy,
        )

    execution = freeze_execution_input_from_cache(
        candle_cache_path=candle_cache_path,
        autonomy_decision=autonomy,
        observed_at_ms=evaluated_at_ms,
    )
    if execution.status is PaperExecutionInputStatus.WAITING_FOR_NEXT_CLOSED_CANDLE:
        return _result(
            status=PaperActivationDryRunStatus.WAITING_EXECUTION_INPUT,
            event=event,
            autonomy=autonomy,
        )
    frozen_input = execution.frozen_input
    if frozen_input is None:
        raise PaperActivationDryRunError("FROZEN execution result lost input")

    venue_rules = read_latest_binance_spot_venue_rules(
        path=paper_ledger_path,
        symbol=frozen_input.symbol,
        observed_at_ms=frozen_input.observed_at_ms,
    )
    if venue_rules is None:
        return _result(
            status=PaperActivationDryRunStatus.WAITING_VENUE_RULES,
            event=event,
            autonomy=autonomy,
            execution_input=frozen_input,
        )

    sizing = size_paper_candidate(
        state=state,
        autonomy_decision=autonomy,
        execution_input=frozen_input,
        signals=event.signals,
    )
    if sizing.status is PaperPositionSizingStatus.REJECTED:
        return _result(
            status=PaperActivationDryRunStatus.SIZING_REJECTED,
            event=event,
            autonomy=autonomy,
            execution_input=frozen_input,
            venue_rule_snapshot_identity=venue_rules.snapshot_identity,
            sizing=sizing,
        )

    bound = prepare_authoritative_paper_trade_plan(
        state=state,
        sizing=sizing,
        execution_input=frozen_input,
        venue_rules=venue_rules,
        planned_at_ms=evaluated_at_ms,
        mark_prices=mark_prices,
    )
    status = (
        PaperActivationDryRunStatus.PRETRADE_READY
        if bound.pretrade.status.value == "planned"
        else PaperActivationDryRunStatus.PRETRADE_REJECTED
    )
    return _result(
        status=status,
        event=event,
        autonomy=autonomy,
        execution_input=frozen_input,
        venue_rule_snapshot_identity=venue_rules.snapshot_identity,
        sizing=sizing,
        venue_bound_pretrade=bound,
    )


def _read_paper_state_and_actions(
    *,
    path: Path,
    activation: PaperActivationState,
    event_identity: str,
) -> tuple[PaperFundState, dict[PaperSymbol, int]]:
    if not path.exists():
        raise PaperActivationDryRunError("paper ledger does not exist")
    uri = f"file:{path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            required = tuple(_TABLE_BY_KIND.values()) + (
                "paper_replay_index",
                "paper_activation_state",
                "paper_processed_events",
            )
            for table in required:
                _require_table(connection, table, "paper ledger")
            activation_row = connection.execute(
                """
                SELECT activation_identity
                FROM paper_activation_state
                WHERE singleton = 1
                """
            ).fetchone()
            if (
                activation_row is None
                or str(activation_row["activation_identity"])
                != activation.activation_identity
            ):
                raise PaperActivationDryRunError(
                    "persistent activation identity mismatch"
                )
            processed = connection.execute(
                """
                SELECT 1
                FROM paper_processed_events
                WHERE event_identity = ?
                """,
                (event_identity,),
            ).fetchone()
            if processed is not None:
                raise PaperActivationDryRunError(
                    "dry-run refuses already processed event"
                )
            rows = connection.execute(
                """
                SELECT sequence_id, record_kind, record_identity, appended_at_ms
                FROM paper_replay_index
                ORDER BY sequence_id ASC
                """
            ).fetchall()
            entries: list[PaperLedgerEntry] = []
            for row in rows:
                kind = PaperRecordKind(str(row["record_kind"]))
                table = _TABLE_BY_KIND[kind]
                payload_row = connection.execute(
                    f"""
                    SELECT payload_json
                    FROM {table}
                    WHERE record_identity = ?
                    """,
                    (str(row["record_identity"]),),
                ).fetchone()
                if payload_row is None:
                    raise PaperActivationDryRunError(
                        "paper replay index references missing payload"
                    )
                payload_json = str(payload_row["payload_json"])
                entries.append(
                    PaperLedgerEntry(
                        sequence_id=int(row["sequence_id"]),
                        record_kind=kind,
                        record_identity=str(row["record_identity"]),
                        appended_at_ms=int(row["appended_at_ms"]),
                        payload_json=payload_json,
                        record=deserialize_paper_record(kind, payload_json),
                    )
                )
    except sqlite3.Error as exc:
        raise PaperActivationDryRunError(
            f"failed to read paper ledger: {exc}"
        ) from exc

    state = reconstruct_paper_fund_state_from_entries(tuple(entries))
    if state.fund_identity != activation.fund_identity:
        raise PaperActivationDryRunError("activation/paper fund identity mismatch")
    last_actions: dict[PaperSymbol, int] = {}
    for entry in entries:
        record = entry.record
        if (
            isinstance(record, DecisionIntentRecord)
            and record.action in {PaperAction.BUY, PaperAction.EXIT}
            and record.symbol is not None
        ):
            current = last_actions.get(record.symbol)
            if current is None or record.decided_at_ms > current:
                last_actions[record.symbol] = record.decided_at_ms
    return state, last_actions


def _read_mark_prices(
    *,
    candle_cache_path: Path,
    state: PaperFundState,
    observed_at_ms: int,
) -> dict[PaperSymbol, Decimal]:
    if not state.positions:
        return {}
    if not candle_cache_path.exists():
        raise PaperActivationDryRunError("canonical candle cache does not exist")
    uri = f"file:{candle_cache_path.resolve()}?mode=ro"
    marks: dict[PaperSymbol, Decimal] = {}
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            _require_table(connection, "candles", "candle cache")
            for position in state.positions:
                row = connection.execute(
                    """
                    SELECT close
                    FROM candles
                    WHERE exchange = ?
                      AND market_type = ?
                      AND symbol = ?
                      AND timeframe = ?
                      AND is_closed = 1
                      AND close_time_ms <= ?
                      AND ingested_at_ms <= ?
                      AND source_timestamp_ms <= ?
                    ORDER BY open_time_ms DESC
                    LIMIT 1
                    """,
                    (
                        Exchange.BINANCE.value,
                        MarketType.SPOT.value,
                        position.symbol.value,
                        "15m",
                        observed_at_ms,
                        observed_at_ms,
                        observed_at_ms,
                    ),
                ).fetchone()
                if row is not None:
                    marks[position.symbol] = Decimal(str(row["close"]))
    except sqlite3.Error as exc:
        raise PaperActivationDryRunError(
            f"failed to read paper mark prices: {exc}"
        ) from exc
    return marks


def _result(
    *,
    status: PaperActivationDryRunStatus,
    event: PaperSignalEventCandidate,
    autonomy: PaperAutonomyDecision,
    execution_input: FrozenPaperExecutionInput | None = None,
    venue_rule_snapshot_identity: str | None = None,
    sizing: PaperPositionSizingDecision | None = None,
    venue_bound_pretrade: PaperVenueBoundPretrade | None = None,
) -> PaperActivationDryRunResult:
    return PaperActivationDryRunResult(
        version=PAPER_ACTIVATION_DRY_RUN_VERSION,
        status=status,
        event_identity=event.event_identity,
        autonomy=autonomy,
        execution_input=execution_input,
        venue_rule_snapshot_identity=venue_rule_snapshot_identity,
        sizing=sizing,
        venue_bound_pretrade=venue_bound_pretrade,
        real_capital=REAL_CAPITAL,
    )


def _require_table(
    connection: sqlite3.Connection,
    table: str,
    label: str,
) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table,),
    ).fetchone()
    if row is None:
        raise PaperActivationDryRunError(f"{label} missing required table: {table}")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
