from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper.epochs import (
    EPOCH_1_LEDGER_FILENAME,
    EPOCH_2_LEDGER_FILENAME,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    PaperSymbol,
)
from crypto_signal.paper.vault_v3 import (
    DEFAULT_PAPER_VAULT_V3_STARTING_CAPITAL_USDT,
    PAPER_VAULT_V3_ALLOCATION_POLICY_VERSION,
    PAPER_VAULT_V3_CONSTITUTION_POLICY_VERSION,
    PaperVaultV3Book,
    PaperVaultV3EvidencePolicyVersion,
    PaperVaultV3LifecycleAction,
    PaperVaultV3Status,
    PaperVaultV3Store,
    build_paper_vault_v3_allocation_policy,
    build_paper_vault_v3_constitution,
    build_paper_vault_v3_lifecycle_event,
)


def _evidence_versions() -> tuple[PaperVaultV3EvidencePolicyVersion, ...]:
    return (
        PaperVaultV3EvidencePolicyVersion(
            domain="order_flow",
            version="order-flow-proof-policy-v1/1",
        ),
        PaperVaultV3EvidencePolicyVersion(
            domain="geometry",
            version="geometry-proof-policy-v1/1",
        ),
        PaperVaultV3EvidencePolicyVersion(
            domain="event_risk",
            version="event-risk-proof-policy-v1/1",
        ),
    )


def _constitution(
    *,
    created_at_ms: int = 1_000,
    capital: Decimal = DEFAULT_PAPER_VAULT_V3_STARTING_CAPITAL_USDT,
):
    return build_paper_vault_v3_constitution(
        created_at_ms=created_at_ms,
        starting_virtual_capital_usdt=capital,
        evidence_policy_versions=_evidence_versions(),
        permitted_instruments=(
            PaperSymbol.SOLUSDT,
            PaperSymbol.BTCUSDT,
            PaperSymbol.ETHUSDT,
        ),
    )


def test_v3_constitution_is_deterministic_and_freezes_complete_policy() -> None:
    first = _constitution()
    second = build_paper_vault_v3_constitution(
        created_at_ms=1_000,
        evidence_policy_versions=tuple(reversed(_evidence_versions())),
        permitted_instruments=(
            PaperSymbol.ETHUSDT,
            PaperSymbol.SOLUSDT,
            PaperSymbol.BTCUSDT,
        ),
    )

    assert first == second
    assert len(first.vault_identity) == 64
    assert first.starting_virtual_capital_usdt == Decimal("10000.00")
    assert (
        first.constitution_policy_version
        == PAPER_VAULT_V3_CONSTITUTION_POLICY_VERSION
    )
    assert first.execution_policy_version == PAPER_EXECUTION_POLICY_VERSION
    assert first.risk_policy_version == PAPER_RISK_POLICY_VERSION
    assert first.permitted_instruments == (
        PaperSymbol.BTCUSDT,
        PaperSymbol.ETHUSDT,
        PaperSymbol.SOLUSDT,
    )
    assert tuple(item.domain for item in first.evidence_policy_versions) == (
        "event_risk",
        "geometry",
        "order_flow",
    )
    assert first.real_capital == REAL_CAPITAL == 0
    assert first.production_authority is False
    assert first.cross_vault_borrowing_allowed is False


def test_v3_starting_capital_is_constitution_truth_not_global_reset() -> None:
    default = _constitution()
    custom = _constitution(
        capital=Decimal("12345.67"),
        created_at_ms=1_001,
    )

    assert custom.starting_virtual_capital_usdt == Decimal("12345.67")
    assert custom.vault_identity != default.vault_identity
    with pytest.raises(ValueError, match="starting capital"):
        _constitution(capital=Decimal(0))


def test_v3_allocation_policy_allows_full_cash_and_forbids_forced_exposure() -> None:
    policy = build_paper_vault_v3_allocation_policy()

    assert policy.version == PAPER_VAULT_V3_ALLOCATION_POLICY_VERSION
    assert policy.permitted_books == (
        PaperVaultV3Book.CASH,
        PaperVaultV3Book.CORE,
        PaperVaultV3Book.OPPORTUNITY,
        PaperVaultV3Book.TACTICAL,
    )
    assert policy.minimum_market_exposure_fraction == Decimal(0)
    assert policy.maximum_market_exposure_fraction == Decimal(1)
    assert policy.cash_is_valid is True
    assert policy.cross_vault_borrowing_allowed is False
    assert policy.forced_deployment is False
    assert policy.production_authority is False
    assert policy.real_capital == 0
    assert len(policy.policy_identity) == 64

    with pytest.raises(ValueError, match="minimum market exposure"):
        replace(
            policy,
            minimum_market_exposure_fraction=Decimal("0.01"),
        )
    with pytest.raises(ValueError, match="maximum market exposure"):
        replace(
            policy,
            maximum_market_exposure_fraction=Decimal("0.50"),
        )
    with pytest.raises(ValueError, match="borrowing"):
        replace(policy, cross_vault_borrowing_allowed=True)
    with pytest.raises(ValueError, match="forced deployment"):
        replace(policy, forced_deployment=True)


def test_v3_store_is_separate_append_only_and_preserves_legacy_bytes(
    tmp_path: Path,
) -> None:
    epoch1 = tmp_path / EPOCH_1_LEDGER_FILENAME
    epoch2 = tmp_path / EPOCH_2_LEDGER_FILENAME
    epoch1.write_bytes(b"immutable-epoch-1-sentinel")
    epoch2.write_bytes(b"immutable-epoch-2-sentinel")
    epoch1_before = epoch1.read_bytes()
    epoch2_before = epoch2.read_bytes()

    store_path = tmp_path / "paper_vault_v3.sqlite3"
    store = PaperVaultV3Store(store_path)
    constitution = _constitution()

    assert store.append_constitution(constitution) is True
    assert store.append_constitution(constitution) is False
    assert store.read_constitution(constitution.vault_identity) == constitution
    assert store.list_constitutions() == (constitution,)
    assert (
        store.current_status(constitution.vault_identity)
        is PaperVaultV3Status.ACTIVE
    )

    assert epoch1.read_bytes() == epoch1_before
    assert epoch2.read_bytes() == epoch2_before

    with sqlite3.connect(store_path) as connection:
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable Paper Vault V3 truth",
        ):
            connection.execute(
                """
                UPDATE paper_vault_v3_constitutions
                SET created_at_ms = created_at_ms + 1
                WHERE vault_identity = ?
                """,
                (constitution.vault_identity,),
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable Paper Vault V3 truth",
        ):
            connection.execute(
                """
                DELETE FROM paper_vault_v3_constitutions
                WHERE vault_identity = ?
                """,
                (constitution.vault_identity,),
            )


def test_v3_lifecycle_is_append_only_stop_then_archive_with_no_reactivation(
    tmp_path: Path,
) -> None:
    store = PaperVaultV3Store(tmp_path / "paper_vault_v3.sqlite3")
    constitution = _constitution()
    assert store.append_constitution(constitution)

    stop = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.STOP,
        event_at_ms=1_100,
        previous_status=PaperVaultV3Status.ACTIVE,
        reason="user stopped this paper program",
    )
    assert store.append_lifecycle_event(stop) is True
    assert store.append_lifecycle_event(stop) is False
    assert (
        store.current_status(constitution.vault_identity)
        is PaperVaultV3Status.STOPPED
    )

    stale_archive = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.ARCHIVE,
        event_at_ms=1_200,
        previous_status=PaperVaultV3Status.ACTIVE,
        reason="stale transition attempt",
    )
    with pytest.raises(ValueError, match="previous status mismatch"):
        store.append_lifecycle_event(stale_archive)

    archive = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.ARCHIVE,
        event_at_ms=1_200,
        previous_status=PaperVaultV3Status.STOPPED,
        reason="archive stopped paper program",
    )
    assert store.append_lifecycle_event(archive) is True
    assert (
        store.current_status(constitution.vault_identity)
        is PaperVaultV3Status.ARCHIVED
    )
    assert store.read_lifecycle_events(constitution.vault_identity) == (
        stop,
        archive,
    )

    after_archive = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.ARCHIVE,
        event_at_ms=1_300,
        previous_status=PaperVaultV3Status.STOPPED,
        reason="cannot mutate archived program",
    )
    with pytest.raises(ValueError, match="previous status mismatch"):
        store.append_lifecycle_event(after_archive)

    with sqlite3.connect(store.path) as connection, pytest.raises(
        sqlite3.IntegrityError,
        match="immutable Paper Vault V3 truth",
    ):
        connection.execute(
            """
            DELETE FROM paper_vault_v3_lifecycle_events
            WHERE event_identity = ?
            """,
            (stop.event_identity,),
        )


def test_v3_can_archive_directly_from_active(tmp_path: Path) -> None:
    store = PaperVaultV3Store(tmp_path / "paper_vault_v3-direct.sqlite3")
    constitution = _constitution()
    assert store.append_constitution(constitution)

    archive = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.ARCHIVE,
        event_at_ms=1_100,
        previous_status=PaperVaultV3Status.ACTIVE,
        reason="archive active paper program",
    )
    assert store.append_lifecycle_event(archive)
    assert (
        store.current_status(constitution.vault_identity)
        is PaperVaultV3Status.ARCHIVED
    )


def test_v3_lifecycle_rejects_backfill_and_missing_constitution(
    tmp_path: Path,
) -> None:
    store = PaperVaultV3Store(tmp_path / "paper_vault_v3-life.sqlite3")
    constitution = _constitution(created_at_ms=2_000)
    store.initialize()

    missing_event = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.STOP,
        event_at_ms=2_100,
        previous_status=PaperVaultV3Status.ACTIVE,
        reason="missing constitution",
    )
    with pytest.raises(ValueError, match="requires constitution"):
        store.append_lifecycle_event(missing_event)

    assert store.append_constitution(constitution)
    backfill = build_paper_vault_v3_lifecycle_event(
        vault_identity=constitution.vault_identity,
        action=PaperVaultV3LifecycleAction.STOP,
        event_at_ms=1_999,
        previous_status=PaperVaultV3Status.ACTIVE,
        reason="backfill forbidden",
    )
    with pytest.raises(ValueError, match="predates constitution"):
        store.append_lifecycle_event(backfill)


def test_v3_missing_store_reads_are_noncreating(tmp_path: Path) -> None:
    path = tmp_path / "missing-paper-vault-v3.sqlite3"
    store = PaperVaultV3Store(path)
    constitution = _constitution()

    assert store.read_constitution(constitution.vault_identity) is None
    assert store.list_constitutions() == ()
    assert store.read_lifecycle_events(constitution.vault_identity) == ()
    assert store.current_status(constitution.vault_identity) is None
    assert not path.exists()


def test_v3_store_rejects_epoch1_and_epoch2_ledger_filenames(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="Epoch 1/2"):
        PaperVaultV3Store(tmp_path / EPOCH_1_LEDGER_FILENAME)
    with pytest.raises(ValueError, match="Epoch 1/2"):
        PaperVaultV3Store(tmp_path / EPOCH_2_LEDGER_FILENAME)


def test_v3_read_fails_closed_on_persisted_payload_corruption(
    tmp_path: Path,
) -> None:
    store = PaperVaultV3Store(tmp_path / "paper_vault_v3-corrupt.sqlite3")
    constitution = _constitution()
    assert store.append_constitution(constitution)

    with sqlite3.connect(store.path) as connection, connection:
        connection.execute(
            "DROP TRIGGER paper_vault_v3_constitutions_immutable_update"
        )
        connection.execute(
            """
            UPDATE paper_vault_v3_constitutions
            SET payload_json = payload_json || 'corrupt'
            WHERE vault_identity = ?
            """,
            (constitution.vault_identity,),
        )

    with pytest.raises(ValueError, match="payload digest mismatch"):
        store.read_constitution(constitution.vault_identity)


def test_v3_constitutions_can_coexist_without_reset_semantics(
    tmp_path: Path,
) -> None:
    store = PaperVaultV3Store(tmp_path / "paper_vault_v3-many.sqlite3")
    first = _constitution(created_at_ms=1_000, capital=Decimal(10000))
    second = _constitution(created_at_ms=2_000, capital=Decimal(25000))

    assert store.append_constitution(first)
    assert store.append_constitution(second)
    assert first.vault_identity != second.vault_identity
    assert store.list_constitutions() == (first, second)
    assert store.current_status(first.vault_identity) is PaperVaultV3Status.ACTIVE
    assert store.current_status(second.vault_identity) is PaperVaultV3Status.ACTIVE
