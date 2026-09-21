from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

_DAY_MS = 24 * 60 * 60 * 1000


class CrossMarketSeries(StrEnum):
    CBOE_VIX_CLOSE = "cboe_vix_close"
    US_TREASURY_10Y_YIELD = "us_treasury_10y_yield"


class CrossMarketUnit(StrEnum):
    INDEX_POINTS = "index_points"
    PERCENT = "percent"


@dataclass(frozen=True, slots=True)
class CrossMarketDailyRecord:
    record_identity: str
    series: CrossMarketSeries
    unit: CrossMarketUnit
    day_start_ms: int
    value: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "cross-market record identity")
        if self.day_start_ms < 0 or self.day_start_ms % _DAY_MS != 0:
            raise ValueError("cross-market day_start_ms must be UTC-day aligned")
        if self.series is CrossMarketSeries.CBOE_VIX_CLOSE:
            if self.unit is not CrossMarketUnit.INDEX_POINTS:
                raise ValueError("VIX records require index-point units")
            if self.value <= Decimal(0):
                raise ValueError("VIX close must be positive")
        elif self.series is CrossMarketSeries.US_TREASURY_10Y_YIELD:
            if self.unit is not CrossMarketUnit.PERCENT:
                raise ValueError("Treasury yield records require percent units")
            if not Decimal("-20") < self.value < Decimal("100"):
                raise ValueError("Treasury 10Y yield is outside bounded range")
        if self.record_identity != canonical_sha256(cross_market_record_payload(self)):
            raise ValueError("cross-market record identity mismatch")


@dataclass(frozen=True, slots=True)
class CrossMarketWindowObservation:
    observation_identity: str
    series: CrossMarketSeries
    unit: CrossMarketUnit
    observed_at_ms: int
    records: tuple[CrossMarketDailyRecord, ...]
    source: DataSource
    adapter_version: str
    temporal_semantic: str = "ingestion_time_snapshot"

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "cross-market observation identity")
        if self.observed_at_ms < 0:
            raise ValueError("cross-market observed_at_ms must be non-negative")
        if not 1 <= len(self.records) <= 64:
            raise ValueError("cross-market observation must contain 1..64 records")
        previous_day: int | None = None
        identities: set[str] = set()
        for record in self.records:
            if record.series is not self.series or record.unit is not self.unit:
                raise ValueError("cross-market record context mismatch")
            if previous_day is not None and record.day_start_ms <= previous_day:
                raise ValueError("cross-market records must be strictly ascending")
            if record.record_identity in identities:
                raise ValueError("duplicate cross-market record identity")
            previous_day = record.day_start_ms
            identities.add(record.record_identity)
        if self.records[-1].day_start_ms + _DAY_MS > self.observed_at_ms:
            raise ValueError("latest cross-market record day must be complete")
        if self.source is not DataSource.REST:
            raise ValueError("cross-market v1 requires REST source")
        if not self.adapter_version.strip():
            raise ValueError("cross-market adapter_version must be non-empty")
        if self.temporal_semantic != "ingestion_time_snapshot":
            raise ValueError("unsupported cross-market temporal semantic")
        if self.observation_identity != canonical_sha256(
            cross_market_observation_payload(self)
        ):
            raise ValueError("cross-market observation identity mismatch")


def build_cross_market_daily_record(
    *,
    series: CrossMarketSeries,
    unit: CrossMarketUnit,
    day_start_ms: int,
    value: Decimal,
) -> CrossMarketDailyRecord:
    payload = {
        "day_start_ms": day_start_ms,
        "series": series,
        "unit": unit,
        "value": value,
    }
    return CrossMarketDailyRecord(
        record_identity=canonical_sha256(payload),
        series=series,
        unit=unit,
        day_start_ms=day_start_ms,
        value=value,
    )


def build_cross_market_window_observation(
    *,
    series: CrossMarketSeries,
    unit: CrossMarketUnit,
    observed_at_ms: int,
    records: tuple[CrossMarketDailyRecord, ...],
    source: DataSource,
    adapter_version: str,
) -> CrossMarketWindowObservation:
    payload = {
        "adapter_version": adapter_version,
        "observed_at_ms": observed_at_ms,
        "record_identities": [item.record_identity for item in records],
        "series": series,
        "source": source,
        "temporal_semantic": "ingestion_time_snapshot",
        "unit": unit,
    }
    return CrossMarketWindowObservation(
        observation_identity=canonical_sha256(payload),
        series=series,
        unit=unit,
        observed_at_ms=observed_at_ms,
        records=records,
        source=source,
        adapter_version=adapter_version,
    )


def cross_market_record_payload(
    record: CrossMarketDailyRecord,
) -> dict[str, object]:
    return {
        "day_start_ms": record.day_start_ms,
        "series": record.series,
        "unit": record.unit,
        "value": record.value,
    }


def cross_market_observation_payload(
    observation: CrossMarketWindowObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "observed_at_ms": observation.observed_at_ms,
        "record_identities": [
            item.record_identity for item in observation.records
        ],
        "series": observation.series,
        "source": observation.source,
        "temporal_semantic": observation.temporal_semantic,
        "unit": observation.unit,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
