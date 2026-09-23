from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from test_r22_intent_preview import (
    _activation,
    _fixed_selection,
    _market_reference,
    _sizing,
)

from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.r22_intent_preview import build_r22_intent_preview
from crypto_signal.paper.shadow_intent_journal import (
    R25ShadowIntentJournal,
    ShadowIntentAppendDisposition,
)


def _buy_preview(tmp_path, *, offset: int = 2, previous_intent_identity=None):
    issuance, sizing = _sizing(tmp_path)
    _, selection = _fixed_selection(sizing)
    preview = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + offset,
        reviewed_selection=selection,
        market_reference=_market_reference(issuance),
        quantity=Decimal("0.10"),
        previous_intent_identity=previous_intent_identity,
    )
    return issuance, sizing, preview


def test_shadow_journal_append_is_idempotent_and_read_only_verifiable(
    tmp_path,
) -> None:
    _, _, preview = _buy_preview(tmp_path)
    path = tmp_path / "r25.shadow-intent.sqlite3"
    journal = R25ShadowIntentJournal(path)

    first = journal.append(preview)
    second = journal.append(preview)
    status = R25ShadowIntentJournal(path).verify_read_only()

    assert first.disposition is ShadowIntentAppendDisposition.INSERTED
    assert second.disposition is ShadowIntentAppendDisposition.IDEMPOTENT
    assert second.record == first.record
    assert status.record_count == 1
    assert status.last_record_identities == (
        (PaperVaultId.CORE, first.record.record_identity),
    )
    assert status.quick_check_ok is True
    assert status.read_only_verified is True
    assert status.canonical_epoch2_write_authority is False
    assert status.production_authority is False
    assert status.real_capital == 0


def test_shadow_journal_builds_strict_per_vault_predecessor_chain(tmp_path) -> None:
    issuance, sizing, first_preview = _buy_preview(tmp_path, offset=2)
    _, selection = _fixed_selection(sizing)
    second_preview = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + 4,
        reviewed_selection=selection,
        market_reference=_market_reference(issuance),
        quantity=Decimal("0.10"),
        previous_intent_identity=first_preview.intent.intent_identity,
    )
    journal = R25ShadowIntentJournal(
        tmp_path / "chain.shadow-intent.sqlite3"
    )
    first = journal.append(first_preview)
    second = journal.append(second_preview)
    status = journal.verify_read_only()

    assert second.record.previous_record_identity == first.record.record_identity
    assert status.record_count == 2
    assert status.last_record_identities == (
        (PaperVaultId.CORE, second.record.record_identity),
    )


def test_shadow_journal_rejects_backfill_without_partial_insert(tmp_path) -> None:
    issuance, sizing, later = _buy_preview(tmp_path, offset=4)
    _, selection = _fixed_selection(sizing)
    earlier = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + 2,
        reviewed_selection=selection,
        market_reference=_market_reference(issuance),
        quantity=Decimal("0.10"),
    )
    journal = R25ShadowIntentJournal(
        tmp_path / "backfill.shadow-intent.sqlite3"
    )
    journal.append(later)

    with pytest.raises(ValueError, match="cannot backfill or fork"):
        journal.append(earlier)

    assert journal.verify_read_only().record_count == 1


def test_shadow_journal_accepts_hold_cash_preview_without_trade_mutation(
    tmp_path,
) -> None:
    issuance, sizing = _sizing(tmp_path)
    hold = build_r22_intent_preview(
        issuance,
        sizing,
        _activation(),
        vault_id=PaperVaultId.CORE,
        previewed_at_ms=sizing.sized_at_ms + 1,
    )
    journal = R25ShadowIntentJournal(
        tmp_path / "hold.shadow-intent.sqlite3"
    )
    result = journal.append(hold)
    status = journal.verify_read_only()

    assert result.disposition is ShadowIntentAppendDisposition.INSERTED
    assert hold.decision is None
    assert status.record_count == 1


def test_shadow_journal_update_delete_are_blocked_by_immutable_triggers(
    tmp_path,
) -> None:
    _, _, preview = _buy_preview(tmp_path)
    path = tmp_path / "immutable.shadow-intent.sqlite3"
    journal = R25ShadowIntentJournal(path)
    journal.append(preview)

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute(
                """UPDATE r25_shadow_intent_records
                SET event_at_ms = event_at_ms + 1"""
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable R25"):
            db.execute("DELETE FROM r25_shadow_intent_records")

    assert journal.verify_read_only().record_count == 1


def test_shadow_journal_refuses_database_with_non_shadow_tables(tmp_path) -> None:
    path = tmp_path / "wrong.shadow-intent.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE canonical_epoch2_accounting (id TEXT)")

    journal = R25ShadowIntentJournal(path)
    with pytest.raises(ValueError, match="non-shadow tables"):
        journal.initialize()


def test_shadow_journal_refuses_non_isolated_filename(tmp_path) -> None:
    with pytest.raises(ValueError, match="must end with"):
        R25ShadowIntentJournal(tmp_path / "epoch2.sqlite3")
