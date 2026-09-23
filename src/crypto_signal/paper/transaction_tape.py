"""R22 Slice 1: immutable, development-only Epoch 2 decision and transaction audit.

This module is evidence, not a paper execution engine. It neither mutates the
accepted R21 ledger nor authorizes live/paper orders. The separate SQLite tape
is an isolated development artifact until cross-ledger atomicity is accepted.
REAL_CAPITAL=0.
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
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.product.decision_proof import DecisionProofSnapshot

R22_SCHEMA_VERSION = "r22-transaction-decision-tape-v1/1"
R22_ENGINE_VERSION = "r22-transaction-decision-tape-slice1/1"


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
    sizing_decision_identity: str | None
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
        for identity, label in (
            (self.intent_identity, "intent"),
            (self.activation_identity, "activation"),
            (self.policy_identity, "policy"),
        ):
            _sha(identity, label)
        for identity, label in (
            (self.forecast_identity, "forecast"),
            (self.proof_identity, "proof"),
            (self.signal_freeze_identity, "signal"),
            (self.sizing_decision_identity, "sizing"),
            (self.previous_intent_identity, "previous intent"),
        ):
            _sha(identity, label, optional=True)
        if self.schema_version != R22_SCHEMA_VERSION or self.engine_version != R22_ENGINE_VERSION:
            raise ValueError("unsupported R22 version")
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
        if self.action is PaperAction.HOLD_CASH:
            if any(item is not None for item in (
                self.forecast_identity, self.proof_identity,
                self.signal_freeze_identity, self.sizing_decision_identity,
                self.symbol, self.quantity, self.reference_price,
            )):
                raise ValueError("R22 HOLD_CASH cannot invent a trade or forecast")
        else:
            if None in (
                self.forecast_identity, self.proof_identity,
                self.signal_freeze_identity, self.sizing_decision_identity,
            ):
                raise ValueError("R22 trade decision requires complete evidence lineage")
            if self.symbol is None or self.quantity is None or self.reference_price is None:
                raise ValueError("R22 trade decision requires symbol, quantity, price")
            if not isinstance(self.symbol, PaperSymbol):
                raise ValueError("R22 trade symbol must be permitted")
            _money(self.quantity, "decision quantity", positive=True)
            _money(self.reference_price, "decision reference price", positive=True)
            if not self.source_evidence_identities:
                raise ValueError("R22 trade decision requires source evidence")
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
    filled_at_ms: int
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
        for value, label in (
            (self.fill_identity, "fill"), (self.intent_identity, "intent"),
            (self.activation_identity, "activation"),
            (self.before_snapshot_identity, "before snapshot"),
            (self.after_snapshot_identity, "after snapshot"),
            (self.mark_evidence_identity, "mark evidence"),
        ):
            _sha(value, label)
        _sha(self.previous_fill_identity, "previous fill", optional=True)
        _sha(self.outcome_evidence_identity, "outcome", optional=True)
        if self.schema_version != R22_SCHEMA_VERSION or self.engine_version != R22_ENGINE_VERSION:
            raise ValueError("unsupported R22 fill version")
        if not isinstance(self.vault_id, PaperVaultId) or not isinstance(self.symbol, PaperSymbol):
            raise TypeError("R22 fill requires valid vault and symbol")
        if self.action not in (PaperAction.BUY, PaperAction.REDUCE, PaperAction.EXIT):
            raise ValueError("HOLD_CASH cannot create a fill")
        if min(self.filled_at_ms, self.snapshot_at_ms) < 0:
            raise ValueError("R22 fill times cannot be negative")
        if self.filled_at_ms > self.snapshot_at_ms:
            raise ValueError("R22 fill cannot occur after bound R21 snapshot")
        for value, label in (
            (self.quantity, "quantity"), (self.reference_price, "reference price"),
            (self.simulated_fill_price, "simulated fill price"),
        ):
            _money(value, label, positive=True)
        for value, label in (
            (self.notional_usdt, "notional"), (self.fee_usdt, "fee"),
            (self.spread_usdt, "spread"), (self.slippage_usdt, "slippage"),
            (self.cash_before_usdt, "cash before"), (self.cash_after_usdt, "cash after"),
            (self.position_before_quantity, "quantity before"),
            (self.position_after_quantity, "quantity after"),
            (self.nav_before_usdt, "NAV before"), (self.nav_after_usdt, "NAV after"),
        ):
            _money(value, label)
        if self.notional_usdt != self.quantity * self.simulated_fill_price:
            raise ValueError("R22 notional must use simulated fill price")
        if self.action is PaperAction.BUY and self.simulated_fill_price < self.reference_price:
            raise ValueError("R22 BUY cannot claim adverse execution improvement")
        if self.action is not PaperAction.BUY and self.simulated_fill_price > self.reference_price:
            raise ValueError("R22 sale cannot claim adverse execution improvement")
        price_impact = abs(self.simulated_fill_price - self.reference_price) * self.quantity
        if self.spread_usdt + self.slippage_usdt != price_impact:
            raise ValueError("R22 execution impact cannot be double-counted")
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
    policy_identity: str,
    reason_codes: tuple[str, ...],
    forecast: ImmutableForecast | None = None,
    proof: DecisionProofSnapshot | None = None,
    sizing_decision_identity: str | None = None,
    symbol: PaperSymbol | None = None,
    quantity: Decimal | None = None,
    reference_price: Decimal | None = None,
    previous_intent_identity: str | None = None,
) -> PaperTapeIntent:
    if decided_at_ms < activation.activated_at_ms:
        raise ValueError("R22 intent cannot predate Epoch2 activation")
    if action is PaperAction.HOLD_CASH:
        if forecast is not None or proof is not None:
            raise ValueError("R22 HOLD_CASH must have no trade forecast")
        evidence: tuple[str, ...] = ()
    else:
        if forecast is None or proof is None:
            raise ValueError("R22 trade requires exact R20 forecast and Decision Proof")
        if (
            forecast.forecast_identity != proof.forecast_identity
            or forecast.signal_freeze_identity != proof.signal_freeze_identity
            or forecast.issued_at_ms != proof.issued_at_ms
            or forecast.symbol != proof.symbol
            or forecast.source_as_of_ms != proof.source_as_of_ms
        ):
            raise ValueError("R22 forecast and proof lineage mismatch")
        if decided_at_ms < forecast.issued_at_ms:
            raise ValueError("R22 decision cannot precede immutable forecast")
        if symbol is None or symbol.value != forecast.symbol:
            raise ValueError("R22 symbol must match exact forecast")
        if not proof.read_only or proof.production_authority:
            raise ValueError("R22 proof must preserve read-only authority")
        evidence = forecast.source_evidence_identities
    payload: dict[str, object] = {
        "activation_identity": activation.activation_identity,
        "vault_id": vault_id,
        "forecast_identity": None if forecast is None else forecast.forecast_identity,
        "proof_identity": None if proof is None else proof.proof_identity,
        "signal_freeze_identity": None if forecast is None else forecast.signal_freeze_identity,
        "policy_identity": policy_identity,
        "sizing_decision_identity": sizing_decision_identity,
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
    filled_at_ms: int,
    simulated_fill_price: Decimal,
    fee_usdt: Decimal,
    spread_usdt: Decimal,
    slippage_usdt: Decimal,
    mark_evidence_identity: str,
    outcome_evidence_identity: str | None = None,
    previous_fill_identity: str | None = None,
) -> PaperTapeFill:
    if intent.action is PaperAction.HOLD_CASH or intent.symbol is None:
        raise ValueError("R22 HOLD_CASH cannot create a capital mutation")
    if intent.quantity is None or intent.reference_price is None:
        raise ValueError("R22 fill requires exact prior quantity and reference price")
    if before.activation_identity != intent.activation_identity or after.activation_identity != intent.activation_identity:
        raise ValueError("R22 fill activation mismatch")
    if before.vault_id is not intent.vault_id or after.vault_id is not intent.vault_id:
        raise ValueError("R22 fill cannot cross vaults")
    if after.previous_snapshot_identity != before.snapshot_identity:
        raise ValueError("R22 fill requires exact R21 previous snapshot")
    if not (before.snapshot_at_ms < filled_at_ms <= after.snapshot_at_ms):
        raise ValueError("R22 fill must follow previous accounting and decision")
    if filled_at_ms < intent.decided_at_ms:
        raise ValueError("R22 fill predates immutable decision")
    if intent.intent_identity not in after.source_record_identities:
        raise ValueError("R22 R21 after-snapshot must cite the exact frozen intent")
    if mark_evidence_identity not in after.source_record_identities:
        raise ValueError("R22 R21 after-snapshot requires exact mark evidence")
    if intent.action is PaperAction.BUY and after.closed_trade_count != before.closed_trade_count:
        raise ValueError("R22 BUY cannot report a closed trade")
    if intent.action in (PaperAction.REDUCE, PaperAction.EXIT):
        if after.closed_trade_count != before.closed_trade_count + 1:
            raise ValueError("R22 sale must account for its closed-trade outcome")
        if outcome_evidence_identity is None or outcome_evidence_identity not in after.source_record_identities:
            raise ValueError("R22 sale requires explicit outcome evidence")
    if (
        after.fee_usdt - before.fee_usdt != fee_usdt
        or after.spread_usdt - before.spread_usdt != spread_usdt
        or after.slippage_usdt - before.slippage_usdt != slippage_usdt
    ):
        raise ValueError("R22 cumulative execution costs must reconcile")
    notional = intent.quantity * simulated_fill_price
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
        expected_cash = before.cash_usdt - notional - fee_usdt
    else:
        if before_qty < intent.quantity or after_qty != before_qty - intent.quantity:
            raise ValueError("R22 sale position quantity mismatch")
        if intent.action is PaperAction.EXIT and after_qty != 0:
            raise ValueError("R22 EXIT must flatten the specified symbol")
        expected_cash = before.cash_usdt + notional - fee_usdt
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
        "filled_at_ms": filled_at_ms,
        "snapshot_at_ms": after.snapshot_at_ms,
        "before_snapshot_identity": before.snapshot_identity,
        "after_snapshot_identity": after.snapshot_identity,
        "previous_fill_identity": previous_fill_identity,
        "quantity": intent.quantity,
        "reference_price": intent.reference_price,
        "simulated_fill_price": simulated_fill_price,
        "notional_usdt": notional,
        "fee_usdt": fee_usdt,
        "spread_usdt": spread_usdt,
        "slippage_usdt": slippage_usdt,
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
