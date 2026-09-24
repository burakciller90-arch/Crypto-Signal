"""Read-only Product Truth for persisted provider divergence evidence."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

_PROVIDER_DIVERGENCE_SCHEMA = "provider-divergence-v1/1"
_PROVIDER_DIVERGENCE_SEMANTIC = "spot_candle_close_grid_divergence"
_ACCEPTED_GRID_STATES = frozenset(
    {"full_overlap", "partial_overlap", "no_overlap"}
)
_REQUIRED_TABLE_COLUMNS = frozenset(
    {
        "sequence_id",
        "snapshot_identity",
        "market_type",
        "symbol",
        "timeframe",
        "observed_at_ms",
        "left_exchange",
        "right_exchange",
        "payload_json",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderQualityRuntimeTruth:
    exchange: str
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
        if self.exchange not in {"binance", "bybit"}:
            raise ValueError("unsupported provider exchange")
        if self.consumed_closed_candles < 0:
            raise ValueError("provider consumed candle count cannot be negative")
        if self.available != (self.consumed_closed_candles > 0):
            raise ValueError("provider availability/count mismatch")
        if self.latest_open_time_ms is not None and self.latest_open_time_ms < 0:
            raise ValueError("provider latest open cannot be negative")
        for value in (self.latest_source_age_ms, self.latest_closed_age_ms):
            if value is not None and value < 0:
                raise ValueError("provider freshness age cannot be negative")
        if self.gap_count < 0 or self.gap_missing_candles < 0:
            raise ValueError("provider gap count cannot be negative")
        if self.freshness_reasons != tuple(
            sorted(set(self.freshness_reasons))
        ):
            raise ValueError("provider freshness reasons must be canonical")
        if not self.available and (
            self.latest_open_time_ms is not None
            or self.latest_source_age_ms is not None
            or self.latest_closed_age_ms is not None
        ):
            raise ValueError("unavailable provider cannot expose latest evidence")


@dataclass(frozen=True, slots=True)
class ProviderDivergenceRuntimeTruth:
    snapshot_identity: str
    semantic: str
    market_type: str
    symbol: str
    timeframe: str
    observed_at_ms: int
    observation_age_ms: int
    lookback_limit: int
    left_exchange: str
    right_exchange: str
    left_quality: ProviderQualityRuntimeTruth
    right_quality: ProviderQualityRuntimeTruth
    left_source_evidence_identities: tuple[str, ...]
    right_source_evidence_identities: tuple[str, ...]
    overlap_count: int
    left_only_open_times_ms: tuple[int, ...]
    right_only_open_times_ms: tuple[int, ...]
    latest_overlap_open_time_ms: int | None
    latest_close_spread_bps: Decimal | None
    median_absolute_close_spread_bps: Decimal | None
    max_absolute_close_spread_bps: Decimal | None
    grid_state: str
    consensus_status: str = "NOT_INFERRED"
    schema_version: str = _PROVIDER_DIVERGENCE_SCHEMA
    read_only_verified: bool = True
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "provider divergence snapshot")
        if self.semantic != _PROVIDER_DIVERGENCE_SEMANTIC:
            raise ValueError("provider divergence semantic mismatch")
        if self.schema_version != _PROVIDER_DIVERGENCE_SCHEMA:
            raise ValueError("provider divergence schema mismatch")
        if self.market_type != "spot":
            raise ValueError("provider divergence market type mismatch")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("provider divergence symbol must be uppercase")
        if not self.timeframe:
            raise ValueError("provider divergence timeframe missing")
        if self.observed_at_ms < 0 or self.observation_age_ms < 0:
            raise ValueError("provider divergence observation time invalid")
        if self.lookback_limit <= 0:
            raise ValueError("provider divergence lookback invalid")
        if (self.left_exchange, self.right_exchange) != ("binance", "bybit"):
            raise ValueError("provider divergence exchange pair mismatch")
        if self.left_quality.exchange != self.left_exchange:
            raise ValueError("left provider quality mismatch")
        if self.right_quality.exchange != self.right_exchange:
            raise ValueError("right provider quality mismatch")
        for identities in (
            self.left_source_evidence_identities,
            self.right_source_evidence_identities,
        ):
            if len(set(identities)) != len(identities):
                raise ValueError("provider evidence identities must be unique")
            for identity in identities:
                _require_sha256(identity, "provider source evidence identity")
        if self.overlap_count < 0:
            raise ValueError("provider overlap cannot be negative")
        if tuple(sorted(self.left_only_open_times_ms)) != (
            self.left_only_open_times_ms
        ):
            raise ValueError("left-only provider opens must be sorted")
        if tuple(sorted(self.right_only_open_times_ms)) != (
            self.right_only_open_times_ms
        ):
            raise ValueError("right-only provider opens must be sorted")
        if self.grid_state not in _ACCEPTED_GRID_STATES:
            raise ValueError("provider divergence grid state invalid")
        if self.overlap_count == 0:
            if self.grid_state != "no_overlap":
                raise ValueError("zero provider overlap must be no_overlap")
            if any(
                value is not None
                for value in (
                    self.latest_overlap_open_time_ms,
                    self.latest_close_spread_bps,
                    self.median_absolute_close_spread_bps,
                    self.max_absolute_close_spread_bps,
                )
            ):
                raise ValueError("no-overlap provider snapshot exposes spread")
        elif self.grid_state == "no_overlap":
            raise ValueError("provider overlap cannot be no_overlap")
        if self.consensus_status != "NOT_INFERRED":
            raise ValueError("provider Product Truth cannot infer consensus")
        if not self.read_only_verified:
            raise ValueError("provider Product Truth must be read-only verified")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("provider Product Truth cannot grant authority")


def read_provider_divergence_runtime_truth(
    path: Path,
    *,
    observed_at_ms: int,
) -> tuple[ProviderDivergenceRuntimeTruth, ...]:
    if observed_at_ms < 0:
        raise ValueError("provider divergence observation time cannot be negative")
    if not path.is_file():
        raise ValueError("provider divergence runtime database missing")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).lower() != "ok":
            raise ValueError("provider divergence SQLite quick_check failed")

        tables = {
            str(row[0])
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
            ).fetchall()
        }
        required = {
            "provider_divergence_meta",
            "provider_divergence_snapshots",
        }
        if not required.issubset(tables):
            raise ValueError("provider divergence required table missing")

        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(provider_divergence_snapshots)"
            ).fetchall()
        }
        missing = _REQUIRED_TABLE_COLUMNS - columns
        if missing:
            raise ValueError(
                "provider divergence columns missing: "
                + ",".join(sorted(missing))
            )

        schema_row = connection.execute(
            """SELECT value FROM provider_divergence_meta
            WHERE key='schema_version'"""
        ).fetchone()
        if (
            schema_row is None
            or str(schema_row[0]) != _PROVIDER_DIVERGENCE_SCHEMA
        ):
            raise ValueError("provider divergence schema version mismatch")

        rows = connection.execute(
            """
            SELECT
                s.snapshot_identity,
                s.market_type,
                s.symbol,
                s.timeframe,
                s.observed_at_ms,
                s.left_exchange,
                s.right_exchange,
                s.payload_json
            FROM provider_divergence_snapshots AS s
            WHERE s.observed_at_ms <= ?
              AND s.sequence_id = (
                SELECT candidate.sequence_id
                FROM provider_divergence_snapshots AS candidate
                WHERE candidate.market_type = s.market_type
                  AND candidate.symbol = s.symbol
                  AND candidate.timeframe = s.timeframe
                  AND candidate.observed_at_ms <= ?
                ORDER BY
                    candidate.observed_at_ms DESC,
                    candidate.sequence_id DESC
                LIMIT 1
              )
            ORDER BY s.market_type, s.symbol, s.timeframe
            """,
            (observed_at_ms, observed_at_ms),
        ).fetchall()

    return tuple(
        _runtime_truth_from_row(row, observed_at_ms=observed_at_ms)
        for row in rows
    )


def _runtime_truth_from_row(
    row: sqlite3.Row,
    *,
    observed_at_ms: int,
) -> ProviderDivergenceRuntimeTruth:
    snapshot_identity = str(row["snapshot_identity"])
    payload_json = str(row["payload_json"])
    _verify_payload_identity(snapshot_identity, payload_json)
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("provider divergence payload must be object")

    for key in ("market_type", "symbol", "timeframe", "left_exchange", "right_exchange"):
        if str(payload.get(key)) != str(row[key]):
            raise ValueError(f"provider divergence row/payload mismatch: {key}")
    payload_observed_at_ms = int(payload["observed_at_ms"])
    if payload_observed_at_ms != int(row["observed_at_ms"]):
        raise ValueError("provider divergence row/payload observation mismatch")
    if payload_observed_at_ms > observed_at_ms:
        raise ValueError("provider divergence contains future evidence")
    if str(payload.get("schema_version")) != _PROVIDER_DIVERGENCE_SCHEMA:
        raise ValueError("provider divergence payload schema mismatch")
    if str(payload.get("semantic")) != _PROVIDER_DIVERGENCE_SEMANTIC:
        raise ValueError("provider divergence payload semantic mismatch")
    if bool(payload.get("production_authority")):
        raise ValueError("provider divergence payload grants production authority")
    if int(payload.get("real_capital", -1)) != 0:
        raise ValueError("provider divergence payload real capital mismatch")

    return ProviderDivergenceRuntimeTruth(
        snapshot_identity=snapshot_identity,
        semantic=str(payload["semantic"]),
        market_type=str(payload["market_type"]),
        symbol=str(payload["symbol"]),
        timeframe=str(payload["timeframe"]),
        observed_at_ms=payload_observed_at_ms,
        observation_age_ms=observed_at_ms - payload_observed_at_ms,
        lookback_limit=int(payload["lookback_limit"]),
        left_exchange=str(payload["left_exchange"]),
        right_exchange=str(payload["right_exchange"]),
        left_quality=_quality_from_payload(payload["left_quality"]),
        right_quality=_quality_from_payload(payload["right_quality"]),
        left_source_evidence_identities=_identity_tuple(
            payload["left_source_evidence_identities"]
        ),
        right_source_evidence_identities=_identity_tuple(
            payload["right_source_evidence_identities"]
        ),
        overlap_count=int(payload["overlap_count"]),
        left_only_open_times_ms=_int_tuple(
            payload["left_only_open_times_ms"]
        ),
        right_only_open_times_ms=_int_tuple(
            payload["right_only_open_times_ms"]
        ),
        latest_overlap_open_time_ms=_optional_int(
            payload["latest_overlap_open_time_ms"]
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
        grid_state=str(payload["grid_state"]),
    )


def _quality_from_payload(value: Any) -> ProviderQualityRuntimeTruth:
    if not isinstance(value, dict):
        raise TypeError("provider quality payload must be object")
    reasons = value.get("freshness_reasons")
    if not isinstance(reasons, list):
        raise TypeError("provider freshness reasons must be array")
    return ProviderQualityRuntimeTruth(
        exchange=str(value["exchange"]),
        available=bool(value["available"]),
        consumed_closed_candles=int(value["consumed_closed_candles"]),
        latest_open_time_ms=_optional_int(value["latest_open_time_ms"]),
        latest_source_age_ms=_optional_int(value["latest_source_age_ms"]),
        latest_closed_age_ms=_optional_int(value["latest_closed_age_ms"]),
        stale=bool(value["stale"]),
        freshness_reasons=tuple(str(item) for item in reasons),
        gap_count=int(value["gap_count"]),
        gap_missing_candles=int(value["gap_missing_candles"]),
    )


def _verify_payload_identity(snapshot_identity: str, payload_json: str) -> None:
    _require_sha256(snapshot_identity, "provider divergence snapshot")
    parsed = json.loads(payload_json)
    canonical = json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    observed = hashlib.sha256(canonical.encode()).hexdigest()
    if observed != snapshot_identity:
        raise ValueError("provider divergence payload identity mismatch")


def _identity_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError("provider evidence identities must be array")
    return tuple(str(item) for item in value)


def _int_tuple(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise TypeError("provider open times must be array")
    return tuple(int(item) for item in value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
