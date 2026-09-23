from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest
from test_decision_proof_live_feed import ISSUED_AT, _forecast, _slices

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    build_epoch2_activation_record,
    build_epoch2_vault_accounting_snapshot,
    build_initial_epoch2_vault_snapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperPosition, PaperSymbol
from crypto_signal.paper.transaction_tape import (
    R22DevelopmentTape,
    build_tape_fill,
    build_tape_intent,
)
from crypto_signal.product.decision_proof import build_decision_proof_snapshot


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _context():
    activation = build_epoch2_activation_record(
        activated_at_ms=1000,
        epoch1_ledger_sha256=_sha("immutable-epoch1"),
    )
    before = build_initial_epoch2_vault_snapshot(activation, PaperVaultId.CORE)
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    return activation, before, forecast, proof


def _buy():
    activation, before, forecast, proof = _context()
    intent = build_tape_intent(
        activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.BUY,
        decided_at_ms=ISSUED_AT + 100,
        policy_identity=_sha("accepted-paper-policy"),
        sizing_decision_identity=_sha("sizing-decision"),
        reason_codes=("forecast_active",),
        forecast=forecast,
        proof=proof,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
    )
    mark = _sha("mark-after-buy")
    after = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=ISSUED_AT + 300,
        cash_usdt=Decimal(498),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal(1)),),
        marked_exposure_usdt=Decimal(100),
        realized_pnl_usdt=Decimal(0),
        unrealized_pnl_usdt=Decimal(-2),
        fee_usdt=Decimal(1),
        spread_usdt=Decimal("0.4"),
        slippage_usdt=Decimal("0.6"),
        turnover_notional_usdt=Decimal(101),
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(),
        source_record_identities=(intent.intent_identity, mark),
        previous=before,
    )
    fill = build_tape_fill(
        intent, before, after,
        filled_at_ms=ISSUED_AT + 200,
        simulated_fill_price=Decimal(101),
        fee_usdt=Decimal(1),
        spread_usdt=Decimal("0.4"),
        slippage_usdt=Decimal("0.6"),
        mark_evidence_identity=mark,
    )
    return activation, before, forecast, proof, intent, after, fill


def test_r22_exact_forecast_proof_to_r21_cash_position_nav_lineage() -> None:
    activation, before, _, _, intent, after, fill = _buy()
    assert fill.activation_identity == activation.activation_identity
    assert fill.intent_identity == intent.intent_identity
    assert fill.before_snapshot_identity == before.snapshot_identity
    assert fill.after_snapshot_identity == after.snapshot_identity
    assert fill.cash_before_usdt == Decimal(600)
    assert fill.cash_after_usdt == Decimal(498)
    assert fill.nav_before_usdt == Decimal(600)
    assert fill.nav_after_usdt == Decimal(598)
    assert fill.unrealized_pnl_delta_usdt == Decimal(-2)
    assert fill.notional_usdt == Decimal(101)
    assert fill.spread_usdt + fill.slippage_usdt == Decimal(1)
    assert fill.real_capital == 0 and not fill.production_authority
    assert intent.real_capital == 0 and not intent.production_authority


def test_r22_forecast_and_proof_are_exact_not_user_claimed() -> None:
    activation, _, forecast, proof = _context()
    args = {
        "vault_id": PaperVaultId.CORE,
        "action": PaperAction.BUY,
        "decided_at_ms": ISSUED_AT + 100,
        "policy_identity": _sha("policy"),
        "sizing_decision_identity": _sha("sizing"),
        "reason_codes": ("active",),
        "forecast": forecast,
        "symbol": PaperSymbol.BTCUSDT,
        "quantity": Decimal(1),
        "reference_price": Decimal(100),
    }
    other_forecast = _forecast(calibrated=True)
    other_proof = build_decision_proof_snapshot(other_forecast, _slices(other_forecast))
    with pytest.raises(ValueError, match="lineage mismatch"):
        build_tape_intent(activation, proof=other_proof, **args)
    # A valid Decision Proof from another immutable forecast cannot be substituted.
    with pytest.raises(ValueError, match="decision cannot precede"):
        build_tape_intent(
            activation, proof=proof, **{**args, "decided_at_ms": ISSUED_AT - 1}
        )
    with pytest.raises(ValueError, match="symbol must match"):
        build_tape_intent(
            activation, proof=proof, **{**args, "symbol": PaperSymbol.ETHUSDT}
        )


def test_r22_rejects_nonreconciling_cash_cost_position_or_missing_mark() -> None:
    activation, before, _, _, intent, after, _ = _buy()
    with pytest.raises(ValueError, match="cash movement"):
        bad = build_epoch2_vault_accounting_snapshot(
            activation,
            vault_id=PaperVaultId.CORE,
            snapshot_at_ms=after.snapshot_at_ms,
            cash_usdt=Decimal(497),
            positions=after.positions,
            marked_exposure_usdt=Decimal(100),
            realized_pnl_usdt=Decimal(0),
            unrealized_pnl_usdt=Decimal(-3),
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.4"),
            slippage_usdt=Decimal("0.6"),
            turnover_notional_usdt=Decimal(101),
            closed_trade_count=0,
            win_count=0,
            loss_count=0,
            breakeven_count=0,
            outcome_distribution=(),
            source_record_identities=after.source_record_identities,
            previous=before,
        )
        build_tape_fill(
            intent, before, bad,
            filled_at_ms=ISSUED_AT + 200,
            simulated_fill_price=Decimal(101),
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.4"),
            slippage_usdt=Decimal("0.6"),
            mark_evidence_identity=_sha("mark-after-buy"),
        )
    with pytest.raises(ValueError, match="execution costs"):
        build_tape_fill(
            intent, before, after,
            filled_at_ms=ISSUED_AT + 200,
            simulated_fill_price=Decimal(101),
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.5"),
            slippage_usdt=Decimal("0.5"),
            mark_evidence_identity=_sha("mark-after-buy"),
        )
    with pytest.raises(ValueError, match="mark evidence"):
        build_tape_fill(
            intent, before, after,
            filled_at_ms=ISSUED_AT + 200,
            simulated_fill_price=Decimal(101),
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.4"),
            slippage_usdt=Decimal("0.6"),
            mark_evidence_identity=_sha("invented-mark"),
        )


def test_r22_sell_requires_outcome_and_reconciles_realized_nav() -> None:
    activation, _, forecast, proof, buy_intent, after_buy, buy_fill = _buy()
    sale = build_tape_intent(
        activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.EXIT,
        decided_at_ms=ISSUED_AT + 400,
        policy_identity=_sha("paper-exit-policy"),
        sizing_decision_identity=_sha("exit-sizing"),
        forecast=forecast,
        proof=proof,
        reason_codes=("exit_condition",),
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(109),
        previous_intent_identity=buy_intent.intent_identity,
    )
    mark, outcome = _sha("mark-after-exit"), _sha("closed-trade-win")
    after_sale = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=ISSUED_AT + 700,
        cash_usdt=Decimal(605),
        positions=(),
        marked_exposure_usdt=Decimal(0),
        realized_pnl_usdt=Decimal(5),
        unrealized_pnl_usdt=Decimal(0),
        fee_usdt=Decimal(2),
        spread_usdt=Decimal("0.8"),
        slippage_usdt=Decimal("1.2"),
        turnover_notional_usdt=Decimal(209),
        closed_trade_count=1,
        win_count=1,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(("WIN", 1),),
        source_record_identities=(sale.intent_identity, mark, outcome),
        previous=after_buy,
    )
    with pytest.raises(ValueError, match="outcome evidence"):
        build_tape_fill(
            sale, after_buy, after_sale,
            filled_at_ms=ISSUED_AT + 600,
            simulated_fill_price=Decimal(108),
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.4"),
            slippage_usdt=Decimal("0.6"),
            mark_evidence_identity=mark,
            previous_fill_identity=buy_fill.fill_identity,
        )
    fill = build_tape_fill(
        sale, after_buy, after_sale,
        filled_at_ms=ISSUED_AT + 600,
        simulated_fill_price=Decimal(108),
        fee_usdt=Decimal(1),
        spread_usdt=Decimal("0.4"),
        slippage_usdt=Decimal("0.6"),
        mark_evidence_identity=mark,
        outcome_evidence_identity=outcome,
        previous_fill_identity=buy_fill.fill_identity,
    )
    assert fill.position_after_quantity == 0
    assert fill.nav_after_usdt - fill.nav_before_usdt == Decimal(7)
    assert fill.realized_pnl_delta_usdt == 5
    assert fill.unrealized_pnl_delta_usdt == 2


def test_r22_hold_cash_has_no_fill_and_no_fabricated_signal() -> None:
    activation, before, _, _ = _context()
    hold = build_tape_intent(
        activation,
        vault_id=PaperVaultId.TACTICAL,
        action=PaperAction.HOLD_CASH,
        decided_at_ms=ISSUED_AT + 10,
        policy_identity=_sha("hold-policy"),
        reason_codes=("event_block",),
    )
    assert hold.forecast_identity is None
    assert hold.quantity is None
    with pytest.raises(ValueError, match="cannot create"):
        build_tape_fill(
            hold, before, before,
            filled_at_ms=ISSUED_AT + 20,
            simulated_fill_price=Decimal(100),
            fee_usdt=Decimal(0),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
            mark_evidence_identity=_sha("mark"),
        )


def test_r22_isolated_tape_is_immutable_idempotent_and_hash_checked(tmp_path) -> None:
    _, _, _, _, intent, _, fill = _buy()
    path = tmp_path / "isolated_r22_development.sqlite3"
    tape = R22DevelopmentTape(path)
    assert tape.append_intent(intent)
    assert not tape.append_intent(intent)
    assert tape.append_fill(fill)
    assert not tape.append_fill(fill)
    assert tape.verify_read_only() == (1, 1)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="immutable R22"):
            db.execute("UPDATE r22_fills SET payload_json = 'tampered'")
        with pytest.raises(sqlite3.DatabaseError, match="immutable R22"):
            db.execute("DELETE FROM r22_intents")
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(intent, decided_at_ms=intent.decided_at_ms + 1)
