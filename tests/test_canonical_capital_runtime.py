from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_decision_proof_live_feed import ISSUED_AT, _forecast, _slices
from test_position_sizing_intelligence import (
    _policy as sizing_policy,
)
from test_smart_capital_allocator import _candidate
from test_transaction_tape_atomic import _initial_state

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.canonical_capital_runtime import (
    S11_CAPITAL_COMMIT_VERSION,
    commit_canonical_paper_buy,
)
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.canonical_vault_eligibility import promote_vault_eligibility
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.models import PaperSymbol
from crypto_signal.paper.position_sizing_intelligence import (
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.smart_capital_allocator import assess_smart_capital_candidate
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.decision_proof import build_decision_proof_snapshot


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _capital_inputs(vault_id: PaperVaultId):
    candidate = _candidate()
    allocator = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )
    envelope = next(
        item for item in allocator.vaults if item.vault_id is vault_id
    )
    context = build_position_sizing_risk_context(
        vault_id=vault_id,
        asset="BTCUSDT",
        as_of_ms=ISSUED_AT,
        allocator_assessment_identity=allocator.assessment_identity,
        allocator_candidate_identity=candidate.candidate_identity,
        expected_win_r=Decimal(2),
        expected_loss_r=Decimal(1),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=Decimal("0.20"),
        current_drawdown_fraction=Decimal("0.05"),
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=(
            _sha(f"{vault_id.value}-correlation"),
            _sha(f"{vault_id.value}-drawdown"),
            _sha(f"{vault_id.value}-liquidity"),
            _sha(f"{vault_id.value}-payoff"),
            _sha(f"{vault_id.value}-volatility"),
        ),
    )
    sizing = evaluate_position_sizing_intelligence(
        policy=sizing_policy(),
        vault=envelope,
        context=context,
    )
    eligibility = promote_vault_eligibility(
        candidate,
        allocator,
        vault_id=vault_id,
    )
    return sizing, eligibility


def _execution_snapshot():
    return build_frozen_execution_snapshot(
        venue_reference="s11:test-binance-spot",
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        min_notional_usdt=Decimal(1),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
    )


def test_s11_atomic_buy_mutates_only_target_vault_and_binds_exact_lineage(
    tmp_path: Path,
) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    core = next(
        item for item in before.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, eligibility = _capital_inputs(PaperVaultId.CORE)
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=core,
        selected_at_ms=ISSUED_AT + 10,
    )

    result = commit_canonical_paper_buy(
        epoch2_path=epoch2_path,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        symbol=PaperSymbol.BTCUSDT,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("reference-price"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("mark-set"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=ISSUED_AT + 20,
        filled_at_ms=ISSUED_AT + 30,
        mutated_at_ms=ISSUED_AT + 31,
        snapshot_at_ms=ISSUED_AT + 40,
    )

    assert result.version == S11_CAPITAL_COMMIT_VERSION
    assert result.vault_id is PaperVaultId.CORE
    assert result.sizing_selection_identity == selection.selection_identity
    assert result.inserted is True
    assert result.production_authority is False
    assert result.real_capital == 0

    after = Epoch2CanonicalLedger(epoch2_path).read_state()
    before_by_vault = {item.vault_id: item for item in before.vault_snapshots}
    after_by_vault = {item.vault_id: item for item in after.vault_snapshots}
    core_after = after_by_vault[PaperVaultId.CORE]
    assert core_after.snapshot_identity == result.after_vault_snapshot_identity
    assert core_after.cash_usdt < before_by_vault[PaperVaultId.CORE].cash_usdt
    assert core_after.positions
    assert core_after.positions[0].symbol is PaperSymbol.BTCUSDT
    assert core_after.real_capital == 0

    for vault_id in (
        PaperVaultId.TACTICAL,
        PaperVaultId.OPPORTUNITY_RESERVE,
    ):
        previous = before_by_vault[vault_id]
        current = after_by_vault[vault_id]
        assert current.cash_usdt == previous.cash_usdt
        assert current.positions == previous.positions
        assert current.realized_pnl_usdt == previous.realized_pnl_usdt
        assert current.unrealized_pnl_usdt == previous.unrealized_pnl_usdt
        assert current.fee_usdt == previous.fee_usdt
        assert current.turnover_notional_usdt == previous.turnover_notional_usdt

    audit = R22Epoch2AtomicTape(epoch2_path).audit_bundle_read_only(
        result.accounting_bundle_identity
    )
    assert audit["intent_identity"] == result.intent_identity
    assert audit["fill_identity"] == result.fill_identity
    assert audit["after_consolidated_snapshot_identity"] == (
        result.after_consolidated_snapshot_identity
    )
    assert audit["real_capital"] == 0
    assert audit["production_authority"] is False


def test_s11_same_atomic_runtime_can_participate_for_all_three_vaults(
    tmp_path: Path,
) -> None:
    epoch2_path, _ = _initial_state(tmp_path)
    execution = _execution_snapshot()

    for index, vault_id in enumerate(
        (
            PaperVaultId.CORE,
            PaperVaultId.TACTICAL,
            PaperVaultId.OPPORTUNITY_RESERVE,
        )
    ):
        forecast = _forecast(
            timeframe="5m" if vault_id is PaperVaultId.TACTICAL else "4h"
        )
        proof = build_decision_proof_snapshot(forecast, _slices(forecast))
        state = Epoch2CanonicalLedger(epoch2_path).read_state()
        current = next(
            item for item in state.vault_snapshots
            if item.vault_id is vault_id
        )
        assessment, eligibility = _capital_inputs(vault_id)
        base_time = ISSUED_AT + 100 + index * 100
        selection = promote_fixed_fractional_sizing(
            assessment,
            current_vault=current,
            selected_at_ms=base_time,
        )
        result = commit_canonical_paper_buy(
            epoch2_path=epoch2_path,
            forecast=forecast,
            proof=proof,
            sizing_assessment=assessment,
            sizing_selection=selection,
            symbol=PaperSymbol.BTCUSDT,
            reference_price=Decimal(101),
            reference_price_evidence_identity=_sha(
                f"reference-price-{vault_id.value}"
            ),
            mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
            mark_evidence_identity=_sha(f"mark-{vault_id.value}"),
            execution_snapshot=execution,
            decided_at_ms=base_time + 1,
            filled_at_ms=base_time + 2,
            mutated_at_ms=base_time + 3,
            snapshot_at_ms=base_time + 4,
        )
        assert result.vault_id is vault_id
        assert result.inserted is True

    final = Epoch2CanonicalLedger(epoch2_path).read_state()
    by_vault = {item.vault_id: item for item in final.vault_snapshots}
    assert all(by_vault[vault_id].positions for vault_id in PaperVaultId)
    assert all(by_vault[vault_id].cash_usdt > 0 for vault_id in PaperVaultId)
    assert final.consolidated_snapshot.real_capital == 0
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == (3, 3, 3)


def test_s11_buy_refuses_stale_selection_and_price_outside_trigger(
    tmp_path: Path,
) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    forecast = _forecast()
    proof = build_decision_proof_snapshot(forecast, _slices(forecast))
    core = next(
        item for item in before.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, eligibility = _capital_inputs(PaperVaultId.CORE)
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=core,
        selected_at_ms=ISSUED_AT + 10,
    )
    kwargs = {
        "epoch2_path": epoch2_path,
        "forecast": forecast,
        "proof": proof,
        "sizing_assessment": assessment,
        "sizing_selection": selection,
        "eligibility_proof": eligibility,
        "symbol": PaperSymbol.BTCUSDT,
        "reference_price_evidence_identity": _sha("reference-price"),
        "mark_prices": {PaperSymbol.BTCUSDT: Decimal(101)},
        "mark_evidence_identity": _sha("mark-set"),
        "execution_snapshot": _execution_snapshot(),
        "decided_at_ms": ISSUED_AT + 20,
        "filled_at_ms": ISSUED_AT + 30,
        "mutated_at_ms": ISSUED_AT + 31,
        "snapshot_at_ms": ISSUED_AT + 40,
    }

    with pytest.raises(ValueError, match="inside exact trigger zone"):
        commit_canonical_paper_buy(
            reference_price=Decimal(103),
            **kwargs,
        )

    committed = commit_canonical_paper_buy(
        reference_price=Decimal(101),
        **kwargs,
    )
    assert committed.inserted is True

    with pytest.raises(ValueError, match="stale against current vault"):
        commit_canonical_paper_buy(
            reference_price=Decimal(101),
            decided_at_ms=ISSUED_AT + 50,
            filled_at_ms=ISSUED_AT + 51,
            mutated_at_ms=ISSUED_AT + 52,
            snapshot_at_ms=ISSUED_AT + 53,
            **{
                key: value
                for key, value in kwargs.items()
                if key not in {
                    "decided_at_ms",
                    "filled_at_ms",
                    "mutated_at_ms",
                    "snapshot_at_ms",
                }
            },
        )
