from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2UntouchedForwardPolicy,
)
from crypto_signal.ledger.coverage import LiveCoveragePlan
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord

WC2_COLLECTION_PROTOCOL_SCHEMA_VERSION = "wc2-collection-protocol-v1/1"
WC2_COLLECTION_PROTOCOL_ENGINE_VERSION = "wc2-collection-protocol-v1/1"
WC2_COLLECTION_PROTOCOL_SUFFIX = ".wc2-collection-protocol.sqlite3"

WC2_COLLECTION_MAXIMUM_ISSUANCE_DELAY_MS = 120_000
WC2_COLLECTION_HORIZON_BARS_BY_TIMEFRAME = (
    ("15m", 4),
    ("1h", 4),
    ("4h", 4),
)
WC2_COLLECTION_PAPER_ACTION_MODE = "hold_cash_no_reviewed_sizing"
WC2_COLLECTION_PROBABILITY_MODE = "not_calibrated_unless_exact_r19"
REAL_CAPITAL = 0

_RECORD_TABLE = "wc2_collection_protocols"
_META_TABLE = "wc2_collection_protocol_meta"
_ALLOWED_TABLES = {_RECORD_TABLE, _META_TABLE}


def current_wc2_collection_context_identities() -> tuple[
    tuple[str, str, str, str], ...
]:
    plan = LiveCoveragePlan.current_pilot()
    return tuple(sorted(context.identity for context in plan.enabled_contexts))


@dataclass(frozen=True, slots=True)
class WC2CollectionProtocol:
    protocol_identity: str
    review_policy_identity: str
    epoch2_activation_identity: str
    preregistered_at_ms: int
    collection_start_ms: int
    review_policy_collection_start_ms: int
    epoch2_activated_at_ms: int
    coverage_plan_version: str
    coverage_context_identities: tuple[tuple[str, str, str, str], ...]
    maximum_issuance_delay_ms: int
    horizon_bars_by_timeframe: tuple[tuple[str, int], ...]
    paper_action_mode: str
    probability_mode: str
    historical_backfill_authority: bool = False
    automatic_promotion: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = WC2_COLLECTION_PROTOCOL_SCHEMA_VERSION
    engine_version: str = WC2_COLLECTION_PROTOCOL_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.protocol_identity, "WC2 collection protocol"),
            (self.review_policy_identity, "WC2 review policy"),
            (self.epoch2_activation_identity, "WC2 Epoch2 activation"),
        ):
            _require_sha256(value, label)
        if min(
            self.preregistered_at_ms,
            self.collection_start_ms,
            self.review_policy_collection_start_ms,
            self.epoch2_activated_at_ms,
        ) < 0:
            raise ValueError("WC2 collection protocol timestamps cannot be negative")
        if self.preregistered_at_ms >= self.collection_start_ms:
            raise ValueError(
                "WC2 collection protocol must be preregistered before collection"
            )
        if self.collection_start_ms < self.review_policy_collection_start_ms:
            raise ValueError(
                "WC2 collection protocol cannot predate review policy collection"
            )
        if self.collection_start_ms < self.epoch2_activated_at_ms:
            raise ValueError(
                "WC2 collection protocol cannot predate canonical Epoch2 activation"
            )
        current_plan = LiveCoveragePlan.current_pilot()
        if self.coverage_plan_version != current_plan.version:
            raise ValueError("WC2 collection protocol coverage plan version mismatch")
        expected_contexts = current_wc2_collection_context_identities()
        if self.coverage_context_identities != expected_contexts:
            raise ValueError(
                "WC2 collection protocol must freeze exact current pilot contexts"
            )
        if (
            self.maximum_issuance_delay_ms
            != WC2_COLLECTION_MAXIMUM_ISSUANCE_DELAY_MS
        ):
            raise ValueError("WC2 collection issuance-delay contract is immutable")
        if (
            self.horizon_bars_by_timeframe
            != WC2_COLLECTION_HORIZON_BARS_BY_TIMEFRAME
        ):
            raise ValueError("WC2 collection horizon contract is immutable")
        if self.paper_action_mode != WC2_COLLECTION_PAPER_ACTION_MODE:
            raise ValueError("WC2 collection paper-action mode mismatch")
        if self.probability_mode != WC2_COLLECTION_PROBABILITY_MODE:
            raise ValueError("WC2 collection probability mode mismatch")
        if (
            self.historical_backfill_authority
            or self.automatic_promotion
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 collection protocol cannot grant authority")
        if self.schema_version != WC2_COLLECTION_PROTOCOL_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 collection protocol schema")
        if self.engine_version != WC2_COLLECTION_PROTOCOL_ENGINE_VERSION:
            raise ValueError("unsupported WC2 collection protocol engine")
        if self.protocol_identity != canonical_sha256(
            _protocol_payload(self)
        ):
            raise ValueError("WC2 collection protocol identity mismatch")

    def horizon_bars_for(self, timeframe: str) -> int:
        mapping = dict(self.horizon_bars_by_timeframe)
        try:
            return mapping[timeframe]
        except KeyError as exc:
            raise ValueError(
                f"WC2 collection protocol does not authorize timeframe {timeframe}"
            ) from exc


def build_wc2_collection_protocol(
    *,
    review_policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    preregistered_at_ms: int,
    collection_start_ms: int,
) -> WC2CollectionProtocol:
    if collection_start_ms < review_policy.collection_start_ms:
        raise ValueError(
            "WC2 collection protocol cannot predate review policy collection"
        )
    if collection_start_ms < activation.activated_at_ms:
        raise ValueError(
            "WC2 collection protocol cannot predate canonical Epoch2 activation"
        )
    plan = LiveCoveragePlan.current_pilot()
    values: dict[str, object] = {
        "automatic_promotion": False,
        "collection_start_ms": collection_start_ms,
        "coverage_context_identities": current_wc2_collection_context_identities(),
        "coverage_plan_version": plan.version,
        "engine_version": WC2_COLLECTION_PROTOCOL_ENGINE_VERSION,
        "epoch2_activated_at_ms": activation.activated_at_ms,
        "epoch2_activation_identity": activation.activation_identity,
        "historical_backfill_authority": False,
        "horizon_bars_by_timeframe": (
            WC2_COLLECTION_HORIZON_BARS_BY_TIMEFRAME
        ),
        "maximum_issuance_delay_ms": (
            WC2_COLLECTION_MAXIMUM_ISSUANCE_DELAY_MS
        ),
        "paper_action_mode": WC2_COLLECTION_PAPER_ACTION_MODE,
        "preregistered_at_ms": preregistered_at_ms,
        "probability_mode": WC2_COLLECTION_PROBABILITY_MODE,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "review_policy_collection_start_ms": (
            review_policy.collection_start_ms
        ),
        "review_policy_identity": review_policy.policy_identity,
        "schema_version": WC2_COLLECTION_PROTOCOL_SCHEMA_VERSION,
    }
    return WC2CollectionProtocol(
        protocol_identity=canonical_sha256(values),
        review_policy_identity=review_policy.policy_identity,
        epoch2_activation_identity=activation.activation_identity,
        preregistered_at_ms=preregistered_at_ms,
        collection_start_ms=collection_start_ms,
        review_policy_collection_start_ms=review_policy.collection_start_ms,
        epoch2_activated_at_ms=activation.activated_at_ms,
        coverage_plan_version=plan.version,
        coverage_context_identities=current_wc2_collection_context_identities(),
        maximum_issuance_delay_ms=WC2_COLLECTION_MAXIMUM_ISSUANCE_DELAY_MS,
        horizon_bars_by_timeframe=WC2_COLLECTION_HORIZON_BARS_BY_TIMEFRAME,
        paper_action_mode=WC2_COLLECTION_PAPER_ACTION_MODE,
        probability_mode=WC2_COLLECTION_PROBABILITY_MODE,
    )


class WC2CollectionProtocolStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(WC2_COLLECTION_PROTOCOL_SUFFIX):
            raise ValueError(
                "WC2 collection protocol path must end with "
                f"{WC2_COLLECTION_PROTOCOL_SUFFIX}"
            )

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            unexpected = existing - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "WC2 collection protocol refuses database with other tables"
                )
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_RECORD_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    protocol_identity TEXT UNIQUE NOT NULL,
                    review_policy_identity TEXT NOT NULL,
                    epoch2_activation_identity TEXT NOT NULL,
                    preregistered_at_ms INTEGER NOT NULL,
                    collection_start_ms INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                )"""
            )
            expected = {
                "engine_version": WC2_COLLECTION_PROTOCOL_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": WC2_COLLECTION_PROTOCOL_SCHEMA_VERSION,
                "semantic": (
                    "preregistered_collection_rules_not_performance_claim"
                ),
            }
            for key, value in expected.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key=?",
                    (key,),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE}(key,value) VALUES (?,?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError(
                        "WC2 collection protocol metadata mismatch"
                    )
            for table in (_META_TABLE, _RECORD_TABLE):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'append-only WC2 collection protocol'
                            );
                        END"""
                    )

    def append(self, protocol: WC2CollectionProtocol) -> bool:
        self.initialize()
        payload = canonical_json(_protocol_payload(protocol))
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = db.execute(
                f"""SELECT protocol_identity, payload_json
                FROM {_RECORD_TABLE}
                WHERE protocol_identity=? OR collection_start_ms=?""",
                (protocol.protocol_identity, protocol.collection_start_ms),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == protocol.protocol_identity
                    and str(existing[1]) == payload
                ):
                    return False
                raise ValueError("WC2 collection protocol identity conflict")
            last = db.execute(
                f"""SELECT collection_start_ms
                FROM {_RECORD_TABLE}
                ORDER BY sequence_id DESC
                LIMIT 1"""
            ).fetchone()
            if last is not None and protocol.preregistered_at_ms <= int(last[0]):
                raise ValueError(
                    "new WC2 collection protocol must be preregistered "
                    "after prior collection boundary"
                )
            db.execute(
                f"""INSERT INTO {_RECORD_TABLE}(
                    protocol_identity,
                    review_policy_identity,
                    epoch2_activation_identity,
                    preregistered_at_ms,
                    collection_start_ms,
                    payload_json
                ) VALUES (?,?,?,?,?,?)""",
                (
                    protocol.protocol_identity,
                    protocol.review_policy_identity,
                    protocol.epoch2_activation_identity,
                    protocol.preregistered_at_ms,
                    protocol.collection_start_ms,
                    payload,
                ),
            )
        return True

    def latest(self) -> WC2CollectionProtocol | None:
        if not self.path.is_file():
            return None
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                f"""SELECT payload_json
                FROM {_RECORD_TABLE}
                ORDER BY sequence_id DESC
                LIMIT 1"""
            ).fetchone()
        return None if row is None else _protocol_from_json(str(row[0]))

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _protocol_payload(protocol: WC2CollectionProtocol) -> dict[str, object]:
    return {
        "automatic_promotion": protocol.automatic_promotion,
        "collection_start_ms": protocol.collection_start_ms,
        "coverage_context_identities": protocol.coverage_context_identities,
        "coverage_plan_version": protocol.coverage_plan_version,
        "engine_version": protocol.engine_version,
        "epoch2_activated_at_ms": protocol.epoch2_activated_at_ms,
        "epoch2_activation_identity": protocol.epoch2_activation_identity,
        "historical_backfill_authority": (
            protocol.historical_backfill_authority
        ),
        "horizon_bars_by_timeframe": protocol.horizon_bars_by_timeframe,
        "maximum_issuance_delay_ms": protocol.maximum_issuance_delay_ms,
        "paper_action_mode": protocol.paper_action_mode,
        "preregistered_at_ms": protocol.preregistered_at_ms,
        "probability_mode": protocol.probability_mode,
        "production_authority": protocol.production_authority,
        "real_capital": protocol.real_capital,
        "review_policy_collection_start_ms": (
            protocol.review_policy_collection_start_ms
        ),
        "review_policy_identity": protocol.review_policy_identity,
        "schema_version": protocol.schema_version,
    }


def _protocol_from_json(payload_json: str) -> WC2CollectionProtocol:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("WC2 collection protocol payload must be object")
    protocol = WC2CollectionProtocol(
        protocol_identity=canonical_sha256(raw),
        review_policy_identity=_text(raw, "review_policy_identity"),
        epoch2_activation_identity=_text(raw, "epoch2_activation_identity"),
        preregistered_at_ms=_integer(raw, "preregistered_at_ms"),
        collection_start_ms=_integer(raw, "collection_start_ms"),
        review_policy_collection_start_ms=_integer(
            raw,
            "review_policy_collection_start_ms",
        ),
        epoch2_activated_at_ms=_integer(raw, "epoch2_activated_at_ms"),
        coverage_plan_version=_text(raw, "coverage_plan_version"),
        coverage_context_identities=tuple(
            tuple(_text_item(part) for part in item)
            for item in _list(raw, "coverage_context_identities")
        ),
        maximum_issuance_delay_ms=_integer(
            raw,
            "maximum_issuance_delay_ms",
        ),
        horizon_bars_by_timeframe=tuple(
            (_text_item(item[0]), _integer_item(item[1]))
            for item in _list(raw, "horizon_bars_by_timeframe")
        ),
        paper_action_mode=_text(raw, "paper_action_mode"),
        probability_mode=_text(raw, "probability_mode"),
        historical_backfill_authority=bool(
            raw.get("historical_backfill_authority")
        ),
        automatic_promotion=bool(raw.get("automatic_promotion")),
        production_authority=bool(raw.get("production_authority")),
        real_capital=_integer(raw, "real_capital"),
        schema_version=_text(raw, "schema_version"),
        engine_version=_text(raw, "engine_version"),
    )
    if canonical_json(raw) != payload_json:
        raise ValueError("WC2 collection protocol JSON is not canonical")
    return protocol


def _list(raw: dict[str, object], key: str) -> list[object]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be list")
    return value


def _text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be non-empty text")
    return value


def _integer(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    return _integer_item(value)


def _text_item(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("WC2 collection protocol item must be text")
    return value


def _integer_item(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("WC2 collection protocol item must be integer")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
