from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    DerivativesObservation,
)
from crypto_signal.data.liquidations import (
    LiquidatedPositionSide,
    LiquidationFeedCoverage,
    LiquidationObservation,
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
    liquidations: int
    liquidation_coverage: int

    @property
    def total(self) -> int:
        return (
            self.orderbooks
            + self.trades
            + self.derivatives
            + self.liquidations
            + self.liquidation_coverage
        )


@dataclass(frozen=True, slots=True)
class MarketTapeLiquidationReplay:
    coverage: LiquidationFeedCoverage
    events: tuple[LiquidationObservation, ...]
    as_of_ms: int


class MarketTapeStore:
    """Append-only SQLite persistence for normalized market-intelligence evidence."""

    SCHEMA_VERSION = "market-tape-schema-v1/2"
    LEGACY_SCHEMA_VERSIONS = frozenset({"market-tape-schema-v1/1"})

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
            row = connection.execute(
                """
                SELECT value
                FROM market_tape_meta
                WHERE key = 'schema_version'
                """
            ).fetchone()
            if row is None:
                previous_schema_version = self.SCHEMA_VERSION
                connection.execute(
                    """
                    INSERT INTO market_tape_meta(key, value)
                    VALUES ('schema_version', ?)
                    """,
                    (self.SCHEMA_VERSION,),
                )
            else:
                previous_schema_version = str(row["value"])
                if (
                    previous_schema_version != self.SCHEMA_VERSION
                    and previous_schema_version not in self.LEGACY_SCHEMA_VERSIONS
                ):
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

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_liquidations (
                    liquidation_identity TEXT PRIMARY KEY,
                    provider_identity TEXT NOT NULL UNIQUE,
                    exchange TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    source_row_index INTEGER NOT NULL,
                    liquidated_position_side TEXT NOT NULL,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_liquidations_context
                ON market_tape_liquidations(
                    exchange, instrument_type, symbol, event_at_ms
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_liquidation_coverage (
                    coverage_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    coverage_start_ms INTEGER NOT NULL,
                    coverage_end_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_liquidation_coverage_context
                ON market_tape_liquidation_coverage(
                    exchange,
                    instrument_type,
                    symbol,
                    coverage_end_ms,
                    coverage_start_ms
                )
                """
            )
            if previous_schema_version != self.SCHEMA_VERSION:
                connection.execute(
                    """
                    UPDATE market_tape_meta
                    SET value = ?
                    WHERE key = 'schema_version'
                    """,
                    (self.SCHEMA_VERSION,),
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

    def orderbook_identity_for_provider_update(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        update_id: int,
        sequence: int,
    ) -> str | None:
        row = self._find_by_fields(
            table="market_tape_orderbooks",
            fields={
                "exchange": exchange.value,
                "market_type": market_type.value,
                "symbol": symbol,
                "update_id": update_id,
                "sequence": sequence,
            },
        )
        return None if row is None else str(row["snapshot_identity"])

    def trade_identity_for_exec_id(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        exec_id: str,
    ) -> str | None:
        row = self._find_by_fields(
            table="market_tape_trades",
            fields={
                "exchange": exchange.value,
                "market_type": market_type.value,
                "symbol": symbol,
                "exec_id": exec_id,
            },
        )
        return None if row is None else str(row["trade_identity"])

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

    def derivatives_identity_for_semantic_observation(
        self,
        observation: DerivativesObservation,
    ) -> str | None:
        row = self._find_by_fields(
            table="market_tape_derivatives",
            fields={
                "semantic_identity": _derivatives_semantic_identity(
                    observation
                )
            },
        )
        return None if row is None else str(row["observation_identity"])

    def append_liquidation(
        self,
        observation: LiquidationObservation,
    ) -> MarketTapeWriteDisposition:
        provider_identity = _liquidation_provider_identity(observation)
        duplicate = self._find_by_fields(
            table="market_tape_liquidations",
            fields={"provider_identity": provider_identity},
        )
        if duplicate is not None:
            existing = _liquidation_from_payload(str(duplicate["payload_json"]))
            if _liquidation_market_truth(existing) != _liquidation_market_truth(
                observation
            ):
                raise MarketTapeConflictError(
                    "liquidation provider identity conflicts with market truth"
                )
            return MarketTapeWriteDisposition.UNCHANGED
        return self._append(
            table="market_tape_liquidations",
            identity_column="liquidation_identity",
            identity=observation.liquidation_identity,
            payload_json=canonical_json(observation),
            columns=(
                "liquidation_identity",
                "provider_identity",
                "exchange",
                "instrument_type",
                "symbol",
                "event_at_ms",
                "source_timestamp_ms",
                "ingested_at_ms",
                "source_row_index",
                "liquidated_position_side",
                "source",
                "adapter_version",
                "payload_json",
            ),
            values=(
                observation.liquidation_identity,
                provider_identity,
                observation.exchange.value,
                observation.instrument_type.value,
                observation.symbol,
                observation.event_at_ms,
                observation.source_timestamp_ms,
                observation.ingested_at_ms,
                observation.source_row_index,
                observation.liquidated_position_side.value,
                observation.source.value,
                observation.adapter_version,
                canonical_json(observation),
            ),
        )

    def append_liquidation_coverage(
        self,
        coverage: LiquidationFeedCoverage,
    ) -> MarketTapeWriteDisposition:
        duplicate = self._find_by_fields(
            table="market_tape_liquidation_coverage",
            fields={"coverage_identity": coverage.coverage_identity},
        )
        if duplicate is not None:
            existing = _liquidation_coverage_from_payload(
                str(duplicate["payload_json"])
            )
            if _liquidation_coverage_truth(existing) != _liquidation_coverage_truth(
                coverage
            ):
                raise MarketTapeConflictError(
                    "liquidation coverage identity conflicts with coverage truth"
                )
            return MarketTapeWriteDisposition.UNCHANGED
        return self._append(
            table="market_tape_liquidation_coverage",
            identity_column="coverage_identity",
            identity=coverage.coverage_identity,
            payload_json=canonical_json(coverage),
            columns=(
                "coverage_identity",
                "exchange",
                "instrument_type",
                "symbol",
                "coverage_start_ms",
                "coverage_end_ms",
                "observed_at_ms",
                "source",
                "adapter_version",
                "payload_json",
            ),
            values=(
                coverage.coverage_identity,
                coverage.exchange.value,
                coverage.instrument_type.value,
                coverage.symbol,
                coverage.coverage_start_ms,
                coverage.coverage_end_ms,
                coverage.observed_at_ms,
                coverage.source.value,
                coverage.adapter_version,
                canonical_json(coverage),
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
                liquidations=self._count_table(
                    connection,
                    "market_tape_liquidations",
                ),
                liquidation_coverage=self._count_table(
                    connection,
                    "market_tape_liquidation_coverage",
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
                    UNION ALL
                    SELECT event_at_ms FROM market_tape_liquidations
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

    def recent_liquidations(
        self,
        *,
        exchange: Exchange,
        instrument_type: DerivativesInstrumentType,
        symbol: str,
        limit: int = 1000,
    ) -> tuple[LiquidationObservation, ...]:
        rows = self._recent_rows(
            table="market_tape_liquidations",
            exchange=exchange.value,
            symbol=symbol,
            limit=limit,
            instrument_type=instrument_type.value,
        )
        return tuple(_liquidation_from_payload(row["payload_json"]) for row in rows)

    def recent_liquidation_coverage(
        self,
        *,
        exchange: Exchange,
        instrument_type: DerivativesInstrumentType,
        symbol: str,
        limit: int = 100,
    ) -> tuple[LiquidationFeedCoverage, ...]:
        if limit <= 0:
            raise ValueError("market tape read limit must be positive")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM market_tape_liquidation_coverage
                WHERE exchange = ?
                  AND instrument_type = ?
                  AND symbol = ?
                ORDER BY coverage_end_ms DESC, coverage_start_ms DESC, rowid DESC
                LIMIT ?
                """,
                (exchange.value, instrument_type.value, symbol, limit),
            ).fetchall()
        return tuple(
            reversed(
                tuple(
                    _liquidation_coverage_from_payload(row["payload_json"])
                    for row in rows
                )
            )
        )

    def liquidation_replay(
        self,
        *,
        coverage_identity: str,
        as_of_ms: int,
    ) -> MarketTapeLiquidationReplay:
        if as_of_ms < 0:
            raise ValueError("liquidation replay as_of_ms must be non-negative")
        self.initialize()
        with self._connect() as connection:
            coverage_row = connection.execute(
                """
                SELECT payload_json
                FROM market_tape_liquidation_coverage
                WHERE coverage_identity = ?
                """,
                (coverage_identity,),
            ).fetchone()
            if coverage_row is None:
                raise MarketTapeConflictError(
                    "liquidation replay coverage is not persisted"
                )
            coverage = _liquidation_coverage_from_payload(
                str(coverage_row["payload_json"])
            )
            if coverage.observed_at_ms > as_of_ms:
                raise MarketTapeConflictError(
                    "liquidation replay coverage is future evidence"
                )
            rows = connection.execute(
                """
                SELECT payload_json
                FROM market_tape_liquidations
                WHERE exchange = ?
                  AND instrument_type = ?
                  AND symbol = ?
                  AND event_at_ms >= ?
                  AND event_at_ms <= ?
                  AND event_at_ms <= ?
                  AND source_timestamp_ms <= ?
                  AND ingested_at_ms <= ?
                ORDER BY
                    event_at_ms ASC,
                    source_timestamp_ms ASC,
                    source_row_index ASC,
                    liquidation_identity ASC
                """,
                (
                    coverage.exchange.value,
                    coverage.instrument_type.value,
                    coverage.symbol,
                    coverage.coverage_start_ms,
                    coverage.coverage_end_ms,
                    as_of_ms,
                    as_of_ms,
                    as_of_ms,
                ),
            ).fetchall()
        return MarketTapeLiquidationReplay(
            coverage=coverage,
            events=tuple(
                _liquidation_from_payload(row["payload_json"])
                for row in rows
            ),
            as_of_ms=as_of_ms,
        )

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
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    f"""
                    SELECT *
                    FROM {table}
                    WHERE {" AND ".join(clauses)}
                    LIMIT 1
                    """,
                    tuple(fields.values()),
                ).fetchone(),
            )

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


def _liquidation_provider_identity(
    observation: LiquidationObservation,
) -> str:
    return canonical_sha256(
        {
            "exchange": observation.exchange,
            "instrument_type": observation.instrument_type,
            "symbol": observation.symbol,
            "event_at_ms": observation.event_at_ms,
            "source_timestamp_ms": observation.source_timestamp_ms,
            "source_row_index": observation.source_row_index,
        }
    )


def _liquidation_market_truth(
    observation: LiquidationObservation,
) -> dict[str, object]:
    return {
        "exchange": observation.exchange,
        "instrument_type": observation.instrument_type,
        "symbol": observation.symbol,
        "liquidated_position_side": observation.liquidated_position_side,
        "size": observation.size,
        "bankruptcy_price": observation.bankruptcy_price,
        "event_at_ms": observation.event_at_ms,
        "source_timestamp_ms": observation.source_timestamp_ms,
        "source_row_index": observation.source_row_index,
    }


def _liquidation_coverage_truth(
    coverage: LiquidationFeedCoverage,
) -> dict[str, object]:
    return {
        "exchange": coverage.exchange,
        "instrument_type": coverage.instrument_type,
        "symbol": coverage.symbol,
        "coverage_start_ms": coverage.coverage_start_ms,
        "coverage_end_ms": coverage.coverage_end_ms,
        "source": coverage.source,
        "adapter_version": coverage.adapter_version,
    }


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


def _liquidation_from_payload(payload_json: str) -> LiquidationObservation:
    payload = _json_object(payload_json)
    return LiquidationObservation(
        liquidation_identity=str(payload["liquidation_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        instrument_type=DerivativesInstrumentType(str(payload["instrument_type"])),
        symbol=str(payload["symbol"]),
        liquidated_position_side=LiquidatedPositionSide(
            str(payload["liquidated_position_side"])
        ),
        size=Decimal(str(payload["size"])),
        bankruptcy_price=Decimal(str(payload["bankruptcy_price"])),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        source_row_index=int(payload["source_row_index"]),
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _liquidation_coverage_from_payload(
    payload_json: str,
) -> LiquidationFeedCoverage:
    payload = _json_object(payload_json)
    return LiquidationFeedCoverage(
        coverage_identity=str(payload["coverage_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        instrument_type=DerivativesInstrumentType(str(payload["instrument_type"])),
        symbol=str(payload["symbol"]),
        coverage_start_ms=int(payload["coverage_start_ms"]),
        coverage_end_ms=int(payload["coverage_end_ms"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        source=DataSource(str(payload["source"])),
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
