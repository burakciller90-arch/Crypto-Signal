"""R25 Slice 9: isolated append-only shadow journal for reviewed R22 previews.

This journal persists only R22IntentPreview evidence. It is deliberately isolated
from canonical R21/R22 accounting databases, grants no execution authority and
cannot mutate Epoch 2. REAL_CAPITAL=0.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.r22_intent_preview import (
    R22IntentPreview,
    r22_intent_preview_payload,
)

SHADOW_INTENT_JOURNAL_SCHEMA_VERSION = "r25-shadow-intent-journal-v1/1"
SHADOW_INTENT_JOURNAL_ENGINE_VERSION = "r25-shadow-intent-journal-v1/1"
SHADOW_INTENT_JOURNAL_SUFFIX = ".shadow-intent.sqlite3"
REAL_CAPITAL = 0

_RECORD_TABLE = "r25_shadow_intent_records"
_META_TABLE = "r25_shadow_intent_meta"
_ALLOWED_TABLES = {_RECORD_TABLE, _META_TABLE}


class ShadowIntentAppendDisposition(StrEnum):
    INSERTED = "INSERTED"
    IDEMPOTENT = "IDEMPOTENT"


@dataclass(frozen=True, slots=True)
class ShadowIntentJournalRecord:
    record_identity: str
    preview_identity: str
    vault_id: PaperVaultId
    event_at_ms: int
    previous_record_identity: str | None
    schema_version: str = SHADOW_INTENT_JOURNAL_SCHEMA_VERSION
    engine_version: str = SHADOW_INTENT_JOURNAL_ENGINE_VERSION
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "shadow journal record")
        _require_sha256(self.preview_identity, "shadow journal preview")
        if self.previous_record_identity is not None:
            _require_sha256(
                self.previous_record_identity,
                "shadow journal previous record",
            )
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("shadow journal requires canonical vault id")
        if self.event_at_ms < 0:
            raise ValueError("shadow journal event time must be non-negative")
        if self.schema_version != SHADOW_INTENT_JOURNAL_SCHEMA_VERSION:
            raise ValueError("unsupported shadow intent journal schema")
        if self.engine_version != SHADOW_INTENT_JOURNAL_ENGINE_VERSION:
            raise ValueError("unsupported shadow intent journal engine")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("shadow intent journal cannot grant authority")
        if self.record_identity != canonical_sha256(_record_payload(self)):
            raise ValueError("shadow journal record identity mismatch")


@dataclass(frozen=True, slots=True)
class ShadowIntentAppendResult:
    disposition: ShadowIntentAppendDisposition
    record: ShadowIntentJournalRecord

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ShadowIntentAppendDisposition):
            raise TypeError("invalid shadow intent append disposition")


@dataclass(frozen=True, slots=True)
class ShadowIntentJournalStatus:
    record_count: int
    last_record_identities: tuple[tuple[PaperVaultId, str], ...]
    quick_check_ok: bool
    read_only_verified: bool
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.record_count < 0:
            raise ValueError("shadow journal record count cannot be negative")
        expected = tuple(
            sorted(self.last_record_identities, key=lambda item: item[0].value)
        )
        if self.last_record_identities != expected:
            raise ValueError("shadow journal last identities must be canonical")
        for vault_id, identity in self.last_record_identities:
            if not isinstance(vault_id, PaperVaultId):
                raise TypeError("shadow journal status vault id invalid")
            _require_sha256(identity, "shadow journal status record")
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("shadow journal status requires verified read-only state")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("shadow journal status cannot grant authority")


class R25ShadowIntentJournal:
    """Append-only SQLite journal isolated from canonical Epoch 2 databases."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(SHADOW_INTENT_JOURNAL_SUFFIX):
            raise ValueError(
                f"shadow intent journal path must end with {SHADOW_INTENT_JOURNAL_SUFFIX}"
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
                    "shadow intent journal refuses database with non-shadow tables"
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
                    record_identity TEXT PRIMARY KEY,
                    preview_identity TEXT NOT NULL UNIQUE,
                    vault_id TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    previous_record_identity TEXT,
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
                        SELECT RAISE(ABORT, 'immutable R25 shadow intent journal');
                    END"""
                )
                db.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS
                    {_META_TABLE}_immutable_{action.lower()}
                    BEFORE {action} ON {_META_TABLE}
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable R25 shadow intent metadata');
                    END"""
                )
            meta = {
                "engine_version": SHADOW_INTENT_JOURNAL_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": SHADOW_INTENT_JOURNAL_SCHEMA_VERSION,
                "semantic": "isolated_reviewed_r22_preview_evidence_only",
            }
            for key, value in meta.items():
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
                    raise ValueError("shadow intent journal metadata mismatch")

    def append(self, preview: R22IntentPreview) -> ShadowIntentAppendResult:
        self.initialize()
        _validate_preview_authority(preview)
        payload_json = canonical_json(r22_intent_preview_payload(preview))
        if sha256_text(payload_json) != preview.preview_identity:
            raise ValueError("shadow journal preview payload identity mismatch")

        vault_id = preview.intent.vault_id
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                f"""SELECT record_identity, vault_id, event_at_ms,
                previous_record_identity, payload_json, schema_version,
                engine_version, canonical_epoch2_write_authority,
                production_authority, real_capital
                FROM {_RECORD_TABLE}
                WHERE preview_identity = ?""",
                (preview.preview_identity,),
            ).fetchone()
            if existing is not None:
                record = _record_from_row(preview.preview_identity, existing)
                if (
                    record.vault_id is not vault_id
                    or record.event_at_ms != preview.previewed_at_ms
                    or str(existing[4]) != payload_json
                ):
                    raise ValueError("shadow journal preview identity conflict")
                return ShadowIntentAppendResult(
                    disposition=ShadowIntentAppendDisposition.IDEMPOTENT,
                    record=record,
                )

            last = db.execute(
                f"""SELECT record_identity, event_at_ms
                FROM {_RECORD_TABLE}
                WHERE vault_id = ?
                ORDER BY event_at_ms DESC, record_identity DESC
                LIMIT 1""",
                (vault_id.value,),
            ).fetchone()
            previous = None if last is None else str(last[0])
            if last is not None and preview.previewed_at_ms <= int(last[1]):
                raise ValueError(
                    "shadow journal cannot backfill or fork vault event time"
                )

            record = _build_record(
                preview_identity=preview.preview_identity,
                vault_id=vault_id,
                event_at_ms=preview.previewed_at_ms,
                previous_record_identity=previous,
            )
            db.execute(
                f"""INSERT INTO {_RECORD_TABLE} (
                    record_identity, preview_identity, vault_id, event_at_ms,
                    previous_record_identity, payload_json, schema_version,
                    engine_version, canonical_epoch2_write_authority,
                    production_authority, real_capital
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_identity,
                    record.preview_identity,
                    record.vault_id.value,
                    record.event_at_ms,
                    record.previous_record_identity,
                    payload_json,
                    record.schema_version,
                    record.engine_version,
                    int(record.canonical_epoch2_write_authority),
                    int(record.production_authority),
                    record.real_capital,
                ),
            )
        return ShadowIntentAppendResult(
            disposition=ShadowIntentAppendDisposition.INSERTED,
            record=record,
        )

    def verify_read_only(self) -> ShadowIntentJournalStatus:
        if not self.path.is_file():
            raise ValueError("shadow intent journal missing")
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
                    "shadow intent journal contains non-shadow tables"
                )
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("shadow intent journal quick_check failed")
            _verify_meta(db)

            rows = db.execute(
                f"""SELECT record_identity, preview_identity, vault_id,
                event_at_ms, previous_record_identity, payload_json,
                schema_version, engine_version,
                canonical_epoch2_write_authority,
                production_authority, real_capital
                FROM {_RECORD_TABLE}
                ORDER BY vault_id, event_at_ms, record_identity"""
            ).fetchall()

            last_by_vault: dict[PaperVaultId, tuple[str, int]] = {}
            for row in rows:
                record_identity = str(row[0])
                preview_identity = str(row[1])
                vault_id = PaperVaultId(str(row[2]))
                event_at_ms = int(row[3])
                previous = None if row[4] is None else str(row[4])
                payload_json = str(row[5])
                record = ShadowIntentJournalRecord(
                    record_identity=record_identity,
                    preview_identity=preview_identity,
                    vault_id=vault_id,
                    event_at_ms=event_at_ms,
                    previous_record_identity=previous,
                    schema_version=str(row[6]),
                    engine_version=str(row[7]),
                    canonical_epoch2_write_authority=bool(row[8]),
                    production_authority=bool(row[9]),
                    real_capital=int(row[10]),
                )
                if sha256_text(payload_json) != preview_identity:
                    raise ValueError("shadow journal persisted preview digest mismatch")
                raw = json.loads(payload_json)
                if (
                    raw.get("real_capital") != REAL_CAPITAL
                    or raw.get("production_authority") is not False
                    or raw.get("canonical_epoch2_write_authority") is not False
                    or raw.get("tape_write_authority") is not False
                ):
                    raise ValueError("shadow journal persisted authority boundary mismatch")

                prior = last_by_vault.get(vault_id)
                expected_previous = None if prior is None else prior[0]
                if record.previous_record_identity != expected_previous:
                    raise ValueError("shadow journal predecessor chain mismatch")
                if prior is not None and record.event_at_ms <= prior[1]:
                    raise ValueError("shadow journal event time is not monotonic")
                last_by_vault[vault_id] = (
                    record.record_identity,
                    record.event_at_ms,
                )

        last = tuple(
            sorted(
                (
                    (vault_id, record_and_time[0])
                    for vault_id, record_and_time in last_by_vault.items()
                ),
                key=lambda item: item[0].value,
            )
        )
        return ShadowIntentJournalStatus(
            record_count=len(rows),
            last_record_identities=last,
            quick_check_ok=True,
            read_only_verified=True,
        )


def _build_record(
    *,
    preview_identity: str,
    vault_id: PaperVaultId,
    event_at_ms: int,
    previous_record_identity: str | None,
) -> ShadowIntentJournalRecord:
    payload = {
        "canonical_epoch2_write_authority": False,
        "engine_version": SHADOW_INTENT_JOURNAL_ENGINE_VERSION,
        "event_at_ms": event_at_ms,
        "previous_record_identity": previous_record_identity,
        "preview_identity": preview_identity,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": SHADOW_INTENT_JOURNAL_SCHEMA_VERSION,
        "vault_id": vault_id,
    }
    return ShadowIntentJournalRecord(
        record_identity=canonical_sha256(payload),
        preview_identity=preview_identity,
        vault_id=vault_id,
        event_at_ms=event_at_ms,
        previous_record_identity=previous_record_identity,
    )


def _record_from_row(
    preview_identity: str,
    row: tuple[object, ...],
) -> ShadowIntentJournalRecord:
    return ShadowIntentJournalRecord(
        record_identity=str(row[0]),
        preview_identity=preview_identity,
        vault_id=PaperVaultId(str(row[1])),
        event_at_ms=int(row[2]),
        previous_record_identity=None if row[3] is None else str(row[3]),
        schema_version=str(row[5]),
        engine_version=str(row[6]),
        canonical_epoch2_write_authority=bool(row[7]),
        production_authority=bool(row[8]),
        real_capital=int(row[9]),
    )


def _record_payload(record: ShadowIntentJournalRecord) -> dict[str, object]:
    return {
        "canonical_epoch2_write_authority": (
            record.canonical_epoch2_write_authority
        ),
        "engine_version": record.engine_version,
        "event_at_ms": record.event_at_ms,
        "previous_record_identity": record.previous_record_identity,
        "preview_identity": record.preview_identity,
        "production_authority": record.production_authority,
        "real_capital": record.real_capital,
        "schema_version": record.schema_version,
        "vault_id": record.vault_id,
    }


def _verify_meta(db: sqlite3.Connection) -> None:
    expected = {
        "engine_version": SHADOW_INTENT_JOURNAL_ENGINE_VERSION,
        "real_capital": str(REAL_CAPITAL),
        "schema_version": SHADOW_INTENT_JOURNAL_SCHEMA_VERSION,
        "semantic": "isolated_reviewed_r22_preview_evidence_only",
    }
    rows = {
        str(key): str(value)
        for key, value in db.execute(
            f"SELECT key, value FROM {_META_TABLE}"
        ).fetchall()
    }
    if rows != expected:
        raise ValueError("shadow intent journal metadata mismatch")


def _validate_preview_authority(preview: R22IntentPreview) -> None:
    if (
        preview.tape_write_authority
        or preview.canonical_epoch2_write_authority
        or preview.production_authority
        or preview.real_capital != REAL_CAPITAL
    ):
        raise ValueError("shadow journal rejects authority-bearing preview")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
