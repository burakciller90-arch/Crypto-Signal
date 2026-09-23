from __future__ import annotations

import hashlib
import inspect
import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.epoch2_accounting import (
    Epoch2CanonicalLedger,
    Epoch2MetricsStatus,
    build_consolidated_epoch2_snapshot,
    build_epoch2_vault_accounting_snapshot,
    initialize_epoch2_canonical_fund,
)
from crypto_signal.paper.epochs import (
    EPOCH_1_SPEC,
    EPOCH_2_SPEC,
    PaperVaultId,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperPosition,
    PaperSymbol,
    build_fund_creation,
)

ACTIVATED_AT = 1_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _epoch1(tmp_path):
    path = tmp_path / EPOCH_1_SPEC.ledger_filename
    ledger = PaperFundLedger(path)
    creation = build_fund_creation(created_at_ms=1)
    ledger.append_fund_creation(creation)
    return path, creation


def _activate(tmp_path):
    epoch1, creation = _epoch1(tmp_path)
    before = epoch1.read_bytes()
    state = initialize_epoch2_canonical_fund(
        epoch1_ledger_path=epoch1,
        epoch2_ledger_path=tmp_path / EPOCH_2_SPEC.ledger_filename,
        activated_at_ms=ACTIVATED_AT,
    )
    return epoch1, creation, before, state


def test_epoch2_activation_is_separate_idempotent_and_preserves_epoch1_bytes(tmp_path) -> None:
    epoch1, creation, before, state = _activate(tmp_path)
    epoch2_path = tmp_path / EPOCH_2_SPEC.ledger_filename

    assert creation.initial_cash_usdt == Decimal("100.00")
    assert epoch1.name == "paper_fund.sqlite3"
    assert epoch2_path.name == "paper_fund_epoch2.sqlite3"
    assert epoch1 != epoch2_path
    assert epoch1.read_bytes() == before
    assert (
        state.activation.epoch1_ledger_sha256
        == hashlib.sha256(before).hexdigest()
    )
    assert state.activation.starting_cash_usdt == Decimal("1000.00")
    assert state.activation.real_capital == REAL_CAPITAL == 0
    assert state.activation.leverage_allowed is False
    assert state.activation.borrowing_allowed is False
    assert state.activation.martingale_allowed is False

    by_vault = {item.vault_id: item for item in state.vault_snapshots}
    assert by_vault[PaperVaultId.CORE].cash_usdt == Decimal("600.00")
    assert by_vault[PaperVaultId.TACTICAL].cash_usdt == Decimal("300.00")
    assert (
        by_vault[PaperVaultId.OPPORTUNITY_RESERVE].cash_usdt
        == Decimal("100.00")
    )
    for item in state.vault_snapshots:
        assert item.positions == ()
        assert item.marked_exposure_usdt == 0
        assert item.nav_usdt == item.starting_cash_usdt
        assert item.closed_trade_count == 0
        assert item.expectancy_usdt_per_closed_trade is None
        assert item.metrics_status is Epoch2MetricsStatus.NOT_YET_MEASURED
        assert item.previous_snapshot_identity is None

    parent = state.consolidated_snapshot
    assert parent.cash_usdt == Decimal("1000.00")
    assert parent.marked_exposure_usdt == 0
    assert parent.nav_usdt == Decimal("1000.00")
    assert parent.realized_pnl_usdt == 0
    assert parent.unrealized_pnl_usdt == 0
    assert parent.drawdown_fraction == 0
    assert parent.closed_trade_count == 0
    assert parent.expectancy_usdt_per_closed_trade is None
    assert parent.metrics_status is Epoch2MetricsStatus.NOT_YET_MEASURED
    assert parent.previous_snapshot_identity is None

    second = initialize_epoch2_canonical_fund(
        epoch1_ledger_path=epoch1,
        epoch2_ledger_path=epoch2_path,
        activated_at_ms=ACTIVATED_AT,
    )
    assert second == state
    assert epoch1.read_bytes() == before


def test_epoch2_accounting_tracks_vault_and_consolidated_truth(tmp_path) -> None:
    _, _, _, initial = _activate(tmp_path)
    ledger = Epoch2CanonicalLedger(tmp_path / EPOCH_2_SPEC.ledger_filename)
    activation = initial.activation
    previous = {item.vault_id: item for item in initial.vault_snapshots}

    core = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal("500"),
        positions=(PaperPosition(PaperSymbol.BTCUSDT, Decimal("1")),),
        marked_exposure_usdt=Decimal("110"),
        realized_pnl_usdt=Decimal("5"),
        unrealized_pnl_usdt=Decimal("5"),
        fee_usdt=Decimal("1"),
        spread_usdt=Decimal("0.5"),
        slippage_usdt=Decimal("0.5"),
        turnover_notional_usdt=Decimal("200"),
        closed_trade_count=1,
        win_count=1,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(("WIN", 1),),
        source_record_identities=(_sha("core-tx"),),
        previous=previous[PaperVaultId.CORE],
    )
    tactical = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.TACTICAL,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal("250"),
        positions=(PaperPosition(PaperSymbol.ETHUSDT, Decimal("1")),),
        marked_exposure_usdt=Decimal("45"),
        realized_pnl_usdt=Decimal("-3"),
        unrealized_pnl_usdt=Decimal("-2"),
        fee_usdt=Decimal("0.4"),
        spread_usdt=Decimal("0.3"),
        slippage_usdt=Decimal("0.3"),
        turnover_notional_usdt=Decimal("100"),
        closed_trade_count=1,
        win_count=0,
        loss_count=1,
        breakeven_count=0,
        outcome_distribution=(("LOSS", 1),),
        source_record_identities=(_sha("tactical-tx"),),
        previous=previous[PaperVaultId.TACTICAL],
    )
    reserve = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.OPPORTUNITY_RESERVE,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal("100"),
        positions=(),
        marked_exposure_usdt=Decimal(0),
        realized_pnl_usdt=Decimal(0),
        unrealized_pnl_usdt=Decimal(0),
        fee_usdt=Decimal(0),
        spread_usdt=Decimal(0),
        slippage_usdt=Decimal(0),
        turnover_notional_usdt=Decimal(0),
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(),
        source_record_identities=(_sha("reserve-hold-cash"),),
        previous=previous[PaperVaultId.OPPORTUNITY_RESERVE],
    )

    for item in (core, tactical, reserve):
        assert ledger.append_vault_snapshot(item) is True

    parent = build_consolidated_epoch2_snapshot(
        (core, tactical, reserve),
        previous=initial.consolidated_snapshot,
    )
    assert ledger.append_consolidated_snapshot(parent) is True

    assert parent.cash_usdt == Decimal("850")
    assert parent.marked_exposure_usdt == Decimal("155")
    assert parent.nav_usdt == Decimal("1005")
    assert parent.realized_pnl_usdt == Decimal("2")
    assert parent.unrealized_pnl_usdt == Decimal("3")
    assert parent.high_water_nav_usdt == Decimal("1005")
    assert parent.drawdown_fraction == 0
    assert parent.fee_usdt == Decimal("1.4")
    assert parent.spread_usdt == Decimal("0.8")
    assert parent.slippage_usdt == Decimal("0.8")
    assert parent.turnover_notional_usdt == Decimal("300")
    assert parent.turnover_fraction == Decimal("0.3")
    assert parent.closed_trade_count == 2
    assert parent.win_count == 1
    assert parent.loss_count == 1
    assert parent.expectancy_usdt_per_closed_trade == Decimal("1")
    assert parent.outcome_distribution == (("LOSS", 1), ("WIN", 1))
    assert parent.metrics_status is Epoch2MetricsStatus.AVAILABLE

    state = ledger.read_state()
    assert state.consolidated_snapshot == parent
    assert tuple(item.snapshot_identity for item in state.vault_snapshots) == tuple(
        sorted(
            (core, tactical, reserve),
            key=lambda item: item.vault_id.value,
        )[index].snapshot_identity
        for index in range(3)
    )


def test_parent_high_water_uses_parent_history_not_sum_of_vault_peaks(tmp_path) -> None:
    _, _, _, initial = _activate(tmp_path)
    ledger = Epoch2CanonicalLedger(tmp_path / EPOCH_2_SPEC.ledger_filename)
    activation = initial.activation
    first_by_vault = {item.vault_id: item for item in initial.vault_snapshots}

    def snap(
        vault: PaperVaultId,
        previous,
        cash: str,
        exposure: str,
        realized: str,
        unrealized: str,
        source: str,
    ):
        return build_epoch2_vault_accounting_snapshot(
            activation,
            vault_id=vault,
            snapshot_at_ms=2_000,
            cash_usdt=Decimal(cash),
            positions=(),
            marked_exposure_usdt=Decimal(exposure),
            realized_pnl_usdt=Decimal(realized),
            unrealized_pnl_usdt=Decimal(unrealized),
            fee_usdt=Decimal(0),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
            turnover_notional_usdt=Decimal(0),
            closed_trade_count=0,
            win_count=0,
            loss_count=0,
            breakeven_count=0,
            outcome_distribution=(),
            source_record_identities=(_sha(source),),
            previous=previous,
        )

    core_up = snap(
        PaperVaultId.CORE,
        first_by_vault[PaperVaultId.CORE],
        "610",
        "0",
        "5",
        "5",
        "core-up",
    )
    tactical_down = snap(
        PaperVaultId.TACTICAL,
        first_by_vault[PaperVaultId.TACTICAL],
        "295",
        "0",
        "-3",
        "-2",
        "tactical-down",
    )
    reserve_flat = snap(
        PaperVaultId.OPPORTUNITY_RESERVE,
        first_by_vault[PaperVaultId.OPPORTUNITY_RESERVE],
        "100",
        "0",
        "0",
        "0",
        "reserve-flat",
    )
    for item in (core_up, tactical_down, reserve_flat):
        ledger.append_vault_snapshot(item)
    peak = build_consolidated_epoch2_snapshot(
        (core_up, tactical_down, reserve_flat),
        previous=initial.consolidated_snapshot,
    )
    ledger.append_consolidated_snapshot(peak)
    assert peak.nav_usdt == Decimal("1005")
    assert peak.high_water_nav_usdt == Decimal("1005")

    second_by_vault = {item.vault_id: item for item in (core_up, tactical_down, reserve_flat)}

    def down(
        vault: PaperVaultId,
        cash: str,
        realized: str,
        unrealized: str,
        source: str,
    ):
        return build_epoch2_vault_accounting_snapshot(
            activation,
            vault_id=vault,
            snapshot_at_ms=3_000,
            cash_usdt=Decimal(cash),
            positions=(),
            marked_exposure_usdt=Decimal(0),
            realized_pnl_usdt=Decimal(realized),
            unrealized_pnl_usdt=Decimal(unrealized),
            fee_usdt=Decimal(0),
            spread_usdt=Decimal(0),
            slippage_usdt=Decimal(0),
            turnover_notional_usdt=Decimal(0),
            closed_trade_count=0,
            win_count=0,
            loss_count=0,
            breakeven_count=0,
            outcome_distribution=(),
            source_record_identities=(_sha(source),),
            previous=second_by_vault[vault],
        )

    core_down = down(PaperVaultId.CORE, "590", "5", "-15", "core-down")
    tactical_down2 = down(
        PaperVaultId.TACTICAL,
        "290",
        "-3",
        "-7",
        "tactical-down2",
    )
    reserve_flat2 = down(
        PaperVaultId.OPPORTUNITY_RESERVE,
        "100",
        "0",
        "0",
        "reserve-flat2",
    )
    for item in (core_down, tactical_down2, reserve_flat2):
        ledger.append_vault_snapshot(item)
    drawdown = build_consolidated_epoch2_snapshot(
        (core_down, tactical_down2, reserve_flat2),
        previous=peak,
    )
    ledger.append_consolidated_snapshot(drawdown)

    assert drawdown.nav_usdt == Decimal("980")
    assert drawdown.high_water_nav_usdt == Decimal("1005")
    assert drawdown.drawdown_fraction == Decimal(25) / Decimal(1005)
    assert ledger.read_state().consolidated_snapshot == drawdown


def test_stale_snapshot_lineage_backfill_and_same_timestamp_forks_fail_closed(tmp_path) -> None:
    _, _, _, initial = _activate(tmp_path)
    ledger = Epoch2CanonicalLedger(tmp_path / EPOCH_2_SPEC.ledger_filename)
    activation = initial.activation
    core0 = next(
        item
        for item in initial.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )

    core1 = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=2_000,
        cash_usdt=Decimal("600"),
        positions=(),
        marked_exposure_usdt=Decimal(0),
        realized_pnl_usdt=Decimal(0),
        unrealized_pnl_usdt=Decimal(0),
        fee_usdt=Decimal(0),
        spread_usdt=Decimal(0),
        slippage_usdt=Decimal(0),
        turnover_notional_usdt=Decimal(0),
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(),
        source_record_identities=(_sha("core1"),),
        previous=core0,
    )
    ledger.append_vault_snapshot(core1)

    stale = build_epoch2_vault_accounting_snapshot(
        activation,
        vault_id=PaperVaultId.CORE,
        snapshot_at_ms=2_500,
        cash_usdt=Decimal("600"),
        positions=(),
        marked_exposure_usdt=Decimal(0),
        realized_pnl_usdt=Decimal(0),
        unrealized_pnl_usdt=Decimal(0),
        fee_usdt=Decimal(0),
        spread_usdt=Decimal(0),
        slippage_usdt=Decimal(0),
        turnover_notional_usdt=Decimal(0),
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        outcome_distribution=(),
        source_record_identities=(_sha("stale"),),
        previous=core0,
    )
    with pytest.raises(ValueError, match="previous lineage mismatch"):
        ledger.append_vault_snapshot(stale)

    fork = replace(
        core1,
        snapshot_identity=_sha("fork"),
        source_record_identities=(_sha("fork-source"),),
    )
    with pytest.raises(ValueError):
        ledger.append_vault_snapshot(fork)


def test_sqlite_r21_tables_are_update_delete_immutable(tmp_path) -> None:
    _, _, _, _ = _activate(tmp_path)
    path = tmp_path / EPOCH_2_SPEC.ledger_filename

    with sqlite3.connect(path) as connection:
        for table in (
            "r21_epoch2_activation",
            "r21_vault_snapshots",
            "r21_consolidated_snapshots",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable R21 paper ledger"):
                connection.execute(f"DELETE FROM {table}")


def test_epoch2_activation_rejects_missing_or_shared_epoch1_path(tmp_path) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError, match="requires existing immutable Epoch1 ledger"):
        initialize_epoch2_canonical_fund(
            epoch1_ledger_path=missing,
            epoch2_ledger_path=tmp_path / EPOCH_2_SPEC.ledger_filename,
            activated_at_ms=ACTIVATED_AT,
        )

    epoch1, _ = _epoch1(tmp_path)
    with pytest.raises(ValueError, match="must remain separate"):
        initialize_epoch2_canonical_fund(
            epoch1_ledger_path=epoch1,
            epoch2_ledger_path=epoch1,
            activated_at_ms=ACTIVATED_AT,
        )


def test_r21_accounting_has_no_real_order_network_or_cross_vault_transfer_surface() -> None:
    from crypto_signal.paper import epoch2_accounting

    source = inspect.getsource(epoch2_accounting).lower()
    forbidden = (
        "place_order",
        "submit_order",
        "real_exchange",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "cross_vault_transfer",
        "borrow_from_vault",
        "martingale",
        "leverage_ratio",
    )
    assert all(token not in source for token in forbidden)
    assert epoch2_accounting.REAL_CAPITAL == 0
