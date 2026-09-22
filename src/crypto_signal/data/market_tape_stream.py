from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256


class MarketTapeStreamConflictError(ValueError):
    """Raised when one exchange-native stream identity maps to conflicting truth."""


class MarketTapeChannel(StrEnum):
    PUBLIC_TRADE = "public_trade"
    ORDERBOOK_DELTA = "orderbook_delta"


class MarketTapeSequenceStatus(StrEnum):
    UNSEQUENCED = "unsequenced"
    INITIAL = "initial"
    CONTIGUOUS = "contiguous"
    OVERLAP = "overlap"
    DUPLICATE_OR_STALE = "duplicate_or_stale"
    GAP = "gap"


@dataclass(frozen=True, slots=True)
class RawMarketEvent:
    event_identity: str
    exchange: Exchange
    market_type: MarketType
    symbol: str
    channel: MarketTapeChannel
    event_at_ms: int
    source_timestamp_ms: int
    ingested_at_ms: int
    first_sequence: int | None
    last_sequence: int | None
    payload_json: str
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        if len(self.event_identity) != 64 or any(
            char not in "0123456789abcdef" for char in self.event_identity
        ):
            raise ValueError("raw market event identity must be SHA256")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("raw market event symbol must be non-empty uppercase")
        if min(self.event_at_ms, self.source_timestamp_ms, self.ingested_at_ms) < 0:
            raise ValueError("raw market event timestamps must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("raw market event cannot postdate source timestamp")
        if self.source is not DataSource.WEBSOCKET:
            raise ValueError("raw market stream event source must be websocket")
        if not self.adapter_version.strip():
            raise ValueError("raw market event adapter_version must be non-empty")
        if (self.first_sequence is None) != (self.last_sequence is None):
            raise ValueError("raw market event sequence range must be both set or both absent")
        if self.first_sequence is not None and (
            self.first_sequence < 0
            or cast(int, self.last_sequence) < self.first_sequence
        ):
            raise ValueError("raw market event sequence range is invalid")
        payload = _json_object(self.payload_json)
        if canonical_json(payload) != self.payload_json:
            raise ValueError("raw market event payload_json must be canonical")
        if self.event_identity != canonical_sha256(raw_market_event_identity_payload(self)):
            raise ValueError("raw market event identity mismatch")


@dataclass(frozen=True, slots=True)
class SequenceObservation:
    status: MarketTapeSequenceStatus
    previous_last_sequence: int | None
    first_sequence: int | None
    last_sequence: int | None
    expected_next_sequence: int | None

    @property
    def requires_resync(self) -> bool:
        return self.status is MarketTapeSequenceStatus.GAP


class MarketTapeSequenceGuard:
    """In-memory gap detector for exchange sequence ranges.

    Raw events are still persisted when a gap is detected. The guard only decides
    whether downstream order-book reconstruction may continue without a fresh snapshot.
    """

    def __init__(self) -> None:
        self._last_by_stream: dict[
            tuple[Exchange, MarketType, str, MarketTapeChannel],
            int,
        ] = {}

    def observe(self, event: RawMarketEvent) -> SequenceObservation:
        if event.first_sequence is None or event.last_sequence is None:
            return SequenceObservation(
                status=MarketTapeSequenceStatus.UNSEQUENCED,
                previous_last_sequence=None,
                first_sequence=None,
                last_sequence=None,
                expected_next_sequence=None,
            )

        key = (
            event.exchange,
            event.market_type,
            event.symbol,
            event.channel,
        )
        previous = self._last_by_stream.get(key)
        first = event.first_sequence
        last = event.last_sequence

        if previous is None:
            self._last_by_stream[key] = last
            return SequenceObservation(
                status=MarketTapeSequenceStatus.INITIAL,
                previous_last_sequence=None,
                first_sequence=first,
                last_sequence=last,
                expected_next_sequence=last + 1,
            )

        expected = previous + 1
        if last <= previous:
            return SequenceObservation(
                status=MarketTapeSequenceStatus.DUPLICATE_OR_STALE,
                previous_last_sequence=previous,
                first_sequence=first,
                last_sequence=last,
                expected_next_sequence=expected,
            )

        if first > expected:
            return SequenceObservation(
                status=MarketTapeSequenceStatus.GAP,
                previous_last_sequence=previous,
                first_sequence=first,
                last_sequence=last,
                expected_next_sequence=expected,
            )

        self._last_by_stream[key] = last
        status = (
            MarketTapeSequenceStatus.CONTIGUOUS
            if first == expected
            else MarketTapeSequenceStatus.OVERLAP
        )
        return SequenceObservation(
            status=status,
            previous_last_sequence=previous,
            first_sequence=first,
            last_sequence=last,
            expected_next_sequence=last + 1,
        )

    def reset(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        channel: MarketTapeChannel,
        last_sequence: int | None = None,
    ) -> None:
        key = (exchange, market_type, symbol, channel)
        if last_sequence is None:
            self._last_by_stream.pop(key, None)
            return
        if last_sequence < 0:
            raise ValueError("sequence reset value must be non-negative")
        self._last_by_stream[key] = last_sequence


def build_raw_market_event(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    channel: MarketTapeChannel,
    event_at_ms: int,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    first_sequence: int | None,
    last_sequence: int | None,
    payload: dict[str, object],
    adapter_version: str,
) -> RawMarketEvent:
    payload_json = canonical_json(payload)
    identity_payload = {
        "adapter_version": adapter_version,
        "channel": channel,
        "event_at_ms": event_at_ms,
        "exchange": exchange,
        "first_sequence": first_sequence,
        "last_sequence": last_sequence,
        "market_type": market_type,
        "payload": payload,
        "source": DataSource.WEBSOCKET,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol,
    }
    return RawMarketEvent(
        event_identity=canonical_sha256(identity_payload),
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        channel=channel,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        payload_json=payload_json,
        source=DataSource.WEBSOCKET,
        adapter_version=adapter_version,
    )


def raw_market_event_identity_payload(event: RawMarketEvent) -> dict[str, object]:
    return {
        "adapter_version": event.adapter_version,
        "channel": event.channel,
        "event_at_ms": event.event_at_ms,
        "exchange": event.exchange,
        "first_sequence": event.first_sequence,
        "last_sequence": event.last_sequence,
        "market_type": event.market_type,
        "payload": _json_object(event.payload_json),
        "source": event.source,
        "source_timestamp_ms": event.source_timestamp_ms,
        "symbol": event.symbol,
    }


class MarketTapeStreamStore:
    """Append-only raw WebSocket event persistence inside the Market Tape DB."""

    STREAM_SCHEMA_VERSION = "market-tape-raw-stream-v1/1"

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
                VALUES ('raw_stream_schema_version', ?)
                """,
                (self.STREAM_SCHEMA_VERSION,),
            )
            row = connection.execute(
                """
                SELECT value
                FROM market_tape_meta
                WHERE key = 'raw_stream_schema_version'
                """
            ).fetchone()
            if row is None or str(row["value"]) != self.STREAM_SCHEMA_VERSION:
                raise MarketTapeStreamConflictError(
                    "raw market stream schema version mismatch"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_tape_raw_events (
                    event_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    first_sequence INTEGER,
                    last_sequence INTEGER,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_raw_stream_context
                ON market_tape_raw_events(
                    exchange, market_type, symbol, channel, event_at_ms
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_tape_raw_stream_sequence
                ON market_tape_raw_events(
                    exchange, market_type, symbol, channel,
                    first_sequence, last_sequence
                )
                """
            )

    def append(self, event: RawMarketEvent) -> bool:
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            same_identity = connection.execute(
                """
                SELECT payload_json
                FROM market_tape_raw_events
                WHERE event_identity = ?
                """,
                (event.event_identity,),
            ).fetchone()
            if same_identity is not None:
                if str(same_identity["payload_json"]) != event.payload_json:
                    raise MarketTapeStreamConflictError(
                        "raw market event identity conflicts with payload"
                    )
                return False

            if event.first_sequence is not None:
                same_range = connection.execute(
                    """
                    SELECT payload_json
                    FROM market_tape_raw_events
                    WHERE exchange = ?
                      AND market_type = ?
                      AND symbol = ?
                      AND channel = ?
                      AND first_sequence = ?
                      AND last_sequence = ?
                    LIMIT 1
                    """,
                    (
                        event.exchange.value,
                        event.market_type.value,
                        event.symbol,
                        event.channel.value,
                        event.first_sequence,
                        event.last_sequence,
                    ),
                ).fetchone()
                if same_range is not None:
                    if str(same_range["payload_json"]) != event.payload_json:
                        raise MarketTapeStreamConflictError(
                            "exchange sequence range conflicts with raw market payload"
                        )
                    return False

            connection.execute(
                """
                INSERT INTO market_tape_raw_events(
                    event_identity,
                    exchange,
                    market_type,
                    symbol,
                    channel,
                    event_at_ms,
                    source_timestamp_ms,
                    ingested_at_ms,
                    first_sequence,
                    last_sequence,
                    source,
                    adapter_version,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.exchange.value,
                    event.market_type.value,
                    event.symbol,
                    event.channel.value,
                    event.event_at_ms,
                    event.source_timestamp_ms,
                    event.ingested_at_ms,
                    event.first_sequence,
                    event.last_sequence,
                    event.source.value,
                    event.adapter_version,
                    event.payload_json,
                ),
            )
            return True

    def count(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM market_tape_raw_events"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def latest_event_at_ms(
        self,
        *,
        exchange: Exchange | None = None,
        symbol: str | None = None,
        channel: MarketTapeChannel | None = None,
    ) -> int | None:
        self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        if exchange is not None:
            clauses.append("exchange = ?")
            params.append(exchange.value)
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)
        if channel is not None:
            clauses.append("channel = ?")
            params.append(channel.value)
        where = "" if not clauses else " WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT MAX(event_at_ms) AS latest FROM market_tape_raw_events{where}",
                tuple(params),
            ).fetchone()
        if row is None or row["latest"] is None:
            return None
        return int(row["latest"])

    def recent(
        self,
        *,
        exchange: Exchange,
        market_type: MarketType,
        symbol: str,
        channel: MarketTapeChannel,
        limit: int = 100,
    ) -> tuple[RawMarketEvent, ...]:
        if limit <= 0:
            raise ValueError("raw market stream read limit must be positive")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM market_tape_raw_events
                WHERE exchange = ?
                  AND market_type = ?
                  AND symbol = ?
                  AND channel = ?
                ORDER BY event_at_ms DESC, rowid DESC
                LIMIT ?
                """,
                (
                    exchange.value,
                    market_type.value,
                    symbol,
                    channel.value,
                    limit,
                ),
            ).fetchall()
        return tuple(_raw_event_from_row(row) for row in reversed(rows))

    def quick_check(self) -> bool:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]) == "ok"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection


def _raw_event_from_row(row: sqlite3.Row) -> RawMarketEvent:
    return RawMarketEvent(
        event_identity=str(row["event_identity"]),
        exchange=Exchange(str(row["exchange"])),
        market_type=MarketType(str(row["market_type"])),
        symbol=str(row["symbol"]),
        channel=MarketTapeChannel(str(row["channel"])),
        event_at_ms=int(row["event_at_ms"]),
        source_timestamp_ms=int(row["source_timestamp_ms"]),
        ingested_at_ms=int(row["ingested_at_ms"]),
        first_sequence=(
            None if row["first_sequence"] is None else int(row["first_sequence"])
        ),
        last_sequence=None if row["last_sequence"] is None else int(row["last_sequence"]),
        payload_json=str(row["payload_json"]),
        source=DataSource(str(row["source"])),
        adapter_version=str(row["adapter_version"]),
    )


def _json_object(value: str | object) -> dict[str, Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise MarketTapeStreamConflictError("raw market stream payload must be an object")
    return parsed
