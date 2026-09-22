from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.derivatives import DerivativesInstrumentType
from crypto_signal.data.models import DataSource, Exchange
from crypto_signal.ledger.serialization import canonical_sha256


class LiquidatedPositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class LiquidationObservation:
    liquidation_identity: str
    exchange: Exchange
    instrument_type: DerivativesInstrumentType
    symbol: str
    liquidated_position_side: LiquidatedPositionSide
    size: Decimal
    bankruptcy_price: Decimal
    event_at_ms: int
    source_timestamp_ms: int
    ingested_at_ms: int
    source_row_index: int
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.liquidation_identity, "liquidation identity")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidation symbol must be non-empty uppercase")
        for label, value in (
            ("size", self.size),
            ("bankruptcy_price", self.bankruptcy_price),
        ):
            if value.is_nan() or value.is_infinite() or value <= Decimal(0):
                raise ValueError(f"{label} must be finite and positive")
        if min(
            self.event_at_ms,
            self.source_timestamp_ms,
            self.ingested_at_ms,
            self.source_row_index,
        ) < 0:
            raise ValueError("liquidation timestamps/index must be non-negative")
        if self.event_at_ms > self.source_timestamp_ms:
            raise ValueError("liquidation event cannot postdate source timestamp")
        if not self.adapter_version.strip():
            raise ValueError("liquidation adapter_version must be non-empty")
        if self.liquidation_identity != canonical_sha256(
            liquidation_observation_payload(self)
        ):
            raise ValueError("liquidation identity mismatch")

    @property
    def bankruptcy_notional(self) -> Decimal:
        return self.size * self.bankruptcy_price


@dataclass(frozen=True, slots=True)
class LiquidationFeedCoverage:
    coverage_identity: str
    exchange: Exchange
    instrument_type: DerivativesInstrumentType
    symbol: str
    coverage_start_ms: int
    coverage_end_ms: int
    observed_at_ms: int
    source: DataSource
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.coverage_identity, "liquidation coverage identity")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("liquidation coverage symbol must be uppercase")
        if min(
            self.coverage_start_ms,
            self.coverage_end_ms,
            self.observed_at_ms,
        ) < 0:
            raise ValueError("liquidation coverage timestamps cannot be negative")
        if self.coverage_end_ms < self.coverage_start_ms:
            raise ValueError("liquidation coverage end precedes start")
        if self.observed_at_ms < self.coverage_end_ms:
            raise ValueError("liquidation coverage cannot be observed before end")
        if not self.adapter_version.strip():
            raise ValueError("liquidation coverage adapter_version must be non-empty")
        if self.coverage_identity != canonical_sha256(
            liquidation_feed_coverage_payload(self)
        ):
            raise ValueError("liquidation coverage identity mismatch")


def build_liquidation_observation(
    *,
    exchange: Exchange,
    instrument_type: DerivativesInstrumentType,
    symbol: str,
    liquidated_position_side: LiquidatedPositionSide,
    size: Decimal,
    bankruptcy_price: Decimal,
    event_at_ms: int,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    source_row_index: int,
    source: DataSource,
    adapter_version: str,
) -> LiquidationObservation:
    payload = {
        "adapter_version": adapter_version,
        "bankruptcy_price": bankruptcy_price,
        "event_at_ms": event_at_ms,
        "exchange": exchange,
        "ingested_at_ms": ingested_at_ms,
        "instrument_type": instrument_type,
        "liquidated_position_side": liquidated_position_side,
        "size": size,
        "source": source,
        "source_row_index": source_row_index,
        "source_timestamp_ms": source_timestamp_ms,
        "symbol": symbol,
    }
    return LiquidationObservation(
        liquidation_identity=canonical_sha256(payload),
        exchange=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        liquidated_position_side=liquidated_position_side,
        size=size,
        bankruptcy_price=bankruptcy_price,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        source_row_index=source_row_index,
        source=source,
        adapter_version=adapter_version,
    )


def build_liquidation_feed_coverage(
    *,
    exchange: Exchange,
    instrument_type: DerivativesInstrumentType,
    symbol: str,
    coverage_start_ms: int,
    coverage_end_ms: int,
    observed_at_ms: int,
    source: DataSource,
    adapter_version: str,
) -> LiquidationFeedCoverage:
    payload = {
        "adapter_version": adapter_version,
        "coverage_end_ms": coverage_end_ms,
        "coverage_start_ms": coverage_start_ms,
        "exchange": exchange,
        "instrument_type": instrument_type,
        "observed_at_ms": observed_at_ms,
        "source": source,
        "symbol": symbol,
    }
    return LiquidationFeedCoverage(
        coverage_identity=canonical_sha256(payload),
        exchange=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        coverage_start_ms=coverage_start_ms,
        coverage_end_ms=coverage_end_ms,
        observed_at_ms=observed_at_ms,
        source=source,
        adapter_version=adapter_version,
    )


def liquidation_observation_payload(
    observation: LiquidationObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "bankruptcy_price": observation.bankruptcy_price,
        "event_at_ms": observation.event_at_ms,
        "exchange": observation.exchange,
        "ingested_at_ms": observation.ingested_at_ms,
        "instrument_type": observation.instrument_type,
        "liquidated_position_side": observation.liquidated_position_side,
        "size": observation.size,
        "source": observation.source,
        "source_row_index": observation.source_row_index,
        "source_timestamp_ms": observation.source_timestamp_ms,
        "symbol": observation.symbol,
    }


def liquidation_feed_coverage_payload(
    coverage: LiquidationFeedCoverage,
) -> dict[str, object]:
    return {
        "adapter_version": coverage.adapter_version,
        "coverage_end_ms": coverage.coverage_end_ms,
        "coverage_start_ms": coverage.coverage_start_ms,
        "exchange": coverage.exchange,
        "instrument_type": coverage.instrument_type,
        "observed_at_ms": coverage.observed_at_ms,
        "source": coverage.source,
        "symbol": coverage.symbol,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
