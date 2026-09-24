from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.data.health import assess_freshness, detect_gaps
from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.reconciliation import reconcile_candle_grids
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

PROVIDER_DIVERGENCE_SCHEMA_VERSION = "provider-divergence-v1/1"
PROVIDER_DIVERGENCE_SEMANTIC = "spot_candle_close_grid_divergence"
REAL_CAPITAL = 0

_CANDLE_COLUMNS = frozenset(
    {
        "exchange",
        "market_type",
        "symbol",
        "timeframe",
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "is_closed",
        "source",
        "source_timestamp_ms",
        "ingested_at_ms",
        "adapter_version",
    }
)


class ProviderGridState(StrEnum):
    FULL_OVERLAP = "full_overlap"
    PARTIAL_OVERLAP = "partial_overlap"
    NO_OVERLAP = "no_overlap"


@dataclass(frozen=True, slots=True)
class ProviderQualityEvidence:
    exchange: Exchange
    available: bool
    consumed_closed_candles: int
    latest_open_time_ms: int | None
    latest_source_age_ms: int | None
    latest_closed_age_ms: int | None
    stale: bool
    freshness_reasons: tuple[str, ...]
    gap_count: int
    gap_missing_candles: int

    def __post_init__(self) -> None:
        if self.consumed_closed_candles < 0:
            raise ValueError("provider candle count cannot be negative")
        if self.gap_count < 0 or self.gap_missing_candles < 0:
            raise ValueError("provider gap counts cannot be negative")
        if self.available != (self.consumed_closed_candles > 0):
            raise ValueError("provider availability/count mismatch")
        if self.latest_open_time_ms is not None and self.latest_open_time_ms < 0:
            raise ValueError("provider latest open cannot be negative")
        for age in (self.latest_source_age_ms, self.latest_closed_age_ms):
            if age is not None and age < 0:
                raise ValueError("provider freshness age cannot be negative")
        if self.freshness_reasons != tuple(sorted(set(self.freshness_reasons))):
            raise ValueError("provider freshness reasons must be canonical")
        if not self.available:
            if self.latest_open_time_ms is not None:
                raise ValueError("unavailable provider cannot have latest open")
            if self.latest_source_age_ms is not None:
                raise ValueError("unavailable provider cannot have source age")
            if self.latest_closed_age_ms is not None:
                raise ValueError("unavailable provider cannot have closed age")
            if not self.stale or "no_candles" not in self.freshness_reasons:
                raise ValueError("unavailable provider must fail closed")


@dataclass(frozen=True, slots=True)
class ProviderSpreadPoint:
    open_time_ms: int
    left_candle_identity: str
    right_candle_identity: str
    spread_bps: Decimal
    absolute_spread_bps: Decimal

    def __post_init__(self) -> None:
        if self.open_time_ms < 0:
            raise ValueError("provider spread open time cannot be negative")
        _require_sha256(self.left_candle_identity, "left candle identity")
        _require_sha256(self.right_candle_identity, "right candle identity")
        if self.absolute_spread_bps < 0:
            raise ValueError("absolute provider spread cannot be negative")
        if abs(self.spread_bps) != self.absolute_spread_bps:
            raise ValueError("provider absolute spread mismatch")


@dataclass(frozen=True, slots=True)
class ProviderDivergenceSnapshot:
    snapshot_identity: str
    semantic: str
    market_type: MarketType
    symbol: str
    timeframe: str
    observed_at_ms: int
    lookback_limit: int
    left_exchange: Exchange
    right_exchange: Exchange
    left_quality: ProviderQualityEvidence
    right_quality: ProviderQualityEvidence
    left_source_evidence_identities: tuple[str, ...]
    right_source_evidence_identities: tuple[str, ...]
    overlap_count: int
    left_only_open_times_ms: tuple[int, ...]
    right_only_open_times_ms: tuple[int, ...]
    spread_points: tuple[ProviderSpreadPoint, ...]
    latest_overlap_open_time_ms: int | None
    latest_close_spread_bps: Decimal | None
    median_absolute_close_spread_bps: Decimal | None
    max_absolute_close_spread_bps: Decimal | None
    grid_state: ProviderGridState
    schema_version: str = PROVIDER_DIVERGENCE_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "provider divergence snapshot")
        if self.semantic != PROVIDER_DIVERGENCE_SEMANTIC:
            raise ValueError("unsupported provider divergence semantic")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("provider divergence symbol must be uppercase")
        if not self.timeframe.strip():
            raise ValueError("provider divergence timeframe must be non-empty")
        if self.observed_at_ms < 0:
            raise ValueError("provider divergence observation time cannot be negative")
        if self.lookback_limit <= 0:
            raise ValueError("provider divergence lookback must be positive")
        if self.left_exchange.value >= self.right_exchange.value:
            raise ValueError("provider pair must use canonical exchange ordering")
        if self.left_quality.exchange is not self.left_exchange:
            raise ValueError("left quality exchange mismatch")
        if self.right_quality.exchange is not self.right_exchange:
            raise ValueError("right quality exchange mismatch")
        for identities in (
            self.left_source_evidence_identities,
            self.right_source_evidence_identities,
        ):
            if len(set(identities)) != len(identities):
                raise ValueError("provider source evidence identities must be unique")
            for identity in identities:
                _require_sha256(identity, "provider source evidence identity")
        if self.overlap_count < 0:
            raise ValueError("provider overlap count cannot be negative")
        if self.overlap_count != len(self.spread_points):
            raise ValueError("provider overlap/spread point mismatch")
        if tuple(sorted(self.left_only_open_times_ms)) != self.left_only_open_times_ms:
            raise ValueError("left-only opens must be sorted")
        if tuple(sorted(self.right_only_open_times_ms)) != self.right_only_open_times_ms:
            raise ValueError("right-only opens must be sorted")
        if self.spread_points != tuple(
            sorted(self.spread_points, key=lambda item: item.open_time_ms)
        ):
            raise ValueError("provider spread points must be sorted")

        if self.overlap_count == 0:
            if self.grid_state is not ProviderGridState.NO_OVERLAP:
                raise ValueError("zero overlap must be NO_OVERLAP")
            if any(
                value is not None
                for value in (
                    self.latest_overlap_open_time_ms,
                    self.latest_close_spread_bps,
                    self.median_absolute_close_spread_bps,
                    self.max_absolute_close_spread_bps,
                )
            ):
                raise ValueError("no-overlap snapshot cannot expose spread metrics")
        else:
            expected_state = (
                ProviderGridState.FULL_OVERLAP
                if not self.left_only_open_times_ms
                and not self.right_only_open_times_ms
                else ProviderGridState.PARTIAL_OVERLAP
            )
            if self.grid_state is not expected_state:
                raise ValueError("provider grid state mismatch")
            if self.latest_overlap_open_time_ms != self.spread_points[-1].open_time_ms:
                raise ValueError("latest overlap open mismatch")
            if self.latest_close_spread_bps != self.spread_points[-1].spread_bps:
                raise ValueError("latest provider spread mismatch")
            if self.median_absolute_close_spread_bps is None:
                raise ValueError("overlap requires median spread")
            if self.max_absolute_close_spread_bps is None:
                raise ValueError("overlap requires max spread")

        if self.schema_version != PROVIDER_DIVERGENCE_SCHEMA_VERSION:
            raise ValueError("unsupported provider divergence schema")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("provider divergence cannot grant authority")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("provider divergence snapshot identity mismatch")


def candle_evidence_identity(candle: Candle) -> str:
    return canonical_sha256(_candle_payload(candle))


def build_provider_divergence_snapshot(
    *,
    market_type: MarketType,
    symbol: str,
    timeframe: str,
    observed_at_ms: int,
    left_exchange: Exchange,
    right_exchange: Exchange,
    left_candles: tuple[Candle, ...],
    right_candles: tuple[Candle, ...],
    lookback_limit: int = 96,
) -> ProviderDivergenceSnapshot:
    if observed_at_ms < 0:
        raise ValueError("provider divergence observation time cannot be negative")
    if lookback_limit <= 0 or lookback_limit > 10_000:
        raise ValueError("provider divergence lookback must be inside 1..10000")
    if left_exchange.value >= right_exchange.value:
        raise ValueError("provider pair must use canonical exchange ordering")
    if not symbol or symbol != symbol.upper():
        raise ValueError("provider divergence symbol must be uppercase")
    if not timeframe.strip():
        raise ValueError("provider divergence timeframe must be non-empty")

    left = _prepare_provider_candles(
        candles=left_candles,
        exchange=left_exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        observed_at_ms=observed_at_ms,
        lookback_limit=lookback_limit,
    )
    right = _prepare_provider_candles(
        candles=right_candles,
        exchange=right_exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        observed_at_ms=observed_at_ms,
        lookback_limit=lookback_limit,
    )

    left_quality = _provider_quality(
        left,
        exchange=left_exchange,
        timeframe=timeframe,
        observed_at_ms=observed_at_ms,
    )
    right_quality = _provider_quality(
        right,
        exchange=right_exchange,
        timeframe=timeframe,
        observed_at_ms=observed_at_ms,
    )
    reconciliation = reconcile_candle_grids(left, right)

    left_by_open = {item.open_time_ms: item for item in left}
    right_by_open = {item.open_time_ms: item for item in right}
    points = tuple(
        ProviderSpreadPoint(
            open_time_ms=item.open_time_ms,
            left_candle_identity=candle_evidence_identity(
                left_by_open[item.open_time_ms]
            ),
            right_candle_identity=candle_evidence_identity(
                right_by_open[item.open_time_ms]
            ),
            spread_bps=item.spread_bps,
            absolute_spread_bps=abs(item.spread_bps),
        )
        for item in reconciliation.spreads
    )

    if points:
        absolute = tuple(point.absolute_spread_bps for point in points)
        latest_overlap_open_time_ms = points[-1].open_time_ms
        latest_close_spread_bps = points[-1].spread_bps
        median_absolute_close_spread_bps = _decimal_median(absolute)
        max_absolute_close_spread_bps = max(absolute)
        grid_state = (
            ProviderGridState.FULL_OVERLAP
            if not reconciliation.left_only_open_times_ms
            and not reconciliation.right_only_open_times_ms
            else ProviderGridState.PARTIAL_OVERLAP
        )
    else:
        latest_overlap_open_time_ms = None
        latest_close_spread_bps = None
        median_absolute_close_spread_bps = None
        max_absolute_close_spread_bps = None
        grid_state = ProviderGridState.NO_OVERLAP

    values = {
        "semantic": PROVIDER_DIVERGENCE_SEMANTIC,
        "market_type": market_type,
        "symbol": symbol,
        "timeframe": timeframe,
        "observed_at_ms": observed_at_ms,
        "lookback_limit": lookback_limit,
        "left_exchange": left_exchange,
        "right_exchange": right_exchange,
        "left_quality": left_quality,
        "right_quality": right_quality,
        "left_source_evidence_identities": tuple(
            candle_evidence_identity(item) for item in left
        ),
        "right_source_evidence_identities": tuple(
            candle_evidence_identity(item) for item in right
        ),
        "overlap_count": reconciliation.overlap_count,
        "left_only_open_times_ms": reconciliation.left_only_open_times_ms,
        "right_only_open_times_ms": reconciliation.right_only_open_times_ms,
        "spread_points": points,
        "latest_overlap_open_time_ms": latest_overlap_open_time_ms,
        "latest_close_spread_bps": latest_close_spread_bps,
        "median_absolute_close_spread_bps": median_absolute_close_spread_bps,
        "max_absolute_close_spread_bps": max_absolute_close_spread_bps,
        "grid_state": grid_state,
        "schema_version": PROVIDER_DIVERGENCE_SCHEMA_VERSION,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return ProviderDivergenceSnapshot(
        snapshot_identity=canonical_sha256(values),
        semantic=PROVIDER_DIVERGENCE_SEMANTIC,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        observed_at_ms=observed_at_ms,
        lookback_limit=lookback_limit,
        left_exchange=left_exchange,
        right_exchange=right_exchange,
        left_quality=left_quality,
        right_quality=right_quality,
        left_source_evidence_identities=tuple(
            candle_evidence_identity(item) for item in left
        ),
        right_source_evidence_identities=tuple(
            candle_evidence_identity(item) for item in right
        ),
        overlap_count=reconciliation.overlap_count,
        left_only_open_times_ms=reconciliation.left_only_open_times_ms,
        right_only_open_times_ms=reconciliation.right_only_open_times_ms,
        spread_points=points,
        latest_overlap_open_time_ms=latest_overlap_open_time_ms,
        latest_close_spread_bps=latest_close_spread_bps,
        median_absolute_close_spread_bps=median_absolute_close_spread_bps,
        max_absolute_close_spread_bps=max_absolute_close_spread_bps,
        grid_state=grid_state,
        schema_version=PROVIDER_DIVERGENCE_SCHEMA_VERSION,
        production_authority=False,
        real_capital=REAL_CAPITAL,
    )


class ProviderDivergenceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_divergence_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_divergence_snapshots (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_identity TEXT UNIQUE NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    left_exchange TEXT NOT NULL,
                    right_exchange TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS provider_divergence_context
                    ON provider_divergence_snapshots(
                        market_type, symbol, timeframe, observed_at_ms
                    );
                CREATE TRIGGER IF NOT EXISTS provider_divergence_no_update
                BEFORE UPDATE ON provider_divergence_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'provider divergence snapshots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS provider_divergence_no_delete
                BEFORE DELETE ON provider_divergence_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'provider divergence snapshots are append-only');
                END;
                """
            )
            row = db.execute(
                "SELECT value FROM provider_divergence_meta "
                "WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO provider_divergence_meta(key, value) "
                    "VALUES (?, ?)",
                    ("schema_version", PROVIDER_DIVERGENCE_SCHEMA_VERSION),
                )
            elif str(row[0]) != PROVIDER_DIVERGENCE_SCHEMA_VERSION:
                raise ValueError("provider divergence schema mismatch")

    def append(self, snapshot: ProviderDivergenceSnapshot) -> None:
        self.initialize()
        payload = canonical_json(_snapshot_payload(snapshot))
        with sqlite3.connect(self.path) as db:
            existing = db.execute(
                "SELECT payload_json FROM provider_divergence_snapshots "
                "WHERE snapshot_identity=?",
                (snapshot.snapshot_identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("provider divergence identity conflict")
                return
            db.execute(
                """
                INSERT INTO provider_divergence_snapshots(
                    snapshot_identity, market_type, symbol, timeframe,
                    observed_at_ms, left_exchange, right_exchange, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_identity,
                    snapshot.market_type.value,
                    snapshot.symbol,
                    snapshot.timeframe,
                    snapshot.observed_at_ms,
                    snapshot.left_exchange.value,
                    snapshot.right_exchange.value,
                    payload,
                ),
            )

    def latest(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        timeframe: str,
    ) -> ProviderDivergenceSnapshot | None:
        if not self.path.is_file():
            return None
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                """
                SELECT snapshot_identity, payload_json
                FROM provider_divergence_snapshots
                WHERE market_type=? AND symbol=? AND timeframe=?
                ORDER BY observed_at_ms DESC, sequence_id DESC
                LIMIT 1
                """,
                (market_type.value, symbol, timeframe),
            ).fetchone()
        if row is None:
            return None
        return _snapshot_from_payload(str(row[0]), str(row[1]))

    def count(self) -> int:
        if not self.path.is_file():
            return 0
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT COUNT(*) FROM provider_divergence_snapshots"
            ).fetchone()
        return 0 if row is None else int(row[0])

    def quick_check(self) -> bool:
        if not self.path.is_file():
            return False
        with sqlite3.connect(self.path) as db:
            row = db.execute("PRAGMA quick_check").fetchone()
        return row is not None and str(row[0]).lower() == "ok"


def read_candles_read_only(
    path: Path,
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    timeframe: str,
) -> tuple[Candle, ...]:
    if not path.is_file():
        raise ValueError("canonical candle database missing")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        quick = db.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("canonical candle database quick_check failed")
        table = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='candles'"
        ).fetchone()
        if table is None:
            raise ValueError("canonical candle table missing")
        columns = {
            str(row[1])
            for row in db.execute("PRAGMA table_info(candles)").fetchall()
        }
        missing = _CANDLE_COLUMNS - columns
        if missing:
            raise ValueError(
                "canonical candle columns missing: " + ",".join(sorted(missing))
            )
        rows = db.execute(
            """
            SELECT * FROM candles
            WHERE exchange=? AND market_type=? AND symbol=? AND timeframe=?
            ORDER BY open_time_ms ASC
            """,
            (exchange.value, market_type.value, symbol, timeframe),
        ).fetchall()
    return tuple(_candle_from_row(row) for row in rows)


def _prepare_provider_candles(
    *,
    candles: tuple[Candle, ...],
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    timeframe: str,
    observed_at_ms: int,
    lookback_limit: int,
) -> tuple[Candle, ...]:
    eligible: list[Candle] = []
    for candle in candles:
        if (
            candle.exchange is not exchange
            or candle.market_type is not market_type
            or candle.symbol != symbol
            or candle.timeframe != timeframe
        ):
            raise ValueError("provider candle context mismatch")
        if (
            not candle.is_closed
            or candle.close_time_ms > observed_at_ms
            or candle.source_timestamp_ms > observed_at_ms
            or candle.ingested_at_ms > observed_at_ms
        ):
            continue
        eligible.append(candle)

    ordered = tuple(sorted(eligible, key=lambda item: item.open_time_ms))
    opens = tuple(item.open_time_ms for item in ordered)
    if len(set(opens)) != len(opens):
        raise ValueError("duplicate provider candle open time")
    return ordered[-lookback_limit:]


def _provider_quality(
    candles: tuple[Candle, ...],
    *,
    exchange: Exchange,
    timeframe: str,
    observed_at_ms: int,
) -> ProviderQualityEvidence:
    freshness = assess_freshness(
        candles,
        timeframe=timeframe,
        now_ms=observed_at_ms,
    )
    gaps = detect_gaps(candles, timeframe)
    return ProviderQualityEvidence(
        exchange=exchange,
        available=bool(candles),
        consumed_closed_candles=len(candles),
        latest_open_time_ms=(
            None if not candles else candles[-1].open_time_ms
        ),
        latest_source_age_ms=freshness.source_age_ms,
        latest_closed_age_ms=freshness.closed_age_ms,
        stale=freshness.stale,
        freshness_reasons=tuple(sorted(set(freshness.reasons))),
        gap_count=len(gaps),
        gap_missing_candles=sum(item.missing_count for item in gaps),
    )


def _decimal_median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("median requires values")
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def _candle_payload(candle: Candle) -> dict[str, object]:
    return {
        "exchange": candle.exchange,
        "market_type": candle.market_type,
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open_time_ms": candle.open_time_ms,
        "close_time_ms": candle.close_time_ms,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "quote_volume": candle.quote_volume,
        "trade_count": candle.trade_count,
        "is_closed": candle.is_closed,
        "source": candle.source,
        "source_timestamp_ms": candle.source_timestamp_ms,
        "ingested_at_ms": candle.ingested_at_ms,
        "adapter_version": candle.adapter_version,
    }


def _snapshot_payload(snapshot: ProviderDivergenceSnapshot) -> dict[str, object]:
    return {
        "semantic": snapshot.semantic,
        "market_type": snapshot.market_type,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "observed_at_ms": snapshot.observed_at_ms,
        "lookback_limit": snapshot.lookback_limit,
        "left_exchange": snapshot.left_exchange,
        "right_exchange": snapshot.right_exchange,
        "left_quality": snapshot.left_quality,
        "right_quality": snapshot.right_quality,
        "left_source_evidence_identities": snapshot.left_source_evidence_identities,
        "right_source_evidence_identities": snapshot.right_source_evidence_identities,
        "overlap_count": snapshot.overlap_count,
        "left_only_open_times_ms": snapshot.left_only_open_times_ms,
        "right_only_open_times_ms": snapshot.right_only_open_times_ms,
        "spread_points": snapshot.spread_points,
        "latest_overlap_open_time_ms": snapshot.latest_overlap_open_time_ms,
        "latest_close_spread_bps": snapshot.latest_close_spread_bps,
        "median_absolute_close_spread_bps": (
            snapshot.median_absolute_close_spread_bps
        ),
        "max_absolute_close_spread_bps": snapshot.max_absolute_close_spread_bps,
        "grid_state": snapshot.grid_state,
        "schema_version": snapshot.schema_version,
        "production_authority": snapshot.production_authority,
        "real_capital": snapshot.real_capital,
    }


def _snapshot_from_payload(
    snapshot_identity: str,
    payload_json: str,
) -> ProviderDivergenceSnapshot:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("provider divergence payload must be object")

    left_quality = _quality_from_payload(payload["left_quality"])
    right_quality = _quality_from_payload(payload["right_quality"])
    points_raw = payload["spread_points"]
    if not isinstance(points_raw, list):
        raise TypeError("provider spread points must be array")
    points = tuple(_spread_point_from_payload(item) for item in points_raw)

    return ProviderDivergenceSnapshot(
        snapshot_identity=snapshot_identity,
        semantic=str(payload["semantic"]),
        market_type=MarketType(str(payload["market_type"])),
        symbol=str(payload["symbol"]),
        timeframe=str(payload["timeframe"]),
        observed_at_ms=int(payload["observed_at_ms"]),
        lookback_limit=int(payload["lookback_limit"]),
        left_exchange=Exchange(str(payload["left_exchange"])),
        right_exchange=Exchange(str(payload["right_exchange"])),
        left_quality=left_quality,
        right_quality=right_quality,
        left_source_evidence_identities=tuple(
            str(value)
            for value in payload["left_source_evidence_identities"]
        ),
        right_source_evidence_identities=tuple(
            str(value)
            for value in payload["right_source_evidence_identities"]
        ),
        overlap_count=int(payload["overlap_count"]),
        left_only_open_times_ms=tuple(
            int(value) for value in payload["left_only_open_times_ms"]
        ),
        right_only_open_times_ms=tuple(
            int(value) for value in payload["right_only_open_times_ms"]
        ),
        spread_points=points,
        latest_overlap_open_time_ms=(
            None
            if payload["latest_overlap_open_time_ms"] is None
            else int(payload["latest_overlap_open_time_ms"])
        ),
        latest_close_spread_bps=_optional_decimal(
            payload["latest_close_spread_bps"]
        ),
        median_absolute_close_spread_bps=_optional_decimal(
            payload["median_absolute_close_spread_bps"]
        ),
        max_absolute_close_spread_bps=_optional_decimal(
            payload["max_absolute_close_spread_bps"]
        ),
        grid_state=ProviderGridState(str(payload["grid_state"])),
        schema_version=str(payload["schema_version"]),
        production_authority=bool(payload["production_authority"]),
        real_capital=int(payload["real_capital"]),
    )


def _quality_from_payload(value: Any) -> ProviderQualityEvidence:
    if not isinstance(value, dict):
        raise TypeError("provider quality payload must be object")
    return ProviderQualityEvidence(
        exchange=Exchange(str(value["exchange"])),
        available=bool(value["available"]),
        consumed_closed_candles=int(value["consumed_closed_candles"]),
        latest_open_time_ms=(
            None
            if value["latest_open_time_ms"] is None
            else int(value["latest_open_time_ms"])
        ),
        latest_source_age_ms=(
            None
            if value["latest_source_age_ms"] is None
            else int(value["latest_source_age_ms"])
        ),
        latest_closed_age_ms=(
            None
            if value["latest_closed_age_ms"] is None
            else int(value["latest_closed_age_ms"])
        ),
        stale=bool(value["stale"]),
        freshness_reasons=tuple(
            str(item) for item in value["freshness_reasons"]
        ),
        gap_count=int(value["gap_count"]),
        gap_missing_candles=int(value["gap_missing_candles"]),
    )


def _spread_point_from_payload(value: Any) -> ProviderSpreadPoint:
    if not isinstance(value, dict):
        raise TypeError("provider spread point payload must be object")
    return ProviderSpreadPoint(
        open_time_ms=int(value["open_time_ms"]),
        left_candle_identity=str(value["left_candle_identity"]),
        right_candle_identity=str(value["right_candle_identity"]),
        spread_bps=Decimal(str(value["spread_bps"])),
        absolute_spread_bps=Decimal(str(value["absolute_spread_bps"])),
    )


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _candle_from_row(row: sqlite3.Row) -> Candle:
    return Candle(
        exchange=Exchange(str(row["exchange"])),
        market_type=MarketType(str(row["market_type"])),
        symbol=str(row["symbol"]),
        timeframe=str(row["timeframe"]),
        open_time_ms=int(row["open_time_ms"]),
        close_time_ms=int(row["close_time_ms"]),
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=Decimal(str(row["volume"])),
        quote_volume=(
            None
            if row["quote_volume"] is None
            else Decimal(str(row["quote_volume"]))
        ),
        trade_count=(
            None
            if row["trade_count"] is None
            else int(row["trade_count"])
        ),
        is_closed=bool(row["is_closed"]),
        source=DataSource(str(row["source"])),
        source_timestamp_ms=int(row["source_timestamp_ms"]),
        ingested_at_ms=int(row["ingested_at_ms"]),
        adapter_version=str(row["adapter_version"]),
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
