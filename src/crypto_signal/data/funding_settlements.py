"""Immutable settled funding observations for perpetual paper execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.ledger.serialization import canonical_sha256

FUNDING_SETTLEMENT_SCHEMA_VERSION = "funding_settlement.v1"


@dataclass(frozen=True, slots=True)
class FundingSettlementObservation:
    settlement_identity: str
    schema_version: str
    exchange: Exchange
    instrument_type: DerivativesInstrumentType
    symbol: str
    settlement_at_ms: int
    funding_rate: Decimal
    source_timestamp_ms: int
    ingested_at_ms: int
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.settlement_identity, "settlement_identity")
        if self.schema_version != FUNDING_SETTLEMENT_SCHEMA_VERSION:
            raise ValueError("unsupported funding settlement schema version")
        if self.instrument_type is not DerivativesInstrumentType.LINEAR_PERPETUAL:
            raise ValueError("funding settlement v1 requires linear perpetual")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("funding settlement symbol must be non-empty uppercase")
        if min(
            self.settlement_at_ms,
            self.source_timestamp_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("funding settlement timestamps must be non-negative")
        if self.settlement_at_ms > self.source_timestamp_ms:
            raise ValueError("settlement cannot postdate source timestamp")
        if self.source_timestamp_ms > self.ingested_at_ms:
            raise ValueError("source timestamp cannot postdate ingestion")
        if self.funding_rate.is_nan() or self.funding_rate.is_infinite():
            raise ValueError("funding_rate must be finite")
        if not self.adapter_version.strip():
            raise ValueError("adapter_version must be non-empty")
        if self.settlement_identity != compute_funding_settlement_identity(
            schema_version=self.schema_version,
            exchange=self.exchange,
            instrument_type=self.instrument_type,
            symbol=self.symbol,
            settlement_at_ms=self.settlement_at_ms,
            funding_rate=self.funding_rate,
            source_timestamp_ms=self.source_timestamp_ms,
            ingested_at_ms=self.ingested_at_ms,
            source=self.source,
            adapter_version=self.adapter_version,
        ):
            raise ValueError("funding settlement identity mismatch")


def compute_funding_settlement_identity(
    *,
    schema_version: str,
    exchange: Exchange,
    instrument_type: DerivativesInstrumentType,
    symbol: str,
    settlement_at_ms: int,
    funding_rate: Decimal,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    source: DataSource,
    adapter_version: str,
) -> str:
    return canonical_sha256(
        {
            "adapter_version": adapter_version,
            "exchange": exchange.value,
            "funding_rate": funding_rate,
            "ingested_at_ms": ingested_at_ms,
            "instrument_type": instrument_type.value,
            "schema_version": schema_version,
            "settlement_at_ms": settlement_at_ms,
            "source": source.value,
            "source_timestamp_ms": source_timestamp_ms,
            "symbol": symbol,
        }
    )


def build_funding_settlement_observation(
    *,
    exchange: Exchange,
    instrument_type: DerivativesInstrumentType,
    symbol: str,
    settlement_at_ms: int,
    funding_rate: Decimal,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    source: DataSource,
    adapter_version: str,
) -> FundingSettlementObservation:
    identity = compute_funding_settlement_identity(
        schema_version=FUNDING_SETTLEMENT_SCHEMA_VERSION,
        exchange=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        settlement_at_ms=settlement_at_ms,
        funding_rate=funding_rate,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        source=source,
        adapter_version=adapter_version,
    )
    return FundingSettlementObservation(
        settlement_identity=identity,
        schema_version=FUNDING_SETTLEMENT_SCHEMA_VERSION,
        exchange=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        settlement_at_ms=settlement_at_ms,
        funding_rate=funding_rate,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        source=source,
        adapter_version=adapter_version,
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")


__all__ = [
    "FUNDING_SETTLEMENT_SCHEMA_VERSION",
    "FundingSettlementObservation",
    "build_funding_settlement_observation",
    "compute_funding_settlement_identity",
]
