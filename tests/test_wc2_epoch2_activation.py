from __future__ import annotations

from pathlib import Path

import pytest

from crypto_signal.paper.epoch2_accounting import read_epoch2_state_read_only
from crypto_signal.paper.epochs import EPOCH_1_SPEC, EPOCH_2_SPEC, PaperVaultId
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import build_fund_creation
from ops.activate_wc2_epoch2 import (
    WC2Epoch2ActivationStatus,
    activate_wc2_epoch2,
)


def _epoch1(tmp_path: Path) -> Path:
    path = tmp_path / EPOCH_1_SPEC.ledger_filename
    ledger = PaperFundLedger(path)
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return path


def test_wc2_epoch2_activation_is_exact_and_preserves_epoch1_bytes(
    tmp_path: Path,
) -> None:
    epoch1 = _epoch1(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename
    epoch1_before = epoch1.read_bytes()

    result = activate_wc2_epoch2(
        epoch1_ledger_path=epoch1,
        epoch2_ledger_path=epoch2,
        activated_at_ms=2_000,
    )

    assert result.status is WC2Epoch2ActivationStatus.INSERTED
    assert epoch1.read_bytes() == epoch1_before
    assert result.state.activation.activated_at_ms == 2_000
    assert result.state.activation.starting_cash_usdt == (
        EPOCH_2_SPEC.starting_cash_usdt
    )
    assert dict(result.state.activation.vault_starting_cash) == {
        item.vault_id: item.starting_cash_usdt
        for item in EPOCH_2_SPEC.vault_allocations
    }
    assert result.state.activation.real_capital == 0
    assert result.state.activation.leverage_allowed is False
    assert result.state.activation.borrowing_allowed is False
    assert result.state.activation.martingale_allowed is False

    vaults = {item.vault_id: item for item in result.state.vault_snapshots}
    assert vaults[PaperVaultId.CORE].cash_usdt == 600
    assert vaults[PaperVaultId.TACTICAL].cash_usdt == 300
    assert vaults[PaperVaultId.OPPORTUNITY_RESERVE].cash_usdt == 100
    assert all(not item.positions for item in vaults.values())
    assert result.state.consolidated_snapshot.nav_usdt == 1_000
    assert read_epoch2_state_read_only(epoch2) == result.state


def test_wc2_epoch2_second_activation_is_read_only_and_keeps_original_time(
    tmp_path: Path,
) -> None:
    epoch1 = _epoch1(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename

    first = activate_wc2_epoch2(
        epoch1_ledger_path=epoch1,
        epoch2_ledger_path=epoch2,
        activated_at_ms=2_000,
    )
    epoch1_before = epoch1.read_bytes()
    epoch2_before = epoch2.read_bytes()

    second = activate_wc2_epoch2(
        epoch1_ledger_path=epoch1,
        epoch2_ledger_path=epoch2,
        activated_at_ms=999_999,
    )

    assert second.status is WC2Epoch2ActivationStatus.UNCHANGED
    assert second.state == first.state
    assert second.state.activation.activated_at_ms == 2_000
    assert epoch1.read_bytes() == epoch1_before
    assert epoch2.read_bytes() == epoch2_before
    assert second.epoch2_sha256_before == second.epoch2_sha256_after


def test_wc2_epoch2_requires_existing_immutable_epoch1(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires existing Epoch1"):
        activate_wc2_epoch2(
            epoch1_ledger_path=tmp_path / EPOCH_1_SPEC.ledger_filename,
            epoch2_ledger_path=tmp_path / EPOCH_2_SPEC.ledger_filename,
            activated_at_ms=2_000,
        )


def test_wc2_epoch2_refuses_malformed_existing_epoch2(tmp_path: Path) -> None:
    epoch1 = _epoch1(tmp_path)
    epoch2 = tmp_path / EPOCH_2_SPEC.ledger_filename
    epoch2.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(ValueError):
        activate_wc2_epoch2(
            epoch1_ledger_path=epoch1,
            epoch2_ledger_path=epoch2,
            activated_at_ms=2_000,
        )
