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

DERIVATIVES_CONTEXT_ENGINE_VERSION = "bounded-derivatives-context-v1/1"
DERIVATIVES_CONTEXT_FREEZE_SCHEMA_VERSION = (
    "bounded-derivatives-context-freeze-v1/1"
)
_BPS = Decimal(10_000)


class FundingState(StrEnum):
    POSITIVE_EXTREME = "positive_extreme"
    NEGATIVE_EXTREME = "negative_extreme"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class OpenInterestState(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNAVAILABLE = "unavailable"


class BasisState(StrEnum):
    PREMIUM = "premium"
    DISCOUNT = "discount"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class DerivativesContextLabel(StrEnum):
    CROWDED_LONG = "crowded_long"
    CROWDED_SHORT = "crowded_short"
    LEVERAGE_BUILDUP = "leverage_buildup"
    DELEVERAGING = "deleveraging"
    BALANCED = "balanced"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class DerivativesContextConfig:
    lookback_observations: int = 16
    minimum_components: int = 2
    max_observation_age_ms: int = 30 * 60_000
    funding_extreme_bps: Decimal = Decimal(5)
    open_interest_change_min_fraction: Decimal = Decimal("0.05")
    basis_extreme_bps: Decimal = Decimal(25)

    def __post_init__(self) -> None:
        if self.lookback_observations < 2:
            raise ValueError("lookback_observations must be at least 2")
        if not 1 <= self.minimum_components <= 3:
            raise ValueError("minimum_components must be inside [1,3]")
        if self.max_observation_age_ms <= 0:
            raise ValueError("max_observation_age_ms must be positive")
        if self.funding_extreme_bps <= Decimal(0):
            raise ValueError("funding extreme threshold must be positive")
        if self.open_interest_change_min_fraction <= Decimal(0):
            raise ValueError("open-interest change threshold must be positive")
        if self.basis_extreme_bps <= Decimal(0):
            raise ValueError("basis extreme threshold must be positive")


DEFAULT_DERIVATIVES_CONTEXT_CONFIG = DerivativesContextConfig()


@dataclass(frozen=True, slots=True)
class DerivativesContextMetrics:
    latest_funding_rate: Decimal | None
    funding_rate_bps: Decimal | None
    latest_open_interest: Decimal | None
    open_interest_change_fraction: Decimal | None
    basis_bps: Decimal | None
    observation_count: int
    available_component_count: int

    def __post_init__(self) -> None:
        if self.observation_count <= 0:
            raise ValueError("derivatives metrics require observations")
        if not 1 <= self.available_component_count <= 3:
            raise ValueError("available component count must be inside [1,3]")
        for label, value in (
            ("latest_funding_rate", self.latest_funding_rate),
            ("funding_rate_bps", self.funding_rate_bps),
            ("latest_open_interest", self.latest_open_interest),
            (
                "open_interest_change_fraction",
                self.open_interest_change_fraction,
            ),
            ("basis_bps", self.basis_bps),
        ):
            if value is not None and (value.is_nan() or value.is_infinite()):
                raise ValueError(f"{label} must be finite")
        if (
            self.latest_open_interest is not None
            and self.latest_open_interest < Decimal(0)
        ):
            raise ValueError("latest_open_interest cannot be negative")
        if (self.latest_funding_rate is None) != (self.funding_rate_bps is None):
            raise ValueError("funding rate and funding bps must appear together")
        if self.latest_funding_rate is not None and self.funding_rate_bps != (
            self.latest_funding_rate * _BPS
        ):
            raise ValueError("funding bps mismatch")


@dataclass(frozen=True, slots=True)
class DerivativesContextAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: Exchange
    instrument_type: DerivativesInstrumentType
    symbol: str
    as_of_ms: int
    market_available_at_ms: int
    observed_at_ms: int
    source_cutoff_event_at_ms: int
    consumed_observation_count: int
    label: DerivativesContextLabel
    funding_state: FundingState
    open_interest_state: OpenInterestState
    basis_state: BasisState
    metrics: DerivativesContextMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.evidence_identity,
            "derivatives context evidence identity",
        )
        if self.engine_version != DERIVATIVES_CONTEXT_ENGINE_VERSION:
            raise ValueError("unsupported derivatives context engine version")
        if self.as_of_ms < 0:
            raise ValueError("derivatives context as_of_ms must be non-negative")
        if self.market_available_at_ms > self.as_of_ms:
            raise ValueError("derivatives market evidence is from the future")
        if self.observed_at_ms > self.as_of_ms:
            raise ValueError("derivatives observed evidence is from the future")
        if self.source_cutoff_event_at_ms > self.as_of_ms:
            raise ValueError("derivatives source cutoff is from the future")
        if self.consumed_observation_count <= 0:
            raise ValueError("derivatives context must consume observations")
        if len(set(self.uncertainty_flags)) != len(self.uncertainty_flags):
            raise ValueError("derivatives uncertainty flags must be unique")
        if self.label is DerivativesContextLabel.UNRESOLVED:
            if not self.uncertainty_flags:
                raise ValueError("unresolved derivatives context requires uncertainty")
            if self.metrics is not None:
                raise ValueError("unresolved derivatives context cannot fabricate metrics")
            if self.funding_state is not FundingState.UNAVAILABLE:
                raise ValueError("unresolved context funding state must be unavailable")
            if self.open_interest_state is not OpenInterestState.UNAVAILABLE:
                raise ValueError("unresolved context OI state must be unavailable")
            if self.basis_state is not BasisState.UNAVAILABLE:
                raise ValueError("unresolved context basis state must be unavailable")
        elif self.metrics is None:
            raise ValueError("resolved derivatives context requires metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("derivatives context evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class DerivativesContextEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: DerivativesContextAnalysis
    observations: tuple[DerivativesObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.freeze_identity,
            "derivatives context freeze identity",
        )
        if self.schema_version != DERIVATIVES_CONTEXT_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported derivatives context freeze schema")
        if not self.observations:
            raise ValueError("derivatives context freeze requires observations")
        if len(self.observations) != self.analysis.consumed_observation_count:
            raise ValueError("derivatives context freeze observation count mismatch")
        if (
            self.observations[-1].event_at_ms
            != self.analysis.source_cutoff_event_at_ms
        ):
            raise ValueError("derivatives context freeze source cutoff mismatch")
        if any(
            observation.event_at_ms > self.analysis.as_of_ms
            or observation.source_timestamp_ms > self.analysis.as_of_ms
            or observation.ingested_at_ms > self.analysis.as_of_ms
            for observation in self.observations
        ):
            raise ValueError("derivatives context freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("derivatives context freeze identity mismatch")


def analyze_derivatives_context(
    observations: Sequence[DerivativesObservation],
    *,
    as_of_ms: int,
    config: DerivativesContextConfig = DEFAULT_DERIVATIVES_CONTEXT_CONFIG,
) -> DerivativesContextAnalysis:
    eligible = _eligible_observations(observations, as_of_ms=as_of_ms)
    window = eligible[-config.lookback_observations :]
    first = window[0]
    latest = window[-1]

    label = DerivativesContextLabel.UNRESOLVED
    funding_state = FundingState.UNAVAILABLE
    open_interest_state = OpenInterestState.UNAVAILABLE
    basis_state = BasisState.UNAVAILABLE
    metrics: DerivativesContextMetrics | None = None
    uncertainty: tuple[str, ...] = ()

    if as_of_ms - latest.event_at_ms > config.max_observation_age_ms:
        uncertainty = ("stale_derivatives_observation",)
    else:
        candidate, flags = _derive_metrics(window)
        if candidate.available_component_count < config.minimum_components:
            uncertainty = (*flags, "insufficient_derivatives_components")
        else:
            metrics = candidate
            funding_state = _funding_state(candidate, config=config)
            open_interest_state = _open_interest_state(candidate, config=config)
            basis_state = _basis_state(candidate, config=config)
            label, label_flags = _label(
                funding_state=funding_state,
                open_interest_state=open_interest_state,
                basis_state=basis_state,
            )
            uncertainty = tuple((*flags, *label_flags))

    payload = {
        "engine_version": DERIVATIVES_CONTEXT_ENGINE_VERSION,
        "exchange": first.exchange,
        "instrument_type": first.instrument_type,
        "symbol": first.symbol,
        "as_of_ms": as_of_ms,
        "market_available_at_ms": latest.event_at_ms,
        "observed_at_ms": max(item.ingested_at_ms for item in window),
        "source_cutoff_event_at_ms": latest.event_at_ms,
        "consumed_observation_count": len(window),
        "label": label,
        "funding_state": funding_state,
        "open_interest_state": open_interest_state,
        "basis_state": basis_state,
        "metrics": metrics,
        "uncertainty_flags": uncertainty,
    }
    return DerivativesContextAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DERIVATIVES_CONTEXT_ENGINE_VERSION,
        exchange=first.exchange,
        instrument_type=first.instrument_type,
        symbol=first.symbol,
        as_of_ms=as_of_ms,
        market_available_at_ms=latest.event_at_ms,
        observed_at_ms=max(item.ingested_at_ms for item in window),
        source_cutoff_event_at_ms=latest.event_at_ms,
        consumed_observation_count=len(window),
        label=label,
        funding_state=funding_state,
        open_interest_state=open_interest_state,
        basis_state=basis_state,
        metrics=metrics,
        uncertainty_flags=uncertainty,
    )


def build_derivatives_context_evidence_freeze(
    observations: Sequence[DerivativesObservation],
    *,
    as_of_ms: int,
    config: DerivativesContextConfig = DEFAULT_DERIVATIVES_CONTEXT_CONFIG,
) -> DerivativesContextEvidenceFreeze:
    analysis = analyze_derivatives_context(
        observations,
        as_of_ms=as_of_ms,
        config=config,
    )
    eligible = _eligible_observations(observations, as_of_ms=as_of_ms)
    consumed = tuple(eligible[-analysis.consumed_observation_count :])
    payload = {
        "schema_version": DERIVATIVES_CONTEXT_FREEZE_SCHEMA_VERSION,
        "analysis": analysis,
        "observations": consumed,
    }
    return DerivativesContextEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=DERIVATIVES_CONTEXT_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observations=consumed,
    )


def _eligible_observations(
    observations: Sequence[DerivativesObservation],
    *,
    as_of_ms: int,
) -> tuple[DerivativesObservation, ...]:
    if not observations:
        raise ValueError("derivatives context requires observations")
    if as_of_ms < 0:
        raise ValueError("as_of_ms must be non-negative")

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (item.event_at_ms, item.observation_identity),
        )
    )
    context = (
        ordered[0].exchange,
        ordered[0].instrument_type,
        ordered[0].symbol,
    )
    if any(
        (
            item.exchange,
            item.instrument_type,
            item.symbol,
        )
        != context
        for item in ordered
    ):
        raise ValueError("derivatives observation context mismatch")
    identities = tuple(item.observation_identity for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("derivatives observations must have unique identities")

    eligible = tuple(
        item
        for item in ordered
        if item.event_at_ms <= as_of_ms
        and item.source_timestamp_ms <= as_of_ms
        and item.ingested_at_ms <= as_of_ms
    )
    if not eligible:
        raise ValueError("derivatives context has no PIT-eligible observations")
    return eligible


def _derive_metrics(
    observations: Sequence[DerivativesObservation],
) -> tuple[DerivativesContextMetrics, tuple[str, ...]]:
    funding_observation = next(
        (
            item
            for item in reversed(observations)
            if item.funding_rate is not None
        ),
        None,
    )
    funding_rate = (
        None if funding_observation is None else funding_observation.funding_rate
    )
    funding_bps = None if funding_rate is None else funding_rate * _BPS

    oi_observations = tuple(
        item for item in observations if item.open_interest is not None
    )
    latest_oi = (
        None if not oi_observations else oi_observations[-1].open_interest
    )
    oi_change: Decimal | None = None
    oi_baseline_zero = False
    if len(oi_observations) >= 2:
        first_oi = oi_observations[0].open_interest
        last_oi = oi_observations[-1].open_interest
        assert first_oi is not None
        assert last_oi is not None
        if first_oi == Decimal(0):
            oi_baseline_zero = True
        else:
            oi_change = (last_oi - first_oi) / first_oi

    basis_observation = next(
        (
            item
            for item in reversed(observations)
            if item.mark_price is not None and item.index_price is not None
        ),
        None,
    )
    basis_bps: Decimal | None = None
    if basis_observation is not None:
        mark = basis_observation.mark_price
        index = basis_observation.index_price
        assert mark is not None
        assert index is not None
        basis_bps = (mark - index) / index * _BPS

    component_count = sum(
        value is not None
        for value in (
            funding_bps,
            oi_change,
            basis_bps,
        )
    )
    flags: list[str] = []
    if funding_bps is None:
        flags.append("funding_unavailable")
    if oi_change is None:
        flags.append(
            "open_interest_baseline_zero"
            if oi_baseline_zero
            else "open_interest_trend_unavailable"
        )
    if basis_bps is None:
        flags.append("basis_unavailable")

    return (
        DerivativesContextMetrics(
            latest_funding_rate=funding_rate,
            funding_rate_bps=funding_bps,
            latest_open_interest=latest_oi,
            open_interest_change_fraction=oi_change,
            basis_bps=basis_bps,
            observation_count=len(observations),
            available_component_count=component_count,
        ),
        tuple(flags),
    )


def _funding_state(
    metrics: DerivativesContextMetrics,
    *,
    config: DerivativesContextConfig,
) -> FundingState:
    value = metrics.funding_rate_bps
    if value is None:
        return FundingState.UNAVAILABLE
    if value >= config.funding_extreme_bps:
        return FundingState.POSITIVE_EXTREME
    if value <= -config.funding_extreme_bps:
        return FundingState.NEGATIVE_EXTREME
    return FundingState.NEUTRAL


def _open_interest_state(
    metrics: DerivativesContextMetrics,
    *,
    config: DerivativesContextConfig,
) -> OpenInterestState:
    value = metrics.open_interest_change_fraction
    if value is None:
        return OpenInterestState.UNAVAILABLE
    if value >= config.open_interest_change_min_fraction:
        return OpenInterestState.RISING
    if value <= -config.open_interest_change_min_fraction:
        return OpenInterestState.FALLING
    return OpenInterestState.STABLE


def _basis_state(
    metrics: DerivativesContextMetrics,
    *,
    config: DerivativesContextConfig,
) -> BasisState:
    value = metrics.basis_bps
    if value is None:
        return BasisState.UNAVAILABLE
    if value >= config.basis_extreme_bps:
        return BasisState.PREMIUM
    if value <= -config.basis_extreme_bps:
        return BasisState.DISCOUNT
    return BasisState.NEUTRAL


def _label(
    *,
    funding_state: FundingState,
    open_interest_state: OpenInterestState,
    basis_state: BasisState,
) -> tuple[DerivativesContextLabel, tuple[str, ...]]:
    if (
        funding_state is FundingState.POSITIVE_EXTREME
        and open_interest_state is OpenInterestState.RISING
        and basis_state is BasisState.PREMIUM
    ):
        return DerivativesContextLabel.CROWDED_LONG, ()
    if (
        funding_state is FundingState.NEGATIVE_EXTREME
        and open_interest_state is OpenInterestState.RISING
        and basis_state is BasisState.DISCOUNT
    ):
        return DerivativesContextLabel.CROWDED_SHORT, ()
    if open_interest_state is OpenInterestState.FALLING:
        return DerivativesContextLabel.DELEVERAGING, ()
    if open_interest_state is OpenInterestState.RISING:
        return DerivativesContextLabel.LEVERAGE_BUILDUP, ()
    if (
        funding_state is FundingState.NEUTRAL
        and open_interest_state is OpenInterestState.STABLE
        and basis_state is BasisState.NEUTRAL
    ):
        return DerivativesContextLabel.BALANCED, ()
    return (
        DerivativesContextLabel.MIXED,
        ("component_disagreement_or_incomplete_alignment",),
    )


def _analysis_payload(
    analysis: DerivativesContextAnalysis,
) -> dict[str, object]:
    return {
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "instrument_type": analysis.instrument_type,
        "symbol": analysis.symbol,
        "as_of_ms": analysis.as_of_ms,
        "market_available_at_ms": analysis.market_available_at_ms,
        "observed_at_ms": analysis.observed_at_ms,
        "source_cutoff_event_at_ms": analysis.source_cutoff_event_at_ms,
        "consumed_observation_count": analysis.consumed_observation_count,
        "label": analysis.label,
        "funding_state": analysis.funding_state,
        "open_interest_state": analysis.open_interest_state,
        "basis_state": analysis.basis_state,
        "metrics": analysis.metrics,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(
    freeze: DerivativesContextEvidenceFreeze,
) -> dict[str, object]:
    return {
        "schema_version": freeze.schema_version,
        "analysis": freeze.analysis,
        "observations": freeze.observations,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
