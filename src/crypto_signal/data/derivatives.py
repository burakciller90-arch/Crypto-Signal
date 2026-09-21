from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.ledger.serialization import canonical_sha256


class DerivativesInstrumentType(StrEnum):
    LINEAR_PERPETUAL = "linear_perpetual"


@dataclass(frozen=True, slots=True)
class DerivativesObservation:
    observation_identity: str
    exchange: Exchange
    instrument_type: DerivativesInstrumentType
    symbol: str
    event_at_ms: int
    funding_rate: Decimal | None
    open_interest: Decimal | None
    mark_price: Decimal | None
    index_price: Decimal | None
    funding_interval_hours: int | None
    source: DataSource
    source_timestamp_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "derivatives observation identity")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("derivatives symbol must be non-empty uppercase")
        if min(
            self.event_at_ms,
            self.source_timestamp_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("derivatives timestamps must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("derivatives event cannot postdate source timestamp")
        if self.funding_rate is not None:
            _require_finite(self.funding_rate, "funding_rate")
        if self.open_interest is not None:
            _require_finite(self.open_interest, "open_interest")
            if self.open_interest < Decimal(0):
                raise ValueError("open_interest cannot be negative")
        if (self.mark_price is None) != (self.index_price is None):
            raise ValueError("mark_price and index_price must appear together")
        if self.mark_price is not None:
            index_price = self.index_price
            assert index_price is not None
            _require_finite(self.mark_price, "mark_price")
            _require_finite(index_price, "index_price")
            if self.mark_price <= Decimal(0) or index_price <= Decimal(0):
                raise ValueError("derivatives mark/index prices must be positive")
        if self.funding_interval_hours is not None and self.funding_interval_hours <= 0:
            raise ValueError("funding interval must be positive")
        if all(
            value is None
            for value in (
                self.funding_rate,
                self.open_interest,
                self.mark_price,
            )
        ):
            raise ValueError("derivatives observation requires at least one measurement")
        if not self.adapter_version.strip():
            raise ValueError("derivatives adapter_version must be non-empty")
        if self.observation_identity != canonical_sha256(
            derivatives_observation_payload(self)
        ):
            raise ValueError("derivatives observation identity mismatch")


def build_derivatives_observation(
    *,
    exchange: Exchange,
    instrument_type: DerivativesInstrumentType,
    symbol: str,
    event_at_ms: int,
    funding_rate: Decimal | None,
    open_interest: Decimal | None,
    mark_price: Decimal | None,
    index_price: Decimal | None,
    funding_interval_hours: int | None,
    source: DataSource,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> DerivativesObservation:
    payload = {
        "adapter_version": adapter_version,
        "event_at_ms": event_at_ms,
        "exchange": exchange,
        "funding_interval_hours": funding_interval_hours,
        "funding_rate": funding_rate,
        "index_price": index_price,
        "ingested_at_ms": ingested_at_ms,
        "instrument_type": instrument_type,
        "mark_price": mark_price,
        "open_interest": open_interest,
        "source": source,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol,
    }
    return DerivativesObservation(
        observation_identity=canonical_sha256(payload),
        exchange=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        event_at_ms=event_at_ms,
        funding_rate=funding_rate,
        open_interest=open_interest,
        mark_price=mark_price,
        index_price=index_price,
        funding_interval_hours=funding_interval_hours,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
    )


def derivatives_observation_payload(
    observation: DerivativesObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "event_at_ms": observation.event_at_ms,
        "exchange": observation.exchange,
        "funding_interval_hours": observation.funding_interval_hours,
        "funding_rate": observation.funding_rate,
        "index_price": observation.index_price,
        "ingested_at_ms": observation.ingested_at_ms,
        "instrument_type": observation.instrument_type,
        "mark_price": observation.mark_price,
        "open_interest": observation.open_interest,
        "source": observation.source,
        "source_timestamp_ms": observation.source_timestamp_ms,
        "symbol": observation.symbol,
    }


def _require_finite(value: Decimal | None, label: str) -> None:
    if value is None or value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
