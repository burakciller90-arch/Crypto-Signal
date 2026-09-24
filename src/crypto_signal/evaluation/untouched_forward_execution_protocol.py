from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocol,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2UntouchedForwardPolicy,
)
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.autonomy import (
    DEFAULT_AUTONOMY_COOLDOWN_MS,
    DEFAULT_AUTONOMY_DECISION_TIMEFRAME,
    DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION,
    DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS,
    DEFAULT_AUTONOMY_REQUIRED_EXCHANGES,
    PAPER_AUTONOMY_POLICY_VERSION,
)
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution_input import PAPER_EXECUTION_INPUT_POLICY_VERSION
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    REAL_CAPITAL,
)
from crypto_signal.paper.sizing import PAPER_POSITION_SIZING_POLICY_VERSION
from crypto_signal.paper.venue_rules import (
    DEFAULT_SIMULATED_FEE_RATE,
    DEFAULT_SIMULATED_SLIPPAGE_RATE,
    DEFAULT_SIMULATED_SPREAD_RATE,
    PAPER_SIMULATED_COST_POLICY_VERSION,
    PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION,
)

WC2_PAPER_EXECUTION_PROTOCOL_SCHEMA_VERSION = (
    "wc2-paper-execution-protocol.v1"
)
WC2_PAPER_EXECUTION_PROTOCOL_ENGINE_VERSION = (
    "wc2-paper-execution-protocol-v1/1"
)
WC2_PAPER_EXECUTION_PROTOCOL_SUFFIX = (
    ".wc2-paper-execution-protocol.sqlite3"
)
WC2_PAPER_EXECUTION_DECISION_MODE = (
    "paper_autonomy_v2_exact_dual_provider_4h"
)
WC2_PAPER_EXECUTION_SIZING_MODE = (
    "paper_position_sizing_policy_v1"
)
WC2_PAPER_EXECUTION_REFERENCE_MODE = (
    "binance_spot_15m_first_closed_after_signal_open"
)
WC2_PAPER_EXECUTION_VENUE_MODE = (
    "frozen_binance_spot_rules_asof_execution_input"
)
WC2_PAPER_EXECUTION_FILL_MODE = (
    "deterministic_adverse_full_fill_no_partial"
)
WC2_PAPER_EXECUTION_ECONOMIC_CLAIM_RULE = (
    "at_least_one_trade_with_fill_and_explicit_cost_evidence"
)

_META_TABLE = "wc2_paper_execution_protocol_meta"
_RECORD_TABLE = "wc2_paper_execution_protocols"
_ALLOWED_TABLES = {_META_TABLE, _RECORD_TABLE}


@dataclass(frozen=True, slots=True)
class WC2PaperExecutionProtocol:
    protocol_identity: str
    review_policy_identity: str
    collection_protocol_identity: str
    epoch2_activation_identity: str
    preregistered_at_ms: int
    execution_start_ms: int
    review_policy_collection_start_ms: int
    collection_protocol_start_ms: int
    epoch2_activated_at_ms: int
    vault_id: PaperVaultId
    decision_mode: str
    autonomy_policy_version: str
    autonomy_decision_timeframe: str
    autonomy_required_exchanges: tuple[str, ...]
    autonomy_max_position_risk_fraction: Decimal
    autonomy_cooldown_ms: int
    autonomy_max_signal_age_ms: int
    execution_input_policy_version: str
    execution_reference_mode: str
    position_sizing_policy_version: str
    venue_rule_schema_version: str
    venue_mode: str
    simulated_cost_policy_version: str
    simulated_fee_rate: Decimal
    simulated_spread_rate: Decimal
    simulated_slippage_rate: Decimal
    execution_policy_version: str
    fill_mode: str
    economic_claim_rule: str
    paper_simulation_authority: bool = True
    historical_backfill_authority: bool = False
    automatic_promotion: bool = False
    real_order_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = WC2_PAPER_EXECUTION_PROTOCOL_SCHEMA_VERSION
    engine_version: str = WC2_PAPER_EXECUTION_PROTOCOL_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.protocol_identity, "WC2 paper execution protocol"),
            (self.review_policy_identity, "WC2 review policy"),
            (self.collection_protocol_identity, "WC2 collection protocol"),
            (self.epoch2_activation_identity, "WC2 Epoch2 activation"),
        ):
            _require_sha256(value, label)
        if min(
            self.preregistered_at_ms,
            self.execution_start_ms,
            self.review_policy_collection_start_ms,
            self.collection_protocol_start_ms,
            self.epoch2_activated_at_ms,
        ) < 0:
            raise ValueError("WC2 paper execution timestamps cannot be negative")
        if self.preregistered_at_ms >= self.execution_start_ms:
            raise ValueError(
                "WC2 paper execution must be preregistered before activation"
            )
        if self.execution_start_ms < self.review_policy_collection_start_ms:
            raise ValueError(
                "WC2 paper execution cannot predate review policy collection"
            )
        if self.execution_start_ms < self.collection_protocol_start_ms:
            raise ValueError(
                "WC2 paper execution cannot predate collection protocol"
            )
        if self.execution_start_ms < self.epoch2_activated_at_ms:
            raise ValueError(
                "WC2 paper execution cannot predate canonical Epoch2"
            )
        if self.vault_id is not PaperVaultId.CORE:
            raise ValueError("WC2 paper execution v1 is bound to CORE vault")
        if self.decision_mode != WC2_PAPER_EXECUTION_DECISION_MODE:
            raise ValueError("WC2 paper execution decision mode mismatch")
        if self.autonomy_policy_version != PAPER_AUTONOMY_POLICY_VERSION:
            raise ValueError("WC2 paper execution autonomy policy mismatch")
        if (
            self.autonomy_decision_timeframe
            != DEFAULT_AUTONOMY_DECISION_TIMEFRAME
        ):
            raise ValueError("WC2 paper execution timeframe mismatch")
        expected_exchanges = tuple(
            exchange.value for exchange in DEFAULT_AUTONOMY_REQUIRED_EXCHANGES
        )
        if self.autonomy_required_exchanges != expected_exchanges:
            raise ValueError("WC2 paper execution provider set mismatch")
        if (
            self.autonomy_max_position_risk_fraction
            != DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION
        ):
            raise ValueError("WC2 paper execution risk fraction mismatch")
        if self.autonomy_cooldown_ms != DEFAULT_AUTONOMY_COOLDOWN_MS:
            raise ValueError("WC2 paper execution cooldown mismatch")
        if (
            self.autonomy_max_signal_age_ms
            != DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS
        ):
            raise ValueError("WC2 paper execution signal-age mismatch")
        if (
            self.execution_input_policy_version
            != PAPER_EXECUTION_INPUT_POLICY_VERSION
        ):
            raise ValueError("WC2 paper execution input policy mismatch")
        if (
            self.execution_reference_mode
            != WC2_PAPER_EXECUTION_REFERENCE_MODE
        ):
            raise ValueError("WC2 paper execution reference mode mismatch")
        if (
            self.position_sizing_policy_version
            != PAPER_POSITION_SIZING_POLICY_VERSION
        ):
            raise ValueError("WC2 paper execution sizing policy mismatch")
        if (
            self.venue_rule_schema_version
            != PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION
        ):
            raise ValueError("WC2 paper execution venue schema mismatch")
        if self.venue_mode != WC2_PAPER_EXECUTION_VENUE_MODE:
            raise ValueError("WC2 paper execution venue mode mismatch")
        if (
            self.simulated_cost_policy_version
            != PAPER_SIMULATED_COST_POLICY_VERSION
        ):
            raise ValueError("WC2 paper execution cost policy mismatch")
        if self.simulated_fee_rate != DEFAULT_SIMULATED_FEE_RATE:
            raise ValueError("WC2 paper execution fee assumption mismatch")
        if self.simulated_spread_rate != DEFAULT_SIMULATED_SPREAD_RATE:
            raise ValueError("WC2 paper execution spread assumption mismatch")
        if self.simulated_slippage_rate != DEFAULT_SIMULATED_SLIPPAGE_RATE:
            raise ValueError("WC2 paper execution slippage assumption mismatch")
        if self.execution_policy_version != PAPER_EXECUTION_POLICY_VERSION:
            raise ValueError("WC2 paper execution fill policy mismatch")
        if self.fill_mode != WC2_PAPER_EXECUTION_FILL_MODE:
            raise ValueError("WC2 paper execution fill mode mismatch")
        if self.economic_claim_rule != WC2_PAPER_EXECUTION_ECONOMIC_CLAIM_RULE:
            raise ValueError("WC2 paper execution economic claim rule mismatch")
        if not self.paper_simulation_authority:
            raise ValueError(
                "WC2 paper execution protocol must authorize virtual simulation"
            )
        if (
            self.historical_backfill_authority
            or self.automatic_promotion
            or self.real_order_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 paper execution cannot grant real authority")
        if self.schema_version != WC2_PAPER_EXECUTION_PROTOCOL_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 paper execution schema")
        if self.engine_version != WC2_PAPER_EXECUTION_PROTOCOL_ENGINE_VERSION:
            raise ValueError("unsupported WC2 paper execution engine")
        if self.protocol_identity != canonical_sha256(_protocol_payload(self)):
            raise ValueError("WC2 paper execution protocol identity mismatch")


def build_wc2_paper_execution_protocol(
    *,
    review_policy: WC2UntouchedForwardPolicy,
    collection_protocol: WC2CollectionProtocol,
    activation: Epoch2ActivationRecord,
    preregistered_at_ms: int,
    execution_start_ms: int,
) -> WC2PaperExecutionProtocol:
    if collection_protocol.review_policy_identity != review_policy.policy_identity:
        raise ValueError(
            "WC2 paper execution requires exact collection/review policy lineage"
        )
    if (
        collection_protocol.epoch2_activation_identity
        != activation.activation_identity
    ):
        raise ValueError(
            "WC2 paper execution requires exact collection/Epoch2 lineage"
        )
    values: dict[str, object] = {
        "automatic_promotion": False,
        "autonomy_cooldown_ms": DEFAULT_AUTONOMY_COOLDOWN_MS,
        "autonomy_decision_timeframe": DEFAULT_AUTONOMY_DECISION_TIMEFRAME,
        "autonomy_max_position_risk_fraction": (
            DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION
        ),
        "autonomy_max_signal_age_ms": DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS,
        "autonomy_policy_version": PAPER_AUTONOMY_POLICY_VERSION,
        "autonomy_required_exchanges": tuple(
            exchange.value for exchange in DEFAULT_AUTONOMY_REQUIRED_EXCHANGES
        ),
        "collection_protocol_identity": (
            collection_protocol.protocol_identity
        ),
        "collection_protocol_start_ms": (
            collection_protocol.collection_start_ms
        ),
        "decision_mode": WC2_PAPER_EXECUTION_DECISION_MODE,
        "economic_claim_rule": WC2_PAPER_EXECUTION_ECONOMIC_CLAIM_RULE,
        "engine_version": WC2_PAPER_EXECUTION_PROTOCOL_ENGINE_VERSION,
        "epoch2_activated_at_ms": activation.activated_at_ms,
        "epoch2_activation_identity": activation.activation_identity,
        "execution_input_policy_version": (
            PAPER_EXECUTION_INPUT_POLICY_VERSION
        ),
        "execution_policy_version": PAPER_EXECUTION_POLICY_VERSION,
        "execution_reference_mode": WC2_PAPER_EXECUTION_REFERENCE_MODE,
        "execution_start_ms": execution_start_ms,
        "fill_mode": WC2_PAPER_EXECUTION_FILL_MODE,
        "historical_backfill_authority": False,
        "paper_simulation_authority": True,
        "position_sizing_policy_version": (
            PAPER_POSITION_SIZING_POLICY_VERSION
        ),
        "preregistered_at_ms": preregistered_at_ms,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "real_order_authority": False,
        "review_policy_collection_start_ms": (
            review_policy.collection_start_ms
        ),
        "review_policy_identity": review_policy.policy_identity,
        "schema_version": WC2_PAPER_EXECUTION_PROTOCOL_SCHEMA_VERSION,
        "simulated_cost_policy_version": (
            PAPER_SIMULATED_COST_POLICY_VERSION
        ),
        "simulated_fee_rate": DEFAULT_SIMULATED_FEE_RATE,
        "simulated_slippage_rate": DEFAULT_SIMULATED_SLIPPAGE_RATE,
        "simulated_spread_rate": DEFAULT_SIMULATED_SPREAD_RATE,
        "vault_id": PaperVaultId.CORE,
        "venue_mode": WC2_PAPER_EXECUTION_VENUE_MODE,
        "venue_rule_schema_version": (
            PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION
        ),
    }
    return WC2PaperExecutionProtocol(
        protocol_identity=canonical_sha256(values),
        review_policy_identity=review_policy.policy_identity,
        collection_protocol_identity=collection_protocol.protocol_identity,
        epoch2_activation_identity=activation.activation_identity,
        preregistered_at_ms=preregistered_at_ms,
        execution_start_ms=execution_start_ms,
        review_policy_collection_start_ms=review_policy.collection_start_ms,
        collection_protocol_start_ms=collection_protocol.collection_start_ms,
        epoch2_activated_at_ms=activation.activated_at_ms,
        vault_id=PaperVaultId.CORE,
        decision_mode=WC2_PAPER_EXECUTION_DECISION_MODE,
        autonomy_policy_version=PAPER_AUTONOMY_POLICY_VERSION,
        autonomy_decision_timeframe=DEFAULT_AUTONOMY_DECISION_TIMEFRAME,
        autonomy_required_exchanges=tuple(
            exchange.value for exchange in DEFAULT_AUTONOMY_REQUIRED_EXCHANGES
        ),
        autonomy_max_position_risk_fraction=(
            DEFAULT_AUTONOMY_MAX_POSITION_RISK_FRACTION
        ),
        autonomy_cooldown_ms=DEFAULT_AUTONOMY_COOLDOWN_MS,
        autonomy_max_signal_age_ms=DEFAULT_AUTONOMY_MAX_SIGNAL_AGE_MS,
        execution_input_policy_version=PAPER_EXECUTION_INPUT_POLICY_VERSION,
        execution_reference_mode=WC2_PAPER_EXECUTION_REFERENCE_MODE,
        position_sizing_policy_version=PAPER_POSITION_SIZING_POLICY_VERSION,
        venue_rule_schema_version=PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION,
        venue_mode=WC2_PAPER_EXECUTION_VENUE_MODE,
        simulated_cost_policy_version=PAPER_SIMULATED_COST_POLICY_VERSION,
        simulated_fee_rate=DEFAULT_SIMULATED_FEE_RATE,
        simulated_spread_rate=DEFAULT_SIMULATED_SPREAD_RATE,
        simulated_slippage_rate=DEFAULT_SIMULATED_SLIPPAGE_RATE,
        execution_policy_version=PAPER_EXECUTION_POLICY_VERSION,
        fill_mode=WC2_PAPER_EXECUTION_FILL_MODE,
        economic_claim_rule=WC2_PAPER_EXECUTION_ECONOMIC_CLAIM_RULE,
    )


class WC2PaperExecutionProtocolStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(WC2_PAPER_EXECUTION_PROTOCOL_SUFFIX):
            raise ValueError(
                "WC2 paper execution protocol path must end with "
                f"{WC2_PAPER_EXECUTION_PROTOCOL_SUFFIX}"
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
                    "WC2 paper execution protocol refuses unrelated tables"
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
                    collection_protocol_identity TEXT NOT NULL,
                    epoch2_activation_identity TEXT NOT NULL,
                    preregistered_at_ms INTEGER NOT NULL,
                    execution_start_ms INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                )"""
            )
            expected = {
                "engine_version": WC2_PAPER_EXECUTION_PROTOCOL_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": WC2_PAPER_EXECUTION_PROTOCOL_SCHEMA_VERSION,
                "semantic": "preregistered_virtual_execution_rules_not_edge_claim",
            }
            for key, value in expected.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key=?",
                    (key, value),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE}(key,value) VALUES (?,?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError(
                        "WC2 paper execution protocol metadata mismatch"
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
                                'append-only WC2 paper execution protocol'
                            );
                        END"""
                    )

    def append(self, protocol: WC2PaperExecutionProtocol) -> bool:
        self.initialize()
        payload = canonical_json(_protocol_payload(protocol))
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = db.execute(
                f"""SELECT protocol_identity, payload_json
                FROM {_RECORD_TABLE}
                WHERE protocol_identity=? OR execution_start_ms=?""",
                (protocol.protocol_identity, protocol.execution_start_ms),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == protocol.protocol_identity
                    and str(existing[1]) == payload
                ):
                    return False
                raise ValueError(
                    "WC2 paper execution protocol identity conflict"
                )
            last = db.execute(
                f"""SELECT execution_start_ms
                FROM {_RECORD_TABLE}
                ORDER BY sequence_id DESC LIMIT 1"""
            ).fetchone()
            if last is not None and protocol.preregistered_at_ms <= int(last[0]):
                raise ValueError(
                    "new WC2 paper execution protocol must be preregistered "
                    "after prior execution boundary"
                )
            db.execute(
                f"""INSERT INTO {_RECORD_TABLE}(
                    protocol_identity,
                    review_policy_identity,
                    collection_protocol_identity,
                    epoch2_activation_identity,
                    preregistered_at_ms,
                    execution_start_ms,
                    payload_json
                ) VALUES (?,?,?,?,?,?,?)""",
                (
                    protocol.protocol_identity,
                    protocol.review_policy_identity,
                    protocol.collection_protocol_identity,
                    protocol.epoch2_activation_identity,
                    protocol.preregistered_at_ms,
                    protocol.execution_start_ms,
                    payload,
                ),
            )
        return True

    def latest(self) -> WC2PaperExecutionProtocol | None:
        if not self.path.is_file():
            return None
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                f"""SELECT payload_json
                FROM {_RECORD_TABLE}
                ORDER BY sequence_id DESC LIMIT 1"""
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


def _protocol_payload(
    protocol: WC2PaperExecutionProtocol,
) -> dict[str, object]:
    return {
        "automatic_promotion": protocol.automatic_promotion,
        "autonomy_cooldown_ms": protocol.autonomy_cooldown_ms,
        "autonomy_decision_timeframe": protocol.autonomy_decision_timeframe,
        "autonomy_max_position_risk_fraction": (
            protocol.autonomy_max_position_risk_fraction
        ),
        "autonomy_max_signal_age_ms": protocol.autonomy_max_signal_age_ms,
        "autonomy_policy_version": protocol.autonomy_policy_version,
        "autonomy_required_exchanges": protocol.autonomy_required_exchanges,
        "collection_protocol_identity": protocol.collection_protocol_identity,
        "collection_protocol_start_ms": protocol.collection_protocol_start_ms,
        "decision_mode": protocol.decision_mode,
        "economic_claim_rule": protocol.economic_claim_rule,
        "engine_version": protocol.engine_version,
        "epoch2_activated_at_ms": protocol.epoch2_activated_at_ms,
        "epoch2_activation_identity": protocol.epoch2_activation_identity,
        "execution_input_policy_version": (
            protocol.execution_input_policy_version
        ),
        "execution_policy_version": protocol.execution_policy_version,
        "execution_reference_mode": protocol.execution_reference_mode,
        "execution_start_ms": protocol.execution_start_ms,
        "fill_mode": protocol.fill_mode,
        "historical_backfill_authority": (
            protocol.historical_backfill_authority
        ),
        "paper_simulation_authority": protocol.paper_simulation_authority,
        "position_sizing_policy_version": (
            protocol.position_sizing_policy_version
        ),
        "preregistered_at_ms": protocol.preregistered_at_ms,
        "production_authority": protocol.production_authority,
        "real_capital": protocol.real_capital,
        "real_order_authority": protocol.real_order_authority,
        "review_policy_collection_start_ms": (
            protocol.review_policy_collection_start_ms
        ),
        "review_policy_identity": protocol.review_policy_identity,
        "schema_version": protocol.schema_version,
        "simulated_cost_policy_version": (
            protocol.simulated_cost_policy_version
        ),
        "simulated_fee_rate": protocol.simulated_fee_rate,
        "simulated_slippage_rate": protocol.simulated_slippage_rate,
        "simulated_spread_rate": protocol.simulated_spread_rate,
        "vault_id": protocol.vault_id,
        "venue_mode": protocol.venue_mode,
        "venue_rule_schema_version": protocol.venue_rule_schema_version,
    }


def _protocol_from_json(payload_json: str) -> WC2PaperExecutionProtocol:
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("WC2 paper execution protocol payload must be object")
    protocol = WC2PaperExecutionProtocol(
        protocol_identity=canonical_sha256(raw),
        review_policy_identity=_text(raw, "review_policy_identity"),
        collection_protocol_identity=_text(
            raw, "collection_protocol_identity"
        ),
        epoch2_activation_identity=_text(raw, "epoch2_activation_identity"),
        preregistered_at_ms=_integer(raw, "preregistered_at_ms"),
        execution_start_ms=_integer(raw, "execution_start_ms"),
        review_policy_collection_start_ms=_integer(
            raw, "review_policy_collection_start_ms"
        ),
        collection_protocol_start_ms=_integer(
            raw, "collection_protocol_start_ms"
        ),
        epoch2_activated_at_ms=_integer(raw, "epoch2_activated_at_ms"),
        vault_id=PaperVaultId(_text(raw, "vault_id")),
        decision_mode=_text(raw, "decision_mode"),
        autonomy_policy_version=_text(raw, "autonomy_policy_version"),
        autonomy_decision_timeframe=_text(
            raw, "autonomy_decision_timeframe"
        ),
        autonomy_required_exchanges=tuple(
            _text_item(item)
            for item in _list(raw, "autonomy_required_exchanges")
        ),
        autonomy_max_position_risk_fraction=_decimal(
            raw, "autonomy_max_position_risk_fraction"
        ),
        autonomy_cooldown_ms=_integer(raw, "autonomy_cooldown_ms"),
        autonomy_max_signal_age_ms=_integer(
            raw, "autonomy_max_signal_age_ms"
        ),
        execution_input_policy_version=_text(
            raw, "execution_input_policy_version"
        ),
        execution_reference_mode=_text(raw, "execution_reference_mode"),
        position_sizing_policy_version=_text(
            raw, "position_sizing_policy_version"
        ),
        venue_rule_schema_version=_text(raw, "venue_rule_schema_version"),
        venue_mode=_text(raw, "venue_mode"),
        simulated_cost_policy_version=_text(
            raw, "simulated_cost_policy_version"
        ),
        simulated_fee_rate=_decimal(raw, "simulated_fee_rate"),
        simulated_spread_rate=_decimal(raw, "simulated_spread_rate"),
        simulated_slippage_rate=_decimal(raw, "simulated_slippage_rate"),
        execution_policy_version=_text(raw, "execution_policy_version"),
        fill_mode=_text(raw, "fill_mode"),
        economic_claim_rule=_text(raw, "economic_claim_rule"),
        paper_simulation_authority=bool(
            raw.get("paper_simulation_authority")
        ),
        historical_backfill_authority=bool(
            raw.get("historical_backfill_authority")
        ),
        automatic_promotion=bool(raw.get("automatic_promotion")),
        real_order_authority=bool(raw.get("real_order_authority")),
        production_authority=bool(raw.get("production_authority")),
        real_capital=_integer(raw, "real_capital"),
        schema_version=_text(raw, "schema_version"),
        engine_version=_text(raw, "engine_version"),
    )
    if canonical_json(raw) != payload_json:
        raise ValueError(
            "WC2 paper execution protocol JSON is not canonical"
        )
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
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be integer")
    return value


def _decimal(raw: dict[str, object], key: str) -> Decimal:
    value = raw.get(key)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    raise TypeError(f"{key} must be decimal-compatible")


def _text_item(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("WC2 paper execution protocol item must be text")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
