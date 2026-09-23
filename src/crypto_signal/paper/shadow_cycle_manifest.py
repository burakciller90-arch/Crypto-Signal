"""R25 Slice 12: immutable manifest for one accepted shadow decision cycle.

The manifest binds the exact identities produced by the accepted shadow rail:
forecast -> Decision Proof -> Capital Science -> Position Sizing -> explicit
review (optional) -> R22 preview -> shadow intent journal record.

It is isolated from canonical Epoch 2 and carries no execution authority.
REAL_CAPITAL=0.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import SizingMethod
from crypto_signal.paper.shadow_replay_orchestrator import ShadowReplayCycleResult

SHADOW_CYCLE_MANIFEST_SCHEMA_VERSION = "r25-shadow-cycle-manifest-v1/1"
SHADOW_CYCLE_MANIFEST_ENGINE_VERSION = "r25-shadow-cycle-manifest-v1/1"
SHADOW_CYCLE_MANIFEST_SUFFIX = ".shadow-cycle.sqlite3"
REAL_CAPITAL = 0

_RECORD_TABLE = "r25_shadow_cycle_manifest"
_META_TABLE = "r25_shadow_cycle_meta"
_ALLOWED_TABLES = {_RECORD_TABLE, _META_TABLE}


class ShadowCycleManifestDisposition(StrEnum):
    INSERTED = "INSERTED"
    IDEMPOTENT = "IDEMPOTENT"


@dataclass(frozen=True, slots=True)
class ShadowCycleManifestRecord:
    manifest_identity: str
    cycle_identity: str
    forecast_identity: str
    proof_identity: str
    capital_bridge_identity: str
    sizing_bridge_identity: str
    review_selection_identity: str | None
    preview_identity: str
    journal_record_identity: str
    vault_id: PaperVaultId
    reviewed_method: SizingMethod | None
    event_at_ms: int
    previous_manifest_identity: str | None
    schema_version: str = SHADOW_CYCLE_MANIFEST_SCHEMA_VERSION
    engine_version: str = SHADOW_CYCLE_MANIFEST_ENGINE_VERSION
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.manifest_identity, "shadow cycle manifest"),
            (self.cycle_identity, "shadow cycle"),
            (self.forecast_identity, "shadow cycle forecast"),
            (self.proof_identity, "shadow cycle proof"),
            (self.capital_bridge_identity, "shadow cycle capital"),
            (self.sizing_bridge_identity, "shadow cycle sizing"),
            (self.preview_identity, "shadow cycle preview"),
            (self.journal_record_identity, "shadow cycle journal record"),
        ):
            _require_sha256(value, label)
        if self.review_selection_identity is not None:
            _require_sha256(
                self.review_selection_identity,
                "shadow cycle review selection",
            )
        if self.previous_manifest_identity is not None:
            _require_sha256(
                self.previous_manifest_identity,
                "shadow cycle previous manifest",
            )
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("shadow cycle manifest requires canonical vault id")
        if self.reviewed_method is not None and not isinstance(
            self.reviewed_method,
            SizingMethod,
        ):
            raise TypeError("shadow cycle reviewed method is invalid")
        if self.event_at_ms < 0:
            raise ValueError("shadow cycle event time must be non-negative")
        if self.schema_version != SHADOW_CYCLE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported shadow cycle manifest schema")
        if self.engine_version != SHADOW_CYCLE_MANIFEST_ENGINE_VERSION:
            raise ValueError("unsupported shadow cycle manifest engine")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("shadow cycle manifest cannot grant authority")
        if self.manifest_identity != canonical_sha256(_record_payload(self)):
            raise ValueError("shadow cycle manifest identity mismatch")


@dataclass(frozen=True, slots=True)
class ShadowCycleManifestAppendResult:
    disposition: ShadowCycleManifestDisposition
    record: ShadowCycleManifestRecord


@dataclass(frozen=True, slots=True)
class ShadowCycleManifestStatus:
    record_count: int
    last_manifest_identities: tuple[tuple[PaperVaultId, str], ...]
    quick_check_ok: bool
    read_only_verified: bool
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.record_count < 0:
            raise ValueError("shadow cycle manifest count cannot be negative")
        expected = tuple(
            sorted(self.last_manifest_identities, key=lambda item: item[0].value)
        )
        if self.last_manifest_identities != expected:
            raise ValueError("shadow cycle manifest last identities not canonical")
        for vault_id, identity in self.last_manifest_identities:
            if not isinstance(vault_id, PaperVaultId):
                raise TypeError("shadow cycle manifest status vault invalid")
            _require_sha256(identity, "shadow cycle status manifest")
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("shadow cycle manifest status must be verified")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("shadow cycle manifest status cannot grant authority")


class R25ShadowCycleManifest:
    """Append-only SQLite manifest isolated from all canonical paper ledgers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(SHADOW_CYCLE_MANIFEST_SUFFIX):
            raise ValueError(
                f"shadow cycle manifest path must end with "
                f"{SHADOW_CYCLE_MANIFEST_SUFFIX}"
            )

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            existing = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            unexpected = existing - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "shadow cycle manifest refuses database with non-shadow tables"
                )
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_RECORD_TABLE} (
                    manifest_identity TEXT PRIMARY KEY,
                    cycle_identity TEXT NOT NULL UNIQUE,
                    forecast_identity TEXT NOT NULL,
                    proof_identity TEXT NOT NULL,
                    capital_bridge_identity TEXT NOT NULL,
                    sizing_bridge_identity TEXT NOT NULL,
                    review_selection_identity TEXT,
                    preview_identity TEXT NOT NULL,
                    journal_record_identity TEXT NOT NULL,
                    vault_id TEXT NOT NULL,
                    reviewed_method TEXT,
                    event_at_ms INTEGER NOT NULL,
                    previous_manifest_identity TEXT,
                    payload_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    canonical_epoch2_write_authority INTEGER NOT NULL,
                    production_authority INTEGER NOT NULL,
                    real_capital INTEGER NOT NULL
                )"""
            )
            for action in ("UPDATE", "DELETE"):
                db.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS
                    {_RECORD_TABLE}_immutable_{action.lower()}
                    BEFORE {action} ON {_RECORD_TABLE}
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable R25 shadow cycle manifest');
                    END"""
                )
                db.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS
                    {_META_TABLE}_immutable_{action.lower()}
                    BEFORE {action} ON {_META_TABLE}
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable R25 shadow cycle metadata');
                    END"""
                )
            expected_meta = {
                "engine_version": SHADOW_CYCLE_MANIFEST_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": SHADOW_CYCLE_MANIFEST_SCHEMA_VERSION,
                "semantic": "shadow_research_cycle_lineage_only",
            }
            for key, value in expected_meta.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE} (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError("shadow cycle manifest metadata mismatch")

    def append(
        self,
        cycle: ShadowReplayCycleResult,
    ) -> ShadowCycleManifestAppendResult:
        self.initialize()
        _validate_cycle(cycle)

        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                f"""SELECT manifest_identity, cycle_identity, forecast_identity,
                proof_identity, capital_bridge_identity, sizing_bridge_identity,
                review_selection_identity, preview_identity,
                journal_record_identity, vault_id, reviewed_method, event_at_ms,
                previous_manifest_identity, payload_json, schema_version,
                engine_version, canonical_epoch2_write_authority,
                production_authority, real_capital
                FROM {_RECORD_TABLE}
                WHERE cycle_identity = ?""",
                (cycle.cycle_identity,),
            ).fetchone()
            if existing is not None:
                record = _record_from_row(existing)
                expected = _record_from_cycle(
                    cycle,
                    previous_manifest_identity=record.previous_manifest_identity,
                )
                if record != expected:
                    raise ValueError("shadow cycle identity conflict")
                return ShadowCycleManifestAppendResult(
                    disposition=ShadowCycleManifestDisposition.IDEMPOTENT,
                    record=record,
                )

            last = db.execute(
                f"""SELECT manifest_identity, event_at_ms
                FROM {_RECORD_TABLE}
                WHERE vault_id = ?
                ORDER BY event_at_ms DESC, manifest_identity DESC
                LIMIT 1""",
                (cycle.vault_id.value,),
            ).fetchone()
            previous = None if last is None else str(last[0])
            if last is not None and cycle.preview.previewed_at_ms <= int(last[1]):
                raise ValueError(
                    "shadow cycle manifest cannot backfill or fork vault event time"
                )

            record = _record_from_cycle(
                cycle,
                previous_manifest_identity=previous,
            )
            payload_json = canonical_json(_record_payload(record))
            if sha256_text(payload_json) != record.manifest_identity:
                raise ValueError("shadow cycle manifest payload identity mismatch")
            db.execute(
                f"""INSERT INTO {_RECORD_TABLE} (
                    manifest_identity, cycle_identity, forecast_identity,
                    proof_identity, capital_bridge_identity,
                    sizing_bridge_identity, review_selection_identity,
                    preview_identity, journal_record_identity, vault_id,
                    reviewed_method, event_at_ms, previous_manifest_identity,
                    payload_json, schema_version, engine_version,
                    canonical_epoch2_write_authority, production_authority,
                    real_capital
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.manifest_identity,
                    record.cycle_identity,
                    record.forecast_identity,
                    record.proof_identity,
                    record.capital_bridge_identity,
                    record.sizing_bridge_identity,
                    record.review_selection_identity,
                    record.preview_identity,
                    record.journal_record_identity,
                    record.vault_id.value,
                    (
                        None
                        if record.reviewed_method is None
                        else record.reviewed_method.value
                    ),
                    record.event_at_ms,
                    record.previous_manifest_identity,
                    payload_json,
                    record.schema_version,
                    record.engine_version,
                    int(record.canonical_epoch2_write_authority),
                    int(record.production_authority),
                    record.real_capital,
                ),
            )
        return ShadowCycleManifestAppendResult(
            disposition=ShadowCycleManifestDisposition.INSERTED,
            record=record,
        )

    def read_latest(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ShadowCycleManifestRecord, ...]:
        if limit <= 0 or limit > 500:
            raise ValueError("shadow cycle manifest limit must be inside 1..500")
        self.verify_read_only()
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            rows = db.execute(
                f"""SELECT manifest_identity, cycle_identity, forecast_identity,
                proof_identity, capital_bridge_identity, sizing_bridge_identity,
                review_selection_identity, preview_identity,
                journal_record_identity, vault_id, reviewed_method, event_at_ms,
                previous_manifest_identity, payload_json, schema_version,
                engine_version, canonical_epoch2_write_authority,
                production_authority, real_capital
                FROM {_RECORD_TABLE}
                ORDER BY event_at_ms DESC, manifest_identity DESC
                LIMIT ?""",
                (limit,),
            ).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def verify_read_only(self) -> ShadowCycleManifestStatus:
        if not self.path.is_file():
            raise ValueError("shadow cycle manifest missing")
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            unexpected = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            } - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "shadow cycle manifest contains non-shadow tables"
                )
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("shadow cycle manifest quick_check failed")
            _verify_meta(db)

            rows = db.execute(
                f"""SELECT manifest_identity, cycle_identity, forecast_identity,
                proof_identity, capital_bridge_identity, sizing_bridge_identity,
                review_selection_identity, preview_identity,
                journal_record_identity, vault_id, reviewed_method, event_at_ms,
                previous_manifest_identity, payload_json, schema_version,
                engine_version, canonical_epoch2_write_authority,
                production_authority, real_capital
                FROM {_RECORD_TABLE}
                ORDER BY vault_id, event_at_ms, manifest_identity"""
            ).fetchall()

            last_by_vault: dict[PaperVaultId, tuple[str, int]] = {}
            for row in rows:
                record = _record_from_row(row)
                payload_json = str(row[13])
                if sha256_text(payload_json) != record.manifest_identity:
                    raise ValueError("shadow cycle persisted payload digest mismatch")
                raw = json.loads(payload_json)
                if not isinstance(raw, dict):
                    raise TypeError("shadow cycle manifest payload must be object")
                if canonical_sha256(raw) != record.manifest_identity:
                    raise ValueError("shadow cycle persisted payload identity mismatch")
                if (
                    raw.get("real_capital") != REAL_CAPITAL
                    or raw.get("production_authority") is not False
                    or raw.get("canonical_epoch2_write_authority") is not False
                ):
                    raise ValueError("shadow cycle authority boundary mismatch")

                prior = last_by_vault.get(record.vault_id)
                expected_previous = None if prior is None else prior[0]
                if record.previous_manifest_identity != expected_previous:
                    raise ValueError("shadow cycle predecessor chain mismatch")
                if prior is not None and record.event_at_ms <= prior[1]:
                    raise ValueError("shadow cycle event time is not monotonic")
                last_by_vault[record.vault_id] = (
                    record.manifest_identity,
                    record.event_at_ms,
                )

        latest = tuple(
            sorted(
                (
                    (vault_id, record_and_time[0])
                    for vault_id, record_and_time in last_by_vault.items()
                ),
                key=lambda item: item[0].value,
            )
        )
        return ShadowCycleManifestStatus(
            record_count=len(rows),
            last_manifest_identities=latest,
            quick_check_ok=True,
            read_only_verified=True,
        )


def _record_from_cycle(
    cycle: ShadowReplayCycleResult,
    *,
    previous_manifest_identity: str | None,
) -> ShadowCycleManifestRecord:
    review_identity = (
        None
        if cycle.reviewed_selection is None
        else cycle.reviewed_selection.selection_identity
    )
    payload = {
        "canonical_epoch2_write_authority": False,
        "capital_bridge_identity": cycle.capital.bridge_identity,
        "cycle_identity": cycle.cycle_identity,
        "engine_version": SHADOW_CYCLE_MANIFEST_ENGINE_VERSION,
        "event_at_ms": cycle.preview.previewed_at_ms,
        "forecast_identity": cycle.forecast_identity,
        "journal_record_identity": cycle.journal_append.record.record_identity,
        "preview_identity": cycle.preview.preview_identity,
        "previous_manifest_identity": previous_manifest_identity,
        "production_authority": False,
        "proof_identity": cycle.proof_identity,
        "real_capital": REAL_CAPITAL,
        "review_selection_identity": review_identity,
        "reviewed_method": cycle.reviewed_method,
        "schema_version": SHADOW_CYCLE_MANIFEST_SCHEMA_VERSION,
        "sizing_bridge_identity": cycle.sizing.bridge_identity,
        "vault_id": cycle.vault_id,
    }
    return ShadowCycleManifestRecord(
        manifest_identity=canonical_sha256(payload),
        cycle_identity=cycle.cycle_identity,
        forecast_identity=cycle.forecast_identity,
        proof_identity=cycle.proof_identity,
        capital_bridge_identity=cycle.capital.bridge_identity,
        sizing_bridge_identity=cycle.sizing.bridge_identity,
        review_selection_identity=review_identity,
        preview_identity=cycle.preview.preview_identity,
        journal_record_identity=cycle.journal_append.record.record_identity,
        vault_id=cycle.vault_id,
        reviewed_method=cycle.reviewed_method,
        event_at_ms=cycle.preview.previewed_at_ms,
        previous_manifest_identity=previous_manifest_identity,
    )


def _record_from_row(row: tuple[object, ...]) -> ShadowCycleManifestRecord:
    reviewed_method = None if row[10] is None else SizingMethod(str(row[10]))
    return ShadowCycleManifestRecord(
        manifest_identity=str(row[0]),
        cycle_identity=str(row[1]),
        forecast_identity=str(row[2]),
        proof_identity=str(row[3]),
        capital_bridge_identity=str(row[4]),
        sizing_bridge_identity=str(row[5]),
        review_selection_identity=None if row[6] is None else str(row[6]),
        preview_identity=str(row[7]),
        journal_record_identity=str(row[8]),
        vault_id=PaperVaultId(str(row[9])),
        reviewed_method=reviewed_method,
        event_at_ms=int(str(row[11])),
        previous_manifest_identity=None if row[12] is None else str(row[12]),
        schema_version=str(row[14]),
        engine_version=str(row[15]),
        canonical_epoch2_write_authority=bool(row[16]),
        production_authority=bool(row[17]),
        real_capital=int(str(row[18])),
    )


def _record_payload(record: ShadowCycleManifestRecord) -> dict[str, object]:
    return {
        "canonical_epoch2_write_authority": (
            record.canonical_epoch2_write_authority
        ),
        "capital_bridge_identity": record.capital_bridge_identity,
        "cycle_identity": record.cycle_identity,
        "engine_version": record.engine_version,
        "event_at_ms": record.event_at_ms,
        "forecast_identity": record.forecast_identity,
        "journal_record_identity": record.journal_record_identity,
        "preview_identity": record.preview_identity,
        "previous_manifest_identity": record.previous_manifest_identity,
        "production_authority": record.production_authority,
        "proof_identity": record.proof_identity,
        "real_capital": record.real_capital,
        "review_selection_identity": record.review_selection_identity,
        "reviewed_method": record.reviewed_method,
        "schema_version": record.schema_version,
        "sizing_bridge_identity": record.sizing_bridge_identity,
        "vault_id": record.vault_id,
    }


def _verify_meta(db: sqlite3.Connection) -> None:
    expected = {
        "engine_version": SHADOW_CYCLE_MANIFEST_ENGINE_VERSION,
        "real_capital": str(REAL_CAPITAL),
        "schema_version": SHADOW_CYCLE_MANIFEST_SCHEMA_VERSION,
        "semantic": "shadow_research_cycle_lineage_only",
    }
    rows = {
        str(key): str(value)
        for key, value in db.execute(
            f"SELECT key, value FROM {_META_TABLE}"
        ).fetchall()
    }
    if rows != expected:
        raise ValueError("shadow cycle manifest metadata mismatch")


def _validate_cycle(cycle: ShadowReplayCycleResult) -> None:
    if (
        cycle.canonical_epoch2_write_authority
        or cycle.production_authority
        or cycle.real_capital != REAL_CAPITAL
    ):
        raise ValueError("shadow cycle manifest rejects authority-bearing cycle")
    if cycle.preview.preview_identity != cycle.journal_append.record.preview_identity:
        raise ValueError("shadow cycle preview/journal mismatch")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
