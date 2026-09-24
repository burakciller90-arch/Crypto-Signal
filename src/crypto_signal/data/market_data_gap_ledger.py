from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TypedDict

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

MARKET_DATA_GAP_SCHEMA_VERSION = "market-data-gap-ledger-v1/1"
REAL_CAPITAL = 0


class GapExpectationKind(StrEnum):
    MAX_INGESTION_SILENCE_MS = "max_ingestion_silence_ms"


class GapEventKind(StrEnum):
    OBSERVED = "observed"
    RECOVERY_ATTEMPTED = "recovery_attempted"
    RECOVERED = "recovered"
    UNRECOVERED = "unrecovered"


class _GapEventValues(TypedDict):
    gap_identity: str
    previous_event_identity: str | None
    event_kind: GapEventKind
    provider: str
    source: str
    channel: str
    symbol: str
    expectation_kind: GapExpectationKind
    expectation_value: int
    last_successful_ingestion_ms: int
    gap_started_at_ms: int
    observed_at_ms: int
    recovered_at_ms: int | None
    source_evidence_identities: tuple[str, ...]
    recovery_action: str | None
    reason_codes: tuple[str, ...]
    schema_version: str
    production_authority: bool
    real_capital: int


@dataclass(frozen=True, slots=True)
class MarketDataGapEvent:
    event_identity: str
    gap_identity: str
    previous_event_identity: str | None
    event_kind: GapEventKind
    provider: str
    source: str
    channel: str
    symbol: str
    expectation_kind: GapExpectationKind
    expectation_value: int
    last_successful_ingestion_ms: int
    gap_started_at_ms: int
    observed_at_ms: int
    recovered_at_ms: int | None
    source_evidence_identities: tuple[str, ...]
    recovery_action: str | None
    reason_codes: tuple[str, ...]
    schema_version: str = MARKET_DATA_GAP_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for identity, label in (
            (self.event_identity, "gap event identity"),
            (self.gap_identity, "gap identity"),
        ):
            _require_sha256(identity, label)
        if self.previous_event_identity is not None:
            _require_sha256(
                self.previous_event_identity,
                "gap previous event identity",
            )
        if self.schema_version != MARKET_DATA_GAP_SCHEMA_VERSION:
            raise ValueError("unsupported market-data gap schema")
        if not all(
            value.strip()
            for value in (self.provider, self.source, self.channel, self.symbol)
        ):
            raise ValueError("gap provider/source/channel/symbol must be non-empty")
        if self.symbol != self.symbol.upper():
            raise ValueError("gap symbol must be uppercase")
        if self.expectation_value <= 0:
            raise ValueError("gap expectation must be positive")
        if min(
            self.last_successful_ingestion_ms,
            self.gap_started_at_ms,
            self.observed_at_ms,
        ) < 0:
            raise ValueError("gap timestamps cannot be negative")
        if self.gap_started_at_ms < self.last_successful_ingestion_ms:
            raise ValueError("gap cannot start before last successful ingestion")
        if self.observed_at_ms < self.gap_started_at_ms:
            raise ValueError("gap observation cannot predate gap start")
        if self.event_kind is GapEventKind.OBSERVED:
            if self.previous_event_identity is not None:
                raise ValueError("first gap observation cannot have predecessor")
            if self.recovered_at_ms is not None or self.recovery_action is not None:
                raise ValueError("gap observation cannot claim recovery")
        else:
            if self.previous_event_identity is None:
                raise ValueError("gap transition requires predecessor")
        if self.event_kind is GapEventKind.RECOVERY_ATTEMPTED:
            if self.recovery_action is None or not self.recovery_action.strip():
                raise ValueError("recovery attempt requires action")
            if self.recovered_at_ms is not None:
                raise ValueError("recovery attempt cannot claim recovered time")
        if self.event_kind is GapEventKind.RECOVERED:
            if self.recovered_at_ms is None:
                raise ValueError("recovered gap requires recovered_at_ms")
            if self.recovered_at_ms < self.observed_at_ms:
                raise ValueError("gap recovery cannot predate observation")
        if (
            self.event_kind is GapEventKind.UNRECOVERED
            and self.recovered_at_ms is not None
        ):
            raise ValueError("unrecovered gap cannot carry recovery time")
        if not self.source_evidence_identities:
            raise ValueError("gap event requires exact source evidence")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "gap source evidence identity")
        if tuple(sorted(set(self.source_evidence_identities))) != (
            self.source_evidence_identities
        ):
            raise ValueError("gap source evidence identities must be canonical")
        if not self.reason_codes:
            raise ValueError("gap event requires reason code")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("gap reason codes must be canonical")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("gap evidence cannot grant production authority")
        if self.event_identity != canonical_sha256(_event_payload(self)):
            raise ValueError("gap event identity mismatch")


def build_gap_observed(
    *,
    provider: str,
    source: str,
    channel: str,
    symbol: str,
    expectation_value: int,
    last_successful_ingestion_ms: int,
    observed_at_ms: int,
    source_evidence_identities: tuple[str, ...],
) -> MarketDataGapEvent:
    gap_started_at_ms = last_successful_ingestion_ms + expectation_value
    gap_identity = canonical_sha256(
        {
            "schema_version": MARKET_DATA_GAP_SCHEMA_VERSION,
            "provider": provider,
            "source": source,
            "channel": channel,
            "symbol": symbol,
            "expectation_kind": GapExpectationKind.MAX_INGESTION_SILENCE_MS,
            "expectation_value": expectation_value,
            "last_successful_ingestion_ms": last_successful_ingestion_ms,
            "gap_started_at_ms": gap_started_at_ms,
        }
    )
    values = _event_values(
        gap_identity=gap_identity,
        previous_event_identity=None,
        event_kind=GapEventKind.OBSERVED,
        provider=provider,
        source=source,
        channel=channel,
        symbol=symbol,
        expectation_value=expectation_value,
        last_successful_ingestion_ms=last_successful_ingestion_ms,
        gap_started_at_ms=gap_started_at_ms,
        observed_at_ms=observed_at_ms,
        recovered_at_ms=None,
        source_evidence_identities=source_evidence_identities,
        recovery_action=None,
        reason_codes=("ingestion_silence_exceeded_policy",),
    )
    return MarketDataGapEvent(
        event_identity=canonical_sha256(values),
        **values,
    )


def build_gap_recovery_attempt(
    previous: MarketDataGapEvent,
    *,
    attempted_at_ms: int,
    recovery_action: str,
    source_evidence_identities: tuple[str, ...],
) -> MarketDataGapEvent:
    if previous.event_kind in {GapEventKind.RECOVERED, GapEventKind.UNRECOVERED}:
        raise ValueError("terminal gap cannot receive recovery attempt")
    values = _event_values(
        gap_identity=previous.gap_identity,
        previous_event_identity=previous.event_identity,
        event_kind=GapEventKind.RECOVERY_ATTEMPTED,
        provider=previous.provider,
        source=previous.source,
        channel=previous.channel,
        symbol=previous.symbol,
        expectation_value=previous.expectation_value,
        last_successful_ingestion_ms=previous.last_successful_ingestion_ms,
        gap_started_at_ms=previous.gap_started_at_ms,
        observed_at_ms=attempted_at_ms,
        recovered_at_ms=None,
        source_evidence_identities=source_evidence_identities,
        recovery_action=recovery_action,
        reason_codes=("recovery_attempt_recorded",),
    )
    return MarketDataGapEvent(event_identity=canonical_sha256(values), **values)


def build_gap_recovered(
    previous: MarketDataGapEvent,
    *,
    recovered_at_ms: int,
    source_evidence_identities: tuple[str, ...],
) -> MarketDataGapEvent:
    if previous.event_kind in {GapEventKind.RECOVERED, GapEventKind.UNRECOVERED}:
        raise ValueError("terminal gap cannot recover")
    values = _event_values(
        gap_identity=previous.gap_identity,
        previous_event_identity=previous.event_identity,
        event_kind=GapEventKind.RECOVERED,
        provider=previous.provider,
        source=previous.source,
        channel=previous.channel,
        symbol=previous.symbol,
        expectation_value=previous.expectation_value,
        last_successful_ingestion_ms=previous.last_successful_ingestion_ms,
        gap_started_at_ms=previous.gap_started_at_ms,
        observed_at_ms=recovered_at_ms,
        recovered_at_ms=recovered_at_ms,
        source_evidence_identities=source_evidence_identities,
        recovery_action=None,
        reason_codes=("ingestion_resumed_after_gap",),
    )
    return MarketDataGapEvent(event_identity=canonical_sha256(values), **values)


class MarketDataGapLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_data_gap_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_data_gap_events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_identity TEXT UNIQUE NOT NULL,
                    gap_identity TEXT NOT NULL,
                    previous_event_identity TEXT,
                    event_kind TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS market_data_gap_context
                    ON market_data_gap_events(
                        provider, source, channel, symbol, observed_at_ms
                    );
                CREATE INDEX IF NOT EXISTS market_data_gap_identity
                    ON market_data_gap_events(gap_identity, sequence_id);
                """
            )
            row = db.execute(
                "SELECT value FROM market_data_gap_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO market_data_gap_meta(key, value) VALUES (?, ?)",
                    ("schema_version", MARKET_DATA_GAP_SCHEMA_VERSION),
                )
            elif str(row[0]) != MARKET_DATA_GAP_SCHEMA_VERSION:
                raise ValueError("market-data gap schema mismatch")

    def append(self, event: MarketDataGapEvent) -> None:
        self.initialize()
        payload = canonical_json(_event_payload(event))
        with sqlite3.connect(self.path) as db:
            existing = db.execute(
                "SELECT payload_json FROM market_data_gap_events "
                "WHERE event_identity=?",
                (event.event_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("gap event identity conflict")
                return
            chain = db.execute(
                """SELECT event_identity, event_kind, payload_json
                FROM market_data_gap_events
                WHERE gap_identity=?
                ORDER BY sequence_id DESC LIMIT 1""",
                (event.gap_identity,),
            ).fetchone()
            if chain is None:
                if event.event_kind is not GapEventKind.OBSERVED:
                    raise ValueError("gap transition without observed root")
            else:
                if event.previous_event_identity != str(chain[0]):
                    raise ValueError("gap transition predecessor mismatch")
                if str(chain[1]) in {
                    GapEventKind.RECOVERED.value,
                    GapEventKind.UNRECOVERED.value,
                }:
                    raise ValueError("gap is already terminal")
                previous = _event_from_payload(str(chain[2]))
                if event.observed_at_ms < previous.observed_at_ms:
                    raise ValueError("gap transition time regressed")
            db.execute(
                """INSERT INTO market_data_gap_events(
                    event_identity, gap_identity, previous_event_identity,
                    event_kind, provider, source, channel, symbol,
                    observed_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_identity,
                    event.gap_identity,
                    event.previous_event_identity,
                    event.event_kind.value,
                    event.provider,
                    event.source,
                    event.channel,
                    event.symbol,
                    event.observed_at_ms,
                    payload,
                ),
            )

    def latest_for_gap(self, gap_identity: str) -> MarketDataGapEvent | None:
        if not self.path.is_file():
            return None
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                """SELECT payload_json FROM market_data_gap_events
                WHERE gap_identity=?
                ORDER BY sequence_id DESC LIMIT 1""",
                (gap_identity,),
            ).fetchone()
        return None if row is None else _event_from_payload(str(row[0]))

    def events(self) -> tuple[MarketDataGapEvent, ...]:
        if not self.path.is_file():
            return ()
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT payload_json FROM market_data_gap_events ORDER BY sequence_id"
            ).fetchall()
        return tuple(_event_from_payload(str(row[0])) for row in rows)

    def open_gaps(
        self,
        *,
        provider: str,
        source: str,
    ) -> tuple[MarketDataGapEvent, ...]:
        latest_by_gap: dict[str, MarketDataGapEvent] = {}
        for event in self.events():
            if event.provider != provider or event.source != source:
                continue
            latest_by_gap[event.gap_identity] = event

        open_events = tuple(
            sorted(
                (
                    event
                    for event in latest_by_gap.values()
                    if event.event_kind
                    not in {GapEventKind.RECOVERED, GapEventKind.UNRECOVERED}
                ),
                key=lambda event: (
                    event.channel,
                    event.symbol,
                    event.gap_started_at_ms,
                    event.gap_identity,
                ),
            )
        )
        contexts: set[tuple[str, str]] = set()
        for event in open_events:
            key = (event.channel, event.symbol)
            if key in contexts:
                raise ValueError(
                    "multiple open gaps exist for one provider/source context"
                )
            contexts.add(key)
        return open_events

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with sqlite3.connect(self.path) as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


@dataclass(slots=True)
class IngestionSilenceGapMonitor:
    ledger: MarketDataGapLedger
    provider: str
    source: str
    max_ingestion_silence_ms: int
    _last_ingestion: dict[tuple[str, str], int] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _open_gaps: dict[tuple[str, str], MarketDataGapEvent] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.source.strip():
            raise ValueError("gap monitor provider/source must be non-empty")
        if self.max_ingestion_silence_ms <= 0:
            raise ValueError("gap monitor silence threshold must be positive")

        for event in self.ledger.open_gaps(
            provider=self.provider,
            source=self.source,
        ):
            if event.expectation_value != self.max_ingestion_silence_ms:
                raise ValueError(
                    "open gap expectation conflicts with active monitor policy"
                )
            key = (event.channel, event.symbol)
            self._open_gaps[key] = event
            self._last_ingestion[key] = event.last_successful_ingestion_ms

    def seed_persisted_event(
        self,
        *,
        channel: str,
        symbol: str,
        ingested_at_ms: int,
        source_evidence_identities: tuple[str, ...],
    ) -> None:
        key = (channel, symbol)
        previous = self._last_ingestion.get(key)
        open_gap = self._open_gaps.get(key)
        if previous is not None and ingested_at_ms < previous:
            raise ValueError("gap monitor seed ingestion time regressed")
        if open_gap is not None:
            if ingested_at_ms <= open_gap.last_successful_ingestion_ms:
                return
            if ingested_at_ms <= open_gap.observed_at_ms:
                raise ValueError(
                    "persisted evidence conflicts with restored open gap"
                )
            self.observe_persisted_event(
                channel=channel,
                symbol=symbol,
                ingested_at_ms=ingested_at_ms,
                source_evidence_identities=source_evidence_identities,
            )
            return
        self._last_ingestion[key] = ingested_at_ms

    def observe_persisted_event(
        self,
        *,
        channel: str,
        symbol: str,
        ingested_at_ms: int,
        source_evidence_identities: tuple[str, ...],
    ) -> None:
        key = (channel, symbol)
        previous = self._last_ingestion.get(key)
        open_gap = self._open_gaps.get(key)
        if previous is not None and ingested_at_ms < previous:
            raise ValueError("gap monitor ingestion time regressed")
        if open_gap is not None:
            if ingested_at_ms <= open_gap.observed_at_ms:
                raise ValueError(
                    "gap recovery evidence must postdate gap observation"
                )
            recovered = build_gap_recovered(
                open_gap,
                recovered_at_ms=ingested_at_ms,
                source_evidence_identities=source_evidence_identities,
            )
            self.ledger.append(recovered)
            self._open_gaps.pop(key, None)
        elif (
            previous is not None
            and ingested_at_ms - previous > self.max_ingestion_silence_ms
        ):
            observed = build_gap_observed(
                provider=self.provider,
                source=self.source,
                channel=channel,
                symbol=symbol,
                expectation_value=self.max_ingestion_silence_ms,
                last_successful_ingestion_ms=previous,
                observed_at_ms=ingested_at_ms,
                source_evidence_identities=source_evidence_identities,
            )
            self.ledger.append(observed)
            recovered = build_gap_recovered(
                observed,
                recovered_at_ms=ingested_at_ms,
                source_evidence_identities=source_evidence_identities,
            )
            self.ledger.append(recovered)
        self._last_ingestion[key] = ingested_at_ms

    def check_silence(
        self,
        *,
        observed_at_ms: int,
        source_evidence_identities: tuple[str, ...],
    ) -> None:
        if observed_at_ms < 0:
            raise ValueError("gap monitor observation time cannot be negative")
        for (channel, symbol), last_ingestion in sorted(
            self._last_ingestion.items()
        ):
            key = (channel, symbol)
            if observed_at_ms < last_ingestion:
                raise ValueError("gap monitor observation time regressed")
            if key in self._open_gaps:
                continue
            if (
                observed_at_ms - last_ingestion
                <= self.max_ingestion_silence_ms
            ):
                continue
            observed = build_gap_observed(
                provider=self.provider,
                source=self.source,
                channel=channel,
                symbol=symbol,
                expectation_value=self.max_ingestion_silence_ms,
                last_successful_ingestion_ms=last_ingestion,
                observed_at_ms=observed_at_ms,
                source_evidence_identities=source_evidence_identities,
            )
            self.ledger.append(observed)
            self._open_gaps[key] = observed


def _event_values(
    *,
    gap_identity: str,
    previous_event_identity: str | None,
    event_kind: GapEventKind,
    provider: str,
    source: str,
    channel: str,
    symbol: str,
    expectation_value: int,
    last_successful_ingestion_ms: int,
    gap_started_at_ms: int,
    observed_at_ms: int,
    recovered_at_ms: int | None,
    source_evidence_identities: tuple[str, ...],
    recovery_action: str | None,
    reason_codes: tuple[str, ...],
) -> _GapEventValues:
    return {
        "gap_identity": gap_identity,
        "previous_event_identity": previous_event_identity,
        "event_kind": event_kind,
        "provider": provider,
        "source": source,
        "channel": channel,
        "symbol": symbol,
        "expectation_kind": GapExpectationKind.MAX_INGESTION_SILENCE_MS,
        "expectation_value": expectation_value,
        "last_successful_ingestion_ms": last_successful_ingestion_ms,
        "gap_started_at_ms": gap_started_at_ms,
        "observed_at_ms": observed_at_ms,
        "recovered_at_ms": recovered_at_ms,
        "source_evidence_identities": tuple(
            sorted(set(source_evidence_identities))
        ),
        "recovery_action": recovery_action,
        "reason_codes": tuple(sorted(set(reason_codes))),
        "schema_version": MARKET_DATA_GAP_SCHEMA_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }


def _event_payload(event: MarketDataGapEvent) -> _GapEventValues:
    return _event_values(
        gap_identity=event.gap_identity,
        previous_event_identity=event.previous_event_identity,
        event_kind=event.event_kind,
        provider=event.provider,
        source=event.source,
        channel=event.channel,
        symbol=event.symbol,
        expectation_value=event.expectation_value,
        last_successful_ingestion_ms=event.last_successful_ingestion_ms,
        gap_started_at_ms=event.gap_started_at_ms,
        observed_at_ms=event.observed_at_ms,
        recovered_at_ms=event.recovered_at_ms,
        source_evidence_identities=event.source_evidence_identities,
        recovery_action=event.recovery_action,
        reason_codes=event.reason_codes,
    )


def _event_from_payload(payload_json: str) -> MarketDataGapEvent:
    import json

    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("gap payload must be object")
    values: _GapEventValues = {
        "gap_identity": str(payload["gap_identity"]),
        "previous_event_identity": (
            None
            if payload["previous_event_identity"] is None
            else str(payload["previous_event_identity"])
        ),
        "event_kind": GapEventKind(str(payload["event_kind"])),
        "provider": str(payload["provider"]),
        "source": str(payload["source"]),
        "channel": str(payload["channel"]),
        "symbol": str(payload["symbol"]),
        "expectation_kind": GapExpectationKind(
            str(payload["expectation_kind"])
        ),
        "expectation_value": int(payload["expectation_value"]),
        "last_successful_ingestion_ms": int(
            payload["last_successful_ingestion_ms"]
        ),
        "gap_started_at_ms": int(payload["gap_started_at_ms"]),
        "observed_at_ms": int(payload["observed_at_ms"]),
        "recovered_at_ms": (
            None
            if payload["recovered_at_ms"] is None
            else int(payload["recovered_at_ms"])
        ),
        "source_evidence_identities": tuple(
            str(value) for value in payload["source_evidence_identities"]
        ),
        "recovery_action": (
            None
            if payload["recovery_action"] is None
            else str(payload["recovery_action"])
        ),
        "reason_codes": tuple(str(value) for value in payload["reason_codes"]),
        "schema_version": str(payload["schema_version"]),
        "production_authority": bool(payload["production_authority"]),
        "real_capital": int(payload["real_capital"]),
    }
    return MarketDataGapEvent(
        event_identity=canonical_sha256(values),
        **values,
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
