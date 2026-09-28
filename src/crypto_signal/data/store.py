from __future__ import annotations

import sqlite3
from contextlib import closing
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256


class CandleConflictError(ValueError):
    """Raised when finalized candle truth conflicts with new finalized data."""


class WriteDisposition(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    IGNORED_STALE = "ignored_stale"
    IGNORED_FINALIZED = "ignored_finalized"


class CandleStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    exchange TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time_ms INTEGER NOT NULL,
                    close_time_ms INTEGER NOT NULL,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    quote_volume TEXT,
                    trade_count INTEGER,
                    is_closed INTEGER NOT NULL CHECK (is_closed IN (0, 1)),
                    source TEXT NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    adapter_version TEXT NOT NULL,
                    PRIMARY KEY (exchange, market_type, symbol, timeframe, open_time_ms)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_candles_lookup
                ON candles(exchange, market_type, symbol, timeframe, open_time_ms)
                """
            )

    def upsert(self, candle: Candle) -> WriteDisposition:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._get_one(connection, candle)
            if existing is None:
                self._write(connection, candle)
                return WriteDisposition.INSERTED

            if existing.is_closed:
                if not candle.is_closed:
                    return WriteDisposition.IGNORED_FINALIZED
                if self._market_equal(existing, candle):
                    return WriteDisposition.UNCHANGED
                raise CandleConflictError(f"finalized candle conflict: {candle.identity!r}")

            if not candle.is_closed and candle.source_timestamp_ms < existing.source_timestamp_ms:
                return WriteDisposition.IGNORED_STALE
            if self._market_equal(existing, candle) and existing.is_closed == candle.is_closed:
                return WriteDisposition.UNCHANGED

            self._write(connection, candle)
            return WriteDisposition.UPDATED
    def list_candles(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        timeframe: str,
    ) -> tuple[Candle, ...]:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT * FROM candles
                WHERE exchange = ? AND market_type = ? AND symbol = ? AND timeframe = ?
                ORDER BY open_time_ms ASC
                """,
                (exchange.value, market_type.value, symbol, timeframe),
            ).fetchall()
        return tuple(self._row_to_candle(row) for row in rows)

    def list_candles_read_only(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        timeframe: str,
    ) -> tuple[Candle, ...]:
        """Read persisted candles without initializing or mutating the cache."""
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            rows = connection.execute(
                """
                SELECT * FROM candles
                WHERE exchange = ? AND market_type = ? AND symbol = ? AND timeframe = ?
                ORDER BY open_time_ms ASC
                """,
                (exchange.value, market_type.value, symbol, timeframe),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._row_to_candle(row) for row in rows)

    def normalized_identity_for_key(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        timeframe: str,
        open_time_ms: int,
    ) -> str | None:
        if not self.path.is_file():
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM candles
                WHERE exchange = ? AND market_type = ? AND symbol = ?
                  AND timeframe = ? AND open_time_ms = ?
                """,
                (
                    exchange.value,
                    market_type.value,
                    symbol,
                    timeframe,
                    open_time_ms,
                ),
            ).fetchone()
        if row is None:
            return None
        return canonical_sha256(
            _candle_normalized_payload(self._row_to_candle(row))
        )

    def count(self) -> int:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM candles").fetchone()
        if row is None:
            return 0
        return int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _get_one(self, connection: sqlite3.Connection, candle: Candle) -> Candle | None:
        row = connection.execute(
            """
            SELECT * FROM candles
            WHERE exchange = ? AND market_type = ? AND symbol = ?
              AND timeframe = ? AND open_time_ms = ?
            """,
            candle.identity,
        ).fetchone()
        return None if row is None else self._row_to_candle(row)
    def _write(self, connection: sqlite3.Connection, candle: Candle) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO candles VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                candle.exchange.value,
                candle.market_type.value,
                candle.symbol,
                candle.timeframe,
                candle.open_time_ms,
                candle.close_time_ms,
                str(candle.open),
                str(candle.high),
                str(candle.low),
                str(candle.close),
                str(candle.volume),
                None if candle.quote_volume is None else str(candle.quote_volume),
                candle.trade_count,
                int(candle.is_closed),
                candle.source.value,
                candle.source_timestamp_ms,
                candle.ingested_at_ms,
                candle.adapter_version,
            ),
        )

    @staticmethod
    def _market_equal(left: Candle, right: Candle) -> bool:
        return (
            left.close_time_ms == right.close_time_ms
            and left.open == right.open
            and left.high == right.high
            and left.low == right.low
            and left.close == right.close
            and left.volume == right.volume
            and left.quote_volume == right.quote_volume
            and left.trade_count == right.trade_count
        )
    @staticmethod
    def _row_to_candle(row: sqlite3.Row) -> Candle:
        from decimal import Decimal

        return Candle(
            exchange=Exchange(row["exchange"]),
            market_type=MarketType(row["market_type"]),
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
            open_time_ms=int(row["open_time_ms"]),
            close_time_ms=int(row["close_time_ms"]),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            quote_volume=None
            if row["quote_volume"] is None
            else Decimal(str(row["quote_volume"])),
            trade_count=None if row["trade_count"] is None else int(row["trade_count"]),
            is_closed=bool(row["is_closed"]),
            source=DataSource(row["source"]),
            source_timestamp_ms=int(row["source_timestamp_ms"]),
            ingested_at_ms=int(row["ingested_at_ms"]),
            adapter_version=str(row["adapter_version"]),
        )



def _candle_normalized_payload(candle: Candle) -> dict[str, object]:
    return {
        "exchange": candle.exchange.value,
        "market_type": candle.market_type.value,
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open_time_ms": candle.open_time_ms,
        "close_time_ms": candle.close_time_ms,
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
        "quote_volume": (
            None
            if candle.quote_volume is None
            else str(candle.quote_volume)
        ),
        "trade_count": candle.trade_count,
        "is_closed": candle.is_closed,
        "source": candle.source.value,
        "source_timestamp_ms": candle.source_timestamp_ms,
        "ingested_at_ms": candle.ingested_at_ms,
        "adapter_version": candle.adapter_version,
    }
