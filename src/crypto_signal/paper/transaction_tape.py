"""R22: immutable Epoch 2 decision and transaction audit.

R22 is evidence and paper-accounting audit infrastructure. It does not create
exchange/network/credential authority. Trade decisions are admitted only when
their exact R20/R20.5 forecast-proof lineage and accepted sizing evidence are
bound to an immutable paper decision. REAL_CAPITAL=0.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, fields
from decimal import Decimal
from pathlib import Path

from crypto_signal.forecast_stream import ImmutableForecast
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.epoch2_accounting import (
    Epoch2ActivationRecord,
    Epoch2VaultAccountingSnapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    DecisionIntentRecord,
    PaperAction,
    PaperSymbol,
    PositionCashMutationRecord,
    SimulatedFillRecord,
)
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingAssessment,
    SizingMethodResult,
    SizingMethodStatus,
)
from crypto_signal.product.decision_proof import DecisionProofSnapshot

R22_SCHEMA_VERSION = "r22-transaction-decision-tape-v1/2"
R22_ENGINE_VERSION = "r22-transaction-decision-tape-v1/2"


def _sha(value: str | None, label: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if value is None or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")


def _money(value: Decimal, label: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{label} must be a finite Decimal")
    if (value <= 0 if positive else value < 0):
        raise ValueError(f"{label} must be {'positive' if positive else 'non-negative'}")


def _payload(record: PaperTapeIntent | PaperTapeFill) -> dict[str, object]:
    identity_key = "intent_identity" if isinstance(record, PaperTapeIntent) else "fill_identity"
    return {
        field.name: getattr(record, field.name)
        for field in fields(record)
        if field.name != identity_key
    }


@dataclass(frozen=True, slots=True)
class PaperTapeIntent:
    intent_identity: str
    activation_identity: str
    vault_id: PaperVaultId
    forecast_identity: str | None
    proof_identity: str | None
    signal_freeze_identity: str | None
    policy_identity: str
    sizing_assessment_identity: str | None
    sizing_decision_identity: str | None
    allocator_candidate_identity: str | None
    decision_identity: str | None
    source_evidence_identities: tuple[str, ...]
    action: PaperAction
    symbol: PaperSymbol | None
    quantity: Decimal | None
    reference_price: Decimal | None
    decided_at_ms: int
    reason_codes: tuple[str, ...]
    previous_intent_identity: str | None = None
    schema_version: str = R22_SCHEMA_VERSION
    engine_version: str = R22_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _sha(self.intent_identity, "intent")
        _sha(self.activation_identity, "activation")
        _sha(self.policy_identity, "policy")
        _sha(self.forecast_identity, "forecast", optional=True)
        _sha(self.proof_identity, "proof", optional=True)
        _sha(self.signal_freeze_identity, "signal", optional=True)
        _sha(self.sizing_assessment_identity, "sizing assessment", optional=True)
        _sha(self.sizing_decision_identity, "sizing result", optional=True)
        _sha(self.allocator_candidate_identity, "allocator candidate", optional=True)
        _sha(self.decision_identity, "paper decision", optional=True)
        _sha(self.previous_intent_identity, "previous intent", optional=True)
        if self.schema_version != R22_SCHEMA_VERSION or self.engine_version != R22_ENGINE_VERSION:
            raise ValueError("unsupported R22 intent version")
        if not isinstance(self.vault_id, PaperVaultId) or not isinstance(self.action, PaperAction):
            raise TypeError("invalid R22 vault or action")
        if self.decided_at_ms < 0:
            raise ValueError("R22 decision time must be non-negative")
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("R22 reason codes must be non-empty, unique, sorted")
        if any(not code.strip() for code in self.reason_codes):
            raise ValueError("R22 reason code cannot be blank")
        if self.source_evidence_identities != tuple(sorted(set(self.source_evidence_identities))):
            raise ValueError("R22 source identities must be sorted and unique")
        for identity in self.source_evidence_identities:
            _sha(identity, "source evidence")

        trade_lineage = (
            self.forecast_identity,
            self.proof_identity,
            self.signal_freeze_identity,
            self.sizing_assessment_identity,
            self.sizing_decision_identity,
            self.allocator_candidate_identity,
            self.decision_identity,
        )
        if self.action is PaperAction.HOLD_CASH:
            if any(item is not None for item in (*trade_lineage, self.symbol, self.quantity, self.reference_price)):
                raise ValueError("R22 HOLD_CASH cannot invent trade/sizing/forecast lineage")
        else:
            if any(item is None for item in trade_lineage):
                raise ValueError("R22 trade requires complete forecast/sizing/decision lineage")
            if self.symbol is None or self.quantity is None or self.reference_price is None:
                raise ValueError("R22 trade decision requires symbol, quantity and price")
            if not isinstance(self.symbol, PaperSymbol):
                raise TypeError("R22 trade symbol must be permitted")
            _money(self.quantity, "decision quantity", positive=True)
            _money(self.reference_price, "decision reference price", positive=True)
            required_sources = {
                self.proof_identity,
                self.policy_identity,
                self.sizing_assessment_identity,
                self.sizing_decision_identity,
                self.allocator_candidate_identity,
                self.decision_identity,
            }
            if not required_sources.issubset(set(self.source_evidence_identities)):
                raise ValueError("R22 trade source evidence misses exact decision lineage")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("R22 decision cannot grant execution authority")
        if self.intent_identity != canonical_sha256(_payload(self)):
            raise ValueError("R22 immutable intent identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperTapeFill:
    fill_identity: str
    intent_identity: str
    activation_identity: str
    vault_id: PaperVaultId
    action: PaperAction
    symbol: PaperSymbol
    source_fill_identity: str
    mutation_identity: str
    filled_at_ms: int
    mutated_at_ms: int
    snapshot_at_ms: int
    before_snapshot_identity: str
    after_snapshot_identity: str
    previous_fill_identity: str | None
    quantity: Decimal
    reference_price: Decimal
    simulated_fill_price: Decimal
    notional_usdt: Decimal
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    execution_policy_version: str
    venue_reference: str
    cash_before_usdt: Decimal
    cash_after_usdt: Decimal
    position_before_quantity: Decimal
    position_after_quantity: Decimal
    nav_before_usdt: Decimal
    nav_after_usdt: Decimal
    realized_pnl_delta_usdt: Decimal
    unrealized_pnl_delta_usdt: Decimal
    mark_evidence_identity: str
    outcome_evidence_identity: str | None
    schema_version: str = R22_SCHEMA_VERSION
    engine_version: str = R22_ENGINE_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _sha(self.fill_identity, "fill")
        _sha(self.intent_identity, "intent")
        _sha(self.activation_identity, "activation")
        _sha(self.source_fill_identity, "source fill")
        _sha(self.mutation_identity, "mutation")
        _sha(self.before_snapshot_identity, "before snapshot")
        _sha(self.after_snapshot_identity, "after snapshot")
        _sha(self.mark_evidence_identity, "mark evidence")
        _sha(self.previous_fill_identity, "previous fill", optional=True)
        _sha(self.outcome_evidence_identity, "outcome", optional=True)
        if self.schema_version != R22_SCHEMA_VERSION or self.engine_version != R22_ENGINE_VERSION:
            raise ValueError("unsupported R22 fill version")
        if not isinstance(self.vault_id, PaperVaultId) or not isinstance(self.symbol, PaperSymbol):
            raise TypeError("R22 fill requires valid vault and symbol")
        if self.action not in (PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT):
            raise ValueError("HOLD_CASH cannot create a fill")
        if min(self.filled_at_ms, self.mutated_at_ms, self.snapshot_at_ms) < 0:
            raise ValueError("R22 fill times cannot be negative")
        if not (self.filled_at_ms <= self.mutated_at_ms <= self.snapshot_at_ms):
            raise ValueError("R22 fill/mutation/accounting times are out of order")
        if not self.execution_policy_version.strip() or not self.venue_reference.strip():
            raise ValueError("R22 fill requires exact execution policy and venue reference")
        _money(self.quantity, "quantity", positive=True)
        _money(self.reference_price, "reference price", positive=True)
        _money(self.simulated_fill_price, "simulated fill price", positive=True)
        _money(self.notional_usdt, "notional")
        _money(self.fee_usdt, "fee")
        _money(self.spread_usdt, "spread")
        _money(self.slippage_usdt, "slippage")
        _money(self.cash_before_usdt, "cash before")
        _money(self.cash_after_usdt, "cash after")
        _money(self.position_before_quantity, "quantity before")
        _money(self.position_after_quantity, "quantity after")
        _money(self.nav_before_usdt, "NAV before")
        _money(self.nav_after_usdt, "NAV after")
        if self.notional_usdt != self.quantity * self.simulated_fill_price:
            raise ValueError("R22 notional must use simulated fill price")
        if self.action is PaperAction.BUY and self.simulated_fill_price < self.reference_price:
            raise ValueError("R22 BUY cannot claim adverse execution improvement")
        if self.action is not PaperAction.BUY and self.simulated_fill_price > self.reference_price:
            raise ValueError("R22 sale cannot claim adverse execution improvement")
        price_impact = abs(self.simulated_fill_price - self.reference_price) * self.quantity
        if self.spread_usdt + self.slippage_usdt != price_impact:
            raise ValueError("R22 execution impact must equal spread plus slippage")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("R22 fill cannot grant execution authority")
        if self.fill_identity != canonical_sha256(_payload(self)):
            raise ValueError("R22 immutable fill identity mismatch")


def build_tape_intent(
    activation: Epoch2ActivationRecord,
    *,
    vault_id: PaperVaultId,
    action: PaperAction,
    decided_at_ms: int,
    reason_codes: tuple[str, ...],
    hold_policy_identity: str | None = None,
    forecast: ImmutableForecast | None = None,
    proof: DecisionProofSnapshot | None = None,
    sizing_assessment: PositionSizingAssessment | None = None,
    sizing_result: SizingMethodResult | None = None,
    decision: DecisionIntentRecord | None = None,
    previous_intent_identity: str | None = None,
) -> PaperTapeIntent:
    if decided_at_ms < activation.activated_at_ms:
        raise ValueError("R22 intent cannot predate Epoch2 activation")

    if action is PaperAction.HOLD_CASH:
        if any(item is not None for item in (forecast, proof, sizing_assessment, sizing_result, decision)):
            raise ValueError("R22 HOLD_CASH cannot claim trade evidence")
        if hold_policy_identity is None:
            raise ValueError("R22 HOLD_CASH requires exact hold-policy identity")
        _sha(hold_policy_identity, "hold policy")
        policy_identity = hold_policy_identity
        evidence: tuple[str, ...] = ()
        symbol = None
        quantity = None
        reference_price = None
        forecast_identity = None
        proof_identity = None
        signal_identity = None
        sizing_assessment_identity = None
        sizing_result_identity = None
        allocator_candidate_identity = None
        decision_identity = None
    else:
        if hold_policy_identity is not None:
            raise ValueError("R22 trade cannot use HOLD_CASH policy argument")
        if any(item is None for item in (forecast, proof, sizing_assessment, sizing_result, decision)):
            raise ValueError("R22 trade requires exact forecast/proof/sizing/decision objects")
        assert forecast is not None
        assert proof is not None
        assert sizing_assessment is not None
        assert sizing_result is not None
        assert decision is not None
        if (
            forecast.forecast_identity != proof.forecast_identity
            or forecast.signal_freeze_identity != proof.signal_freeze_identity
            or forecast.issued_at_ms != proof.issued_at_ms
            or forecast.symbol != proof.symbol
            or forecast.source_as_of_ms != proof.source_as_of_ms
        ):
            raise ValueError("R22 forecast and proof lineage mismatch")
        if not proof.read_only or proof.production_authority:
            raise ValueError("R22 proof must preserve read-only authority")
        if decision.fund_identity != activation.activation_identity:
            raise ValueError("R22 paper decision must target exact Epoch2 activation")
        if decision.action is not action or decision.decided_at_ms != decided_at_ms:
            raise ValueError("R22 immutable decision/action/time mismatch")
        if decided_at_ms < forecast.issued_at_ms:
            raise ValueError("R22 decision cannot precede immutable forecast")
        if decision.symbol is None or decision.symbol.value != forecast.symbol:
            raise ValueError("R22 paper decision symbol must match exact forecast")
        if sizing_assessment.vault_id is not vault_id:
            raise ValueError("R22 sizing assessment vault mismatch")
        accepted_result = next(
            (
                item
                for item in sizing_assessment.results
                if item.result_identity == sizing_result.result_identity
            ),
            None,
        )
        if accepted_result != sizing_result:
            raise ValueError("R22 sizing result does not belong to exact assessment")
        if sizing_result.status is not SizingMethodStatus.AVAILABLE_SHADOW:
            raise ValueError("R22 trade requires an available reviewed sizing result")
        if sizing_result.hypothetical_notional_usdt is None:
            raise ValueError("R22 sizing result lacks hypothetical notional")
        if decision.quantity is None or decision.reference_price is None:
            raise ValueError("R22 trade decision requires quantity and reference price")
        if decision.quantity * decision.reference_price > sizing_result.hypothetical_notional_usdt:
            raise ValueError("R22 paper decision exceeds traced sizing envelope")
        policy_identity = sizing_assessment.policy_identity
        symbol = decision.symbol
        quantity = decision.quantity
        reference_price = decision.reference_price
        forecast_identity = forecast.forecast_identity
        proof_identity = proof.proof_identity
        signal_identity = forecast.signal_freeze_identity
        sizing_assessment_identity = sizing_assessment.assessment_identity
        sizing_result_identity = sizing_result.result_identity
        allocator_candidate_identity = sizing_assessment.allocator_candidate_identity
        decision_identity = decision.record_identity
        evidence = tuple(
            sorted(
                {
                    *forecast.source_evidence_identities,
                    *proof.forecast_source_evidence_identities,
                    proof.proof_identity,
                    sizing_assessment.assessment_identity,
                    sizing_assessment.policy_identity,
                    sizing_result.result_identity,
                    sizing_assessment.allocator_candidate_identity,
                    decision.record_identity,
                }
            )
        )

    payload: dict[str, object] = {
        "activation_identity": activation.activation_identity,
        "vault_id": vault_id,
        "forecast_identity": forecast_identity,
        "proof_identity": proof_identity,
        "signal_freeze_identity": signal_identity,
        "policy_identity": policy_identity,
        "sizing_assessment_identity": sizing_assessment_identity,
        "sizing_decision_identity": sizing_result_identity,
        "allocator_candidate_identity": allocator_candidate_identity,
        "decision_identity": decision_identity,
        "source_evidence_identities": evidence,
        "action": action,
        "symbol": symbol,
        "quantity": quantity,
        "reference_price": reference_price,
        "decided_at_ms": decided_at_ms,
        "reason_codes": tuple(sorted(set(reason_codes))),
        "previous_intent_identity": previous_intent_identity,
        "schema_version": R22_SCHEMA_VERSION,
        "engine_version": R22_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return PaperTapeIntent(intent_identity=canonical_sha256(payload), **payload)  # type: ignore[arg-type]


def build_tape_fill(
    intent: PaperTapeIntent,
    before: Epoch2VaultAccountingSnapshot,
    after: Epoch2VaultAccountingSnapshot,
    *,
    fill: SimulatedFillRecord,
    mutation: PositionCashMutationRecord,
    mark_evidence_identity: str,
    outcome_evidence_identity: str | None = None,
    previous_fill_identity: str | None = None,
) -> PaperTapeFill:
    if intent.action is PaperAction.HOLD_CASH or intent.symbol is None:
        raise ValueError("R22 HOLD_CASH cannot create a capital mutation")
    if intent.quantity is None or intent.reference_price is None or intent.decision_identity is None:
        raise ValueError("R22 fill requires exact prior decision lineage")
    if fill.fund_identity != intent.activation_identity:
        raise ValueError("R22 simulated fill fund mismatch")
    if fill.decision_identity != intent.decision_identity:
        raise ValueError("R22 simulated fill must bind exact paper decision")
    if (
        fill.action is not intent.action
        or fill.symbol is not intent.symbol
        or fill.quantity != intent.quantity
        or fill.reference_price != intent.reference_price
    ):
        raise ValueError("R22 simulated fill does not exactly match frozen intent")
    if fill.filled_at_ms < intent.decided_at_ms:
        raise ValueError("R22 fill predates immutable decision")
    if mutation.fund_identity != intent.activation_identity:
        raise ValueError("R22 mutation fund mismatch")
    if mutation.source_identity != fill.record_identity:
        raise ValueError("R22 mutation must be sourced from exact simulated fill")
    if mutation.mutated_at_ms < fill.filled_at_ms:
        raise ValueError("R22 mutation cannot predate simulated fill")
    if before.activation_identity != intent.activation_identity or after.activation_identity != intent.activation_identity:
        raise ValueError("R22 fill activation mismatch")
    if before.vault_id is not intent.vault_id or after.vault_id is not intent.vault_id:
        raise ValueError("R22 fill cannot cross vaults")
    if after.previous_snapshot_identity != before.snapshot_identity:
        raise ValueError("R22 fill requires exact R21 previous snapshot")
    if not (before.snapshot_at_ms < fill.filled_at_ms <= mutation.mutated_at_ms <= after.snapshot_at_ms):
        raise ValueError("R22 fill/mutation must follow previous accounting and precede new snapshot")
    if (
        mutation.cash_before_usdt != before.cash_usdt
        or mutation.cash_after_usdt != after.cash_usdt
        or mutation.positions_before != before.positions
        or mutation.positions_after != after.positions
    ):
        raise ValueError("R22 exact mutation does not reconcile R21 before/after state")

    required_sources = {
        intent.intent_identity,
        fill.record_identity,
        mutation.record_identity,
        mark_evidence_identity,
    }
    if not required_sources.issubset(set(after.source_record_identities)):
        raise ValueError("R22 R21 after-snapshot lacks exact intent/fill/mutation/mark lineage")
    if intent.action is PaperAction.BUY and after.closed_trade_count != before.closed_trade_count:
        raise ValueError("R22 BUY cannot report a closed trade")
    if intent.action in (PaperAction.REDUCE, PaperAction.EXIT):
        if after.closed_trade_count != before.closed_trade_count + 1:
            raise ValueError("R22 sale must account for its closed-trade outcome")
        if outcome_evidence_identity is None or outcome_evidence_identity not in after.source_record_identities:
            raise ValueError("R22 sale requires explicit outcome evidence")

    costs = fill.costs
    if (
        after.fee_usdt - before.fee_usdt != costs.fee_usdt
        or after.spread_usdt - before.spread_usdt != costs.spread_usdt
        or after.slippage_usdt - before.slippage_usdt != costs.slippage_usdt
    ):
        raise ValueError("R22 cumulative execution costs must reconcile")
    notional = fill.quantity * fill.simulated_fill_price
    if after.turnover_notional_usdt - before.turnover_notional_usdt != notional:
        raise ValueError("R22 turnover must reconcile to simulated fill notional")
    before_qty = next(
        (position.quantity for position in before.positions if position.symbol is intent.symbol),
        Decimal(0),
    )
    after_qty = next(
        (position.quantity for position in after.positions if position.symbol is intent.symbol),
        Decimal(0),
    )
    if intent.action is PaperAction.BUY:
        if after_qty != before_qty + intent.quantity:
            raise ValueError("R22 BUY position quantity mismatch")
        expected_cash = before.cash_usdt - notional - costs.fee_usdt
    else:
        if before_qty < intent.quantity or after_qty != before_qty - intent.quantity:
            raise ValueError("R22 sale position quantity mismatch")
        if intent.action is PaperAction.EXIT and after_qty != 0:
            raise ValueError("R22 EXIT must flatten the specified symbol")
        expected_cash = before.cash_usdt + notional - costs.fee_usdt
    if after.cash_usdt != expected_cash:
        raise ValueError("R22 cash movement does not match fill and fee")
    before_other = tuple(p for p in before.positions if p.symbol is not intent.symbol)
    after_other = tuple(p for p in after.positions if p.symbol is not intent.symbol)
    if before_other != after_other:
        raise ValueError("R22 one-fill audit cannot conceal another symbol mutation")
    realized_delta = after.realized_pnl_usdt - before.realized_pnl_usdt
    unrealized_delta = after.unrealized_pnl_usdt - before.unrealized_pnl_usdt
    if after.nav_usdt - before.nav_usdt != realized_delta + unrealized_delta:
        raise ValueError("R22 NAV delta cannot hide unexplained PnL")

    payload: dict[str, object] = {
        "intent_identity": intent.intent_identity,
        "activation_identity": intent.activation_identity,
        "vault_id": intent.vault_id,
        "action": intent.action,
        "symbol": intent.symbol,
        "source_fill_identity": fill.record_identity,
        "mutation_identity": mutation.record_identity,
        "filled_at_ms": fill.filled_at_ms,
        "mutated_at_ms": mutation.mutated_at_ms,
        "snapshot_at_ms": after.snapshot_at_ms,
        "before_snapshot_identity": before.snapshot_identity,
        "after_snapshot_identity": after.snapshot_identity,
        "previous_fill_identity": previous_fill_identity,
        "quantity": fill.quantity,
        "reference_price": fill.reference_price,
        "simulated_fill_price": fill.simulated_fill_price,
        "notional_usdt": notional,
        "fee_usdt": costs.fee_usdt,
        "spread_usdt": costs.spread_usdt,
        "slippage_usdt": costs.slippage_usdt,
        "execution_policy_version": costs.execution_policy_version,
        "venue_reference": fill.venue_reference,
        "cash_before_usdt": before.cash_usdt,
        "cash_after_usdt": after.cash_usdt,
        "position_before_quantity": before_qty,
        "position_after_quantity": after_qty,
        "nav_before_usdt": before.nav_usdt,
        "nav_after_usdt": after.nav_usdt,
        "realized_pnl_delta_usdt": realized_delta,
        "unrealized_pnl_delta_usdt": unrealized_delta,
        "mark_evidence_identity": mark_evidence_identity,
        "outcome_evidence_identity": outcome_evidence_identity,
        "schema_version": R22_SCHEMA_VERSION,
        "engine_version": R22_ENGINE_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return PaperTapeFill(fill_identity=canonical_sha256(payload), **payload)  # type: ignore[arg-type]


class R22DevelopmentTape:
    """Isolated append-only SQLite evidence; never opens the R21 or Epoch1 DB."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            for table, identity in (
                ("r22_intents", "intent_identity"),
                ("r22_fills", "fill_identity"),
            ):
                connection.execute(
                    f"""CREATE TABLE IF NOT EXISTS {table} (
                        {identity} TEXT PRIMARY KEY,
                        activation_identity TEXT NOT NULL,
                        vault_id TEXT NOT NULL,
                        event_at_ms INTEGER NOT NULL,
                        payload_json TEXT NOT NULL
                    )"""
                )
                for action in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'immutable R22 development tape'); END"""
                    )

    def append_intent(self, intent: PaperTapeIntent) -> bool:
        self.initialize()
        payload = canonical_json(_payload(intent))
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT payload_json FROM r22_intents WHERE intent_identity = ?",
                (intent.intent_identity,),
            ).fetchone()
            if old is not None:
                if old[0] != payload:
                    raise ValueError("R22 intent identity conflict")
                return False
            last = db.execute(
                """SELECT intent_identity, event_at_ms FROM r22_intents
                WHERE vault_id = ? ORDER BY event_at_ms DESC, intent_identity DESC LIMIT 1""",
                (intent.vault_id.value,),
            ).fetchone()
            expected = None if last is None else str(last[0])
            if intent.previous_intent_identity != expected:
                raise ValueError("R22 stale or forked intent predecessor")
            if last is not None and intent.decided_at_ms <= int(last[1]):
                raise ValueError("R22 intent cannot backfill or fork timestamp")
            db.execute(
                "INSERT INTO r22_intents VALUES (?, ?, ?, ?, ?)",
                (
                    intent.intent_identity, intent.activation_identity,
                    intent.vault_id.value, intent.decided_at_ms, payload,
                ),
            )
        return True

    def append_fill(self, fill: PaperTapeFill) -> bool:
        self.initialize()
        payload = canonical_json(_payload(fill))
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT payload_json FROM r22_fills WHERE fill_identity = ?",
                (fill.fill_identity,),
            ).fetchone()
            if old is not None:
                if old[0] != payload:
                    raise ValueError("R22 fill identity conflict")
                return False
            row = db.execute(
                "SELECT payload_json FROM r22_intents WHERE intent_identity = ?",
                (fill.intent_identity,),
            ).fetchone()
            if row is None:
                raise ValueError("R22 fill cannot precede its recorded decision")
            intent_payload = json.loads(str(row[0]))
            if (
                intent_payload["activation_identity"] != fill.activation_identity
                or intent_payload["vault_id"] != fill.vault_id.value
                or intent_payload["action"] != fill.action.value
                or intent_payload["symbol"] != fill.symbol.value
                or intent_payload["decided_at_ms"] > fill.filled_at_ms
            ):
                raise ValueError("R22 persisted intent and fill do not match")
            last = db.execute(
                """SELECT fill_identity, event_at_ms FROM r22_fills
                WHERE vault_id = ? ORDER BY event_at_ms DESC, fill_identity DESC LIMIT 1""",
                (fill.vault_id.value,),
            ).fetchone()
            expected = None if last is None else str(last[0])
            if fill.previous_fill_identity != expected:
                raise ValueError("R22 stale or forked fill predecessor")
            if last is not None and fill.filled_at_ms <= int(last[1]):
                raise ValueError("R22 fill cannot backfill or fork timestamp")
            db.execute(
                "INSERT INTO r22_fills VALUES (?, ?, ?, ?, ?)",
                (
                    fill.fill_identity, fill.activation_identity,
                    fill.vault_id.value, fill.filled_at_ms, payload,
                ),
            )
        return True

    def verify_read_only(self) -> tuple[int, int]:
        """Detect stored-payload tampering without mutating either ledger."""
        if not self.path.is_file():
            raise ValueError("R22 tape missing")
        counts: list[int] = []
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            for table, identity in (
                ("r22_intents", "intent_identity"),
                ("r22_fills", "fill_identity"),
            ):
                rows = db.execute(
                    f"SELECT {identity}, payload_json FROM {table} ORDER BY event_at_ms"
                ).fetchall()
                for recorded_identity, payload in rows:
                    if sha256_text(str(payload)) != str(recorded_identity):
                        raise ValueError("R22 persisted tape payload digest mismatch")
                    raw = json.loads(str(payload))
                    if raw["real_capital"] != 0 or raw["production_authority"]:
                        raise ValueError("R22 persisted authority boundary mismatch")
                counts.append(len(rows))
        return counts[0], counts[1]
