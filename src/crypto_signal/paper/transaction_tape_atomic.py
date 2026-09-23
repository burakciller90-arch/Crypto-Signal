"""R22 Phase 17 integration: atomic Epoch 2 accounting + immutable tape commit.

Development infrastructure only. The transaction is local SQLite paper accounting.
No exchange, network, credential, broker, leverage or real-capital authority is added.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.epoch2_accounting import (
    Epoch2CanonicalLedger,
    Epoch2ConsolidatedAccountingSnapshot,
    Epoch2LedgerState,
    Epoch2VaultAccountingSnapshot,
    build_consolidated_epoch2_snapshot,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction
from crypto_signal.paper.transaction_tape import PaperTapeFill, PaperTapeIntent

R22_BUNDLE_SCHEMA_VERSION = "r22-epoch2-accounting-bundle-v1/1"
R22_BUNDLE_ENGINE_VERSION = "r22-epoch2-accounting-bundle-v1/1"


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")


def _identity_tuple(values: tuple[str, ...], label: str) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} identities must be non-empty, sorted and unique")
    for value in values:
        _require_sha256(value, label)


def _decode_object(payload_json: str, label: str) -> dict[str, object]:
    decoded = json.loads(payload_json)
    if not isinstance(decoded, dict):
        raise TypeError(f"{label} payload must be an object")
    return cast(dict[str, object], decoded)


def _verify_embedded_identity(
    payload_json: str,
    *,
    identity_field: str,
    expected_identity: str,
    label: str,
) -> dict[str, object]:
    raw = _decode_object(payload_json, label)
    if raw.get(identity_field) != expected_identity:
        raise ValueError(f"{label} embedded identity mismatch")
    identity_payload = dict(raw)
    identity_payload.pop(identity_field, None)
    if canonical_sha256(identity_payload) != expected_identity:
        raise ValueError(f"{label} payload hash mismatch")
    return raw


def _identity_list(raw: dict[str, object], key: str, label: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise TypeError(f"{label} must be a non-empty identity list")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must contain SHA256 strings")
    result = tuple(cast(list[str], value))
    _identity_tuple(result, label)
    return result


def _assert_row_headers(
    raw: dict[str, object],
    *,
    activation_identity: str,
    vault_id: str | None = None,
    event_at_ms: int | None = None,
    label: str,
) -> None:
    if raw.get("activation_identity") != activation_identity:
        raise ValueError(f"{label} activation header mismatch")
    if vault_id is not None and raw.get("vault_id") != vault_id:
        raise ValueError(f"{label} vault header mismatch")
    if event_at_ms is not None:
        payload_time = raw.get("snapshot_at_ms")
        if payload_time is None:
            payload_time = raw.get("filled_at_ms")
        if payload_time is None:
            payload_time = raw.get("decided_at_ms")
        if payload_time != event_at_ms:
            raise ValueError(f"{label} event-time header mismatch")


def _vault_financial_state(snapshot: Epoch2VaultAccountingSnapshot) -> tuple[object, ...]:
    return (
        snapshot.activation_identity,
        snapshot.vault_id,
        snapshot.starting_cash_usdt,
        snapshot.cash_usdt,
        snapshot.positions,
        snapshot.marked_exposure_usdt,
        snapshot.nav_usdt,
        snapshot.realized_pnl_usdt,
        snapshot.unrealized_pnl_usdt,
        snapshot.high_water_nav_usdt,
        snapshot.drawdown_fraction,
        snapshot.fee_usdt,
        snapshot.spread_usdt,
        snapshot.slippage_usdt,
        snapshot.turnover_notional_usdt,
        snapshot.turnover_fraction,
        snapshot.closed_trade_count,
        snapshot.win_count,
        snapshot.loss_count,
        snapshot.breakeven_count,
        snapshot.expectancy_usdt_per_closed_trade,
        snapshot.outcome_distribution,
        snapshot.metrics_status,
        snapshot.real_capital,
    )


@dataclass(frozen=True, slots=True)
class R22Epoch2AccountingBundle:
    bundle_identity: str
    activation_identity: str
    intent_identity: str
    fill_identity: str
    vault_id: PaperVaultId
    before_vault_snapshot_identities: tuple[str, ...]
    after_vault_snapshot_identities: tuple[str, ...]
    before_consolidated_snapshot_identity: str
    after_consolidated_snapshot_identity: str
    snapshot_at_ms: int
    schema_version: str = R22_BUNDLE_SCHEMA_VERSION
    engine_version: str = R22_BUNDLE_ENGINE_VERSION
    atomic_same_database: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.bundle_identity, "R22 bundle"),
            (self.activation_identity, "R22 activation"),
            (self.intent_identity, "R22 intent"),
            (self.fill_identity, "R22 fill"),
            (self.before_consolidated_snapshot_identity, "R22 before parent"),
            (self.after_consolidated_snapshot_identity, "R22 after parent"),
        ):
            _require_sha256(identity, label)
        _identity_tuple(self.before_vault_snapshot_identities, "R22 before vault")
        _identity_tuple(self.after_vault_snapshot_identities, "R22 after vault")
        if len(self.before_vault_snapshot_identities) != len(PaperVaultId):
            raise ValueError("R22 bundle requires exactly three before-vault snapshots")
        if len(self.after_vault_snapshot_identities) != len(PaperVaultId):
            raise ValueError("R22 bundle requires exactly three after-vault snapshots")
        if self.snapshot_at_ms < 0:
            raise ValueError("R22 bundle snapshot time must be non-negative")
        if self.schema_version != R22_BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported R22 bundle schema")
        if self.engine_version != R22_BUNDLE_ENGINE_VERSION:
            raise ValueError("unsupported R22 bundle engine")
        if not self.atomic_same_database:
            raise ValueError("R22 canonical bundle must remain one SQLite transaction")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("R22 bundle cannot grant production or real-capital authority")
        if self.bundle_identity != canonical_sha256(_bundle_payload(self)):
            raise ValueError("R22 bundle identity mismatch")


def _bundle_payload(bundle: R22Epoch2AccountingBundle) -> dict[str, object]:
    return {
        "activation_identity": bundle.activation_identity,
        "after_consolidated_snapshot_identity": (
            bundle.after_consolidated_snapshot_identity
        ),
        "after_vault_snapshot_identities": bundle.after_vault_snapshot_identities,
        "atomic_same_database": bundle.atomic_same_database,
        "before_consolidated_snapshot_identity": (
            bundle.before_consolidated_snapshot_identity
        ),
        "before_vault_snapshot_identities": bundle.before_vault_snapshot_identities,
        "engine_version": bundle.engine_version,
        "fill_identity": bundle.fill_identity,
        "intent_identity": bundle.intent_identity,
        "production_authority": bundle.production_authority,
        "real_capital": bundle.real_capital,
        "schema_version": bundle.schema_version,
        "snapshot_at_ms": bundle.snapshot_at_ms,
        "vault_id": bundle.vault_id,
    }


def build_epoch2_accounting_bundle(
    before: Epoch2LedgerState,
    *,
    intent: PaperTapeIntent,
    fill: PaperTapeFill,
    after_vaults: tuple[Epoch2VaultAccountingSnapshot, ...],
    after_consolidated: Epoch2ConsolidatedAccountingSnapshot,
) -> R22Epoch2AccountingBundle:
    if intent.action is PaperAction.HOLD_CASH:
        raise ValueError("R22 HOLD_CASH is a decision only and cannot create an accounting bundle")
    if intent.activation_identity != before.activation.activation_identity:
        raise ValueError("R22 intent does not belong to current Epoch2 activation")
    if fill.intent_identity != intent.intent_identity:
        raise ValueError("R22 fill must bind the exact immutable intent")
    if fill.activation_identity != before.activation.activation_identity:
        raise ValueError("R22 fill activation mismatch")
    if fill.vault_id is not intent.vault_id:
        raise ValueError("R22 fill vault mismatch")

    before_by_vault = {item.vault_id: item for item in before.vault_snapshots}
    after_by_vault = {item.vault_id: item for item in after_vaults}
    if set(before_by_vault) != set(PaperVaultId) or set(after_by_vault) != set(PaperVaultId):
        raise ValueError("R22 bundle requires one before and after snapshot per vault")
    if len(after_vaults) != len(PaperVaultId):
        raise ValueError("R22 bundle requires exactly three after-vault snapshots")

    snapshot_times = {item.snapshot_at_ms for item in after_vaults}
    if snapshot_times != {fill.snapshot_at_ms}:
        raise ValueError("R22 after-vault snapshots must share the fill accounting timestamp")
    target_before = before_by_vault[intent.vault_id]
    target_after = after_by_vault[intent.vault_id]
    if fill.before_snapshot_identity != target_before.snapshot_identity:
        raise ValueError("R22 fill before-snapshot does not match canonical Epoch2 state")
    if fill.after_snapshot_identity != target_after.snapshot_identity:
        raise ValueError("R22 fill after-snapshot does not match target vault")

    for vault_id in PaperVaultId:
        previous = before_by_vault[vault_id]
        current = after_by_vault[vault_id]
        if current.activation_identity != before.activation.activation_identity:
            raise ValueError("R22 after-vault activation mismatch")
        if current.previous_snapshot_identity != previous.snapshot_identity:
            raise ValueError("R22 after-vault lineage must point to exact previous state")
        if (
            vault_id is not intent.vault_id
            and _vault_financial_state(current) != _vault_financial_state(previous)
        ):
            raise ValueError("R22 accounting bundle cannot mutate a non-target vault")

    expected_parent = build_consolidated_epoch2_snapshot(
        tuple(after_by_vault[vault_id] for vault_id in PaperVaultId),
        previous=before.consolidated_snapshot,
    )
    if after_consolidated != expected_parent:
        raise ValueError("R22 consolidated snapshot must exactly reconstruct from three vaults")
    if fill.snapshot_at_ms != after_consolidated.snapshot_at_ms:
        raise ValueError("R22 fill and consolidated accounting timestamps must match")

    before_ids = tuple(sorted(item.snapshot_identity for item in before.vault_snapshots))
    after_ids = tuple(sorted(item.snapshot_identity for item in after_vaults))
    payload: dict[str, object] = {
        "activation_identity": before.activation.activation_identity,
        "after_consolidated_snapshot_identity": after_consolidated.snapshot_identity,
        "after_vault_snapshot_identities": after_ids,
        "atomic_same_database": True,
        "before_consolidated_snapshot_identity": (
            before.consolidated_snapshot.snapshot_identity
        ),
        "before_vault_snapshot_identities": before_ids,
        "engine_version": R22_BUNDLE_ENGINE_VERSION,
        "fill_identity": fill.fill_identity,
        "intent_identity": intent.intent_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": R22_BUNDLE_SCHEMA_VERSION,
        "snapshot_at_ms": fill.snapshot_at_ms,
        "vault_id": intent.vault_id,
    }
    return R22Epoch2AccountingBundle(
        bundle_identity=canonical_sha256(payload),
        activation_identity=before.activation.activation_identity,
        intent_identity=intent.intent_identity,
        fill_identity=fill.fill_identity,
        vault_id=intent.vault_id,
        before_vault_snapshot_identities=before_ids,
        after_vault_snapshot_identities=after_ids,
        before_consolidated_snapshot_identity=(
            before.consolidated_snapshot.snapshot_identity
        ),
        after_consolidated_snapshot_identity=after_consolidated.snapshot_identity,
        snapshot_at_ms=fill.snapshot_at_ms,
    )


class R22Epoch2AtomicTape:
    """Append R22 evidence and R21 accounting in one local SQLite transaction."""

    def __init__(self, epoch2_path: Path) -> None:
        self.epoch2_path = epoch2_path

    def initialize(self) -> None:
        Epoch2CanonicalLedger(self.epoch2_path).initialize()
        with sqlite3.connect(self.epoch2_path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS r22_epoch2_intents (
                    intent_identity TEXT PRIMARY KEY,
                    activation_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS r22_epoch2_fills (
                    fill_identity TEXT PRIMARY KEY,
                    intent_identity TEXT NOT NULL UNIQUE,
                    activation_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS r22_epoch2_bundles (
                    bundle_identity TEXT PRIMARY KEY,
                    fill_identity TEXT NOT NULL UNIQUE,
                    activation_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            for table in (
                "r22_epoch2_intents",
                "r22_epoch2_fills",
                "r22_epoch2_bundles",
            ):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, 'immutable R22 Epoch2 audit tape');
                        END"""
                    )

    def append_hold_decision(self, intent: PaperTapeIntent) -> bool:
        if intent.action is not PaperAction.HOLD_CASH:
            raise ValueError("R22 hold-decision API accepts HOLD_CASH only")
        self.initialize()
        with sqlite3.connect(self.epoch2_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_activation(connection, intent.activation_identity)
            existing = connection.execute(
                """SELECT payload_json FROM r22_epoch2_intents
                WHERE intent_identity = ?""",
                (intent.intent_identity,),
            ).fetchone()
            payload = canonical_json(intent)
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("R22 immutable HOLD_CASH identity conflict")
                return False
            self._assert_intent_predecessor(connection, intent)
            connection.execute(
                """INSERT INTO r22_epoch2_intents (
                    intent_identity, activation_identity, vault_id, event_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    intent.intent_identity,
                    intent.activation_identity,
                    intent.vault_id.value,
                    intent.decided_at_ms,
                    payload,
                ),
            )
        return True

    def append_accounting_bundle(
        self,
        before: Epoch2LedgerState,
        *,
        intent: PaperTapeIntent,
        fill: PaperTapeFill,
        after_vaults: tuple[Epoch2VaultAccountingSnapshot, ...],
        after_consolidated: Epoch2ConsolidatedAccountingSnapshot,
        bundle: R22Epoch2AccountingBundle,
    ) -> bool:
        expected_bundle = build_epoch2_accounting_bundle(
            before,
            intent=intent,
            fill=fill,
            after_vaults=after_vaults,
            after_consolidated=after_consolidated,
        )
        if bundle != expected_bundle:
            raise ValueError("R22 supplied bundle is not the deterministic accounting bundle")
        self.initialize()
        with sqlite3.connect(self.epoch2_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_activation(connection, bundle.activation_identity)
            existing = connection.execute(
                """SELECT payload_json FROM r22_epoch2_bundles
                WHERE bundle_identity = ?""",
                (bundle.bundle_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != canonical_json(bundle):
                    raise ValueError("R22 immutable accounting bundle identity conflict")
                self._assert_persisted_bundle(
                    connection,
                    intent=intent,
                    fill=fill,
                    after_vaults=after_vaults,
                    after_consolidated=after_consolidated,
                )
                return False

            self._assert_current_r21_state(connection, before)
            self._assert_intent_predecessor(connection, intent)
            self._assert_fill_predecessor(connection, fill)

            connection.execute(
                """INSERT INTO r22_epoch2_intents (
                    intent_identity, activation_identity, vault_id, event_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    intent.intent_identity,
                    intent.activation_identity,
                    intent.vault_id.value,
                    intent.decided_at_ms,
                    canonical_json(intent),
                ),
            )
            for snapshot in sorted(after_vaults, key=lambda item: item.vault_id.value):
                connection.execute(
                    """INSERT INTO r21_vault_snapshots (
                        snapshot_identity, vault_id, payload_json, snapshot_at_ms
                    ) VALUES (?, ?, ?, ?)""",
                    (
                        snapshot.snapshot_identity,
                        snapshot.vault_id.value,
                        canonical_json(snapshot),
                        snapshot.snapshot_at_ms,
                    ),
                )
            connection.execute(
                """INSERT INTO r21_consolidated_snapshots (
                    snapshot_identity, payload_json, snapshot_at_ms
                ) VALUES (?, ?, ?)""",
                (
                    after_consolidated.snapshot_identity,
                    canonical_json(after_consolidated),
                    after_consolidated.snapshot_at_ms,
                ),
            )
            connection.execute(
                """INSERT INTO r22_epoch2_fills (
                    fill_identity, intent_identity, activation_identity,
                    vault_id, event_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    fill.fill_identity,
                    fill.intent_identity,
                    fill.activation_identity,
                    fill.vault_id.value,
                    fill.filled_at_ms,
                    canonical_json(fill),
                ),
            )
            connection.execute(
                """INSERT INTO r22_epoch2_bundles (
                    bundle_identity, fill_identity, activation_identity,
                    vault_id, event_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    bundle.bundle_identity,
                    bundle.fill_identity,
                    bundle.activation_identity,
                    bundle.vault_id.value,
                    bundle.snapshot_at_ms,
                    canonical_json(bundle),
                ),
            )
        return True

    def audit_bundle_read_only(self, bundle_identity: str) -> dict[str, object]:
        """Verify one persisted R22/R21 accounting bundle without mutating the ledger."""
        _require_sha256(bundle_identity, "R22 audit bundle")
        if not self.epoch2_path.is_file():
            raise ValueError("R22 Epoch2 ledger is missing")
        uri = f"{self.epoch2_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            bundle_row = connection.execute(
                """SELECT fill_identity, activation_identity, vault_id,
                event_at_ms, payload_json
                FROM r22_epoch2_bundles WHERE bundle_identity = ?""",
                (bundle_identity,),
            ).fetchone()
            if bundle_row is None:
                raise ValueError("R22 audit bundle not found")
            bundle = _verify_embedded_identity(
                str(bundle_row[4]),
                identity_field="bundle_identity",
                expected_identity=bundle_identity,
                label="R22 bundle",
            )
            activation_identity = str(bundle_row[1])
            vault_id = str(bundle_row[2])
            event_at_ms = int(bundle_row[3])
            _assert_row_headers(
                bundle,
                activation_identity=activation_identity,
                vault_id=vault_id,
                event_at_ms=event_at_ms,
                label="R22 bundle",
            )
            if bundle.get("fill_identity") != str(bundle_row[0]):
                raise ValueError("R22 bundle fill header mismatch")
            if (
                bundle.get("real_capital") != 0
                or bundle.get("production_authority") is not False
                or bundle.get("atomic_same_database") is not True
            ):
                raise ValueError("R22 stored bundle authority/atomicity mismatch")

            activation_row = connection.execute(
                """SELECT payload_json FROM r21_epoch2_activation
                WHERE activation_identity = ?""",
                (activation_identity,),
            ).fetchone()
            if activation_row is None:
                raise ValueError("R22 bundle activation evidence missing")
            activation = _verify_embedded_identity(
                str(activation_row[0]),
                identity_field="activation_identity",
                expected_identity=activation_identity,
                label="R21 activation",
            )
            if activation.get("real_capital") != 0:
                raise ValueError("R21 activation REAL_CAPITAL boundary mismatch")

            intent_identity = str(bundle["intent_identity"])
            intent_row = connection.execute(
                """SELECT activation_identity, vault_id, event_at_ms, payload_json
                FROM r22_epoch2_intents WHERE intent_identity = ?""",
                (intent_identity,),
            ).fetchone()
            if intent_row is None:
                raise ValueError("R22 bundle intent evidence missing")
            intent = _verify_embedded_identity(
                str(intent_row[3]),
                identity_field="intent_identity",
                expected_identity=intent_identity,
                label="R22 intent",
            )
            _assert_row_headers(
                intent,
                activation_identity=str(intent_row[0]),
                vault_id=str(intent_row[1]),
                event_at_ms=int(intent_row[2]),
                label="R22 intent",
            )
            if (
                str(intent_row[0]) != activation_identity
                or str(intent_row[1]) != vault_id
                or intent.get("real_capital") != 0
                or intent.get("production_authority") is not False
            ):
                raise ValueError("R22 intent bundle lineage/authority mismatch")

            fill_identity = str(bundle["fill_identity"])
            fill_row = connection.execute(
                """SELECT intent_identity, activation_identity, vault_id,
                event_at_ms, payload_json
                FROM r22_epoch2_fills WHERE fill_identity = ?""",
                (fill_identity,),
            ).fetchone()
            if fill_row is None:
                raise ValueError("R22 bundle fill evidence missing")
            fill = _verify_embedded_identity(
                str(fill_row[4]),
                identity_field="fill_identity",
                expected_identity=fill_identity,
                label="R22 fill",
            )
            _assert_row_headers(
                fill,
                activation_identity=str(fill_row[1]),
                vault_id=str(fill_row[2]),
                event_at_ms=int(fill_row[3]),
                label="R22 fill",
            )
            if (
                str(fill_row[0]) != intent_identity
                or str(fill_row[1]) != activation_identity
                or str(fill_row[2]) != vault_id
                or fill.get("intent_identity") != intent_identity
                or fill.get("real_capital") != 0
                or fill.get("production_authority") is not False
            ):
                raise ValueError("R22 fill bundle lineage/authority mismatch")

            before_parent_identity = str(bundle["before_consolidated_snapshot_identity"])
            after_parent_identity = str(bundle["after_consolidated_snapshot_identity"])
            before_parent = self._read_verified_snapshot(
                connection,
                table="r21_consolidated_snapshots",
                identity=before_parent_identity,
                label="R21 before consolidated",
            )
            after_parent = self._read_verified_snapshot(
                connection,
                table="r21_consolidated_snapshots",
                identity=after_parent_identity,
                label="R21 after consolidated",
            )
            if (
                before_parent.get("activation_identity") != activation_identity
                or after_parent.get("activation_identity") != activation_identity
                or after_parent.get("previous_snapshot_identity") != before_parent_identity
                or after_parent.get("snapshot_at_ms") != event_at_ms
            ):
                raise ValueError("R22 consolidated before/after lineage mismatch")

            before_ids = _identity_list(
                bundle,
                "before_vault_snapshot_identities",
                "R22 before vault",
            )
            after_ids = _identity_list(
                bundle,
                "after_vault_snapshot_identities",
                "R22 after vault",
            )
            before_vaults = self._read_vault_set(connection, before_ids, "R21 before vault")
            after_vaults = self._read_vault_set(connection, after_ids, "R21 after vault")
            if tuple(sorted(cast(list[str], before_parent["vault_snapshot_identities"]))) != before_ids:
                raise ValueError("R22 before parent does not bind exact vault set")
            if tuple(sorted(cast(list[str], after_parent["vault_snapshot_identities"]))) != after_ids:
                raise ValueError("R22 after parent does not bind exact vault set")

            for current_vault in PaperVaultId:
                key = current_vault.value
                before_vault = before_vaults[key]
                after_vault = after_vaults[key]
                before_identity = str(before_vault["snapshot_identity"])
                if (
                    before_vault.get("activation_identity") != activation_identity
                    or after_vault.get("activation_identity") != activation_identity
                    or after_vault.get("previous_snapshot_identity") != before_identity
                    or after_vault.get("snapshot_at_ms") != event_at_ms
                ):
                    raise ValueError("R22 vault before/after lineage mismatch")
                if key != vault_id and self._raw_financial_state(after_vault) != (
                    self._raw_financial_state(before_vault)
                ):
                    raise ValueError("R22 audit found hidden non-target vault mutation")

            target_before = before_vaults[vault_id]
            target_after = after_vaults[vault_id]
            if (
                fill.get("before_snapshot_identity")
                != target_before.get("snapshot_identity")
                or fill.get("after_snapshot_identity")
                != target_after.get("snapshot_identity")
                or fill.get("snapshot_at_ms") != event_at_ms
            ):
                raise ValueError("R22 fill does not bind exact audited target snapshots")
        return bundle

    def audit_all_read_only(self) -> tuple[int, int, int]:
        """Replay-check all intent/fill chains and every accounting bundle read-only."""
        if not self.epoch2_path.is_file():
            raise ValueError("R22 Epoch2 ledger is missing")
        uri = f"{self.epoch2_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            intents = connection.execute(
                """SELECT intent_identity, activation_identity, vault_id,
                event_at_ms, payload_json
                FROM r22_epoch2_intents
                ORDER BY vault_id, event_at_ms, intent_identity"""
            ).fetchall()
            previous_intent: dict[str, str] = {}
            for row in intents:
                identity = str(row[0])
                vault_id = str(row[2])
                raw = _verify_embedded_identity(
                    str(row[4]),
                    identity_field="intent_identity",
                    expected_identity=identity,
                    label="R22 replay intent",
                )
                _assert_row_headers(
                    raw,
                    activation_identity=str(row[1]),
                    vault_id=vault_id,
                    event_at_ms=int(row[3]),
                    label="R22 replay intent",
                )
                if raw.get("previous_intent_identity") != previous_intent.get(vault_id):
                    raise ValueError("R22 replay intent predecessor chain mismatch")
                previous_intent[vault_id] = identity

            fills = connection.execute(
                """SELECT fill_identity, intent_identity, activation_identity,
                vault_id, event_at_ms, payload_json
                FROM r22_epoch2_fills
                ORDER BY vault_id, event_at_ms, fill_identity"""
            ).fetchall()
            previous_fill: dict[str, str] = {}
            fill_by_intent: dict[str, str] = {}
            for row in fills:
                identity = str(row[0])
                intent_identity = str(row[1])
                vault_id = str(row[3])
                raw = _verify_embedded_identity(
                    str(row[5]),
                    identity_field="fill_identity",
                    expected_identity=identity,
                    label="R22 replay fill",
                )
                _assert_row_headers(
                    raw,
                    activation_identity=str(row[2]),
                    vault_id=vault_id,
                    event_at_ms=int(row[4]),
                    label="R22 replay fill",
                )
                if raw.get("intent_identity") != intent_identity:
                    raise ValueError("R22 replay fill/intent identity mismatch")
                if raw.get("previous_fill_identity") != previous_fill.get(vault_id):
                    raise ValueError("R22 replay fill predecessor chain mismatch")
                if intent_identity in fill_by_intent:
                    raise ValueError("R22 replay found multiple fills for one intent")
                fill_by_intent[intent_identity] = identity
                previous_fill[vault_id] = identity

            bundle_rows = connection.execute(
                """SELECT bundle_identity, fill_identity
                FROM r22_epoch2_bundles
                ORDER BY event_at_ms, bundle_identity"""
            ).fetchall()
            bundle_by_fill = {str(row[1]): str(row[0]) for row in bundle_rows}
            if len(bundle_by_fill) != len(bundle_rows):
                raise ValueError("R22 replay found duplicate bundle fill bindings")

            for row in intents:
                raw = _decode_object(str(row[4]), "R22 replay intent")
                if raw.get("action") == PaperAction.HOLD_CASH.value:
                    if str(row[0]) in fill_by_intent:
                        raise ValueError("R22 HOLD_CASH replay unexpectedly has a fill")
                elif str(row[0]) not in fill_by_intent:
                    raise ValueError("R22 trade intent replay is missing its fill")
            for fill_identity in (str(row[0]) for row in fills):
                if fill_identity not in bundle_by_fill:
                    raise ValueError("R22 fill replay is missing its accounting bundle")

            bundle_ids = tuple(str(row[0]) for row in bundle_rows)
        for bundle_identity in bundle_ids:
            self.audit_bundle_read_only(bundle_identity)
        return len(intents), len(fills), len(bundle_ids)

    @staticmethod
    def _read_verified_snapshot(
        connection: sqlite3.Connection,
        *,
        table: str,
        identity: str,
        label: str,
    ) -> dict[str, object]:
        row = connection.execute(
            f"SELECT payload_json FROM {table} WHERE snapshot_identity = ?",
            (identity,),
        ).fetchone()
        if row is None:
            raise ValueError(f"{label} evidence missing")
        return _verify_embedded_identity(
            str(row[0]),
            identity_field="snapshot_identity",
            expected_identity=identity,
            label=label,
        )

    @classmethod
    def _read_vault_set(
        cls,
        connection: sqlite3.Connection,
        identities: tuple[str, ...],
        label: str,
    ) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for identity in identities:
            raw = cls._read_verified_snapshot(
                connection,
                table="r21_vault_snapshots",
                identity=identity,
                label=label,
            )
            vault_id = raw.get("vault_id")
            if not isinstance(vault_id, str) or vault_id in result:
                raise ValueError(f"{label} vault set is invalid or duplicated")
            result[vault_id] = raw
        if set(result) != {item.value for item in PaperVaultId}:
            raise ValueError(f"{label} must contain exactly all three vaults")
        return result

    @staticmethod
    def _raw_financial_state(raw: dict[str, object]) -> tuple[object, ...]:
        return tuple(
            raw.get(key)
            for key in (
                "starting_cash_usdt",
                "cash_usdt",
                "positions",
                "marked_exposure_usdt",
                "nav_usdt",
                "realized_pnl_usdt",
                "unrealized_pnl_usdt",
                "high_water_nav_usdt",
                "drawdown_fraction",
                "fee_usdt",
                "spread_usdt",
                "slippage_usdt",
                "turnover_notional_usdt",
                "turnover_fraction",
                "closed_trade_count",
                "win_count",
                "loss_count",
                "breakeven_count",
                "expectancy_usdt_per_closed_trade",
                "outcome_distribution",
                "metrics_status",
                "real_capital",
            )
        )

    @staticmethod
    def _assert_activation(
        connection: sqlite3.Connection,
        activation_identity: str,
    ) -> None:
        row = connection.execute(
            """SELECT activation_identity FROM r21_epoch2_activation
            WHERE singleton = 1"""
        ).fetchone()
        if row is None or str(row[0]) != activation_identity:
            raise ValueError("R22 atomic tape activation does not match R21 Epoch2")

    @staticmethod
    def _assert_intent_predecessor(
        connection: sqlite3.Connection,
        intent: PaperTapeIntent,
    ) -> None:
        row = connection.execute(
            """SELECT intent_identity, event_at_ms FROM r22_epoch2_intents
            WHERE vault_id = ? ORDER BY event_at_ms DESC, intent_identity DESC LIMIT 1""",
            (intent.vault_id.value,),
        ).fetchone()
        expected = None if row is None else str(row[0])
        if intent.previous_intent_identity != expected:
            raise ValueError("R22 atomic intent predecessor is stale or forked")
        if row is not None and intent.decided_at_ms <= int(row[1]):
            raise ValueError("R22 atomic intent cannot backfill or fork a timestamp")

    @staticmethod
    def _assert_fill_predecessor(
        connection: sqlite3.Connection,
        fill: PaperTapeFill,
    ) -> None:
        row = connection.execute(
            """SELECT fill_identity, event_at_ms FROM r22_epoch2_fills
            WHERE vault_id = ? ORDER BY event_at_ms DESC, fill_identity DESC LIMIT 1""",
            (fill.vault_id.value,),
        ).fetchone()
        expected = None if row is None else str(row[0])
        if fill.previous_fill_identity != expected:
            raise ValueError("R22 atomic fill predecessor is stale or forked")
        if row is not None and fill.filled_at_ms <= int(row[1]):
            raise ValueError("R22 atomic fill cannot backfill or fork a timestamp")

    @staticmethod
    def _assert_current_r21_state(
        connection: sqlite3.Connection,
        before: Epoch2LedgerState,
    ) -> None:
        for snapshot in before.vault_snapshots:
            row = connection.execute(
                """SELECT snapshot_identity, snapshot_at_ms FROM r21_vault_snapshots
                WHERE vault_id = ?
                ORDER BY snapshot_at_ms DESC, snapshot_identity DESC LIMIT 1""",
                (snapshot.vault_id.value,),
            ).fetchone()
            if row is None:
                raise ValueError("R22 atomic commit requires existing R21 vault state")
            if str(row[0]) != snapshot.snapshot_identity:
                raise ValueError("R22 atomic commit detected stale R21 vault state")
            if int(row[1]) != snapshot.snapshot_at_ms:
                raise ValueError("R22 atomic commit detected R21 vault timestamp mismatch")
        parent = connection.execute(
            """SELECT snapshot_identity, snapshot_at_ms
            FROM r21_consolidated_snapshots
            ORDER BY snapshot_at_ms DESC, snapshot_identity DESC LIMIT 1"""
        ).fetchone()
        if parent is None:
            raise ValueError("R22 atomic commit requires existing R21 parent state")
        if str(parent[0]) != before.consolidated_snapshot.snapshot_identity:
            raise ValueError("R22 atomic commit detected stale R21 parent state")
        if int(parent[1]) != before.consolidated_snapshot.snapshot_at_ms:
            raise ValueError("R22 atomic commit detected R21 parent timestamp mismatch")

    @staticmethod
    def _assert_persisted_bundle(
        connection: sqlite3.Connection,
        *,
        intent: PaperTapeIntent,
        fill: PaperTapeFill,
        after_vaults: tuple[Epoch2VaultAccountingSnapshot, ...],
        after_consolidated: Epoch2ConsolidatedAccountingSnapshot,
    ) -> None:
        expected_rows = (
            (
                "r22_epoch2_intents",
                "intent_identity",
                intent.intent_identity,
                canonical_json(intent),
            ),
            (
                "r22_epoch2_fills",
                "fill_identity",
                fill.fill_identity,
                canonical_json(fill),
            ),
            (
                "r21_consolidated_snapshots",
                "snapshot_identity",
                after_consolidated.snapshot_identity,
                canonical_json(after_consolidated),
            ),
        )
        for table, key, identity, payload in expected_rows:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE {key} = ?",
                (identity,),
            ).fetchone()
            if row is None or str(row[0]) != payload:
                raise ValueError("R22 idempotent replay found incomplete persisted bundle")
        for snapshot in after_vaults:
            row = connection.execute(
                """SELECT payload_json FROM r21_vault_snapshots
                WHERE snapshot_identity = ?""",
                (snapshot.snapshot_identity,),
            ).fetchone()
            if row is None or str(row[0]) != canonical_json(snapshot):
                raise ValueError("R22 idempotent replay found incomplete vault evidence")


def r22_payload_sha256(payload_json: str) -> str:
    """Small exported helper for offline audit tooling."""
    return sha256_text(payload_json)
