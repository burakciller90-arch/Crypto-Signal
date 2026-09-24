from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from crypto_signal.intelligence.breakout_volatility import (
    BREAKOUT_VOLATILITY_ENGINE_VERSION,
)
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.epoch2_accounting import R21_ENGINE_VERSION
from crypto_signal.paper.position_sizing_intelligence import (
    PositionSizingPolicy,
    SizingMethod,
    build_position_sizing_policy,
)
from crypto_signal.paper.venue_rules import (
    PAPER_SIMULATED_COST_POLICY_VERSION,
)

WC2_ECONOMIC_EXECUTION_POLICY_SCHEMA_VERSION = (
    "wc2-economic-execution-policy-v1/1"
)
WC2_ECONOMIC_EXECUTION_POLICY_ENGINE_VERSION = (
    "wc2-economic-execution-policy-v1/1"
)
WC2_ECONOMIC_EXECUTION_POLICY_SUFFIX = (
    ".wc2-economic-execution-policy.sqlite3"
)
WC2_ECONOMIC_PAPER_MODE = (
    "reviewed_fixed_fractional_simulated_execution_v1"
)
WC2_PAYOFF_MEASUREMENT_VERSION = "wc2-geometry-payoff-r-v1/1"
WC2_CORRELATION_MEASUREMENT_VERSION = (
    "wc2-core-exposure-correlation-15m-v1/1"
)
WC2_LIQUIDITY_MEASUREMENT_VERSION = (
    "wc2-pit-liquidity-gate-score-v1/1"
)
WC2_MARKET_REFERENCE_VERSION = "wc2-public-market-reference-v1/1"
WC2_CORRELATION_WINDOW_15M_BARS = 672
WC2_CORRELATION_MINIMUM_RETURN_PAIRS = 192
WC2_MARKET_REFERENCE_MAX_DELAY_MS = 120_000
WC2_MINIMUM_ACTUAL_PAPER_TRADES_FOR_ECONOMIC_REVIEW = 30
REAL_CAPITAL = 0

_META_TABLE = "wc2_economic_execution_policy_meta"
_POLICY_TABLE = "wc2_economic_execution_policies"
_ALLOWED_TABLES = {_META_TABLE, _POLICY_TABLE}


def build_wc2_fixed_fractional_sizing_policy() -> PositionSizingPolicy:
    """Return the accepted R25 fixed-fractional research-policy envelope."""
    return build_position_sizing_policy(
        policy_version="position-sizing-research-policy-v1/1",
        fixed_fraction_of_vault=Decimal("0.02"),
        maximum_fraction_of_vault=Decimal("0.25"),
        maximum_absolute_correlation=Decimal("0.70"),
        maximum_drawdown_fraction=Decimal("0.20"),
        maximum_volatility_fraction=Decimal("0.25"),
        minimum_liquidity_score_0_1=Decimal("0.60"),
        maximum_transaction_cost_r=Decimal("0.20"),
    )


@dataclass(frozen=True, slots=True)
class WC2EconomicExecutionPolicy:
    policy_identity: str
    preregistered_at_ms: int
    collection_start_ms: int
    review_policy_identity: str
    collection_protocol_identity: str
    epoch2_activation_identity: str
    sizing_policy_identity: str
    reviewed_sizing_method: SizingMethod
    paper_mode: str
    payoff_measurement_version: str
    correlation_measurement_version: str
    drawdown_measurement_version: str
    volatility_measurement_version: str
    liquidity_measurement_version: str
    execution_cost_policy_version: str
    market_reference_version: str
    correlation_window_15m_bars: int
    correlation_minimum_return_pairs: int
    market_reference_max_delay_ms: int
    minimum_actual_paper_trades_for_economic_review: int
    require_all_risk_domains_predecision: bool = True
    require_simulated_execution_for_every_trade: bool = True
    require_explicit_cost_evidence_for_every_trade: bool = True
    automatic_promotion: bool = False
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = WC2_ECONOMIC_EXECUTION_POLICY_SCHEMA_VERSION
    engine_version: str = WC2_ECONOMIC_EXECUTION_POLICY_ENGINE_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.policy_identity, "WC2 economic policy"),
            (self.review_policy_identity, "WC2 review policy"),
            (self.collection_protocol_identity, "WC2 collection protocol"),
            (self.epoch2_activation_identity, "WC2 Epoch2 activation"),
            (self.sizing_policy_identity, "WC2 sizing policy"),
        ):
            _require_sha256(value, label)
        if min(self.preregistered_at_ms, self.collection_start_ms) < 0:
            raise ValueError("WC2 economic policy timestamps cannot be negative")
        if self.preregistered_at_ms >= self.collection_start_ms:
            raise ValueError(
                "WC2 economic policy must be preregistered before collection"
            )
        expected_sizing = build_wc2_fixed_fractional_sizing_policy()
        if self.sizing_policy_identity != expected_sizing.policy_identity:
            raise ValueError("WC2 economic sizing policy identity mismatch")
        if self.reviewed_sizing_method is not SizingMethod.FIXED_FRACTIONAL:
            raise ValueError("WC2 economic v1 reviews fixed fractional only")
        if self.paper_mode != WC2_ECONOMIC_PAPER_MODE:
            raise ValueError("unsupported WC2 economic paper mode")
        expected_versions = (
            (self.payoff_measurement_version, WC2_PAYOFF_MEASUREMENT_VERSION),
            (
                self.correlation_measurement_version,
                WC2_CORRELATION_MEASUREMENT_VERSION,
            ),
            (self.drawdown_measurement_version, R21_ENGINE_VERSION),
            (
                self.volatility_measurement_version,
                BREAKOUT_VOLATILITY_ENGINE_VERSION,
            ),
            (
                self.liquidity_measurement_version,
                WC2_LIQUIDITY_MEASUREMENT_VERSION,
            ),
            (
                self.execution_cost_policy_version,
                PAPER_SIMULATED_COST_POLICY_VERSION,
            ),
            (self.market_reference_version, WC2_MARKET_REFERENCE_VERSION),
        )
        if any(actual != expected for actual, expected in expected_versions):
            raise ValueError("WC2 economic measurement version mismatch")
        if (
            self.correlation_window_15m_bars
            != WC2_CORRELATION_WINDOW_15M_BARS
            or self.correlation_minimum_return_pairs
            != WC2_CORRELATION_MINIMUM_RETURN_PAIRS
            or self.market_reference_max_delay_ms
            != WC2_MARKET_REFERENCE_MAX_DELAY_MS
            or self.minimum_actual_paper_trades_for_economic_review
            != WC2_MINIMUM_ACTUAL_PAPER_TRADES_FOR_ECONOMIC_REVIEW
        ):
            raise ValueError("WC2 economic v1 thresholds are immutable")
        if (
            self.correlation_minimum_return_pairs
            >= self.correlation_window_15m_bars
        ):
            raise ValueError("WC2 correlation minimum must fit inside window")
        if not (
            self.require_all_risk_domains_predecision
            and self.require_simulated_execution_for_every_trade
            and self.require_explicit_cost_evidence_for_every_trade
        ):
            raise ValueError("WC2 economic policy cannot weaken evidence gates")
        if (
            self.automatic_promotion
            or self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 economic policy crossed authority boundary")
        if self.schema_version != WC2_ECONOMIC_EXECUTION_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 economic policy schema")
        if self.engine_version != WC2_ECONOMIC_EXECUTION_POLICY_ENGINE_VERSION:
            raise ValueError("unsupported WC2 economic policy engine")
        if self.policy_identity != canonical_sha256(_policy_payload(self)):
            raise ValueError("WC2 economic policy identity mismatch")


def build_wc2_economic_execution_policy(
    *,
    preregistered_at_ms: int,
    collection_start_ms: int,
    review_policy_identity: str,
    collection_protocol_identity: str,
    epoch2_activation_identity: str,
) -> WC2EconomicExecutionPolicy:
    sizing = build_wc2_fixed_fractional_sizing_policy()
    values = {
        "preregistered_at_ms": preregistered_at_ms,
        "collection_start_ms": collection_start_ms,
        "review_policy_identity": review_policy_identity,
        "collection_protocol_identity": collection_protocol_identity,
        "epoch2_activation_identity": epoch2_activation_identity,
        "sizing_policy_identity": sizing.policy_identity,
        "reviewed_sizing_method": SizingMethod.FIXED_FRACTIONAL,
        "paper_mode": WC2_ECONOMIC_PAPER_MODE,
        "payoff_measurement_version": WC2_PAYOFF_MEASUREMENT_VERSION,
        "correlation_measurement_version": (
            WC2_CORRELATION_MEASUREMENT_VERSION
        ),
        "drawdown_measurement_version": R21_ENGINE_VERSION,
        "volatility_measurement_version": BREAKOUT_VOLATILITY_ENGINE_VERSION,
        "liquidity_measurement_version": WC2_LIQUIDITY_MEASUREMENT_VERSION,
        "execution_cost_policy_version": PAPER_SIMULATED_COST_POLICY_VERSION,
        "market_reference_version": WC2_MARKET_REFERENCE_VERSION,
        "correlation_window_15m_bars": WC2_CORRELATION_WINDOW_15M_BARS,
        "correlation_minimum_return_pairs": (
            WC2_CORRELATION_MINIMUM_RETURN_PAIRS
        ),
        "market_reference_max_delay_ms": WC2_MARKET_REFERENCE_MAX_DELAY_MS,
        "minimum_actual_paper_trades_for_economic_review": (
            WC2_MINIMUM_ACTUAL_PAPER_TRADES_FOR_ECONOMIC_REVIEW
        ),
        "require_all_risk_domains_predecision": True,
        "require_simulated_execution_for_every_trade": True,
        "require_explicit_cost_evidence_for_every_trade": True,
        "automatic_promotion": False,
        "canonical_epoch2_write_authority": False,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC2_ECONOMIC_EXECUTION_POLICY_SCHEMA_VERSION,
        "engine_version": WC2_ECONOMIC_EXECUTION_POLICY_ENGINE_VERSION,
    }
    return WC2EconomicExecutionPolicy(
        policy_identity=canonical_sha256(values),
        **values,
    )


class WC2EconomicExecutionPolicyStore:
    """Append-only preregistration for the future WC2 paper-economic rail."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(WC2_ECONOMIC_EXECUTION_POLICY_SUFFIX):
            raise ValueError(
                "WC2 economic policy path must end with "
                f"{WC2_ECONOMIC_EXECUTION_POLICY_SUFFIX}"
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
                    "WC2 economic policy refuses database with other tables"
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
                f"""CREATE TABLE IF NOT EXISTS {_POLICY_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_identity TEXT UNIQUE NOT NULL,
                    preregistered_at_ms INTEGER NOT NULL,
                    collection_start_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            expected_meta = {
                "schema_version": WC2_ECONOMIC_EXECUTION_POLICY_SCHEMA_VERSION,
                "engine_version": WC2_ECONOMIC_EXECUTION_POLICY_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "semantic": "forward_paper_execution_evidence_not_edge_claim",
            }
            for key, value in expected_meta.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key=?",
                    (key,),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE}(key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError("WC2 economic policy metadata mismatch")
            for table in (_META_TABLE, _POLICY_TABLE):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable WC2 economic execution policy'
                            );
                        END"""
                    )

    def append(self, policy: WC2EconomicExecutionPolicy) -> bool:
        self.initialize()
        payload = canonical_json(_policy_payload(policy))
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = db.execute(
                f"""SELECT payload_json FROM {_POLICY_TABLE}
                WHERE policy_identity=?""",
                (policy.policy_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("WC2 economic policy identity conflict")
                return False
            previous = db.execute(
                f"""SELECT collection_start_ms FROM {_POLICY_TABLE}
                ORDER BY sequence_id DESC LIMIT 1"""
            ).fetchone()
            if (
                previous is not None
                and policy.collection_start_ms <= int(previous[0])
            ):
                raise ValueError(
                    "new WC2 economic policy must start after prior cohort"
                )
            db.execute(
                f"""INSERT INTO {_POLICY_TABLE}(
                    policy_identity,
                    preregistered_at_ms,
                    collection_start_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?)""",
                (
                    policy.policy_identity,
                    policy.preregistered_at_ms,
                    policy.collection_start_ms,
                    payload,
                ),
            )
        return True

    def latest(self) -> WC2EconomicExecutionPolicy | None:
        if not self.path.is_file():
            return None
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("WC2 economic policy quick_check failed")
            row = db.execute(
                f"""SELECT policy_identity, payload_json
                FROM {_POLICY_TABLE}
                ORDER BY sequence_id DESC LIMIT 1"""
            ).fetchone()
        if row is None:
            return None
        raw = json.loads(str(row[1]))
        if not isinstance(raw, dict):
            raise TypeError("WC2 economic policy payload must be object")
        policy = build_wc2_economic_execution_policy(
            preregistered_at_ms=int(raw["preregistered_at_ms"]),
            collection_start_ms=int(raw["collection_start_ms"]),
            review_policy_identity=str(raw["review_policy_identity"]),
            collection_protocol_identity=str(
                raw["collection_protocol_identity"]
            ),
            epoch2_activation_identity=str(raw["epoch2_activation_identity"]),
        )
        if policy.policy_identity != str(row[0]):
            raise ValueError("stored WC2 economic policy identity mismatch")
        if canonical_json(_policy_payload(policy)) != str(row[1]):
            raise ValueError("stored WC2 economic policy payload mismatch")
        return policy

    def count(self) -> int:
        if not self.path.is_file():
            return 0
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                f"SELECT COUNT(*) FROM {_POLICY_TABLE}"
            ).fetchone()
        return 0 if row is None else int(row[0])


def _policy_payload(
    policy: WC2EconomicExecutionPolicy,
) -> dict[str, object]:
    return {
        "preregistered_at_ms": policy.preregistered_at_ms,
        "collection_start_ms": policy.collection_start_ms,
        "review_policy_identity": policy.review_policy_identity,
        "collection_protocol_identity": policy.collection_protocol_identity,
        "epoch2_activation_identity": policy.epoch2_activation_identity,
        "sizing_policy_identity": policy.sizing_policy_identity,
        "reviewed_sizing_method": policy.reviewed_sizing_method,
        "paper_mode": policy.paper_mode,
        "payoff_measurement_version": policy.payoff_measurement_version,
        "correlation_measurement_version": (
            policy.correlation_measurement_version
        ),
        "drawdown_measurement_version": policy.drawdown_measurement_version,
        "volatility_measurement_version": (
            policy.volatility_measurement_version
        ),
        "liquidity_measurement_version": (
            policy.liquidity_measurement_version
        ),
        "execution_cost_policy_version": (
            policy.execution_cost_policy_version
        ),
        "market_reference_version": policy.market_reference_version,
        "correlation_window_15m_bars": (
            policy.correlation_window_15m_bars
        ),
        "correlation_minimum_return_pairs": (
            policy.correlation_minimum_return_pairs
        ),
        "market_reference_max_delay_ms": (
            policy.market_reference_max_delay_ms
        ),
        "minimum_actual_paper_trades_for_economic_review": (
            policy.minimum_actual_paper_trades_for_economic_review
        ),
        "require_all_risk_domains_predecision": (
            policy.require_all_risk_domains_predecision
        ),
        "require_simulated_execution_for_every_trade": (
            policy.require_simulated_execution_for_every_trade
        ),
        "require_explicit_cost_evidence_for_every_trade": (
            policy.require_explicit_cost_evidence_for_every_trade
        ),
        "automatic_promotion": policy.automatic_promotion,
        "canonical_epoch2_write_authority": (
            policy.canonical_epoch2_write_authority
        ),
        "production_authority": policy.production_authority,
        "real_capital": policy.real_capital,
        "schema_version": policy.schema_version,
        "engine_version": policy.engine_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
