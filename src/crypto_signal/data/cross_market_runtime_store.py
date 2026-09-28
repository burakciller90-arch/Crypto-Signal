from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from crypto_signal.data.cross_market import (
    CrossMarketDailyRecord,
    CrossMarketSeries,
    CrossMarketUnit,
    CrossMarketWindowObservation,
)
from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_json

CROSS_MARKET_RUNTIME_STORE_VERSION = "cross-market-runtime-store-v1/1"


@dataclass(frozen=True, slots=True)
class CrossMarketRuntimeCounts:
    vix_observations: int
    treasury_10y_observations: int

    @property
    def total(self) -> int:
        return self.vix_observations + self.treasury_10y_observations


class CrossMarketRuntimeStore:
    """Append-only PIT store for accepted cross-market observations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _connect_ro(self) -> sqlite3.Connection:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
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
                CREATE TABLE IF NOT EXISTS cross_market_runtime_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cross_market_window_observations (
                    observation_identity TEXT PRIMARY KEY,
                    series TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    latest_day_start_ms INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS cross_market_window_pit
                    ON cross_market_window_observations(
                        series, observed_at_ms, latest_day_start_ms,
                        observation_identity
                    );

                CREATE TRIGGER IF NOT EXISTS cross_market_window_no_update
                BEFORE UPDATE ON cross_market_window_observations
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'immutable cross-market runtime record'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS cross_market_window_no_delete
                BEFORE DELETE ON cross_market_window_observations
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'immutable cross-market runtime record'
                    );
                END;
                """
            )
            row = db.execute(
                "SELECT value FROM cross_market_runtime_meta "
                "WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO cross_market_runtime_meta(key, value) "
                    "VALUES (?, ?)",
                    ("schema_version", CROSS_MARKET_RUNTIME_STORE_VERSION),
                )
            elif str(row["value"]) != CROSS_MARKET_RUNTIME_STORE_VERSION:
                raise ValueError("cross-market runtime store schema mismatch")
        self._initialized = True

    def append_observation(
        self,
        observation: CrossMarketWindowObservation,
    ) -> bool:
        self.initialize()
        payload = canonical_json(_observation_storage_payload(observation))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload_json FROM cross_market_window_observations "
                "WHERE observation_identity=?",
                (observation.observation_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("cross-market observation identity conflict")
                return False
            db.execute(
                """
                INSERT INTO cross_market_window_observations(
                    observation_identity, series, observed_at_ms,
                    latest_day_start_ms, source, adapter_version, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_identity,
                    observation.series.value,
                    observation.observed_at_ms,
                    observation.records[-1].day_start_ms,
                    observation.source.value,
                    observation.adapter_version,
                    payload,
                ),
            )
        return True

    def observations_as_of(
        self,
        *,
        series: CrossMarketSeries,
        as_of_ms: int,
        limit: int = 64,
    ) -> tuple[CrossMarketWindowObservation, ...]:
        if as_of_ms < 0:
            raise ValueError("cross-market as-of cannot be negative")
        if limit <= 0 or limit > 256:
            raise ValueError("cross-market observation limit must be 1..256")
        if not self.path.is_file():
            return ()
        with self._connect_ro() as db:
            rows = db.execute(
                """
                SELECT payload_json
                FROM cross_market_window_observations
                WHERE series=? AND observed_at_ms<=?
                ORDER BY observed_at_ms DESC, observation_identity DESC
                LIMIT ?
                """,
                (series.value, as_of_ms, limit),
            ).fetchall()
        return tuple(
            reversed(
                tuple(
                    _observation_from_storage_payload(str(row["payload_json"]))
                    for row in rows
                )
            )
        )

    def latest_observation_as_of(
        self,
        *,
        series: CrossMarketSeries,
        as_of_ms: int,
    ) -> CrossMarketWindowObservation | None:
        observations = self.observations_as_of(
            series=series,
            as_of_ms=as_of_ms,
            limit=1,
        )
        return observations[-1] if observations else None

    def counts(self) -> CrossMarketRuntimeCounts:
        if not self.path.is_file():
            return CrossMarketRuntimeCounts(0, 0)
        with self._connect_ro() as db:
            rows = db.execute(
                """
                SELECT series, COUNT(*) AS count
                FROM cross_market_window_observations
                GROUP BY series
                """
            ).fetchall()
        by_series = {str(row["series"]): int(row["count"]) for row in rows}
        return CrossMarketRuntimeCounts(
            vix_observations=by_series.get(
                CrossMarketSeries.CBOE_VIX_CLOSE.value,
                0,
            ),
            treasury_10y_observations=by_series.get(
                CrossMarketSeries.US_TREASURY_10Y_YIELD.value,
                0,
            ),
        )

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect_ro() as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def _observation_storage_payload(
    observation: CrossMarketWindowObservation,
) -> dict[str, object]:
    return {
        "observation_identity": observation.observation_identity,
        "series": observation.series,
        "unit": observation.unit,
        "observed_at_ms": observation.observed_at_ms,
        "records": [
            {
                "record_identity": record.record_identity,
                "series": record.series,
                "unit": record.unit,
                "day_start_ms": record.day_start_ms,
                "value": record.value,
            }
            for record in observation.records
        ],
        "source": observation.source,
        "adapter_version": observation.adapter_version,
        "temporal_semantic": observation.temporal_semantic,
    }


def _observation_from_storage_payload(
    payload_json: str,
) -> CrossMarketWindowObservation:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("cross-market persisted payload must be an object")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise TypeError("cross-market persisted records must be an array")
    records = tuple(
        CrossMarketDailyRecord(
            record_identity=str(item["record_identity"]),
            series=CrossMarketSeries(str(item["series"])),
            unit=CrossMarketUnit(str(item["unit"])),
            day_start_ms=int(item["day_start_ms"]),
            value=Decimal(str(item["value"])),
        )
        for item in raw_records
        if isinstance(item, dict)
    )
    if len(records) != len(raw_records):
        raise TypeError("cross-market persisted record must be an object")
    return CrossMarketWindowObservation(
        observation_identity=str(payload["observation_identity"]),
        series=CrossMarketSeries(str(payload["series"])),
        unit=CrossMarketUnit(str(payload["unit"])),
        observed_at_ms=int(payload["observed_at_ms"]),
        records=records,
        source=DataSource(str(payload["source"])),
        adapter_version=str(payload["adapter_version"]),
        temporal_semantic=str(payload["temporal_semantic"]),
    )
