from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.data.models import Exchange
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256


class RawMarketTapeWriteDisposition(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class RawMarketEvent:
    event_identity: str
    exchange: Exchange
    channel: str
    symbol: str
    event_kind: str
    source_timestamp_ms: int
    event_at_ms: int
    ingested_at_ms: int
    sequence: int
    update_id: int
    payload_json: str

    def __post_init__(self) -> None:
        if len(self.event_identity) != 64 or any(
            char not in "0123456789abcdef"
            for char in self.event_identity
        ):
            raise ValueError("raw market event identity must be SHA256")
        if not self.channel.strip():
            raise ValueError("raw market event channel must be non-empty")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("raw market event symbol must be uppercase")
        if not self.event_kind.strip():
            raise ValueError("raw market event kind must be non-empty")
        if min(
            self.source_timestamp_ms,
            self.event_at_ms,
            self.ingested_at_ms,
            self.sequence,
            self.update_id,
        ) < 0:
            raise ValueError("raw market event numeric fields must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("raw market event cannot postdate source timestamp")
        if not self.payload_json.strip():
            raise ValueError("raw market event payload must be non-empty")


class RawMarketTapeStore:
    """Append-only canonical JSON journal for exchange wire evidence."""

    SCHEMA_VERSION = "raw-market-tape-schema-v1/1"

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_market_tape_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO raw_market_tape_meta(key, value)
                VALUES ('schema_version', ?)
                """,
                (self.SCHEMA_VERSION,),
            )
            row = connection.execute(
                """
                SELECT value
                FROM raw_market_tape_meta
                WHERE key = 'schema_version'
                """
            ).fetchone()
            if row is None or str(row["value"]) != self.SCHEMA_VERSION:
                raise ValueError("raw market tape schema version mismatch")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_market_events (
                    event_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    update_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_raw_market_events_context
                ON raw_market_events(
                    exchange,
                    channel,
                    symbol,
                    event_at_ms,
                    sequence,
                    update_id
                )
                """
            )

    def append(
        self,
        *,
        exchange: Exchange,
        channel: str,
        symbol: str,
        event_kind: str,
        source_timestamp_ms: int,
        event_at_ms: int,
        ingested_at_ms: int,
        sequence: int,
        update_id: int,
        payload: dict[str, Any],
    ) -> tuple[RawMarketTapeWriteDisposition, RawMarketEvent]:
        payload_json = canonical_json(payload)
        event_identity = canonical_sha256(
            {
                "exchange": exchange,
                "channel": channel,
                "symbol": symbol,
                "event_kind": event_kind,
                "source_timestamp_ms": source_timestamp_ms,
                "event_at_ms": event_at_ms,
                "sequence": sequence,
                "update_id": update_id,
                "payload": payload,
            }
        )
        event = RawMarketEvent(
            event_identity=event_identity,
            exchange=exchange,
            channel=channel,
            symbol=symbol,
            event_kind=event_kind,
            source_timestamp_ms=source_timestamp_ms,
            event_at_ms=event_at_ms,
            ingested_at_ms=ingested_at_ms,
            sequence=sequence,
            update_id=update_id,
            payload_json=payload_json,
        )

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT payload_json
                FROM raw_market_events
                WHERE event_identity = ?
                """,
                (event.event_identity,),
            ).fetchone()
            if row is not None:
                if str(row["payload_json"]) != payload_json:
                    raise ValueError("raw market event identity conflict")
                return RawMarketTapeWriteDisposition.UNCHANGED, event

            connection.execute(
                """
                INSERT INTO raw_market_events(
                    event_identity,
                    exchange,
                    channel,
                    symbol,
                    event_kind,
                    source_timestamp_ms,
                    event_at_ms,
                    ingested_at_ms,
                    sequence,
                    update_id,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.exchange.value,
                    event.channel,
                    event.symbol,
                    event.event_kind,
                    event.source_timestamp_ms,
                    event.event_at_ms,
                    event.ingested_at_ms,
                    event.sequence,
                    event.update_id,
                    event.payload_json,
                ),
            )
        return RawMarketTapeWriteDisposition.INSERTED, event

    def count(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM raw_market_events"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def latest_event_at_ms(self) -> int | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(event_at_ms) AS latest_event_at_ms
                FROM raw_market_events
                """
            ).fetchone()
        if row is None or row["latest_event_at_ms"] is None:
            return None
        return int(row["latest_event_at_ms"])

    def quick_check(self) -> bool:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]) == "ok"

    def recent(
        self,
        *,
        exchange: Exchange,
        channel: str,
        symbol: str,
        limit: int = 100,
    ) -> tuple[RawMarketEvent, ...]:
        if limit <= 0:
            raise ValueError("raw market tape read limit must be positive")

        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM raw_market_events
                WHERE exchange = ? AND channel = ? AND symbol = ?
                ORDER BY event_at_ms DESC, rowid DESC
                LIMIT ?
                """,
                (exchange.value, channel, symbol, limit),
            ).fetchall()

        return tuple(
            reversed(tuple(_event_from_row(row) for row in rows))
        )

    def latest_by_context(
        self,
        *,
        exchange: Exchange,
    ) -> tuple[RawMarketEvent, ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM raw_market_events
                WHERE exchange = ?
                ORDER BY channel, symbol, ingested_at_ms DESC, rowid DESC
                """,
                (exchange.value,),
            ).fetchall()

        latest: dict[tuple[str, str], RawMarketEvent] = {}
        for row in rows:
            event = _event_from_row(row)
            latest.setdefault((event.channel, event.symbol), event)
        return tuple(
            latest[key]
            for key in sorted(latest)
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection


def _event_from_row(row: sqlite3.Row) -> RawMarketEvent:
    return RawMarketEvent(
        event_identity=str(row["event_identity"]),
        exchange=Exchange(str(row["exchange"])),
        channel=str(row["channel"]),
        symbol=str(row["symbol"]),
        event_kind=str(row["event_kind"]),
        source_timestamp_ms=int(row["source_timestamp_ms"]),
        event_at_ms=int(row["event_at_ms"]),
        ingested_at_ms=int(row["ingested_at_ms"]),
        sequence=int(row["sequence"]),
        update_id=int(row["update_id"]),
        payload_json=str(row["payload_json"]),
    )
