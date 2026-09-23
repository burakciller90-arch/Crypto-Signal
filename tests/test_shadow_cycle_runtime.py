from __future__ import annotations

import sqlite3
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
from crypto_signal.paper.shadow_cycle_manifest import (
    R25ShadowCycleManifest,
    ShadowCycleManifestDisposition,
)
from crypto_signal.paper.shadow_cycle_runtime import run_persisted_shadow_cycle
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


def _kwargs(
    tmp_path,
    journal,
    *,
    shift: int = 0,
    reviewed_method: SizingMethod | None = SizingMethod.FIXED_FRACTIONAL,
    risk: bool = True,
):
    issuance, event = _inputs(tmp_path)
    issued = issuance.forecast.issued_at_ms
    return issuance, {
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
        "reason_codes": ("r25_persisted_cycle_acceptance",),
    }


def test_persisted_shadow_cycle_exact_replay_is_double_idempotent(
    tmp_path,
) -> None:
    journal_path = tmp_path / "double.shadow-intent.sqlite3"
    manifest_path = tmp_path / "double.shadow-cycle.sqlite3"

    issuance, kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    first = run_persisted_shadow_cycle(
        issuance,
        manifest=R25ShadowCycleManifest(manifest_path),
        **kwargs,
    )

    issuance2, kwargs2 = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    second = run_persisted_shadow_cycle(
        issuance2,
        manifest=R25ShadowCycleManifest(manifest_path),
        **kwargs2,
    )

    assert first.persisted_cycle_identity == second.persisted_cycle_identity
    assert first.cycle.cycle_identity == second.cycle.cycle_identity
    assert (
        first.cycle.journal_append.record.record_identity
        == second.cycle.journal_append.record.record_identity
    )
    assert (
        first.manifest_append.record.manifest_identity
        == second.manifest_append.record.manifest_identity
    )
    assert (
        first.cycle.journal_append.disposition
        is ShadowIntentAppendDisposition.INSERTED
    )
    assert (
        second.cycle.journal_append.disposition
        is ShadowIntentAppendDisposition.IDEMPOTENT
    )
    assert (
        first.manifest_append.disposition
        is ShadowCycleManifestDisposition.INSERTED
    )
    assert (
        second.manifest_append.disposition
        is ShadowCycleManifestDisposition.IDEMPOTENT
    )
    assert second.cycle.journal_status.record_count == 1
    assert second.manifest_status.record_count == 1
    assert second.canonical_epoch2_write_authority is False
    assert second.production_authority is False
    assert second.real_capital == 0


def test_restart_recovers_crash_after_journal_before_manifest(tmp_path) -> None:
    journal_path = tmp_path / "crash.shadow-intent.sqlite3"
    manifest_path = tmp_path / "crash.shadow-cycle.sqlite3"
    journal = R25ShadowIntentJournal(journal_path)

    issuance, kwargs = _kwargs(tmp_path, journal)
    orphan_cycle = run_shadow_restart_replay_cycle(issuance, **kwargs)

    assert orphan_cycle.journal_append.disposition is (
        ShadowIntentAppendDisposition.INSERTED
    )
    assert journal.verify_read_only().record_count == 1
    assert not manifest_path.exists()

    issuance2, kwargs2 = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    recovered = run_persisted_shadow_cycle(
        issuance2,
        manifest=R25ShadowCycleManifest(manifest_path),
        **kwargs2,
    )

    assert recovered.cycle.cycle_identity == orphan_cycle.cycle_identity
    assert recovered.cycle.journal_append.disposition is (
        ShadowIntentAppendDisposition.IDEMPOTENT
    )
    assert recovered.manifest_append.disposition is (
        ShadowCycleManifestDisposition.INSERTED
    )
    assert recovered.cycle.journal_status.record_count == 1
    assert recovered.manifest_status.record_count == 1
    assert (
        recovered.manifest_append.record.journal_record_identity
        == orphan_cycle.journal_append.record.record_identity
    )


def test_hold_cash_cycle_is_persisted_without_fabricated_review(tmp_path) -> None:
    issuance, kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(
            tmp_path / "hold.shadow-intent.sqlite3"
        ),
        reviewed_method=None,
        risk=False,
    )
    result = run_persisted_shadow_cycle(
        issuance,
        manifest=R25ShadowCycleManifest(
            tmp_path / "hold.shadow-cycle.sqlite3"
        ),
        **kwargs,
    )

    assert result.cycle.preview.intent.action is PaperAction.HOLD_CASH
    assert result.cycle.reviewed_selection is None
    assert result.manifest_append.record.review_selection_identity is None
    assert result.manifest_append.record.reviewed_method is None
    assert result.manifest_status.record_count == 1


def test_disabled_kelly_fails_before_journal_or_manifest_creation(
    tmp_path,
) -> None:
    journal_path = tmp_path / "kelly.shadow-intent.sqlite3"
    manifest_path = tmp_path / "kelly.shadow-cycle.sqlite3"
    issuance, kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
        reviewed_method=SizingMethod.KELLY_HALF,
    )

    with pytest.raises(ValueError, match="not AVAILABLE_SHADOW"):
        run_persisted_shadow_cycle(
            issuance,
            manifest=R25ShadowCycleManifest(manifest_path),
            **kwargs,
        )

    assert not journal_path.exists()
    assert not manifest_path.exists()


def test_manifest_failure_does_not_rewrite_existing_journal(tmp_path) -> None:
    journal_path = tmp_path / "isolation.shadow-intent.sqlite3"
    bad_manifest = tmp_path / "bad.shadow-cycle.sqlite3"

    with sqlite3.connect(bad_manifest) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    issuance, kwargs = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    with pytest.raises(ValueError, match="non-shadow tables"):
        run_persisted_shadow_cycle(
            issuance,
            manifest=R25ShadowCycleManifest(bad_manifest),
            **kwargs,
        )

    journal = R25ShadowIntentJournal(journal_path)
    before = journal.verify_read_only()
    raw_before = journal_path.read_bytes()

    issuance2, kwargs2 = _kwargs(
        tmp_path,
        R25ShadowIntentJournal(journal_path),
    )
    recovered = run_persisted_shadow_cycle(
        issuance2,
        manifest=R25ShadowCycleManifest(
            tmp_path / "recovered.shadow-cycle.sqlite3"
        ),
        **kwargs2,
    )

    raw_after = journal_path.read_bytes()
    assert before.record_count == 1
    assert recovered.cycle.journal_append.disposition is (
        ShadowIntentAppendDisposition.IDEMPOTENT
    )
    assert recovered.manifest_append.disposition is (
        ShadowCycleManifestDisposition.INSERTED
    )
    assert raw_after == raw_before
