"""M4 Slice 1: PIT-safe temporal derivatives dynamics.

Extends the accepted bounded derivatives context without rewriting it.
This layer adds OI x spot-price state, historical funding distribution/change,
and mark-vs-spot basis. It is context evidence only: no trade command, no
probability and no universal directional funding rule.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.derivatives import DerivativesObservation
from crypto_signal.data.models import Candle, Exchange, MarketType
from crypto_signal.intelligence.derivatives_context import (
    DEFAULT_DERIVATIVES_CONTEXT_CONFIG,
    DerivativesContextConfig,
    DerivativesContextEvidenceFreeze,
    build_derivatives_context_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256

DERIVATIVES_DYNAMICS_ENGINE_VERSION = "m4-derivatives-dynamics-slice1/1"
DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION = "m4-derivatives-dynamics-freeze-v1/1"

_ZERO = Decimal(0)
_ONE = Decimal(1)
_BPS = Decimal(10000)


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
            if value.is_nan() or value.is_infinite() or value <= _ZERO:
                raise ValueError(f"{label} must be positive and finite")

    @property
    def identity(self) -> str:
        return canonical_sha256(
            {
                "context": {
                    "basis_extreme_bps": self.context_config.basis_extreme_bps,
                    "funding_extreme_bps": self.context_config.funding_extreme_bps,
                    "lookback_observations": self.context_config.lookback_observations,
                    "max_observation_age_ms": self.context_config.max_observation_age_ms,
                    "minimum_components": self.context_config.minimum_components,
                    "open_interest_change_min_fraction": (
                        self.context_config.open_interest_change_min_fraction
                    ),
                },
                "max_spot_reference_gap_ms": self.max_spot_reference_gap_ms,
                "minimum_funding_observations": self.minimum_funding_observations,
                "minimum_oi_observations": self.minimum_oi_observations,
                "oi_move_threshold_fraction": self.oi_move_threshold_fraction,
                "price_move_threshold_bps": self.price_move_threshold_bps,
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
            _finite(value, label)
        if self.first_oi <= _ZERO or self.last_oi < _ZERO:
            raise ValueError("OI x price metrics require nonnegative OI and positive baseline")
        if self.first_spot_close <= _ZERO or self.last_spot_close <= _ZERO:
            raise ValueError("OI x price spot closes must be positive")
        if self.last_oi_event_at_ms <= self.first_oi_event_at_ms:
            raise ValueError("OI x price observations must be chronological")
        _sha(self.first_spot_candle_identity, "first OI x price candle")
        _sha(self.last_spot_candle_identity, "last OI x price candle")


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
        for label, value in (
            ("latest_funding_rate", self.latest_funding_rate),
            ("latest_funding_bps", self.latest_funding_bps),
        ):
            _finite(value, label)
        if self.latest_funding_bps != self.latest_funding_rate * _BPS:
            raise ValueError("funding bps mismatch")
        if self.funding_observation_count <= 0:
            raise ValueError("funding dynamics requires observations")
        if self.funding_percentile is not None:
            _finite(self.funding_percentile, "funding_percentile")
            if not _ZERO <= self.funding_percentile <= _ONE:
                raise ValueError("funding_percentile outside [0,1]")
        if self.funding_acceleration_bps is not None:
            _finite(self.funding_acceleration_bps, "funding_acceleration_bps")
        if (self.funding_percentile is None) == (
            self.percentile_status is DataAvailability.AVAILABLE
        ):
            raise ValueError("funding percentile availability mismatch")
        if (self.funding_acceleration_bps is None) == (
            self.acceleration_status is DataAvailability.AVAILABLE
        ):
            raise ValueError("funding acceleration availability mismatch")
        if (
            self.predicted_funding_status
            is not DataAvailability.UNAVAILABLE_SOURCE_NOT_COLLECTED
        ):
            raise ValueError("predicted funding is not collected in this slice")


@dataclass(frozen=True, slots=True)
class BasisDynamicsMetrics:
    mark_index_basis_bps: Decimal | None
    perp_mark_vs_spot_basis_bps: Decimal | None
    spot_reference_candle_identity: str | None
    spot_reference_gap_ms: int | None

    def __post_init__(self) -> None:
        if self.mark_index_basis_bps is not None:
            _finite(self.mark_index_basis_bps, "mark_index_basis_bps")
        if self.perp_mark_vs_spot_basis_bps is not None:
            _finite(
                self.perp_mark_vs_spot_basis_bps,
                "perp_mark_vs_spot_basis_bps",
            )
        if (self.spot_reference_candle_identity is None) != (
            self.perp_mark_vs_spot_basis_bps is None
        ):
            raise ValueError("spot basis identity/value mismatch")
        if (self.spot_reference_gap_ms is None) != (
            self.perp_mark_vs_spot_basis_bps is None
        ):
            raise ValueError("spot basis gap/value mismatch")
        if self.spot_reference_candle_identity is not None:
            _sha(self.spot_reference_candle_identity, "spot basis candle")
        if self.spot_reference_gap_ms is not None and self.spot_reference_gap_ms < 0:
            raise ValueError("spot reference gap cannot be negative")


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsAnalysis:
    evidence_identity: str
    engine_version: str
    config_identity: str
    exchange: Exchange
    symbol: str
    spot_market_type: MarketType
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

    def __post_init__(self) -> None:
        for label, value in (
            ("derivatives dynamics evidence", self.evidence_identity),
            ("derivatives dynamics config", self.config_identity),
            ("derivatives context evidence", self.context_evidence_identity),
            ("derivatives context freeze", self.context_freeze_identity),
        ):
            _sha(value, label)
        if self.engine_version != DERIVATIVES_DYNAMICS_ENGINE_VERSION:
            raise ValueError("unsupported derivatives dynamics engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("derivatives dynamics symbol must be uppercase")
        if not self.spot_timeframe:
            raise ValueError("spot timeframe must be non-empty")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("derivatives dynamics observed_at outside PIT boundary")
        _validate_candle_bounds(
            self.consumed_spot_candle_count,
            self.first_spot_candle_identity,
            self.last_spot_candle_identity,
        )
        if self.status is DerivativesDynamicsStatus.UNRESOLVED:
            if self.oi_price_state is not OIPriceState.UNAVAILABLE:
                raise ValueError("unresolved dynamics cannot expose OI x price state")
            if self.oi_price_metrics is not None:
                raise ValueError("unresolved dynamics cannot expose OI x price metrics")
            if not self.uncertainty_flags:
                raise ValueError("unresolved dynamics requires uncertainty")
        elif self.oi_price_state is OIPriceState.UNAVAILABLE:
            raise ValueError("measured dynamics requires OI x price state")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("derivatives dynamics evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: DerivativesDynamicsAnalysis
    context_freeze: DerivativesContextEvidenceFreeze
    spot_candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _sha(self.freeze_identity, "derivatives dynamics freeze")
        if self.schema_version != DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported derivatives dynamics freeze schema")
        if self.context_freeze.freeze_identity != self.analysis.context_freeze_identity:
            raise ValueError("derivatives context freeze mismatch")
        if len(self.spot_candles) != self.analysis.consumed_spot_candle_count:
            raise ValueError("derivatives dynamics candle count mismatch")
        for candle in self.spot_candles:
            if (
                candle.exchange is not self.analysis.exchange
                or candle.market_type is not self.analysis.spot_market_type
                or candle.symbol != self.analysis.symbol
                or candle.timeframe != self.analysis.spot_timeframe
            ):
                raise ValueError("derivatives dynamics candle context mismatch")
            if (
                not candle.is_closed
                or candle.close_time_ms > self.analysis.as_of_ms
                or candle.source_timestamp_ms > self.analysis.as_of_ms
                or candle.ingested_at_ms > self.analysis.as_of_ms
            ):
                raise ValueError("derivatives dynamics freeze contains non-PIT candle")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "context_freeze_identity": self.context_freeze.freeze_identity,
                "schema_version": DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION,
                "spot_candle_identities": [
                    _candle_identity(item) for item in self.spot_candles
                ],
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("derivatives dynamics freeze identity mismatch")


def build_derivatives_dynamics_evidence_freeze(
    observations: Sequence[DerivativesObservation],
    spot_candles: Sequence[Candle],
    *,
    as_of_ms: int,
    config: DerivativesDynamicsConfig = DEFAULT_DERIVATIVES_DYNAMICS_CONFIG,
) -> DerivativesDynamicsEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("derivatives dynamics as_of_ms must be nonnegative")
    if not observations:
        raise ValueError("derivatives dynamics requires derivatives observations")
    if not spot_candles:
        raise ValueError("derivatives dynamics requires spot candles")

    context_freeze = build_derivatives_context_evidence_freeze(
        observations,
        as_of_ms=as_of_ms,
        config=config.context_config,
    )
    context = context_freeze.analysis

    ordered = tuple(
        sorted(spot_candles, key=lambda item: (item.open_time_ms, item.close_time_ms))
    )
    _reject_duplicate_candles(ordered)
    first = ordered[0]
    if first.market_type is not MarketType.SPOT:
        raise ValueError("derivatives dynamics price reference must be spot candles")
    for candle in ordered:
        if (
            candle.exchange is not context.exchange
            or candle.market_type is not MarketType.SPOT
            or candle.symbol != context.symbol
            or candle.timeframe != first.timeframe
        ):
            raise ValueError("mixed derivatives dynamics spot candle context")

    selected = tuple(
        candle
        for candle in ordered
        if candle.is_closed
        and candle.close_time_ms <= as_of_ms
        and candle.source_timestamp_ms <= as_of_ms
        and candle.ingested_at_ms <= as_of_ms
    )

    flags: list[str] = [
        "spot_price_is_proxy_for_price_x_oi_state",
        "derivatives_context_reused_not_recomputed_locally",
        "predicted_funding_not_collected",
        "cross_venue_basis_not_evaluated_in_slice1",
    ]
    status = DerivativesDynamicsStatus.MEASURED
    oi_state = OIPriceState.UNAVAILABLE
    oi_metrics: OIPriceMetrics | None = None

    oi_observations = tuple(
        item
        for item in context_freeze.observations
        if item.open_interest is not None
    )
    if len(oi_observations) < config.minimum_oi_observations:
        status = DerivativesDynamicsStatus.UNRESOLVED
        flags.append("insufficient_open_interest_history")
    elif not selected:
        status = DerivativesDynamicsStatus.UNRESOLVED
        flags.append("spot_candle_unavailable_at_as_of")
    else:
        first_oi = oi_observations[0]
        last_oi = oi_observations[-1]
        first_candle = _spot_reference_for_event(
            selected,
            event_at_ms=first_oi.event_at_ms,
            max_gap_ms=config.max_spot_reference_gap_ms,
        )
        last_candle = _spot_reference_for_event(
            selected,
            event_at_ms=last_oi.event_at_ms,
            max_gap_ms=config.max_spot_reference_gap_ms,
        )
        if first_candle is None or last_candle is None:
            status = DerivativesDynamicsStatus.UNRESOLVED
            flags.append("spot_reference_gap_exceeds_limit")
        elif first_oi.open_interest is None or last_oi.open_interest is None:
            raise RuntimeError("filtered OI observation unexpectedly missing OI")
        elif first_oi.open_interest <= _ZERO:
            status = DerivativesDynamicsStatus.UNRESOLVED
            flags.append("nonpositive_open_interest_baseline")
        elif last_oi.event_at_ms <= first_oi.event_at_ms:
            status = DerivativesDynamicsStatus.UNRESOLVED
            flags.append("insufficient_open_interest_temporal_span")
        else:
            oi_change = (
                last_oi.open_interest - first_oi.open_interest
            ) / first_oi.open_interest
            price_change_bps = (
                last_candle.close - first_candle.close
            ) / first_candle.close * _BPS
            oi_metrics = OIPriceMetrics(
                first_oi=first_oi.open_interest,
                last_oi=last_oi.open_interest,
                oi_change_fraction=oi_change,
                first_spot_close=first_candle.close,
                last_spot_close=last_candle.close,
                price_change_bps=price_change_bps,
                first_oi_event_at_ms=first_oi.event_at_ms,
                last_oi_event_at_ms=last_oi.event_at_ms,
                first_spot_candle_identity=_candle_identity(first_candle),
                last_spot_candle_identity=_candle_identity(last_candle),
            )
            oi_state = _oi_price_state(oi_metrics, config=config)

    funding_metrics = _funding_dynamics(
        context_freeze.observations,
        config=config,
        flags=flags,
    )
    basis_metrics = _basis_dynamics(
        context_freeze.observations,
        selected,
        config=config,
        flags=flags,
    )

    observed_at_ms = max(
        context.observed_at_ms,
        max((item.ingested_at_ms for item in selected), default=0),
    )
    payload: dict[str, object] = {
        "as_of_ms": as_of_ms,
        "basis_metrics": basis_metrics,
        "config_identity": config.identity,
        "consumed_spot_candle_count": len(selected),
        "context_evidence_identity": context.evidence_identity,
        "context_freeze_identity": context_freeze.freeze_identity,
        "engine_version": DERIVATIVES_DYNAMICS_ENGINE_VERSION,
        "exchange": context.exchange,
        "first_spot_candle_identity": (
            None if not selected else _candle_identity(selected[0])
        ),
        "funding_metrics": funding_metrics,
        "last_spot_candle_identity": (
            None if not selected else _candle_identity(selected[-1])
        ),
        "observed_at_ms": observed_at_ms,
        "oi_price_metrics": oi_metrics,
        "oi_price_state": oi_state,
        "spot_market_type": MarketType.SPOT,
        "spot_timeframe": first.timeframe,
        "status": status,
        "symbol": context.symbol,
        "uncertainty_flags": tuple(flags),
    }
    analysis = DerivativesDynamicsAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DERIVATIVES_DYNAMICS_ENGINE_VERSION,
        config_identity=config.identity,
        exchange=context.exchange,
        symbol=context.symbol,
        spot_market_type=MarketType.SPOT,
        spot_timeframe=first.timeframe,
        as_of_ms=as_of_ms,
        observed_at_ms=observed_at_ms,
        context_evidence_identity=context.evidence_identity,
        context_freeze_identity=context_freeze.freeze_identity,
        consumed_spot_candle_count=len(selected),
        first_spot_candle_identity=(
            None if not selected else _candle_identity(selected[0])
        ),
        last_spot_candle_identity=(
            None if not selected else _candle_identity(selected[-1])
        ),
        status=status,
        oi_price_state=oi_state,
        oi_price_metrics=oi_metrics,
        funding_metrics=funding_metrics,
        basis_metrics=basis_metrics,
        uncertainty_flags=tuple(flags),
    )
    return DerivativesDynamicsEvidenceFreeze(
        freeze_identity=canonical_sha256(
            {
                "analysis_identity": analysis.evidence_identity,
                "context_freeze_identity": context_freeze.freeze_identity,
                "schema_version": DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION,
                "spot_candle_identities": [
                    _candle_identity(item) for item in selected
                ],
            }
        ),
        schema_version=DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        context_freeze=context_freeze,
        spot_candles=selected,
    )


def _oi_price_state(
    metrics: OIPriceMetrics,
    *,
    config: DerivativesDynamicsConfig,
) -> OIPriceState:
    price_up = metrics.price_change_bps >= config.price_move_threshold_bps
    price_down = metrics.price_change_bps <= -config.price_move_threshold_bps
    oi_up = metrics.oi_change_fraction >= config.oi_move_threshold_fraction
    oi_down = metrics.oi_change_fraction <= -config.oi_move_threshold_fraction

    if price_up and oi_up:
        return OIPriceState.PRICE_UP_OI_UP
    if price_up and oi_down:
        return OIPriceState.PRICE_UP_OI_DOWN
    if price_down and oi_up:
        return OIPriceState.PRICE_DOWN_OI_UP
    if price_down and oi_down:
        return OIPriceState.PRICE_DOWN_OI_DOWN
    if not price_up and not price_down and oi_up:
        return OIPriceState.PRICE_FLAT_OI_EXPANDING
    return OIPriceState.OTHER


def _funding_dynamics(
    observations: tuple[DerivativesObservation, ...],
    *,
    config: DerivativesDynamicsConfig,
    flags: list[str],
) -> FundingDynamicsMetrics | None:
    funding = tuple(
        item
        for item in observations
        if item.funding_rate is not None
    )
    if not funding:
        flags.append("funding_unavailable")
        return None
    latest_rate = funding[-1].funding_rate
    assert latest_rate is not None

    percentile: Decimal | None = None
    acceleration: Decimal | None = None
    percentile_status = DataAvailability.INSUFFICIENT_HISTORY
    acceleration_status = DataAvailability.INSUFFICIENT_HISTORY
    if len(funding) >= config.minimum_funding_observations:
        rates = tuple(
            item.funding_rate for item in funding if item.funding_rate is not None
        )
        rank = sum(1 for value in rates if value <= latest_rate)
        percentile = Decimal(rank) / Decimal(len(rates))
        previous_rate = rates[-2]
        acceleration = (latest_rate - previous_rate) * _BPS
        percentile_status = DataAvailability.AVAILABLE
        acceleration_status = DataAvailability.AVAILABLE
    else:
        flags.append("insufficient_funding_history_for_percentile_and_acceleration")

    return FundingDynamicsMetrics(
        latest_funding_rate=latest_rate,
        latest_funding_bps=latest_rate * _BPS,
        funding_percentile=percentile,
        funding_acceleration_bps=acceleration,
        funding_observation_count=len(funding),
        percentile_status=percentile_status,
        acceleration_status=acceleration_status,
        predicted_funding_status=(
            DataAvailability.UNAVAILABLE_SOURCE_NOT_COLLECTED
        ),
    )


def _basis_dynamics(
    observations: tuple[DerivativesObservation, ...],
    spot_candles: tuple[Candle, ...],
    *,
    config: DerivativesDynamicsConfig,
    flags: list[str],
) -> BasisDynamicsMetrics:
    mark_observations = tuple(
        item
        for item in observations
        if item.mark_price is not None and item.index_price is not None
    )
    if not mark_observations:
        flags.append("mark_index_basis_unavailable")
        return BasisDynamicsMetrics(
            mark_index_basis_bps=None,
            perp_mark_vs_spot_basis_bps=None,
            spot_reference_candle_identity=None,
            spot_reference_gap_ms=None,
        )

    latest = mark_observations[-1]
    mark = latest.mark_price
    index = latest.index_price
    assert mark is not None and index is not None
    mark_index_basis = (mark - index) / index * _BPS
    spot_reference = _spot_reference_for_event(
        spot_candles,
        event_at_ms=latest.event_at_ms,
        max_gap_ms=config.max_spot_reference_gap_ms,
    )
    if spot_reference is None:
        flags.append("spot_reference_unavailable_for_perp_basis")
        return BasisDynamicsMetrics(
            mark_index_basis_bps=mark_index_basis,
            perp_mark_vs_spot_basis_bps=None,
            spot_reference_candle_identity=None,
            spot_reference_gap_ms=None,
        )

    return BasisDynamicsMetrics(
        mark_index_basis_bps=mark_index_basis,
        perp_mark_vs_spot_basis_bps=(
            (mark - spot_reference.close) / spot_reference.close * _BPS
        ),
        spot_reference_candle_identity=_candle_identity(spot_reference),
        spot_reference_gap_ms=latest.event_at_ms - spot_reference.close_time_ms,
    )


def _spot_reference_for_event(
    candles: tuple[Candle, ...],
    *,
    event_at_ms: int,
    max_gap_ms: int,
) -> Candle | None:
    eligible = tuple(
        item for item in candles if item.close_time_ms <= event_at_ms
    )
    if not eligible:
        return None
    candidate = eligible[-1]
    if event_at_ms - candidate.close_time_ms > max_gap_ms:
        return None
    return candidate


def _candle_identity(candle: Candle) -> str:
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


def _reject_duplicate_candles(candles: tuple[Candle, ...]) -> None:
    identities = [_candle_identity(item) for item in candles]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate derivatives dynamics spot candle identity")


def _validate_candle_bounds(
    count: int,
    first_identity: str | None,
    last_identity: str | None,
) -> None:
    if count == 0:
        if first_identity is not None or last_identity is not None:
            raise ValueError("empty spot candle set cannot carry identities")
        return
    if first_identity is None or last_identity is None:
        raise ValueError("nonempty spot candle set requires boundary identities")
    _sha(first_identity, "first derivatives dynamics spot candle")
    _sha(last_identity, "last derivatives dynamics spot candle")


def _analysis_payload(
    analysis: DerivativesDynamicsAnalysis,
) -> dict[str, object]:
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


def _finite(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{label} must be finite")


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be SHA256")
