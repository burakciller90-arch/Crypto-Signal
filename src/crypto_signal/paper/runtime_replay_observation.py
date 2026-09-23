"""R25 Slice 14: immutable runtime restart/replay observations.

A VERIFIED observation can exist only when one complete persisted shadow cycle
is followed by an exact replay of the same immutable inputs on the same explicit
runtime-instance identity:

first run: journal INSERTED + manifest INSERTED
replay:    journal IDEMPOTENT + manifest IDEMPOTENT

CI acceptance never creates this artefact by itself. REAL_CAPITAL=0.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.shadow_cycle_manifest import (
    ShadowCycleManifestDisposition,
)
from crypto_signal.paper.shadow_cycle_runtime import PersistedShadowCycleResult
from crypto_signal.paper.shadow_intent_journal import (
    ShadowIntentAppendDisposition,
)

RUNTIME_REPLAY_OBSERVATION_SCHEMA_VERSION = "r25-runtime-replay-observation-v1/1"
RUNTIME_REPLAY_OBSERVATION_ENGINE_VERSION = "r25-runtime-replay-observation-v1/1"
RUNTIME_REPLAY_OBSERVATION_SUFFIX = ".shadow-replay.sqlite3"
REAL_CAPITAL = 0

_RECORD_TABLE = "r25_runtime_replay_observations"
_META_TABLE = "r25_runtime_replay_meta"
_ALLOWED_TABLES = {_RECORD_TABLE, _META_TABLE}


@dataclass(frozen=True, slots=True)
class RuntimeReplayObservation:
    observation_identity: str
    runtime_instance_identity: str
    persisted_cycle_identity: str
    cycle_identity: str
    forecast_identity: str
    proof_identity: str
    capital_bridge_identity: str
    sizing_bridge_identity: str
    review_selection_identity: str | None
    preview_identity: str
    journal_record_identity: str
    manifest_identity: str
    first_observed_at_ms: int
    replay_observed_at_ms: int
    restart_replay_verified: bool = True
    schema_version: str = RUNTIME_REPLAY_OBSERVATION_SCHEMA_VERSION
    engine_version: str = RUNTIME_REPLAY_OBSERVATION_ENGINE_VERSION
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.observation_identity, "replay observation"),
            (self.runtime_instance_identity, "runtime instance"),
            (self.persisted_cycle_identity, "persisted cycle"),
            (self.cycle_identity, "cycle"),
            (self.forecast_identity, "forecast"),
            (self.proof_identity, "proof"),
            (self.capital_bridge_identity, "capital bridge"),
            (self.sizing_bridge_identity, "sizing bridge"),
            (self.preview_identity, "preview"),
            (self.journal_record_identity, "journal record"),
            (self.manifest_identity, "manifest"),
        ):
            _require_sha256(value, label)
        if self.review_selection_identity is not None:
            _require_sha256(
                self.review_selection_identity,
                "review selection",
            )
        if self.first_observed_at_ms < 0 or self.replay_observed_at_ms < 0:
            raise ValueError("replay observation times must be non-negative")
        if self.replay_observed_at_ms <= self.first_observed_at_ms:
            raise ValueError("replay observation must occur after first observation")
        if not self.restart_replay_verified:
            raise ValueError("persisted replay observation must be verified")
        if self.schema_version != RUNTIME_REPLAY_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("unsupported replay observation schema")
        if self.engine_version != RUNTIME_REPLAY_OBSERVATION_ENGINE_VERSION:
            raise ValueError("unsupported replay observation engine")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("replay observation cannot grant authority")
        if self.observation_identity != canonical_sha256(_observation_payload(self)):
            raise ValueError("replay observation identity mismatch")


@dataclass(frozen=True, slots=True)
class RuntimeReplayObservationStatus:
    record_count: int
    latest_observation_identity: str | None
    quick_check_ok: bool
    read_only_verified: bool
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.record_count < 0:
            raise ValueError("replay observation count cannot be negative")
        if self.latest_observation_identity is not None:
            _require_sha256(
                self.latest_observation_identity,
                "latest replay observation",
            )
        if not self.quick_check_ok or not self.read_only_verified:
            raise ValueError("replay observation status must be verified")
        if (
            self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("replay observation status cannot grant authority")


def build_runtime_replay_observation(
    first: PersistedShadowCycleResult,
    replay: PersistedShadowCycleResult,
    *,
    runtime_instance_identity: str,
    first_observed_at_ms: int,
    replay_observed_at_ms: int,
) -> RuntimeReplayObservation:
    """Prove one exact persisted cycle survived restart/replay unchanged."""
    _require_sha256(runtime_instance_identity, "runtime instance")
    if first_observed_at_ms < first.cycle.preview.previewed_at_ms:
        raise ValueError("first replay observation predates first cycle")
    if replay_observed_at_ms < replay.cycle.preview.previewed_at_ms:
        raise ValueError("replay observation predates replay cycle")
    if replay_observed_at_ms <= first_observed_at_ms:
        raise ValueError("replay observation must occur after first observation")

    if (
        first.cycle.journal_append.disposition
        is not ShadowIntentAppendDisposition.INSERTED
        or first.manifest_append.disposition
        is not ShadowCycleManifestDisposition.INSERTED
    ):
        raise ValueError(
            "first persisted cycle must be journal INSERTED + manifest INSERTED"
        )
    if (
        replay.cycle.journal_append.disposition
        is not ShadowIntentAppendDisposition.IDEMPOTENT
        or replay.manifest_append.disposition
        is not ShadowCycleManifestDisposition.IDEMPOTENT
    ):
        raise ValueError(
            "replay persisted cycle must be journal IDEMPOTENT + manifest IDEMPOTENT"
        )

    first_ids = _lineage_tuple(first)
    replay_ids = _lineage_tuple(replay)
    if first_ids != replay_ids:
        raise ValueError("restart replay immutable lineage mismatch")

    review_identity = (
        None
        if first.cycle.reviewed_selection is None
        else first.cycle.reviewed_selection.selection_identity
    )
    payload = {
        "canonical_epoch2_write_authority": False,
        "capital_bridge_identity": first.cycle.capital.bridge_identity,
        "cycle_identity": first.cycle.cycle_identity,
        "engine_version": RUNTIME_REPLAY_OBSERVATION_ENGINE_VERSION,
        "first_observed_at_ms": first_observed_at_ms,
        "forecast_identity": first.cycle.forecast_identity,
        "journal_record_identity": (
            first.cycle.journal_append.record.record_identity
        ),
        "manifest_identity": first.manifest_append.record.manifest_identity,
        "persisted_cycle_identity": first.persisted_cycle_identity,
        "preview_identity": first.cycle.preview.preview_identity,
        "production_authority": False,
        "proof_identity": first.cycle.proof_identity,
        "real_capital": REAL_CAPITAL,
        "replay_observed_at_ms": replay_observed_at_ms,
        "restart_replay_verified": True,
        "review_selection_identity": review_identity,
        "runtime_instance_identity": runtime_instance_identity,
        "schema_version": RUNTIME_REPLAY_OBSERVATION_SCHEMA_VERSION,
        "sizing_bridge_identity": first.cycle.sizing.bridge_identity,
    }
    return RuntimeReplayObservation(
        observation_identity=canonical_sha256(payload),
        runtime_instance_identity=runtime_instance_identity,
        persisted_cycle_identity=first.persisted_cycle_identity,
        cycle_identity=first.cycle.cycle_identity,
        forecast_identity=first.cycle.forecast_identity,
        proof_identity=first.cycle.proof_identity,
        capital_bridge_identity=first.cycle.capital.bridge_identity,
        sizing_bridge_identity=first.cycle.sizing.bridge_identity,
        review_selection_identity=review_identity,
        preview_identity=first.cycle.preview.preview_identity,
        journal_record_identity=(
            first.cycle.journal_append.record.record_identity
        ),
        manifest_identity=first.manifest_append.record.manifest_identity,
        first_observed_at_ms=first_observed_at_ms,
        replay_observed_at_ms=replay_observed_at_ms,
    )


class R25RuntimeReplayObservationLedger:
    """Append-only replay proof isolated from canonical and shadow-cycle stores."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(RUNTIME_REPLAY_OBSERVATION_SUFFIX):
            raise ValueError(
                "runtime replay observation path must end with "
                f"{RUNTIME_REPLAY_OBSERVATION_SUFFIX}"
            )

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
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
                    "runtime replay observation refuses non-replay database"
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
                    observation_identity TEXT PRIMARY KEY,
                    runtime_instance_identity TEXT NOT NULL,
                    cycle_identity TEXT NOT NULL,
                    forecast_identity TEXT NOT NULL,
                    replay_observed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(runtime_instance_identity, cycle_identity)
                )"""
            )
            for action in ("UPDATE", "DELETE"):
                db.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS
                    {_RECORD_TABLE}_immutable_{action.lower()}
                    BEFORE {action} ON {_RECORD_TABLE}
                    BEGIN
                        SELECT RAISE(ABORT, 'immutable R25 runtime replay observation');
                    END"""
                )
            expected = {
                "engine_version": RUNTIME_REPLAY_OBSERVATION_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": RUNTIME_REPLAY_OBSERVATION_SCHEMA_VERSION,
                "semantic": "runtime_restart_replay_observation_only",
            }
            for key, value in expected.items():
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
                    raise ValueError("runtime replay observation metadata mismatch")

    def append(self, observation: RuntimeReplayObservation) -> bool:
        self.initialize()
        payload_json = canonical_json(_observation_payload(observation))
        if sha256_text(payload_json) != observation.observation_identity:
            raise ValueError("runtime replay observation payload mismatch")
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                f"""SELECT observation_identity, payload_json
                FROM {_RECORD_TABLE}
                WHERE runtime_instance_identity = ? AND cycle_identity = ?""",
                (
                    observation.runtime_instance_identity,
                    observation.cycle_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) != observation.observation_identity
                    or str(existing[1]) != payload_json
                ):
                    raise ValueError("runtime replay observation identity conflict")
                db.commit()
                return False
            db.execute(
                f"""INSERT INTO {_RECORD_TABLE} (
                    observation_identity, runtime_instance_identity,
                    cycle_identity, forecast_identity,
                    replay_observed_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    observation.observation_identity,
                    observation.runtime_instance_identity,
                    observation.cycle_identity,
                    observation.forecast_identity,
                    observation.replay_observed_at_ms,
                    payload_json,
                ),
            )
            db.commit()
        return True

    def read_latest_for_forecast(
        self,
        forecast_identity: str,
    ) -> RuntimeReplayObservation | None:
        _require_sha256(forecast_identity, "replay forecast lookup")
        self.verify_read_only()
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            row = db.execute(
                f"""SELECT payload_json
                FROM {_RECORD_TABLE}
                WHERE forecast_identity = ?
                ORDER BY replay_observed_at_ms DESC, observation_identity DESC
                LIMIT 1""",
                (forecast_identity,),
            ).fetchone()
        return None if row is None else _observation_from_json(str(row[0]))

    def verify_read_only(self) -> RuntimeReplayObservationStatus:
        if not self.path.is_file():
            raise ValueError("runtime replay observation ledger missing")
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            unexpected = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            } - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "runtime replay observation contains non-replay tables"
                )
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("runtime replay observation quick_check failed")
            _verify_meta(db)
            rows = db.execute(
                f"""SELECT observation_identity, runtime_instance_identity,
                cycle_identity, forecast_identity, replay_observed_at_ms,
                payload_json
                FROM {_RECORD_TABLE}
                ORDER BY replay_observed_at_ms, observation_identity"""
            ).fetchall()
            latest: str | None = None
            for row in rows:
                observation = _observation_from_json(str(row[5]))
                if observation.observation_identity != str(row[0]):
                    raise ValueError("runtime replay row identity mismatch")
                if observation.runtime_instance_identity != str(row[1]):
                    raise ValueError("runtime replay runtime identity mismatch")
                if observation.cycle_identity != str(row[2]):
                    raise ValueError("runtime replay cycle identity mismatch")
                if observation.forecast_identity != str(row[3]):
                    raise ValueError("runtime replay forecast identity mismatch")
                if observation.replay_observed_at_ms != int(str(row[4])):
                    raise ValueError("runtime replay timestamp mismatch")
                latest = observation.observation_identity

        return RuntimeReplayObservationStatus(
            record_count=len(rows),
            latest_observation_identity=latest,
            quick_check_ok=True,
            read_only_verified=True,
        )


def _lineage_tuple(result: PersistedShadowCycleResult) -> tuple[object, ...]:
    review_identity = (
        None
        if result.cycle.reviewed_selection is None
        else result.cycle.reviewed_selection.selection_identity
    )
    return (
        result.persisted_cycle_identity,
        result.cycle.cycle_identity,
        result.cycle.forecast_identity,
        result.cycle.proof_identity,
        result.cycle.capital.bridge_identity,
        result.cycle.sizing.bridge_identity,
        review_identity,
        result.cycle.preview.preview_identity,
        result.cycle.journal_append.record.record_identity,
        result.manifest_append.record.manifest_identity,
        result.cycle.vault_id.value,
        (
            None
            if result.cycle.reviewed_method is None
            else result.cycle.reviewed_method.value
        ),
    )


def _observation_payload(
    observation: RuntimeReplayObservation,
) -> dict[str, object]:
    return {
        "canonical_epoch2_write_authority": (
            observation.canonical_epoch2_write_authority
        ),
        "capital_bridge_identity": observation.capital_bridge_identity,
        "cycle_identity": observation.cycle_identity,
        "engine_version": observation.engine_version,
        "first_observed_at_ms": observation.first_observed_at_ms,
        "forecast_identity": observation.forecast_identity,
        "journal_record_identity": observation.journal_record_identity,
        "manifest_identity": observation.manifest_identity,
        "persisted_cycle_identity": observation.persisted_cycle_identity,
        "preview_identity": observation.preview_identity,
        "production_authority": observation.production_authority,
        "proof_identity": observation.proof_identity,
        "real_capital": observation.real_capital,
        "replay_observed_at_ms": observation.replay_observed_at_ms,
        "restart_replay_verified": observation.restart_replay_verified,
        "review_selection_identity": observation.review_selection_identity,
        "runtime_instance_identity": observation.runtime_instance_identity,
        "schema_version": observation.schema_version,
        "sizing_bridge_identity": observation.sizing_bridge_identity,
    }


def _observation_from_json(payload_json: str) -> RuntimeReplayObservation:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("runtime replay observation payload must be object")
    if sha256_text(payload_json) != raw.get("observation_identity", ""):
        # observation_identity is intentionally not inside canonical payload.
        # Validate through reconstruction below instead.
        pass
    return RuntimeReplayObservation(
        observation_identity=canonical_sha256(raw),
        runtime_instance_identity=_raw_sha(raw, "runtime_instance_identity"),
        persisted_cycle_identity=_raw_sha(raw, "persisted_cycle_identity"),
        cycle_identity=_raw_sha(raw, "cycle_identity"),
        forecast_identity=_raw_sha(raw, "forecast_identity"),
        proof_identity=_raw_sha(raw, "proof_identity"),
        capital_bridge_identity=_raw_sha(raw, "capital_bridge_identity"),
        sizing_bridge_identity=_raw_sha(raw, "sizing_bridge_identity"),
        review_selection_identity=_raw_optional_sha(
            raw,
            "review_selection_identity",
        ),
        preview_identity=_raw_sha(raw, "preview_identity"),
        journal_record_identity=_raw_sha(raw, "journal_record_identity"),
        manifest_identity=_raw_sha(raw, "manifest_identity"),
        first_observed_at_ms=_raw_int(raw, "first_observed_at_ms"),
        replay_observed_at_ms=_raw_int(raw, "replay_observed_at_ms"),
        restart_replay_verified=raw.get("restart_replay_verified") is True,
        schema_version=str(raw.get("schema_version", "")),
        engine_version=str(raw.get("engine_version", "")),
        canonical_epoch2_write_authority=(
            raw.get("canonical_epoch2_write_authority") is True
        ),
        production_authority=raw.get("production_authority") is True,
        real_capital=_raw_int(raw, "real_capital"),
    )


def _verify_meta(db: sqlite3.Connection) -> None:
    expected = {
        "engine_version": RUNTIME_REPLAY_OBSERVATION_ENGINE_VERSION,
        "real_capital": str(REAL_CAPITAL),
        "schema_version": RUNTIME_REPLAY_OBSERVATION_SCHEMA_VERSION,
        "semantic": "runtime_restart_replay_observation_only",
    }
    rows = {
        str(key): str(value)
        for key, value in db.execute(
            f"SELECT key, value FROM {_META_TABLE}"
        ).fetchall()
    }
    if rows != expected:
        raise ValueError("runtime replay observation metadata mismatch")


def _raw_sha(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be SHA256 string")
    _require_sha256(value, key)
    return value


def _raw_optional_sha(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be SHA256 string or null")
    _require_sha256(value, key)
    return value


def _raw_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be integer")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
