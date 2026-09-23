from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.epochs import (
    EPOCH_1_SPEC,
    EPOCH_2_SPEC,
    PaperVaultId,
    assert_legacy_epoch1_fund_creation,
)
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    FundCreationRecord,
    PaperPosition,
    PaperSymbol,
    normalize_positions,
)
from crypto_signal.paper.portfolio import read_paper_entries_read_only

R21_ENGINE_VERSION = "r21-canonical-paper-fund-v1-slice1/1"
R21_SCHEMA_VERSION = "r21-canonical-paper-fund-v1/1"


class Epoch2MetricsStatus(StrEnum):
    NOT_YET_MEASURED = "not_yet_measured"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True)
class Epoch2ActivationRecord:
    activation_identity: str
    schema_version: str
    engine_version: str
    epoch_identity: str
    predecessor_epoch_identity: str
    activated_at_ms: int
    starting_cash_usdt: Decimal
    vault_starting_cash: tuple[tuple[PaperVaultId, Decimal], ...]
    epoch1_ledger_sha256: str
    real_capital: int = REAL_CAPITAL
    leverage_allowed: bool = False
    borrowing_allowed: bool = False
    martingale_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.activation_identity, "R21 activation identity")
        _require_sha256(self.epoch_identity, "R21 epoch identity")
        _require_sha256(
            self.predecessor_epoch_identity,
            "R21 predecessor epoch identity",
        )
        _require_sha256(self.epoch1_ledger_sha256, "R21 Epoch1 ledger SHA256")
        if self.schema_version != R21_SCHEMA_VERSION:
            raise ValueError("unsupported R21 activation schema")
        if self.engine_version != R21_ENGINE_VERSION:
            raise ValueError("unsupported R21 activation engine")
        if self.epoch_identity != EPOCH_2_SPEC.epoch_identity:
            raise ValueError("R21 activation must target accepted Epoch2")
        if self.predecessor_epoch_identity != EPOCH_1_SPEC.epoch_identity:
            raise ValueError("R21 activation predecessor must be immutable Epoch1")
        if self.activated_at_ms < 0:
            raise ValueError("R21 activation time must be non-negative")
        if self.starting_cash_usdt != EPOCH_2_SPEC.starting_cash_usdt:
            raise ValueError("R21 starting cash must equal accepted Epoch2")
        expected = tuple(
            sorted(
                (
                    (item.vault_id, item.starting_cash_usdt)
                    for item in EPOCH_2_SPEC.vault_allocations
                ),
                key=lambda item: item[0].value,
            )
        )
        if self.vault_starting_cash != expected:
            raise ValueError("R21 vault starting cash must be exact 600/300/100")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.leverage_allowed or self.borrowing_allowed or self.martingale_allowed:
            raise ValueError("R21 canonical paper fund forbids leverage/borrowing/martingale")
        if self.activation_identity != canonical_sha256(_activation_payload(self)):
            raise ValueError("R21 activation identity mismatch")


@dataclass(frozen=True, slots=True)
class Epoch2VaultAccountingSnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    activation_identity: str
    vault_id: PaperVaultId
    snapshot_at_ms: int
    starting_cash_usdt: Decimal
    cash_usdt: Decimal
    positions: tuple[PaperPosition, ...]
    marked_exposure_usdt: Decimal
    nav_usdt: Decimal
    realized_pnl_usdt: Decimal
    unrealized_pnl_usdt: Decimal
    high_water_nav_usdt: Decimal
    drawdown_fraction: Decimal
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    turnover_notional_usdt: Decimal
    turnover_fraction: Decimal
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    expectancy_usdt_per_closed_trade: Decimal | None
    outcome_distribution: tuple[tuple[str, int], ...]
    metrics_status: Epoch2MetricsStatus
    source_record_identities: tuple[str, ...]
    previous_snapshot_identity: str | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "R21 vault snapshot identity")
        _require_sha256(self.activation_identity, "R21 vault activation identity")
        if self.schema_version != R21_SCHEMA_VERSION:
            raise ValueError("unsupported R21 vault snapshot schema")
        if self.engine_version != R21_ENGINE_VERSION:
            raise ValueError("unsupported R21 vault snapshot engine")
        if self.snapshot_at_ms < 0:
            raise ValueError("R21 vault snapshot time must be non-negative")
        expected_budget = {
            item.vault_id: item.starting_cash_usdt
            for item in EPOCH_2_SPEC.vault_allocations
        }[self.vault_id]
        if self.starting_cash_usdt != expected_budget:
            raise ValueError("R21 vault starting cash mismatch")
        for value, label in (
            (self.cash_usdt, "cash"),
            (self.marked_exposure_usdt, "marked exposure"),
            (self.nav_usdt, "NAV"),
            (self.high_water_nav_usdt, "high-water NAV"),
            (self.drawdown_fraction, "drawdown"),
            (self.fee_usdt, "fees"),
            (self.spread_usdt, "spread"),
            (self.slippage_usdt, "slippage"),
            (self.turnover_notional_usdt, "turnover notional"),
            (self.turnover_fraction, "turnover fraction"),
        ):
            _require_non_negative_decimal(value, f"R21 vault {label}")
        for value, label in (
            (self.realized_pnl_usdt, "realized PnL"),
            (self.unrealized_pnl_usdt, "unrealized PnL"),
        ):
            _require_finite_decimal(value, f"R21 vault {label}")
        if self.positions != normalize_positions(self.positions):
            raise ValueError("R21 vault positions must be normalized")
        if self.nav_usdt != self.cash_usdt + self.marked_exposure_usdt:
            raise ValueError("R21 vault NAV must equal cash plus marked exposure")
        if (
            self.nav_usdt
            != self.starting_cash_usdt
            + self.realized_pnl_usdt
            + self.unrealized_pnl_usdt
        ):
            raise ValueError("R21 vault NAV/PnL reconciliation mismatch")
        if self.high_water_nav_usdt < self.nav_usdt:
            raise ValueError("R21 high-water NAV cannot be below current NAV")
        expected_drawdown = (
            Decimal(0)
            if self.high_water_nav_usdt == Decimal(0)
            else (self.high_water_nav_usdt - self.nav_usdt)
            / self.high_water_nav_usdt
        )
        if self.drawdown_fraction != expected_drawdown:
            raise ValueError("R21 vault drawdown mismatch")
        expected_turnover = self.turnover_notional_usdt / self.starting_cash_usdt
        if self.turnover_fraction != expected_turnover:
            raise ValueError("R21 vault turnover fraction mismatch")
        if min(
            self.closed_trade_count,
            self.win_count,
            self.loss_count,
            self.breakeven_count,
        ) < 0:
            raise ValueError("R21 vault trade counts cannot be negative")
        if (
            self.win_count + self.loss_count + self.breakeven_count
            != self.closed_trade_count
        ):
            raise ValueError("R21 vault trade outcome counts do not reconcile")
        _require_outcome_distribution(
            self.outcome_distribution,
            self.closed_trade_count,
        )
        if self.closed_trade_count == 0:
            if self.realized_pnl_usdt != Decimal(0):
                raise ValueError("R21 vault cannot realize PnL without closed trades")
            if self.metrics_status is not Epoch2MetricsStatus.NOT_YET_MEASURED:
                raise ValueError("R21 empty vault performance must be NOT_YET_MEASURED")
            if self.expectancy_usdt_per_closed_trade is not None:
                raise ValueError("R21 unmeasured expectancy must be None")
        else:
            if self.metrics_status is not Epoch2MetricsStatus.AVAILABLE:
                raise ValueError("R21 measured vault performance must be AVAILABLE")
            if self.expectancy_usdt_per_closed_trade is None:
                raise ValueError("R21 measured vault requires expectancy")
            _require_finite_decimal(
                self.expectancy_usdt_per_closed_trade,
                "R21 vault expectancy",
            )
        _require_identity_tuple(
            self.source_record_identities,
            "R21 vault source record",
        )
        if self.previous_snapshot_identity is not None:
            _require_sha256(
                self.previous_snapshot_identity,
                "R21 vault previous snapshot identity",
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(_vault_snapshot_payload(self)):
            raise ValueError("R21 vault snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class Epoch2ConsolidatedAccountingSnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    activation_identity: str
    snapshot_at_ms: int
    vault_snapshot_identities: tuple[str, ...]
    cash_usdt: Decimal
    marked_exposure_usdt: Decimal
    nav_usdt: Decimal
    realized_pnl_usdt: Decimal
    unrealized_pnl_usdt: Decimal
    high_water_nav_usdt: Decimal
    drawdown_fraction: Decimal
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    turnover_notional_usdt: Decimal
    turnover_fraction: Decimal
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    expectancy_usdt_per_closed_trade: Decimal | None
    outcome_distribution: tuple[tuple[str, int], ...]
    metrics_status: Epoch2MetricsStatus
    previous_snapshot_identity: str | None
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "R21 consolidated snapshot identity")
        _require_sha256(self.activation_identity, "R21 consolidated activation identity")
        if self.schema_version != R21_SCHEMA_VERSION:
            raise ValueError("unsupported R21 consolidated snapshot schema")
        if self.engine_version != R21_ENGINE_VERSION:
            raise ValueError("unsupported R21 consolidated snapshot engine")
        if self.snapshot_at_ms < 0:
            raise ValueError("R21 consolidated snapshot time must be non-negative")
        _require_identity_tuple(
            self.vault_snapshot_identities,
            "R21 consolidated vault snapshot",
        )
        if self.previous_snapshot_identity is not None:
            _require_sha256(
                self.previous_snapshot_identity,
                "R21 consolidated previous snapshot identity",
            )
        if len(self.vault_snapshot_identities) != len(PaperVaultId):
            raise ValueError("R21 consolidated snapshot requires exactly three vaults")
        for value, label in (
            (self.cash_usdt, "cash"),
            (self.marked_exposure_usdt, "marked exposure"),
            (self.nav_usdt, "NAV"),
            (self.high_water_nav_usdt, "high-water NAV"),
            (self.drawdown_fraction, "drawdown"),
            (self.fee_usdt, "fees"),
            (self.spread_usdt, "spread"),
            (self.slippage_usdt, "slippage"),
            (self.turnover_notional_usdt, "turnover notional"),
            (self.turnover_fraction, "turnover fraction"),
        ):
            _require_non_negative_decimal(value, f"R21 consolidated {label}")
        for value, label in (
            (self.realized_pnl_usdt, "realized PnL"),
            (self.unrealized_pnl_usdt, "unrealized PnL"),
        ):
            _require_finite_decimal(value, f"R21 consolidated {label}")
        if self.nav_usdt != self.cash_usdt + self.marked_exposure_usdt:
            raise ValueError("R21 consolidated NAV must equal cash plus exposure")
        if (
            self.nav_usdt
            != EPOCH_2_SPEC.starting_cash_usdt
            + self.realized_pnl_usdt
            + self.unrealized_pnl_usdt
        ):
            raise ValueError("R21 consolidated NAV/PnL reconciliation mismatch")
        if self.high_water_nav_usdt < self.nav_usdt:
            raise ValueError("R21 consolidated high-water NAV below NAV")
        expected_drawdown = (
            Decimal(0)
            if self.high_water_nav_usdt == Decimal(0)
            else (self.high_water_nav_usdt - self.nav_usdt)
            / self.high_water_nav_usdt
        )
        if self.drawdown_fraction != expected_drawdown:
            raise ValueError("R21 consolidated drawdown mismatch")
        expected_turnover = (
            self.turnover_notional_usdt / EPOCH_2_SPEC.starting_cash_usdt
        )
        if self.turnover_fraction != expected_turnover:
            raise ValueError("R21 consolidated turnover mismatch")
        if min(
            self.closed_trade_count,
            self.win_count,
            self.loss_count,
            self.breakeven_count,
        ) < 0:
            raise ValueError("R21 consolidated trade counts cannot be negative")
        if (
            self.win_count + self.loss_count + self.breakeven_count
            != self.closed_trade_count
        ):
            raise ValueError("R21 consolidated trade outcome counts do not reconcile")
        _require_outcome_distribution(
            self.outcome_distribution,
            self.closed_trade_count,
        )
        if self.closed_trade_count == 0:
            if self.realized_pnl_usdt != Decimal(0):
                raise ValueError(
                    "R21 consolidated cannot realize PnL without closed trades"
                )
            if self.metrics_status is not Epoch2MetricsStatus.NOT_YET_MEASURED:
                raise ValueError("R21 empty consolidated metrics must be NOT_YET_MEASURED")
            if self.expectancy_usdt_per_closed_trade is not None:
                raise ValueError("R21 empty consolidated expectancy must be None")
        else:
            if self.metrics_status is not Epoch2MetricsStatus.AVAILABLE:
                raise ValueError("R21 measured consolidated metrics must be AVAILABLE")
            if self.expectancy_usdt_per_closed_trade is None:
                raise ValueError("R21 measured consolidated requires expectancy")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(
            _consolidated_snapshot_payload(self)
        ):
            raise ValueError("R21 consolidated snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class Epoch2LedgerState:
    activation: Epoch2ActivationRecord
    vault_snapshots: tuple[Epoch2VaultAccountingSnapshot, ...]
    consolidated_snapshot: Epoch2ConsolidatedAccountingSnapshot


class Epoch2CanonicalLedger:
    """Append-only R21 accounting ledger inside the separate Epoch2 DB."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS r21_epoch2_activation (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    activation_identity TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    activated_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS r21_vault_snapshots (
                    snapshot_identity TEXT PRIMARY KEY,
                    vault_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    snapshot_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS r21_consolidated_snapshots (
                    snapshot_identity TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    snapshot_at_ms INTEGER NOT NULL
                )
                """
            )
            self._install_immutability_triggers(connection)

    def activate(self, record: Epoch2ActivationRecord) -> bool:
        self.initialize()
        payload = canonical_json(record)
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                """
                SELECT activation_identity, payload_json, activated_at_ms
                FROM r21_epoch2_activation
                WHERE singleton = 1
                """
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == record.activation_identity
                    and str(existing[1]) == payload
                    and int(existing[2]) == record.activated_at_ms
                ):
                    return False
                raise ValueError("R21 Epoch2 activation is immutable once created")
            connection.execute(
                """
                INSERT INTO r21_epoch2_activation (
                    singleton, activation_identity, payload_json, activated_at_ms
                ) VALUES (1, ?, ?, ?)
                """,
                (record.activation_identity, payload, record.activated_at_ms),
            )
        return True

    def append_vault_snapshot(self, snapshot: Epoch2VaultAccountingSnapshot) -> bool:
        activation = self.read_activation()
        if activation is None:
            raise ValueError("R21 vault snapshot requires Epoch2 activation")
        if snapshot.activation_identity != activation.activation_identity:
            raise ValueError("R21 vault snapshot activation mismatch")
        if snapshot.snapshot_at_ms < activation.activated_at_ms:
            raise ValueError("R21 vault snapshot cannot predate activation")
        latest = self.read_latest_vault_snapshots()
        latest_for_vault = next(
            (item for item in latest if item.vault_id is snapshot.vault_id),
            None,
        )
        expected_previous = (
            None if latest_for_vault is None else latest_for_vault.snapshot_identity
        )
        if snapshot.previous_snapshot_identity != expected_previous:
            raise ValueError("R21 vault snapshot previous lineage mismatch")
        return self._append_snapshot(
            table="r21_vault_snapshots",
            identity=snapshot.snapshot_identity,
            payload=canonical_json(snapshot),
            snapshot_at_ms=snapshot.snapshot_at_ms,
            vault_id=snapshot.vault_id.value,
        )

    def append_consolidated_snapshot(
        self,
        snapshot: Epoch2ConsolidatedAccountingSnapshot,
    ) -> bool:
        activation = self.read_activation()
        if activation is None:
            raise ValueError("R21 consolidated snapshot requires Epoch2 activation")
        if snapshot.activation_identity != activation.activation_identity:
            raise ValueError("R21 consolidated snapshot activation mismatch")
        if snapshot.snapshot_at_ms < activation.activated_at_ms:
            raise ValueError("R21 consolidated snapshot cannot predate activation")
        latest_consolidated = self.read_latest_consolidated_snapshot()
        expected_previous = (
            None
            if latest_consolidated is None
            else latest_consolidated.snapshot_identity
        )
        if snapshot.previous_snapshot_identity != expected_previous:
            raise ValueError("R21 consolidated previous lineage mismatch")
        vaults = self.read_latest_vault_snapshots(at_or_before_ms=snapshot.snapshot_at_ms)
        if len(vaults) != len(PaperVaultId):
            raise ValueError("R21 consolidated snapshot requires all three vaults")
        if any(item.snapshot_at_ms != snapshot.snapshot_at_ms for item in vaults):
            raise ValueError(
                "R21 consolidated snapshot requires same-time vault snapshots"
            )
        expected = tuple(sorted(item.snapshot_identity for item in vaults))
        if snapshot.vault_snapshot_identities != expected:
            raise ValueError("R21 consolidated snapshot must reference latest three vaults")
        _validate_consolidated_matches_vaults(snapshot, vaults)
        return self._append_snapshot(
            table="r21_consolidated_snapshots",
            identity=snapshot.snapshot_identity,
            payload=canonical_json(snapshot),
            snapshot_at_ms=snapshot.snapshot_at_ms,
        )

    def read_activation(self) -> Epoch2ActivationRecord | None:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM r21_epoch2_activation WHERE singleton = 1"
            ).fetchone()
        return None if row is None else _decode_activation(str(row[0]))

    def read_latest_vault_snapshots(
        self,
        *,
        at_or_before_ms: int | None = None,
    ) -> tuple[Epoch2VaultAccountingSnapshot, ...]:
        self.initialize()
        snapshots: list[Epoch2VaultAccountingSnapshot] = []
        with sqlite3.connect(self.path) as connection:
            for vault_id in PaperVaultId:
                if at_or_before_ms is None:
                    row = connection.execute(
                        """
                        SELECT payload_json FROM r21_vault_snapshots
                        WHERE vault_id = ?
                        ORDER BY snapshot_at_ms DESC, snapshot_identity DESC
                        LIMIT 1
                        """,
                        (vault_id.value,),
                    ).fetchone()
                else:
                    row = connection.execute(
                        """
                        SELECT payload_json FROM r21_vault_snapshots
                        WHERE vault_id = ? AND snapshot_at_ms <= ?
                        ORDER BY snapshot_at_ms DESC, snapshot_identity DESC
                        LIMIT 1
                        """,
                        (vault_id.value, at_or_before_ms),
                    ).fetchone()
                if row is None:
                    continue
                snapshots.append(_decode_vault_snapshot(str(row[0])))
        return tuple(sorted(snapshots, key=lambda item: item.vault_id.value))

    def read_latest_consolidated_snapshot(
        self,
    ) -> Epoch2ConsolidatedAccountingSnapshot | None:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM r21_consolidated_snapshots
                ORDER BY snapshot_at_ms DESC, snapshot_identity DESC
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else _decode_consolidated_snapshot(str(row[0]))

    def read_state(self) -> Epoch2LedgerState:
        activation = self.read_activation()
        if activation is None:
            raise ValueError("R21 Epoch2 ledger is not activated")
        vaults = self.read_latest_vault_snapshots()
        if len(vaults) != len(PaperVaultId):
            raise ValueError("R21 Epoch2 state requires all three vault snapshots")
        consolidated = self.read_latest_consolidated_snapshot()
        if consolidated is None:
            raise ValueError("R21 Epoch2 state requires consolidated snapshot")
        expected = tuple(sorted(item.snapshot_identity for item in vaults))
        if consolidated.vault_snapshot_identities != expected:
            raise ValueError("R21 latest consolidated snapshot is stale versus vaults")
        _validate_consolidated_matches_vaults(consolidated, vaults)
        return Epoch2LedgerState(
            activation=activation,
            vault_snapshots=vaults,
            consolidated_snapshot=consolidated,
        )

    def _append_snapshot(
        self,
        *,
        table: str,
        identity: str,
        payload: str,
        snapshot_at_ms: int,
        vault_id: str | None = None,
    ) -> bool:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                f"SELECT payload_json, snapshot_at_ms FROM {table} WHERE snapshot_identity = ?",
                (identity,),
            ).fetchone()
            if row is not None:
                if str(row[0]) == payload and int(row[1]) == snapshot_at_ms:
                    return False
                raise ValueError("R21 immutable snapshot identity conflict")
            if vault_id is None:
                same_time = connection.execute(
                    f"SELECT snapshot_identity FROM {table} WHERE snapshot_at_ms = ? LIMIT 1",
                    (snapshot_at_ms,),
                ).fetchone()
                latest = connection.execute(
                    f"SELECT snapshot_at_ms FROM {table} ORDER BY snapshot_at_ms DESC LIMIT 1"
                ).fetchone()
                if same_time is not None:
                    raise ValueError("R21 consolidated snapshot timestamp conflict")
                if latest is not None and snapshot_at_ms < int(latest[0]):
                    raise ValueError("R21 consolidated snapshots cannot backfill history")
                connection.execute(
                    f"""
                    INSERT INTO {table} (
                        snapshot_identity, payload_json, snapshot_at_ms
                    ) VALUES (?, ?, ?)
                    """,
                    (identity, payload, snapshot_at_ms),
                )
            else:
                same_time = connection.execute(
                    f"""
                    SELECT snapshot_identity FROM {table}
                    WHERE vault_id = ? AND snapshot_at_ms = ?
                    LIMIT 1
                    """,
                    (vault_id, snapshot_at_ms),
                ).fetchone()
                latest = connection.execute(
                    f"""
                    SELECT snapshot_at_ms FROM {table}
                    WHERE vault_id = ?
                    ORDER BY snapshot_at_ms DESC
                    LIMIT 1
                    """,
                    (vault_id,),
                ).fetchone()
                if same_time is not None:
                    raise ValueError("R21 vault snapshot timestamp conflict")
                if latest is not None and snapshot_at_ms < int(latest[0]):
                    raise ValueError("R21 vault snapshots cannot backfill history")
                connection.execute(
                    f"""
                    INSERT INTO {table} (
                        snapshot_identity, vault_id, payload_json, snapshot_at_ms
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (identity, vault_id, payload, snapshot_at_ms),
                )
        return True

    @staticmethod
    def _install_immutability_triggers(connection: sqlite3.Connection) -> None:
        for table in (
            "r21_epoch2_activation",
            "r21_vault_snapshots",
            "r21_consolidated_snapshots",
        ):
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable R21 paper ledger');
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'immutable R21 paper ledger');
                END
                """
            )


def build_epoch2_activation_record(
    *,
    activated_at_ms: int,
    epoch1_ledger_sha256: str,
) -> Epoch2ActivationRecord:
    vaults = tuple(
        sorted(
            (
                (item.vault_id, item.starting_cash_usdt)
                for item in EPOCH_2_SPEC.vault_allocations
            ),
            key=lambda item: item[0].value,
        )
    )
    payload = {
        "activated_at_ms": activated_at_ms,
        "borrowing_allowed": False,
        "engine_version": R21_ENGINE_VERSION,
        "epoch1_ledger_sha256": epoch1_ledger_sha256,
        "epoch_identity": EPOCH_2_SPEC.epoch_identity,
        "leverage_allowed": False,
        "martingale_allowed": False,
        "predecessor_epoch_identity": EPOCH_1_SPEC.epoch_identity,
        "real_capital": REAL_CAPITAL,
        "schema_version": R21_SCHEMA_VERSION,
        "starting_cash_usdt": EPOCH_2_SPEC.starting_cash_usdt,
        "vault_starting_cash": vaults,
    }
    return Epoch2ActivationRecord(
        activation_identity=canonical_sha256(payload),
        schema_version=R21_SCHEMA_VERSION,
        engine_version=R21_ENGINE_VERSION,
        epoch_identity=EPOCH_2_SPEC.epoch_identity,
        predecessor_epoch_identity=EPOCH_1_SPEC.epoch_identity,
        activated_at_ms=activated_at_ms,
        starting_cash_usdt=EPOCH_2_SPEC.starting_cash_usdt,
        vault_starting_cash=vaults,
        epoch1_ledger_sha256=epoch1_ledger_sha256,
    )


def build_initial_epoch2_vault_snapshot(
    activation: Epoch2ActivationRecord,
    vault_id: PaperVaultId,
) -> Epoch2VaultAccountingSnapshot:
    starting_cash = dict(activation.vault_starting_cash)[vault_id]
    payload = {
        "activation_identity": activation.activation_identity,
        "breakeven_count": 0,
        "cash_usdt": starting_cash,
        "closed_trade_count": 0,
        "drawdown_fraction": Decimal(0),
        "engine_version": R21_ENGINE_VERSION,
        "expectancy_usdt_per_closed_trade": None,
        "fee_usdt": Decimal(0),
        "high_water_nav_usdt": starting_cash,
        "loss_count": 0,
        "marked_exposure_usdt": Decimal(0),
        "metrics_status": Epoch2MetricsStatus.NOT_YET_MEASURED,
        "nav_usdt": starting_cash,
        "outcome_distribution": (),
        "positions": (),
        "previous_snapshot_identity": None,
        "real_capital": REAL_CAPITAL,
        "realized_pnl_usdt": Decimal(0),
        "schema_version": R21_SCHEMA_VERSION,
        "slippage_usdt": Decimal(0),
        "snapshot_at_ms": activation.activated_at_ms,
        "source_record_identities": (activation.activation_identity,),
        "spread_usdt": Decimal(0),
        "starting_cash_usdt": starting_cash,
        "turnover_fraction": Decimal(0),
        "turnover_notional_usdt": Decimal(0),
        "unrealized_pnl_usdt": Decimal(0),
        "vault_id": vault_id,
        "win_count": 0,
    }
    return Epoch2VaultAccountingSnapshot(
        snapshot_identity=canonical_sha256(payload),
        schema_version=R21_SCHEMA_VERSION,
        engine_version=R21_ENGINE_VERSION,
        activation_identity=activation.activation_identity,
        vault_id=vault_id,
        snapshot_at_ms=activation.activated_at_ms,
        starting_cash_usdt=starting_cash,
        cash_usdt=starting_cash,
        positions=(),
        marked_exposure_usdt=Decimal(0),
        nav_usdt=starting_cash,
        realized_pnl_usdt=Decimal(0),
        unrealized_pnl_usdt=Decimal(0),
        high_water_nav_usdt=starting_cash,
        drawdown_fraction=Decimal(0),
        fee_usdt=Decimal(0),
        spread_usdt=Decimal(0),
        slippage_usdt=Decimal(0),
        turnover_notional_usdt=Decimal(0),
        turnover_fraction=Decimal(0),
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        expectancy_usdt_per_closed_trade=None,
        outcome_distribution=(),
        metrics_status=Epoch2MetricsStatus.NOT_YET_MEASURED,
        source_record_identities=(activation.activation_identity,),
        previous_snapshot_identity=None,
    )


def build_epoch2_vault_accounting_snapshot(
    activation: Epoch2ActivationRecord,
    *,
    vault_id: PaperVaultId,
    snapshot_at_ms: int,
    cash_usdt: Decimal,
    positions: tuple[PaperPosition, ...],
    marked_exposure_usdt: Decimal,
    realized_pnl_usdt: Decimal,
    unrealized_pnl_usdt: Decimal,
    fee_usdt: Decimal,
    spread_usdt: Decimal,
    slippage_usdt: Decimal,
    turnover_notional_usdt: Decimal,
    closed_trade_count: int,
    win_count: int,
    loss_count: int,
    breakeven_count: int,
    outcome_distribution: tuple[tuple[str, int], ...],
    source_record_identities: tuple[str, ...],
    previous: Epoch2VaultAccountingSnapshot,
) -> Epoch2VaultAccountingSnapshot:
    if previous.activation_identity != activation.activation_identity:
        raise ValueError("R21 vault previous activation mismatch")
    if previous.vault_id is not vault_id:
        raise ValueError("R21 vault previous snapshot vault mismatch")
    if snapshot_at_ms <= previous.snapshot_at_ms:
        raise ValueError("R21 vault snapshot must advance time")
    starting_cash = dict(activation.vault_starting_cash)[vault_id]
    normalized_positions = normalize_positions(positions)
    nav = cash_usdt + marked_exposure_usdt
    high_water = max(previous.high_water_nav_usdt, nav)
    drawdown = (
        Decimal(0)
        if high_water == Decimal(0)
        else (high_water - nav) / high_water
    )
    turnover_fraction = turnover_notional_usdt / starting_cash
    metrics_status = (
        Epoch2MetricsStatus.AVAILABLE
        if closed_trade_count > 0
        else Epoch2MetricsStatus.NOT_YET_MEASURED
    )
    expectancy = (
        None
        if closed_trade_count == 0
        else realized_pnl_usdt / Decimal(closed_trade_count)
    )
    sources = tuple(sorted(set(source_record_identities)))
    if not sources:
        raise ValueError("R21 measured vault snapshot requires source records")
    payload = {
        "activation_identity": activation.activation_identity,
        "breakeven_count": breakeven_count,
        "cash_usdt": cash_usdt,
        "closed_trade_count": closed_trade_count,
        "drawdown_fraction": drawdown,
        "engine_version": R21_ENGINE_VERSION,
        "expectancy_usdt_per_closed_trade": expectancy,
        "fee_usdt": fee_usdt,
        "high_water_nav_usdt": high_water,
        "loss_count": loss_count,
        "marked_exposure_usdt": marked_exposure_usdt,
        "metrics_status": metrics_status,
        "nav_usdt": nav,
        "outcome_distribution": outcome_distribution,
        "positions": normalized_positions,
        "previous_snapshot_identity": previous.snapshot_identity,
        "real_capital": REAL_CAPITAL,
        "realized_pnl_usdt": realized_pnl_usdt,
        "schema_version": R21_SCHEMA_VERSION,
        "slippage_usdt": slippage_usdt,
        "snapshot_at_ms": snapshot_at_ms,
        "source_record_identities": sources,
        "spread_usdt": spread_usdt,
        "starting_cash_usdt": starting_cash,
        "turnover_fraction": turnover_fraction,
        "turnover_notional_usdt": turnover_notional_usdt,
        "unrealized_pnl_usdt": unrealized_pnl_usdt,
        "vault_id": vault_id,
        "win_count": win_count,
    }
    return Epoch2VaultAccountingSnapshot(
        snapshot_identity=canonical_sha256(payload),
        schema_version=R21_SCHEMA_VERSION,
        engine_version=R21_ENGINE_VERSION,
        activation_identity=activation.activation_identity,
        vault_id=vault_id,
        snapshot_at_ms=snapshot_at_ms,
        starting_cash_usdt=starting_cash,
        cash_usdt=cash_usdt,
        positions=normalized_positions,
        marked_exposure_usdt=marked_exposure_usdt,
        nav_usdt=nav,
        realized_pnl_usdt=realized_pnl_usdt,
        unrealized_pnl_usdt=unrealized_pnl_usdt,
        high_water_nav_usdt=high_water,
        drawdown_fraction=drawdown,
        fee_usdt=fee_usdt,
        spread_usdt=spread_usdt,
        slippage_usdt=slippage_usdt,
        turnover_notional_usdt=turnover_notional_usdt,
        turnover_fraction=turnover_fraction,
        closed_trade_count=closed_trade_count,
        win_count=win_count,
        loss_count=loss_count,
        breakeven_count=breakeven_count,
        expectancy_usdt_per_closed_trade=expectancy,
        outcome_distribution=outcome_distribution,
        metrics_status=metrics_status,
        source_record_identities=sources,
        previous_snapshot_identity=previous.snapshot_identity,
    )


def build_consolidated_epoch2_snapshot(
    vaults: tuple[Epoch2VaultAccountingSnapshot, ...],
    *,
    previous: Epoch2ConsolidatedAccountingSnapshot | None = None,
) -> Epoch2ConsolidatedAccountingSnapshot:
    if len(vaults) != len(PaperVaultId):
        raise ValueError("R21 consolidated builder requires exactly three vaults")
    by_vault = {item.vault_id: item for item in vaults}
    if set(by_vault) != set(PaperVaultId):
        raise ValueError("R21 consolidated builder requires one snapshot per vault")
    ordered = tuple(by_vault[item] for item in sorted(PaperVaultId, key=lambda x: x.value))
    activation_ids = {item.activation_identity for item in ordered}
    snapshot_times = {item.snapshot_at_ms for item in ordered}
    if len(activation_ids) != 1:
        raise ValueError("R21 consolidated vault activation identities must match")
    if len(snapshot_times) != 1:
        raise ValueError("R21 consolidated vault snapshot times must match")
    cash = sum((item.cash_usdt for item in ordered), start=Decimal(0))
    exposure = sum(
        (item.marked_exposure_usdt for item in ordered),
        start=Decimal(0),
    )
    nav = sum((item.nav_usdt for item in ordered), start=Decimal(0))
    realized = sum((item.realized_pnl_usdt for item in ordered), start=Decimal(0))
    unrealized = sum((item.unrealized_pnl_usdt for item in ordered), start=Decimal(0))
    if previous is not None:
        if previous.activation_identity != ordered[0].activation_identity:
            raise ValueError("R21 consolidated previous activation mismatch")
        if previous.snapshot_at_ms >= ordered[0].snapshot_at_ms:
            raise ValueError("R21 consolidated snapshot must advance time")
    high_water = (
        nav
        if previous is None
        else max(previous.high_water_nav_usdt, nav)
    )
    fee = sum((item.fee_usdt for item in ordered), start=Decimal(0))
    spread = sum((item.spread_usdt for item in ordered), start=Decimal(0))
    slippage = sum((item.slippage_usdt for item in ordered), start=Decimal(0))
    turnover_notional = sum(
        (item.turnover_notional_usdt for item in ordered),
        start=Decimal(0),
    )
    closed_count = sum(item.closed_trade_count for item in ordered)
    win_count = sum(item.win_count for item in ordered)
    loss_count = sum(item.loss_count for item in ordered)
    breakeven_count = sum(item.breakeven_count for item in ordered)
    outcome_counts: dict[str, int] = {}
    for item in ordered:
        for outcome, count in item.outcome_distribution:
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + count
    outcome_distribution = tuple(sorted(outcome_counts.items()))
    metrics_status = (
        Epoch2MetricsStatus.AVAILABLE
        if closed_count > 0
        else Epoch2MetricsStatus.NOT_YET_MEASURED
    )
    expectancy = (
        None if closed_count == 0 else realized / Decimal(closed_count)
    )
    drawdown = (
        Decimal(0)
        if high_water == Decimal(0)
        else (high_water - nav) / high_water
    )
    turnover_fraction = turnover_notional / EPOCH_2_SPEC.starting_cash_usdt
    ids = tuple(sorted(item.snapshot_identity for item in ordered))
    activation_identity = ordered[0].activation_identity
    snapshot_at_ms = ordered[0].snapshot_at_ms
    payload = {
        "activation_identity": activation_identity,
        "breakeven_count": breakeven_count,
        "cash_usdt": cash,
        "closed_trade_count": closed_count,
        "drawdown_fraction": drawdown,
        "engine_version": R21_ENGINE_VERSION,
        "expectancy_usdt_per_closed_trade": expectancy,
        "fee_usdt": fee,
        "high_water_nav_usdt": high_water,
        "loss_count": loss_count,
        "marked_exposure_usdt": exposure,
        "metrics_status": metrics_status,
        "nav_usdt": nav,
        "outcome_distribution": outcome_distribution,
        "previous_snapshot_identity": (
            None if previous is None else previous.snapshot_identity
        ),
        "real_capital": REAL_CAPITAL,
        "realized_pnl_usdt": realized,
        "schema_version": R21_SCHEMA_VERSION,
        "slippage_usdt": slippage,
        "snapshot_at_ms": snapshot_at_ms,
        "spread_usdt": spread,
        "turnover_fraction": turnover_fraction,
        "turnover_notional_usdt": turnover_notional,
        "unrealized_pnl_usdt": unrealized,
        "vault_snapshot_identities": ids,
        "win_count": win_count,
    }
    return Epoch2ConsolidatedAccountingSnapshot(
        snapshot_identity=canonical_sha256(payload),
        schema_version=R21_SCHEMA_VERSION,
        engine_version=R21_ENGINE_VERSION,
        activation_identity=activation_identity,
        snapshot_at_ms=snapshot_at_ms,
        vault_snapshot_identities=ids,
        cash_usdt=cash,
        marked_exposure_usdt=exposure,
        nav_usdt=nav,
        realized_pnl_usdt=realized,
        unrealized_pnl_usdt=unrealized,
        high_water_nav_usdt=high_water,
        drawdown_fraction=drawdown,
        fee_usdt=fee,
        spread_usdt=spread,
        slippage_usdt=slippage,
        turnover_notional_usdt=turnover_notional,
        turnover_fraction=turnover_fraction,
        closed_trade_count=closed_count,
        win_count=win_count,
        loss_count=loss_count,
        breakeven_count=breakeven_count,
        expectancy_usdt_per_closed_trade=expectancy,
        outcome_distribution=outcome_distribution,
        metrics_status=metrics_status,
        previous_snapshot_identity=(
            None if previous is None else previous.snapshot_identity
        ),
    )


def initialize_epoch2_canonical_fund(
    *,
    epoch1_ledger_path: Path,
    epoch2_ledger_path: Path,
    activated_at_ms: int,
) -> Epoch2LedgerState:
    if epoch1_ledger_path.resolve() == epoch2_ledger_path.resolve():
        raise ValueError("R21 Epoch1 and Epoch2 ledger paths must remain separate")
    if not epoch1_ledger_path.is_file():
        raise ValueError("R21 activation requires existing immutable Epoch1 ledger")
    epoch1_before = epoch1_ledger_path.read_bytes()
    entries = read_paper_entries_read_only(epoch1_ledger_path)
    creations = tuple(
        entry.record
        for entry in entries
        if isinstance(entry.record, FundCreationRecord)
    )
    if len(creations) != 1:
        raise ValueError("R21 activation requires exactly one legacy Epoch1 fund")
    assert_legacy_epoch1_fund_creation(creations[0])
    if epoch1_ledger_path.read_bytes() != epoch1_before:
        raise ValueError("R21 read-only Epoch1 validation mutated ledger bytes")
    epoch1_sha = hashlib.sha256(epoch1_before).hexdigest()
    activation = build_epoch2_activation_record(
        activated_at_ms=activated_at_ms,
        epoch1_ledger_sha256=epoch1_sha,
    )
    ledger = Epoch2CanonicalLedger(epoch2_ledger_path)
    inserted = ledger.activate(activation)
    if not inserted:
        if epoch1_ledger_path.read_bytes() != epoch1_before:
            raise ValueError("R21 activation must never mutate Epoch1 ledger")
        return ledger.read_state()
    vaults = tuple(
        build_initial_epoch2_vault_snapshot(activation, vault_id)
        for vault_id in sorted(PaperVaultId, key=lambda item: item.value)
    )
    for snapshot in vaults:
        ledger.append_vault_snapshot(snapshot)
    consolidated = build_consolidated_epoch2_snapshot(vaults)
    ledger.append_consolidated_snapshot(consolidated)
    if epoch1_ledger_path.read_bytes() != epoch1_before:
        raise ValueError("R21 activation must never mutate Epoch1 ledger")
    return ledger.read_state()


def _validate_consolidated_matches_vaults(
    consolidated: Epoch2ConsolidatedAccountingSnapshot,
    vaults: tuple[Epoch2VaultAccountingSnapshot, ...],
) -> None:
    cash = sum((item.cash_usdt for item in vaults), start=Decimal(0))
    exposure = sum((item.marked_exposure_usdt for item in vaults), start=Decimal(0))
    nav = sum((item.nav_usdt for item in vaults), start=Decimal(0))
    realized = sum((item.realized_pnl_usdt for item in vaults), start=Decimal(0))
    unrealized = sum((item.unrealized_pnl_usdt for item in vaults), start=Decimal(0))
    fee = sum((item.fee_usdt for item in vaults), start=Decimal(0))
    spread = sum((item.spread_usdt for item in vaults), start=Decimal(0))
    slippage = sum((item.slippage_usdt for item in vaults), start=Decimal(0))
    turnover = sum((item.turnover_notional_usdt for item in vaults), start=Decimal(0))
    if (
        consolidated.cash_usdt != cash
        or consolidated.marked_exposure_usdt != exposure
        or consolidated.nav_usdt != nav
        or consolidated.realized_pnl_usdt != realized
        or consolidated.unrealized_pnl_usdt != unrealized
        or consolidated.fee_usdt != fee
        or consolidated.spread_usdt != spread
        or consolidated.slippage_usdt != slippage
        or consolidated.turnover_notional_usdt != turnover
    ):
        raise ValueError("R21 consolidated snapshot does not reconcile to vault snapshots")


def _activation_payload(record: Epoch2ActivationRecord) -> dict[str, object]:
    return {
        "activated_at_ms": record.activated_at_ms,
        "borrowing_allowed": record.borrowing_allowed,
        "engine_version": record.engine_version,
        "epoch1_ledger_sha256": record.epoch1_ledger_sha256,
        "epoch_identity": record.epoch_identity,
        "leverage_allowed": record.leverage_allowed,
        "martingale_allowed": record.martingale_allowed,
        "predecessor_epoch_identity": record.predecessor_epoch_identity,
        "real_capital": record.real_capital,
        "schema_version": record.schema_version,
        "starting_cash_usdt": record.starting_cash_usdt,
        "vault_starting_cash": record.vault_starting_cash,
    }


def _vault_snapshot_payload(
    snapshot: Epoch2VaultAccountingSnapshot,
) -> dict[str, object]:
    return {
        "activation_identity": snapshot.activation_identity,
        "breakeven_count": snapshot.breakeven_count,
        "cash_usdt": snapshot.cash_usdt,
        "closed_trade_count": snapshot.closed_trade_count,
        "drawdown_fraction": snapshot.drawdown_fraction,
        "engine_version": snapshot.engine_version,
        "expectancy_usdt_per_closed_trade": snapshot.expectancy_usdt_per_closed_trade,
        "fee_usdt": snapshot.fee_usdt,
        "high_water_nav_usdt": snapshot.high_water_nav_usdt,
        "loss_count": snapshot.loss_count,
        "marked_exposure_usdt": snapshot.marked_exposure_usdt,
        "metrics_status": snapshot.metrics_status,
        "nav_usdt": snapshot.nav_usdt,
        "outcome_distribution": snapshot.outcome_distribution,
        "positions": snapshot.positions,
        "previous_snapshot_identity": snapshot.previous_snapshot_identity,
        "real_capital": snapshot.real_capital,
        "realized_pnl_usdt": snapshot.realized_pnl_usdt,
        "schema_version": snapshot.schema_version,
        "slippage_usdt": snapshot.slippage_usdt,
        "snapshot_at_ms": snapshot.snapshot_at_ms,
        "source_record_identities": snapshot.source_record_identities,
        "spread_usdt": snapshot.spread_usdt,
        "starting_cash_usdt": snapshot.starting_cash_usdt,
        "turnover_fraction": snapshot.turnover_fraction,
        "turnover_notional_usdt": snapshot.turnover_notional_usdt,
        "unrealized_pnl_usdt": snapshot.unrealized_pnl_usdt,
        "vault_id": snapshot.vault_id,
        "win_count": snapshot.win_count,
    }


def _consolidated_snapshot_payload(
    snapshot: Epoch2ConsolidatedAccountingSnapshot,
) -> dict[str, object]:
    return {
        "activation_identity": snapshot.activation_identity,
        "breakeven_count": snapshot.breakeven_count,
        "cash_usdt": snapshot.cash_usdt,
        "closed_trade_count": snapshot.closed_trade_count,
        "drawdown_fraction": snapshot.drawdown_fraction,
        "engine_version": snapshot.engine_version,
        "expectancy_usdt_per_closed_trade": snapshot.expectancy_usdt_per_closed_trade,
        "fee_usdt": snapshot.fee_usdt,
        "high_water_nav_usdt": snapshot.high_water_nav_usdt,
        "loss_count": snapshot.loss_count,
        "marked_exposure_usdt": snapshot.marked_exposure_usdt,
        "metrics_status": snapshot.metrics_status,
        "nav_usdt": snapshot.nav_usdt,
        "outcome_distribution": snapshot.outcome_distribution,
        "previous_snapshot_identity": snapshot.previous_snapshot_identity,
        "real_capital": snapshot.real_capital,
        "realized_pnl_usdt": snapshot.realized_pnl_usdt,
        "schema_version": snapshot.schema_version,
        "slippage_usdt": snapshot.slippage_usdt,
        "snapshot_at_ms": snapshot.snapshot_at_ms,
        "spread_usdt": snapshot.spread_usdt,
        "turnover_fraction": snapshot.turnover_fraction,
        "turnover_notional_usdt": snapshot.turnover_notional_usdt,
        "unrealized_pnl_usdt": snapshot.unrealized_pnl_usdt,
        "vault_snapshot_identities": snapshot.vault_snapshot_identities,
        "win_count": snapshot.win_count,
    }


def _decode_activation(payload_json: str) -> Epoch2ActivationRecord:
    raw = json.loads(payload_json)
    return Epoch2ActivationRecord(
        activation_identity=str(raw["activation_identity"]),
        schema_version=str(raw["schema_version"]),
        engine_version=str(raw["engine_version"]),
        epoch_identity=str(raw["epoch_identity"]),
        predecessor_epoch_identity=str(raw["predecessor_epoch_identity"]),
        activated_at_ms=int(raw["activated_at_ms"]),
        starting_cash_usdt=Decimal(str(raw["starting_cash_usdt"])),
        vault_starting_cash=tuple(
            (
                PaperVaultId(str(item[0])),
                Decimal(str(item[1])),
            )
            for item in raw["vault_starting_cash"]
        ),
        epoch1_ledger_sha256=str(raw["epoch1_ledger_sha256"]),
        real_capital=int(raw["real_capital"]),
        leverage_allowed=bool(raw["leverage_allowed"]),
        borrowing_allowed=bool(raw["borrowing_allowed"]),
        martingale_allowed=bool(raw["martingale_allowed"]),
    )


def _decode_vault_snapshot(payload_json: str) -> Epoch2VaultAccountingSnapshot:
    raw = json.loads(payload_json)
    positions = tuple(
        PaperPosition(
            symbol=PaperSymbol(str(item["symbol"])),
            quantity=Decimal(str(item["quantity"])),
        )
        for item in raw["positions"]
    )
    return Epoch2VaultAccountingSnapshot(
        snapshot_identity=str(raw["snapshot_identity"]),
        schema_version=str(raw["schema_version"]),
        engine_version=str(raw["engine_version"]),
        activation_identity=str(raw["activation_identity"]),
        vault_id=PaperVaultId(str(raw["vault_id"])),
        snapshot_at_ms=int(raw["snapshot_at_ms"]),
        starting_cash_usdt=Decimal(str(raw["starting_cash_usdt"])),
        cash_usdt=Decimal(str(raw["cash_usdt"])),
        positions=positions,
        marked_exposure_usdt=Decimal(str(raw["marked_exposure_usdt"])),
        nav_usdt=Decimal(str(raw["nav_usdt"])),
        realized_pnl_usdt=Decimal(str(raw["realized_pnl_usdt"])),
        unrealized_pnl_usdt=Decimal(str(raw["unrealized_pnl_usdt"])),
        high_water_nav_usdt=Decimal(str(raw["high_water_nav_usdt"])),
        drawdown_fraction=Decimal(str(raw["drawdown_fraction"])),
        fee_usdt=Decimal(str(raw["fee_usdt"])),
        spread_usdt=Decimal(str(raw["spread_usdt"])),
        slippage_usdt=Decimal(str(raw["slippage_usdt"])),
        turnover_notional_usdt=Decimal(str(raw["turnover_notional_usdt"])),
        turnover_fraction=Decimal(str(raw["turnover_fraction"])),
        closed_trade_count=int(raw["closed_trade_count"]),
        win_count=int(raw["win_count"]),
        loss_count=int(raw["loss_count"]),
        breakeven_count=int(raw["breakeven_count"]),
        expectancy_usdt_per_closed_trade=(
            None
            if raw["expectancy_usdt_per_closed_trade"] is None
            else Decimal(str(raw["expectancy_usdt_per_closed_trade"]))
        ),
        outcome_distribution=tuple(
            (str(item[0]), int(item[1])) for item in raw["outcome_distribution"]
        ),
        metrics_status=Epoch2MetricsStatus(str(raw["metrics_status"])),
        source_record_identities=tuple(str(item) for item in raw["source_record_identities"]),
        previous_snapshot_identity=(
            None
            if raw.get("previous_snapshot_identity") is None
            else str(raw["previous_snapshot_identity"])
        ),
        real_capital=int(raw["real_capital"]),
    )


def _decode_consolidated_snapshot(
    payload_json: str,
) -> Epoch2ConsolidatedAccountingSnapshot:
    raw = json.loads(payload_json)
    return Epoch2ConsolidatedAccountingSnapshot(
        snapshot_identity=str(raw["snapshot_identity"]),
        schema_version=str(raw["schema_version"]),
        engine_version=str(raw["engine_version"]),
        activation_identity=str(raw["activation_identity"]),
        snapshot_at_ms=int(raw["snapshot_at_ms"]),
        vault_snapshot_identities=tuple(
            str(item) for item in raw["vault_snapshot_identities"]
        ),
        cash_usdt=Decimal(str(raw["cash_usdt"])),
        marked_exposure_usdt=Decimal(str(raw["marked_exposure_usdt"])),
        nav_usdt=Decimal(str(raw["nav_usdt"])),
        realized_pnl_usdt=Decimal(str(raw["realized_pnl_usdt"])),
        unrealized_pnl_usdt=Decimal(str(raw["unrealized_pnl_usdt"])),
        high_water_nav_usdt=Decimal(str(raw["high_water_nav_usdt"])),
        drawdown_fraction=Decimal(str(raw["drawdown_fraction"])),
        fee_usdt=Decimal(str(raw["fee_usdt"])),
        spread_usdt=Decimal(str(raw["spread_usdt"])),
        slippage_usdt=Decimal(str(raw["slippage_usdt"])),
        turnover_notional_usdt=Decimal(str(raw["turnover_notional_usdt"])),
        turnover_fraction=Decimal(str(raw["turnover_fraction"])),
        closed_trade_count=int(raw["closed_trade_count"]),
        win_count=int(raw["win_count"]),
        loss_count=int(raw["loss_count"]),
        breakeven_count=int(raw["breakeven_count"]),
        expectancy_usdt_per_closed_trade=(
            None
            if raw["expectancy_usdt_per_closed_trade"] is None
            else Decimal(str(raw["expectancy_usdt_per_closed_trade"]))
        ),
        outcome_distribution=tuple(
            (str(item[0]), int(item[1])) for item in raw["outcome_distribution"]
        ),
        metrics_status=Epoch2MetricsStatus(str(raw["metrics_status"])),
        previous_snapshot_identity=(
            None
            if raw.get("previous_snapshot_identity") is None
            else str(raw["previous_snapshot_identity"])
        ),
        real_capital=int(raw["real_capital"]),
    )


def _require_outcome_distribution(
    distribution: tuple[tuple[str, int], ...],
    closed_trade_count: int,
) -> None:
    if tuple(sorted(distribution)) != distribution:
        raise ValueError("R21 outcome distribution must be sorted")
    if len({key for key, _ in distribution}) != len(distribution):
        raise ValueError("R21 outcome distribution keys must be unique")
    if any(not key.strip() or count < 0 for key, count in distribution):
        raise ValueError("R21 outcome distribution entries must be valid")
    if sum(count for _, count in distribution) != closed_trade_count:
        raise ValueError("R21 outcome distribution count mismatch")


def _require_identity_tuple(values: tuple[str, ...], label: str) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} values must be unique and sorted")
    for value in values:
        _require_sha256(value, label)


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    _require_finite_decimal(value, label)
    if value < Decimal(0):
        raise ValueError(f"{label} cannot be negative")


def _require_finite_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
