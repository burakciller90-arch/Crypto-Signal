"""Authoritative public Binance spot venue-rule snapshots for paper trading.

The public Binance exchangeInfo endpoint is used only for market metadata.
No credentials, account endpoints or real orders are involved. Parsed rules are
stored immutably and can be selected deterministically as-of an already-frozen
paper execution input.

Fee/spread/slippage values in this module are explicit *simulation assumptions*,
not claims about the user's actual Binance account fee tier. REAL_CAPITAL stays 0.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256
from crypto_signal.paper.execution import (
    FrozenExecutionSnapshot,
    build_frozen_execution_snapshot,
)
from crypto_signal.paper.execution_input import FrozenPaperExecutionInput
from crypto_signal.paper.ledger import (
    PaperLedgerConflictError,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    REAL_CAPITAL,
    PaperSymbol,
)

__all__ = [
    "BINANCE_SPOT_EXCHANGE_INFO_URL",
    "DEFAULT_SIMULATED_FEE_RATE",
    "DEFAULT_SIMULATED_SLIPPAGE_RATE",
    "DEFAULT_SIMULATED_SPREAD_RATE",
    "PAPER_SIMULATED_COST_POLICY_VERSION",
    "PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION",
    "REAL_CAPITAL",
    "FrozenBinanceSpotVenueRules",
    "PaperSimulatedCostPolicy",
    "PaperVenueRuleError",
    "PaperVenueRuleStore",
    "build_execution_snapshot_from_venue_rules",
    "default_conservative_simulated_cost_policy",
    "fetch_binance_spot_venue_rules",
    "parse_binance_spot_venue_rules",
]

BINANCE_SPOT_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"
PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION = "paper_binance_spot_venue_rules.v1"
PAPER_SIMULATED_COST_POLICY_VERSION = "paper_simulated_cost_policy.v1"
DEFAULT_SIMULATED_FEE_RATE = Decimal("0.001")
DEFAULT_SIMULATED_SPREAD_RATE = Decimal("0.0005")
DEFAULT_SIMULATED_SLIPPAGE_RATE = Decimal("0.0005")
_AUTHORITATIVE_VENUE_REFERENCE_PREFIX = "binance_spot_exchange_info.v1"


class PaperVenueRuleError(ValueError):
    """Raised when public venue-rule truth cannot be frozen safely."""


@dataclass(frozen=True, slots=True)
class PaperSimulatedCostPolicy:
    version: str
    fee_rate: Decimal
    spread_rate: Decimal
    slippage_rate: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("simulated cost policy version must be non-empty")
        for label, value in (
            ("fee_rate", self.fee_rate),
            ("spread_rate", self.spread_rate),
            ("slippage_rate", self.slippage_rate),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
            if value < Decimal(0) or value > Decimal(1):
                raise ValueError(f"{label} must be between 0 and 1")
        if self.spread_rate + self.slippage_rate >= Decimal(1):
            raise ValueError("combined simulated spread/slippage must remain below 1")


@dataclass(frozen=True, slots=True)
class FrozenBinanceSpotVenueRules:
    snapshot_identity: str
    schema_version: str
    symbol: PaperSymbol
    observed_at_ms: int
    source_endpoint: str
    source_payload_sha256: str
    source_symbol_payload_json: str
    trading_status: str
    base_asset: str
    quote_asset: str
    quantity_step: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional_usdt: Decimal
    tick_size: Decimal
    cost_policy_version: str
    fee_rate: Decimal
    spread_rate: Decimal
    slippage_rate: Decimal
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        _require_sha256(self.snapshot_identity, "snapshot_identity")
        _require_sha256(self.source_payload_sha256, "source_payload_sha256")
        if self.schema_version != PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported venue-rule snapshot schema")
        if self.observed_at_ms < 0:
            raise ValueError("venue-rule observed_at_ms must be non-negative")
        if self.source_endpoint != BINANCE_SPOT_EXCHANGE_INFO_URL:
            raise ValueError("venue-rule source endpoint mismatch")
        if self.trading_status != "TRADING":
            raise ValueError("venue-rule snapshot requires TRADING symbol")
        if not self.base_asset.strip() or self.quote_asset != "USDT":
            raise ValueError("venue-rule snapshot requires non-empty base and USDT quote")
        if not self.source_symbol_payload_json.strip():
            raise ValueError("venue-rule snapshot requires source payload")
        if canonical_sha256(json.loads(self.source_symbol_payload_json)) != (
            self.source_payload_sha256
        ):
            raise ValueError("venue-rule source payload hash mismatch")
        for label, value in (
            ("quantity_step", self.quantity_step),
            ("min_quantity", self.min_quantity),
            ("max_quantity", self.max_quantity),
            ("min_notional_usdt", self.min_notional_usdt),
            ("tick_size", self.tick_size),
            ("fee_rate", self.fee_rate),
            ("spread_rate", self.spread_rate),
            ("slippage_rate", self.slippage_rate),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value.is_nan() or value.is_infinite():
                raise ValueError(f"{label} must be finite")
        if min(
            self.quantity_step,
            self.min_quantity,
            self.max_quantity,
            self.min_notional_usdt,
            self.tick_size,
        ) <= Decimal(0):
            raise ValueError("venue quantity/notional/tick rules must be positive")
        if self.max_quantity < self.min_quantity:
            raise ValueError("venue max quantity cannot be below min quantity")
        if not self.cost_policy_version.strip():
            raise ValueError("cost policy version must be non-empty")
        PaperSimulatedCostPolicy(
            version=self.cost_policy_version,
            fee_rate=self.fee_rate,
            spread_rate=self.spread_rate,
            slippage_rate=self.slippage_rate,
        )
        expected = compute_venue_rule_snapshot_identity(
            schema_version=self.schema_version,
            symbol=self.symbol,
            observed_at_ms=self.observed_at_ms,
            source_endpoint=self.source_endpoint,
            source_payload_sha256=self.source_payload_sha256,
            trading_status=self.trading_status,
            base_asset=self.base_asset,
            quote_asset=self.quote_asset,
            quantity_step=self.quantity_step,
            min_quantity=self.min_quantity,
            max_quantity=self.max_quantity,
            min_notional_usdt=self.min_notional_usdt,
            tick_size=self.tick_size,
            cost_policy_version=self.cost_policy_version,
            fee_rate=self.fee_rate,
            spread_rate=self.spread_rate,
            slippage_rate=self.slippage_rate,
        )
        if self.snapshot_identity != expected:
            raise ValueError("venue-rule snapshot identity mismatch")


class PaperVenueRuleStore:
    """Append-only venue-rule cache, normally sharing the paper SQLite file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_venue_rule_snapshots (
                    snapshot_identity TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    source_payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            for action in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS
                        paper_venue_rule_snapshots_reject_{action.lower()}
                    BEFORE {action} ON paper_venue_rule_snapshots
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'immutable paper venue-rule cache rejects mutation'
                        );
                    END
                    """
                )

    def append(
        self,
        snapshot: FrozenBinanceSpotVenueRules,
    ) -> PaperLedgerWriteDisposition:
        payload_json = canonical_json(snapshot)
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT symbol, observed_at_ms, source_payload_sha256, payload_json
                FROM paper_venue_rule_snapshots
                WHERE snapshot_identity = ?
                """,
                (snapshot.snapshot_identity,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["symbol"]) == snapshot.symbol.value
                    and int(existing["observed_at_ms"]) == snapshot.observed_at_ms
                    and str(existing["source_payload_sha256"])
                    == snapshot.source_payload_sha256
                    and str(existing["payload_json"]) == payload_json
                ):
                    return PaperLedgerWriteDisposition.UNCHANGED
                raise PaperLedgerConflictError(
                    "immutable paper venue-rule snapshot identity conflict"
                )
            connection.execute(
                """
                INSERT INTO paper_venue_rule_snapshots (
                    snapshot_identity,
                    symbol,
                    observed_at_ms,
                    source_payload_sha256,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_identity,
                    snapshot.symbol.value,
                    snapshot.observed_at_ms,
                    snapshot.source_payload_sha256,
                    payload_json,
                ),
            )
        return PaperLedgerWriteDisposition.INSERTED

    def list(
        self,
        *,
        symbol: PaperSymbol | None = None,
    ) -> tuple[FrozenBinanceSpotVenueRules, ...]:
        self.initialize()
        with self._connect() as connection:
            if symbol is None:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM paper_venue_rule_snapshots
                    ORDER BY observed_at_ms ASC, snapshot_identity ASC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM paper_venue_rule_snapshots
                    WHERE symbol = ?
                    ORDER BY observed_at_ms ASC, snapshot_identity ASC
                    """,
                    (symbol.value,),
                ).fetchall()
        return tuple(_deserialize_snapshot(str(row["payload_json"])) for row in rows)

    def latest_at_or_before(
        self,
        *,
        symbol: PaperSymbol,
        observed_at_ms: int,
    ) -> FrozenBinanceSpotVenueRules | None:
        if observed_at_ms < 0:
            raise ValueError("observed_at_ms must be non-negative")
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM paper_venue_rule_snapshots
                WHERE symbol = ? AND observed_at_ms <= ?
                ORDER BY observed_at_ms DESC, snapshot_identity DESC
                LIMIT 1
                """,
                (symbol.value, observed_at_ms),
            ).fetchone()
        return None if row is None else _deserialize_snapshot(str(row["payload_json"]))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection


def default_conservative_simulated_cost_policy() -> PaperSimulatedCostPolicy:
    return PaperSimulatedCostPolicy(
        version=PAPER_SIMULATED_COST_POLICY_VERSION,
        fee_rate=DEFAULT_SIMULATED_FEE_RATE,
        spread_rate=DEFAULT_SIMULATED_SPREAD_RATE,
        slippage_rate=DEFAULT_SIMULATED_SLIPPAGE_RATE,
    )


def compute_venue_rule_snapshot_identity(
    *,
    schema_version: str,
    symbol: PaperSymbol,
    observed_at_ms: int,
    source_endpoint: str,
    source_payload_sha256: str,
    trading_status: str,
    base_asset: str,
    quote_asset: str,
    quantity_step: Decimal,
    min_quantity: Decimal,
    max_quantity: Decimal,
    min_notional_usdt: Decimal,
    tick_size: Decimal,
    cost_policy_version: str,
    fee_rate: Decimal,
    spread_rate: Decimal,
    slippage_rate: Decimal,
) -> str:
    return canonical_sha256(
        {
            "base_asset": base_asset,
            "cost_policy_version": cost_policy_version,
            "fee_rate": fee_rate,
            "max_quantity": max_quantity,
            "min_notional_usdt": min_notional_usdt,
            "min_quantity": min_quantity,
            "observed_at_ms": observed_at_ms,
            "quantity_step": quantity_step,
            "quote_asset": quote_asset,
            "schema_version": schema_version,
            "slippage_rate": slippage_rate,
            "source_endpoint": source_endpoint,
            "source_payload_sha256": source_payload_sha256,
            "spread_rate": spread_rate,
            "symbol": symbol.value,
            "tick_size": tick_size,
            "trading_status": trading_status,
        }
    )


def parse_binance_spot_venue_rules(
    payload: object,
    *,
    symbol: PaperSymbol,
    observed_at_ms: int,
    cost_policy: PaperSimulatedCostPolicy | None = None,
) -> FrozenBinanceSpotVenueRules:
    if observed_at_ms < 0:
        raise PaperVenueRuleError("observed_at_ms must be non-negative")
    root = _mapping(payload, "exchangeInfo response")
    raw_symbols = root.get("symbols")
    if not isinstance(raw_symbols, list):
        raise PaperVenueRuleError("exchangeInfo symbols must be a list")
    matches = [
        item
        for item in raw_symbols
        if isinstance(item, dict) and str(item.get("symbol")) == symbol.value
    ]
    if len(matches) != 1:
        raise PaperVenueRuleError("exchangeInfo must contain exactly one requested symbol")
    raw_symbol = _mapping(matches[0], "exchangeInfo symbol")
    if str(raw_symbol.get("status")) != "TRADING":
        raise PaperVenueRuleError("Binance spot symbol is not TRADING")
    if raw_symbol.get("isSpotTradingAllowed") is not True:
        raise PaperVenueRuleError("Binance symbol is not explicitly spot-trading enabled")
    if str(raw_symbol.get("quoteAsset")) != "USDT":
        raise PaperVenueRuleError("paper venue rule requires USDT quote asset")
    order_types = raw_symbol.get("orderTypes")
    if not isinstance(order_types, list) or "MARKET" not in {
        str(item) for item in order_types
    }:
        raise PaperVenueRuleError("Binance symbol does not advertise MARKET support")

    lot = _single_filter(raw_symbol, "LOT_SIZE")
    price_filter = _single_filter(raw_symbol, "PRICE_FILTER")
    notional_filters = [
        _mapping(item, "notional filter")
        for item in _filters(raw_symbol)
        if str(_mapping(item, "notional filter").get("filterType"))
        in {"MIN_NOTIONAL", "NOTIONAL"}
    ]
    if not notional_filters:
        raise PaperVenueRuleError("Binance symbol has no MIN_NOTIONAL/NOTIONAL filter")

    quantity_step = _positive_decimal(lot, "stepSize", "LOT_SIZE stepSize")
    min_quantity = _positive_decimal(lot, "minQty", "LOT_SIZE minQty")
    max_quantity = _positive_decimal(lot, "maxQty", "LOT_SIZE maxQty")
    tick_size = _positive_decimal(price_filter, "tickSize", "PRICE_FILTER tickSize")
    min_notionals = tuple(
        _positive_decimal(item, "minNotional", "notional minNotional")
        for item in notional_filters
    )
    min_notional = max(min_notionals)
    selected_costs = cost_policy or default_conservative_simulated_cost_policy()
    source_payload_json = canonical_json(raw_symbol)
    source_payload_sha256 = canonical_sha256(raw_symbol)

    identity = compute_venue_rule_snapshot_identity(
        schema_version=PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        source_endpoint=BINANCE_SPOT_EXCHANGE_INFO_URL,
        source_payload_sha256=source_payload_sha256,
        trading_status="TRADING",
        base_asset=str(raw_symbol.get("baseAsset")),
        quote_asset="USDT",
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
        min_notional_usdt=min_notional,
        tick_size=tick_size,
        cost_policy_version=selected_costs.version,
        fee_rate=selected_costs.fee_rate,
        spread_rate=selected_costs.spread_rate,
        slippage_rate=selected_costs.slippage_rate,
    )
    return FrozenBinanceSpotVenueRules(
        snapshot_identity=identity,
        schema_version=PAPER_VENUE_RULE_SNAPSHOT_SCHEMA_VERSION,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        source_endpoint=BINANCE_SPOT_EXCHANGE_INFO_URL,
        source_payload_sha256=source_payload_sha256,
        source_symbol_payload_json=source_payload_json,
        trading_status="TRADING",
        base_asset=str(raw_symbol.get("baseAsset")),
        quote_asset="USDT",
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
        min_notional_usdt=min_notional,
        tick_size=tick_size,
        cost_policy_version=selected_costs.version,
        fee_rate=selected_costs.fee_rate,
        spread_rate=selected_costs.spread_rate,
        slippage_rate=selected_costs.slippage_rate,
        real_capital=REAL_CAPITAL,
    )


async def fetch_binance_spot_venue_rules(
    *,
    symbol: PaperSymbol,
    observed_at_ms: int | None = None,
    client: httpx.AsyncClient | None = None,
    cost_policy: PaperSimulatedCostPolicy | None = None,
) -> FrozenBinanceSpotVenueRules:
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await http_client.get(
            BINANCE_SPOT_EXCHANGE_INFO_URL,
            params={"symbol": symbol.value},
        )
        response.raise_for_status()
        payload = response.json()
        observed = (
            time.time_ns() // 1_000_000
            if observed_at_ms is None
            else observed_at_ms
        )
        return parse_binance_spot_venue_rules(
            payload,
            symbol=symbol,
            observed_at_ms=observed,
            cost_policy=cost_policy,
        )
    finally:
        if owns_client:
            await http_client.aclose()


def build_execution_snapshot_from_venue_rules(
    *,
    execution_input: FrozenPaperExecutionInput,
    venue_rules: FrozenBinanceSpotVenueRules,
) -> FrozenExecutionSnapshot:
    if execution_input.real_capital != REAL_CAPITAL or venue_rules.real_capital != REAL_CAPITAL:
        raise PaperVenueRuleError("REAL_CAPITAL must remain 0")
    if execution_input.symbol is not venue_rules.symbol:
        raise PaperVenueRuleError("venue rules/execution input symbol mismatch")
    if venue_rules.observed_at_ms > execution_input.observed_at_ms:
        raise PaperVenueRuleError(
            "venue rules must be observed no later than frozen execution input"
        )
    venue_reference = (
        f"{_AUTHORITATIVE_VENUE_REFERENCE_PREFIX}"
        f"|rules:{venue_rules.snapshot_identity}"
        f"|cost:{venue_rules.cost_policy_version}"
        f"|{execution_input.venue_reference}"
    )
    return build_frozen_execution_snapshot(
        venue_reference=venue_reference,
        symbol=venue_rules.symbol,
        quantity_step=venue_rules.quantity_step,
        min_quantity=venue_rules.min_quantity,
        min_notional_usdt=venue_rules.min_notional_usdt,
        fee_rate=venue_rules.fee_rate,
        spread_rate=venue_rules.spread_rate,
        slippage_rate=venue_rules.slippage_rate,
        policy_version=PAPER_EXECUTION_POLICY_VERSION,
    )


def _deserialize_snapshot(payload_json: str) -> FrozenBinanceSpotVenueRules:
    raw = _mapping(json.loads(payload_json), "stored venue-rule snapshot")
    return FrozenBinanceSpotVenueRules(
        snapshot_identity=str(raw["snapshot_identity"]),
        schema_version=str(raw["schema_version"]),
        symbol=PaperSymbol(str(raw["symbol"])),
        observed_at_ms=int(raw["observed_at_ms"]),
        source_endpoint=str(raw["source_endpoint"]),
        source_payload_sha256=str(raw["source_payload_sha256"]),
        source_symbol_payload_json=str(raw["source_symbol_payload_json"]),
        trading_status=str(raw["trading_status"]),
        base_asset=str(raw["base_asset"]),
        quote_asset=str(raw["quote_asset"]),
        quantity_step=Decimal(str(raw["quantity_step"])),
        min_quantity=Decimal(str(raw["min_quantity"])),
        max_quantity=Decimal(str(raw["max_quantity"])),
        min_notional_usdt=Decimal(str(raw["min_notional_usdt"])),
        tick_size=Decimal(str(raw["tick_size"])),
        cost_policy_version=str(raw["cost_policy_version"]),
        fee_rate=Decimal(str(raw["fee_rate"])),
        spread_rate=Decimal(str(raw["spread_rate"])),
        slippage_rate=Decimal(str(raw["slippage_rate"])),
        real_capital=int(raw["real_capital"]),
    )


def _filters(raw_symbol: dict[str, Any]) -> list[object]:
    filters = raw_symbol.get("filters")
    if not isinstance(filters, list):
        raise PaperVenueRuleError("Binance symbol filters must be a list")
    return filters


def _single_filter(raw_symbol: dict[str, Any], filter_type: str) -> dict[str, Any]:
    matches = [
        _mapping(item, f"{filter_type} filter")
        for item in _filters(raw_symbol)
        if str(_mapping(item, f"{filter_type} filter").get("filterType"))
        == filter_type
    ]
    if len(matches) != 1:
        raise PaperVenueRuleError(f"Binance symbol requires exactly one {filter_type}")
    return matches[0]


def _positive_decimal(
    mapping: dict[str, Any],
    key: str,
    label: str,
) -> Decimal:
    if key not in mapping:
        raise PaperVenueRuleError(f"{label} is missing")
    try:
        value = Decimal(str(mapping[key]))
    except Exception as exc:
        raise PaperVenueRuleError(f"{label} is not a Decimal") from exc
    if value.is_nan() or value.is_infinite() or value <= Decimal(0):
        raise PaperVenueRuleError(f"{label} must be finite and positive")
    return value


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PaperVenueRuleError(f"{label} must be an object")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
