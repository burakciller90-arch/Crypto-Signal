from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_shadow_replay_orchestrator import _run

from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import SizingMethod
from crypto_signal.paper.shadow_cycle_manifest import (
    R25ShadowCycleManifest,
    ShadowCycleManifestDisposition,
)
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal


def _cycle(
    tmp_path: Path,
    *,
    shift: int = 0,
    reviewed_method: SizingMethod | None = SizingMethod.FIXED_FRACTIONAL,
):
    journal = R25ShadowIntentJournal(
        tmp_path / f"intent-{shift}.shadow-intent.sqlite3"
    )
    _, cycle = _run(
        tmp_path,
        journal,
        shift=shift,
        reviewed_method=reviewed_method,
        risk=reviewed_method is not None,
    )
    return cycle


def test_shadow_cycle_manifest_is_idempotent_for_exact_restart_replay(
    tmp_path: Path,
) -> None:
    intent_path = tmp_path / "replay.shadow-intent.sqlite3"
    first_journal = R25ShadowIntentJournal(intent_path)
    _, first_cycle = _run(tmp_path, first_journal)

    second_journal = R25ShadowIntentJournal(intent_path)
    _, second_cycle = _run(tmp_path, second_journal)

    manifest = R25ShadowCycleManifest(
        tmp_path / "replay.shadow-cycle.sqlite3"
    )
    first = manifest.append(first_cycle)
    second = manifest.append(second_cycle)
    status = manifest.verify_read_only()

    assert first_cycle.cycle_identity == second_cycle.cycle_identity
    assert first.record == second.record
    assert first.disposition is ShadowCycleManifestDisposition.INSERTED
    assert second.disposition is ShadowCycleManifestDisposition.IDEMPOTENT
    assert first.record.forecast_identity == first_cycle.forecast_identity
    assert first.record.proof_identity == first_cycle.proof_identity
    assert (
        first.record.capital_bridge_identity
        == first_cycle.capital.bridge_identity
    )
    assert (
        first.record.sizing_bridge_identity
        == first_cycle.sizing.bridge_identity
    )
    assert (
        first.record.review_selection_identity
        == first_cycle.reviewed_selection.selection_identity
    )
    assert first.record.preview_identity == first_cycle.preview.preview_identity
    assert (
        first.record.journal_record_identity
        == first_cycle.journal_append.record.record_identity
    )
    assert status.record_count == 1
    assert status.quick_check_ok is True
    assert status.read_only_verified is True
    assert status.canonical_epoch2_write_authority is False
    assert status.production_authority is False
    assert status.real_capital == 0


def test_shadow_cycle_manifest_keeps_hold_cash_review_null(
    tmp_path: Path,
) -> None:
    cycle = _cycle(tmp_path, reviewed_method=None)
    manifest = R25ShadowCycleManifest(
        tmp_path / "hold.shadow-cycle.sqlite3"
    )
    result = manifest.append(cycle)
    latest = manifest.read_latest()

    assert result.record.review_selection_identity is None
    assert result.record.reviewed_method is None
    assert len(latest) == 1
    assert latest[0] == result.record


def test_shadow_cycle_manifest_builds_strict_per_vault_chain(
    tmp_path: Path,
) -> None:
    first_cycle = _cycle(tmp_path, shift=0)
    second_cycle = _cycle(tmp_path, shift=20)
    manifest = R25ShadowCycleManifest(
        tmp_path / "chain.shadow-cycle.sqlite3"
    )

    first = manifest.append(first_cycle)
    second = manifest.append(second_cycle)
    status = manifest.verify_read_only()

    assert second.record.previous_manifest_identity == (
        first.record.manifest_identity
    )
    assert status.record_count == 2
    assert status.last_manifest_identities == (
        (PaperVaultId.CORE, second.record.manifest_identity),
    )


def test_shadow_cycle_manifest_rejects_backfill_without_partial_insert(
    tmp_path: Path,
) -> None:
    later_cycle = _cycle(tmp_path, shift=20)
    earlier_cycle = _cycle(tmp_path, shift=0)
    manifest = R25ShadowCycleManifest(
        tmp_path / "backfill.shadow-cycle.sqlite3"
    )
    later = manifest.append(later_cycle)

    with pytest.raises(ValueError, match="cannot backfill or fork"):
        manifest.append(earlier_cycle)

    status = manifest.verify_read_only()
    assert status.record_count == 1
    assert status.last_manifest_identities == (
        (PaperVaultId.CORE, later.record.manifest_identity),
    )


def test_shadow_cycle_manifest_read_only_verification_is_byte_stable(
    tmp_path: Path,
) -> None:
    cycle = _cycle(tmp_path)
    path = tmp_path / "byte-stable.shadow-cycle.sqlite3"
    manifest = R25ShadowCycleManifest(path)
    manifest.append(cycle)
    before = path.read_bytes()

    status = manifest.verify_read_only()
    latest = manifest.read_latest()
    after = path.read_bytes()

    assert status.record_count == 1
    assert len(latest) == 1
    assert after == before


def test_shadow_cycle_manifest_append_does_not_mutate_intent_journal(
    tmp_path: Path,
) -> None:
    intent_path = tmp_path / "isolated.shadow-intent.sqlite3"
    journal = R25ShadowIntentJournal(intent_path)
    _, cycle = _run(tmp_path, journal)
    intent_before = intent_path.read_bytes()

    manifest = R25ShadowCycleManifest(
        tmp_path / "isolated.shadow-cycle.sqlite3"
    )
    result = manifest.append(cycle)
    intent_after = intent_path.read_bytes()

    assert result.record.journal_record_identity == (
        cycle.journal_append.record.record_identity
    )
    assert intent_after == intent_before


def test_shadow_cycle_manifest_update_delete_are_immutable(
    tmp_path: Path,
) -> None:
    cycle = _cycle(tmp_path)
    path = tmp_path / "immutable.shadow-cycle.sqlite3"
    manifest = R25ShadowCycleManifest(path)
    manifest.append(cycle)

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute(
                """UPDATE r25_shadow_cycle_manifest
                SET event_at_ms = event_at_ms + 1"""
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute("DELETE FROM r25_shadow_cycle_manifest")

    assert manifest.verify_read_only().record_count == 1


def test_shadow_cycle_manifest_refuses_wrong_database_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wrong.shadow-cycle.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    manifest = R25ShadowCycleManifest(path)
    with pytest.raises(ValueError, match="non-shadow tables"):
        manifest.initialize()


def test_shadow_cycle_manifest_requires_isolated_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must end with"):
        R25ShadowCycleManifest(tmp_path / "epoch2.sqlite3")
