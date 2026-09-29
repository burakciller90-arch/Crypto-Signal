"""FP4-E canonical immutable execution receipt.

Binds authoritative venue/pretrade truth to exactly one FP4-A depth or FP4-B
passive-limit outcome plus FP4-D exact fee evidence. It does not mutate R21/R22
and does not fold FP4-C funding into fill execution cost. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.microstructure import OrderBookSnapshot, PublicTradeObservation
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.execution_depth_v2 import DepthExecutionOutcome
from crypto_signal.paper.execution_limit_v2 import PassiveLimitExecutionOutcome
from crypto_signal.paper.instrument_fees_v2 import (
    InstrumentFeeProjection,
    InstrumentFeeProjectionStatus,
    InstrumentFeeRole,
    InstrumentFeeScheduleSnapshot,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.pretrade import PaperPretradeStatus
from crypto_signal.paper.venue_rules import PaperVenueBoundPretrade

FP4_EXECUTION_RECEIPT_SCHEMA_VERSION = "paper_execution_receipt.v2"


class ExecutionReceiptRejectedError(ValueError):
    """Raised when FP4 execution evidence cannot reconcile exactly."""


class ExecutionReceiptMode(StrEnum):
    DEPTH = "depth"
    PASSIVE_LIMIT = "passive_limit"


class ExecutionReceiptStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NOT_FILLED = "not_filled"
    FILL_NOT_PROVEN = "fill_not_proven"


ExecutionOutcomeV2 = DepthExecutionOutcome | PassiveLimitExecutionOutcome


@dataclass(frozen=True, slots=True)
class ExecutionReceiptV2:
    receipt_identity: str
    schema_version: str
    mode: ExecutionReceiptMode
    status: ExecutionReceiptStatus
    action: PaperAction
    symbol: PaperSymbol
    venue_rule_snapshot_identity: str
    pretrade_identity: str
    plan_identity: str
    execution_snapshot_identity: str
    execution_outcome_identity: str
    market_evidence_identities: tuple[str, ...]
    fee_projection_identity: str | None
    fee_schedule_snapshot_identity: str | None
    fee_role: InstrumentFeeRole | None
    requested_quantity: Decimal
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    reference_price: Decimal
    average_fill_price: Decimal | None
    fill_notional_usdt: Decimal
    fee_usdt: Decimal
    adverse_price_impact_usdt: Decimal
    immediate_execution_cost_usdt: Decimal
    funding_accounted_separately: bool = True
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.schema_version != FP4_EXECUTION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported FP4 execution receipt schema")
        for label, value in (
            ("receipt_identity", self.receipt_identity),
            ("venue_rule_snapshot_identity", self.venue_rule_snapshot_identity),
            ("pretrade_identity", self.pretrade_identity),
            ("plan_identity", self.plan_identity),
            ("execution_snapshot_identity", self.execution_snapshot_identity),
            ("execution_outcome_identity", self.execution_outcome_identity),
        ):
            _require_sha256(value, label)
        for identity in self.market_evidence_identities:
            _require_sha256(identity, "market_evidence_identity")
        if len(set(self.market_evidence_identities)) != len(
            self.market_evidence_identities
        ):
            raise ValueError("market evidence identities must be unique")
        _require_positive_decimal(self.requested_quantity, "requested_quantity")
        _require_non_negative_decimal(self.filled_quantity, "filled_quantity")
        _require_non_negative_decimal(self.unfilled_quantity, "unfilled_quantity")
        _require_positive_decimal(self.reference_price, "reference_price")
        _require_non_negative_decimal(self.fill_notional_usdt, "fill_notional_usdt")
        _require_non_negative_decimal(self.fee_usdt, "fee_usdt")
        _require_non_negative_decimal(
            self.adverse_price_impact_usdt,
            "adverse_price_impact_usdt",
        )
        _require_non_negative_decimal(
            self.immediate_execution_cost_usdt,
            "immediate_execution_cost_usdt",
        )
        if self.filled_quantity + self.unfilled_quantity != self.requested_quantity:
            raise ValueError("receipt filled + unfilled must equal requested quantity")
        if not self.funding_accounted_separately:
            raise ValueError("FP4-C funding must remain separate from fill receipt")
        if self.immediate_execution_cost_usdt != (
            self.adverse_price_impact_usdt + self.fee_usdt
        ):
            raise ValueError("immediate execution cost must equal impact plus fee")

        filled = self.status in {
            ExecutionReceiptStatus.FULL,
            ExecutionReceiptStatus.PARTIAL,
        }
        if filled:
            if self.filled_quantity <= Decimal(0):
                raise ValueError("filled receipt requires positive filled quantity")
            if self.average_fill_price is None:
                raise ValueError("filled receipt requires average fill price")
            _require_positive_decimal(self.average_fill_price, "average_fill_price")
            if self.fill_notional_usdt != (
                self.filled_quantity * self.average_fill_price
            ):
                raise ValueError("receipt notional must reconcile to average fill price")
            if (
                self.fee_projection_identity is None
                or self.fee_schedule_snapshot_identity is None
                or self.fee_role is None
            ):
                raise ValueError("filled receipt requires exact fee evidence")
            _require_sha256(
                self.fee_projection_identity,
                "fee_projection_identity",
            )
            _require_sha256(
                self.fee_schedule_snapshot_identity,
                "fee_schedule_snapshot_identity",
            )
        else:
            if self.filled_quantity != Decimal(0):
                raise ValueError("non-filled receipt cannot contain filled quantity")
            if self.average_fill_price is not None:
                raise ValueError("non-filled receipt cannot expose fill price")
            if self.fill_notional_usdt != Decimal(0):
                raise ValueError("non-filled receipt must have zero notional")
            if self.fee_usdt != Decimal(0):
                raise ValueError("non-filled receipt must have zero fee")
            if self.adverse_price_impact_usdt != Decimal(0):
                raise ValueError("non-filled receipt must have zero price impact")
            if self.immediate_execution_cost_usdt != Decimal(0):
                raise ValueError("non-filled receipt must have zero immediate cost")
            if any(
                value is not None
                for value in (
                    self.fee_projection_identity,
                    self.fee_schedule_snapshot_identity,
                    self.fee_role,
                )
            ):
                raise ValueError("non-filled receipt cannot invent fee evidence")

        expected = compute_execution_receipt_identity(
            schema_version=self.schema_version,
            mode=self.mode,
            status=self.status,
            action=self.action,
            symbol=self.symbol,
            venue_rule_snapshot_identity=self.venue_rule_snapshot_identity,
            pretrade_identity=self.pretrade_identity,
            plan_identity=self.plan_identity,
            execution_snapshot_identity=self.execution_snapshot_identity,
            execution_outcome_identity=self.execution_outcome_identity,
            market_evidence_identities=self.market_evidence_identities,
            fee_projection_identity=self.fee_projection_identity,
            fee_schedule_snapshot_identity=self.fee_schedule_snapshot_identity,
            fee_role=self.fee_role,
            requested_quantity=self.requested_quantity,
            filled_quantity=self.filled_quantity,
            unfilled_quantity=self.unfilled_quantity,
            reference_price=self.reference_price,
            average_fill_price=self.average_fill_price,
            fill_notional_usdt=self.fill_notional_usdt,
            fee_usdt=self.fee_usdt,
            adverse_price_impact_usdt=self.adverse_price_impact_usdt,
            immediate_execution_cost_usdt=self.immediate_execution_cost_usdt,
            funding_accounted_separately=self.funding_accounted_separately,
        )
        if self.receipt_identity != expected:
            raise ValueError("execution receipt identity mismatch")


def build_execution_receipt_v2(
    *,
    bound_pretrade: PaperVenueBoundPretrade,
    outcome: ExecutionOutcomeV2,
    fee_projection: InstrumentFeeProjection | None,
    fee_snapshot: InstrumentFeeScheduleSnapshot | None,
    orderbook: OrderBookSnapshot,
    public_trades: tuple[PublicTradeObservation, ...] = (),
) -> ExecutionReceiptV2:
    pretrade = bound_pretrade.pretrade
    if pretrade.status is not PaperPretradeStatus.PLANNED:
        raise ExecutionReceiptRejectedError(
            "execution receipt requires PLANNED authoritative pretrade"
        )
    if pretrade.plan is None or pretrade.planned_quantity is None:
        raise ExecutionReceiptRejectedError("planned pretrade lost exact plan lineage")

    mode, status, expected_fee_role, market_evidence = _outcome_contract(
        outcome=outcome,
        orderbook=orderbook,
        public_trades=public_trades,
        symbol=pretrade.symbol,
    )

    if outcome.action is not pretrade.action:
        raise ExecutionReceiptRejectedError("execution outcome action mismatch")
    if outcome.requested_quantity != pretrade.planned_quantity:
        raise ExecutionReceiptRejectedError("execution requested quantity mismatch")

    filled_quantity = outcome.filled_quantity
    unfilled_quantity = outcome.unfilled_quantity
    average_fill_price = outcome.average_fill_price
    fill_notional = outcome.fill_notional
    filled = status in {
        ExecutionReceiptStatus.FULL,
        ExecutionReceiptStatus.PARTIAL,
    }

    fee_projection_identity: str | None = None
    fee_schedule_snapshot_identity: str | None = None
    fee_role: InstrumentFeeRole | None = None
    fee_usdt = Decimal(0)

    if filled:
        if fee_projection is None or fee_snapshot is None:
            raise ExecutionReceiptRejectedError(
                "filled execution requires exact fee projection and snapshot"
            )
        if fee_projection.status is not InstrumentFeeProjectionStatus.PROVEN:
            raise ExecutionReceiptRejectedError(
                "filled execution requires PROVEN fee projection"
            )
        if fee_projection.symbol is not pretrade.symbol:
            raise ExecutionReceiptRejectedError("fee projection symbol mismatch")
        if fee_snapshot.symbol is not pretrade.symbol:
            raise ExecutionReceiptRejectedError("fee snapshot symbol mismatch")
        if fee_projection.snapshot_identity != fee_snapshot.snapshot_identity:
            raise ExecutionReceiptRejectedError(
                "fee projection snapshot identity mismatch"
            )
        if fee_snapshot.ingested_at_ms > _execution_evidence_cutoff_ms(outcome):
            raise ExecutionReceiptRejectedError(
                "future fee schedule cannot enter historical execution receipt"
            )
        if fee_projection.action is not pretrade.action:
            raise ExecutionReceiptRejectedError("fee projection action mismatch")
        if fee_projection.role is not expected_fee_role:
            raise ExecutionReceiptRejectedError("fee role does not match execution mode")
        if fee_projection.fill_notional_usdt != fill_notional:
            raise ExecutionReceiptRejectedError("fee projection notional mismatch")
        if (
            fee_projection.snapshot_identity is None
            or fee_projection.fee_usdt is None
        ):
            raise ExecutionReceiptRejectedError("PROVEN fee projection lost evidence")
        fee_projection_identity = fee_projection.projection_identity
        fee_schedule_snapshot_identity = fee_projection.snapshot_identity
        fee_role = fee_projection.role
        fee_usdt = fee_projection.fee_usdt
    elif fee_projection is not None or fee_snapshot is not None:
        raise ExecutionReceiptRejectedError(
            "non-filled execution must not carry fee projection or snapshot"
        )

    adverse_impact = _adverse_price_impact(
        action=pretrade.action,
        reference_price=pretrade.reference_price,
        average_fill_price=average_fill_price,
        filled_quantity=filled_quantity,
    )
    immediate_cost = adverse_impact + fee_usdt

    receipt_identity = compute_execution_receipt_identity(
        schema_version=FP4_EXECUTION_RECEIPT_SCHEMA_VERSION,
        mode=mode,
        status=status,
        action=pretrade.action,
        symbol=pretrade.symbol,
        venue_rule_snapshot_identity=bound_pretrade.venue_rule_snapshot_identity,
        pretrade_identity=pretrade.pretrade_identity,
        plan_identity=pretrade.plan.plan_identity,
        execution_snapshot_identity=bound_pretrade.execution_snapshot.snapshot_identity,
        execution_outcome_identity=outcome.outcome_identity,
        market_evidence_identities=market_evidence,
        fee_projection_identity=fee_projection_identity,
        fee_schedule_snapshot_identity=fee_schedule_snapshot_identity,
        fee_role=fee_role,
        requested_quantity=outcome.requested_quantity,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        reference_price=pretrade.reference_price,
        average_fill_price=average_fill_price,
        fill_notional_usdt=fill_notional,
        fee_usdt=fee_usdt,
        adverse_price_impact_usdt=adverse_impact,
        immediate_execution_cost_usdt=immediate_cost,
        funding_accounted_separately=True,
    )
    return ExecutionReceiptV2(
        receipt_identity=receipt_identity,
        schema_version=FP4_EXECUTION_RECEIPT_SCHEMA_VERSION,
        mode=mode,
        status=status,
        action=pretrade.action,
        symbol=pretrade.symbol,
        venue_rule_snapshot_identity=bound_pretrade.venue_rule_snapshot_identity,
        pretrade_identity=pretrade.pretrade_identity,
        plan_identity=pretrade.plan.plan_identity,
        execution_snapshot_identity=bound_pretrade.execution_snapshot.snapshot_identity,
        execution_outcome_identity=outcome.outcome_identity,
        market_evidence_identities=market_evidence,
        fee_projection_identity=fee_projection_identity,
        fee_schedule_snapshot_identity=fee_schedule_snapshot_identity,
        fee_role=fee_role,
        requested_quantity=outcome.requested_quantity,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        reference_price=pretrade.reference_price,
        average_fill_price=average_fill_price,
        fill_notional_usdt=fill_notional,
        fee_usdt=fee_usdt,
        adverse_price_impact_usdt=adverse_impact,
        immediate_execution_cost_usdt=immediate_cost,
        funding_accounted_separately=True,
        real_capital=REAL_CAPITAL,
    )


def compute_execution_receipt_identity(
    *,
    schema_version: str,
    mode: ExecutionReceiptMode,
    status: ExecutionReceiptStatus,
    action: PaperAction,
    symbol: PaperSymbol,
    venue_rule_snapshot_identity: str,
    pretrade_identity: str,
    plan_identity: str,
    execution_snapshot_identity: str,
    execution_outcome_identity: str,
    market_evidence_identities: tuple[str, ...],
    fee_projection_identity: str | None,
    fee_schedule_snapshot_identity: str | None,
    fee_role: InstrumentFeeRole | None,
    requested_quantity: Decimal,
    filled_quantity: Decimal,
    unfilled_quantity: Decimal,
    reference_price: Decimal,
    average_fill_price: Decimal | None,
    fill_notional_usdt: Decimal,
    fee_usdt: Decimal,
    adverse_price_impact_usdt: Decimal,
    immediate_execution_cost_usdt: Decimal,
    funding_accounted_separately: bool,
) -> str:
    return canonical_sha256(
        {
            "action": action.value,
            "adverse_price_impact_usdt": adverse_price_impact_usdt,
            "average_fill_price": average_fill_price,
            "execution_outcome_identity": execution_outcome_identity,
            "execution_snapshot_identity": execution_snapshot_identity,
            "fee_projection_identity": fee_projection_identity,
            "fee_role": None if fee_role is None else fee_role.value,
            "fee_schedule_snapshot_identity": fee_schedule_snapshot_identity,
            "fee_usdt": fee_usdt,
            "fill_notional_usdt": fill_notional_usdt,
            "filled_quantity": filled_quantity,
            "funding_accounted_separately": funding_accounted_separately,
            "immediate_execution_cost_usdt": immediate_execution_cost_usdt,
            "market_evidence_identities": list(market_evidence_identities),
            "mode": mode.value,
            "plan_identity": plan_identity,
            "pretrade_identity": pretrade_identity,
            "reference_price": reference_price,
            "requested_quantity": requested_quantity,
            "schema_version": schema_version,
            "status": status.value,
            "symbol": symbol.value,
            "unfilled_quantity": unfilled_quantity,
            "venue_rule_snapshot_identity": venue_rule_snapshot_identity,
        }
    )


def _outcome_contract(
    *,
    outcome: ExecutionOutcomeV2,
    orderbook: OrderBookSnapshot,
    public_trades: tuple[PublicTradeObservation, ...],
    symbol: PaperSymbol,
) -> tuple[
    ExecutionReceiptMode,
    ExecutionReceiptStatus,
    InstrumentFeeRole,
    tuple[str, ...],
]:
    if orderbook.snapshot_identity != outcome.orderbook_snapshot_identity:
        raise ExecutionReceiptRejectedError("orderbook evidence identity mismatch")
    if (
        orderbook.exchange is not Exchange.BINANCE
        or orderbook.market_type is not MarketType.SPOT
        or orderbook.symbol != symbol.value
    ):
        raise ExecutionReceiptRejectedError(
            "execution market evidence must match Binance Spot pretrade symbol"
        )

    if isinstance(outcome, DepthExecutionOutcome):
        if public_trades:
            raise ExecutionReceiptRejectedError(
                "depth receipt must not attach passive trade evidence"
            )
        status = ExecutionReceiptStatus(outcome.status.value)
        return (
            ExecutionReceiptMode.DEPTH,
            status,
            InstrumentFeeRole.TAKER,
            (outcome.orderbook_snapshot_identity,),
        )

    if isinstance(outcome, PassiveLimitExecutionOutcome):
        supplied = {trade.trade_identity: trade for trade in public_trades}
        expected = set(outcome.evidence_trade_identities)
        if set(supplied) != expected:
            raise ExecutionReceiptRejectedError(
                "passive trade evidence identities do not match outcome"
            )
        for trade in supplied.values():
            if (
                trade.exchange is not orderbook.exchange
                or trade.market_type is not orderbook.market_type
                or trade.symbol != orderbook.symbol
            ):
                raise ExecutionReceiptRejectedError(
                    "passive trade evidence venue/symbol mismatch"
                )
        status = ExecutionReceiptStatus(outcome.status.value)
        market_evidence = (
            outcome.orderbook_snapshot_identity,
            *outcome.evidence_trade_identities,
        )
        return (
            ExecutionReceiptMode.PASSIVE_LIMIT,
            status,
            InstrumentFeeRole.MAKER,
            market_evidence,
        )
    raise TypeError("unsupported FP4 execution outcome type")


def _execution_evidence_cutoff_ms(outcome: ExecutionOutcomeV2) -> int:
    if isinstance(outcome, DepthExecutionOutcome):
        return outcome.execution_cutoff_ms
    if isinstance(outcome, PassiveLimitExecutionOutcome):
        return outcome.completed_at_ms
    raise TypeError("unsupported FP4 execution outcome type")


def _adverse_price_impact(
    *,
    action: PaperAction,
    reference_price: Decimal,
    average_fill_price: Decimal | None,
    filled_quantity: Decimal,
) -> Decimal:
    if average_fill_price is None or filled_quantity == Decimal(0):
        return Decimal(0)
    if action is PaperAction.BUY:
        delta = average_fill_price - reference_price
    else:
        delta = reference_price - average_fill_price
    return max(delta, Decimal(0)) * filled_quantity


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "FP4_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "ExecutionReceiptMode",
    "ExecutionReceiptRejectedError",
    "ExecutionReceiptStatus",
    "ExecutionReceiptV2",
    "build_execution_receipt_v2",
    "compute_execution_receipt_identity",
]
