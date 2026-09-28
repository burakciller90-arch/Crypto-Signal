from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.ledger.serialization import canonical_json, sha256_text

FROZEN_PROOF_OBJECT_SCHEMA_VERSION = "frozen-proof-object-v1/1"
FROZEN_PROOF_STORE_SCHEMA_VERSION = "frozen-proof-store-v1/1"
REAL_CAPITAL = 0


class FrozenProofConflictError(ValueError):
    """Raised when immutable frozen proof truth cannot be trusted."""


class FrozenProofWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class FrozenProofObject:
    object_identity: str
    analysis_identity: str | None
    object_kind: str
    family: str
    domains: tuple[str, ...]
    asset: str | None
    symbol: str | None
    network: str | None
    timeframe: str | None
    as_of_ms: int
    market_available_at_ms: int
    observed_at_ms: int
    source_provider: str
    source_quality: str
    freshness_state: str
    freshness_age_ms: int | None
    uncertainty_flags: tuple[str, ...]
    source_object_identities: tuple[str, ...]
    depends_on_evidence_identities: tuple[str, ...]
    payload_json: str
    visualization_json: str | None
    renderer_contract_version: str
    persisted_at_ms: int
    schema_version: str = FROZEN_PROOF_OBJECT_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.object_identity, "frozen proof object identity")
        if self.analysis_identity is not None:
            _require_sha256(
                self.analysis_identity,
                "frozen proof analysis identity",
            )
        for value, label in (
            (self.object_kind, "frozen proof object kind"),
            (self.family, "frozen proof family"),
            (self.source_provider, "frozen proof source provider"),
            (self.source_quality, "frozen proof source quality"),
            (self.freshness_state, "frozen proof freshness state"),
            (
                self.renderer_contract_version,
                "frozen proof renderer contract version",
            ),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        _require_sorted_unique_text(
            self.domains,
            "frozen proof domain",
            allow_empty=False,
        )
        for value, label in (
            (self.asset, "frozen proof asset"),
            (self.symbol, "frozen proof symbol"),
            (self.network, "frozen proof network"),
            (self.timeframe, "frozen proof timeframe"),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{label} must be non-empty when present")
        for value, label in (
            (self.as_of_ms, "frozen proof as-of"),
            (
                self.market_available_at_ms,
                "frozen proof market-available",
            ),
            (self.observed_at_ms, "frozen proof observed-at"),
            (self.persisted_at_ms, "frozen proof persisted-at"),
        ):
            _require_non_negative_int(value, label)
        if self.market_available_at_ms > self.as_of_ms:
            raise ValueError("frozen proof market availability is future evidence")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("frozen proof observation is future evidence")
        if self.persisted_at_ms < max(
            self.market_available_at_ms,
            self.observed_at_ms,
        ):
            raise ValueError(
                "frozen proof persistence predates source availability"
            )
        if self.freshness_age_ms is not None:
            _require_non_negative_int(
                self.freshness_age_ms,
                "frozen proof freshness age",
            )
        _require_sorted_unique_text(
            self.uncertainty_flags,
            "frozen proof uncertainty flag",
            allow_empty=True,
        )
        _require_sorted_unique_identities(
            self.source_object_identities,
            "frozen proof source object identity",
        )
        _require_sorted_unique_identities(
            self.depends_on_evidence_identities,
            "frozen proof dependency identity",
        )
        _require_canonical_object_json(
            self.payload_json,
            "frozen proof payload",
        )
        if self.visualization_json is not None:
            _require_canonical_object_json(
                self.visualization_json,
                "frozen proof visualization",
            )
        if self.schema_version != FROZEN_PROOF_OBJECT_SCHEMA_VERSION:
            raise ValueError("unsupported frozen proof object schema")
        if self.production_authority:
            raise ValueError("frozen proof cannot grant production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")


def frozen_proof_object_json(value: FrozenProofObject) -> str:
    return canonical_json(value)


class FrozenProofStore:
    """Append-only exact derived-proof registry.

    The store never computes historical evidence and intentionally exposes no
    "latest proof" API. Resolution requires an exact object or analysis
    identity, which keeps historical callers from substituting current truth.
    Callers must persist the exact proof before publishing READY_EXACT.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS frozen_proof_store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS frozen_proof_objects (
                    object_identity TEXT PRIMARY KEY,
                    analysis_identity TEXT,
                    object_kind TEXT NOT NULL,
                    family TEXT NOT NULL,
                    as_of_ms INTEGER NOT NULL,
                    market_available_at_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    persisted_at_ms INTEGER NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    object_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS frozen_proof_analysis_lookup
                    ON frozen_proof_objects(
                        analysis_identity,
                        as_of_ms,
                        object_identity
                    );

                CREATE INDEX IF NOT EXISTS frozen_proof_family_kind_lookup
                    ON frozen_proof_objects(
                        family,
                        object_kind,
                        as_of_ms,
                        object_identity
                    );
                """
            )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                        frozen_proof_objects_reject_{operation.lower()}
                    BEFORE {operation} ON frozen_proof_objects
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable frozen proof object'
                        );
                    END
                    """
                )
            row = connection.execute(
                """
                SELECT value
                FROM frozen_proof_store_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO frozen_proof_store_meta(key, value)
                    VALUES ('schema_version', ?)
                    """,
                    (FROZEN_PROOF_STORE_SCHEMA_VERSION,),
                )
            elif str(row["value"]) != FROZEN_PROOF_STORE_SCHEMA_VERSION:
                raise FrozenProofConflictError(
                    "unsupported frozen proof store schema"
                )

    def append(
        self,
        value: FrozenProofObject,
    ) -> FrozenProofWriteDisposition:
        self.initialize()
        object_json = frozen_proof_object_json(value)
        payload_sha256 = sha256_text(value.payload_json)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT object_json, payload_sha256
                FROM frozen_proof_objects
                WHERE object_identity=?
                """,
                (value.object_identity,),
            ).fetchone()
            if row is not None:
                if (
                    str(row["object_json"]) != object_json
                    or str(row["payload_sha256"]) != payload_sha256
                ):
                    raise FrozenProofConflictError(
                        "frozen proof identity rebound to different content"
                    )
                return FrozenProofWriteDisposition.UNCHANGED
            connection.execute(
                """
                INSERT INTO frozen_proof_objects (
                    object_identity,
                    analysis_identity,
                    object_kind,
                    family,
                    as_of_ms,
                    market_available_at_ms,
                    observed_at_ms,
                    persisted_at_ms,
                    payload_sha256,
                    object_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    value.object_identity,
                    value.analysis_identity,
                    value.object_kind,
                    value.family,
                    value.as_of_ms,
                    value.market_available_at_ms,
                    value.observed_at_ms,
                    value.persisted_at_ms,
                    payload_sha256,
                    object_json,
                ),
            )
        return FrozenProofWriteDisposition.INSERTED

    def read_exact(
        self,
        object_identity: str,
    ) -> FrozenProofObject | None:
        _require_sha256(object_identity, "frozen proof object identity")
        if not self.path.is_file():
            return None
        try:
            with self._connect_ro() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM frozen_proof_objects
                    WHERE object_identity=?
                    """,
                    (object_identity,),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise FrozenProofConflictError(str(exc)) from exc
        if row is None:
            return None
        return _proof_from_row(row)

    def read_by_analysis_identity(
        self,
        analysis_identity: str,
        *,
        as_of_ms: int,
    ) -> FrozenProofObject | None:
        _require_sha256(
            analysis_identity,
            "frozen proof analysis identity",
        )
        _require_non_negative_int(as_of_ms, "frozen proof read as-of")
        if not self.path.is_file():
            return None
        try:
            with self._connect_ro() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM frozen_proof_objects
                    WHERE analysis_identity=?
                      AND as_of_ms <= ?
                    ORDER BY as_of_ms DESC, object_identity
                    LIMIT 2
                    """,
                    (analysis_identity, as_of_ms),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise FrozenProofConflictError(str(exc)) from exc
        if not rows:
            return None
        if len(rows) > 1 and int(rows[0]["as_of_ms"]) == int(rows[1]["as_of_ms"]):
            raise FrozenProofConflictError(
                "analysis identity maps to ambiguous frozen proof objects"
            )
        return _proof_from_row(rows[0])

    def count(self) -> int:
        if not self.path.is_file():
            return 0
        try:
            with self._connect_ro() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM frozen_proof_objects"
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise FrozenProofConflictError(str(exc)) from exc
        if row is None:
            raise FrozenProofConflictError("frozen proof count disappeared")
        return int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _connect_ro(self) -> sqlite3.Connection:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection


def _proof_from_row(row: sqlite3.Row) -> FrozenProofObject:
    object_json = str(row["object_json"])
    try:
        raw = json.loads(object_json)
    except json.JSONDecodeError as exc:
        raise FrozenProofConflictError(
            "frozen proof object JSON is invalid"
        ) from exc
    if not isinstance(raw, dict):
        raise FrozenProofConflictError(
            "frozen proof object JSON must decode to object"
        )
    if canonical_json(raw) != object_json:
        raise FrozenProofConflictError(
            "frozen proof object JSON is not canonical"
        )
    try:
        value = FrozenProofObject(
            object_identity=str(raw["object_identity"]),
            analysis_identity=(
                None
                if raw.get("analysis_identity") is None
                else str(raw["analysis_identity"])
            ),
            object_kind=str(raw["object_kind"]),
            family=str(raw["family"]),
            domains=_raw_text_tuple(raw.get("domains"), "domains"),
            asset=_raw_optional_text(raw.get("asset"), "asset"),
            symbol=_raw_optional_text(raw.get("symbol"), "symbol"),
            network=_raw_optional_text(raw.get("network"), "network"),
            timeframe=_raw_optional_text(raw.get("timeframe"), "timeframe"),
            as_of_ms=_raw_int(raw.get("as_of_ms"), "as_of_ms"),
            market_available_at_ms=_raw_int(
                raw.get("market_available_at_ms"),
                "market_available_at_ms",
            ),
            observed_at_ms=_raw_int(
                raw.get("observed_at_ms"),
                "observed_at_ms",
            ),
            source_provider=str(raw["source_provider"]),
            source_quality=str(raw["source_quality"]),
            freshness_state=str(raw["freshness_state"]),
            freshness_age_ms=_raw_optional_int(
                raw.get("freshness_age_ms"),
                "freshness_age_ms",
            ),
            uncertainty_flags=_raw_text_tuple(
                raw.get("uncertainty_flags"),
                "uncertainty_flags",
            ),
            source_object_identities=_raw_text_tuple(
                raw.get("source_object_identities"),
                "source_object_identities",
            ),
            depends_on_evidence_identities=_raw_text_tuple(
                raw.get("depends_on_evidence_identities"),
                "depends_on_evidence_identities",
            ),
            payload_json=str(raw["payload_json"]),
            visualization_json=(
                None
                if raw.get("visualization_json") is None
                else str(raw["visualization_json"])
            ),
            renderer_contract_version=str(
                raw["renderer_contract_version"]
            ),
            persisted_at_ms=_raw_int(
                raw.get("persisted_at_ms"),
                "persisted_at_ms",
            ),
            schema_version=str(raw["schema_version"]),
            production_authority=_raw_bool(
                raw.get("production_authority"),
                "production_authority",
            ),
            real_capital=_raw_int(raw.get("real_capital"), "real_capital"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FrozenProofConflictError(
            "frozen proof object payload is invalid"
        ) from exc

    row_metadata = (
        str(row["object_identity"]),
        (
            None
            if row["analysis_identity"] is None
            else str(row["analysis_identity"])
        ),
        str(row["object_kind"]),
        str(row["family"]),
        int(row["as_of_ms"]),
        int(row["market_available_at_ms"]),
        int(row["observed_at_ms"]),
        int(row["persisted_at_ms"]),
    )
    object_metadata = (
        value.object_identity,
        value.analysis_identity,
        value.object_kind,
        value.family,
        value.as_of_ms,
        value.market_available_at_ms,
        value.observed_at_ms,
        value.persisted_at_ms,
    )
    if row_metadata != object_metadata:
        raise FrozenProofConflictError(
            "frozen proof row/object metadata mismatch"
        )
    if str(row["payload_sha256"]) != sha256_text(value.payload_json):
        raise FrozenProofConflictError("frozen proof payload digest mismatch")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be lowercase SHA256")


def _require_non_negative_int(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _require_sorted_unique_text(
    values: tuple[str, ...],
    label: str,
    *,
    allow_empty: bool,
) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{label} must not be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} must be sorted and unique")


def _require_sorted_unique_identities(
    values: tuple[str, ...],
    label: str,
) -> None:
    _require_sorted_unique_text(values, label, allow_empty=True)
    for value in values:
        _require_sha256(value, label)


def _require_canonical_object_json(value: str, label: str) -> None:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must decode to object")
    if canonical_json(raw) != value:
        raise ValueError(f"{label} must be canonical JSON")


def _raw_text_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise TypeError(f"{label} must be a JSON string array")
    return tuple(value)


def _raw_optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text or null")
    return value


def _raw_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be integer")
    return value


def _raw_optional_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _raw_int(value, label)


def _raw_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be boolean")
    return value
