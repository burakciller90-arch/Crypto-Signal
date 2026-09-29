"""Deterministic paper funding cash-flow projection from exact settlement evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.funding_settlements import FundingSettlementObservation
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import REAL_CAPITAL, PaperSymbol

PAPER_FUNDING_COST_POLICY_VERSION = "paper_funding_cost.v2"


class PaperFundingSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class PaperFundingCostStatus(StrEnum):
    PROVEN = "proven"
    NOT_PROVEN = "not_proven"


@dataclass(frozen=True, slots=True)
class PaperFundingCostProjection:
    projection_identity: str
    policy_version: str
    status: PaperFundingCostStatus
    side: PaperFundingSide
    symbol: PaperSymbol
    position_quantity: Decimal
    settlement_identity: str | None
    settlement_at_ms: int | None
    mark_evidence_identity: str | None
    mark_price: Decimal | None
    mark_at_ms: int | None
    cash_flow_usdt: Decimal | None
    reason_code: str
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.projection_identity, "projection_identity")
        if not self.policy_version.strip() or not self.reason_code.strip():
            raise ValueError("policy_version and reason_code must be non-empty")
        _require_positive_decimal(self.position_quantity, "position_quantity")
        if self.status is PaperFundingCostStatus.PROVEN:
            if (
                self.settlement_identity is None
                or self.settlement_at_ms is None
                or self.mark_evidence_identity is None
                or self.mark_price is None
                or self.mark_at_ms is None
                or self.cash_flow_usdt is None
            ):
                raise ValueError("PROVEN funding cost requires complete exact evidence")
            _require_sha256(self.settlement_identity, "settlement_identity")
            _require_sha256(self.mark_evidence_identity, "mark_evidence_identity")
            _require_positive_decimal(self.mark_price, "mark_price")
            if self.mark_at_ms != self.settlement_at_ms:
                raise ValueError("PROVEN funding mark must match settlement timestamp")
        else:
            if self.cash_flow_usdt is not None:
                raise ValueError("NOT_PROVEN funding cost cannot invent cash flow")
        if self.projection_identity != compute_funding_projection_identity(
            policy_version=self.policy_version,
            status=self.status,
            side=self.side,
            symbol=self.symbol,
            position_quantity=self.position_quantity,
            settlement_identity=self.settlement_identity,
            settlement_at_ms=self.settlement_at_ms,
            mark_evidence_identity=self.mark_evidence_identity,
            mark_price=self.mark_price,
            mark_at_ms=self.mark_at_ms,
            cash_flow_usdt=self.cash_flow_usdt,
            reason_code=self.reason_code,
        ):
            raise ValueError("funding projection identity mismatch")


def project_paper_funding_cost(
    *,
    side: PaperFundingSide,
    symbol: PaperSymbol,
    position_quantity: Decimal,
    settlement: FundingSettlementObservation | None,
    mark_price: Decimal | None,
    mark_evidence_identity: str | None,
    mark_at_ms: int | None,
    evaluation_cutoff_ms: int,
    policy_version: str = PAPER_FUNDING_COST_POLICY_VERSION,
) -> PaperFundingCostProjection:
    _require_positive_decimal(position_quantity, "position_quantity")
    if evaluation_cutoff_ms < 0:
        raise ValueError("evaluation_cutoff_ms must be non-negative")

    if settlement is None:
        return _not_proven(
            side=side,
            symbol=symbol,
            position_quantity=position_quantity,
            settlement=None,
            mark_price=mark_price,
            mark_evidence_identity=mark_evidence_identity,
            mark_at_ms=mark_at_ms,
            policy_version=policy_version,
            reason_code="missing_exact_settlement_evidence",
        )
    if settlement.ingested_at_ms > evaluation_cutoff_ms:
        raise ValueError("future settlement evidence cannot enter historical funding")
    if settlement.symbol != symbol.value:
        raise ValueError("funding settlement symbol mismatch")
    if (
        mark_price is None
        or mark_evidence_identity is None
        or mark_at_ms is None
        or mark_at_ms != settlement.settlement_at_ms
    ):
        return _not_proven(
            side=side,
            symbol=symbol,
            position_quantity=position_quantity,
            settlement=settlement,
            mark_price=mark_price,
            mark_evidence_identity=mark_evidence_identity,
            mark_at_ms=mark_at_ms,
            policy_version=policy_version,
            reason_code="missing_exact_settlement_mark_evidence",
        )

    _require_positive_decimal(mark_price, "mark_price")
    _require_sha256(mark_evidence_identity, "mark_evidence_identity")
    notional = position_quantity * mark_price
    signed_payment = notional * settlement.funding_rate
    cash_flow = (
        -signed_payment
        if side is PaperFundingSide.LONG
        else signed_payment
    )
    return _build_projection(
        status=PaperFundingCostStatus.PROVEN,
        side=side,
        symbol=symbol,
        position_quantity=position_quantity,
        settlement=settlement,
        mark_price=mark_price,
        mark_evidence_identity=mark_evidence_identity,
        mark_at_ms=mark_at_ms,
        cash_flow_usdt=cash_flow,
        policy_version=policy_version,
        reason_code="exact_settlement_and_mark_proven",
    )


def compute_funding_projection_identity(
    *,
    policy_version: str,
    status: PaperFundingCostStatus,
    side: PaperFundingSide,
    symbol: PaperSymbol,
    position_quantity: Decimal,
    settlement_identity: str | None,
    settlement_at_ms: int | None,
    mark_evidence_identity: str | None,
    mark_price: Decimal | None,
    mark_at_ms: int | None,
    cash_flow_usdt: Decimal | None,
    reason_code: str,
) -> str:
    return canonical_sha256(
        {
            "cash_flow_usdt": cash_flow_usdt,
            "mark_at_ms": mark_at_ms,
            "mark_evidence_identity": mark_evidence_identity,
            "mark_price": mark_price,
            "policy_version": policy_version,
            "position_quantity": position_quantity,
            "reason_code": reason_code,
            "settlement_at_ms": settlement_at_ms,
            "settlement_identity": settlement_identity,
            "side": side.value,
            "status": status.value,
            "symbol": symbol.value,
        }
    )


def _not_proven(
    *,
    side: PaperFundingSide,
    symbol: PaperSymbol,
    position_quantity: Decimal,
    settlement: FundingSettlementObservation | None,
    mark_price: Decimal | None,
    mark_evidence_identity: str | None,
    mark_at_ms: int | None,
    policy_version: str,
    reason_code: str,
) -> PaperFundingCostProjection:
    return _build_projection(
        status=PaperFundingCostStatus.NOT_PROVEN,
        side=side,
        symbol=symbol,
        position_quantity=position_quantity,
        settlement=settlement,
        mark_price=mark_price,
        mark_evidence_identity=mark_evidence_identity,
        mark_at_ms=mark_at_ms,
        cash_flow_usdt=None,
        policy_version=policy_version,
        reason_code=reason_code,
    )


def _build_projection(
    *,
    status: PaperFundingCostStatus,
    side: PaperFundingSide,
    symbol: PaperSymbol,
    position_quantity: Decimal,
    settlement: FundingSettlementObservation | None,
    mark_price: Decimal | None,
    mark_evidence_identity: str | None,
    mark_at_ms: int | None,
    cash_flow_usdt: Decimal | None,
    policy_version: str,
    reason_code: str,
) -> PaperFundingCostProjection:
    settlement_identity = (
        None if settlement is None else settlement.settlement_identity
    )
    settlement_at_ms = None if settlement is None else settlement.settlement_at_ms
    identity = compute_funding_projection_identity(
        policy_version=policy_version,
        status=status,
        side=side,
        symbol=symbol,
        position_quantity=position_quantity,
        settlement_identity=settlement_identity,
        settlement_at_ms=settlement_at_ms,
        mark_evidence_identity=mark_evidence_identity,
        mark_price=mark_price,
        mark_at_ms=mark_at_ms,
        cash_flow_usdt=cash_flow_usdt,
        reason_code=reason_code,
    )
    return PaperFundingCostProjection(
        projection_identity=identity,
        policy_version=policy_version,
        status=status,
        side=side,
        symbol=symbol,
        position_quantity=position_quantity,
        settlement_identity=settlement_identity,
        settlement_at_ms=settlement_at_ms,
        mark_evidence_identity=mark_evidence_identity,
        mark_price=mark_price,
        mark_at_ms=mark_at_ms,
        cash_flow_usdt=cash_flow_usdt,
        reason_code=reason_code,
        real_capital=REAL_CAPITAL,
    )


def _require_positive_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise ValueError(f"{label} must be finite and positive")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "PAPER_FUNDING_COST_POLICY_VERSION",
    "PaperFundingCostProjection",
    "PaperFundingCostStatus",
    "PaperFundingSide",
    "compute_funding_projection_identity",
    "project_paper_funding_cost",
]
