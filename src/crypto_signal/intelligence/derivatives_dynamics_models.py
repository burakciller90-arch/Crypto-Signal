"""Contracts for M4 temporal derivatives dynamics."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.intelligence.derivatives_context import (
    DEFAULT_DERIVATIVES_CONTEXT_CONFIG,
    DerivativesContextConfig,
    DerivativesContextEvidenceFreeze,
)
from crypto_signal.ledger.serialization import canonical_sha256

ENGINE_VERSION = "m4-derivatives-dynamics-slice1/1"
FREEZE_SCHEMA_VERSION = "m4-derivatives-dynamics-freeze-v1/1"
ZERO = Decimal(0)
ONE = Decimal(1)
BPS = Decimal(10000)


class DerivativesDynamicsStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class OIPriceState(StrEnum):
    PRICE_UP_OI_UP = "price_up_oi_up"
    PRICE_UP_OI_DOWN = "price_up_oi_down"
    PRICE_DOWN_OI_UP = "price_down_oi_up"
    PRICE_DOWN_OI_DOWN = "price_down_oi_down"
    PRICE_FLAT_OI_EXPANDING = "price_flat_oi_expanding"
    OTHER = "other"
    UNAVAILABLE = "unavailable"


class DataAvailability(StrEnum):
    AVAILABLE = "available"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNAVAILABLE_SOURCE_NOT_COLLECTED = "unavailable_source_not_collected"


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsConfig:
    minimum_oi_observations: int = 2
    minimum_funding_observations: int = 3
    price_move_threshold_bps: Decimal = Decimal(10)
    oi_move_threshold_fraction: Decimal = Decimal("0.02")
    max_spot_reference_gap_ms: int = 20 * 60_000
    context_config: DerivativesContextConfig = DEFAULT_DERIVATIVES_CONTEXT_CONFIG

    def __post_init__(self) -> None:
        if self.minimum_oi_observations < 2:
            raise ValueError("minimum_oi_observations must be at least 2")
        if self.minimum_funding_observations < 2:
            raise ValueError("minimum_funding_observations must be at least 2")
        if self.max_spot_reference_gap_ms <= 0:
            raise ValueError("max_spot_reference_gap_ms must be positive")
        for label, value in (
            ("price_move_threshold_bps", self.price_move_threshold_bps),
            ("oi_move_threshold_fraction", self.oi_move_threshold_fraction),
        ):
            finite(value, label)
            if value <= ZERO:
                raise ValueError(f"{label} must be positive")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "context_config": {
                    "lookback_observations": self.context_config.lookback_observations,
                    "minimum_components": self.context_config.minimum_components,
                    "max_observation_age_ms": self.context_config.max_observation_age_ms,
                    "funding_extreme_bps": self.context_config.funding_extreme_bps,
                    "open_interest_change_min_fraction": (
                        self.context_config.open_interest_change_min_fraction
                    ),
                    "basis_extreme_bps": self.context_config.basis_extreme_bps,
                },
                "minimum_oi_observations": self.minimum_oi_observations,
                "minimum_funding_observations": self.minimum_funding_observations,
                "price_move_threshold_bps": self.price_move_threshold_bps,
                "oi_move_threshold_fraction": self.oi_move_threshold_fraction,
                "max_spot_reference_gap_ms": self.max_spot_reference_gap_ms,
            }
        )


DEFAULT_DERIVATIVES_DYNAMICS_CONFIG = DerivativesDynamicsConfig()


@dataclass(frozen=True, slots=True)
class OIPriceMetrics:
    first_oi: Decimal
    last_oi: Decimal
    oi_change_fraction: Decimal
    first_spot_close: Decimal
    last_spot_close: Decimal
    price_change_bps: Decimal
    first_oi_event_at_ms: int
    last_oi_event_at_ms: int
    first_spot_candle_identity: str
    last_spot_candle_identity: str

    def __post_init__(self) -> None:
        for label, value in (
            ("first_oi", self.first_oi),
            ("last_oi", self.last_oi),
            ("oi_change_fraction", self.oi_change_fraction),
            ("first_spot_close", self.first_spot_close),
            ("last_spot_close", self.last_spot_close),
            ("price_change_bps", self.price_change_bps),
        ):
            finite(value, label)
        if self.first_oi <= ZERO or self.last_oi < ZERO:
            raise ValueError("invalid OI values")
        if self.first_spot_close <= ZERO or self.last_spot_close <= ZERO:
            raise ValueError("invalid spot prices")
        if self.last_oi_event_at_ms <= self.first_oi_event_at_ms:
            raise ValueError("OI observations require temporal span")
        sha(self.first_spot_candle_identity, "first spot candle")
        sha(self.last_spot_candle_identity, "last spot candle")


@dataclass(frozen=True, slots=True)
class FundingDynamicsMetrics:
    latest_funding_rate: Decimal
    latest_funding_bps: Decimal
    funding_percentile: Decimal | None
    funding_acceleration_bps: Decimal | None
    funding_observation_count: int
    percentile_status: DataAvailability
    acceleration_status: DataAvailability
    predicted_funding_status: DataAvailability

    def __post_init__(self) -> None:
        finite(self.latest_funding_rate, "latest funding")
        finite(self.latest_funding_bps, "latest funding bps")
        if self.latest_funding_bps != self.latest_funding_rate * BPS:
            raise ValueError("funding bps mismatch")
        if self.funding_observation_count <= 0:
            raise ValueError("funding observation count must be positive")
        if self.funding_percentile is not None:
            finite(self.funding_percentile, "funding percentile")
            if not ZERO <= self.funding_percentile <= ONE:
                raise ValueError("funding percentile outside [0,1]")
        if self.funding_acceleration_bps is not None:
            finite(self.funding_acceleration_bps, "funding acceleration")
        if (self.funding_percentile is not None) != (
            self.percentile_status is DataAvailability.AVAILABLE
        ):
            raise ValueError("funding percentile availability mismatch")
        if (self.funding_acceleration_bps is not None) != (
            self.acceleration_status is DataAvailability.AVAILABLE
        ):
            raise ValueError("funding acceleration availability mismatch")
        if (
            self.predicted_funding_status
            is not DataAvailability.UNAVAILABLE_SOURCE_NOT_COLLECTED
        ):
            raise ValueError("predicted funding is not collected")


@dataclass(frozen=True, slots=True)
class BasisDynamicsMetrics:
    mark_index_basis_bps: Decimal | None
    perp_mark_vs_spot_basis_bps: Decimal | None
    spot_reference_candle_identity: str | None
    spot_reference_gap_ms: int | None

    def __post_init__(self) -> None:
        if self.mark_index_basis_bps is not None:
            finite(self.mark_index_basis_bps, "mark/index basis")
        if self.perp_mark_vs_spot_basis_bps is not None:
            finite(self.perp_mark_vs_spot_basis_bps, "mark/spot basis")
        has_spot = self.perp_mark_vs_spot_basis_bps is not None
        if (self.spot_reference_candle_identity is not None) != has_spot:
            raise ValueError("spot basis identity mismatch")
        if (self.spot_reference_gap_ms is not None) != has_spot:
            raise ValueError("spot basis gap mismatch")
        if self.spot_reference_candle_identity is not None:
            sha(self.spot_reference_candle_identity, "spot basis candle")
        if self.spot_reference_gap_ms is not None and self.spot_reference_gap_ms < 0:
            raise ValueError("spot basis gap cannot be negative")


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsAnalysis:
    evidence_identity: str
    config_identity: str
    exchange: Exchange
    symbol: str
    spot_timeframe: str
    as_of_ms: int
    observed_at_ms: int
    context_evidence_identity: str
    context_freeze_identity: str
    consumed_spot_candle_count: int
    first_spot_candle_identity: str | None
    last_spot_candle_identity: str | None
    status: DerivativesDynamicsStatus
    oi_price_state: OIPriceState
    oi_price_metrics: OIPriceMetrics | None
    funding_metrics: FundingDynamicsMetrics | None
    basis_metrics: BasisDynamicsMetrics
    uncertainty_flags: tuple[str, ...]
    engine_version: str = ENGINE_VERSION
    spot_market_type: MarketType = MarketType.SPOT

    def __post_init__(self) -> None:
        for label, value in (
            ("dynamics evidence", self.evidence_identity),
            ("dynamics config", self.config_identity),
            ("context evidence", self.context_evidence_identity),
            ("context freeze", self.context_freeze_identity),
        ):
            sha(value, label)
        if self.engine_version != ENGINE_VERSION:
            raise ValueError("unsupported derivatives dynamics engine")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be uppercase")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("observed_at outside PIT boundary")
        validate_candle_bounds(
            self.consumed_spot_candle_count,
            self.first_spot_candle_identity,
            self.last_spot_candle_identity,
        )
        if self.status is DerivativesDynamicsStatus.UNRESOLVED:
            if self.oi_price_state is not OIPriceState.UNAVAILABLE:
                raise ValueError("unresolved dynamics cannot expose OI state")
            if self.oi_price_metrics is not None:
                raise ValueError("unresolved dynamics cannot expose OI metrics")
        elif self.oi_price_state is OIPriceState.UNAVAILABLE:
            raise ValueError("measured dynamics requires OI state")
        if self.evidence_identity != canonical_sha256(analysis_payload(self)):
            raise ValueError("derivatives dynamics evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsEvidenceFreeze:
    freeze_identity: str
    analysis: DerivativesDynamicsAnalysis
    context_freeze: DerivativesContextEvidenceFreeze
    spot_candles: tuple[Candle, ...]
    schema_version: str = FREEZE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        sha(self.freeze_identity, "dynamics freeze")
        if self.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported derivatives dynamics freeze schema")
        if self.context_freeze.freeze_identity != self.analysis.context_freeze_identity:
            raise ValueError("context freeze mismatch")
        if len(self.spot_candles) != self.analysis.consumed_spot_candle_count:
            raise ValueError("spot candle count mismatch")
        for candle in self.spot_candles:
            if (
                candle.exchange is not self.analysis.exchange
                or candle.market_type is not MarketType.SPOT
                or candle.symbol != self.analysis.symbol
                or candle.timeframe != self.analysis.spot_timeframe
            ):
                raise ValueError("spot candle context mismatch")
            if (
                not candle.is_closed
                or candle.close_time_ms > self.analysis.as_of_ms
                or candle.source_timestamp_ms > self.analysis.as_of_ms
                or candle.ingested_at_ms > self.analysis.as_of_ms
            ):
                raise ValueError("freeze contains non-PIT spot candle")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "context_freeze_identity": self.context_freeze.freeze_identity,
                "schema_version": FREEZE_SCHEMA_VERSION,
                "spot_candle_identities": [
                    candle_identity(item) for item in self.spot_candles
                ],
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("derivatives dynamics freeze identity mismatch")


def candle_identity(candle: Candle) -> str:
    return canonical_sha256(
        {
            "adapter_version": candle.adapter_version,
            "close": candle.close,
            "close_time_ms": candle.close_time_ms,
            "exchange": candle.exchange,
            "high": candle.high,
            "ingested_at_ms": candle.ingested_at_ms,
            "is_closed": candle.is_closed,
            "low": candle.low,
            "market_type": candle.market_type,
            "open": candle.open,
            "open_time_ms": candle.open_time_ms,
            "quote_volume": candle.quote_volume,
            "source": candle.source,
            "source_timestamp_ms": candle.source_timestamp_ms,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "trade_count": candle.trade_count,
            "volume": candle.volume,
        }
    )


def analysis_payload(analysis: DerivativesDynamicsAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "basis_metrics": analysis.basis_metrics,
        "config_identity": analysis.config_identity,
        "consumed_spot_candle_count": analysis.consumed_spot_candle_count,
        "context_evidence_identity": analysis.context_evidence_identity,
        "context_freeze_identity": analysis.context_freeze_identity,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "first_spot_candle_identity": analysis.first_spot_candle_identity,
        "funding_metrics": analysis.funding_metrics,
        "last_spot_candle_identity": analysis.last_spot_candle_identity,
        "observed_at_ms": analysis.observed_at_ms,
        "oi_price_metrics": analysis.oi_price_metrics,
        "oi_price_state": analysis.oi_price_state,
        "spot_market_type": analysis.spot_market_type,
        "spot_timeframe": analysis.spot_timeframe,
        "status": analysis.status,
        "symbol": analysis.symbol,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def validate_candle_bounds(
    count: int, first_identity: str | None, last_identity: str | None
) -> None:
    if count == 0:
        if first_identity is not None or last_identity is not None:
            raise ValueError("empty candle set cannot carry identities")
        return
    if first_identity is None or last_identity is None:
        raise ValueError("nonempty candle set requires identities")
    sha(first_identity, "first candle")
    sha(last_identity, "last candle")


def finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def sha(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
