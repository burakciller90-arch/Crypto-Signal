from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_transaction_tape import _buy, _sizing
from test_transaction_tape_atomic import _initial_state

from crypto_signal.paper.canonical_sizing import (
    S11_CANONICAL_SIZING_POLICY_VERSION,
    S11_CANONICAL_SIZING_VERSION,
    promote_fixed_fractional_sizing,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction
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
