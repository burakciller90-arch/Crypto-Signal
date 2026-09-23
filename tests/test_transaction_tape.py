from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_decision_proof_live_feed import ISSUED_AT, _forecast, _slices
from test_position_sizing_intelligence import (
    _context as sizing_context,
    _vault as sizing_vault,
)

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    build_epoch2_activation_record,
    build_epoch2_vault_accounting_snapshot,
    build_initial_epoch2_vault_snapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import (
    ExecutionCostAssumptions,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    build_decision_intent,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.position_sizing_intelligence import (
    SizingMethod,
    build_position_sizing_policy,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.transaction_tape import (
    R22DevelopmentTape,
    build_tape_fill,
    build_tape_intent,
)
from crypto_signal.product.decision_proof import build_decision_proof_snapshot


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _sizing(fraction: str = "0.25"):
    policy = build_position_sizing_policy(
        policy_version=f"r22-test-sizing-{fraction}",
        fixed_fraction_of_vault=Decimal(fraction),
        maximum_fraction_of_vault=Decimal("0.25"),
        maximum_absolute_correlation=Decimal("0.70"),
        maximum_drawdown_fraction=Decimal("0.20"),
        maximum_volatility_fraction=Decimal("0.25"),
        minimum_liquidity_score_0_1=Decimal("0.60"),
        maximum_transaction_cost_r=Decimal("0.20"),
    )
    assessment = evaluate_position_sizing_intelligence(
        policy=policy,
        vault=sizing_vault(),
        context=sizing_context(),
    )
    result = next(
        item for item in assessment.results if item.method is SizingMethod.FIXED_FRACTIONAL
    )
    return assessment, result


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
    sizing_assessment, sizing_result = _sizing()
    decision = build_decision_intent(
        fund_identity=activation.activation_identity,
        decided_at_ms=ISSUED_AT + 100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        reason="R22 accepted forecast",
        invalidation_context="exact R20 invalidation",
    )
    intent = build_tape_intent(
        activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.BUY,
        decided_at_ms=decision.decided_at_ms,
        reason_codes=("forecast_active",),
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=decision,
    )
    costs = ExecutionCostAssumptions(
        fee_usdt=Decimal(1),
        spread_usdt=Decimal("0.4"),
        slippage_usdt=Decimal("0.6"),
    )
    source_fill = build_simulated_fill(
        fund_identity=activation.activation_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=ISSUED_AT + 200,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        simulated_fill_price=Decimal(101),
        costs=costs,
        venue_reference="r22-test-venue",
    )
    mutation = build_position_cash_mutation(
        fund_identity=activation.activation_identity,
        source_identity=source_fill.record_identity,
        mutated_at_ms=ISSUED_AT + 210,
        cash_before_usdt=Decimal(600),
        cash_after_usdt=Decimal(498),
        positions_before=(),
        positions_after=(PaperPosition(PaperSymbol.BTCUSDT, Decimal(1)),),
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
        source_record_identities=(
            intent.intent_identity,
            source_fill.record_identity,
            mutation.record_identity,
            mark,
        ),
        previous=before,
    )
    tape_fill = build_tape_fill(
        intent,
        before,
        after,
        fill=source_fill,
        mutation=mutation,
        mark_evidence_identity=mark,
    )
    return (
        activation,
        before,
        forecast,
        proof,
        sizing_assessment,
        sizing_result,
        decision,
        intent,
        source_fill,
        mutation,
        after,
        tape_fill,
    )


def test_r22_exact_forecast_sizing_decision_fill_to_r21_lineage() -> None:
    (
        activation,
        before,
        _,
        _,
        sizing_assessment,
        sizing_result,
        decision,
        intent,
        source_fill,
        mutation,
        after,
        fill,
    ) = _buy()
    assert intent.activation_identity == activation.activation_identity
    assert intent.sizing_assessment_identity == sizing_assessment.assessment_identity
    assert intent.sizing_decision_identity == sizing_result.result_identity
    assert intent.decision_identity == decision.record_identity
    assert fill.source_fill_identity == source_fill.record_identity
    assert fill.mutation_identity == mutation.record_identity
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


def test_r22_rejects_mismatched_forecast_proof_sizing_or_decision() -> None:
    activation, _, forecast, proof = _context()
    sizing_assessment, sizing_result = _sizing()
    decision = build_decision_intent(
        fund_identity=activation.activation_identity,
        decided_at_ms=ISSUED_AT + 100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        reason="candidate",
        invalidation_context="candidate invalidation",
    )
    common = {
        "vault_id": PaperVaultId.CORE,
        "action": PaperAction.BUY,
        "decided_at_ms": decision.decided_at_ms,
        "reason_codes": ("active",),
        "forecast": forecast,
        "sizing_assessment": sizing_assessment,
        "sizing_result": sizing_result,
        "decision": decision,
    }

    other_forecast = _forecast(calibrated=True)
    other_proof = build_decision_proof_snapshot(other_forecast, _slices(other_forecast))
    with pytest.raises(ValueError, match="lineage mismatch"):
        build_tape_intent(activation, proof=other_proof, **common)

    _, wrong_result = _sizing("0.20")
    with pytest.raises(ValueError, match="does not belong"):
        build_tape_intent(
            activation,
            proof=proof,
            **{**common, "sizing_result": wrong_result},
        )

    wrong_symbol_decision = build_decision_intent(
        fund_identity=activation.activation_identity,
        decided_at_ms=decision.decided_at_ms,
        action=PaperAction.BUY,
        symbol=PaperSymbol.ETHUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        reason="wrong symbol",
        invalidation_context="wrong symbol invalidation",
    )
    with pytest.raises(ValueError, match="symbol must match"):
        build_tape_intent(
            activation,
            proof=proof,
            **{**common, "decision": wrong_symbol_decision},
        )

    early = build_decision_intent(
        fund_identity=activation.activation_identity,
        decided_at_ms=ISSUED_AT - 1,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        reason="too early",
        invalidation_context="too early invalidation",
    )
    with pytest.raises(ValueError, match="cannot precede"):
        build_tape_intent(
            activation,
            proof=proof,
            **{
                **common,
                "decided_at_ms": early.decided_at_ms,
                "decision": early,
            },
        )


def test_r22_rejects_untraced_fill_mutation_or_execution_costs() -> None:
    (
        activation,
        before,
        _,
        _,
        _,
        _,
        decision,
        intent,
        source_fill,
        mutation,
        after,
        _,
    ) = _buy()

    other_fill = build_simulated_fill(
        fund_identity=activation.activation_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=source_fill.filled_at_ms,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        simulated_fill_price=Decimal(101),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.5"),
            slippage_usdt=Decimal("0.5"),
        ),
        venue_reference="r22-test-venue",
    )
    with pytest.raises(ValueError, match="sourced from exact"):
        build_tape_fill(
            intent,
            before,
            after,
            fill=other_fill,
            mutation=mutation,
            mark_evidence_identity=_sha("mark-after-buy"),
        )

    bad_mutation = build_position_cash_mutation(
        fund_identity=activation.activation_identity,
        source_identity=source_fill.record_identity,
        mutated_at_ms=mutation.mutated_at_ms,
        cash_before_usdt=Decimal(600),
        cash_after_usdt=Decimal(497),
        positions_before=(),
        positions_after=(PaperPosition(PaperSymbol.BTCUSDT, Decimal(1)),),
    )
    with pytest.raises(ValueError, match="does not reconcile"):
        build_tape_fill(
            intent,
            before,
            after,
            fill=source_fill,
            mutation=bad_mutation,
            mark_evidence_identity=_sha("mark-after-buy"),
        )


def test_r22_sell_requires_outcome_and_reconciles_realized_nav() -> None:
    (
        activation,
        _,
        forecast,
        proof,
        sizing_assessment,
        sizing_result,
        _,
        buy_intent,
        _,
        _,
        after_buy,
        buy_fill,
    ) = _buy()
    exit_decision = build_decision_intent(
        fund_identity=activation.activation_identity,
        decided_at_ms=ISSUED_AT + 400,
        action=PaperAction.EXIT,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(109),
        reason="exit condition",
        invalidation_context="position closed",
    )
    sale = build_tape_intent(
        activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.EXIT,
        decided_at_ms=exit_decision.decided_at_ms,
        forecast=forecast,
        proof=proof,
        sizing_assessment=sizing_assessment,
        sizing_result=sizing_result,
        decision=exit_decision,
        reason_codes=("exit_condition",),
        previous_intent_identity=buy_intent.intent_identity,
    )
    source_fill = build_simulated_fill(
        fund_identity=activation.activation_identity,
        decision_identity=exit_decision.record_identity,
        filled_at_ms=ISSUED_AT + 600,
        action=PaperAction.EXIT,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(109),
        simulated_fill_price=Decimal(108),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.4"),
            slippage_usdt=Decimal("0.6"),
        ),
        venue_reference="r22-test-venue",
    )
    mutation = build_position_cash_mutation(
        fund_identity=activation.activation_identity,
        source_identity=source_fill.record_identity,
        mutated_at_ms=ISSUED_AT + 610,
        cash_before_usdt=Decimal(498),
        cash_after_usdt=Decimal(605),
        positions_before=(PaperPosition(PaperSymbol.BTCUSDT, Decimal(1)),),
        positions_after=(),
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
        source_record_identities=(
            sale.intent_identity,
            source_fill.record_identity,
            mutation.record_identity,
            mark,
            outcome,
        ),
        previous=after_buy,
    )
    with pytest.raises(ValueError, match="outcome evidence"):
        build_tape_fill(
            sale,
            after_buy,
            after_sale,
            fill=source_fill,
            mutation=mutation,
            mark_evidence_identity=mark,
            previous_fill_identity=buy_fill.fill_identity,
        )
    fill = build_tape_fill(
        sale,
        after_buy,
        after_sale,
        fill=source_fill,
        mutation=mutation,
        mark_evidence_identity=mark,
        outcome_evidence_identity=outcome,
        previous_fill_identity=buy_fill.fill_identity,
    )
    assert fill.position_after_quantity == 0
    assert fill.nav_after_usdt - fill.nav_before_usdt == Decimal(7)
    assert fill.realized_pnl_delta_usdt == 5
    assert fill.unrealized_pnl_delta_usdt == 2


def test_r22_hold_cash_has_no_fill_and_no_fabricated_trade_lineage() -> None:
    activation, before, _, _ = _context()
    hold = build_tape_intent(
        activation,
        vault_id=PaperVaultId.TACTICAL,
        action=PaperAction.HOLD_CASH,
        decided_at_ms=ISSUED_AT + 10,
        hold_policy_identity=_sha("hold-policy"),
        reason_codes=("event_block",),
    )
    assert hold.forecast_identity is None
    assert hold.sizing_assessment_identity is None
    assert hold.decision_identity is None
    assert hold.quantity is None

    *_, source_fill, mutation, _, _ = _buy()
    with pytest.raises(ValueError, match="cannot create"):
        build_tape_fill(
            hold,
            before,
            before,
            fill=source_fill,
            mutation=mutation,
            mark_evidence_identity=_sha("mark"),
        )


def test_r22_isolated_tape_is_immutable_idempotent_and_hash_checked(
    tmp_path: Path,
) -> None:
    data = _buy()
    intent = data[7]
    fill = data[11]
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
