from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import cast

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.data.options import (
    OptionContractQuote,
    OptionInstrumentSpec,
    OptionSurfaceObservation,
    OptionType,
    build_option_instrument_metadata_identity,
)
from crypto_signal.ledger.serialization import canonical_json

OPTIONS_SURFACE_STORE_VERSION = "options-surface-store-v1/1"


class OptionsSurfaceStore:
    """Append-only PIT store for exact option metadata and surface snapshots."""

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
                CREATE TABLE IF NOT EXISTS options_surface_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS option_instrument_specs (
                    instrument_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    base_coin TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    expiry_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS option_instrument_specs_context
                    ON option_instrument_specs(
                        exchange, base_coin, symbol, ingested_at_ms
                    );
                CREATE TABLE IF NOT EXISTS option_instrument_metadata (
                    metadata_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    base_coin TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS option_surface_snapshots (
                    surface_identity TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    base_coin TEXT NOT NULL,
                    source_timestamp_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS option_surface_snapshots_context_pit
                    ON option_surface_snapshots(
                        exchange, base_coin, ingested_at_ms,
                        source_timestamp_ms, surface_identity
                    );
                """
            )
            row = db.execute(
                "SELECT value FROM options_surface_meta "
                "WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO options_surface_meta(key, value) VALUES (?, ?)",
                    ("schema_version", OPTIONS_SURFACE_STORE_VERSION),
                )
            elif str(row["value"]) != OPTIONS_SURFACE_STORE_VERSION:
                raise ValueError("options surface store schema mismatch")
        self._initialized = True

    def append_snapshot(
        self,
        *,
        instrument_specs: tuple[OptionInstrumentSpec, ...],
        surface: OptionSurfaceObservation,
    ) -> None:
        self.initialize()
        metadata_identity = build_option_instrument_metadata_identity(
            exchange=surface.exchange,
            base_coin=surface.base_coin,
            instrument_specs=instrument_specs,
        )
        if metadata_identity != surface.instrument_metadata_identity:
            raise ValueError("option surface instrument metadata identity mismatch")

        specs_by_identity = {
            item.instrument_identity: item for item in instrument_specs
        }
        if len(specs_by_identity) != len(instrument_specs):
            raise ValueError("option surface instrument metadata duplicated")
        for quote in surface.contracts:
            instrument = specs_by_identity.get(quote.instrument_identity)
            if instrument is None:
                raise ValueError("option quote missing exact instrument metadata")
            if (
                quote.exchange is not instrument.exchange
                or quote.symbol != instrument.symbol
                or quote.base_coin != instrument.base_coin
                or quote.option_type is not instrument.option_type
                or quote.strike != instrument.strike
                or quote.expiry_at_ms != instrument.expiry_at_ms
            ):
                raise ValueError("option quote conflicts with instrument metadata")

        canonical_specs = tuple(
            sorted(instrument_specs, key=lambda item: item.instrument_identity)
        )
        metadata_payload = canonical_json(
            {
                "base_coin": surface.base_coin,
                "exchange": surface.exchange,
                "instrument_identities": tuple(
                    item.instrument_identity for item in canonical_specs
                ),
            }
        )
        surface_payload = canonical_json(surface)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for instrument in canonical_specs:
                payload = canonical_json(instrument)
                existing = db.execute(
                    "SELECT payload_json FROM option_instrument_specs "
                    "WHERE instrument_identity=?",
                    (instrument.instrument_identity,),
                ).fetchone()
                if existing is not None:
                    if str(existing["payload_json"]) != payload:
                        raise ValueError("option instrument identity conflict")
                    continue
                db.execute(
                    """
                    INSERT INTO option_instrument_specs(
                        instrument_identity, exchange, base_coin, symbol,
                        expiry_at_ms, ingested_at_ms, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        instrument.instrument_identity,
                        instrument.exchange.value,
                        instrument.base_coin,
                        instrument.symbol,
                        instrument.expiry_at_ms,
                        instrument.ingested_at_ms,
                        payload,
                    ),
                )

            metadata_existing = db.execute(
                "SELECT payload_json FROM option_instrument_metadata "
                "WHERE metadata_identity=?",
                (metadata_identity,),
            ).fetchone()
            if metadata_existing is not None:
                if str(metadata_existing["payload_json"]) != metadata_payload:
                    raise ValueError("option instrument metadata identity conflict")
            else:
                db.execute(
                    """
                    INSERT INTO option_instrument_metadata(
                        metadata_identity, exchange, base_coin, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        metadata_identity,
                        surface.exchange.value,
                        surface.base_coin,
                        metadata_payload,
                    ),
                )

            surface_existing = db.execute(
                "SELECT payload_json FROM option_surface_snapshots "
                "WHERE surface_identity=?",
                (surface.surface_identity,),
            ).fetchone()
            if surface_existing is not None:
                if str(surface_existing["payload_json"]) != surface_payload:
                    raise ValueError("option surface identity conflict")
                return
            db.execute(
                """
                INSERT INTO option_surface_snapshots(
                    surface_identity, exchange, base_coin,
                    source_timestamp_ms, observed_at_ms, ingested_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    surface.surface_identity,
                    surface.exchange.value,
                    surface.base_coin,
                    surface.source_timestamp_ms,
                    surface.observed_at_ms,
                    surface.ingested_at_ms,
                    surface_payload,
                ),
            )

    def surface(self, surface_identity: str) -> OptionSurfaceObservation | None:
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM option_surface_snapshots "
                "WHERE surface_identity=?",
                (surface_identity,),
            ).fetchone()
        if row is None:
            return None
        return _surface_from_payload(str(row["payload_json"]))

    def latest_surface_as_of(
        self,
        *,
        exchange: Exchange,
        base_coin: str,
        as_of_ms: int,
    ) -> OptionSurfaceObservation | None:
        if as_of_ms < 0:
            raise ValueError("option surface as-of cannot be negative")
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT payload_json
                FROM option_surface_snapshots
                WHERE exchange=? AND base_coin=? AND ingested_at_ms<=?
                ORDER BY ingested_at_ms DESC, source_timestamp_ms DESC,
                         surface_identity DESC
                LIMIT 1
                """,
                (exchange.value, base_coin, as_of_ms),
            ).fetchone()
        if row is None:
            return None
        return _surface_from_payload(str(row["payload_json"]))

    def instrument_specs_for_metadata(
        self,
        metadata_identity: str,
    ) -> tuple[OptionInstrumentSpec, ...]:
        if not self.path.is_file():
            return ()
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM option_instrument_metadata "
                "WHERE metadata_identity=?",
                (metadata_identity,),
            ).fetchone()
            if row is None:
                return ()
            payload = _json_object(
                str(row["payload_json"]),
                "option instrument metadata",
            )
            identities = cast(list[object], payload["instrument_identities"])
            specs: list[OptionInstrumentSpec] = []
            for identity in identities:
                spec_row = db.execute(
                    "SELECT payload_json FROM option_instrument_specs "
                    "WHERE instrument_identity=?",
                    (str(identity),),
                ).fetchone()
                if spec_row is None:
                    raise ValueError(
                        "option instrument metadata references missing instrument"
                    )
                specs.append(
                    _instrument_from_payload(str(spec_row["payload_json"]))
                )
        return tuple(specs)

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect() as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _instrument_from_payload(payload_json: str) -> OptionInstrumentSpec:
    payload = _json_object(payload_json, "option instrument")
    return OptionInstrumentSpec(
        instrument_identity=str(payload["instrument_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        symbol=str(payload["symbol"]),
        base_coin=str(payload["base_coin"]),
        quote_coin=str(payload["quote_coin"]),
        settle_coin=str(payload["settle_coin"]),
        option_type=OptionType(str(payload["option_type"])),
        strike=Decimal(str(payload["strike"])),
        expiry_at_ms=int(cast(int | str, payload["expiry_at_ms"])),
        status=str(payload["status"]),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(
            cast(int | str, payload["source_timestamp_ms"])
        ),
        observed_at_ms=int(cast(int | str, payload["observed_at_ms"])),
        ingested_at_ms=int(cast(int | str, payload["ingested_at_ms"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _quote_from_payload(payload: dict[str, object]) -> OptionContractQuote:
    def decimal_or_none(key: str) -> Decimal | None:
        value = payload.get(key)
        return None if value is None else Decimal(str(value))

    return OptionContractQuote(
        quote_identity=str(payload["quote_identity"]),
        instrument_identity=str(payload["instrument_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        symbol=str(payload["symbol"]),
        base_coin=str(payload["base_coin"]),
        option_type=OptionType(str(payload["option_type"])),
        strike=Decimal(str(payload["strike"])),
        expiry_at_ms=int(cast(int | str, payload["expiry_at_ms"])),
        mark_iv=decimal_or_none("mark_iv"),
        bid_iv=decimal_or_none("bid_iv"),
        ask_iv=decimal_or_none("ask_iv"),
        mark_price=decimal_or_none("mark_price"),
        index_price=decimal_or_none("index_price"),
        underlying_price=decimal_or_none("underlying_price"),
        delta=decimal_or_none("delta"),
        gamma=decimal_or_none("gamma"),
        vega=decimal_or_none("vega"),
        theta=decimal_or_none("theta"),
        open_interest=decimal_or_none("open_interest"),
        volume_24h=decimal_or_none("volume_24h"),
        turnover_24h=decimal_or_none("turnover_24h"),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(
            cast(int | str, payload["source_timestamp_ms"])
        ),
        observed_at_ms=int(cast(int | str, payload["observed_at_ms"])),
        ingested_at_ms=int(cast(int | str, payload["ingested_at_ms"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _surface_from_payload(payload_json: str) -> OptionSurfaceObservation:
    payload = _json_object(payload_json, "option surface")
    raw_contracts = cast(list[dict[str, object]], payload["contracts"])
    return OptionSurfaceObservation(
        surface_identity=str(payload["surface_identity"]),
        exchange=Exchange(str(payload["exchange"])),
        base_coin=str(payload["base_coin"]),
        instrument_metadata_identity=str(
            payload["instrument_metadata_identity"]
        ),
        contracts=tuple(_quote_from_payload(item) for item in raw_contracts),
        source=DataSource(str(payload["source"])),
        source_timestamp_ms=int(
            cast(int | str, payload["source_timestamp_ms"])
        ),
        observed_at_ms=int(cast(int | str, payload["observed_at_ms"])),
        ingested_at_ms=int(cast(int | str, payload["ingested_at_ms"])),
        adapter_version=str(payload["adapter_version"]),
    )


def _json_object(payload_json: str, label: str) -> dict[str, object]:
    decoded = json.loads(payload_json)
    if not isinstance(decoded, dict):
        raise TypeError(f"{label} payload must be a JSON object")
    return cast(dict[str, object], decoded)
