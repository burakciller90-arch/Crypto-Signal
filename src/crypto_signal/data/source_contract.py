from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

SOURCE_CONTRACT_SCHEMA_VERSION = "source-contract-v1/1"
REAL_CAPITAL = 0


class SourceTransport(StrEnum):
    REST = "rest"
    WEBSOCKET = "websocket"
    SCHEDULED = "scheduled"


class SourceSequenceSemantics(StrEnum):
    NONE = "none"
    MONOTONIC = "monotonic"
    PROVIDER_UPDATE_ID = "provider_update_id"
    PROVIDER_EVENT_ID = "provider_event_id"


class SourceFreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    GAP = "gap"
    UNAVAILABLE = "unavailable"


class SourceCoverageState(StrEnum):
    OBSERVED = "observed"
    GAP = "gap"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SourceCapability:
    capability_identity: str
    provider: str
    source: str
    channel: str
    transport: SourceTransport
    sequence_semantics: SourceSequenceSemantics
    supports_provider_event_id: bool
    freshness_budget_ms: int
    symbols: tuple[str, ...]
    schema_version: str = SOURCE_CONTRACT_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.capability_identity, "source capability identity")
        if self.schema_version != SOURCE_CONTRACT_SCHEMA_VERSION:
            raise ValueError("unsupported source contract schema")
        if not all(
            value.strip() for value in (self.provider, self.source, self.channel)
        ):
            raise ValueError("source capability provider/source/channel must be non-empty")
        if self.freshness_budget_ms <= 0:
            raise ValueError("source capability freshness budget must be positive")
        if not self.symbols:
            raise ValueError("source capability requires at least one symbol")
        if tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("source capability symbols must be canonical")
        if any(not symbol or symbol != symbol.upper() for symbol in self.symbols):
            raise ValueError("source capability symbols must be uppercase")
        if (
            self.sequence_semantics is SourceSequenceSemantics.PROVIDER_EVENT_ID
            and not self.supports_provider_event_id
        ):
            raise ValueError(
                "provider-event-id sequencing requires provider event IDs"
            )
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("source capability cannot grant production authority")
        if self.capability_identity != canonical_sha256(
            _capability_payload_values(
                provider=self.provider,
                source=self.source,
                channel=self.channel,
                transport=self.transport,
                sequence_semantics=self.sequence_semantics,
                supports_provider_event_id=self.supports_provider_event_id,
                freshness_budget_ms=self.freshness_budget_ms,
                symbols=self.symbols,
                production_authority=self.production_authority,
                real_capital=self.real_capital,
            )
        ):
            raise ValueError("source capability identity mismatch")


@dataclass(frozen=True, slots=True)
class SourceEnvelope:
    envelope_identity: str
    capability_identity: str
    provider: str
    source: str
    channel: str
    symbol: str
    provider_event_id: str | None
    provider_sequence: int | None
    event_at_ms: int
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    raw_identity: str
    normalized_identity: str | None
    schema_version: str = SOURCE_CONTRACT_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.envelope_identity, "source envelope identity")
        _require_sha256(self.capability_identity, "source capability identity")
        _require_sha256(self.raw_identity, "source envelope raw identity")
        if self.normalized_identity is not None:
            _require_sha256(
                self.normalized_identity,
                "source envelope normalized identity",
            )
        if self.schema_version != SOURCE_CONTRACT_SCHEMA_VERSION:
            raise ValueError("unsupported source contract schema")
        if not all(
            value.strip() for value in (self.provider, self.source, self.channel)
        ):
            raise ValueError("source envelope provider/source/channel must be non-empty")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("source envelope symbol must be uppercase")
        if self.provider_event_id is not None and not self.provider_event_id.strip():
            raise ValueError("provider event id cannot be blank")
        if self.provider_sequence is not None and self.provider_sequence < 0:
            raise ValueError("provider sequence cannot be negative")
        if min(
            self.event_at_ms,
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("source envelope timestamps cannot be negative")
        if self.observed_at_ms > self.ingested_at_ms:
            raise ValueError("source envelope observation cannot postdate ingestion")
        if self.event_at_ms > self.ingested_at_ms:
            raise ValueError("source envelope event cannot postdate ingestion")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("source envelope cannot grant production authority")
        if self.envelope_identity != canonical_sha256(
            _envelope_payload_values(
                capability_identity=self.capability_identity,
                provider=self.provider,
                source=self.source,
                channel=self.channel,
                symbol=self.symbol,
                provider_event_id=self.provider_event_id,
                provider_sequence=self.provider_sequence,
                event_at_ms=self.event_at_ms,
                source_timestamp_ms=self.source_timestamp_ms,
                observed_at_ms=self.observed_at_ms,
                ingested_at_ms=self.ingested_at_ms,
                raw_identity=self.raw_identity,
                normalized_identity=self.normalized_identity,
                production_authority=self.production_authority,
                real_capital=self.real_capital,
            )
        ):
            raise ValueError("source envelope identity mismatch")


@dataclass(frozen=True, slots=True)
class SourceFreshness:
    capability_identity: str
    source_envelope_identity: str | None
    state: SourceFreshnessState
    as_of_ms: int
    source_age_ms: int | None
    freshness_budget_ms: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.capability_identity, "source capability identity")
        if self.source_envelope_identity is not None:
            _require_sha256(
                self.source_envelope_identity,
                "source envelope identity",
            )
        if self.as_of_ms < 0:
            raise ValueError("freshness as-of cannot be negative")
        if self.freshness_budget_ms <= 0:
            raise ValueError("freshness budget must be positive")
        if (
            self.source_age_ms is not None
            and self.state is not SourceFreshnessState.STALE
            and self.source_age_ms < 0
        ):
            raise ValueError("negative source age is only valid as explicit stale state")
        if not self.reason_codes:
            raise ValueError("freshness requires explicit reason code")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("freshness reason codes must be canonical")


@dataclass(frozen=True, slots=True)
class SourceCoverageEvent:
    coverage_event_identity: str
    previous_event_identity: str | None
    capability_identity: str
    provider: str
    source: str
    channel: str
    symbol: str
    state: SourceCoverageState
    observed_at_ms: int
    source_envelope_identity: str | None
    gap_event_identity: str | None
    reason_codes: tuple[str, ...]
    schema_version: str = SOURCE_CONTRACT_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(
            self.coverage_event_identity,
            "source coverage event identity",
        )
        _require_sha256(self.capability_identity, "source capability identity")
        if self.previous_event_identity is not None:
            _require_sha256(
                self.previous_event_identity,
                "source coverage previous event identity",
            )
        if self.source_envelope_identity is not None:
            _require_sha256(
                self.source_envelope_identity,
                "source coverage envelope identity",
            )
        if self.gap_event_identity is not None:
            _require_sha256(
                self.gap_event_identity,
                "source coverage gap event identity",
            )
        if self.schema_version != SOURCE_CONTRACT_SCHEMA_VERSION:
            raise ValueError("unsupported source contract schema")
        if not all(
            value.strip() for value in (self.provider, self.source, self.channel)
        ):
            raise ValueError("source coverage provider/source/channel must be non-empty")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("source coverage symbol must be uppercase")
        if self.observed_at_ms < 0:
            raise ValueError("source coverage timestamp cannot be negative")
        if not self.reason_codes:
            raise ValueError("source coverage requires reason code")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("source coverage reason codes must be canonical")

        if self.state is SourceCoverageState.OBSERVED:
            if self.source_envelope_identity is None:
                raise ValueError("observed coverage requires source envelope")
            if self.gap_event_identity is not None:
                raise ValueError("observed coverage cannot claim open gap")
        elif self.state is SourceCoverageState.GAP:
            if self.gap_event_identity is None:
                raise ValueError("gap coverage requires exact gap event")
            if self.source_envelope_identity is not None:
                raise ValueError("gap coverage cannot substitute source envelope")
        elif (
            self.source_envelope_identity is not None
            or self.gap_event_identity is not None
        ):
            raise ValueError("unavailable coverage cannot carry source evidence")

        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("source coverage cannot grant production authority")
        if self.coverage_event_identity != canonical_sha256(
            _coverage_payload_values(
                previous_event_identity=self.previous_event_identity,
                capability_identity=self.capability_identity,
                provider=self.provider,
                source=self.source,
                channel=self.channel,
                symbol=self.symbol,
                state=self.state,
                observed_at_ms=self.observed_at_ms,
                source_envelope_identity=self.source_envelope_identity,
                gap_event_identity=self.gap_event_identity,
                reason_codes=self.reason_codes,
                production_authority=self.production_authority,
                real_capital=self.real_capital,
            )
        ):
            raise ValueError("source coverage identity mismatch")


def build_source_capability(
    *,
    provider: str,
    source: str,
    channel: str,
    transport: SourceTransport,
    sequence_semantics: SourceSequenceSemantics,
    supports_provider_event_id: bool,
    freshness_budget_ms: int,
    symbols: tuple[str, ...],
) -> SourceCapability:
    canonical_symbols = tuple(sorted(set(symbols)))
    values = _capability_payload_values(
        provider=provider,
        source=source,
        channel=channel,
        transport=transport,
        sequence_semantics=sequence_semantics,
        supports_provider_event_id=supports_provider_event_id,
        freshness_budget_ms=freshness_budget_ms,
        symbols=canonical_symbols,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return SourceCapability(
        capability_identity=canonical_sha256(values),
        provider=provider,
        source=source,
        channel=channel,
        transport=transport,
        sequence_semantics=sequence_semantics,
        supports_provider_event_id=supports_provider_event_id,
        freshness_budget_ms=freshness_budget_ms,
        symbols=canonical_symbols,
    )


def build_source_envelope(
    *,
    capability: SourceCapability,
    symbol: str,
    provider_event_id: str | None,
    provider_sequence: int | None,
    event_at_ms: int,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    raw_identity: str,
    normalized_identity: str | None,
) -> SourceEnvelope:
    if symbol not in capability.symbols:
        raise ValueError("source envelope symbol is outside capability registry")
    if capability.supports_provider_event_id and provider_event_id is None:
        raise ValueError("source capability requires provider event id")
    if (
        capability.sequence_semantics
        in {
            SourceSequenceSemantics.MONOTONIC,
            SourceSequenceSemantics.PROVIDER_UPDATE_ID,
        }
        and provider_sequence is None
    ):
        raise ValueError("source capability requires provider sequence")

    values = _envelope_payload_values(
        capability_identity=capability.capability_identity,
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
        provider_event_id=provider_event_id,
        provider_sequence=provider_sequence,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        raw_identity=raw_identity,
        normalized_identity=normalized_identity,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return SourceEnvelope(
        envelope_identity=canonical_sha256(values),
        capability_identity=capability.capability_identity,
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
        provider_event_id=provider_event_id,
        provider_sequence=provider_sequence,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        raw_identity=raw_identity,
        normalized_identity=normalized_identity,
    )


def assess_source_freshness(
    *,
    capability: SourceCapability,
    envelope: SourceEnvelope | None,
    as_of_ms: int,
    gap_open: bool = False,
    unavailable_reason: str = "no_source_envelope_as_of",
) -> SourceFreshness:
    if as_of_ms < 0:
        raise ValueError("freshness as-of cannot be negative")
    if not unavailable_reason.strip():
        raise ValueError("unavailable freshness reason must be non-empty")

    if envelope is not None:
        _require_envelope_matches_capability(capability, envelope)

    if gap_open:
        source_age_ms = (
            None
            if envelope is None
            else as_of_ms - envelope.source_timestamp_ms
        )
        return SourceFreshness(
            capability_identity=capability.capability_identity,
            source_envelope_identity=(
                None if envelope is None else envelope.envelope_identity
            ),
            state=SourceFreshnessState.GAP,
            as_of_ms=as_of_ms,
            source_age_ms=source_age_ms,
            freshness_budget_ms=capability.freshness_budget_ms,
            reason_codes=("open_gap",),
        )

    if envelope is None:
        return SourceFreshness(
            capability_identity=capability.capability_identity,
            source_envelope_identity=None,
            state=SourceFreshnessState.UNAVAILABLE,
            as_of_ms=as_of_ms,
            source_age_ms=None,
            freshness_budget_ms=capability.freshness_budget_ms,
            reason_codes=(unavailable_reason,),
        )

    if envelope.ingested_at_ms > as_of_ms:
        return SourceFreshness(
            capability_identity=capability.capability_identity,
            source_envelope_identity=None,
            state=SourceFreshnessState.UNAVAILABLE,
            as_of_ms=as_of_ms,
            source_age_ms=None,
            freshness_budget_ms=capability.freshness_budget_ms,
            reason_codes=("not_ingested_as_of",),
        )

    source_age_ms = as_of_ms - envelope.source_timestamp_ms
    if source_age_ms < 0:
        state = SourceFreshnessState.STALE
        reasons = ("source_timestamp_in_future",)
    elif source_age_ms > capability.freshness_budget_ms:
        state = SourceFreshnessState.STALE
        reasons = ("source_age_exceeded_budget",)
    else:
        state = SourceFreshnessState.FRESH
        reasons = ("inside_freshness_budget",)

    return SourceFreshness(
        capability_identity=capability.capability_identity,
        source_envelope_identity=envelope.envelope_identity,
        state=state,
        as_of_ms=as_of_ms,
        source_age_ms=source_age_ms,
        freshness_budget_ms=capability.freshness_budget_ms,
        reason_codes=reasons,
    )


def build_source_coverage_event(
    *,
    capability: SourceCapability,
    symbol: str,
    state: SourceCoverageState,
    observed_at_ms: int,
    previous: SourceCoverageEvent | None = None,
    source_envelope_identity: str | None = None,
    gap_event_identity: str | None = None,
    reason_codes: tuple[str, ...],
) -> SourceCoverageEvent:
    if symbol not in capability.symbols:
        raise ValueError("source coverage symbol is outside capability registry")
    canonical_reasons = tuple(sorted(set(reason_codes)))
    if not canonical_reasons:
        raise ValueError("source coverage requires reason code")
    if previous is not None:
        if (
            previous.provider,
            previous.source,
            previous.channel,
            previous.symbol,
        ) != (
            capability.provider,
            capability.source,
            capability.channel,
            symbol,
        ):
            raise ValueError("source coverage predecessor context mismatch")
        if observed_at_ms < previous.observed_at_ms:
            raise ValueError("source coverage time regressed")

    values = _coverage_payload_values(
        previous_event_identity=(
            None if previous is None else previous.coverage_event_identity
        ),
        capability_identity=capability.capability_identity,
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
        state=state,
        observed_at_ms=observed_at_ms,
        source_envelope_identity=source_envelope_identity,
        gap_event_identity=gap_event_identity,
        reason_codes=canonical_reasons,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )
    return SourceCoverageEvent(
        coverage_event_identity=canonical_sha256(values),
        previous_event_identity=(
            None if previous is None else previous.coverage_event_identity
        ),
        capability_identity=capability.capability_identity,
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        symbol=symbol,
        state=state,
        observed_at_ms=observed_at_ms,
        source_envelope_identity=source_envelope_identity,
        gap_event_identity=gap_event_identity,
        reason_codes=canonical_reasons,
    )


class SourceContractStore:
    """Append-only registry for source capability, envelope and coverage truth."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def initialize(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_contract_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_capabilities (
                    capability_identity TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS source_capabilities_context
                    ON source_capabilities(provider, source, channel);
                CREATE TABLE IF NOT EXISTS source_envelopes (
                    envelope_identity TEXT PRIMARY KEY,
                    capability_identity TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(capability_identity)
                        REFERENCES source_capabilities(capability_identity)
                );
                CREATE INDEX IF NOT EXISTS source_envelopes_context_time
                    ON source_envelopes(
                        provider, source, channel, symbol, ingested_at_ms
                    );
                CREATE TABLE IF NOT EXISTS source_coverage_events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coverage_event_identity TEXT UNIQUE NOT NULL,
                    previous_event_identity TEXT,
                    capability_identity TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(capability_identity)
                        REFERENCES source_capabilities(capability_identity)
                );
                CREATE INDEX IF NOT EXISTS source_coverage_context_time
                    ON source_coverage_events(
                        provider, source, channel, symbol, observed_at_ms
                    );
                """
            )
            envelope_columns = {
                str(row["name"])
                for row in db.execute(
                    "PRAGMA table_info(source_envelopes)"
                ).fetchall()
            }
            if "event_at_ms" not in envelope_columns:
                db.execute(
                    "ALTER TABLE source_envelopes "
                    "ADD COLUMN event_at_ms INTEGER"
                )
                legacy_rows = db.execute(
                    "SELECT envelope_identity, payload_json "
                    "FROM source_envelopes"
                ).fetchall()
                for legacy_row in legacy_rows:
                    payload = _json_object(
                        str(legacy_row["payload_json"]),
                        "source envelope",
                    )
                    db.execute(
                        "UPDATE source_envelopes SET event_at_ms=? "
                        "WHERE envelope_identity=?",
                        (
                            int(payload["event_at_ms"]),
                            str(legacy_row["envelope_identity"]),
                        ),
                    )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS source_envelopes_context_pit
                ON source_envelopes(
                    provider, source, channel, symbol,
                    ingested_at_ms, event_at_ms
                )
                """
            )
            missing_event_time = db.execute(
                "SELECT COUNT(*) FROM source_envelopes "
                "WHERE event_at_ms IS NULL"
            ).fetchone()
            if (
                missing_event_time is not None
                and int(missing_event_time[0]) != 0
            ):
                raise ValueError(
                    "source envelope PIT event-time migration incomplete"
                )

            row = db.execute(
                "SELECT value FROM source_contract_meta "
                "WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO source_contract_meta(key, value) VALUES (?, ?)",
                    ("schema_version", SOURCE_CONTRACT_SCHEMA_VERSION),
                )
            elif str(row["value"]) != SOURCE_CONTRACT_SCHEMA_VERSION:
                raise ValueError("source contract schema mismatch")
        self._initialized = True

    def append_capability(self, capability: SourceCapability) -> None:
        self.initialize()
        payload = canonical_json(_capability_payload(capability))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload_json FROM source_capabilities "
                "WHERE capability_identity=?",
                (capability.capability_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("source capability identity conflict")
                return
            db.execute(
                """
                INSERT INTO source_capabilities(
                    capability_identity, provider, source, channel, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    capability.capability_identity,
                    capability.provider,
                    capability.source,
                    capability.channel,
                    payload,
                ),
            )

    def append_envelope(self, envelope: SourceEnvelope) -> None:
        self.initialize()
        payload = canonical_json(_envelope_payload(envelope))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            capability = db.execute(
                "SELECT payload_json FROM source_capabilities "
                "WHERE capability_identity=?",
                (envelope.capability_identity,),
            ).fetchone()
            if capability is None:
                raise ValueError("source envelope references unknown capability")
            registered = _capability_from_payload(
                str(capability["payload_json"])
            )
            _require_envelope_matches_capability(registered, envelope)
            existing = db.execute(
                "SELECT payload_json FROM source_envelopes "
                "WHERE envelope_identity=?",
                (envelope.envelope_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("source envelope identity conflict")
                return
            db.execute(
                """
                INSERT INTO source_envelopes(
                    envelope_identity, capability_identity,
                    provider, source, channel, symbol,
                    event_at_ms, source_timestamp_ms,
                    observed_at_ms, ingested_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope.envelope_identity,
                    envelope.capability_identity,
                    envelope.provider,
                    envelope.source,
                    envelope.channel,
                    envelope.symbol,
                    envelope.event_at_ms,
                    envelope.source_timestamp_ms,
                    envelope.observed_at_ms,
                    envelope.ingested_at_ms,
                    payload,
                ),
            )

    def append_coverage(self, event: SourceCoverageEvent) -> None:
        self.initialize()
        payload = canonical_json(_coverage_payload(event))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            capability_row = db.execute(
                "SELECT payload_json FROM source_capabilities "
                "WHERE capability_identity=?",
                (event.capability_identity,),
            ).fetchone()
            if capability_row is None:
                raise ValueError("source coverage references unknown capability")
            capability = _capability_from_payload(
                str(capability_row["payload_json"])
            )
            if (
                event.provider,
                event.source,
                event.channel,
            ) != (
                capability.provider,
                capability.source,
                capability.channel,
            ):
                raise ValueError("source coverage capability context mismatch")
            if event.symbol not in capability.symbols:
                raise ValueError("source coverage symbol outside capability")
            if event.source_envelope_identity is not None:
                envelope_row = db.execute(
                    "SELECT payload_json FROM source_envelopes "
                    "WHERE envelope_identity=?",
                    (event.source_envelope_identity,),
                ).fetchone()
                if envelope_row is None:
                    raise ValueError(
                        "source coverage references unknown envelope"
                    )
                envelope = _envelope_from_payload(
                    str(envelope_row["payload_json"])
                )
                if (
                    envelope.provider,
                    envelope.source,
                    envelope.channel,
                    envelope.symbol,
                ) != (
                    event.provider,
                    event.source,
                    event.channel,
                    event.symbol,
                ):
                    raise ValueError("source coverage envelope context mismatch")
                if envelope.ingested_at_ms > event.observed_at_ms:
                    raise ValueError(
                        "source coverage cannot observe future ingestion"
                    )

            existing = db.execute(
                "SELECT payload_json FROM source_coverage_events "
                "WHERE coverage_event_identity=?",
                (event.coverage_event_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("source coverage identity conflict")
                return

            previous = db.execute(
                """
                SELECT coverage_event_identity, observed_at_ms
                FROM source_coverage_events
                WHERE provider=? AND source=? AND channel=? AND symbol=?
                ORDER BY sequence_id DESC
                LIMIT 1
                """,
                (
                    event.provider,
                    event.source,
                    event.channel,
                    event.symbol,
                ),
            ).fetchone()
            if previous is None:
                if event.previous_event_identity is not None:
                    raise ValueError(
                        "source coverage root cannot claim predecessor"
                    )
            else:
                if event.previous_event_identity != str(
                    previous["coverage_event_identity"]
                ):
                    raise ValueError(
                        "source coverage predecessor mismatch"
                    )
                if event.observed_at_ms < int(previous["observed_at_ms"]):
                    raise ValueError("source coverage time regressed")

            db.execute(
                """
                INSERT INTO source_coverage_events(
                    coverage_event_identity, previous_event_identity,
                    capability_identity, provider, source, channel, symbol,
                    state, observed_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.coverage_event_identity,
                    event.previous_event_identity,
                    event.capability_identity,
                    event.provider,
                    event.source,
                    event.channel,
                    event.symbol,
                    event.state.value,
                    event.observed_at_ms,
                    payload,
                ),
            )

    def latest_envelope_at(
        self,
        *,
        provider: str,
        source: str,
        channel: str,
        symbol: str,
        as_of_ms: int,
    ) -> SourceEnvelope | None:
        if as_of_ms < 0:
            raise ValueError("source envelope as-of cannot be negative")
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM source_envelopes
                WHERE provider=? AND source=? AND channel=? AND symbol=?
                  AND ingested_at_ms<=?
                ORDER BY ingested_at_ms DESC, event_at_ms DESC,
                         source_timestamp_ms DESC, envelope_identity DESC
                LIMIT 1
                """,
                (provider, source, channel, symbol, as_of_ms),
            ).fetchone()
        return None if row is None else _envelope_from_payload(
            str(row["payload_json"])
        )

    def coverage_at(
        self,
        *,
        provider: str,
        source: str,
        channel: str,
        symbol: str,
        as_of_ms: int,
    ) -> SourceCoverageEvent | None:
        if as_of_ms < 0:
            raise ValueError("source coverage as-of cannot be negative")
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM source_coverage_events
                WHERE provider=? AND source=? AND channel=? AND symbol=?
                  AND observed_at_ms<=?
                ORDER BY observed_at_ms DESC, sequence_id DESC
                LIMIT 1
                """,
                (provider, source, channel, symbol, as_of_ms),
            ).fetchone()
        return None if row is None else _coverage_from_payload(
            str(row["payload_json"])
        )

    def capability(
        self,
        capability_identity: str,
    ) -> SourceCapability | None:
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM source_capabilities "
                "WHERE capability_identity=?",
                (capability_identity,),
            ).fetchone()
        return None if row is None else _capability_from_payload(
            str(row["payload_json"])
        )

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect() as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _capability_payload(capability: SourceCapability) -> dict[str, object]:
    return _capability_payload_values(
        provider=capability.provider,
        source=capability.source,
        channel=capability.channel,
        transport=capability.transport,
        sequence_semantics=capability.sequence_semantics,
        supports_provider_event_id=capability.supports_provider_event_id,
        freshness_budget_ms=capability.freshness_budget_ms,
        symbols=capability.symbols,
        production_authority=capability.production_authority,
        real_capital=capability.real_capital,
    )


def _capability_payload_values(
    *,
    provider: str,
    source: str,
    channel: str,
    transport: SourceTransport,
    sequence_semantics: SourceSequenceSemantics,
    supports_provider_event_id: bool,
    freshness_budget_ms: int,
    symbols: tuple[str, ...],
    production_authority: bool,
    real_capital: int,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_CONTRACT_SCHEMA_VERSION,
        "provider": provider,
        "source": source,
        "channel": channel,
        "transport": transport,
        "sequence_semantics": sequence_semantics,
        "supports_provider_event_id": supports_provider_event_id,
        "freshness_budget_ms": freshness_budget_ms,
        "symbols": symbols,
        "production_authority": production_authority,
        "real_capital": real_capital,
    }


def _envelope_payload(envelope: SourceEnvelope) -> dict[str, object]:
    return _envelope_payload_values(
        capability_identity=envelope.capability_identity,
        provider=envelope.provider,
        source=envelope.source,
        channel=envelope.channel,
        symbol=envelope.symbol,
        provider_event_id=envelope.provider_event_id,
        provider_sequence=envelope.provider_sequence,
        event_at_ms=envelope.event_at_ms,
        source_timestamp_ms=envelope.source_timestamp_ms,
        observed_at_ms=envelope.observed_at_ms,
        ingested_at_ms=envelope.ingested_at_ms,
        raw_identity=envelope.raw_identity,
        normalized_identity=envelope.normalized_identity,
        production_authority=envelope.production_authority,
        real_capital=envelope.real_capital,
    )


def _envelope_payload_values(
    *,
    capability_identity: str,
    provider: str,
    source: str,
    channel: str,
    symbol: str,
    provider_event_id: str | None,
    provider_sequence: int | None,
    event_at_ms: int,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    raw_identity: str,
    normalized_identity: str | None,
    production_authority: bool,
    real_capital: int,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_CONTRACT_SCHEMA_VERSION,
        "capability_identity": capability_identity,
        "provider": provider,
        "source": source,
        "channel": channel,
        "symbol": symbol,
        "provider_event_id": provider_event_id,
        "provider_sequence": provider_sequence,
        "event_at_ms": event_at_ms,
        "source_timestamp_ms": source_timestamp_ms,
        "observed_at_ms": observed_at_ms,
        "ingested_at_ms": ingested_at_ms,
        "raw_identity": raw_identity,
        "normalized_identity": normalized_identity,
        "production_authority": production_authority,
        "real_capital": real_capital,
    }


def _coverage_payload(event: SourceCoverageEvent) -> dict[str, object]:
    return _coverage_payload_values(
        previous_event_identity=event.previous_event_identity,
        capability_identity=event.capability_identity,
        provider=event.provider,
        source=event.source,
        channel=event.channel,
        symbol=event.symbol,
        state=event.state,
        observed_at_ms=event.observed_at_ms,
        source_envelope_identity=event.source_envelope_identity,
        gap_event_identity=event.gap_event_identity,
        reason_codes=event.reason_codes,
        production_authority=event.production_authority,
        real_capital=event.real_capital,
    )


def _coverage_payload_values(
    *,
    previous_event_identity: str | None,
    capability_identity: str,
    provider: str,
    source: str,
    channel: str,
    symbol: str,
    state: SourceCoverageState,
    observed_at_ms: int,
    source_envelope_identity: str | None,
    gap_event_identity: str | None,
    reason_codes: tuple[str, ...],
    production_authority: bool,
    real_capital: int,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_CONTRACT_SCHEMA_VERSION,
        "previous_event_identity": previous_event_identity,
        "capability_identity": capability_identity,
        "provider": provider,
        "source": source,
        "channel": channel,
        "symbol": symbol,
        "state": state,
        "observed_at_ms": observed_at_ms,
        "source_envelope_identity": source_envelope_identity,
        "gap_event_identity": gap_event_identity,
        "reason_codes": reason_codes,
        "production_authority": production_authority,
        "real_capital": real_capital,
    }


def _capability_from_payload(payload_json: str) -> SourceCapability:
    payload = _json_object(payload_json, "source capability")
    values = _capability_payload_values(
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        transport=SourceTransport(str(payload["transport"])),
        sequence_semantics=SourceSequenceSemantics(
            str(payload["sequence_semantics"])
        ),
        supports_provider_event_id=bool(payload["supports_provider_event_id"]),
        freshness_budget_ms=int(payload["freshness_budget_ms"]),
        symbols=tuple(str(value) for value in payload["symbols"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )
    return SourceCapability(
        capability_identity=canonical_sha256(values),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        transport=SourceTransport(str(payload["transport"])),
        sequence_semantics=SourceSequenceSemantics(
            str(payload["sequence_semantics"])
        ),
        supports_provider_event_id=bool(payload["supports_provider_event_id"]),
        freshness_budget_ms=int(payload["freshness_budget_ms"]),
        symbols=tuple(str(value) for value in payload["symbols"]),
        schema_version=str(payload["schema_version"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _envelope_from_payload(payload_json: str) -> SourceEnvelope:
    payload = _json_object(payload_json, "source envelope")
    normalized = payload["normalized_identity"]
    values = _envelope_payload_values(
        capability_identity=str(payload["capability_identity"]),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        symbol=str(payload["symbol"]),
        provider_event_id=(
            None
            if payload["provider_event_id"] is None
            else str(payload["provider_event_id"])
        ),
        provider_sequence=(
            None
            if payload["provider_sequence"] is None
            else int(payload["provider_sequence"])
        ),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        raw_identity=str(payload["raw_identity"]),
        normalized_identity=None if normalized is None else str(normalized),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )
    return SourceEnvelope(
        envelope_identity=canonical_sha256(values),
        capability_identity=str(payload["capability_identity"]),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        symbol=str(payload["symbol"]),
        provider_event_id=(
            None
            if payload["provider_event_id"] is None
            else str(payload["provider_event_id"])
        ),
        provider_sequence=(
            None
            if payload["provider_sequence"] is None
            else int(payload["provider_sequence"])
        ),
        event_at_ms=int(payload["event_at_ms"]),
        source_timestamp_ms=int(payload["source_timestamp_ms"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        ingested_at_ms=int(payload["ingested_at_ms"]),
        raw_identity=str(payload["raw_identity"]),
        normalized_identity=None if normalized is None else str(normalized),
        schema_version=str(payload["schema_version"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _coverage_from_payload(payload_json: str) -> SourceCoverageEvent:
    payload = _json_object(payload_json, "source coverage")
    values = _coverage_payload_values(
        previous_event_identity=(
            None
            if payload["previous_event_identity"] is None
            else str(payload["previous_event_identity"])
        ),
        capability_identity=str(payload["capability_identity"]),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        symbol=str(payload["symbol"]),
        state=SourceCoverageState(str(payload["state"])),
        observed_at_ms=int(payload["observed_at_ms"]),
        source_envelope_identity=(
            None
            if payload["source_envelope_identity"] is None
            else str(payload["source_envelope_identity"])
        ),
        gap_event_identity=(
            None
            if payload["gap_event_identity"] is None
            else str(payload["gap_event_identity"])
        ),
        reason_codes=tuple(str(value) for value in payload["reason_codes"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )
    return SourceCoverageEvent(
        coverage_event_identity=canonical_sha256(values),
        previous_event_identity=(
            None
            if payload["previous_event_identity"] is None
            else str(payload["previous_event_identity"])
        ),
        capability_identity=str(payload["capability_identity"]),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        channel=str(payload["channel"]),
        symbol=str(payload["symbol"]),
        state=SourceCoverageState(str(payload["state"])),
        observed_at_ms=int(payload["observed_at_ms"]),
        source_envelope_identity=(
            None
            if payload["source_envelope_identity"] is None
            else str(payload["source_envelope_identity"])
        ),
        gap_event_identity=(
            None
            if payload["gap_event_identity"] is None
            else str(payload["gap_event_identity"])
        ),
        reason_codes=tuple(str(value) for value in payload["reason_codes"]),
        schema_version=str(payload["schema_version"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _require_envelope_matches_capability(
    capability: SourceCapability,
    envelope: SourceEnvelope,
) -> None:
    if envelope.capability_identity != capability.capability_identity:
        raise ValueError("source envelope capability identity mismatch")
    if (
        envelope.provider,
        envelope.source,
        envelope.channel,
    ) != (
        capability.provider,
        capability.source,
        capability.channel,
    ):
        raise ValueError("source envelope capability context mismatch")
    if envelope.symbol not in capability.symbols:
        raise ValueError("source envelope symbol outside capability")
    if capability.supports_provider_event_id and envelope.provider_event_id is None:
        raise ValueError("source envelope missing required provider event id")
    if (
        capability.sequence_semantics
        in {
            SourceSequenceSemantics.MONOTONIC,
            SourceSequenceSemantics.PROVIDER_UPDATE_ID,
        }
        and envelope.provider_sequence is None
    ):
        raise ValueError("source envelope missing required provider sequence")


def _json_object(payload_json: str, label: str) -> dict[str, Any]:
    value = json.loads(payload_json)
    if not isinstance(value, dict):
        raise TypeError(f"{label} payload must be object")
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
