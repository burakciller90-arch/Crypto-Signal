from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.exchange_flows import ExchangeFlowObservation
from crypto_signal.ledger.serialization import canonical_sha256

EXCHANGE_FLOW_ENGINE_VERSION = "exchange-flow-v2-slice1/1"
EXCHANGE_FLOW_FREEZE_SCHEMA_VERSION = "exchange-flow-freeze-v1/1"
_HOUR_MS = Decimal(3_600_000)


class ExchangeFlowStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class ExchangeFlowLabel(StrEnum):
    INFLOW_ANOMALY = "inflow_anomaly"
    OUTFLOW_ANOMALY = "outflow_anomaly"
    BALANCED = "balanced"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


class NetflowDirection(StrEnum):
    TO_EXCHANGES = "to_exchanges"
    FROM_EXCHANGES = "from_exchanges"
    BALANCED = "balanced"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ExchangeFlowConfig:
    lookback_observations: int = 30
    minimum_observations: int = 5
    max_observation_age_ms: int = 6 * 60 * 60_000
    anomaly_percentile: Decimal = Decimal("0.90")
    balanced_netflow_fraction_of_gross: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        if not 2 <= self.minimum_observations <= self.lookback_observations:
            raise ValueError("exchange-flow counts must satisfy 2 <= minimum <= lookback")
        if self.max_observation_age_ms <= 0:
            raise ValueError("exchange-flow max observation age must be positive")
        if (
            self.anomaly_percentile.is_nan()
            or self.anomaly_percentile.is_infinite()
            or not Decimal("0.50") < self.anomaly_percentile <= Decimal(1)
        ):
            raise ValueError("exchange-flow anomaly percentile must be inside (0.5,1]")
        if (
            self.balanced_netflow_fraction_of_gross.is_nan()
            or self.balanced_netflow_fraction_of_gross.is_infinite()
            or not Decimal(0)
            <= self.balanced_netflow_fraction_of_gross
            < Decimal(1)
        ):
            raise ValueError("balanced netflow fraction must be inside [0,1)")


DEFAULT_EXCHANGE_FLOW_CONFIG = ExchangeFlowConfig()


@dataclass(frozen=True, slots=True)
class ExchangeFlowMetrics:
    latest_inflow_amount: Decimal
    latest_outflow_amount: Decimal
    latest_netflow_amount: Decimal
    latest_gross_flow_amount: Decimal
    latest_inflow_rate_per_hour: Decimal
    latest_outflow_rate_per_hour: Decimal
    latest_netflow_rate_per_hour: Decimal
    inflow_rate_percentile_0_1: Decimal
    outflow_rate_percentile_0_1: Decimal
    abs_netflow_rate_percentile_0_1: Decimal
    netflow_rate_velocity_per_hour: Decimal | None
    observation_count: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.latest_inflow_amount, "latest_inflow_amount"),
            (self.latest_outflow_amount, "latest_outflow_amount"),
            (self.latest_netflow_amount, "latest_netflow_amount"),
            (self.latest_gross_flow_amount, "latest_gross_flow_amount"),
            (self.latest_inflow_rate_per_hour, "latest_inflow_rate_per_hour"),
            (self.latest_outflow_rate_per_hour, "latest_outflow_rate_per_hour"),
            (self.latest_netflow_rate_per_hour, "latest_netflow_rate_per_hour"),
            (self.inflow_rate_percentile_0_1, "inflow_rate_percentile_0_1"),
            (self.outflow_rate_percentile_0_1, "outflow_rate_percentile_0_1"),
            (
                self.abs_netflow_rate_percentile_0_1,
                "abs_netflow_rate_percentile_0_1",
            ),
            (
                self.netflow_rate_velocity_per_hour,
                "netflow_rate_velocity_per_hour",
            ),
        ):
            if value is not None and (value.is_nan() or value.is_infinite()):
                raise ValueError(f"{label} must be finite")
        if min(self.latest_inflow_amount, self.latest_outflow_amount) < Decimal(0):
            raise ValueError("exchange-flow amounts cannot be negative")
        if self.latest_gross_flow_amount != (
            self.latest_inflow_amount + self.latest_outflow_amount
        ):
            raise ValueError("exchange-flow gross amount mismatch")
        if self.latest_netflow_amount != (
            self.latest_inflow_amount - self.latest_outflow_amount
        ):
            raise ValueError("exchange-flow net amount mismatch")
        for value in (
            self.inflow_rate_percentile_0_1,
            self.outflow_rate_percentile_0_1,
            self.abs_netflow_rate_percentile_0_1,
        ):
            if not Decimal(0) <= value <= Decimal(1):
                raise ValueError("exchange-flow percentile outside [0,1]")
        if self.observation_count < 2:
            raise ValueError("exchange-flow metrics require at least two observations")


@dataclass(frozen=True, slots=True)
class ExchangeFlowAnalysis:
    evidence_identity: str
    engine_version: str
    asset: str
    exchange_scope: str
    source_provider: str
    attribution_method: str
    as_of_ms: int
    source_window_start_ms: int | None
    source_window_end_ms: int | None
    observed_at_ms: int | None
    consumed_observation_count: int
    latest_observation_age_ms: int | None
    status: ExchangeFlowStatus
    label: ExchangeFlowLabel
    netflow_direction: NetflowDirection
    metrics: ExchangeFlowMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "exchange-flow evidence identity")
        if self.engine_version != EXCHANGE_FLOW_ENGINE_VERSION:
            raise ValueError("unsupported exchange-flow engine version")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("exchange-flow analysis asset must be uppercase")
        for value, label in (
            (self.exchange_scope, "exchange-flow scope"),
            (self.source_provider, "exchange-flow source provider"),
            (self.attribution_method, "exchange-flow attribution method"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.as_of_ms < 0 or self.consumed_observation_count < 0:
            raise ValueError("exchange-flow analysis counters cannot be negative")
        has_window = self.source_window_start_ms is not None
        if has_window != (self.source_window_end_ms is not None):
            raise ValueError("exchange-flow source window bounds must appear together")
        if self.consumed_observation_count == 0:
            if any(
                value is not None
                for value in (
                    self.source_window_start_ms,
                    self.source_window_end_ms,
                    self.observed_at_ms,
                    self.latest_observation_age_ms,
                )
            ):
                raise ValueError("empty exchange-flow analysis cannot expose source times")
        else:
            if (
                self.source_window_start_ms is None
                or self.source_window_end_ms is None
                or self.observed_at_ms is None
                or self.latest_observation_age_ms is None
            ):
                raise ValueError("exchange-flow consumed evidence requires source times")
            if not (
                0
                <= self.source_window_start_ms
                < self.source_window_end_ms
                <= self.as_of_ms
            ):
                raise ValueError("exchange-flow analysis window outside PIT bounds")
            if not 0 <= self.observed_at_ms <= self.as_of_ms:
                raise ValueError("exchange-flow observed_at outside PIT bounds")
            if self.latest_observation_age_ms < 0:
                raise ValueError("exchange-flow observation age cannot be negative")

        if self.status is ExchangeFlowStatus.UNRESOLVED:
            if self.label is not ExchangeFlowLabel.UNRESOLVED:
                raise ValueError("unresolved exchange-flow analysis needs unresolved label")
            if self.netflow_direction is not NetflowDirection.UNAVAILABLE:
                raise ValueError("unresolved exchange-flow direction must be unavailable")
            if self.metrics is not None or not self.uncertainty_flags:
                raise ValueError("unresolved exchange-flow analysis requires uncertainty only")
        else:
            if self.metrics is None:
                raise ValueError("measured exchange-flow analysis requires metrics")
            if self.netflow_direction is NetflowDirection.UNAVAILABLE:
                raise ValueError("measured exchange-flow direction cannot be unavailable")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("exchange-flow evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class ExchangeFlowEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: ExchangeFlowAnalysis
    observations: tuple[ExchangeFlowObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "exchange-flow freeze identity")
        if self.schema_version != EXCHANGE_FLOW_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported exchange-flow freeze schema")
        if len(self.observations) != self.analysis.consumed_observation_count:
            raise ValueError("exchange-flow freeze observation count mismatch")
        if any(
            max(
                item.window_end_ms,
                item.source_timestamp_ms,
                item.ingested_at_ms,
            )
            > self.analysis.as_of_ms
            for item in self.observations
        ):
            raise ValueError("exchange-flow freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("exchange-flow freeze identity mismatch")


def analyze_exchange_flow(
    observations: Sequence[ExchangeFlowObservation],
    *,
    as_of_ms: int,
    config: ExchangeFlowConfig = DEFAULT_EXCHANGE_FLOW_CONFIG,
) -> ExchangeFlowAnalysis:
    return build_exchange_flow_evidence_freeze(
        observations,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_exchange_flow_evidence_freeze(
    observations: Sequence[ExchangeFlowObservation],
    *,
    as_of_ms: int,
    config: ExchangeFlowConfig = DEFAULT_EXCHANGE_FLOW_CONFIG,
) -> ExchangeFlowEvidenceFreeze:
    if not observations:
        raise ValueError("exchange-flow analysis requires observations")
    if as_of_ms < 0:
        raise ValueError("exchange-flow as_of_ms must be non-negative")

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.window_end_ms,
                item.source_timestamp_ms,
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
            item.window_end_ms,
            item.source_timestamp_ms,
            item.ingested_at_ms,
        )
        <= as_of_ms
    )
    context = ordered[0]
    if not eligible:
        analysis = _unresolved(
            context=context,
            window=(),
            as_of_ms=as_of_ms,
            flags=("exchange_flow_unavailable_at_as_of",),
        )
        return _freeze(analysis, ())

    window = eligible[-config.lookback_observations :]
    latest = window[-1]
    age_ms = as_of_ms - latest.window_end_ms
    flags: list[str] = []
    if age_ms > config.max_observation_age_ms:
        flags.append("stale_exchange_flow_observation")
    if len(window) < config.minimum_observations:
        flags.append("insufficient_exchange_flow_history")
    if flags:
        analysis = _unresolved(
            context=context,
            window=window,
            as_of_ms=as_of_ms,
            flags=tuple(flags),
        )
        return _freeze(analysis, window)

    metrics = _metrics(window)
    label, direction, classification_flags = _classify(metrics, config)
    all_flags = (
        "exchange_flow_is_provider_attribution_not_actor_intent",
        "exchange_flow_context_is_not_price_direction",
        *classification_flags,
    )
    payload = _payload(
        context=context,
        window=window,
        as_of_ms=as_of_ms,
        status=ExchangeFlowStatus.MEASURED,
        label=label,
        direction=direction,
        metrics=metrics,
        flags=all_flags,
    )
    analysis = ExchangeFlowAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=EXCHANGE_FLOW_ENGINE_VERSION,
        asset=context.asset,
        exchange_scope=context.exchange_scope,
        source_provider=context.source_provider,
        attribution_method=context.attribution_method,
        as_of_ms=as_of_ms,
        source_window_start_ms=window[0].window_start_ms,
        source_window_end_ms=latest.window_end_ms,
        observed_at_ms=max(item.ingested_at_ms for item in window),
        consumed_observation_count=len(window),
        latest_observation_age_ms=age_ms,
        status=ExchangeFlowStatus.MEASURED,
        label=label,
        netflow_direction=direction,
        metrics=metrics,
        uncertainty_flags=all_flags,
    )
    return _freeze(analysis, window)


def _metrics(
    observations: tuple[ExchangeFlowObservation, ...],
) -> ExchangeFlowMetrics:
    inflow_rates = tuple(_rate_per_hour(item.inflow_amount, item) for item in observations)
    outflow_rates = tuple(
        _rate_per_hour(item.outflow_amount, item) for item in observations
    )
    netflow_rates = tuple(
        inflow - outflow for inflow, outflow in zip(inflow_rates, outflow_rates, strict=True)
    )
    latest = observations[-1]
    latest_inflow_rate = inflow_rates[-1]
    latest_outflow_rate = outflow_rates[-1]
    latest_netflow_rate = netflow_rates[-1]

    previous = observations[-2]
    elapsed_hours = (
        Decimal(latest.window_end_ms - previous.window_end_ms) / _HOUR_MS
    )
    velocity = (latest_netflow_rate - netflow_rates[-2]) / elapsed_hours
    abs_netflows = tuple(abs(value) for value in netflow_rates)

    return ExchangeFlowMetrics(
        latest_inflow_amount=latest.inflow_amount,
        latest_outflow_amount=latest.outflow_amount,
        latest_netflow_amount=latest.netflow_amount,
        latest_gross_flow_amount=latest.gross_flow_amount,
        latest_inflow_rate_per_hour=latest_inflow_rate,
        latest_outflow_rate_per_hour=latest_outflow_rate,
        latest_netflow_rate_per_hour=latest_netflow_rate,
        inflow_rate_percentile_0_1=_percentile_rank(inflow_rates, latest_inflow_rate),
        outflow_rate_percentile_0_1=_percentile_rank(outflow_rates, latest_outflow_rate),
        abs_netflow_rate_percentile_0_1=_percentile_rank(
            abs_netflows,
            abs(latest_netflow_rate),
        ),
        netflow_rate_velocity_per_hour=velocity,
        observation_count=len(observations),
    )


def _classify(
    metrics: ExchangeFlowMetrics,
    config: ExchangeFlowConfig,
) -> tuple[ExchangeFlowLabel, NetflowDirection, tuple[str, ...]]:
    if metrics.latest_netflow_amount > 0:
        direction = NetflowDirection.TO_EXCHANGES
    elif metrics.latest_netflow_amount < 0:
        direction = NetflowDirection.FROM_EXCHANGES
    else:
        direction = NetflowDirection.BALANCED

    inflow_extreme = (
        metrics.inflow_rate_percentile_0_1 >= config.anomaly_percentile
    )
    outflow_extreme = (
        metrics.outflow_rate_percentile_0_1 >= config.anomaly_percentile
    )
    if inflow_extreme and outflow_extreme:
        return (
            ExchangeFlowLabel.MIXED,
            direction,
            ("simultaneous_inflow_outflow_extremes",),
        )
    if inflow_extreme and direction is NetflowDirection.TO_EXCHANGES:
        return ExchangeFlowLabel.INFLOW_ANOMALY, direction, ()
    if outflow_extreme and direction is NetflowDirection.FROM_EXCHANGES:
        return ExchangeFlowLabel.OUTFLOW_ANOMALY, direction, ()

    gross = metrics.latest_gross_flow_amount
    if gross == 0:
        return ExchangeFlowLabel.BALANCED, direction, ("zero_gross_flow_window",)
    if (
        abs(metrics.latest_netflow_amount) / gross
        <= config.balanced_netflow_fraction_of_gross
        and not inflow_extreme
        and not outflow_extreme
    ):
        return ExchangeFlowLabel.BALANCED, direction, ()
    return (
        ExchangeFlowLabel.MIXED,
        direction,
        ("exchange_flow_components_not_aligned_for_anomaly",),
    )


def _rate_per_hour(amount: Decimal, observation: ExchangeFlowObservation) -> Decimal:
    hours = Decimal(observation.window_duration_ms) / _HOUR_MS
    return amount / hours


def _percentile_rank(values: tuple[Decimal, ...], latest: Decimal) -> Decimal:
    return Decimal(sum(value <= latest for value in values)) / Decimal(len(values))


def _validate_context(observations: tuple[ExchangeFlowObservation, ...]) -> None:
    first = observations[0]
    context = (
        first.asset,
        first.exchange_scope,
        first.source_provider,
        first.attribution_method,
    )
    if any(
        (
            item.asset,
            item.exchange_scope,
            item.source_provider,
            item.attribution_method,
        )
        != context
        for item in observations
    ):
        raise ValueError("exchange-flow observations require exact source context")


def _reject_duplicates(observations: tuple[ExchangeFlowObservation, ...]) -> None:
    identities = tuple(item.observation_identity for item in observations)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate exchange-flow observation identity")
    window_ends = tuple(item.window_end_ms for item in observations)
    if len(window_ends) != len(set(window_ends)):
        raise ValueError("exchange-flow observations require unique window ends")


def _unresolved(
    *,
    context: ExchangeFlowObservation,
    window: tuple[ExchangeFlowObservation, ...],
    as_of_ms: int,
    flags: tuple[str, ...],
) -> ExchangeFlowAnalysis:
    if window:
        latest = window[-1]
        start: int | None = window[0].window_start_ms
        end: int | None = latest.window_end_ms
        observed: int | None = max(item.ingested_at_ms for item in window)
        age: int | None = as_of_ms - latest.window_end_ms
    else:
        start = end = observed = age = None
    payload = {
        "asset": context.asset,
        "as_of_ms": as_of_ms,
        "attribution_method": context.attribution_method,
        "consumed_observation_count": len(window),
        "engine_version": EXCHANGE_FLOW_ENGINE_VERSION,
        "exchange_scope": context.exchange_scope,
        "label": ExchangeFlowLabel.UNRESOLVED,
        "latest_observation_age_ms": age,
        "metrics": None,
        "netflow_direction": NetflowDirection.UNAVAILABLE,
        "observed_at_ms": observed,
        "source_provider": context.source_provider,
        "source_window_end_ms": end,
        "source_window_start_ms": start,
        "status": ExchangeFlowStatus.UNRESOLVED,
        "uncertainty_flags": flags,
    }
    return ExchangeFlowAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=EXCHANGE_FLOW_ENGINE_VERSION,
        asset=context.asset,
        exchange_scope=context.exchange_scope,
        source_provider=context.source_provider,
        attribution_method=context.attribution_method,
        as_of_ms=as_of_ms,
        source_window_start_ms=start,
        source_window_end_ms=end,
        observed_at_ms=observed,
        consumed_observation_count=len(window),
        latest_observation_age_ms=age,
        status=ExchangeFlowStatus.UNRESOLVED,
        label=ExchangeFlowLabel.UNRESOLVED,
        netflow_direction=NetflowDirection.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _payload(
    *,
    context: ExchangeFlowObservation,
    window: tuple[ExchangeFlowObservation, ...],
    as_of_ms: int,
    status: ExchangeFlowStatus,
    label: ExchangeFlowLabel,
    direction: NetflowDirection,
    metrics: ExchangeFlowMetrics | None,
    flags: tuple[str, ...],
) -> dict[str, object]:
    latest = window[-1]
    return {
        "asset": context.asset,
        "as_of_ms": as_of_ms,
        "attribution_method": context.attribution_method,
        "consumed_observation_count": len(window),
        "engine_version": EXCHANGE_FLOW_ENGINE_VERSION,
        "exchange_scope": context.exchange_scope,
        "label": label,
        "latest_observation_age_ms": as_of_ms - latest.window_end_ms,
        "metrics": metrics,
        "netflow_direction": direction,
        "observed_at_ms": max(item.ingested_at_ms for item in window),
        "source_provider": context.source_provider,
        "source_window_end_ms": latest.window_end_ms,
        "source_window_start_ms": window[0].window_start_ms,
        "status": status,
        "uncertainty_flags": flags,
    }


def _analysis_payload(analysis: ExchangeFlowAnalysis) -> dict[str, object]:
    return {
        "asset": analysis.asset,
        "as_of_ms": analysis.as_of_ms,
        "attribution_method": analysis.attribution_method,
        "consumed_observation_count": analysis.consumed_observation_count,
        "engine_version": analysis.engine_version,
        "exchange_scope": analysis.exchange_scope,
        "label": analysis.label,
        "latest_observation_age_ms": analysis.latest_observation_age_ms,
        "metrics": analysis.metrics,
        "netflow_direction": analysis.netflow_direction,
        "observed_at_ms": analysis.observed_at_ms,
        "source_provider": analysis.source_provider,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze(
    analysis: ExchangeFlowAnalysis,
    observations: tuple[ExchangeFlowObservation, ...],
) -> ExchangeFlowEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "observation_identities": [item.observation_identity for item in observations],
        "schema_version": EXCHANGE_FLOW_FREEZE_SCHEMA_VERSION,
    }
    return ExchangeFlowEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=EXCHANGE_FLOW_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observations=observations,
    )


def _freeze_payload(freeze: ExchangeFlowEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "observation_identities": [
            item.observation_identity for item in freeze.observations
        ],
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
