from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.forecast_stream import ForecastResolution, ImmutableForecast
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.epoch2_accounting import Epoch2VaultAccountingSnapshot
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import (
    DecisionIntentRecord,
    PaperAction,
    PaperPosition,
    PositionCashMutationRecord,
    SimulatedFillRecord,
    normalize_positions,
)
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingAssessment,
    SizingMethodResult,
    SizingMethodStatus,
)

R22_TAPE_ENGINE_VERSION = "r22-transaction-decision-tape-v1-slice1/1"
R22_TAPE_SCHEMA_VERSION = "r22-transaction-decision-tape-v1/1"
R22_TAPE_AUTHORITY = "audit_only_no_capital_mutation"
REAL_CAPITAL = 0


class R22TapeEventKind(StrEnum):
    HOLD_DECISION = "hold_decision"
    CAPITAL_MUTATION = "capital_mutation"


class R22TapeOutcome(StrEnum):
    HOLD_CASH = "hold_cash"
    OPEN = "open"
    PARTIAL_REDUCTION = "partial_reduction"
    CLOSED_WIN = "closed_win"
    CLOSED_LOSS = "closed_loss"
    CLOSED_BREAKEVEN = "closed_breakeven"


@dataclass(frozen=True, slots=True)
class R22TransactionDecisionRecord:
    record_identity: str
    schema_version: str
    engine_version: str
    authority: str
    previous_record_identity: str | None
    event_kind: R22TapeEventKind
    event_at_ms: int
    forecast_identity: str
    forecast_resolution_identity: str | None
    vault_id: PaperVaultId
    sizing_assessment_identity: str
    sizing_result_identity: str
    sizing_policy_identity: str
    allocator_candidate_identity: str
    decision_identity: str
    fill_identity: str | None
    mutation_identity: str | None
    before_snapshot_identity: str
    after_snapshot_identity: str | None
    action: PaperAction
    symbol: str | None
    quantity: Decimal | None
    reference_price: Decimal | None
    simulated_fill_price: Decimal | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    cash_before_usdt: Decimal
    cash_after_usdt: Decimal
    positions_before: tuple[PaperPosition, ...]
    positions_after: tuple[PaperPosition, ...]
    nav_before_usdt: Decimal
    nav_after_usdt: Decimal
    nav_delta_usdt: Decimal
    exposure_before_usdt: Decimal
    exposure_after_usdt: Decimal
    exposure_delta_usdt: Decimal
    realized_pnl_before_usdt: Decimal
    realized_pnl_after_usdt: Decimal
    realized_pnl_delta_usdt: Decimal
    unrealized_pnl_before_usdt: Decimal
    unrealized_pnl_after_usdt: Decimal
    unrealized_pnl_delta_usdt: Decimal
    turnover_notional_delta_usdt: Decimal
    risk_policy_version: str
    execution_policy_version: str | None
    outcome: R22TapeOutcome
    source_evidence_identities: tuple[str, ...]
    immutable: bool = True
    production_authority: bool = False
    canonical_capital_write_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.record_identity, "R22 record identity"),
            (self.forecast_identity, "R22 forecast identity"),
            (self.sizing_assessment_identity, "R22 sizing assessment identity"),
            (self.sizing_result_identity, "R22 sizing result identity"),
            (self.sizing_policy_identity, "R22 sizing policy identity"),
            (self.allocator_candidate_identity, "R22 allocator candidate identity"),
            (self.decision_identity, "R22 decision identity"),
            (self.before_snapshot_identity, "R22 before snapshot identity"),
        ):
            _require_sha256(value, label)
        for value, label in (
            (self.previous_record_identity, "R22 previous record identity"),
            (self.forecast_resolution_identity, "R22 forecast resolution identity"),
            (self.fill_identity, "R22 fill identity"),
            (self.mutation_identity, "R22 mutation identity"),
            (self.after_snapshot_identity, "R22 after snapshot identity"),
        ):
            if value is not None:
                _require_sha256(value, label)
        if self.schema_version != R22_TAPE_SCHEMA_VERSION:
            raise ValueError("unsupported R22 tape schema")
        if self.engine_version != R22_TAPE_ENGINE_VERSION:
            raise ValueError("unsupported R22 tape engine")
        if self.authority != R22_TAPE_AUTHORITY:
            raise ValueError("R22 tape must remain audit-only")
        if self.event_at_ms < 0:
            raise ValueError("R22 event time must be non-negative")
        if tuple(sorted(set(self.source_evidence_identities))) != (
            self.source_evidence_identities
        ):
            raise ValueError("R22 source evidence identities must be unique and sorted")
        if not self.source_evidence_identities:
            raise ValueError("R22 tape record requires source evidence")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "R22 source evidence identity")
        if self.positions_before != normalize_positions(self.positions_before):
            raise ValueError("R22 positions_before must be normalized")
        if self.positions_after != normalize_positions(self.positions_after):
            raise ValueError("R22 positions_after must be normalized")
        for value, label in (
            (self.fee_usdt, "R22 fee"),
            (self.spread_usdt, "R22 spread"),
            (self.slippage_usdt, "R22 slippage"),
            (self.cash_before_usdt, "R22 cash before"),
            (self.cash_after_usdt, "R22 cash after"),
            (self.nav_before_usdt, "R22 NAV before"),
            (self.nav_after_usdt, "R22 NAV after"),
            (self.exposure_before_usdt, "R22 exposure before"),
            (self.exposure_after_usdt, "R22 exposure after"),
            (self.turnover_notional_delta_usdt, "R22 turnover delta"),
        ):
            _require_non_negative(value, label)
        for value, label in (
            (self.nav_delta_usdt, "R22 NAV delta"),
            (self.exposure_delta_usdt, "R22 exposure delta"),
            (self.realized_pnl_before_usdt, "R22 realized PnL before"),
            (self.realized_pnl_after_usdt, "R22 realized PnL after"),
            (self.realized_pnl_delta_usdt, "R22 realized PnL delta"),
            (self.unrealized_pnl_before_usdt, "R22 unrealized PnL before"),
            (self.unrealized_pnl_after_usdt, "R22 unrealized PnL after"),
            (self.unrealized_pnl_delta_usdt, "R22 unrealized PnL delta"),
        ):
            _require_finite(value, label)
        if self.nav_delta_usdt != self.nav_after_usdt - self.nav_before_usdt:
            raise ValueError("R22 NAV delta mismatch")
        if (
            self.exposure_delta_usdt
            != self.exposure_after_usdt - self.exposure_before_usdt
        ):
            raise ValueError("R22 exposure delta mismatch")
        if (
            self.realized_pnl_delta_usdt
            != self.realized_pnl_after_usdt - self.realized_pnl_before_usdt
        ):
            raise ValueError("R22 realized PnL delta mismatch")
        if (
            self.unrealized_pnl_delta_usdt
            != self.unrealized_pnl_after_usdt - self.unrealized_pnl_before_usdt
        ):
            raise ValueError("R22 unrealized PnL delta mismatch")
        _require_text(self.risk_policy_version, "R22 risk policy version")
        if self.execution_policy_version is not None:
            _require_text(self.execution_policy_version, "R22 execution policy version")

        if self.event_kind is R22TapeEventKind.HOLD_DECISION:
            if self.action is not PaperAction.HOLD_CASH:
                raise ValueError("R22 hold event requires HOLD_CASH action")
            if any(
                value is not None
                for value in (
                    self.fill_identity,
                    self.mutation_identity,
                    self.after_snapshot_identity,
                    self.symbol,
                    self.quantity,
                    self.reference_price,
                    self.simulated_fill_price,
                    self.entry_price,
                    self.exit_price,
                    self.execution_policy_version,
                )
            ):
                raise ValueError("R22 HOLD_CASH event cannot expose trade/fill fields")
            if any(
                value != Decimal(0)
                for value in (
                    self.fee_usdt,
                    self.spread_usdt,
                    self.slippage_usdt,
                    self.nav_delta_usdt,
                    self.exposure_delta_usdt,
                    self.realized_pnl_delta_usdt,
                    self.unrealized_pnl_delta_usdt,
                    self.turnover_notional_delta_usdt,
                )
            ):
                raise ValueError("R22 HOLD_CASH event cannot mutate capital state")
            if (
                self.cash_before_usdt != self.cash_after_usdt
                or self.positions_before != self.positions_after
                or self.nav_before_usdt != self.nav_after_usdt
                or self.outcome is not R22TapeOutcome.HOLD_CASH
            ):
                raise ValueError("R22 HOLD_CASH before/after state must be unchanged")
        else:
            _validate_mutation_fields(self)

        if not self.immutable:
            raise ValueError("R22 tape records must remain immutable")
        if self.production_authority or self.canonical_capital_write_authority:
            raise ValueError("R22 tape has no production/capital mutation authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.record_identity != canonical_sha256(_record_payload(self)):
            raise ValueError("R22 tape record identity mismatch")


@dataclass(frozen=True, slots=True)
class R22StoredTapeRow:
    record_identity: str
    event_at_ms: int
    previous_record_identity: str | None
    payload_json: str
    payload_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "R22 stored record identity")
        if self.previous_record_identity is not None:
            _require_sha256(
                self.previous_record_identity,
                "R22 stored previous record identity",
            )
        _require_sha256(self.payload_sha256, "R22 stored payload SHA256")
        if self.event_at_ms < 0:
            raise ValueError("R22 stored event time must be non-negative")
        if sha256_text(self.payload_json) != self.payload_sha256:
            raise ValueError("R22 stored payload hash mismatch")
        if self.record_identity != self.payload_sha256:
            raise ValueError("R22 stored record identity/payload hash mismatch")
        payload = json.loads(self.payload_json)
        if not isinstance(payload, dict) or canonical_json(payload) != self.payload_json:
            raise ValueError("R22 stored payload must be a canonical object")
        if payload.get("event_at_ms") != self.event_at_ms:
            raise ValueError("R22 stored event time/payload mismatch")
        if payload.get("previous_record_identity") != self.previous_record_identity:
            raise ValueError("R22 stored previous identity/payload mismatch")
        if (
            payload.get("schema_version") != R22_TAPE_SCHEMA_VERSION
            or payload.get("engine_version") != R22_TAPE_ENGINE_VERSION
            or payload.get("authority") != R22_TAPE_AUTHORITY
            or payload.get("real_capital") != REAL_CAPITAL
        ):
            raise ValueError("R22 stored payload authority/schema mismatch")


class R22TransactionDecisionTape:
    """Append-only audit ledger. It cannot mutate the canonical paper fund."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS r22_transaction_decision_tape (
                    record_identity TEXT PRIMARY KEY,
                    event_at_ms INTEGER NOT NULL,
                    previous_record_identity TEXT,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS r22_tape_no_{operation.lower()}
                    BEFORE {operation} ON r22_transaction_decision_tape
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable R22 transaction tape');
                    END
                    """
                )

    def append(self, record: R22TransactionDecisionRecord) -> bool:
        payload_json = canonical_json(_record_payload(record))
        payload_sha = sha256_text(payload_json)
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM r22_transaction_decision_tape
                WHERE record_identity = ?
                """,
                (record.record_identity,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["payload_json"] != payload_json
                    or existing["payload_sha256"] != payload_sha
                ):
                    raise ValueError("R22 duplicate identity payload mismatch")
                return False

            latest = connection.execute(
                """
                SELECT record_identity, event_at_ms
                FROM r22_transaction_decision_tape
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
            if latest is None:
                if record.previous_record_identity is not None:
                    raise ValueError("first R22 record cannot reference previous record")
            else:
                if record.previous_record_identity != latest["record_identity"]:
                    raise ValueError("R22 previous record lineage mismatch")
                if record.event_at_ms < int(latest["event_at_ms"]):
                    raise ValueError("R22 tape cannot backfill before latest event")

            connection.execute(
                """
                INSERT INTO r22_transaction_decision_tape (
                    record_identity,
                    event_at_ms,
                    previous_record_identity,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.record_identity,
                    record.event_at_ms,
                    record.previous_record_identity,
                    payload_json,
                    payload_sha,
                ),
            )
        return True

    def read_rows(self) -> tuple[R22StoredTapeRow, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    record_identity,
                    event_at_ms,
                    previous_record_identity,
                    payload_json,
                    payload_sha256
                FROM r22_transaction_decision_tape
                ORDER BY rowid ASC
                """
            ).fetchall()
        result = tuple(
            R22StoredTapeRow(
                record_identity=str(row["record_identity"]),
                event_at_ms=int(row["event_at_ms"]),
                previous_record_identity=(
                    None
                    if row["previous_record_identity"] is None
                    else str(row["previous_record_identity"])
                ),
                payload_json=str(row["payload_json"]),
                payload_sha256=str(row["payload_sha256"]),
            )
            for row in rows
        )
        previous: str | None = None
        previous_time: int | None = None
        for row in result:
            if row.previous_record_identity != previous:
                raise ValueError("R22 stored tape lineage is broken")
            if previous_time is not None and row.event_at_ms < previous_time:
                raise ValueError("R22 stored tape chronology is broken")
            previous = row.record_identity
            previous_time = row.event_at_ms
        return result


def build_hold_cash_tape_record(
    *,
    forecast: ImmutableForecast,
    vault_id: PaperVaultId,
    sizing_assessment: PositionSizingAssessment,
    sizing_result: SizingMethodResult,
    decision: DecisionIntentRecord,
    current_snapshot: Epoch2VaultAccountingSnapshot,
    previous_record_identity: str | None = None,
    additional_evidence_identities: tuple[str, ...] = (),
) -> R22TransactionDecisionRecord:
    _validate_common_lineage(
        forecast=forecast,
        vault_id=vault_id,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        before_snapshot=current_snapshot,
    )
    if decision.action is not PaperAction.HOLD_CASH:
        raise ValueError("R22 hold builder requires HOLD_CASH decision")
    sources = _source_identities(
        forecast=forecast,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        fill=None,
        mutation=None,
        before_snapshot=current_snapshot,
        after_snapshot=None,
        forecast_resolution=None,
        additional=additional_evidence_identities,
    )
    payload = _base_payload(
        previous_record_identity=previous_record_identity,
        event_kind=R22TapeEventKind.HOLD_DECISION,
        event_at_ms=decision.decided_at_ms,
        forecast=forecast,
        forecast_resolution=None,
        vault_id=vault_id,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        fill=None,
        mutation=None,
        before_snapshot=current_snapshot,
        after_snapshot=None,
        outcome=R22TapeOutcome.HOLD_CASH,
        source_evidence_identities=sources,
    )
    return R22TransactionDecisionRecord(
        record_identity=canonical_sha256(payload),
        **payload,
    )


def build_capital_mutation_tape_record(
    *,
    forecast: ImmutableForecast,
    vault_id: PaperVaultId,
    sizing_assessment: PositionSizingAssessment,
    sizing_result: SizingMethodResult,
    decision: DecisionIntentRecord,
    fill: SimulatedFillRecord,
    mutation: PositionCashMutationRecord,
    before_snapshot: Epoch2VaultAccountingSnapshot,
    after_snapshot: Epoch2VaultAccountingSnapshot,
    forecast_resolution: ForecastResolution | None = None,
    previous_record_identity: str | None = None,
    additional_evidence_identities: tuple[str, ...] = (),
) -> R22TransactionDecisionRecord:
    _validate_common_lineage(
        forecast=forecast,
        vault_id=vault_id,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        before_snapshot=before_snapshot,
    )
    if decision.action is PaperAction.HOLD_CASH:
        raise ValueError("R22 mutation builder cannot accept HOLD_CASH")
    if sizing_result.status is not SizingMethodStatus.AVAILABLE_SHADOW:
        raise ValueError("R22 capital mutation requires available sizing evidence")
    if sizing_result.hypothetical_notional_usdt is None:
        raise ValueError("R22 capital mutation requires sizing hypothetical notional")
    assert decision.quantity is not None
    assert decision.reference_price is not None
    decision_notional = decision.quantity * decision.reference_price
    if decision_notional > sizing_result.hypothetical_notional_usdt:
        raise ValueError("R22 decision notional exceeds traced sizing envelope")

    if (
        fill.decision_identity != decision.record_identity
        or fill.fund_identity != decision.fund_identity
        or fill.action is not decision.action
        or fill.symbol is not decision.symbol
        or fill.quantity != decision.quantity
        or fill.reference_price != decision.reference_price
    ):
        raise ValueError("R22 fill does not exactly match decision intent")
    if fill.filled_at_ms < decision.decided_at_ms:
        raise ValueError("R22 fill cannot predate decision")
    if mutation.fund_identity != decision.fund_identity:
        raise ValueError("R22 mutation fund identity mismatch")
    if mutation.source_identity != fill.record_identity:
        raise ValueError("R22 mutation must be sourced from exact fill")
    if mutation.mutated_at_ms < fill.filled_at_ms:
        raise ValueError("R22 mutation cannot predate fill")
    if after_snapshot.vault_id is not vault_id:
        raise ValueError("R22 after snapshot vault mismatch")
    if after_snapshot.activation_identity != before_snapshot.activation_identity:
        raise ValueError("R22 before/after activation mismatch")
    if decision.fund_identity != before_snapshot.activation_identity:
        raise ValueError("R22 paper decision must target exact Epoch2 activation")
    if after_snapshot.previous_snapshot_identity != before_snapshot.snapshot_identity:
        raise ValueError("R22 after snapshot must directly follow before snapshot")
    if before_snapshot.snapshot_at_ms > decision.decided_at_ms:
        raise ValueError("R22 before snapshot cannot postdate decision")
    if after_snapshot.snapshot_at_ms < mutation.mutated_at_ms:
        raise ValueError("R22 after snapshot cannot predate mutation")
    required_sources = {
        decision.record_identity,
        fill.record_identity,
        mutation.record_identity,
    }
    if not required_sources.issubset(after_snapshot.source_record_identities):
        raise ValueError("R22 after snapshot lacks exact decision/fill/mutation lineage")
    if (
        mutation.cash_before_usdt != before_snapshot.cash_usdt
        or mutation.cash_after_usdt != after_snapshot.cash_usdt
        or mutation.positions_before != before_snapshot.positions
        or mutation.positions_after != after_snapshot.positions
    ):
        raise ValueError("R22 mutation does not reconcile before/after vault state")
    if after_snapshot.fee_usdt - before_snapshot.fee_usdt != fill.costs.fee_usdt:
        raise ValueError("R22 fee delta does not match fill")
    if after_snapshot.spread_usdt - before_snapshot.spread_usdt != fill.costs.spread_usdt:
        raise ValueError("R22 spread delta does not match fill")
    if (
        after_snapshot.slippage_usdt - before_snapshot.slippage_usdt
        != fill.costs.slippage_usdt
    ):
        raise ValueError("R22 slippage delta does not match fill")
    turnover_delta = (
        after_snapshot.turnover_notional_usdt
        - before_snapshot.turnover_notional_usdt
    )
    expected_turnover = fill.quantity * fill.simulated_fill_price
    if turnover_delta != expected_turnover:
        raise ValueError("R22 turnover delta does not match simulated fill notional")

    if forecast_resolution is not None:
        if forecast_resolution.forecast_identity != forecast.forecast_identity:
            raise ValueError("R22 forecast resolution/forecast mismatch")
        if forecast_resolution.evaluated_at_ms < mutation.mutated_at_ms:
            raise ValueError("R22 forecast resolution cannot predate capital mutation")

    outcome = _financial_outcome(
        decision.action,
        after_snapshot.realized_pnl_usdt - before_snapshot.realized_pnl_usdt,
    )
    sources = _source_identities(
        forecast=forecast,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        fill=fill,
        mutation=mutation,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        forecast_resolution=forecast_resolution,
        additional=additional_evidence_identities,
    )
    payload = _base_payload(
        previous_record_identity=previous_record_identity,
        event_kind=R22TapeEventKind.CAPITAL_MUTATION,
        event_at_ms=after_snapshot.snapshot_at_ms,
        forecast=forecast,
        forecast_resolution=forecast_resolution,
        vault_id=vault_id,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        fill=fill,
        mutation=mutation,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        outcome=outcome,
        source_evidence_identities=sources,
    )
    return R22TransactionDecisionRecord(
        record_identity=canonical_sha256(payload),
        **payload,
    )


def _validate_common_lineage(
    *,
    forecast: ImmutableForecast,
    vault_id: PaperVaultId,
    sizing_assessment: PositionSizingAssessment,
    sizing_result: SizingMethodResult,
    decision: DecisionIntentRecord,
    before_snapshot: Epoch2VaultAccountingSnapshot,
) -> None:
    if sizing_assessment.vault_id is not vault_id:
        raise ValueError("R22 sizing assessment vault mismatch")
    if sizing_result.result_identity not in sizing_assessment.result_identities:
        raise ValueError("R22 sizing result does not belong to assessment")
    if sizing_assessment.policy_identity == sizing_result.result_identity:
        raise ValueError("R22 sizing policy/result identities must remain distinct")
    if before_snapshot.vault_id is not vault_id:
        raise ValueError("R22 before snapshot vault mismatch")
    if before_snapshot.activation_identity != decision.fund_identity:
        raise ValueError("R22 decision fund must equal Epoch2 activation")
    if decision.decided_at_ms < forecast.issued_at_ms:
        raise ValueError("R22 decision cannot predate forecast issuance")
    if decision.action is not PaperAction.HOLD_CASH:
        if decision.symbol is None:
            raise ValueError("R22 trade decision requires symbol")
        if decision.symbol.value != forecast.symbol:
            raise ValueError("R22 decision symbol/forecast mismatch")


def _financial_outcome(action: PaperAction, realized_delta: Decimal) -> R22TapeOutcome:
    if action is PaperAction.BUY:
        return R22TapeOutcome.OPEN
    if action is PaperAction.REDUCE:
        return R22TapeOutcome.PARTIAL_REDUCTION
    if action is not PaperAction.EXIT:
        raise ValueError("unsupported R22 capital mutation action")
    if realized_delta > 0:
        return R22TapeOutcome.CLOSED_WIN
    if realized_delta < 0:
        return R22TapeOutcome.CLOSED_LOSS
    return R22TapeOutcome.CLOSED_BREAKEVEN


def _base_payload(
    *,
    previous_record_identity: str | None,
    event_kind: R22TapeEventKind,
    event_at_ms: int,
    forecast: ImmutableForecast,
    forecast_resolution: ForecastResolution | None,
    vault_id: PaperVaultId,
    sizing_assessment: PositionSizingAssessment,
    sizing_result: SizingMethodResult,
    decision: DecisionIntentRecord,
    fill: SimulatedFillRecord | None,
    mutation: PositionCashMutationRecord | None,
    before_snapshot: Epoch2VaultAccountingSnapshot,
    after_snapshot: Epoch2VaultAccountingSnapshot | None,
    outcome: R22TapeOutcome,
    source_evidence_identities: tuple[str, ...],
) -> dict[str, object]:
    after = before_snapshot if after_snapshot is None else after_snapshot
    is_buy = decision.action is PaperAction.BUY
    is_exit_side = decision.action in {PaperAction.REDUCE, PaperAction.EXIT}
    return {
        "schema_version": R22_TAPE_SCHEMA_VERSION,
        "engine_version": R22_TAPE_ENGINE_VERSION,
        "authority": R22_TAPE_AUTHORITY,
        "previous_record_identity": previous_record_identity,
        "event_kind": event_kind,
        "event_at_ms": event_at_ms,
        "forecast_identity": forecast.forecast_identity,
        "forecast_resolution_identity": (
            None if forecast_resolution is None else forecast_resolution.resolution_identity
        ),
        "vault_id": vault_id,
        "sizing_assessment_identity": sizing_assessment.assessment_identity,
        "sizing_result_identity": sizing_result.result_identity,
        "sizing_policy_identity": sizing_assessment.policy_identity,
        "allocator_candidate_identity": sizing_assessment.allocator_candidate_identity,
        "decision_identity": decision.record_identity,
        "fill_identity": None if fill is None else fill.record_identity,
        "mutation_identity": None if mutation is None else mutation.record_identity,
        "before_snapshot_identity": before_snapshot.snapshot_identity,
        "after_snapshot_identity": None if after_snapshot is None else after_snapshot.snapshot_identity,
        "action": decision.action,
        "symbol": None if decision.symbol is None else decision.symbol.value,
        "quantity": decision.quantity,
        "reference_price": None if fill is None else fill.reference_price,
        "simulated_fill_price": None if fill is None else fill.simulated_fill_price,
        "entry_price": None if fill is None or not is_buy else fill.simulated_fill_price,
        "exit_price": None if fill is None or not is_exit_side else fill.simulated_fill_price,
        "fee_usdt": Decimal(0) if fill is None else fill.costs.fee_usdt,
        "spread_usdt": Decimal(0) if fill is None else fill.costs.spread_usdt,
        "slippage_usdt": Decimal(0) if fill is None else fill.costs.slippage_usdt,
        "cash_before_usdt": before_snapshot.cash_usdt,
        "cash_after_usdt": after.cash_usdt,
        "positions_before": before_snapshot.positions,
        "positions_after": after.positions,
        "nav_before_usdt": before_snapshot.nav_usdt,
        "nav_after_usdt": after.nav_usdt,
        "nav_delta_usdt": after.nav_usdt - before_snapshot.nav_usdt,
        "exposure_before_usdt": before_snapshot.marked_exposure_usdt,
        "exposure_after_usdt": after.marked_exposure_usdt,
        "exposure_delta_usdt": (
            after.marked_exposure_usdt - before_snapshot.marked_exposure_usdt
        ),
        "realized_pnl_before_usdt": before_snapshot.realized_pnl_usdt,
        "realized_pnl_after_usdt": after.realized_pnl_usdt,
        "realized_pnl_delta_usdt": (
            after.realized_pnl_usdt - before_snapshot.realized_pnl_usdt
        ),
        "unrealized_pnl_before_usdt": before_snapshot.unrealized_pnl_usdt,
        "unrealized_pnl_after_usdt": after.unrealized_pnl_usdt,
        "unrealized_pnl_delta_usdt": (
            after.unrealized_pnl_usdt - before_snapshot.unrealized_pnl_usdt
        ),
        "turnover_notional_delta_usdt": (
            after.turnover_notional_usdt - before_snapshot.turnover_notional_usdt
        ),
        "risk_policy_version": decision.risk_policy_version,
        "execution_policy_version": (
            None if fill is None else fill.costs.execution_policy_version
        ),
        "outcome": outcome,
        "source_evidence_identities": source_evidence_identities,
        "immutable": True,
        "production_authority": False,
        "canonical_capital_write_authority": False,
        "real_capital": REAL_CAPITAL,
    }


def _source_identities(
    *,
    forecast: ImmutableForecast,
    sizing_assessment: PositionSizingAssessment,
    sizing_result: SizingMethodResult,
    decision: DecisionIntentRecord,
    fill: SimulatedFillRecord | None,
    mutation: PositionCashMutationRecord | None,
    before_snapshot: Epoch2VaultAccountingSnapshot,
    after_snapshot: Epoch2VaultAccountingSnapshot | None,
    forecast_resolution: ForecastResolution | None,
    additional: tuple[str, ...],
) -> tuple[str, ...]:
    values = {
        forecast.forecast_identity,
        sizing_assessment.assessment_identity,
        sizing_assessment.policy_identity,
        sizing_result.result_identity,
        decision.record_identity,
        before_snapshot.snapshot_identity,
        *forecast.source_evidence_identities,
        *additional,
    }
    for identity in additional:
        _require_sha256(identity, "R22 additional evidence identity")
    for value in (
        None if fill is None else fill.record_identity,
        None if mutation is None else mutation.record_identity,
        None if after_snapshot is None else after_snapshot.snapshot_identity,
        None if forecast_resolution is None else forecast_resolution.resolution_identity,
    ):
        if value is not None:
            values.add(value)
    return tuple(sorted(values))


def _record_payload(record: R22TransactionDecisionRecord) -> dict[str, object]:
    return {
        field: getattr(record, field)
        for field in (
            "schema_version",
            "engine_version",
            "authority",
            "previous_record_identity",
            "event_kind",
            "event_at_ms",
            "forecast_identity",
            "forecast_resolution_identity",
            "vault_id",
            "sizing_assessment_identity",
            "sizing_result_identity",
            "sizing_policy_identity",
            "allocator_candidate_identity",
            "decision_identity",
            "fill_identity",
            "mutation_identity",
            "before_snapshot_identity",
            "after_snapshot_identity",
            "action",
            "symbol",
            "quantity",
            "reference_price",
            "simulated_fill_price",
            "entry_price",
            "exit_price",
            "fee_usdt",
            "spread_usdt",
            "slippage_usdt",
            "cash_before_usdt",
            "cash_after_usdt",
            "positions_before",
            "positions_after",
            "nav_before_usdt",
            "nav_after_usdt",
            "nav_delta_usdt",
            "exposure_before_usdt",
            "exposure_after_usdt",
            "exposure_delta_usdt",
            "realized_pnl_before_usdt",
            "realized_pnl_after_usdt",
            "realized_pnl_delta_usdt",
            "unrealized_pnl_before_usdt",
            "unrealized_pnl_after_usdt",
            "unrealized_pnl_delta_usdt",
            "turnover_notional_delta_usdt",
            "risk_policy_version",
            "execution_policy_version",
            "outcome",
            "source_evidence_identities",
            "immutable",
            "production_authority",
            "canonical_capital_write_authority",
            "real_capital",
        )
    }


def _validate_mutation_fields(record: R22TransactionDecisionRecord) -> None:
    if record.action is PaperAction.HOLD_CASH:
        raise ValueError("R22 mutation record cannot be HOLD_CASH")
    required = (
        record.fill_identity,
        record.mutation_identity,
        record.after_snapshot_identity,
        record.symbol,
        record.quantity,
        record.reference_price,
        record.simulated_fill_price,
        record.execution_policy_version,
    )
    if any(value is None for value in required):
        raise ValueError("R22 capital mutation requires complete trade/fill fields")
    assert record.quantity is not None
    assert record.reference_price is not None
    assert record.simulated_fill_price is not None
    if record.quantity <= 0 or record.reference_price <= 0 or record.simulated_fill_price <= 0:
        raise ValueError("R22 trade quantity/prices must be positive")
    if record.action is PaperAction.BUY:
        if record.entry_price != record.simulated_fill_price or record.exit_price is not None:
            raise ValueError("R22 BUY must expose entry price only")
        if record.outcome is not R22TapeOutcome.OPEN:
            raise ValueError("R22 BUY outcome must remain OPEN")
    elif record.action is PaperAction.REDUCE:
        if record.exit_price != record.simulated_fill_price or record.entry_price is not None:
            raise ValueError("R22 REDUCE must expose exit price only")
        if record.outcome is not R22TapeOutcome.PARTIAL_REDUCTION:
            raise ValueError("R22 REDUCE outcome mismatch")
    elif record.action is PaperAction.EXIT:
        if record.exit_price != record.simulated_fill_price or record.entry_price is not None:
            raise ValueError("R22 EXIT must expose exit price only")
        if record.outcome not in {
            R22TapeOutcome.CLOSED_WIN,
            R22TapeOutcome.CLOSED_LOSS,
            R22TapeOutcome.CLOSED_BREAKEVEN,
        }:
            raise ValueError("R22 EXIT requires closed financial outcome")
    else:
        raise ValueError("unsupported R22 paper action")


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _require_non_negative(value: Decimal, label: str) -> None:
    _require_finite(value, label)
    if value < 0:
        raise ValueError(f"{label} must be non-negative")


def _require_finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
