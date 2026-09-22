from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper import (
    EPOCH_1_ID,
    EPOCH_1_LEDGER_FILENAME,
    EPOCH_1_SPEC,
    EPOCH_2_ID,
    EPOCH_2_LEDGER_FILENAME,
    EPOCH_2_SPEC,
    INITIAL_CASH_USDT,
    PAPER_EPOCHS,
    REAL_CAPITAL,
    PaperEpochStatus,
    PaperFundEpochSpec,
    PaperVaultAllocation,
    PaperVaultId,
    assert_legacy_epoch1_fund_creation,
    build_fund_creation,
    current_paper_epoch_spec,
    paper_epoch_ledger_path,
    paper_epoch_spec,
)


def test_legacy_epoch1_remains_exactly_original_100_usdt_contract() -> None:
    assert INITIAL_CASH_USDT == Decimal("100.00")
    assert EPOCH_1_SPEC.epoch_id == EPOCH_1_ID
    assert EPOCH_1_SPEC.status is PaperEpochStatus.LEGACY
    assert EPOCH_1_SPEC.starting_cash_usdt == Decimal("100.00")
    assert EPOCH_1_SPEC.ledger_filename == EPOCH_1_LEDGER_FILENAME
    assert EPOCH_1_SPEC.vault_allocations == ()
    assert EPOCH_1_SPEC.canonical_for_new_activity is False

    legacy = build_fund_creation(created_at_ms=1_700_000_000_000)
    assert legacy.initial_cash_usdt == Decimal("100.00")
    assert_legacy_epoch1_fund_creation(legacy)


def test_epoch2_is_current_separate_1000_usdt_contract() -> None:
    assert REAL_CAPITAL == 0
    assert EPOCH_2_SPEC.epoch_id == EPOCH_2_ID
    assert EPOCH_2_SPEC.status is PaperEpochStatus.CURRENT
    assert EPOCH_2_SPEC.predecessor_epoch_id == EPOCH_1_ID
    assert EPOCH_2_SPEC.starting_cash_usdt == Decimal("1000.00")
    assert EPOCH_2_SPEC.ledger_filename == EPOCH_2_LEDGER_FILENAME
    assert EPOCH_2_SPEC.ledger_filename != EPOCH_1_SPEC.ledger_filename
    assert EPOCH_2_SPEC.canonical_for_new_activity is True
    assert EPOCH_2_SPEC.real_capital == 0
    assert EPOCH_2_SPEC.leverage_allowed is False
    assert EPOCH_2_SPEC.borrowing_allowed is False
    assert EPOCH_2_SPEC.martingale_allowed is False


def test_epoch2_vaults_are_exact_600_300_100_and_sum_to_1000() -> None:
    by_id = {
        allocation.vault_id: allocation.starting_cash_usdt
        for allocation in EPOCH_2_SPEC.vault_allocations
    }
    assert by_id == {
        PaperVaultId.CORE: Decimal("600.00"),
        PaperVaultId.TACTICAL: Decimal("300.00"),
        PaperVaultId.OPPORTUNITY_RESERVE: Decimal("100.00"),
    }
    assert sum(by_id.values(), start=Decimal(0)) == Decimal("1000.00")


def test_epoch_registry_has_one_current_epoch_and_stable_identity() -> None:
    assert PAPER_EPOCHS == (EPOCH_1_SPEC, EPOCH_2_SPEC)
    assert current_paper_epoch_spec() is EPOCH_2_SPEC
    assert paper_epoch_spec(EPOCH_1_ID) is EPOCH_1_SPEC
    assert paper_epoch_spec(EPOCH_2_ID) is EPOCH_2_SPEC
    assert len(EPOCH_1_SPEC.epoch_identity) == 64
    assert len(EPOCH_2_SPEC.epoch_identity) == 64
    assert EPOCH_1_SPEC.epoch_identity != EPOCH_2_SPEC.epoch_identity
    assert EPOCH_2_SPEC.epoch_identity == EPOCH_2_SPEC.epoch_identity


def test_epoch2_uses_separate_ledger_path_without_repointing_legacy() -> None:
    root = Path("/tmp/paper")
    assert paper_epoch_ledger_path(root) == root / EPOCH_2_LEDGER_FILENAME
    assert (
        paper_epoch_ledger_path(root, epoch=EPOCH_1_SPEC)
        == root / EPOCH_1_LEDGER_FILENAME
    )
    assert (
        paper_epoch_ledger_path(root, epoch=EPOCH_2_SPEC)
        == root / EPOCH_2_LEDGER_FILENAME
    )


def test_invalid_current_epoch_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="sum to starting cash"):
        PaperFundEpochSpec(
            epoch_id="bad",
            status=PaperEpochStatus.CURRENT,
            starting_cash_usdt=Decimal(1000),
            ledger_filename="bad.sqlite3",
            predecessor_epoch_id=EPOCH_1_ID,
            vault_allocations=(
                PaperVaultAllocation(PaperVaultId.CORE, Decimal(600)),
                PaperVaultAllocation(PaperVaultId.TACTICAL, Decimal(300)),
            ),
            canonical_for_new_activity=True,
        )

    with pytest.raises(ValueError, match="REAL_CAPITAL"):
        PaperFundEpochSpec(
            epoch_id="bad-real",
            status=PaperEpochStatus.CURRENT,
            starting_cash_usdt=Decimal(1000),
            ledger_filename="bad-real.sqlite3",
            predecessor_epoch_id=EPOCH_1_ID,
            vault_allocations=(
                PaperVaultAllocation(PaperVaultId.CORE, Decimal(1000)),
            ),
            canonical_for_new_activity=True,
            real_capital=1,
        )

    with pytest.raises(ValueError, match="cannot enable leverage"):
        PaperFundEpochSpec(
            epoch_id="bad-leverage",
            status=PaperEpochStatus.CURRENT,
            starting_cash_usdt=Decimal(1000),
            ledger_filename="bad-leverage.sqlite3",
            predecessor_epoch_id=EPOCH_1_ID,
            vault_allocations=(
                PaperVaultAllocation(PaperVaultId.CORE, Decimal(1000)),
            ),
            canonical_for_new_activity=True,
            leverage_allowed=True,
        )


def test_unknown_epoch_id_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown paper epoch"):
        paper_epoch_spec("does-not-exist")
