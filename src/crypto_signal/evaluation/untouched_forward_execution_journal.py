from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Exchange
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
)

WC2_PAPER_EXECUTION_JOURNAL_SCHEMA_VERSION = "wc2-paper-execution-journal.v1/2"
WC2_PAPER_EXECUTION_JOURNAL_ENGINE_VERSION = "wc2-paper-execution-journal-v1/2"
WC2_PAPER_EXECUTION_JOURNAL_SUFFIX = ".wc2-paper-execution.sqlite3"

_META_TABLE = "wc2_paper_execution_meta"
_EVENT_TABLE = "wc2_paper_execution_events"
_ALLOWED_TABLES = {_META_TABLE, _EVENT_TABLE}


class WC2PaperExecutionDecisionStatus(StrEnum):
    HOLD_CASH = "HOLD_CASH"
    SIZING_REJECTED = "SIZING_REJECTED"
    PRETRADE_REJECTED = "PRETRADE_REJECTED"
    EXECUTED = "EXECUTED"


@dataclass(frozen=True, slots=True)
class WC2PaperExecutionDecision:
    record_identity: str
    event_identity: str
    execution_protocol_identity: str
    runtime_activation_identity: str
    execution_start_ms: int
    source_exchanges: tuple[str, str]
    source_freeze_identities: tuple[str, str]
    source_forecast_identities: tuple[str, str]
    source_cohort_forecast_identities: tuple[str, str]
    source_signal_as_of_ms: tuple[int, int]
    source_frozen_at_ms: tuple[int, int]
    source_forecast_issued_at_ms: tuple[int, int]
    source_cutoff_open_time_ms: int
    symbol: PaperSymbol
    epoch2_core_snapshot_identity: str
    decided_at_ms: int
    status: WC2PaperExecutionDecisionStatus
    action: PaperAction
    reason_code: str
    autonomy_policy_version: str
    execution_input_identity: str | None = None
    sizing_identity: str | None = None
    venue_rule_snapshot_identity: str | None = None
    pretrade_identity: str | None = None
    plan_identity: str | None = None
    fill_identity: str | None = None
    cost_evidence_identity: str | None = None
    quantity: Decimal | None = None
    reference_price: Decimal | None = None
    simulated_fill_price: Decimal | None = None
    fee_usdt: Decimal = Decimal(0)
    spread_usdt: Decimal = Decimal(0)
    slippage_usdt: Decimal = Decimal(0)
    execution_policy_version: str = PAPER_EXECUTION_POLICY_VERSION
    venue_reference: str | None = None
    historical_backfill_performed: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = WC2_PAPER_EXECUTION_JOURNAL_SCHEMA_VERSION
    engine_version: str = WC2_PAPER_EXECUTION_JOURNAL_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.record_identity, "WC2 execution record"),
            (self.event_identity, "WC2 execution event"),
            (self.execution_protocol_identity, "WC2 execution protocol"),
            (self.runtime_activation_identity, "WC2 execution runtime activation"),
            (self.epoch2_core_snapshot_identity, "WC2 Epoch2 CORE snapshot"),
        ):
            _require_sha256(value, label)
        if self.source_exchanges != (
            Exchange.BINANCE.value,
            Exchange.BYBIT.value,
        ):
            raise ValueError("WC2 execution source order must be Binance then Bybit")
        for identity_values, label in (
            (self.source_freeze_identities, "source freeze"),
            (self.source_forecast_identities, "source forecast"),
            (self.source_cohort_forecast_identities, "source cohort forecast"),
        ):
            if len(identity_values) != 2 or len(set(identity_values)) != 2:
                raise ValueError(f"WC2 execution requires two unique {label} identities")
            for identity_value in identity_values:
                _require_sha256(identity_value, f"WC2 execution {label}")
        for timestamp_values, label in (
            (self.source_signal_as_of_ms, "source signal as-of"),
            (self.source_frozen_at_ms, "source frozen-at"),
            (self.source_forecast_issued_at_ms, "source forecast issued-at"),
        ):
            if len(timestamp_values) != 2 or min(timestamp_values) < 0:
                raise ValueError(f"WC2 execution {label} values are invalid")
        if self.execution_start_ms < 0 or self.source_cutoff_open_time_ms < 0:
            raise ValueError("WC2 execution boundary/cutoff cannot be negative")
        if any(value < self.execution_start_ms for value in self.source_signal_as_of_ms):
            raise ValueError("WC2 execution source signal predates execution boundary")
        if any(value < self.execution_start_ms for value in self.source_frozen_at_ms):
            raise ValueError("WC2 execution source freeze predates execution boundary")
        if any(
            value < self.execution_start_ms
            for value in self.source_forecast_issued_at_ms
        ):
            raise ValueError("WC2 execution source forecast predates execution boundary")
        if self.decided_at_ms < max(
            *self.source_frozen_at_ms,
            *self.source_forecast_issued_at_ms,
            self.execution_start_ms,
        ):
            raise ValueError("WC2 execution decision predates immutable source evidence")
        if not isinstance(self.symbol, PaperSymbol):
            raise TypeError("WC2 execution symbol must be canonical paper symbol")
        if not isinstance(self.status, WC2PaperExecutionDecisionStatus):
            raise TypeError("WC2 execution status must be canonical")
        if not isinstance(self.action, PaperAction):
            raise TypeError("WC2 execution action must be canonical")
        if not self.reason_code.strip() or not self.autonomy_policy_version.strip():
            raise ValueError("WC2 execution reason/policy must be non-empty")
        if self.execution_policy_version != PAPER_EXECUTION_POLICY_VERSION:
            raise ValueError("WC2 execution policy version mismatch")
        for optional_trade_value, label in (
            (self.quantity, "quantity"),
            (self.reference_price, "reference price"),
            (self.simulated_fill_price, "simulated fill price"),
        ):
            if optional_trade_value is not None and (
                not isinstance(optional_trade_value, Decimal)
                or not optional_trade_value.is_finite()
                or optional_trade_value <= 0
            ):
                raise ValueError(
                    f"WC2 execution {label} must be finite positive when present"
                )
        for cost_value, label in (
            (self.fee_usdt, "fee"),
            (self.spread_usdt, "spread"),
            (self.slippage_usdt, "slippage"),
        ):
            if (
                not isinstance(cost_value, Decimal)
                or not cost_value.is_finite()
                or cost_value < 0
            ):
                raise ValueError(f"WC2 execution {label} must be finite non-negative")

        downstream = (
            self.execution_input_identity,
            self.sizing_identity,
            self.venue_rule_snapshot_identity,
            self.pretrade_identity,
            self.plan_identity,
            self.fill_identity,
            self.cost_evidence_identity,
        )
        for downstream_identity in downstream:
            if downstream_identity is not None:
                _require_sha256(
                    downstream_identity,
                    "WC2 downstream execution evidence",
                )

        if self.status is WC2PaperExecutionDecisionStatus.HOLD_CASH:
            if self.action is not PaperAction.HOLD_CASH:
                raise ValueError("WC2 HOLD_CASH decision must use HOLD_CASH action")
            if any(value is not None for value in downstream):
                raise ValueError("WC2 HOLD_CASH cannot fabricate execution evidence")
            if any(
                value is not None
                for value in (
                    self.quantity,
                    self.reference_price,
                    self.simulated_fill_price,
                )
            ):
                raise ValueError("WC2 HOLD_CASH cannot carry execution economics")
            if any(
                value != Decimal(0)
                for value in (self.fee_usdt, self.spread_usdt, self.slippage_usdt)
            ) or self.venue_reference is not None:
                raise ValueError("WC2 HOLD_CASH cannot carry execution costs")
        elif self.status is WC2PaperExecutionDecisionStatus.SIZING_REJECTED:
            if self.action not in {PaperAction.BUY, PaperAction.EXIT}:
                raise ValueError("WC2 sizing rejection requires trade candidate")
            if (
                self.execution_input_identity is None
                or self.sizing_identity is None
                or self.venue_rule_snapshot_identity is None
            ):
                raise ValueError("WC2 sizing rejection lost frozen upstream evidence")
            if any(
                value is not None
                for value in (
                    self.pretrade_identity,
                    self.plan_identity,
                    self.fill_identity,
                    self.cost_evidence_identity,
                    self.venue_reference,
                )
            ):
                raise ValueError("WC2 sizing rejection cannot carry fill evidence")
            if any(
                value is not None
                for value in (
                    self.quantity,
                    self.reference_price,
                    self.simulated_fill_price,
                )
            ):
                raise ValueError("WC2 sizing rejection cannot carry execution economics")
        elif self.status is WC2PaperExecutionDecisionStatus.PRETRADE_REJECTED:
            if self.action not in {PaperAction.BUY, PaperAction.EXIT}:
                raise ValueError("WC2 pretrade rejection requires trade candidate")
            if any(
                value is None
                for value in (
                    self.execution_input_identity,
                    self.sizing_identity,
                    self.venue_rule_snapshot_identity,
                    self.pretrade_identity,
                )
            ):
                raise ValueError("WC2 pretrade rejection lost exact decision evidence")
            if any(
                value is not None
                for value in (
                    self.plan_identity,
                    self.fill_identity,
                    self.cost_evidence_identity,
                    self.venue_reference,
                )
            ):
                raise ValueError("WC2 pretrade rejection cannot carry fill evidence")
            if any(
                value is not None
                for value in (
                    self.quantity,
                    self.reference_price,
                    self.simulated_fill_price,
                )
            ):
                raise ValueError("WC2 pretrade rejection cannot carry execution economics")
        else:
            if self.status is not WC2PaperExecutionDecisionStatus.EXECUTED:
                raise ValueError("unsupported WC2 execution status")
            if self.action not in {PaperAction.BUY, PaperAction.EXIT}:
                raise ValueError("WC2 executed decision requires BUY or EXIT")
            if any(value is None for value in downstream):
                raise ValueError("WC2 executed decision requires complete evidence lineage")
            if not self.venue_reference:
                raise ValueError("WC2 executed decision requires venue reference")
            if (
                self.quantity is None
                or self.reference_price is None
                or self.simulated_fill_price is None
            ):
                raise ValueError(
                    "WC2 executed decision requires complete execution economics"
                )
            price_impact = (
                abs(self.simulated_fill_price - self.reference_price)
                * self.quantity
            )
            if price_impact != self.spread_usdt + self.slippage_usdt:
                raise ValueError(
                    "WC2 execution price impact must equal spread plus slippage"
                )
            if (
                self.action is PaperAction.BUY
                and self.simulated_fill_price < self.reference_price
            ):
                raise ValueError("WC2 BUY cannot claim beneficial simulated execution")
            if (
                self.action is PaperAction.EXIT
                and self.simulated_fill_price > self.reference_price
            ):
                raise ValueError("WC2 EXIT cannot claim beneficial simulated execution")
            assert self.fill_identity is not None
            expected_cost = compute_wc2_cost_evidence_identity(
                fill_identity=self.fill_identity,
                fee_usdt=self.fee_usdt,
                spread_usdt=self.spread_usdt,
                slippage_usdt=self.slippage_usdt,
                execution_policy_version=self.execution_policy_version,
                venue_reference=self.venue_reference,
            )
            if self.cost_evidence_identity != expected_cost:
                raise ValueError("WC2 explicit cost evidence identity mismatch")

        expected_event = compute_wc2_paper_execution_event_identity(
            execution_protocol_identity=self.execution_protocol_identity,
            symbol=self.symbol,
            source_cutoff_open_time_ms=self.source_cutoff_open_time_ms,
            source_exchanges=self.source_exchanges,
            source_freeze_identities=self.source_freeze_identities,
        )
        if self.event_identity != expected_event:
            raise ValueError("WC2 paper execution event identity mismatch")

        if self.historical_backfill_performed:
            raise ValueError("WC2 paper execution cannot backfill history")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 paper execution cannot grant real authority")
        if self.schema_version != WC2_PAPER_EXECUTION_JOURNAL_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 paper execution journal schema")
        if self.engine_version != WC2_PAPER_EXECUTION_JOURNAL_ENGINE_VERSION:
            raise ValueError("unsupported WC2 paper execution journal engine")
        if self.record_identity != canonical_sha256(_record_payload(self)):
            raise ValueError("WC2 paper execution record identity mismatch")

    @property
    def trade_decision(self) -> bool:
        return self.status is WC2PaperExecutionDecisionStatus.EXECUTED

    @property
    def simulated_execution(self) -> bool:
        return self.fill_identity is not None

    @property
    def explicit_cost_evidence(self) -> bool:
        return self.cost_evidence_identity is not None


@dataclass(frozen=True, slots=True)
class WC2PaperExecutionJournalStatus:
    decision_n: int
    hold_cash_n: int
    rejected_n: int
    trade_decision_n: int
    simulated_execution_n: int
    explicit_cost_evidence_trade_n: int
    quick_check_ok: bool
    read_only_verified: bool
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        counts = (
            self.decision_n,
            self.hold_cash_n,
            self.rejected_n,
            self.trade_decision_n,
            self.simulated_execution_n,
            self.explicit_cost_evidence_trade_n,
        )
        if min(counts) < 0:
            raise ValueError("WC2 execution journal counts cannot be negative")
        if self.decision_n != (
            self.hold_cash_n + self.rejected_n + self.trade_decision_n
        ):
            raise ValueError("WC2 execution terminal decision counts do not reconcile")
        if self.simulated_execution_n != self.trade_decision_n:
            raise ValueError("every WC2 trade decision must have simulated execution")
        if self.explicit_cost_evidence_trade_n != self.trade_decision_n:
            raise ValueError("every WC2 trade decision must have explicit costs")
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("WC2 execution journal must be read-only verified")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 execution journal cannot grant authority")


def compute_wc2_paper_execution_event_identity(
    *,
    execution_protocol_identity: str,
    symbol: PaperSymbol,
    source_cutoff_open_time_ms: int,
    source_exchanges: tuple[str, str],
    source_freeze_identities: tuple[str, str],
) -> str:
    _require_sha256(execution_protocol_identity, "WC2 execution protocol")
    if source_cutoff_open_time_ms < 0:
        raise ValueError("WC2 execution source cutoff cannot be negative")
    if source_exchanges != (
        Exchange.BINANCE.value,
        Exchange.BYBIT.value,
    ):
        raise ValueError("WC2 execution source order must be Binance then Bybit")
    if len(source_freeze_identities) != 2 or len(set(source_freeze_identities)) != 2:
        raise ValueError("WC2 execution event requires two source freezes")
    for identity in source_freeze_identities:
        _require_sha256(identity, "WC2 execution source freeze")
    return canonical_sha256(
        {
            "execution_protocol_identity": execution_protocol_identity,
            "source_cutoff_open_time_ms": source_cutoff_open_time_ms,
            "source_exchanges": source_exchanges,
            "source_freeze_identities": source_freeze_identities,
            "symbol": symbol,
        }
    )


def compute_wc2_cost_evidence_identity(
    *,
    fill_identity: str,
    fee_usdt: Decimal,
    spread_usdt: Decimal,
    slippage_usdt: Decimal,
    execution_policy_version: str,
    venue_reference: str,
) -> str:
    _require_sha256(fill_identity, "WC2 execution fill")
    if not execution_policy_version.strip() or not venue_reference.strip():
        raise ValueError("WC2 cost evidence requires policy and venue")
    return canonical_sha256(
        {
            "execution_policy_version": execution_policy_version,
            "fee_usdt": fee_usdt,
            "fill_identity": fill_identity,
            "slippage_usdt": slippage_usdt,
            "spread_usdt": spread_usdt,
            "venue_reference": venue_reference,
        }
    )


def build_wc2_paper_execution_decision(
    *,
    event_identity: str,
    execution_protocol_identity: str,
    runtime_activation_identity: str,
    execution_start_ms: int,
    source_exchanges: tuple[str, str],
    source_freeze_identities: tuple[str, str],
    source_forecast_identities: tuple[str, str],
    source_cohort_forecast_identities: tuple[str, str],
    source_signal_as_of_ms: tuple[int, int],
    source_frozen_at_ms: tuple[int, int],
    source_forecast_issued_at_ms: tuple[int, int],
    source_cutoff_open_time_ms: int,
    symbol: PaperSymbol,
    epoch2_core_snapshot_identity: str,
    decided_at_ms: int,
    status: WC2PaperExecutionDecisionStatus,
    action: PaperAction,
    reason_code: str,
    autonomy_policy_version: str,
    execution_input_identity: str | None = None,
    sizing_identity: str | None = None,
    venue_rule_snapshot_identity: str | None = None,
    pretrade_identity: str | None = None,
    plan_identity: str | None = None,
    fill_identity: str | None = None,
    cost_evidence_identity: str | None = None,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
    simulated_fill_price: Decimal | None = None,
    fee_usdt: Decimal = Decimal(0),
    spread_usdt: Decimal = Decimal(0),
    slippage_usdt: Decimal = Decimal(0),
    execution_policy_version: str = PAPER_EXECUTION_POLICY_VERSION,
    venue_reference: str | None = None,
    historical_backfill_performed: bool = False,
) -> WC2PaperExecutionDecision:
    values: dict[str, object] = {
        "event_identity": event_identity,
        "execution_protocol_identity": execution_protocol_identity,
        "runtime_activation_identity": runtime_activation_identity,
        "execution_start_ms": execution_start_ms,
        "source_exchanges": source_exchanges,
        "source_freeze_identities": source_freeze_identities,
        "source_forecast_identities": source_forecast_identities,
        "source_cohort_forecast_identities": source_cohort_forecast_identities,
        "source_signal_as_of_ms": source_signal_as_of_ms,
        "source_frozen_at_ms": source_frozen_at_ms,
        "source_forecast_issued_at_ms": source_forecast_issued_at_ms,
        "source_cutoff_open_time_ms": source_cutoff_open_time_ms,
        "symbol": symbol,
        "epoch2_core_snapshot_identity": epoch2_core_snapshot_identity,
        "decided_at_ms": decided_at_ms,
        "status": status,
        "action": action,
        "reason_code": reason_code,
        "autonomy_policy_version": autonomy_policy_version,
        "execution_input_identity": execution_input_identity,
        "sizing_identity": sizing_identity,
        "venue_rule_snapshot_identity": venue_rule_snapshot_identity,
        "pretrade_identity": pretrade_identity,
        "plan_identity": plan_identity,
        "fill_identity": fill_identity,
        "cost_evidence_identity": cost_evidence_identity,
        "quantity": quantity,
        "reference_price": reference_price,
        "simulated_fill_price": simulated_fill_price,
        "fee_usdt": fee_usdt,
        "spread_usdt": spread_usdt,
        "slippage_usdt": slippage_usdt,
        "execution_policy_version": execution_policy_version,
        "venue_reference": venue_reference,
        "historical_backfill_performed": historical_backfill_performed,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC2_PAPER_EXECUTION_JOURNAL_SCHEMA_VERSION,
        "engine_version": WC2_PAPER_EXECUTION_JOURNAL_ENGINE_VERSION,
    }
    return WC2PaperExecutionDecision(
        record_identity=canonical_sha256(values),
        event_identity=event_identity,
        execution_protocol_identity=execution_protocol_identity,
        runtime_activation_identity=runtime_activation_identity,
        execution_start_ms=execution_start_ms,
        source_exchanges=source_exchanges,
        source_freeze_identities=source_freeze_identities,
        source_forecast_identities=source_forecast_identities,
        source_cohort_forecast_identities=source_cohort_forecast_identities,
        source_signal_as_of_ms=source_signal_as_of_ms,
        source_frozen_at_ms=source_frozen_at_ms,
        source_forecast_issued_at_ms=source_forecast_issued_at_ms,
        source_cutoff_open_time_ms=source_cutoff_open_time_ms,
        symbol=symbol,
        epoch2_core_snapshot_identity=epoch2_core_snapshot_identity,
        decided_at_ms=decided_at_ms,
        status=status,
        action=action,
        reason_code=reason_code,
        autonomy_policy_version=autonomy_policy_version,
        execution_input_identity=execution_input_identity,
        sizing_identity=sizing_identity,
        venue_rule_snapshot_identity=venue_rule_snapshot_identity,
        pretrade_identity=pretrade_identity,
        plan_identity=plan_identity,
        fill_identity=fill_identity,
        cost_evidence_identity=cost_evidence_identity,
        quantity=quantity,
        reference_price=reference_price,
        simulated_fill_price=simulated_fill_price,
        fee_usdt=fee_usdt,
        spread_usdt=spread_usdt,
        slippage_usdt=slippage_usdt,
        execution_policy_version=execution_policy_version,
        venue_reference=venue_reference,
        historical_backfill_performed=historical_backfill_performed,
    )


class WC2PaperExecutionJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(WC2_PAPER_EXECUTION_JOURNAL_SUFFIX):
            raise ValueError(
                "WC2 paper execution journal path must end with "
                f"{WC2_PAPER_EXECUTION_JOURNAL_SUFFIX}"
            )

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            unexpected = existing - _ALLOWED_TABLES
            if unexpected:
                raise ValueError("WC2 execution journal refuses unrelated tables")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_identity TEXT UNIQUE NOT NULL,
                    event_identity TEXT UNIQUE NOT NULL,
                    execution_protocol_identity TEXT NOT NULL,
                    source_cutoff_open_time_ms INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    decided_at_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            expected = {
                "engine_version": WC2_PAPER_EXECUTION_JOURNAL_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": WC2_PAPER_EXECUTION_JOURNAL_SCHEMA_VERSION,
                "semantic": "forward_terminal_paper_decisions_with_explicit_costs",
            }
            for key, value in expected.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key=?",
                    (key,),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE}(key,value) VALUES (?,?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError("WC2 execution journal metadata mismatch")
            for table in (_META_TABLE, _EVENT_TABLE):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, 'append-only WC2 execution journal');
                        END"""
                    )

    def append(self, record: WC2PaperExecutionDecision) -> bool:
        self.initialize()
        payload = canonical_json(_record_payload(record))
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = db.execute(
                f"""SELECT record_identity, payload_json
                FROM {_EVENT_TABLE}
                WHERE event_identity=? OR record_identity=?""",
                (record.event_identity, record.record_identity),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.record_identity
                    and str(existing[1]) == payload
                ):
                    return False
                raise ValueError("WC2 execution event already has terminal decision")
            db.execute(
                f"""INSERT INTO {_EVENT_TABLE}(
                    record_identity,
                    event_identity,
                    execution_protocol_identity,
                    source_cutoff_open_time_ms,
                    symbol,
                    decided_at_ms,
                    status,
                    action,
                    payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    record.record_identity,
                    record.event_identity,
                    record.execution_protocol_identity,
                    record.source_cutoff_open_time_ms,
                    record.symbol.value,
                    record.decided_at_ms,
                    record.status.value,
                    record.action.value,
                    payload,
                ),
            )
        return True

    def contains_event(self, event_identity: str) -> bool:
        _require_sha256(event_identity, "WC2 execution event")
        if not self.path.is_file():
            return False
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                f"SELECT 1 FROM {_EVENT_TABLE} WHERE event_identity=?",
                (event_identity,),
            ).fetchone()
        return row is not None

    def read_records(self) -> tuple[WC2PaperExecutionDecision, ...]:
        """Read the immutable terminal execution evidence in event order."""
        if not self.path.is_file():
            return ()
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                f"""SELECT payload_json FROM {_EVENT_TABLE}
                ORDER BY decided_at_ms ASC, event_identity ASC"""
            ).fetchall()
        return tuple(_record_from_json(str(row[0])) for row in rows)

    def verify_read_only(self) -> WC2PaperExecutionJournalStatus:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("WC2 execution journal quick_check failed")
            rows = db.execute(
                f"SELECT status, payload_json FROM {_EVENT_TABLE} ORDER BY sequence_id"
            ).fetchall()

        records = tuple(_record_from_json(str(row[1])) for row in rows)
        hold = sum(
            item.status is WC2PaperExecutionDecisionStatus.HOLD_CASH
            for item in records
        )
        rejected = sum(
            item.status
            in {
                WC2PaperExecutionDecisionStatus.SIZING_REJECTED,
                WC2PaperExecutionDecisionStatus.PRETRADE_REJECTED,
            }
            for item in records
        )
        trades = sum(item.trade_decision for item in records)
        executions = sum(item.simulated_execution for item in records)
        costs = sum(item.explicit_cost_evidence for item in records)
        return WC2PaperExecutionJournalStatus(
            decision_n=len(records),
            hold_cash_n=hold,
            rejected_n=rejected,
            trade_decision_n=trades,
            simulated_execution_n=executions,
            explicit_cost_evidence_trade_n=costs,
            quick_check_ok=True,
            read_only_verified=True,
        )


def _record_payload(record: WC2PaperExecutionDecision) -> dict[str, object]:
    return {
        field: getattr(record, field)
        for field in (
            "event_identity",
            "execution_protocol_identity",
            "runtime_activation_identity",
            "execution_start_ms",
            "source_exchanges",
            "source_freeze_identities",
            "source_forecast_identities",
            "source_cohort_forecast_identities",
            "source_signal_as_of_ms",
            "source_frozen_at_ms",
            "source_forecast_issued_at_ms",
            "source_cutoff_open_time_ms",
            "symbol",
            "epoch2_core_snapshot_identity",
            "decided_at_ms",
            "status",
            "action",
            "reason_code",
            "autonomy_policy_version",
            "execution_input_identity",
            "sizing_identity",
            "venue_rule_snapshot_identity",
            "pretrade_identity",
            "plan_identity",
            "fill_identity",
            "cost_evidence_identity",
            "quantity",
            "reference_price",
            "simulated_fill_price",
            "fee_usdt",
            "spread_usdt",
            "slippage_usdt",
            "execution_policy_version",
            "venue_reference",
            "historical_backfill_performed",
            "production_authority",
            "real_capital",
            "schema_version",
            "engine_version",
        )
    }


def _record_from_json(payload_json: str) -> WC2PaperExecutionDecision:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("WC2 execution journal payload must be object")
    record = WC2PaperExecutionDecision(
        record_identity=canonical_sha256(raw),
        event_identity=_text(raw, "event_identity"),
        execution_protocol_identity=_text(raw, "execution_protocol_identity"),
        runtime_activation_identity=_text(raw, "runtime_activation_identity"),
        execution_start_ms=_integer(raw, "execution_start_ms"),
        source_exchanges=_two_text(raw, "source_exchanges"),
        source_freeze_identities=_two_text(raw, "source_freeze_identities"),
        source_forecast_identities=_two_text(raw, "source_forecast_identities"),
        source_cohort_forecast_identities=_two_text(
            raw, "source_cohort_forecast_identities"
        ),
        source_signal_as_of_ms=_two_int(raw, "source_signal_as_of_ms"),
        source_frozen_at_ms=_two_int(raw, "source_frozen_at_ms"),
        source_forecast_issued_at_ms=_two_int(raw, "source_forecast_issued_at_ms"),
        source_cutoff_open_time_ms=_integer(raw, "source_cutoff_open_time_ms"),
        symbol=PaperSymbol(_text(raw, "symbol")),
        epoch2_core_snapshot_identity=_text(raw, "epoch2_core_snapshot_identity"),
        decided_at_ms=_integer(raw, "decided_at_ms"),
        status=WC2PaperExecutionDecisionStatus(_text(raw, "status")),
        action=PaperAction(_text(raw, "action")),
        reason_code=_text(raw, "reason_code"),
        autonomy_policy_version=_text(raw, "autonomy_policy_version"),
        execution_input_identity=_optional_text(raw.get("execution_input_identity")),
        sizing_identity=_optional_text(raw.get("sizing_identity")),
        venue_rule_snapshot_identity=_optional_text(
            raw.get("venue_rule_snapshot_identity")
        ),
        pretrade_identity=_optional_text(raw.get("pretrade_identity")),
        plan_identity=_optional_text(raw.get("plan_identity")),
        fill_identity=_optional_text(raw.get("fill_identity")),
        cost_evidence_identity=_optional_text(raw.get("cost_evidence_identity")),
        quantity=_optional_decimal(raw.get("quantity")),
        reference_price=_optional_decimal(raw.get("reference_price")),
        simulated_fill_price=_optional_decimal(raw.get("simulated_fill_price")),
        fee_usdt=_decimal(raw, "fee_usdt"),
        spread_usdt=_decimal(raw, "spread_usdt"),
        slippage_usdt=_decimal(raw, "slippage_usdt"),
        execution_policy_version=_text(raw, "execution_policy_version"),
        venue_reference=_optional_text(raw.get("venue_reference")),
        historical_backfill_performed=bool(raw.get("historical_backfill_performed")),
        production_authority=bool(raw.get("production_authority")),
        real_capital=_integer(raw, "real_capital"),
        schema_version=_text(raw, "schema_version"),
        engine_version=_text(raw, "engine_version"),
    )
    if canonical_json(raw) != payload_json:
        raise ValueError("WC2 execution journal payload is not canonical")
    return record


def _two_text(raw: dict[str, object], key: str) -> tuple[str, str]:
    value = raw.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise TypeError(f"{key} must be a two-item list")
    return (_text_item(value[0]), _text_item(value[1]))


def _two_int(raw: dict[str, object], key: str) -> tuple[int, int]:
    value = raw.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise TypeError(f"{key} must be a two-item list")
    return (_int_item(value[0]), _int_item(value[1]))


def _text(raw: dict[str, object], key: str) -> str:
    return _text_item(raw.get(key))


def _text_item(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("WC2 execution journal text must be non-empty")
    return value


def _integer(raw: dict[str, object], key: str) -> int:
    return _int_item(raw.get(key))


def _int_item(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("WC2 execution journal integer value required")
    return value


def _decimal(raw: dict[str, object], key: str) -> Decimal:
    value = raw.get(key)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    raise TypeError(f"{key} must be decimal-compatible")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text_item(value)


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    raise TypeError("WC2 execution journal optional decimal value required")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
