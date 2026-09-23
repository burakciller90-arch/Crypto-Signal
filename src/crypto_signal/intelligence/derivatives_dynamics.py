from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    DerivativesObservation,
)
from crypto_signal.data.models import Exchange
from crypto_signal.ledger.serialization import canonical_sha256

DERIVATIVES_DYNAMICS_ENGINE_VERSION = "derivatives-dynamics-v2-slice1/1"
DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION = "derivatives-dynamics-freeze-v1/1"
_BPS = Decimal(10_000)


class DerivativesDynamicsStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class OiPriceState(StrEnum):
    PRICE_UP_OI_UP = "price_up_oi_up"
    PRICE_UP_OI_DOWN = "price_up_oi_down"
    PRICE_UP_OI_FLAT = "price_up_oi_flat"
    PRICE_DOWN_OI_UP = "price_down_oi_up"
    PRICE_DOWN_OI_DOWN = "price_down_oi_down"
    PRICE_DOWN_OI_FLAT = "price_down_oi_flat"
    PRICE_FLAT_OI_EXPANDING = "price_flat_oi_expanding"
    PRICE_FLAT_OI_CONTRACTING = "price_flat_oi_contracting"
    PRICE_FLAT_OI_STABLE = "price_flat_oi_stable"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsConfig:
    lookback_observations: int = 64
    minimum_components: int = 2
    max_observation_age_ms: int = 30 * 60_000
    price_move_min_fraction: Decimal = Decimal("0.005")
    open_interest_move_min_fraction: Decimal = Decimal("0.02")
    funding_percentile_min_observations: int = 3

    def __post_init__(self) -> None:
        if self.lookback_observations < 2:
            raise ValueError("lookback_observations must be at least 2")
        if not 1 <= self.minimum_components <= 3:
            raise ValueError("minimum_components must be inside [1,3]")
        if self.max_observation_age_ms <= 0:
            raise ValueError("max_observation_age_ms must be positive")
        if self.funding_percentile_min_observations < 2:
            raise ValueError("funding percentile history must be at least 2")
        for name, value in (
            ("price_move_min_fraction", self.price_move_min_fraction),
            ("open_interest_move_min_fraction", self.open_interest_move_min_fraction),
        ):
            if value.is_nan() or value.is_infinite() or value <= 0:
                raise ValueError(f"{name} must be a positive finite Decimal")


DEFAULT_DERIVATIVES_DYNAMICS_CONFIG = DerivativesDynamicsConfig()


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsMetrics:
    latest_funding_rate: Decimal | None
    funding_percentile_0_1: Decimal | None
    funding_acceleration_bps: Decimal | None
    latest_open_interest: Decimal | None
    open_interest_change_fraction: Decimal | None
    latest_mark_price: Decimal | None
    mark_price_change_fraction: Decimal | None
    latest_index_price: Decimal | None
    latest_basis_bps: Decimal | None
    basis_change_bps: Decimal | None
    funding_observation_count: int
    joint_price_oi_snapshot_count: int
    basis_observation_count: int
    available_component_count: int

    @property
    def latest_funding_bps(self) -> Decimal | None:
        if self.latest_funding_rate is None:
            return None
        return self.latest_funding_rate * _BPS


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: Exchange
    instrument_type: DerivativesInstrumentType
    symbol: str
    as_of_ms: int
    source_window_start_ms: int
    source_window_end_ms: int
    observed_at_ms: int
    consumed_observation_count: int
    latest_observation_age_ms: int
    status: DerivativesDynamicsStatus
    oi_price_state: OiPriceState
    metrics: DerivativesDynamicsMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "derivatives dynamics evidence identity")
        if self.engine_version != DERIVATIVES_DYNAMICS_ENGINE_VERSION:
            raise ValueError("unsupported derivatives dynamics engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("derivatives dynamics symbol must be uppercase")
        if not self.source_window_start_ms <= self.source_window_end_ms <= self.as_of_ms:
            raise ValueError("derivatives dynamics source window outside PIT bounds")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("derivatives dynamics observed evidence is from future")
        if self.consumed_observation_count <= 0 or self.latest_observation_age_ms < 0:
            raise ValueError("invalid derivatives dynamics observation accounting")
        if self.status is DerivativesDynamicsStatus.UNRESOLVED:
            if self.metrics is not None or self.oi_price_state is not OiPriceState.UNAVAILABLE:
                raise ValueError("unresolved derivatives dynamics cannot expose measured state")
            if not self.uncertainty_flags:
                raise ValueError("unresolved derivatives dynamics requires uncertainty")
        elif self.metrics is None:
            raise ValueError("measured derivatives dynamics requires metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("derivatives dynamics evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class DerivativesDynamicsEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: DerivativesDynamicsAnalysis
    observations: tuple[DerivativesObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "derivatives dynamics freeze identity")
        if self.schema_version != DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported derivatives dynamics freeze schema")
        if len(self.observations) != self.analysis.consumed_observation_count:
            raise ValueError("derivatives dynamics freeze observation count mismatch")
        if any(
            max(x.event_at_ms, x.source_timestamp_ms, x.ingested_at_ms) > self.analysis.as_of_ms
            for x in self.observations
        ):
            raise ValueError("derivatives dynamics freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("derivatives dynamics freeze identity mismatch")


def analyze_derivatives_dynamics(
    observations: Sequence[DerivativesObservation],
    *,
    as_of_ms: int,
    config: DerivativesDynamicsConfig = DEFAULT_DERIVATIVES_DYNAMICS_CONFIG,
) -> DerivativesDynamicsAnalysis:
    eligible = _eligible(observations, as_of_ms=as_of_ms)
    window = tuple(eligible[-config.lookback_observations :])
    first, latest = window[0], window[-1]
    age_ms = as_of_ms - latest.event_at_ms

    if age_ms > config.max_observation_age_ms:
        return _unresolved(window, as_of_ms, ("stale_derivatives_observation",))

    metrics, flags = _metrics(window, config)
    if metrics.available_component_count < config.minimum_components:
        return _unresolved(
            window,
            as_of_ms,
            (*flags, "insufficient_derivatives_components"),
        )

    state = _oi_price_state(metrics, config)
    payload = _payload(
        window=window,
        as_of_ms=as_of_ms,
        age_ms=age_ms,
        status=DerivativesDynamicsStatus.MEASURED,
        state=state,
        metrics=metrics,
        flags=flags,
    )
    return DerivativesDynamicsAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DERIVATIVES_DYNAMICS_ENGINE_VERSION,
        exchange=first.exchange,
        instrument_type=first.instrument_type,
        symbol=first.symbol,
        as_of_ms=as_of_ms,
        source_window_start_ms=first.event_at_ms,
        source_window_end_ms=latest.event_at_ms,
        observed_at_ms=max(x.ingested_at_ms for x in window),
        consumed_observation_count=len(window),
        latest_observation_age_ms=age_ms,
        status=DerivativesDynamicsStatus.MEASURED,
        oi_price_state=state,
        metrics=metrics,
        uncertainty_flags=flags,
    )


def build_derivatives_dynamics_evidence_freeze(
    observations: Sequence[DerivativesObservation],
    *,
    as_of_ms: int,
    config: DerivativesDynamicsConfig = DEFAULT_DERIVATIVES_DYNAMICS_CONFIG,
) -> DerivativesDynamicsEvidenceFreeze:
    analysis = analyze_derivatives_dynamics(
        observations,
        as_of_ms=as_of_ms,
        config=config,
    )
    eligible = _eligible(observations, as_of_ms=as_of_ms)
    consumed = tuple(eligible[-analysis.consumed_observation_count :])
    freeze = DerivativesDynamicsEvidenceFreeze(
        freeze_identity="0" * 64,
        schema_version=DERIVATIVES_DYNAMICS_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observations=consumed,
    )
    return DerivativesDynamicsEvidenceFreeze(
        freeze_identity=canonical_sha256(_freeze_payload(freeze)),
        schema_version=freeze.schema_version,
        analysis=freeze.analysis,
        observations=freeze.observations,
    )


def _eligible(
    observations: Sequence[DerivativesObservation],
    *,
    as_of_ms: int,
) -> tuple[DerivativesObservation, ...]:
    if not observations:
        raise ValueError("derivatives dynamics requires observations")
    if as_of_ms < 0:
        raise ValueError("as_of_ms must be non-negative")
    ordered = tuple(sorted(observations, key=lambda x: (x.event_at_ms, x.observation_identity)))
    context = (ordered[0].exchange, ordered[0].instrument_type, ordered[0].symbol)
    if any((x.exchange, x.instrument_type, x.symbol) != context for x in ordered):
        raise ValueError("derivatives dynamics observation context mismatch")
    ids = tuple(x.observation_identity for x in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("derivatives dynamics observations require unique identities")
    eligible = tuple(
        x for x in ordered
        if max(x.event_at_ms, x.source_timestamp_ms, x.ingested_at_ms) <= as_of_ms
    )
    if not eligible:
        raise ValueError("derivatives dynamics has no PIT-eligible observations")
    return eligible


def _metrics(
    observations: tuple[DerivativesObservation, ...],
    config: DerivativesDynamicsConfig,
) -> tuple[DerivativesDynamicsMetrics, tuple[str, ...]]:
    flags: list[str] = []

    funding = tuple(x for x in observations if x.funding_rate is not None)
    latest_funding = funding[-1].funding_rate if funding else None
    percentile: Decimal | None = None
    acceleration: Decimal | None = None
    if latest_funding is None:
        flags.append("funding_unavailable")
    else:
        if len(funding) >= config.funding_percentile_min_observations:
            values = tuple(x.funding_rate for x in funding if x.funding_rate is not None)
            percentile = Decimal(sum(v <= latest_funding for v in values)) / Decimal(len(values))
        else:
            flags.append("funding_percentile_insufficient_history")
        if len(funding) >= 2:
            previous = funding[-2].funding_rate
            assert previous is not None
            acceleration = (latest_funding - previous) * _BPS
        else:
            flags.append("funding_acceleration_unavailable")

    joint = tuple(
        x for x in observations
        if x.open_interest is not None and x.mark_price is not None and x.index_price is not None
    )
    latest_oi = joint[-1].open_interest if joint else None
    latest_mark = joint[-1].mark_price if joint else None
    latest_index = joint[-1].index_price if joint else None
    oi_change: Decimal | None = None
    price_change: Decimal | None = None
    if len(joint) >= 2:
        first_oi, last_oi = joint[0].open_interest, joint[-1].open_interest
        first_mark, last_mark = joint[0].mark_price, joint[-1].mark_price
        assert first_oi is not None and last_oi is not None
        assert first_mark is not None and last_mark is not None
        if first_oi == 0:
            flags.append("open_interest_baseline_zero")
        else:
            oi_change = (last_oi - first_oi) / first_oi
        price_change = (last_mark - first_mark) / first_mark
    else:
        flags.append("oi_price_history_unavailable")

    basis = tuple(x for x in observations if x.mark_price is not None and x.index_price is not None)
    latest_basis: Decimal | None = None
    basis_change: Decimal | None = None
    if basis:
        lm, li = basis[-1].mark_price, basis[-1].index_price
        assert lm is not None and li is not None
        latest_basis = (lm - li) / li * _BPS
        if len(basis) >= 2:
            fm, fi = basis[0].mark_price, basis[0].index_price
            assert fm is not None and fi is not None
            basis_change = latest_basis - ((fm - fi) / fi * _BPS)
        else:
            flags.append("basis_change_unavailable")
    else:
        flags.append("basis_unavailable")

    components = sum((
        latest_funding is not None,
        oi_change is not None and price_change is not None,
        latest_basis is not None,
    ))
    return DerivativesDynamicsMetrics(
        latest_funding_rate=latest_funding,
        funding_percentile_0_1=percentile,
        funding_acceleration_bps=acceleration,
        latest_open_interest=latest_oi,
        open_interest_change_fraction=oi_change,
        latest_mark_price=latest_mark,
        mark_price_change_fraction=price_change,
        latest_index_price=latest_index,
        latest_basis_bps=latest_basis,
        basis_change_bps=basis_change,
        funding_observation_count=len(funding),
        joint_price_oi_snapshot_count=len(joint),
        basis_observation_count=len(basis),
        available_component_count=components,
    ), tuple(flags)


def _oi_price_state(
    metrics: DerivativesDynamicsMetrics,
    config: DerivativesDynamicsConfig,
) -> OiPriceState:
    price, oi = metrics.mark_price_change_fraction, metrics.open_interest_change_fraction
    if price is None or oi is None:
        return OiPriceState.UNAVAILABLE
    pu, pd = price >= config.price_move_min_fraction, price <= -config.price_move_min_fraction
    ou, od = oi >= config.open_interest_move_min_fraction, oi <= -config.open_interest_move_min_fraction
    if pu:
        return OiPriceState.PRICE_UP_OI_UP if ou else (OiPriceState.PRICE_UP_OI_DOWN if od else OiPriceState.PRICE_UP_OI_FLAT)
    if pd:
        return OiPriceState.PRICE_DOWN_OI_UP if ou else (OiPriceState.PRICE_DOWN_OI_DOWN if od else OiPriceState.PRICE_DOWN_OI_FLAT)
    if ou:
        return OiPriceState.PRICE_FLAT_OI_EXPANDING
    if od:
        return OiPriceState.PRICE_FLAT_OI_CONTRACTING
    return OiPriceState.PRICE_FLAT_OI_STABLE


def _unresolved(
    window: tuple[DerivativesObservation, ...],
    as_of_ms: int,
    flags: tuple[str, ...],
) -> DerivativesDynamicsAnalysis:
    first, latest = window[0], window[-1]
    age_ms = as_of_ms - latest.event_at_ms
    payload = _payload(
        window=window,
        as_of_ms=as_of_ms,
        age_ms=age_ms,
        status=DerivativesDynamicsStatus.UNRESOLVED,
        state=OiPriceState.UNAVAILABLE,
        metrics=None,
        flags=flags,
    )
    return DerivativesDynamicsAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DERIVATIVES_DYNAMICS_ENGINE_VERSION,
        exchange=first.exchange,
        instrument_type=first.instrument_type,
        symbol=first.symbol,
        as_of_ms=as_of_ms,
        source_window_start_ms=first.event_at_ms,
        source_window_end_ms=latest.event_at_ms,
        observed_at_ms=max(x.ingested_at_ms for x in window),
        consumed_observation_count=len(window),
        latest_observation_age_ms=age_ms,
        status=DerivativesDynamicsStatus.UNRESOLVED,
        oi_price_state=OiPriceState.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _payload(
    *,
    window: tuple[DerivativesObservation, ...],
    as_of_ms: int,
    age_ms: int,
    status: DerivativesDynamicsStatus,
    state: OiPriceState,
    metrics: DerivativesDynamicsMetrics | None,
    flags: tuple[str, ...],
) -> dict[str, object]:
    first, latest = window[0], window[-1]
    return {
        "as_of_ms": as_of_ms,
        "consumed_observation_count": len(window),
        "engine_version": DERIVATIVES_DYNAMICS_ENGINE_VERSION,
        "exchange": first.exchange,
        "instrument_type": first.instrument_type,
        "latest_observation_age_ms": age_ms,
        "metrics": metrics,
        "observed_at_ms": max(x.ingested_at_ms for x in window),
        "oi_price_state": state,
        "source_window_end_ms": latest.event_at_ms,
        "source_window_start_ms": first.event_at_ms,
        "status": status,
        "symbol": first.symbol,
        "uncertainty_flags": flags,
    }


def _analysis_payload(analysis: DerivativesDynamicsAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "consumed_observation_count": analysis.consumed_observation_count,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "instrument_type": analysis.instrument_type,
        "latest_observation_age_ms": analysis.latest_observation_age_ms,
        "metrics": analysis.metrics,
        "observed_at_ms": analysis.observed_at_ms,
        "oi_price_state": analysis.oi_price_state,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "symbol": analysis.symbol,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(freeze: DerivativesDynamicsEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis": freeze.analysis,
        "observations": freeze.observations,
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
