from __future__ import annotations

from decimal import Decimal

import pytest
from test_immutable_forecast_stream import _event_context
from test_position_sizing_bridge import _core_risk
from test_position_sizing_intelligence import _policy
from test_r22_intent_preview import _activation, _market_reference
from test_unified_decision_runtime import _issue

from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction
from crypto_signal.paper.position_sizing_intelligence import SizingMethod
from crypto_signal.paper.shadow_intent_journal import (
    R25ShadowIntentJournal,
    ShadowIntentAppendDisposition,
)
from crypto_signal.paper.shadow_replay_orchestrator import (
    run_shadow_restart_replay_cycle,
)


def _inputs(tmp_path):
    _, issuance = _issue(tmp_path)
    return issuance, _event_context()


def _run(
    tmp_path,
    journal,
    *,
    shift: int = 0,
    reviewed_method: SizingMethod | None = SizingMethod.FIXED_FRACTIONAL,
    risk: bool = True,
):
    issuance, event = _inputs(tmp_path)
    issued = issuance.forecast.issued_at_ms
    kwargs = {
        "event_context": event,
        "base_asset": "BTC",
        "activation": _activation(),
        "sizing_policy": _policy(),
        "journal": journal,
        "vault_id": PaperVaultId.CORE,
        "capital_assessed_at_ms": issued + 4 + shift,
        "sized_at_ms": issued + 5 + shift,
        "previewed_at_ms": issued + 7 + shift,
        "risk_inputs": ((_core_risk(issuance),) if risk else ()),
        "reviewed_method": reviewed_method,
        "reviewed_at_ms": (
            issued + 6 + shift if reviewed_method is not None else None
        ),
        "market_reference": (
            _market_reference(issuance)
            if reviewed_method is not None
            else None
        ),
        "quantity": (
            Decimal("0.10") if reviewed_method is not None else None
        ),
        "reason_codes": ("r25_restart_replay_acceptance",),
    }
    return issuance, run_shadow_restart_replay_cycle(issuance, **kwargs)


def test_exact_restart_replay_is_identity_stable_and_journal_idempotent(
    tmp_path,
) -> None:
    path = tmp_path / "replay.shadow-intent.sqlite3"
    issuance, first = _run(
        tmp_path,
        R25ShadowIntentJournal(path),
    )
    _, second = _run(
        tmp_path,
        R25ShadowIntentJournal(path),
    )

    assert first.cycle_identity == second.cycle_identity
    assert first.capital.bridge_identity == second.capital.bridge_identity
    assert first.sizing.bridge_identity == second.sizing.bridge_identity
    assert (
        first.reviewed_selection is not None
        and second.reviewed_selection is not None
    )
    assert (
        first.reviewed_selection.selection_identity
        == second.reviewed_selection.selection_identity
    )
    assert first.preview.preview_identity == second.preview.preview_identity
    assert (
        first.journal_append.record.record_identity
        == second.journal_append.record.record_identity
    )
    assert (
        first.journal_append.disposition
        is ShadowIntentAppendDisposition.INSERTED
    )
    assert (
        second.journal_append.disposition
        is ShadowIntentAppendDisposition.IDEMPOTENT
    )
    assert second.journal_status.record_count == 1
    assert second.preview.intent.action is PaperAction.BUY
    assert second.preview.intent.forecast_identity == (
        issuance.forecast.forecast_identity
    )
    assert second.canonical_epoch2_write_authority is False
    assert second.production_authority is False
    assert second.real_capital == 0


def test_no_explicit_method_review_replays_as_hold_cash(tmp_path) -> None:
    path = tmp_path / "hold-replay.shadow-intent.sqlite3"
    _, first = _run(
        tmp_path,
        R25ShadowIntentJournal(path),
        reviewed_method=None,
        risk=False,
    )
    _, second = _run(
        tmp_path,
        R25ShadowIntentJournal(path),
        reviewed_method=None,
        risk=False,
    )

    assert first.preview.intent.action is PaperAction.HOLD_CASH
    assert first.reviewed_selection is None
    assert second.preview.preview_identity == first.preview.preview_identity
    assert (
        second.journal_append.disposition
        is ShadowIntentAppendDisposition.IDEMPOTENT
    )
    assert second.journal_status.record_count == 1


def test_unavailable_kelly_review_fails_before_journal_creation(tmp_path) -> None:
    path = tmp_path / "kelly-disabled.shadow-intent.sqlite3"
    with pytest.raises(ValueError, match="not AVAILABLE_SHADOW"):
        _run(
            tmp_path,
            R25ShadowIntentJournal(path),
            reviewed_method=SizingMethod.KELLY_HALF,
        )
    assert not path.exists()


def test_restart_backfill_fails_closed_and_preserves_existing_record(
    tmp_path,
) -> None:
    path = tmp_path / "restart-backfill.shadow-intent.sqlite3"
    _, later = _run(
        tmp_path,
        R25ShadowIntentJournal(path),
        shift=10,
    )
    assert later.journal_status.record_count == 1

    with pytest.raises(ValueError, match="cannot backfill or fork"):
        _run(
            tmp_path,
            R25ShadowIntentJournal(path),
            shift=0,
        )

    status = R25ShadowIntentJournal(path).verify_read_only()
    assert status.record_count == 1
    assert status.last_record_identities == (
        (PaperVaultId.CORE, later.journal_append.record.record_identity),
    )


def test_replay_cycle_never_selects_canonical_sizing_or_writer_authority(
    tmp_path,
) -> None:
    _, result = _run(
        tmp_path,
        R25ShadowIntentJournal(
            tmp_path / "authority.shadow-intent.sqlite3"
        ),
    )

    assert result.sizing.selected_method is None
    assert result.sizing.canonical_notional_usdt is None
    assert result.sizing.automatic_method_selection is False
    assert result.preview.tape_write_authority is False
    assert result.preview.canonical_epoch2_write_authority is False
    assert result.journal_status.canonical_epoch2_write_authority is False
    assert result.canonical_epoch2_write_authority is False
    assert result.production_authority is False
    assert result.real_capital == 0
