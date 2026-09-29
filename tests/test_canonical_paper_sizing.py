from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_canonical_capital_runtime import ISSUED_AT, _capital_inputs
from test_paper_portfolio_risk_v2 import (
    _confluence,
    _event,
    _portfolio_policy,
    _risk,
)
from test_position_sizing_intelligence import _policy as sizing_policy
from test_transaction_tape import _buy, _sizing
from test_transaction_tape_atomic import _initial_state

from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.canonical_sizing import (
    S11_CANONICAL_SIZING_POLICY_V2,
    S11_CANONICAL_SIZING_POLICY_VERSION,
    S11_CANONICAL_SIZING_VERSION,
    promote_fixed_fractional_sizing,
    promote_portfolio_risk_bounded_sizing,
)
from crypto_signal.paper.canonical_sizing_events import build_canonical_sizing_event
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.portfolio_risk_v2 import (
    assess_portfolio_allocation,
    build_portfolio_risk_snapshot,
)
from crypto_signal.paper.position_sizing_intelligence import SizingMethod
from crypto_signal.paper.transaction_tape import build_tape_intent


def test_s11_promotes_only_fixed_fractional_into_epoch2_paper_notional(
    tmp_path: Path,
) -> None:
    _, state = _initial_state(tmp_path)
    current = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, fixed = _sizing("0.25")

    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=current,
        selected_at_ms=current.snapshot_at_ms + 1,
    )

    assert selection.selection_version == S11_CANONICAL_SIZING_VERSION
    assert selection.policy_version == S11_CANONICAL_SIZING_POLICY_VERSION
    assert selection.vault_id is PaperVaultId.CORE
    assert selection.method is SizingMethod.FIXED_FRACTIONAL
    assert selection.fraction_of_vault == fixed.fraction_of_vault
    assert selection.canonical_notional_usdt == Decimal("150.0000")
    assert selection.current_cash_usdt == Decimal("600.00")
    assert selection.current_nav_usdt == Decimal("600.00")
    assert selection.canonical_epoch2_paper_authority is True
    assert selection.automatic_method_selection is True
    assert selection.production_authority is False
    assert selection.real_capital == 0
    assert "kelly_not_promoted" in selection.reason_codes
    assert assessment.assessment_identity in selection.source_evidence_identities
    assert fixed.result_identity in selection.source_evidence_identities
    assert current.snapshot_identity in selection.source_evidence_identities


def test_s11_promotion_rejects_wrong_vault_and_past_selection_time(
    tmp_path: Path,
) -> None:
    _, state = _initial_state(tmp_path)
    core = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    tactical = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.TACTICAL
    )
    assessment, _ = _sizing("0.25")

    with pytest.raises(ValueError, match="assessment/current-vault mismatch"):
        promote_fixed_fractional_sizing(
            assessment,
            current_vault=tactical,
            selected_at_ms=tactical.snapshot_at_ms + 1,
        )

    with pytest.raises(ValueError, match="cannot predate current vault"):
        promote_fixed_fractional_sizing(
            assessment,
            current_vault=core,
            selected_at_ms=core.snapshot_at_ms - 1,
        )


def test_s11_selection_identity_enters_exact_r22_trade_evidence(
    tmp_path: Path,
) -> None:
    (
        activation,
        before,
        forecast,
        proof,
        assessment,
        sizing_result,
        decision,
        _,
        _,
        _,
        _,
        _,
    ) = _buy()
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=before,
        selected_at_ms=max(before.snapshot_at_ms + 1, decision.decided_at_ms),
    )

    intent = build_tape_intent(
        activation,
        vault_id=PaperVaultId.CORE,
        action=PaperAction.BUY,
        decided_at_ms=decision.decided_at_ms,
        reason_codes=(
            "canonical_fixed_fractional_promotion",
            f"sizing_selection:{selection.selection_identity}",
        ),
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        sizing_result=sizing_result,
        decision=decision,
        additional_source_evidence_identities=(selection.selection_identity,),
    )

    assert selection.selection_identity in intent.source_evidence_identities
    assert any(
        code == f"sizing_selection:{selection.selection_identity}"
        for code in intent.reason_codes
    )
    assert intent.real_capital == 0
    assert intent.production_authority is False


def test_r22_hold_refuses_trade_only_promoted_sizing_evidence(
    tmp_path: Path,
) -> None:
    _, state = _initial_state(tmp_path)
    activation = state.activation

    with pytest.raises(ValueError, match="trade-only additional evidence"):
        build_tape_intent(
            activation,
            vault_id=PaperVaultId.CORE,
            action=PaperAction.HOLD_CASH,
            decided_at_ms=activation.activated_at_ms + 1,
            reason_codes=("no_trade",),
            hold_policy_identity="a" * 64,
            additional_source_evidence_identities=("b" * 64,),
        )


def _fp5_bound_assessment(
    state,
    *,
    event_state: CircuitBreakerState = CircuitBreakerState.CLEAR,
    snapshot_proven: bool = True,
    source_identity: str | None = None,
):
    portfolio_policy = _portfolio_policy(new_trade_loss="0.0005")
    risk = _risk(as_of_ms=ISSUED_AT)
    snapshot = None
    if snapshot_proven:
        source = (
            state.consolidated_snapshot.snapshot_identity
            if source_identity is None
            else source_identity
        )
        snapshot = build_portfolio_risk_snapshot(
            policy=portfolio_policy,
            source_portfolio_identity=source,
            as_of_ms=ISSUED_AT,
            cash_usdt=state.consolidated_snapshot.cash_usdt,
            nav_usdt=state.consolidated_snapshot.nav_usdt,
            asset_exposures=(),
        )
    assessment = assess_portfolio_allocation(
        policy=portfolio_policy,
        sizing_policy=sizing_policy(),
        snapshot=snapshot,
        risk_inputs=risk,
        event_context=_event(as_of_ms=ISSUED_AT, state=event_state),
        confluence=_confluence(as_of_ms=ISSUED_AT),
        base_asset="BTC",
        stop_invalidation_fraction=Decimal("0.05"),
    )
    return assessment, risk


def test_s11_v1_identity_payload_remains_backward_compatible(
    tmp_path: Path,
) -> None:
    _, state = _initial_state(tmp_path)
    current = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, fixed = _sizing("0.25")
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=current,
        selected_at_ms=current.snapshot_at_ms + 1,
    )

    expected_payload = {
        "allocator_candidate_identity": assessment.allocator_candidate_identity,
        "automatic_method_selection": True,
        "canonical_epoch2_paper_authority": True,
        "canonical_notional_usdt": Decimal("150.0000"),
        "current_cash_usdt": current.cash_usdt,
        "current_nav_usdt": current.nav_usdt,
        "current_vault_snapshot_identity": current.snapshot_identity,
        "fraction_of_vault": fixed.fraction_of_vault,
        "method": fixed.method,
        "policy_version": S11_CANONICAL_SIZING_POLICY_VERSION,
        "production_authority": False,
        "real_capital": 0,
        "reason_codes": selection.reason_codes,
        "selected_at_ms": current.snapshot_at_ms + 1,
        "selection_version": S11_CANONICAL_SIZING_VERSION,
        "sizing_assessment_identity": assessment.assessment_identity,
        "sizing_policy_identity": assessment.policy_identity,
        "sizing_result_identity": fixed.result_identity,
        "source_evidence_identities": selection.source_evidence_identities,
        "vault_id": assessment.vault_id,
    }
    assert selection.selection_identity == canonical_sha256(expected_payload)
    assert selection.portfolio_risk_assessment_identity is None
    assert selection.portfolio_source_identity is None
    assert selection.portfolio_risk_cap_usdt is None


def test_s11_v2_portfolio_risk_caps_notional_and_binds_lineage(
    tmp_path: Path,
) -> None:
    _, state = _initial_state(tmp_path)
    current = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, eligibility = _capital_inputs(PaperVaultId.CORE)
    portfolio_assessment, risk = _fp5_bound_assessment(state)
    selected_at_ms = max(
        ISSUED_AT + 10,
        current.snapshot_at_ms + 1,
        state.consolidated_snapshot.snapshot_at_ms + 1,
        eligibility.assessed_at_ms + 1,
    )

    selection = promote_portfolio_risk_bounded_sizing(
        assessment,
        current_vault=current,
        current_portfolio=state.consolidated_snapshot,
        portfolio_assessment=portfolio_assessment,
        candidate_asset=risk.asset,
        risk_input_identity=risk.risk_input_identity,
        selected_at_ms=selected_at_ms,
    )

    assert selection is not None
    assert selection.policy_version == S11_CANONICAL_SIZING_POLICY_V2
    assert selection.canonical_notional_usdt == (
        portfolio_assessment.max_deployable_notional_usdt
    )
    assert selection.canonical_notional_usdt < Decimal(12)
    assert selection.portfolio_risk_assessment_identity == (
        portfolio_assessment.assessment_identity
    )
    assert selection.portfolio_source_identity == (
        state.consolidated_snapshot.snapshot_identity
    )
    assert selection.portfolio_risk_cap_usdt == (
        portfolio_assessment.max_deployable_notional_usdt
    )
    assert "capped_by_portfolio_risk" in selection.reason_codes
    assert "portfolio_risk_v2_bound" in selection.reason_codes
    assert portfolio_assessment.assessment_identity in (
        selection.source_evidence_identities
    )
    assert state.consolidated_snapshot.snapshot_identity in (
        selection.source_evidence_identities
    )
    assert risk.risk_input_identity in selection.source_evidence_identities

    event = build_canonical_sizing_event(selection, eligibility)
    assert portfolio_assessment.assessment_identity in event.source_evidence_identities
    assert state.consolidated_snapshot.snapshot_identity in (
        event.source_evidence_identities
    )
    assert event.real_capital == 0


@pytest.mark.parametrize(
    ("event_state", "snapshot_proven"),
    [
        (CircuitBreakerState.CAUTION, True),
        (CircuitBreakerState.CLEAR, False),
    ],
)
def test_s11_v2_hold_or_not_proven_never_promotes_selection(
    tmp_path: Path,
    event_state: CircuitBreakerState,
    snapshot_proven: bool,
) -> None:
    _, state = _initial_state(tmp_path)
    current = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, _ = _capital_inputs(PaperVaultId.CORE)
    portfolio_assessment, risk = _fp5_bound_assessment(
        state,
        event_state=event_state,
        snapshot_proven=snapshot_proven,
    )

    selection = promote_portfolio_risk_bounded_sizing(
        assessment,
        current_vault=current,
        current_portfolio=state.consolidated_snapshot,
        portfolio_assessment=portfolio_assessment,
        candidate_asset=risk.asset,
        risk_input_identity=risk.risk_input_identity,
        selected_at_ms=ISSUED_AT + 10,
    )

    assert selection is None
    assert portfolio_assessment.max_deployable_notional_usdt == Decimal(0)


def test_s11_v2_rejects_stale_portfolio_and_risk_lineage(
    tmp_path: Path,
) -> None:
    _, state = _initial_state(tmp_path)
    current = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    assessment, _ = _capital_inputs(PaperVaultId.CORE)
    stale_source = canonical_sha256({"stale": "portfolio"})
    portfolio_assessment, risk = _fp5_bound_assessment(
        state,
        source_identity=stale_source,
    )

    with pytest.raises(ValueError, match="portfolio source is stale or mismatched"):
        promote_portfolio_risk_bounded_sizing(
            assessment,
            current_vault=current,
            current_portfolio=state.consolidated_snapshot,
            portfolio_assessment=portfolio_assessment,
            candidate_asset=risk.asset,
            risk_input_identity=risk.risk_input_identity,
            selected_at_ms=ISSUED_AT + 10,
        )

    valid_assessment, valid_risk = _fp5_bound_assessment(state)
    with pytest.raises(ValueError, match="risk-input identity mismatch"):
        promote_portfolio_risk_bounded_sizing(
            assessment,
            current_vault=current,
            current_portfolio=state.consolidated_snapshot,
            portfolio_assessment=valid_assessment,
            candidate_asset=valid_risk.asset,
            risk_input_identity="f" * 64,
            selected_at_ms=ISSUED_AT + 10,
        )
