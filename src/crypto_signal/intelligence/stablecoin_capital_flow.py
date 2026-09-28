from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.onchain_capital_flow import (
    StablecoinSupplyObservation,
)
from crypto_signal.ledger.serialization import canonical_sha256

STABLECOIN_CAPITAL_FLOW_ENGINE_VERSION = "stablecoin-capital-flow-v1/1"
STABLECOIN_CAPITAL_FLOW_FREEZE_SCHEMA_VERSION = (
    "stablecoin-capital-flow-freeze-v1/1"
)


class StablecoinCapitalFlowStatus(StrEnum):
    MEASURED = "measured"
    PARTIAL = "partial"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class StablecoinCapitalFlowConfig:
    max_observation_age_ms: int = 30 * 60 * 1000
    minimum_observations: int = 2
    lookback_observations: int = 8

    def __post_init__(self) -> None:
        if self.max_observation_age_ms <= 0:
            raise ValueError("stablecoin freshness budget must be positive")
        if self.minimum_observations < 2:
            raise ValueError("stablecoin delta requires two observations")
        if self.lookback_observations < self.minimum_observations:
            raise ValueError("stablecoin lookback below minimum observations")


DEFAULT_STABLECOIN_CAPITAL_FLOW_CONFIG = StablecoinCapitalFlowConfig()


@dataclass(frozen=True, slots=True)
class StablecoinCapitalFlowMetrics:
    current_circulating_amount: Decimal
    previous_circulating_amount: Decimal | None
    supply_delta: Decimal | None
    supply_delta_ratio: Decimal | None
    observation_count: int

    def __post_init__(self) -> None:
        _require_non_negative(
            self.current_circulating_amount,
            "current circulating amount",
        )
        if self.previous_circulating_amount is not None:
            _require_non_negative(
                self.previous_circulating_amount,
                "previous circulating amount",
            )
        _require_finite_optional(self.supply_delta, "stablecoin supply delta")
        _require_finite_optional(
            self.supply_delta_ratio,
            "stablecoin supply delta ratio",
        )
        if self.observation_count <= 0:
            raise ValueError("stablecoin metrics require observations")
        if self.observation_count < 2:
            if (
                self.previous_circulating_amount is not None
                or self.supply_delta is not None
                or self.supply_delta_ratio is not None
            ):
                raise ValueError(
                    "one stablecoin snapshot cannot expose a supply delta"
                )
        elif (
            self.previous_circulating_amount is None
            or self.supply_delta is None
        ):
            raise ValueError(
                "two stablecoin snapshots require an explicit supply delta"
            )


@dataclass(frozen=True, slots=True)
class StablecoinCapitalFlowAnalysis:
    evidence_identity: str
    engine_version: str
    asset: str
    network_scope: str
    provider: str
    provider_metric_identity: str
    as_of_ms: int
    observed_at_ms: int | None
    latest_observation_age_ms: int | None
    consumed_observation_count: int
    status: StablecoinCapitalFlowStatus
    metrics: StablecoinCapitalFlowMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.evidence_identity,
            "stablecoin capital-flow evidence identity",
        )
        if self.engine_version != STABLECOIN_CAPITAL_FLOW_ENGINE_VERSION:
            raise ValueError("unsupported stablecoin capital-flow engine")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("stablecoin analysis asset must be uppercase")
        for value in (
            self.network_scope,
            self.provider,
            self.provider_metric_identity,
        ):
            if not value.strip():
                raise ValueError("stablecoin analysis context cannot be empty")
        if self.as_of_ms < 0:
            raise ValueError("stablecoin analysis as-of cannot be negative")
        if (
            self.observed_at_ms is not None
            and not 0 <= self.observed_at_ms <= self.as_of_ms
        ):
            raise ValueError("stablecoin observed_at outside PIT bounds")
        if (
            self.latest_observation_age_ms is not None
            and self.latest_observation_age_ms < 0
        ):
            raise ValueError("stablecoin observation age cannot be negative")
        if self.consumed_observation_count < 0:
            raise ValueError("stablecoin consumed count cannot be negative")
        if tuple(sorted(set(self.uncertainty_flags))) != self.uncertainty_flags:
            raise ValueError("stablecoin uncertainty flags must be canonical")
        if self.status in {
            StablecoinCapitalFlowStatus.STALE,
            StablecoinCapitalFlowStatus.UNAVAILABLE,
        }:
            if self.metrics is not None:
                raise ValueError(
                    "stale/unavailable stablecoin state cannot expose metrics"
                )
            if not self.uncertainty_flags:
                raise ValueError(
                    "stale/unavailable stablecoin state requires uncertainty"
                )
        elif self.metrics is None:
            raise ValueError(
                "measured/partial stablecoin state requires metrics"
            )
        if self.evidence_identity != canonical_sha256(
            _analysis_payload(self)
        ):
            raise ValueError("stablecoin evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class StablecoinCapitalFlowEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: StablecoinCapitalFlowAnalysis
    observations: tuple[StablecoinSupplyObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(
            self.freeze_identity,
            "stablecoin capital-flow freeze identity",
        )
        if self.schema_version != STABLECOIN_CAPITAL_FLOW_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported stablecoin capital-flow freeze")
        if len(self.observations) != self.analysis.consumed_observation_count:
            raise ValueError("stablecoin freeze observation count mismatch")
        if any(
            max(
                item.source_timestamp_ms,
                item.observed_at_ms,
                item.ingested_at_ms,
            )
            > self.analysis.as_of_ms
            for item in self.observations
        ):
            raise ValueError("stablecoin freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("stablecoin freeze identity mismatch")


def build_stablecoin_capital_flow_evidence_freeze(
    observations: Sequence[StablecoinSupplyObservation],
    *,
    as_of_ms: int,
    config: StablecoinCapitalFlowConfig = (
        DEFAULT_STABLECOIN_CAPITAL_FLOW_CONFIG
    ),
) -> StablecoinCapitalFlowEvidenceFreeze:
    if not observations:
        raise ValueError("stablecoin capital-flow requires observations")
    if as_of_ms < 0:
        raise ValueError("stablecoin capital-flow as-of cannot be negative")

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.source_timestamp_ms,
                item.observed_at_ms,
                item.observation_identity,
            ),
        )
    )
    _validate_context(ordered)
    _reject_duplicates(ordered)
    eligible = tuple(
        item
        for item in ordered
        if max(
            item.source_timestamp_ms,
            item.observed_at_ms,
            item.ingested_at_ms,
        )
        <= as_of_ms
    )
    context = ordered[0]
    boundary_flags = (
        "stablecoin_supply_is_descriptive_not_directional",
        "stablecoin_supply_change_is_not_risk_asset_flow",
        "stablecoin_supply_does_not_attribute_actor_intent",
    )
    if not eligible:
        return _freeze(
            _analysis(
                context=context,
                window=(),
                as_of_ms=as_of_ms,
                status=StablecoinCapitalFlowStatus.UNAVAILABLE,
                metrics=None,
                flags=(
                    *boundary_flags,
                    "stablecoin_supply_unavailable_at_as_of",
                ),
            ),
            (),
        )

    window = eligible[-config.lookback_observations :]
    latest = window[-1]
    age_ms = as_of_ms - latest.source_timestamp_ms
    if age_ms > config.max_observation_age_ms:
        return _freeze(
            _analysis(
                context=context,
                window=window,
                as_of_ms=as_of_ms,
                status=StablecoinCapitalFlowStatus.STALE,
                metrics=None,
                flags=(
                    *boundary_flags,
                    "stale_stablecoin_supply_observation",
                ),
            ),
            window,
        )

    previous = window[-2] if len(window) >= 2 else None
    if previous is None:
        delta: Decimal | None = None
        delta_ratio: Decimal | None = None
    else:
        delta = latest.circulating_amount - previous.circulating_amount
        delta_ratio = (
            None
            if previous.circulating_amount == Decimal(0)
            else delta / previous.circulating_amount
        )
    flags = list(boundary_flags)
    if previous is None:
        flags.append("stablecoin_supply_history_insufficient_for_delta")
    elif previous.circulating_amount == Decimal(0):
        flags.append("stablecoin_supply_delta_ratio_unavailable_zero_baseline")
    if delta == Decimal(0):
        flags.append("stablecoin_supply_delta_measured_zero")

    metrics = StablecoinCapitalFlowMetrics(
        current_circulating_amount=latest.circulating_amount,
        previous_circulating_amount=(
            None if previous is None else previous.circulating_amount
        ),
        supply_delta=delta,
        supply_delta_ratio=delta_ratio,
        observation_count=len(window),
    )
    status = (
        StablecoinCapitalFlowStatus.MEASURED
        if len(window) >= config.minimum_observations
        else StablecoinCapitalFlowStatus.PARTIAL
    )
    analysis = _analysis(
        context=context,
        window=window,
        as_of_ms=as_of_ms,
        status=status,
        metrics=metrics,
        flags=tuple(flags),
    )
    return _freeze(analysis, window)


def _validate_context(
    observations: tuple[StablecoinSupplyObservation, ...],
) -> None:
    first = observations[0]
    expected = (
        first.asset,
        first.network_scope,
        first.provider,
        first.provider_metric_identity,
        first.source_timestamp_semantic,
    )
    if any(
        (
            item.asset,
            item.network_scope,
            item.provider,
            item.provider_metric_identity,
            item.source_timestamp_semantic,
        )
        != expected
        for item in observations
    ):
        raise ValueError(
            "stablecoin observations require exact source context"
        )


def _reject_duplicates(
    observations: tuple[StablecoinSupplyObservation, ...],
) -> None:
    identities = tuple(item.observation_identity for item in observations)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate stablecoin observation identity")


def _analysis(
    *,
    context: StablecoinSupplyObservation,
    window: tuple[StablecoinSupplyObservation, ...],
    as_of_ms: int,
    status: StablecoinCapitalFlowStatus,
    metrics: StablecoinCapitalFlowMetrics | None,
    flags: tuple[str, ...],
) -> StablecoinCapitalFlowAnalysis:
    canonical_flags = tuple(sorted(set(flags)))
    latest = None if not window else window[-1]
    payload = {
        "asset": context.asset,
        "as_of_ms": as_of_ms,
        "consumed_observation_count": len(window),
        "engine_version": STABLECOIN_CAPITAL_FLOW_ENGINE_VERSION,
        "latest_observation_age_ms": (
            None
            if latest is None
            else as_of_ms - latest.source_timestamp_ms
        ),
        "metrics": metrics,
        "network_scope": context.network_scope,
        "observed_at_ms": (
            None
            if latest is None
            else max(item.ingested_at_ms for item in window)
        ),
        "provider": context.provider,
        "provider_metric_identity": context.provider_metric_identity,
        "status": status,
        "uncertainty_flags": canonical_flags,
    }
    return StablecoinCapitalFlowAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=STABLECOIN_CAPITAL_FLOW_ENGINE_VERSION,
        asset=context.asset,
        network_scope=context.network_scope,
        provider=context.provider,
        provider_metric_identity=context.provider_metric_identity,
        as_of_ms=as_of_ms,
        observed_at_ms=(
            None
            if latest is None
            else max(item.ingested_at_ms for item in window)
        ),
        latest_observation_age_ms=(
            None
            if latest is None
            else as_of_ms - latest.source_timestamp_ms
        ),
        consumed_observation_count=len(window),
        status=status,
        metrics=metrics,
        uncertainty_flags=canonical_flags,
    )


def _freeze(
    analysis: StablecoinCapitalFlowAnalysis,
    observations: tuple[StablecoinSupplyObservation, ...],
) -> StablecoinCapitalFlowEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "observation_identities": [
            item.observation_identity for item in observations
        ],
        "schema_version": STABLECOIN_CAPITAL_FLOW_FREEZE_SCHEMA_VERSION,
    }
    return StablecoinCapitalFlowEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=STABLECOIN_CAPITAL_FLOW_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observations=observations,
    )


def _analysis_payload(
    analysis: StablecoinCapitalFlowAnalysis,
) -> dict[str, object]:
    return {
        "asset": analysis.asset,
        "as_of_ms": analysis.as_of_ms,
        "consumed_observation_count": analysis.consumed_observation_count,
        "engine_version": analysis.engine_version,
        "latest_observation_age_ms": analysis.latest_observation_age_ms,
        "metrics": analysis.metrics,
        "network_scope": analysis.network_scope,
        "observed_at_ms": analysis.observed_at_ms,
        "provider": analysis.provider,
        "provider_metric_identity": analysis.provider_metric_identity,
        "status": analysis.status,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze_payload(
    freeze: StablecoinCapitalFlowEvidenceFreeze,
) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "observation_identities": [
            item.observation_identity for item in freeze.observations
        ],
        "schema_version": freeze.schema_version,
    }


def _require_non_negative(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")


def _require_finite_optional(value: Decimal | None, label: str) -> None:
    if value is not None and (value.is_nan() or value.is_infinite()):
        raise ValueError(f"{label} must be finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be SHA256")
