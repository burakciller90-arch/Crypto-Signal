"""S11 deterministic cost-basis and sell-outcome evidence for canonical paper capital.

The policy reconstructs open cost basis only from immutable R22 fill truth.
It does not contact an exchange and never grants real-money authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol, SimulatedFillRecord

S11_COST_BASIS_POLICY_VERSION = "stream-s11-weighted-average-cost-basis-v1/1"
S11_CAPITAL_OUTCOME_SCHEMA_VERSION = "stream-s11-capital-outcome-v1/1"
S11_CAPITAL_OUTCOME_ENGINE_VERSION = "stream-s11-capital-outcome-engine-v1/1"
REAL_CAPITAL = 0


class CanonicalCapitalFinancialOutcome(StrEnum):
    PARTIAL_REDUCTION = "PARTIAL_REDUCTION"
    CLOSED_WIN = "CLOSED_WIN"
    CLOSED_LOSS = "CLOSED_LOSS"
    CLOSED_BREAKEVEN = "CLOSED_BREAKEVEN"


@dataclass(frozen=True, slots=True)
class ReconstructedOpenCostBasis:
    vault_id: PaperVaultId
    symbol: PaperSymbol
    open_quantity: Decimal
    remaining_cost_basis_usdt: Decimal
    average_cost_per_unit_usdt: Decimal
    prior_fill_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 cost basis requires canonical vault")
        if not isinstance(self.symbol, PaperSymbol):
            raise TypeError("S11 cost basis requires canonical symbol")
        for amount, label in (
            (self.open_quantity, "open quantity"),
            (self.remaining_cost_basis_usdt, "remaining basis"),
            (self.average_cost_per_unit_usdt, "average cost"),
        ):
            _decimal(amount, label, positive=False)
        if self.open_quantity <= 0:
            raise ValueError("S11 cost basis requires an open position")
        if self.remaining_cost_basis_usdt <= 0:
            raise ValueError("S11 cost basis must remain positive for an open position")
        if self.average_cost_per_unit_usdt != (
            self.remaining_cost_basis_usdt / self.open_quantity
        ):
            raise ValueError("S11 average cost does not reconcile")
        _identity_tuple(self.prior_fill_identities, "S11 prior fill")


@dataclass(frozen=True, slots=True)
class CanonicalCapitalOutcomeEvidence:
    outcome_identity: str
    schema_version: str
    engine_version: str
    cost_basis_policy_version: str
    vault_id: PaperVaultId
    action: PaperAction
    symbol: PaperSymbol
    source_fill_identity: str
    exit_evidence_identity: str
    filled_at_ms: int
    quantity: Decimal
    position_quantity_before: Decimal
    position_quantity_after: Decimal
    cost_basis_before_usdt: Decimal
    average_cost_per_unit_usdt: Decimal
    removed_cost_basis_usdt: Decimal
    remaining_cost_basis_usdt: Decimal
    gross_proceeds_usdt: Decimal
    exit_fee_usdt: Decimal
    net_proceeds_usdt: Decimal
    realized_pnl_delta_usdt: Decimal
    financial_outcome: CanonicalCapitalFinancialOutcome
    prior_fill_identities: tuple[str, ...]
    source_evidence_identities: tuple[str, ...]
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.outcome_identity, "S11 outcome"),
            (self.source_fill_identity, "S11 outcome source fill"),
            (self.exit_evidence_identity, "S11 exit evidence"),
        ):
            _sha(identity, label)
        if self.schema_version != S11_CAPITAL_OUTCOME_SCHEMA_VERSION:
            raise ValueError("unsupported S11 capital outcome schema")
        if self.engine_version != S11_CAPITAL_OUTCOME_ENGINE_VERSION:
            raise ValueError("unsupported S11 capital outcome engine")
        if self.cost_basis_policy_version != S11_COST_BASIS_POLICY_VERSION:
            raise ValueError("unsupported S11 cost-basis policy")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 outcome requires canonical vault")
        if self.action not in {PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("S11 outcome requires REDUCE or EXIT")
        if not isinstance(self.symbol, PaperSymbol):
            raise TypeError("S11 outcome requires canonical symbol")
        if self.filled_at_ms < 0:
            raise ValueError("S11 outcome fill time must be non-negative")
        for amount, label, positive in (
            (self.quantity, "quantity", True),
            (self.position_quantity_before, "position before", True),
            (self.position_quantity_after, "position after", False),
            (self.cost_basis_before_usdt, "basis before", True),
            (self.average_cost_per_unit_usdt, "average cost", True),
            (self.removed_cost_basis_usdt, "removed basis", True),
            (self.remaining_cost_basis_usdt, "remaining basis", False),
            (self.gross_proceeds_usdt, "gross proceeds", True),
            (self.exit_fee_usdt, "exit fee", False),
            (self.net_proceeds_usdt, "net proceeds", False),
            (self.realized_pnl_delta_usdt, "realized PnL", False),
        ):
            _decimal(amount, label, positive=positive, allow_negative=label == "realized PnL")
        if self.quantity > self.position_quantity_before:
            raise ValueError("S11 outcome quantity exceeds open position")
        if self.position_quantity_after != self.position_quantity_before - self.quantity:
            raise ValueError("S11 outcome position quantity does not reconcile")
        if self.action is PaperAction.EXIT and self.position_quantity_after != 0:
            raise ValueError("S11 EXIT outcome must flatten the symbol")
        if self.action is PaperAction.REDUCE and self.position_quantity_after <= 0:
            raise ValueError("S11 REDUCE outcome must leave a positive remainder")
        if self.average_cost_per_unit_usdt != (
            self.cost_basis_before_usdt / self.position_quantity_before
        ):
            raise ValueError("S11 outcome average cost does not reconcile")
        expected_removed = (
            self.cost_basis_before_usdt
            if self.action is PaperAction.EXIT
            else self.average_cost_per_unit_usdt * self.quantity
        )
        if self.removed_cost_basis_usdt != expected_removed:
            raise ValueError("S11 removed cost basis does not reconcile")
        if self.remaining_cost_basis_usdt != (
            self.cost_basis_before_usdt - self.removed_cost_basis_usdt
        ):
            raise ValueError("S11 remaining cost basis does not reconcile")
        if self.position_quantity_after == 0 and self.remaining_cost_basis_usdt != 0:
            raise ValueError("S11 flattened position must have zero remaining basis")
        if self.net_proceeds_usdt != self.gross_proceeds_usdt - self.exit_fee_usdt:
            raise ValueError("S11 net proceeds do not reconcile")
        if self.realized_pnl_delta_usdt != (
            self.net_proceeds_usdt - self.removed_cost_basis_usdt
        ):
            raise ValueError("S11 realized PnL does not reconcile")
        expected_outcome = _financial_outcome(self.action, self.realized_pnl_delta_usdt)
        if self.financial_outcome is not expected_outcome:
            raise ValueError("S11 financial outcome does not match realized PnL")
        _identity_tuple(self.prior_fill_identities, "S11 prior fill")
        _identity_tuple(self.source_evidence_identities, "S11 outcome source")
        required = {
            self.source_fill_identity,
            self.exit_evidence_identity,
            *self.prior_fill_identities,
        }
        if not required.issubset(set(self.source_evidence_identities)):
            raise ValueError("S11 outcome lost exact source lineage")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("S11 outcome authority boundary mismatch")
        if self.outcome_identity != canonical_sha256(_outcome_payload(self)):
            raise ValueError("S11 outcome identity mismatch")


def reconstruct_open_cost_basis(
    history: tuple[Mapping[str, object], ...],
    *,
    vault_id: PaperVaultId,
    symbol: PaperSymbol,
) -> ReconstructedOpenCostBasis:
    """Replay verified R22 fill history into weighted-average open cost basis."""
    quantity = Decimal(0)
    basis = Decimal(0)
    fill_ids: list[str] = []

    for item in history:
        fill_raw = item.get("fill")
        if not isinstance(fill_raw, dict):
            raise TypeError("S11 cost-basis history requires verified fill objects")
        if fill_raw.get("vault_id") != vault_id.value:
            raise ValueError("S11 cost-basis history crossed vaults")
        if fill_raw.get("symbol") != symbol.value:
            continue
        fill_identity = _raw_sha(fill_raw, "fill_identity", "S11 historical fill")
        action = PaperAction(_raw_text(fill_raw, "action"))
        fill_quantity = _raw_decimal(fill_raw, "quantity")
        notional = _raw_decimal(fill_raw, "notional_usdt")
        fee = _raw_decimal(fill_raw, "fee_usdt")
        if fill_quantity <= 0 or notional <= 0 or fee < 0:
            raise ValueError("S11 historical fill has invalid money fields")

        if action is PaperAction.BUY:
            quantity += fill_quantity
            basis += notional + fee
            fill_ids.append(fill_identity)
            continue
        if action not in {PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("S11 cost basis found unsupported trade action")
        if quantity <= 0 or fill_quantity > quantity:
            raise ValueError("S11 historical sell exceeds reconstructed position")
        average = basis / quantity
        removed = basis if action is PaperAction.EXIT else average * fill_quantity
        expected_realized = notional - fee - removed
        stored_realized = _raw_decimal(fill_raw, "realized_pnl_delta_usdt")
        if stored_realized != expected_realized:
            raise ValueError("S11 historical realized PnL violates cost-basis policy")
        if action is PaperAction.EXIT and fill_quantity != quantity:
            raise ValueError("S11 historical EXIT did not flatten reconstructed position")
        quantity -= fill_quantity
        basis -= removed
        if quantity == 0:
            basis = Decimal(0)
        fill_ids.append(fill_identity)

    if quantity <= 0 or basis <= 0:
        raise ValueError("S11 cost-basis reconstruction found no open position")
    return ReconstructedOpenCostBasis(
        vault_id=vault_id,
        symbol=symbol,
        open_quantity=quantity,
        remaining_cost_basis_usdt=basis,
        average_cost_per_unit_usdt=basis / quantity,
        prior_fill_identities=tuple(sorted(fill_ids)),
    )


def build_capital_outcome_evidence(
    basis: ReconstructedOpenCostBasis,
    *,
    action: PaperAction,
    fill: SimulatedFillRecord,
    exit_evidence_identity: str,
    additional_source_evidence_identities: tuple[str, ...],
) -> CanonicalCapitalOutcomeEvidence:
    _sha(exit_evidence_identity, "S11 exit evidence")
    if action not in {PaperAction.REDUCE, PaperAction.EXIT}:
        raise ValueError("S11 outcome builder requires REDUCE or EXIT")
    if fill.action is not action:
        raise ValueError("S11 outcome action/fill mismatch")
    if fill.symbol is not basis.symbol:
        raise ValueError("S11 outcome symbol/basis mismatch")
    if fill.quantity > basis.open_quantity:
        raise ValueError("S11 outcome quantity exceeds reconstructed position")
    if action is PaperAction.EXIT and fill.quantity != basis.open_quantity:
        raise ValueError("S11 EXIT must use full reconstructed open quantity")
    if action is PaperAction.REDUCE and fill.quantity >= basis.open_quantity:
        raise ValueError("S11 REDUCE must leave an open quantity")

    removed = (
        basis.remaining_cost_basis_usdt
        if action is PaperAction.EXIT
        else basis.average_cost_per_unit_usdt * fill.quantity
    )
    remaining_quantity = basis.open_quantity - fill.quantity
    remaining_basis = basis.remaining_cost_basis_usdt - removed
    if remaining_quantity == 0:
        remaining_basis = Decimal(0)
    gross = fill.quantity * fill.simulated_fill_price
    fee = fill.costs.fee_usdt
    net = gross - fee
    realized = net - removed
    for identity in additional_source_evidence_identities:
        _sha(identity, "S11 outcome additional evidence")
    sources = tuple(
        sorted(
            {
                *basis.prior_fill_identities,
                *additional_source_evidence_identities,
                fill.record_identity,
                exit_evidence_identity,
            }
        )
    )
    payload = {
        "action": action,
        "average_cost_per_unit_usdt": basis.average_cost_per_unit_usdt,
        "cost_basis_before_usdt": basis.remaining_cost_basis_usdt,
        "cost_basis_policy_version": S11_COST_BASIS_POLICY_VERSION,
        "engine_version": S11_CAPITAL_OUTCOME_ENGINE_VERSION,
        "exit_evidence_identity": exit_evidence_identity,
        "exit_fee_usdt": fee,
        "filled_at_ms": fill.filled_at_ms,
        "financial_outcome": _financial_outcome(action, realized),
        "gross_proceeds_usdt": gross,
        "net_proceeds_usdt": net,
        "position_quantity_after": remaining_quantity,
        "position_quantity_before": basis.open_quantity,
        "prior_fill_identities": basis.prior_fill_identities,
        "production_authority": False,
        "quantity": fill.quantity,
        "real_capital": REAL_CAPITAL,
        "realized_pnl_delta_usdt": realized,
        "remaining_cost_basis_usdt": remaining_basis,
        "removed_cost_basis_usdt": removed,
        "schema_version": S11_CAPITAL_OUTCOME_SCHEMA_VERSION,
        "source_evidence_identities": sources,
        "source_fill_identity": fill.record_identity,
        "symbol": fill.symbol,
        "vault_id": basis.vault_id,
    }
    return CanonicalCapitalOutcomeEvidence(
        outcome_identity=canonical_sha256(payload),
        schema_version=S11_CAPITAL_OUTCOME_SCHEMA_VERSION,
        engine_version=S11_CAPITAL_OUTCOME_ENGINE_VERSION,
        cost_basis_policy_version=S11_COST_BASIS_POLICY_VERSION,
        vault_id=basis.vault_id,
        action=action,
        symbol=fill.symbol,
        source_fill_identity=fill.record_identity,
        exit_evidence_identity=exit_evidence_identity,
        filled_at_ms=fill.filled_at_ms,
        quantity=fill.quantity,
        position_quantity_before=basis.open_quantity,
        position_quantity_after=remaining_quantity,
        cost_basis_before_usdt=basis.remaining_cost_basis_usdt,
        average_cost_per_unit_usdt=basis.average_cost_per_unit_usdt,
        removed_cost_basis_usdt=removed,
        remaining_cost_basis_usdt=remaining_basis,
        gross_proceeds_usdt=gross,
        exit_fee_usdt=fee,
        net_proceeds_usdt=net,
        realized_pnl_delta_usdt=realized,
        financial_outcome=_financial_outcome(action, realized),
        prior_fill_identities=basis.prior_fill_identities,
        source_evidence_identities=sources,
    )


def _financial_outcome(
    action: PaperAction,
    realized_pnl_delta_usdt: Decimal,
) -> CanonicalCapitalFinancialOutcome:
    if action is PaperAction.REDUCE:
        return CanonicalCapitalFinancialOutcome.PARTIAL_REDUCTION
    if realized_pnl_delta_usdt > 0:
        return CanonicalCapitalFinancialOutcome.CLOSED_WIN
    if realized_pnl_delta_usdt < 0:
        return CanonicalCapitalFinancialOutcome.CLOSED_LOSS
    return CanonicalCapitalFinancialOutcome.CLOSED_BREAKEVEN


def _outcome_payload(value: CanonicalCapitalOutcomeEvidence) -> dict[str, object]:
    return {
        "action": value.action,
        "average_cost_per_unit_usdt": value.average_cost_per_unit_usdt,
        "cost_basis_before_usdt": value.cost_basis_before_usdt,
        "cost_basis_policy_version": value.cost_basis_policy_version,
        "engine_version": value.engine_version,
        "exit_evidence_identity": value.exit_evidence_identity,
        "exit_fee_usdt": value.exit_fee_usdt,
        "filled_at_ms": value.filled_at_ms,
        "financial_outcome": value.financial_outcome,
        "gross_proceeds_usdt": value.gross_proceeds_usdt,
        "net_proceeds_usdt": value.net_proceeds_usdt,
        "position_quantity_after": value.position_quantity_after,
        "position_quantity_before": value.position_quantity_before,
        "prior_fill_identities": value.prior_fill_identities,
        "production_authority": value.production_authority,
        "quantity": value.quantity,
        "real_capital": value.real_capital,
        "realized_pnl_delta_usdt": value.realized_pnl_delta_usdt,
        "remaining_cost_basis_usdt": value.remaining_cost_basis_usdt,
        "removed_cost_basis_usdt": value.removed_cost_basis_usdt,
        "schema_version": value.schema_version,
        "source_evidence_identities": value.source_evidence_identities,
        "source_fill_identity": value.source_fill_identity,
        "symbol": value.symbol,
        "vault_id": value.vault_id,
    }


def _raw_text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"S11 historical {key} must be non-empty text")
    return value


def _raw_sha(raw: Mapping[str, object], key: str, label: str) -> str:
    value = _raw_text(raw, key)
    _sha(value, label)
    return value


def _raw_decimal(raw: Mapping[str, object], key: str) -> Decimal:
    value = Decimal(str(raw.get(key)))
    if not value.is_finite():
        raise ValueError(f"S11 historical {key} must be finite")
    return value


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} identities must be non-empty sorted unique")
    for identity in values:
        _sha(identity, label)


def _decimal(
    value: Decimal,
    label: str,
    *,
    positive: bool,
    allow_negative: bool = False,
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"S11 {label} must be finite Decimal")
    if not allow_negative and value < 0:
        raise ValueError(f"S11 {label} cannot be negative")
    if positive and value <= 0:
        raise ValueError(f"S11 {label} must be positive")


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
