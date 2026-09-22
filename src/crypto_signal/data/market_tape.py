from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    DerivativesObservation,
)
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    OrderBookSnapshot,
    PublicTradeObservation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256


class MarketTapeConflictError(ValueError):
    """Raised when an immutable tape identity maps to conflicting content."""


class MarketTapeWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class MarketTapeCounts:
    orderbooks: int
    trades: int
    derivatives: int

    @property
    def total(self) -> int:
        return self.orderbooks + self.trades + self.derivatives


class MarketTapeStore:
    """Append-only SQLite persistence for normalized market-intelligence evidence."""

    SCHEMA_VERSION = "market-tape-schema-v1/1"

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO market_tape_meta(key, value)
                VALUES ('schema_version', ?)
                """,
                (self.SCHEMA_VERSION,),
            )
            row = connection.execute(
                """
                SELECT value
                FROM market_tape_meta
                WHERE key = 'schema_version'
                """
            ).fetchone()
            if row is None or str(row["value"]) != self.SCHEMA_VERSION:
                raise MarketTapeConflictError(
                    "market tape schema version mismatch"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_orderbooks (
                    snapshot_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    update_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_orderbooks_context
                ON market_tape_orderbooks(
                    exchange, market_type, symbol, event_at_ms, sequence
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_trades (
                    trade_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    exec_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    aggressor_side TEXT NOT NULL,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_trades_context
                ON market_tape_trades(
                    exchange, market_type, symbol, event_at_ms, sequence
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_market_tape_trade_exec
                ON market_tape_trades(exchange, market_type, symbol, exec_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_derivatives (
                    observation_identity TEXT PRIMARY KEY,
                    semantic_identity TEXT NOT NULL UNIQUE,
                    exchange TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_derivatives_context
                ON market_tape_derivatives(
                    exchange, instrument_type, symbol, event_at_ms
                )
                """
            )

    def append_orderbook(
        self,
        snapshot: OrderBookSnapshot,
    ) -> MarketTapeWriteDisposition:
        duplicate = self._find_by_fields(
            table="market_tape_orderbooks",
            fields={
                "exchange": snapshot.exchange.value,
                "market_type": snapshot.market_type.value,
                "symbol": snapshot.symbol,
                "update_id": snapshot.update_id,
                "sequence": snapshot.sequence,
            },
        )
        if duplicate is not None:
            existing = _orderbook_from_payload(str(duplicate["payload_json"]))
            if _orderbook_market_truth(existing) != _orderbook_market_truth(snapshot):
                raise MarketTapeConflictError(
                    "orderbook exchange update identity conflicts with market truth"
                )
            return MarketTapeWriteDisposition.UNCHANGED
        return self._append(
            table="market_tape_orderbooks",
            identity_column="snapshot_identity",
            identity=snapshot.snapshot_identity,
            payload_json=canonical_json(snapshot),
            columns=(
                "snapshot_identity",
                "exchange",
                "market_type",
                "symbol",
                "event_at_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "update_id",
                "sequence",
                "source",
                "adapter_version",
                "payload_json",
            ),
            values=(
                snapshot.snapshot_identity,
                snapshot.exchange.value,
                snapshot.market_type.value,
                snapshot.symbol,
                snapshot.event_at_ms,
                snapshot.source_timestamp_ms,
                snapshot.ingested_at_ms,
                snapshot.update_id,
                snapshot.sequence,
                snapshot.source.value,
                snapshot.adapter_version,
                canonical_json(snapshot),
            ),
        )

    def append_trade(
        self,
        trade: PublicTradeObservation,
    ) -> MarketTapeWriteDisposition:
        duplicate = self._find_by_fields(
            table="market_tape_trades",
            fields={
                "exchange": trade.exchange.value,
                "market_type": trade.market_type.value,
                "symbol": trade.symbol,
                "exec_id": trade.exec_id,
            },
        )
        if duplicate is not None:
            existing = _trade_from_payload(str(duplicate["payload_json"]))
            if _trade_market_truth(existing) != _trade_market_truth(trade):
                raise MarketTapeConflictError(
                    "public trade exec identity conflicts with market truth"
                )
            return MarketTapeWriteDisposition.UNCHANGED
        return self._append(
            table="market_tape_trades",
            identity_column="trade_identity",
            identity=trade.trade_identity,
            payload_json=canonical_json(trade),
            columns=(
                "trade_identity",
                "exchange",
                "market_type",
                "symbol",
                "event_at_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "exec_id",
                "sequence",
                "aggressor_side",
                "source",
                "adapter_version",
                "payload_json",
            ),
            values=(
                trade.trade_identity,
                trade.exchange.value,
                trade.market_type.value,
                trade.symbol,
                trade.event_at_ms,
                trade.source_timestamp_ms,
                trade.ingested_at_ms,
                trade.exec_id,
                trade.sequence,
                trade.aggressor_side.value,
                trade.source.value,
                trade.adapter_version,
                canonical_json(trade),
            ),
        )

    def append_derivatives(
        self,
        observation: DerivativesObservation,
    ) -> MarketTapeWriteDisposition:
        semantic_identity = _derivatives_semantic_identity(observation)
        duplicate = self._find_by_fields(
            table="market_tape_derivatives",
            fields={"semantic_identity": semantic_identity},
        )
        if duplicate is not None:
            return MarketTapeWriteDisposition.UNCHANGED
        return self._append(
            table="market_tape_derivatives",
            identity_column="observation_identity",
            identity=observation.observation_identity,
            payload_json=canonical_json(observation),
            columns=(
                "observation_identity",
                "semantic_identity",
                "exchange",
                "instrument_type",
                "symbol",
                "event_at_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "source",
                "adapter_version",
                "payload_json",
            ),
            values=(
                observation.observation_identity,
                semantic_identity,
                observation.exchange.value,
                observation.instrument_type.value,
                observation.symbol,
                observation.event_at_ms,
                observation.source_timestamp_ms,
                observation.ingested_at_ms,
                observation.source.value,
                observation.adapter_version,
                canonical_json(observation),
            ),
        )

    def append_microstructure_snapshot(
        self,
        snapshot: OrderBookSnapshot,
        trades: tuple[PublicTradeObservation, ...],
    ) -> tuple[MarketTapeWriteDisposition, tuple[MarketTapeWriteDisposition, ...]]:
        orderbook_result = self.append_orderbook(snapshot)
        trade_results = tuple(self.append_trade(trade) for trade in trades)
        return orderbook_result, trade_results

    def counts(self) -> MarketTapeCounts:
        self.initialize()
        with self._connect() as connection:
            return MarketTapeCounts(
                orderbooks=self._count_table(connection, "market_tape_orderbooks"),
                trades=self._count_table(connection, "market_tape_trades"),
                derivatives=self._count_table(
                    connection,
                    "market_tape_derivatives",
                ),
            )

    def latest_event_at_ms(self) -> int | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(event_at_ms) AS latest_event_at_ms
                FROM (
                    SELECT event_at_ms FROM market_tape_orderbooks
                    UNION ALL
                    SELECT event_at_ms FROM market_tape_trades
                    UNION ALL
                    SELECT event_at_ms FROM market_tape_derivatives
                )
                """
            ).fetchone()
        if row is None or row["latest_event_at_ms"] is None:
            return None
        return int(row["latest_event_at_ms"])

    def recent_orderbooks(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        limit: int = 100,
    ) -> tuple[OrderBookSnapshot, ...]:
        rows = self._recent_rows(
            table="market_tape_orderbooks",
            exchange=exchange.value,
            symbol=symbol,
            limit=limit,
            market_type=market_type.value,
        )
        return tuple(_orderbook_from_payload(row["payload_json"]) for row in rows)

    def recent_trades(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        limit: int = 1000,
    ) -> tuple[PublicTradeObservation, ...]:
        rows = self._recent_rows(
            table="market_tape_trades",
            exchange=exchange.value,
            symbol=symbol,
            limit=limit,
            market_type=market_type.value,
        )
        return tuple(_trade_from_payload(row["payload_json"]) for row in rows)

    def recent_derivatives(
        self,
        *,
        exchange: Exchange,
        instrument_type: DerivativesInstrumentType,
        symbol: str,
        limit: int = 1000,
    ) -> tuple[DerivativesObservation, ...]:
        rows = self._recent_rows(
            table="market_tape_derivatives",
            exchange=exchange.value,
            symbol=symbol,
            limit=limit,
            instrument_type=instrument_type.value,
        )
        return tuple(_derivatives_from_payload(row["payload_json"]) for row in rows)

    def quick_check(self) -> bool:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]) == "ok"

    def _append(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        payload_json: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
    ) -> MarketTapeWriteDisposition:
        self.initialize()
        placeholders = ",".join("?" for _ in columns)
        column_sql = ",".join(columns)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"""
                SELECT payload_json
                FROM {table}
                WHERE {identity_column} = ?
                """,
                (identity,),
            ).fetchone()
            if row is not None:
                if str(row["payload_json"]) != payload_json:
                    raise MarketTapeConflictError(
                        f"immutable market tape conflict: {identity}"
                    )
                return MarketTapeWriteDisposition.UNCHANGED
            connection.execute(
                f"""
                INSERT INTO {table} ({column_sql})
                VALUES ({placeholders})
                """,
                values,
            )
            return MarketTapeWriteDisposition.INSERTED

    def _find_by_fields(
        self,
        *,
        table: str,
        fields: dict[str, object],
    ) -> sqlite3.Row | None:
        if not fields:
            raise ValueError("market tape lookup fields cannot be empty")
        self.initialize()
        clauses = [f"{field} = ?" for field in fields]
        with self._connect() as connection:
            return connection.execute(
                f"""
                SELECT *
                FROM {table}
                WHERE {" AND ".join(clauses)}
                LIMIT 1
                """,
                tuple(fields.values()),
            ).fetchone()

    def _recent_rows(
        self,
        *,
        table: str,
        exchange: str,
        symbol: str,
        limit: int,
        market_type: str | None = None,
        instrument_type: str | None = None,
    ) -> tuple[sqlite3.Row, ...]:
        if limit <= 0:
            raise ValueError("market tape read limit must be positive")
        self.initialize()
        clauses = ["exchange = ?", "symbol = ?"]
        params: list[object] = [exchange, symbol]
        if market_type is not None:
            clauses.append("market_type = ?")
            params.append(market_type)
        if instrument_type is not None:
            clauses.append("instrument_type = ?")
            params.append(instrument_type)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM {table}
                WHERE {" AND ".join(clauses)}
                ORDER BY event_at_ms DESC, rowid DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return tuple(reversed(rows))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _count_table(connection: sqlite3.Connection, table: str) -> int:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM {table}"
        ).fetchone()
        return 0 if row is None else int(row["count"])


def _orderbook_market_truth(snapshot: OrderBookSnapshot) -> dict[str, object]:
    return {
        "exchange": snapshot.exchange,
        "market_type": snapshot.market_type,
        "symbol": snapshot.symbol,
        "event_at_ms": snapshot.event_at_ms,
        "update_id": snapshot.update_id,
        "sequence": snapshot.sequence,
        "bids": snapshot.bids,
        "asks": snapshot.asks,
    }


def _trade_market_truth(trade: PublicTradeObservation) -> dict[str, object]:
    return {
        "exchange": trade.exchange,
        "market_type": trade.market_type,
        "symbol": trade.symbol,
        "exec_id": trade.exec_id,
        "sequence": trade.sequence,
        "aggressor_side": trade.aggressor_side,
        "price": trade.price,
        "size": trade.size,
        "event_at_ms": trade.event_at_ms,
        "is_block_trade": trade.is_block_trade,
        "is_rpi_trade": trade.is_rpi_trade,
    }


def _derivatives_semantic_identity(
    observation: DerivativesObservation,
) -> str:
    return canonical_sha256(
        {
            "exchange": observation.exchange,
            "instrument_type": observation.instrument_type,
            "symbol": observation.symbol,
            "event_at_ms": observation.event_at_ms,
            "funding_rate": observation.funding_rate,
            "open_interest": observation.open_interest,
            "mark_price": observation.mark_price,
            "index_price": observation.index_price,
            "funding_interval_hours": observation.funding_interval_hours,
        }
    )


def _orderbook_from_payload(payload_json: str) -> OrderBookSnapshot:
    payload = _json_object(payload_json)
    return OrderBookSnapshot(
        snapshot_identity=str(payload["snapshot_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        market_type=MarketType(str(payload["market_type"])),
        symbol=str(payload["symbol"]),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        response_time_ms=int(payload["response_time_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        update_id=int(payload["update_id"]),
        sequence=int(payload["sequence"]),
        bids=tuple(_level_from_payload(item) for item in _json_list(payload["bids"])),
        asks=tuple(_level_from_payload(item) for item in _json_list(payload["asks"])),
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _trade_from_payload(payload_json: str) -> PublicTradeObservation:
    payload = _json_object(payload_json)
    return PublicTradeObservation(
        trade_identity=str(payload["trade_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        market_type=MarketType(str(payload["market_type"])),
        symbol=str(payload["symbol"]),
        exec_id=str(payload["exec_id"]),
        sequence=int(payload["sequence"]),
        aggressor_side=AggressorSide(str(payload["aggressor_side"])),
        price=Decimal(str(payload["price"])),
        size=Decimal(str(payload["size"])),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        is_block_trade=bool(payload["is_block_trade"]),
        is_rpi_trade=bool(payload["is_rpi_trade"]),
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _derivatives_from_payload(payload_json: str) -> DerivativesObservation:
    payload = _json_object(payload_json)
    return DerivativesObservation(
        observation_identity=str(payload["observation_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        instrument_type=DerivativesInstrumentType(str(payload["instrument_type"])),
        symbol=str(payload["symbol"]),
        event_at_ms=int(payload["event_at_ms"]),
        funding_rate=_decimal_or_none(payload.get("funding_rate")),
        open_interest=_decimal_or_none(payload.get("open_interest")),
        mark_price=_decimal_or_none(payload.get("mark_price")),
        index_price=_decimal_or_none(payload.get("index_price")),
        funding_interval_hours=(
            None
            if payload.get("funding_interval_hours") is None
            else int(payload["funding_interval_hours"])
        ),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        adapter_version=str(payload["adapter_version"]),
    )


def _level_from_payload(value: object) -> OrderBookLevel:
    payload = _json_object(value)
    return OrderBookLevel(
        price=Decimal(str(payload["price"])),
        size=Decimal(str(payload["size"])),
    )


def _decimal_or_none(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _json_object(value: str | object) -> dict[str, Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise MarketTapeConflictError("market tape payload must be an object")
    return parsed


def _json_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise MarketTapeConflictError("market tape payload field must be a list")
    return value
