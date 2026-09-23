from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from test_decision_proof_live_feed import ISSUED_AT, _forecast, _slices
from test_transaction_tape import _sizing

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    Epoch2CanonicalLedger,
    Epoch2LedgerState,
    build_consolidated_epoch2_snapshot,
    build_epoch2_vault_accounting_snapshot,
    initialize_epoch2_canonical_fund,
)
from crypto_signal.paper.epochs import EPOCH_1_SPEC, EPOCH_2_SPEC, PaperVaultId
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    ExecutionCostAssumptions,
    PaperAction,
    PaperPosition,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.transaction_tape import build_tape_fill, build_tape_intent
from crypto_signal.paper.transaction_tape_atomic import (
    R22Epoch2AtomicTape,
    build_epoch2_accounting_bundle,
)
from crypto_signal.product.decision_proof import build_decision_proof_snapshot


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _initial_state(tmp_path: Path) -> tuple[Path, Epoch2LedgerState]:
    epoch1_path = tmp_path / EPOCH_1_SPEC.ledger_filename
    epoch1 = PaperFundLedger(epoch1_path)
    epoch1.append_fund_creation(build_fund_creation(created_at_ms=1))
    epoch2_path = tmp_path / EPOCH_2_SPEC.ledger_filename
    state = initialize_epoch2_canonical_fund(
        epoch1_ledger_path=epoch1_path,
        epoch2_ledger_path=epoch2_path,
        activated_at_ms=1000,
    )
    return epoch2_path, state


def _trade_bundle(tmp_path: Path):
    epoch2_path, before = _initial_state(tmp_path)
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    sizing_assessment, sizing_result = _sizing()
    decision = build_decision_intent(
        fund_identity=before.activation.activation_identity,
        decided_at_ms=ISSUED_AT + 100,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        reason="R22 canonical paper buy",
        invalidation_context="exact forecast invalidation",
    )
    intent = build_tape_intent(
        before.activation,
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
    source_fill = build_simulated_fill(
        fund_identity=before.activation.activation_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=ISSUED_AT + 200,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal(1),
        reference_price=Decimal(100),
        simulated_fill_price=Decimal(101),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal(1),
            spread_usdt=Decimal("0.4"),
            slippage_usdt=Decimal("0.6"),
        ),
        venue_reference="r22-atomic-test-venue",
    )
    mutation = build_position_cash_mutation(
        fund_identity=before.activation.activation_identity,
        source_identity=source_fill.record_identity,
        mutated_at_ms=ISSUED_AT + 210,
        cash_before_usdt=Decimal(600),
        cash_after_usdt=Decimal(498),
        positions_before=(),
        positions_after=(PaperPosition(PaperSymbol.BTCUSDT, Decimal(1)),),
    )
    mark = _sha("atomic-mark")
    snapshot_at = ISSUED_AT + 300
    by_vault = {item.vault_id: item for item in before.vault_snapshots}

    core = build_epoch2_vault_accounting_snapshot(
        before.activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=snapshot_at,
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
        previous=by_vault[PaperVaultId.CORE],
    )

    carry = []
    for vault_id in (PaperVaultId.TACTICAL, PaperVaultId.OPPORTUNITY_RESERVE):
        previous = by_vault[vault_id]
        carry.append(
            build_epoch2_vault_accounting_snapshot(
                before.activation,
                vault_id=vault_id,
                snapshot_at_ms=snapshot_at,
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

    after_vaults = (core, *carry)
    parent = build_consolidated_epoch2_snapshot(
        after_vaults,
        previous=before.consolidated_snapshot,
    )
    fill = build_tape_fill(
        intent,
        by_vault[PaperVaultId.CORE],
        core,
        fill=source_fill,
        mutation=mutation,
        mark_evidence_identity=mark,
    )
    bundle = build_epoch2_accounting_bundle(
        before,
        intent=intent,
        fill=fill,
        after_vaults=after_vaults,
        after_consolidated=parent,
    )
    return epoch2_path, before, intent, fill, after_vaults, parent, bundle


def test_r22_atomic_bundle_commits_tape_and_r21_accounting_together(
    tmp_path: Path,
) -> None:
    epoch2_path, before, intent, fill, after_vaults, parent, bundle = _trade_bundle(
        tmp_path
    )
    tape = R22Epoch2AtomicTape(epoch2_path)

    assert tape.append_accounting_bundle(
        before,
        intent=intent,
        fill=fill,
        after_vaults=after_vaults,
        after_consolidated=parent,
        bundle=bundle,
    )
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    assert state.consolidated_snapshot == parent
    assert tuple(sorted(item.snapshot_identity for item in state.vault_snapshots)) == (
        bundle.after_vault_snapshot_identities
    )
    audit = tape.audit_bundle_read_only(bundle.bundle_identity)
    assert audit["intent_identity"] == intent.intent_identity
    assert audit["fill_identity"] == fill.fill_identity
    assert audit["after_consolidated_snapshot_identity"] == parent.snapshot_identity
    assert audit["real_capital"] == 0
    assert audit["production_authority"] is False

    assert not tape.append_accounting_bundle(
        before,
        intent=intent,
        fill=fill,
        after_vaults=after_vaults,
        after_consolidated=parent,
        bundle=bundle,
    )


def test_r22_sqlite_failure_rolls_back_r21_and_r22_as_one_transaction(
    tmp_path: Path,
) -> None:
    epoch2_path, before, intent, fill, after_vaults, parent, bundle = _trade_bundle(
        tmp_path
    )
    tape = R22Epoch2AtomicTape(epoch2_path)
    tape.initialize()

    with sqlite3.connect(epoch2_path) as connection:
        connection.execute(
            """CREATE TRIGGER force_r22_fill_abort
            BEFORE INSERT ON r22_epoch2_fills
            BEGIN SELECT RAISE(ABORT, 'forced R22 rollback test'); END"""
        )

    with pytest.raises(sqlite3.DatabaseError, match="forced R22 rollback test"):
        tape.append_accounting_bundle(
            before,
            intent=intent,
            fill=fill,
            after_vaults=after_vaults,
            after_consolidated=parent,
            bundle=bundle,
        )

    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    assert state == before
    with sqlite3.connect(epoch2_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM r22_epoch2_intents"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM r22_epoch2_fills"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM r22_epoch2_bundles"
        ).fetchone() == (0,)


def test_r22_bundle_refuses_hidden_non_target_vault_mutation(tmp_path: Path) -> None:
    _, before, intent, fill, after_vaults, _, _ = _trade_bundle(tmp_path)
    by_before = {item.vault_id: item for item in before.vault_snapshots}
    by_after = {item.vault_id: item for item in after_vaults}
    tactical_before = by_before[PaperVaultId.TACTICAL]
    tactical_bad = build_epoch2_vault_accounting_snapshot(
        before.activation,
        vault_id=PaperVaultId.TACTICAL,
        snapshot_at_ms=fill.snapshot_at_ms,
        cash_usdt=Decimal(299),
        positions=(),
        marked_exposure_usdt=Decimal(0),
        realized_pnl_usdt=Decimal(-1),
        unrealized_pnl_usdt=Decimal(0),
        fee_usdt=Decimal(0),
        spread_usdt=Decimal(0),
        slippage_usdt=Decimal(0),
        turnover_notional_usdt=Decimal(0),
        closed_trade_count=1,
        win_count=0,
        loss_count=1,
        breakeven_count=0,
        outcome_distribution=(("LOSS", 1),),
        source_record_identities=(_sha("hidden-unrelated-mutation"),),
        previous=tactical_before,
    )
    mutated = (
        by_after[PaperVaultId.CORE],
        tactical_bad,
        by_after[PaperVaultId.OPPORTUNITY_RESERVE],
    )
    mutated_parent = build_consolidated_epoch2_snapshot(
        mutated,
        previous=before.consolidated_snapshot,
    )
    with pytest.raises(ValueError, match="non-target vault"):
        build_epoch2_accounting_bundle(
            before,
            intent=intent,
            fill=fill,
            after_vaults=mutated,
            after_consolidated=mutated_parent,
        )


def test_r22_hold_cash_is_append_only_without_r21_capital_mutation(
    tmp_path: Path,
) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    hold = build_tape_intent(
        before.activation,
        vault_id=PaperVaultId.OPPORTUNITY_RESERVE,
        action=PaperAction.HOLD_CASH,
        decided_at_ms=ISSUED_AT + 50,
        hold_policy_identity=_sha("hold-cash-policy"),
        reason_codes=("event_risk_wait",),
    )
    tape = R22Epoch2AtomicTape(epoch2_path)
    assert tape.append_hold_decision(hold)
    assert not tape.append_hold_decision(hold)
    assert Epoch2CanonicalLedger(epoch2_path).read_state() == before
    with sqlite3.connect(epoch2_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM r22_epoch2_intents"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM r22_epoch2_fills"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM r22_epoch2_bundles"
        ).fetchone() == (0,)


def test_r22_audit_tables_are_update_delete_immutable(tmp_path: Path) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    hold = build_tape_intent(
        before.activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.HOLD_CASH,
        decided_at_ms=ISSUED_AT + 50,
        hold_policy_identity=_sha("hold-policy"),
        reason_codes=("no_trade",),
    )
    tape = R22Epoch2AtomicTape(epoch2_path)
    assert tape.append_hold_decision(hold)
    with sqlite3.connect(epoch2_path) as connection:
        with pytest.raises(
            sqlite3.DatabaseError,
            match="immutable R22 Epoch2 audit tape",
        ):
            connection.execute(
                "UPDATE r22_epoch2_intents SET vault_id = 'TACTICAL'"
            )
        with pytest.raises(
            sqlite3.DatabaseError,
            match="immutable R22 Epoch2 audit tape",
        ):
            connection.execute("DELETE FROM r22_epoch2_intents")
