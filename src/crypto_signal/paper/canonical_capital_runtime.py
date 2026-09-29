"""S11 canonical three-vault paper BUY commit.

The function in this module is deliberately narrow: it commits only a simulated
BUY whose exact forecast/proof/sizing/price/mark/execution evidence is supplied
by the caller. It reuses R21/R22 atomic accounting and never contacts an exchange.
REAL_CAPITAL remains 0.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from crypto_signal.forecast_stream import ImmutableForecast
from crypto_signal.paper.canonical_capital_outcomes import (
    CanonicalCapitalFinancialOutcome,
    build_capital_outcome_evidence,
    reconstruct_open_cost_basis,
)
from crypto_signal.paper.canonical_sizing import CanonicalPaperSizingSelection
from crypto_signal.paper.canonical_sizing_events import (
    CanonicalSizingEvent,
    CanonicalSizingEventLedger,
    build_canonical_sizing_event,
)
from crypto_signal.paper.canonical_vault_eligibility import (
    CanonicalVaultEligibilityProof,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2CanonicalLedger,
    Epoch2ConsolidatedAccountingSnapshot,
    Epoch2LedgerState,
    Epoch2VaultAccountingSnapshot,
    build_consolidated_epoch2_snapshot,
    build_epoch2_vault_accounting_snapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import (
    FrozenExecutionSnapshot,
    simulate_paper_fill,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PAPER_FUND_SCHEMA_VERSION,
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    build_decision_intent,
    build_position_cash_mutation,
    normalize_positions,
)
from crypto_signal.paper.planning import (
    default_conservative_risk_policy,
    plan_paper_trade,
)
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingAssessment,
    SizingMethod,
    SizingMethodResult,
    SizingMethodStatus,
)
from crypto_signal.paper.state import PaperFundState
from crypto_signal.paper.transaction_tape import (
    PaperTapeFill,
    PaperTapeIntent,
    build_tape_fill,
    build_tape_intent,
)
from crypto_signal.paper.transaction_tape_atomic import (
    R22Epoch2AccountingBundle,
    R22Epoch2AtomicTape,
    build_epoch2_accounting_bundle,
)
from crypto_signal.product.decision_proof import DecisionProofSnapshot
from crypto_signal.signals.models import SignalDirection, SignalState

S11_CAPITAL_COMMIT_VERSION = "stream-s11-capital-commit-v1/1"
S11_CAPITAL_SELL_COMMIT_VERSION = "stream-s11-capital-sell-commit-v1/1"


@dataclass(frozen=True, slots=True)
class CanonicalCapitalCommitResult:
    version: str
    vault_id: PaperVaultId
    sizing_selection_identity: str
    sizing_event_identity: str
    intent_identity: str
    fill_identity: str
    accounting_bundle_identity: str
    after_vault_snapshot_identity: str
    after_consolidated_snapshot_identity: str
    quantity: Decimal
    reference_price: Decimal
    simulated_fill_price: Decimal
    inserted: bool
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != S11_CAPITAL_COMMIT_VERSION:
            raise ValueError("unsupported S11 capital commit version")
        for value, label in (
            (self.sizing_selection_identity, "S11 sizing selection"),
            (self.sizing_event_identity, "S11 sizing event"),
            (self.intent_identity, "S11 R22 intent"),
            (self.fill_identity, "S11 R22 fill"),
            (self.accounting_bundle_identity, "S11 accounting bundle"),
            (self.after_vault_snapshot_identity, "S11 vault snapshot"),
            (
                self.after_consolidated_snapshot_identity,
                "S11 consolidated snapshot",
            ),
        ):
            _require_sha256(value, label)
        if self.quantity <= 0:
            raise ValueError("S11 committed quantity must be positive")
        if self.reference_price <= 0 or self.simulated_fill_price <= 0:
            raise ValueError("S11 committed prices must be positive")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("S11 commit cannot grant production/real-capital authority")


@dataclass(frozen=True, slots=True)
class CanonicalCapitalSellCommitResult:
    version: str
    vault_id: PaperVaultId
    action: PaperAction
    intent_identity: str
    fill_identity: str
    outcome_identity: str
    accounting_bundle_identity: str
    after_vault_snapshot_identity: str
    after_consolidated_snapshot_identity: str
    quantity: Decimal
    reference_price: Decimal
    simulated_fill_price: Decimal
    realized_pnl_delta_usdt: Decimal
    financial_outcome: CanonicalCapitalFinancialOutcome
    inserted: bool
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != S11_CAPITAL_SELL_COMMIT_VERSION:
            raise ValueError("unsupported S11 capital sell commit version")
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("S11 sell commit requires canonical vault")
        if self.action not in {PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("S11 sell commit requires REDUCE or EXIT")
        for identity, label in (
            (self.intent_identity, "S11 sell R22 intent"),
            (self.fill_identity, "S11 sell R22 fill"),
            (self.outcome_identity, "S11 sell outcome"),
            (self.accounting_bundle_identity, "S11 sell accounting bundle"),
            (self.after_vault_snapshot_identity, "S11 sell vault snapshot"),
            (
                self.after_consolidated_snapshot_identity,
                "S11 sell consolidated snapshot",
            ),
        ):
            _require_sha256(identity, label)
        if self.quantity <= 0:
            raise ValueError("S11 sold quantity must be positive")
        if self.reference_price <= 0 or self.simulated_fill_price <= 0:
            raise ValueError("S11 sell prices must be positive")
        if not self.realized_pnl_delta_usdt.is_finite():
            raise ValueError("S11 sell realized PnL must be finite")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("S11 sell cannot grant production/real-capital authority")



@dataclass(frozen=True, slots=True)
class CanonicalActiveBuyEntry:
    """Read-only representation of one immutable BUY contributing to an open position."""

    intent_identity: str
    fill_identity: str
    forecast_identity: str
    proof_identity: str
    sizing_assessment_identity: str
    sizing_decision_identity: str
    allocator_candidate_identity: str
    decision_identity: str
    source_evidence_identities: tuple[str, ...]
    quantity: Decimal
    decided_at_ms: int

    def __post_init__(self) -> None:
        for identity, label in (
            (self.intent_identity, "active BUY intent"),
            (self.fill_identity, "active BUY fill"),
            (self.forecast_identity, "active BUY forecast"),
            (self.proof_identity, "active BUY proof"),
            (self.sizing_assessment_identity, "active BUY sizing assessment"),
            (self.sizing_decision_identity, "active BUY sizing decision"),
            (self.allocator_candidate_identity, "active BUY allocator candidate"),
            (self.decision_identity, "active BUY paper decision"),
        ):
            _require_sha256(identity, label)
        if (
            self.source_evidence_identities
            != tuple(sorted(set(self.source_evidence_identities)))
        ):
            raise ValueError("active BUY source evidence must be sorted unique")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "active BUY source evidence")
        required = {
            self.proof_identity,
            self.sizing_assessment_identity,
            self.sizing_decision_identity,
            self.allocator_candidate_identity,
            self.decision_identity,
        }
        if not required.issubset(set(self.source_evidence_identities)):
            raise ValueError("active BUY lost canonical R22 source lineage")
        if (
            not isinstance(self.quantity, Decimal)
            or not self.quantity.is_finite()
            or self.quantity <= 0
        ):
            raise ValueError("active BUY quantity must be positive finite Decimal")
        if self.decided_at_ms < 0:
            raise ValueError("active BUY decision time must be non-negative")

    @property
    def lineage_evidence_identities(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    self.intent_identity,
                    self.fill_identity,
                    self.forecast_identity,
                    self.proof_identity,
                    self.sizing_assessment_identity,
                    self.sizing_decision_identity,
                    self.allocator_candidate_identity,
                    self.decision_identity,
                    *self.source_evidence_identities,
                }
            )
        )


def read_canonical_active_buy_entries(
    *,
    epoch2_path: Path,
    vault_id: PaperVaultId,
    symbol: PaperSymbol,
) -> tuple[CanonicalActiveBuyEntry, ...]:
    """Read the exact immutable BUY-entry set that still contributes to R21 holdings."""

    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    current = _current_vault(state, vault_id)
    history = R22Epoch2AtomicTape(epoch2_path).read_trade_history(vault_id, symbol)
    open_quantity, entries = _active_buy_entries_from_history(
        history,
        vault_id=vault_id,
        symbol=symbol,
    )
    if open_quantity != _held_quantity(current.positions, symbol):
        raise ValueError("active BUY entry set disagrees with current R21 holdings")
    return entries


def commit_canonical_paper_buy(
    *,
    epoch2_path: Path,
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    sizing_assessment: PositionSizingAssessment,
    sizing_selection: CanonicalPaperSizingSelection,
    eligibility_proof: CanonicalVaultEligibilityProof,
    symbol: PaperSymbol,
    reference_price: Decimal,
    reference_price_evidence_identity: str,
    mark_prices: Mapping[PaperSymbol, Decimal],
    mark_evidence_identity: str,
    execution_snapshot: FrozenExecutionSnapshot,
    decided_at_ms: int,
    filled_at_ms: int,
    mutated_at_ms: int,
    snapshot_at_ms: int,
    additional_source_evidence_identities: tuple[str, ...] = (),
    additional_reason_codes: tuple[str, ...] = (),
) -> CanonicalCapitalCommitResult:
    """Commit one exact simulated BUY into canonical Epoch 2/R22 atomically."""
    _require_sha256(
        reference_price_evidence_identity,
        "S11 reference price evidence",
    )
    _require_sha256(mark_evidence_identity, "S11 mark evidence")
    if (
        additional_source_evidence_identities
        != tuple(sorted(set(additional_source_evidence_identities)))
    ):
        raise ValueError("S11 BUY additional source evidence must be sorted unique")
    for identity in additional_source_evidence_identities:
        _require_sha256(identity, "S11 BUY additional source evidence")
    if (
        additional_reason_codes
        != tuple(sorted(set(additional_reason_codes)))
        or any(not item.strip() for item in additional_reason_codes)
    ):
        raise ValueError("S11 BUY additional reason codes must be non-empty sorted unique")
    action_reason_suffix = (
        ""
        if not additional_reason_codes
        else f"; action_reasons={','.join(additional_reason_codes)}"
    )
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    current = _current_vault(state, sizing_selection.vault_id)
    atomic_tape = R22Epoch2AtomicTape(epoch2_path)
    previous_intent_identity, previous_fill_identity = (
        atomic_tape.read_latest_chain_identities(sizing_selection.vault_id)
    )
    _validate_trade_lineage(
        state=state,
        current=current,
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        sizing_selection=sizing_selection,
        eligibility_proof=eligibility_proof,
        symbol=symbol,
        reference_price=reference_price,
        execution_snapshot=execution_snapshot,
        decided_at_ms=decided_at_ms,
        filled_at_ms=filled_at_ms,
        mutated_at_ms=mutated_at_ms,
        snapshot_at_ms=snapshot_at_ms,
    )
    sizing_event = build_canonical_sizing_event(
        sizing_selection,
        eligibility_proof,
    )
    CanonicalSizingEventLedger(epoch2_path).append(sizing_event)
    normalized_marks = _validate_marks(
        current=current,
        new_symbol=symbol,
        mark_prices=mark_prices,
    )
    sizing_result = _selected_sizing_result(
        sizing_assessment,
        sizing_selection,
    )
    quantity = _quantity_from_notional(
        notional=sizing_selection.canonical_notional_usdt,
        reference_price=reference_price,
        snapshot=execution_snapshot,
    )
    cost_budget = _execution_cost_budget(
        quantity=quantity,
        reference_price=reference_price,
        snapshot=execution_snapshot,
    )
    paper_state = _paper_state_from_vault(state, current)
    plan = plan_paper_trade(
        state=paper_state,
        planned_at_ms=decided_at_ms,
        action=PaperAction.BUY,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        cost_budget_usdt=cost_budget,
        mark_prices=normalized_marks,
        risk_policy=default_conservative_risk_policy(),
        reason=(
            "S11 canonical Epoch2 paper BUY from exact fixed-fractional "
            f"selection {sizing_selection.selection_identity}"
            f"{action_reason_suffix}"
        ),
        invalidation_context=(
            f"{forecast.invalidation_trigger.value}:"
            f"{forecast.invalidation_price}"
        ),
    )
    decision = build_decision_intent(
        fund_identity=state.activation.activation_identity,
        decided_at_ms=decided_at_ms,
        action=PaperAction.BUY,
        symbol=symbol,
        quantity=quantity,
        reference_price=reference_price,
        reason=(
            "S11 canonical Epoch2 paper BUY bound to exact "
            f"sizing selection {sizing_selection.selection_identity}"
            f"{action_reason_suffix}"
        ),
        invalidation_context=(
            f"{forecast.invalidation_trigger.value}:"
            f"{forecast.invalidation_price}"
        ),
    )
    additional_evidence = tuple(
        sorted(
            {
                sizing_selection.selection_identity,
                sizing_event.event_identity,
                eligibility_proof.proof_identity,
                eligibility_proof.allocator_assessment_identity,
                reference_price_evidence_identity,
                mark_evidence_identity,
                execution_snapshot.snapshot_identity,
                *additional_source_evidence_identities,
            }
        )
    )
    intent = build_tape_intent(
        state.activation,
        vault_id=sizing_selection.vault_id,
        action=PaperAction.BUY,
        decided_at_ms=decided_at_ms,
        reason_codes=tuple(
            sorted(
                {
                    "canonical_epoch2_paper_buy",
                    "fixed_fractional_promoted",
                    f"sizing_selection:{sizing_selection.selection_identity}",
                    *additional_reason_codes,
                }
            )
        ),
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        previous_intent_identity=previous_intent_identity,
        additional_source_evidence_identities=additional_evidence,
    )
    simulation = simulate_paper_fill(
        plan=plan,
        snapshot=execution_snapshot,
        decision_identity=decision.record_identity,
        filled_at_ms=filled_at_ms,
    )
    if simulation.fill is None or simulation.costs is None:
        raise ValueError("S11 BUY did not produce a simulated fill")
    fill = simulation.fill
    costs = simulation.costs

    after_positions = _positions_after_buy(
        current.positions,
        symbol=symbol,
        quantity=quantity,
    )
    cash_after = current.cash_usdt - simulation.fill_notional_usdt - costs.fee_usdt
    if cash_after < 0:
        raise ValueError("S11 simulated BUY would make vault cash negative")
    mutation = build_position_cash_mutation(
        fund_identity=state.activation.activation_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=mutated_at_ms,
        cash_before_usdt=current.cash_usdt,
        cash_after_usdt=cash_after,
        positions_before=current.positions,
        positions_after=after_positions,
    )
    marked_exposure = _marked_exposure(
        after_positions,
        normalized_marks,
    )
    nav = cash_after + marked_exposure
    realized_pnl = current.realized_pnl_usdt
    unrealized_pnl = (
        nav - current.starting_cash_usdt - realized_pnl
    )
    source_ids = tuple(
        sorted(
            {
                intent.intent_identity,
                fill.record_identity,
                mutation.record_identity,
                mark_evidence_identity,
                reference_price_evidence_identity,
                execution_snapshot.snapshot_identity,
                *additional_source_evidence_identities,
                sizing_selection.selection_identity,
                sizing_event.event_identity,
                eligibility_proof.proof_identity,
                eligibility_proof.allocator_assessment_identity,
            }
        )
    )
    target_after = build_epoch2_vault_accounting_snapshot(
        state.activation,
        vault_id=current.vault_id,
        snapshot_at_ms=snapshot_at_ms,
        cash_usdt=cash_after,
        positions=after_positions,
        marked_exposure_usdt=marked_exposure,
        realized_pnl_usdt=realized_pnl,
        unrealized_pnl_usdt=unrealized_pnl,
        fee_usdt=current.fee_usdt + costs.fee_usdt,
        spread_usdt=current.spread_usdt + costs.spread_usdt,
        slippage_usdt=current.slippage_usdt + costs.slippage_usdt,
        turnover_notional_usdt=(
            current.turnover_notional_usdt + simulation.fill_notional_usdt
        ),
        closed_trade_count=current.closed_trade_count,
        win_count=current.win_count,
        loss_count=current.loss_count,
        breakeven_count=current.breakeven_count,
        outcome_distribution=current.outcome_distribution,
        source_record_identities=source_ids,
        previous=current,
    )
    after_vaults = _same_time_vault_snapshots(
        state=state,
        target=target_after,
        snapshot_at_ms=snapshot_at_ms,
    )
    after_parent = build_consolidated_epoch2_snapshot(
        after_vaults,
        previous=state.consolidated_snapshot,
    )
    tape_fill = build_tape_fill(
        intent,
        current,
        target_after,
        fill=fill,
        mutation=mutation,
        mark_evidence_identity=mark_evidence_identity,
        previous_fill_identity=previous_fill_identity,
    )
    bundle = build_epoch2_accounting_bundle(
        state,
        intent=intent,
        fill=tape_fill,
        after_vaults=after_vaults,
        after_consolidated=after_parent,
    )
    inserted = atomic_tape.append_accounting_bundle(
        state,
        intent=intent,
        fill=tape_fill,
        after_vaults=after_vaults,
        after_consolidated=after_parent,
        bundle=bundle,
    )
    return _result(
        selection=sizing_selection,
        sizing_event=sizing_event,
        intent=intent,
        fill=tape_fill,
        bundle=bundle,
        target_after=target_after,
        after_parent=after_parent,
        reference_price=reference_price,
        simulated_fill_price=fill.simulated_fill_price,
        inserted=inserted,
    )


def commit_canonical_paper_sell(
    *,
    epoch2_path: Path,
    action: PaperAction,
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    sizing_assessment: PositionSizingAssessment,
    symbol: PaperSymbol,
    quantity: Decimal | None,
    reference_price: Decimal,
    reference_price_evidence_identity: str,
    exit_evidence_identity: str,
    exit_reason_codes: tuple[str, ...],
    mark_prices: Mapping[PaperSymbol, Decimal],
    mark_evidence_identity: str,
    execution_snapshot: FrozenExecutionSnapshot,
    decided_at_ms: int,
    filled_at_ms: int,
    mutated_at_ms: int,
    snapshot_at_ms: int,
    additional_source_evidence_identities: tuple[str, ...] = (),
) -> CanonicalCapitalSellCommitResult:
    """Commit one canonical simulated REDUCE/EXIT with exact outcome evidence."""
    if action not in {PaperAction.REDUCE, PaperAction.EXIT}:
        raise ValueError("S11 canonical sell requires REDUCE or EXIT")
    _require_sha256(reference_price_evidence_identity, "S11 sell reference evidence")
    _require_sha256(exit_evidence_identity, "S11 sell exit evidence")
    _require_sha256(mark_evidence_identity, "S11 sell mark evidence")
    if (
        additional_source_evidence_identities
        != tuple(sorted(set(additional_source_evidence_identities)))
    ):
        raise ValueError("S11 sell additional source evidence must be sorted unique")
    for identity in additional_source_evidence_identities:
        _require_sha256(identity, "S11 sell additional source evidence")
    if not exit_reason_codes or any(not item.strip() for item in exit_reason_codes):
        raise ValueError("S11 sell requires non-empty exit reason codes")
    reason_codes = tuple(sorted(set(exit_reason_codes)))
    if reason_codes != exit_reason_codes:
        raise ValueError("S11 sell exit reason codes must be sorted unique")

    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    current = _current_vault(state, sizing_assessment.vault_id)
    atomic_tape = R22Epoch2AtomicTape(epoch2_path)
    history = atomic_tape.read_trade_history(current.vault_id, symbol)
    basis = reconstruct_open_cost_basis(
        history,
        vault_id=current.vault_id,
        symbol=symbol,
    )
    current_quantity = _held_quantity(current.positions, symbol)
    if current_quantity != basis.open_quantity:
        raise ValueError("S11 R21 holdings disagree with reconstructed R22 cost basis")
    sell_quantity = (
        current_quantity
        if action is PaperAction.EXIT
        else quantity
    )
    if sell_quantity is None:
        raise ValueError("S11 REDUCE requires exact sell quantity")
    if not isinstance(sell_quantity, Decimal) or not sell_quantity.is_finite():
        raise TypeError("S11 sell quantity must be finite Decimal")
    if sell_quantity <= 0 or sell_quantity > current_quantity:
        raise ValueError("S11 sell quantity is outside current holdings")
    if action is PaperAction.REDUCE and sell_quantity >= current_quantity:
        raise ValueError("S11 REDUCE must leave a positive open quantity")
    if action is PaperAction.EXIT and quantity not in {None, current_quantity}:
        raise ValueError("S11 EXIT quantity must be omitted or equal full holdings")

    sizing_result, active_entry_evidence = _validate_sell_lineage(
        state=state,
        current=current,
        history=history,
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        symbol=symbol,
        reference_price=reference_price,
        execution_snapshot=execution_snapshot,
        decided_at_ms=decided_at_ms,
        filled_at_ms=filled_at_ms,
        mutated_at_ms=mutated_at_ms,
        snapshot_at_ms=snapshot_at_ms,
    )
    normalized_marks = _validate_marks(
        current=current,
        new_symbol=symbol,
        mark_prices=mark_prices,
    )
    previous_intent_identity, previous_fill_identity = (
        atomic_tape.read_latest_chain_identities(current.vault_id)
    )
    cost_budget = _sell_execution_cost_budget(
        quantity=sell_quantity,
        reference_price=reference_price,
        snapshot=execution_snapshot,
    )
    paper_state = _paper_state_from_vault(state, current)
    reason_text = ",".join(reason_codes)
    plan = plan_paper_trade(
        state=paper_state,
        planned_at_ms=decided_at_ms,
        action=action,
        symbol=symbol,
        quantity=sell_quantity,
        reference_price=reference_price,
        cost_budget_usdt=cost_budget,
        mark_prices=normalized_marks,
        risk_policy=default_conservative_risk_policy(),
        reason=f"S11 canonical Epoch2 paper {action.value}: {reason_text}",
        invalidation_context=f"exit_evidence:{exit_evidence_identity}",
    )
    decision = build_decision_intent(
        fund_identity=state.activation.activation_identity,
        decided_at_ms=decided_at_ms,
        action=action,
        symbol=symbol,
        quantity=sell_quantity,
        reference_price=reference_price,
        reason=f"S11 canonical Epoch2 paper {action.value}: {reason_text}",
        invalidation_context=f"exit_evidence:{exit_evidence_identity}",
    )
    additional_evidence = tuple(
        sorted(
            {
                exit_evidence_identity,
                reference_price_evidence_identity,
                mark_evidence_identity,
                execution_snapshot.snapshot_identity,
                *active_entry_evidence,
                *additional_source_evidence_identities,
            }
        )
    )
    intent = build_tape_intent(
        state.activation,
        vault_id=current.vault_id,
        action=action,
        decided_at_ms=decided_at_ms,
        reason_codes=tuple(
            sorted(
                {
                    f"canonical_epoch2_paper_{action.value.lower()}",
                    "weighted_average_cost_basis",
                    *reason_codes,
                }
            )
        ),
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
        previous_intent_identity=previous_intent_identity,
        additional_source_evidence_identities=additional_evidence,
    )
    simulation = simulate_paper_fill(
        plan=plan,
        snapshot=execution_snapshot,
        decision_identity=decision.record_identity,
        filled_at_ms=filled_at_ms,
    )
    if simulation.fill is None or simulation.costs is None:
        raise ValueError("S11 sell did not produce a simulated fill")
    source_fill = simulation.fill
    costs = simulation.costs
    outcome = build_capital_outcome_evidence(
        basis,
        action=action,
        fill=source_fill,
        exit_evidence_identity=exit_evidence_identity,
        additional_source_evidence_identities=tuple(
            sorted(
                {
                    forecast.forecast_identity,
                    proof.proof_identity,
                    sizing_assessment.assessment_identity,
                    sizing_result.result_identity,
                    reference_price_evidence_identity,
                    mark_evidence_identity,
                    execution_snapshot.snapshot_identity,
                    *active_entry_evidence,
                    *additional_source_evidence_identities,
                }
            )
        ),
    )

    after_positions = plan.projected_positions
    cash_after = current.cash_usdt + simulation.fill_notional_usdt - costs.fee_usdt
    mutation = build_position_cash_mutation(
        fund_identity=state.activation.activation_identity,
        source_identity=source_fill.record_identity,
        mutated_at_ms=mutated_at_ms,
        cash_before_usdt=current.cash_usdt,
        cash_after_usdt=cash_after,
        positions_before=current.positions,
        positions_after=after_positions,
    )
    marked_exposure = _marked_exposure(after_positions, normalized_marks)
    nav = cash_after + marked_exposure
    realized_pnl = current.realized_pnl_usdt + outcome.realized_pnl_delta_usdt
    unrealized_pnl = nav - current.starting_cash_usdt - realized_pnl
    outcome_key = (
        "WIN"
        if outcome.realized_pnl_delta_usdt > 0
        else "LOSS"
        if outcome.realized_pnl_delta_usdt < 0
        else "BREAKEVEN"
    )
    distribution = dict(current.outcome_distribution)
    distribution[outcome_key] = distribution.get(outcome_key, 0) + 1
    win_count = current.win_count + (1 if outcome_key == "WIN" else 0)
    loss_count = current.loss_count + (1 if outcome_key == "LOSS" else 0)
    breakeven_count = (
        current.breakeven_count + (1 if outcome_key == "BREAKEVEN" else 0)
    )
    source_ids = tuple(
        sorted(
            {
                intent.intent_identity,
                source_fill.record_identity,
                mutation.record_identity,
                outcome.outcome_identity,
                exit_evidence_identity,
                mark_evidence_identity,
                reference_price_evidence_identity,
                execution_snapshot.snapshot_identity,
                *active_entry_evidence,
                *additional_source_evidence_identities,
            }
        )
    )
    target_after = build_epoch2_vault_accounting_snapshot(
        state.activation,
        vault_id=current.vault_id,
        snapshot_at_ms=snapshot_at_ms,
        cash_usdt=cash_after,
        positions=after_positions,
        marked_exposure_usdt=marked_exposure,
        realized_pnl_usdt=realized_pnl,
        unrealized_pnl_usdt=unrealized_pnl,
        fee_usdt=current.fee_usdt + costs.fee_usdt,
        spread_usdt=current.spread_usdt + costs.spread_usdt,
        slippage_usdt=current.slippage_usdt + costs.slippage_usdt,
        turnover_notional_usdt=(
            current.turnover_notional_usdt + simulation.fill_notional_usdt
        ),
        closed_trade_count=current.closed_trade_count + 1,
        win_count=win_count,
        loss_count=loss_count,
        breakeven_count=breakeven_count,
        outcome_distribution=tuple(sorted(distribution.items())),
        source_record_identities=source_ids,
        previous=current,
    )
    after_vaults = _same_time_vault_snapshots(
        state=state,
        target=target_after,
        snapshot_at_ms=snapshot_at_ms,
    )
    after_parent = build_consolidated_epoch2_snapshot(
        after_vaults,
        previous=state.consolidated_snapshot,
    )
    tape_fill = build_tape_fill(
        intent,
        current,
        target_after,
        fill=source_fill,
        mutation=mutation,
        mark_evidence_identity=mark_evidence_identity,
        outcome_evidence_identity=outcome.outcome_identity,
        previous_fill_identity=previous_fill_identity,
    )
    bundle = build_epoch2_accounting_bundle(
        state,
        intent=intent,
        fill=tape_fill,
        after_vaults=after_vaults,
        after_consolidated=after_parent,
    )
    inserted = atomic_tape.append_accounting_bundle(
        state,
        intent=intent,
        fill=tape_fill,
        after_vaults=after_vaults,
        after_consolidated=after_parent,
        bundle=bundle,
        outcome_evidence=outcome,
    )
    return CanonicalCapitalSellCommitResult(
        version=S11_CAPITAL_SELL_COMMIT_VERSION,
        vault_id=current.vault_id,
        action=action,
        intent_identity=intent.intent_identity,
        fill_identity=tape_fill.fill_identity,
        outcome_identity=outcome.outcome_identity,
        accounting_bundle_identity=bundle.bundle_identity,
        after_vault_snapshot_identity=target_after.snapshot_identity,
        after_consolidated_snapshot_identity=after_parent.snapshot_identity,
        quantity=sell_quantity,
        reference_price=reference_price,
        simulated_fill_price=source_fill.simulated_fill_price,
        realized_pnl_delta_usdt=outcome.realized_pnl_delta_usdt,
        financial_outcome=outcome.financial_outcome,
        inserted=inserted,
    )


def _validate_trade_lineage(
    *,
    state: Epoch2LedgerState,
    current: Epoch2VaultAccountingSnapshot,
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    sizing_assessment: PositionSizingAssessment,
    sizing_selection: CanonicalPaperSizingSelection,
    eligibility_proof: CanonicalVaultEligibilityProof,
    symbol: PaperSymbol,
    reference_price: Decimal,
    execution_snapshot: FrozenExecutionSnapshot,
    decided_at_ms: int,
    filled_at_ms: int,
    mutated_at_ms: int,
    snapshot_at_ms: int,
) -> None:
    if sizing_selection.current_vault_snapshot_identity != current.snapshot_identity:
        raise ValueError("S11 sizing selection is stale against current vault")
    if eligibility_proof.vault_id is not current.vault_id:
        raise ValueError("S11 allocator eligibility proof vault mismatch")
    if (
        eligibility_proof.allocator_candidate_identity
        != sizing_selection.allocator_candidate_identity
        or eligibility_proof.allocator_candidate_identity
        != sizing_assessment.allocator_candidate_identity
    ):
        raise ValueError("S11 allocator eligibility/sizing candidate mismatch")
    if (
        eligibility_proof.starting_budget_usdt
        != sizing_assessment.allocator_vault_starting_budget_usdt
        or eligibility_proof.starting_budget_usdt != current.starting_cash_usdt
    ):
        raise ValueError("S11 allocator eligibility/vault budget mismatch")
    if not eligibility_proof.canonical_paper_execution_eligible:
        raise ValueError("S11 allocator eligibility proof is not executable")
    if eligibility_proof.assessed_at_ms > sizing_selection.selected_at_ms:
        raise ValueError("S11 sizing selection predates allocator eligibility")
    if eligibility_proof.asset != symbol.value:
        raise ValueError("S11 allocator eligibility asset/symbol mismatch")
    if (
        eligibility_proof.vault_id is PaperVaultId.TACTICAL
        and eligibility_proof.tactical_timeframe != forecast.timeframe
    ):
        raise ValueError(
            "S11 Tactical execution requires exact 1m/5m eligibility timeframe"
        )
    if sizing_selection.vault_id is not current.vault_id:
        raise ValueError("S11 sizing selection vault mismatch")
    if sizing_assessment.assessment_identity != sizing_selection.sizing_assessment_identity:
        raise ValueError("S11 sizing assessment/selection mismatch")
    if sizing_assessment.vault_id is not current.vault_id:
        raise ValueError("S11 sizing assessment vault mismatch")
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("S11 proof/forecast identity mismatch")
    if proof.signal_freeze_identity != forecast.signal_freeze_identity:
        raise ValueError("S11 proof/forecast signal mismatch")
    if proof.proof_identity == forecast.forecast_identity:
        raise ValueError("S11 proof identity cannot alias forecast identity")
    if forecast.symbol != symbol.value or proof.symbol != symbol.value:
        raise ValueError("S11 paper symbol does not match forecast/proof")
    if forecast.signal_state is not SignalState.ACTIVE:
        raise ValueError("S11 canonical BUY requires ACTIVE forecast")
    if forecast.direction is not SignalDirection.BULLISH:
        raise ValueError("S11 canonical long-only BUY requires bullish forecast")
    if reference_price <= 0:
        raise ValueError("S11 reference price must be positive")
    if not (forecast.trigger_zone.low <= reference_price <= forecast.trigger_zone.high):
        raise ValueError("S11 BUY reference price must be inside exact trigger zone")
    if execution_snapshot.symbol is not symbol:
        raise ValueError("S11 execution snapshot symbol mismatch")
    if execution_snapshot.real_capital != REAL_CAPITAL:
        raise ValueError("S11 execution snapshot REAL_CAPITAL mismatch")
    if sizing_selection.selected_at_ms > decided_at_ms:
        raise ValueError("S11 decision cannot predate sizing selection")
    if decided_at_ms < max(forecast.issued_at_ms, state.activation.activated_at_ms):
        raise ValueError("S11 decision predates forecast/Epoch2 activation")
    if not (decided_at_ms <= filled_at_ms <= mutated_at_ms <= snapshot_at_ms):
        raise ValueError("S11 decision/fill/mutation/accounting time order invalid")
    if snapshot_at_ms <= current.snapshot_at_ms:
        raise ValueError("S11 accounting snapshot must advance vault time")


def _history_identity(
    raw: Mapping[str, object],
    key: str,
    label: str,
) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{label} must be SHA256 text")
    _require_sha256(value, label)
    return value


def _history_identity_tuple(
    raw: Mapping[str, object],
    key: str,
    label: str,
) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be an identity list")
    identities = tuple(value)
    if any(not isinstance(item, str) for item in identities):
        raise TypeError(f"{label} entries must be text")
    typed = tuple(str(item) for item in identities)
    if typed != tuple(sorted(set(typed))):
        raise ValueError(f"{label} must be sorted unique")
    for identity in typed:
        _require_sha256(identity, label)
    return typed


def _active_buy_entries_from_history(
    history: tuple[dict[str, object], ...],
    *,
    vault_id: PaperVaultId,
    symbol: PaperSymbol,
) -> tuple[Decimal, tuple[CanonicalActiveBuyEntry, ...]]:
    open_quantity = Decimal(0)
    entries: list[CanonicalActiveBuyEntry] = []
    for record in history:
        fill_raw = record.get("fill")
        intent_raw = record.get("intent")
        if not isinstance(fill_raw, dict) or not isinstance(intent_raw, dict):
            raise TypeError("S11 active-entry history requires verified intent/fill mappings")
        if fill_raw.get("vault_id") != vault_id.value:
            raise ValueError("S11 active-entry history crossed vaults")
        if fill_raw.get("symbol") != symbol.value:
            raise ValueError("S11 active-entry history crossed symbols")
        action = PaperAction(str(fill_raw["action"]))
        fill_quantity = Decimal(str(fill_raw["quantity"]))
        if not fill_quantity.is_finite() or fill_quantity <= 0:
            raise ValueError("S11 active-entry history has invalid fill quantity")
        if action is PaperAction.BUY:
            if open_quantity == 0:
                entries = []
            if (
                intent_raw.get("action") != PaperAction.BUY.value
                or intent_raw.get("vault_id") != vault_id.value
                or intent_raw.get("symbol") != symbol.value
            ):
                raise ValueError("S11 active BUY intent/fill lineage mismatch")
            intent_identity = _history_identity(
                intent_raw,
                "intent_identity",
                "S11 active BUY intent",
            )
            fill_intent_identity = _history_identity(
                fill_raw,
                "intent_identity",
                "S11 active BUY fill intent",
            )
            if fill_intent_identity != intent_identity:
                raise ValueError("S11 active BUY fill references different intent")
            entry = CanonicalActiveBuyEntry(
                intent_identity=intent_identity,
                fill_identity=_history_identity(
                    fill_raw,
                    "fill_identity",
                    "S11 active BUY fill",
                ),
                forecast_identity=_history_identity(
                    intent_raw,
                    "forecast_identity",
                    "S11 active BUY forecast",
                ),
                proof_identity=_history_identity(
                    intent_raw,
                    "proof_identity",
                    "S11 active BUY proof",
                ),
                sizing_assessment_identity=_history_identity(
                    intent_raw,
                    "sizing_assessment_identity",
                    "S11 active BUY sizing assessment",
                ),
                sizing_decision_identity=_history_identity(
                    intent_raw,
                    "sizing_decision_identity",
                    "S11 active BUY sizing decision",
                ),
                allocator_candidate_identity=_history_identity(
                    intent_raw,
                    "allocator_candidate_identity",
                    "S11 active BUY allocator candidate",
                ),
                decision_identity=_history_identity(
                    intent_raw,
                    "decision_identity",
                    "S11 active BUY paper decision",
                ),
                source_evidence_identities=_history_identity_tuple(
                    intent_raw,
                    "source_evidence_identities",
                    "S11 active BUY source evidence",
                ),
                quantity=fill_quantity,
                decided_at_ms=int(str(intent_raw["decided_at_ms"])),
            )
            open_quantity += fill_quantity
            entries.append(entry)
            continue
        if action not in {PaperAction.REDUCE, PaperAction.EXIT}:
            raise ValueError("S11 active-entry history found unsupported trade action")
        open_quantity -= fill_quantity
        if open_quantity < 0:
            raise ValueError("S11 sell history reconstructed negative position")
        if open_quantity == 0:
            entries = []
    return open_quantity, tuple(entries)


def _validate_sell_lineage(
    *,
    state: Epoch2LedgerState,
    current: Epoch2VaultAccountingSnapshot,
    history: tuple[dict[str, object], ...],
    forecast: ImmutableForecast,
    proof: DecisionProofSnapshot,
    sizing_assessment: PositionSizingAssessment,
    symbol: PaperSymbol,
    reference_price: Decimal,
    execution_snapshot: FrozenExecutionSnapshot,
    decided_at_ms: int,
    filled_at_ms: int,
    mutated_at_ms: int,
    snapshot_at_ms: int,
) -> tuple[SizingMethodResult, tuple[str, ...]]:
    if proof.forecast_identity != forecast.forecast_identity:
        raise ValueError("S11 sell proof/forecast identity mismatch")
    if proof.signal_freeze_identity != forecast.signal_freeze_identity:
        raise ValueError("S11 sell proof/forecast signal mismatch")
    if forecast.symbol != symbol.value or proof.symbol != symbol.value:
        raise ValueError("S11 sell symbol does not match forecast/proof")
    if sizing_assessment.vault_id is not current.vault_id:
        raise ValueError("S11 sell sizing assessment vault mismatch")
    if reference_price <= 0:
        raise ValueError("S11 sell reference price must be positive")
    if execution_snapshot.symbol is not symbol:
        raise ValueError("S11 sell execution snapshot symbol mismatch")
    if execution_snapshot.real_capital != REAL_CAPITAL:
        raise ValueError("S11 sell execution snapshot REAL_CAPITAL mismatch")
    if decided_at_ms < max(forecast.issued_at_ms, state.activation.activated_at_ms):
        raise ValueError("S11 sell decision predates forecast/Epoch2 activation")
    if not (decided_at_ms <= filled_at_ms <= mutated_at_ms <= snapshot_at_ms):
        raise ValueError("S11 sell decision/fill/mutation/accounting order invalid")
    if snapshot_at_ms <= current.snapshot_at_ms:
        raise ValueError("S11 sell accounting snapshot must advance vault time")

    open_quantity, active_entries = _active_buy_entries_from_history(
        history,
        vault_id=current.vault_id,
        symbol=symbol,
    )
    if open_quantity != _held_quantity(current.positions, symbol):
        raise ValueError("S11 sell history does not match current R21 holdings")
    if not active_entries:
        raise ValueError("S11 sell cannot find open BUY lineage")

    latest = active_entries[-1]
    if (
        latest.forecast_identity != forecast.forecast_identity
        or latest.proof_identity != proof.proof_identity
        or latest.sizing_assessment_identity != sizing_assessment.assessment_identity
    ):
        raise ValueError("S11 sell must bind the latest active BUY lineage")
    if decided_at_ms <= latest.decided_at_ms:
        raise ValueError("S11 sell decision must follow latest active BUY decision")

    matches = tuple(
        item
        for item in sizing_assessment.results
        if item.result_identity == latest.sizing_decision_identity
    )
    if len(matches) != 1:
        raise ValueError("S11 sell sizing result is not in latest active assessment")
    result = matches[0]
    if (
        result.method is not SizingMethod.FIXED_FRACTIONAL
        or result.status is not SizingMethodStatus.AVAILABLE_SHADOW
        or result.hypothetical_notional_usdt is None
    ):
        raise ValueError("S11 sell requires latest available fixed-fractional sizing")

    active_entry_evidence = tuple(
        sorted(
            {
                identity
                for entry in active_entries
                for identity in entry.lineage_evidence_identities
            }
        )
    )
    return result, active_entry_evidence

def _held_quantity(
    positions: tuple[PaperPosition, ...],
    symbol: PaperSymbol,
) -> Decimal:
    return next(
        (item.quantity for item in positions if item.symbol is symbol),
        Decimal(0),
    )


def _sell_execution_cost_budget(
    *,
    quantity: Decimal,
    reference_price: Decimal,
    snapshot: FrozenExecutionSnapshot,
) -> Decimal:
    reference_notional = quantity * reference_price
    adverse = snapshot.spread_rate + snapshot.slippage_rate
    fill_notional = reference_notional * (Decimal(1) - adverse)
    fee = fill_notional * snapshot.fee_rate
    return (
        fee
        + reference_notional * snapshot.spread_rate
        + reference_notional * snapshot.slippage_rate
    )


def _selected_sizing_result(
    assessment: PositionSizingAssessment,
    selection: CanonicalPaperSizingSelection,
) -> SizingMethodResult:
    matches = tuple(
        item
        for item in assessment.results
        if item.result_identity == selection.sizing_result_identity
    )
    if len(matches) != 1:
        raise ValueError("S11 sizing selection result is not in assessment")
    result = matches[0]
    if result.method is not selection.method:
        raise ValueError("S11 sizing selection method mismatch")
    if result.fraction_of_vault != selection.fraction_of_vault:
        raise ValueError("S11 sizing selection fraction mismatch")
    return result


def _current_vault(
    state: Epoch2LedgerState,
    vault_id: PaperVaultId,
) -> Epoch2VaultAccountingSnapshot:
    matches = tuple(item for item in state.vault_snapshots if item.vault_id is vault_id)
    if len(matches) != 1:
        raise ValueError("S11 Epoch2 state lacks exact target vault")
    return matches[0]


def _quantity_from_notional(
    *,
    notional: Decimal,
    reference_price: Decimal,
    snapshot: FrozenExecutionSnapshot,
) -> Decimal:
    if notional <= 0 or reference_price <= 0:
        raise ValueError("S11 notional/reference price must be positive")
    raw = notional / reference_price
    steps = (raw / snapshot.quantity_step).to_integral_value(rounding=ROUND_DOWN)
    quantity = steps * snapshot.quantity_step
    if quantity < snapshot.min_quantity:
        raise ValueError("S11 canonical notional is below frozen minimum quantity")
    if quantity * reference_price < snapshot.min_notional_usdt:
        raise ValueError("S11 canonical notional is below frozen minimum notional")
    if quantity * reference_price > notional:
        raise ValueError("S11 quantity rounding exceeded canonical notional")
    return quantity


def _execution_cost_budget(
    *,
    quantity: Decimal,
    reference_price: Decimal,
    snapshot: FrozenExecutionSnapshot,
) -> Decimal:
    reference_notional = quantity * reference_price
    adverse = snapshot.spread_rate + snapshot.slippage_rate
    fill_notional = reference_notional * (Decimal(1) + adverse)
    fee = fill_notional * snapshot.fee_rate
    return (
        fee
        + reference_notional * snapshot.spread_rate
        + reference_notional * snapshot.slippage_rate
    )


def _paper_state_from_vault(
    state: Epoch2LedgerState,
    vault: Epoch2VaultAccountingSnapshot,
) -> PaperFundState:
    return PaperFundState(
        fund_identity=state.activation.activation_identity,
        cash_usdt=vault.cash_usdt,
        positions=vault.positions,
        real_capital=REAL_CAPITAL,
        created_at_ms=state.activation.activated_at_ms,
        schema_version=PAPER_FUND_SCHEMA_VERSION,
        execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
        risk_policy_version=PAPER_RISK_POLICY_VERSION,
        last_mutation_identity=None,
        last_mutation_at_ms=None,
        latest_nav_snapshot=None,
        replayed_record_count=0,
    )


def _validate_marks(
    *,
    current: Epoch2VaultAccountingSnapshot,
    new_symbol: PaperSymbol,
    mark_prices: Mapping[PaperSymbol, Decimal],
) -> dict[PaperSymbol, Decimal]:
    required = {item.symbol for item in current.positions} | {new_symbol}
    missing = required - set(mark_prices)
    if missing:
        raise ValueError("S11 exact mark price missing for held/new symbol")
    normalized: dict[PaperSymbol, Decimal] = {}
    for symbol in required:
        price = mark_prices[symbol]
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise ValueError("S11 mark prices must be finite positive Decimal")
        normalized[symbol] = price
    return normalized


def _positions_after_buy(
    positions: tuple[PaperPosition, ...],
    *,
    symbol: PaperSymbol,
    quantity: Decimal,
) -> tuple[PaperPosition, ...]:
    by_symbol = {item.symbol: item.quantity for item in positions}
    by_symbol[symbol] = by_symbol.get(symbol, Decimal(0)) + quantity
    return normalize_positions(by_symbol)


def _marked_exposure(
    positions: tuple[PaperPosition, ...],
    mark_prices: Mapping[PaperSymbol, Decimal],
) -> Decimal:
    return sum(
        (
            item.quantity * mark_prices[item.symbol]
            for item in positions
        ),
        start=Decimal(0),
    )


def _same_time_vault_snapshots(
    *,
    state: Epoch2LedgerState,
    target: Epoch2VaultAccountingSnapshot,
    snapshot_at_ms: int,
) -> tuple[Epoch2VaultAccountingSnapshot, ...]:
    result: list[Epoch2VaultAccountingSnapshot] = []
    for previous in state.vault_snapshots:
        if previous.vault_id is target.vault_id:
            result.append(target)
            continue
        result.append(
            build_epoch2_vault_accounting_snapshot(
                state.activation,
                vault_id=previous.vault_id,
                snapshot_at_ms=snapshot_at_ms,
                cash_usdt=previous.cash_usdt,
                positions=previous.positions,
                marked_exposure_usdt=previous.marked_exposure_usdt,
                realized_pnl_usdt=previous.realized_pnl_usdt,
                unrealized_pnl_usdt=previous.unrealized_pnl_usdt,
                fee_usdt=previous.fee_usdt,
                spread_usdt=previous.spread_usdt,
                slippage_usdt=previous.slippage_usdt,
                turnover_notional_usdt=previous.turnover_notional_usdt,
                closed_trade_count=previous.closed_trade_count,
                win_count=previous.win_count,
                loss_count=previous.loss_count,
                breakeven_count=previous.breakeven_count,
                outcome_distribution=previous.outcome_distribution,
                source_record_identities=(previous.snapshot_identity,),
                previous=previous,
            )
        )
    return tuple(sorted(result, key=lambda item: item.vault_id.value))


def _result(
    *,
    selection: CanonicalPaperSizingSelection,
    sizing_event: CanonicalSizingEvent,
    intent: PaperTapeIntent,
    fill: PaperTapeFill,
    bundle: R22Epoch2AccountingBundle,
    target_after: Epoch2VaultAccountingSnapshot,
    after_parent: Epoch2ConsolidatedAccountingSnapshot,
    reference_price: Decimal,
    simulated_fill_price: Decimal,
    inserted: bool,
) -> CanonicalCapitalCommitResult:
    return CanonicalCapitalCommitResult(
        version=S11_CAPITAL_COMMIT_VERSION,
        vault_id=selection.vault_id,
        sizing_selection_identity=selection.selection_identity,
        sizing_event_identity=sizing_event.event_identity,
        intent_identity=intent.intent_identity,
        fill_identity=fill.fill_identity,
        accounting_bundle_identity=bundle.bundle_identity,
        after_vault_snapshot_identity=target_after.snapshot_identity,
        after_consolidated_snapshot_identity=after_parent.snapshot_identity,
        quantity=fill.quantity,
        reference_price=reference_price,
        simulated_fill_price=simulated_fill_price,
        inserted=inserted,
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
