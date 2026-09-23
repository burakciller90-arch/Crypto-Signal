from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.large_transfers import (
    LargeTransferObservation,
    TransferClusterRole,
)
from crypto_signal.ledger.serialization import canonical_sha256

LARGE_TRANSFER_CLUSTER_ENGINE_VERSION = "large-transfer-clusters-v2-slice3/1"
LARGE_TRANSFER_CLUSTER_FREEZE_SCHEMA_VERSION = "large-transfer-clusters-freeze-v1/1"


class LargeTransferStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class LargeTransferLabel(StrEnum):
    REPEATED_RELATIONSHIP_CLUSTER = "repeated_relationship_cluster"
    ISOLATED_LARGE_TRANSFER = "isolated_large_transfer"
    NORMAL = "normal"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class LargeTransferClusterConfig:
    lookback_ms: int = 60 * 60_000
    minimum_events: int = 3
    large_amount_percentile: Decimal = Decimal("0.80")
    relationship_min_events: int = 2
    relationship_min_amount_share: Decimal = Decimal("0.25")

    def __post_init__(self) -> None:
        if self.lookback_ms <= 0 or self.minimum_events < 2 or self.relationship_min_events < 2:
            raise ValueError("large-transfer count/window configuration invalid")
        for value, label in (
            (self.large_amount_percentile, "large_amount_percentile"),
            (self.relationship_min_amount_share, "relationship_min_amount_share"),
        ):
            if value.is_nan() or value.is_infinite() or not Decimal(0) < value <= Decimal(1):
                raise ValueError(f"{label} must be inside (0,1]")


DEFAULT_LARGE_TRANSFER_CLUSTER_CONFIG = LargeTransferClusterConfig()


@dataclass(frozen=True, slots=True)
class RepeatedTransferRelationship:
    source_cluster_id: str
    destination_cluster_id: str
    source_role: TransferClusterRole
    destination_role: TransferClusterRole
    event_count: int
    total_amount: Decimal
    amount_share: Decimal
    mean_size_percentile_0_1: Decimal
    first_event_at_ms: int
    last_event_at_ms: int

    def __post_init__(self) -> None:
        if self.event_count < 2:
            raise ValueError("repeated transfer relationship requires at least two events")
        if self.total_amount <= Decimal(0):
            raise ValueError("repeated transfer relationship amount must be positive")
        for value in (self.amount_share, self.mean_size_percentile_0_1):
            if value.is_nan() or value.is_infinite() or not Decimal(0) < value <= Decimal(1):
                raise ValueError("repeated transfer normalized values must be inside (0,1]")
        if self.first_event_at_ms > self.last_event_at_ms:
            raise ValueError("repeated transfer relationship time order invalid")


@dataclass(frozen=True, slots=True)
class LargeTransferClusterMetrics:
    event_count: int
    large_event_count: int
    exchange_attributed_event_count: int
    total_amount: Decimal
    median_amount: Decimal
    latest_amount_percentile_0_1: Decimal
    repeated_relationship_count: int

    def __post_init__(self) -> None:
        if self.event_count <= 0:
            raise ValueError("large-transfer metrics require events")
        if not 0 <= self.large_event_count <= self.event_count:
            raise ValueError("large-transfer large event count invalid")
        if not 0 <= self.exchange_attributed_event_count <= self.event_count:
            raise ValueError("large-transfer exchange-attributed count invalid")
        if self.total_amount <= Decimal(0) or self.median_amount <= Decimal(0):
            raise ValueError("large-transfer amount metrics must be positive")
        if (
            self.latest_amount_percentile_0_1.is_nan()
            or self.latest_amount_percentile_0_1.is_infinite()
            or not Decimal(0) < self.latest_amount_percentile_0_1 <= Decimal(1)
        ):
            raise ValueError("large-transfer latest percentile outside (0,1]")
        if self.repeated_relationship_count < 0:
            raise ValueError("large-transfer repeated relationship count cannot be negative")


@dataclass(frozen=True, slots=True)
class LargeTransferClusterAnalysis:
    evidence_identity: str
    engine_version: str
    asset: str
    network: str
    source_provider: str
    attribution_method: str
    as_of_ms: int
    source_window_start_ms: int
    source_window_end_ms: int | None
    observed_at_ms: int | None
    status: LargeTransferStatus
    label: LargeTransferLabel
    metrics: LargeTransferClusterMetrics | None
    relationships: tuple[RepeatedTransferRelationship, ...]
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "large-transfer cluster evidence identity")
        if self.engine_version != LARGE_TRANSFER_CLUSTER_ENGINE_VERSION:
            raise ValueError("unsupported large-transfer cluster engine version")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("large-transfer analysis asset must be uppercase")
        for value, label in (
            (self.network, "network"),
            (self.source_provider, "source_provider"),
            (self.attribution_method, "attribution_method"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not 0 <= self.source_window_start_ms <= self.as_of_ms:
            raise ValueError("large-transfer analysis start outside PIT cutoff")
        if self.status is LargeTransferStatus.UNRESOLVED:
            if self.label is not LargeTransferLabel.UNRESOLVED:
                raise ValueError("unresolved large-transfer analysis requires unresolved label")
            if self.metrics is not None or self.relationships:
                raise ValueError("unresolved large-transfer analysis cannot expose measured evidence")
            if not self.uncertainty_flags:
                raise ValueError("unresolved large-transfer analysis requires uncertainty")
        else:
            if self.metrics is None or self.source_window_end_ms is None or self.observed_at_ms is None:
                raise ValueError("measured large-transfer analysis requires metrics and timestamps")
            if not self.source_window_start_ms <= self.source_window_end_ms <= self.as_of_ms:
                raise ValueError("large-transfer analysis end outside PIT cutoff")
            if not 0 <= self.observed_at_ms <= self.as_of_ms:
                raise ValueError("large-transfer observed_at outside PIT cutoff")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("large-transfer cluster evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class LargeTransferClusterEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: LargeTransferClusterAnalysis
    observations: tuple[LargeTransferObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "large-transfer cluster freeze identity")
        if self.schema_version != LARGE_TRANSFER_CLUSTER_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported large-transfer cluster freeze schema")
        if any(
            max(item.event_at_ms, item.source_timestamp_ms, item.ingested_at_ms)
            > self.analysis.as_of_ms
            for item in self.observations
        ):
            raise ValueError("large-transfer freeze contains future evidence")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("large-transfer cluster freeze identity mismatch")


def analyze_large_transfer_clusters(
    observations: Sequence[LargeTransferObservation],
    *,
    as_of_ms: int,
    config: LargeTransferClusterConfig = DEFAULT_LARGE_TRANSFER_CLUSTER_CONFIG,
) -> LargeTransferClusterAnalysis:
    return build_large_transfer_cluster_evidence_freeze(
        observations,
        as_of_ms=as_of_ms,
        config=config,
    ).analysis


def build_large_transfer_cluster_evidence_freeze(
    observations: Sequence[LargeTransferObservation],
    *,
    as_of_ms: int,
    config: LargeTransferClusterConfig = DEFAULT_LARGE_TRANSFER_CLUSTER_CONFIG,
) -> LargeTransferClusterEvidenceFreeze:
    if not observations:
        raise ValueError("large-transfer clustering requires observations")
    if as_of_ms < 0:
        raise ValueError("large-transfer as_of_ms must be non-negative")
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.event_at_ms,
                item.source_timestamp_ms,
                item.transfer_identity,
            ),
        )
    )
    window_start = max(0, as_of_ms - config.lookback_ms)
    eligible = tuple(
        item
        for item in ordered
        if item.event_at_ms >= window_start
        and max(item.event_at_ms, item.source_timestamp_ms, item.ingested_at_ms) <= as_of_ms
    )
    context = eligible[0] if eligible else ordered[0]
    if eligible:
        _validate_context(eligible)
        _reject_duplicates(eligible)
    if len(eligible) < config.minimum_events:
        analysis = _unresolved(
            context=context,
            as_of_ms=as_of_ms,
            window_start=window_start,
            flags=("insufficient_large_transfer_history",),
        )
        return _freeze(analysis, eligible)

    percentiles = {
        item.transfer_identity: _percentile_rank(
            tuple(row.amount for row in eligible),
            item.amount,
        )
        for item in eligible
    }
    large = tuple(
        item
        for item in eligible
        if percentiles[item.transfer_identity] >= config.large_amount_percentile
    )
    relationships = _relationships(
        eligible,
        percentiles=percentiles,
        config=config,
    )
    amounts = tuple(sorted(item.amount for item in eligible))
    midpoint = len(amounts) // 2
    median = (
        amounts[midpoint]
        if len(amounts) % 2
        else (amounts[midpoint - 1] + amounts[midpoint]) / Decimal(2)
    )
    total = sum(amounts, start=Decimal(0))
    latest = eligible[-1]
    metrics = LargeTransferClusterMetrics(
        event_count=len(eligible),
        large_event_count=len(large),
        exchange_attributed_event_count=sum(
            item.source_role is TransferClusterRole.EXCHANGE
            or item.destination_role is TransferClusterRole.EXCHANGE
            for item in eligible
        ),
        total_amount=total,
        median_amount=median,
        latest_amount_percentile_0_1=percentiles[latest.transfer_identity],
        repeated_relationship_count=len(relationships),
    )
    if relationships:
        label = LargeTransferLabel.REPEATED_RELATIONSHIP_CLUSTER
    elif large:
        label = LargeTransferLabel.ISOLATED_LARGE_TRANSFER
    else:
        label = LargeTransferLabel.NORMAL
    flags = (
        "provider_cluster_attribution_is_not_actor_identity",
        "large_transfer_context_is_not_price_direction",
    )
    payload = _payload(
        context=context,
        as_of_ms=as_of_ms,
        window_start=window_start,
        window_end=latest.event_at_ms,
        observed_at=max(item.ingested_at_ms for item in eligible),
        status=LargeTransferStatus.MEASURED,
        label=label,
        metrics=metrics,
        relationships=relationships,
        flags=flags,
    )
    analysis = LargeTransferClusterAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LARGE_TRANSFER_CLUSTER_ENGINE_VERSION,
        asset=context.asset,
        network=context.network,
        source_provider=context.source_provider,
        attribution_method=context.attribution_method,
        as_of_ms=as_of_ms,
        source_window_start_ms=window_start,
        source_window_end_ms=latest.event_at_ms,
        observed_at_ms=max(item.ingested_at_ms for item in eligible),
        status=LargeTransferStatus.MEASURED,
        label=label,
        metrics=metrics,
        relationships=relationships,
        uncertainty_flags=flags,
    )
    return _freeze(analysis, eligible)


def _relationships(
    observations: tuple[LargeTransferObservation, ...],
    *,
    percentiles: dict[str, Decimal],
    config: LargeTransferClusterConfig,
) -> tuple[RepeatedTransferRelationship, ...]:
    total_amount = sum((item.amount for item in observations), start=Decimal(0))
    groups: dict[tuple[str, str, TransferClusterRole, TransferClusterRole], list[LargeTransferObservation]] = defaultdict(list)
    for item in observations:
        groups[
            (
                item.source_cluster_id,
                item.destination_cluster_id,
                item.source_role,
                item.destination_role,
            )
        ].append(item)

    result: list[RepeatedTransferRelationship] = []
    for key, rows in groups.items():
        if len(rows) < config.relationship_min_events:
            continue
        amount = sum((item.amount for item in rows), start=Decimal(0))
        share = amount / total_amount
        if share < config.relationship_min_amount_share:
            continue
        source_id, destination_id, source_role, destination_role = key
        result.append(
            RepeatedTransferRelationship(
                source_cluster_id=source_id,
                destination_cluster_id=destination_id,
                source_role=source_role,
                destination_role=destination_role,
                event_count=len(rows),
                total_amount=amount,
                amount_share=share,
                mean_size_percentile_0_1=(
                    sum(
                        (percentiles[item.transfer_identity] for item in rows),
                        start=Decimal(0),
                    )
                    / Decimal(len(rows))
                ),
                first_event_at_ms=rows[0].event_at_ms,
                last_event_at_ms=rows[-1].event_at_ms,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.source_cluster_id,
                item.destination_cluster_id,
                item.first_event_at_ms,
            ),
        )
    )


def _percentile_rank(values: tuple[Decimal, ...], value: Decimal) -> Decimal:
    return Decimal(sum(item <= value for item in values)) / Decimal(len(values))


def _validate_context(observations: tuple[LargeTransferObservation, ...]) -> None:
    first = observations[0]
    context = (
        first.asset,
        first.network,
        first.source_provider,
        first.attribution_method,
    )
    if any(
        (
            item.asset,
            item.network,
            item.source_provider,
            item.attribution_method,
        )
        != context
        for item in observations
    ):
        raise ValueError("large-transfer observations require exact source context")


def _reject_duplicates(observations: tuple[LargeTransferObservation, ...]) -> None:
    identities = tuple(item.transfer_identity for item in observations)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate large-transfer identity")
    provider_ids = tuple(item.provider_transfer_id for item in observations)
    if len(provider_ids) != len(set(provider_ids)):
        raise ValueError("duplicate provider transfer id")


def _unresolved(
    *,
    context: LargeTransferObservation,
    as_of_ms: int,
    window_start: int,
    flags: tuple[str, ...],
) -> LargeTransferClusterAnalysis:
    payload = _payload(
        context=context,
        as_of_ms=as_of_ms,
        window_start=window_start,
        window_end=None,
        observed_at=None,
        status=LargeTransferStatus.UNRESOLVED,
        label=LargeTransferLabel.UNRESOLVED,
        metrics=None,
        relationships=(),
        flags=flags,
    )
    return LargeTransferClusterAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=LARGE_TRANSFER_CLUSTER_ENGINE_VERSION,
        asset=context.asset,
        network=context.network,
        source_provider=context.source_provider,
        attribution_method=context.attribution_method,
        as_of_ms=as_of_ms,
        source_window_start_ms=window_start,
        source_window_end_ms=None,
        observed_at_ms=None,
        status=LargeTransferStatus.UNRESOLVED,
        label=LargeTransferLabel.UNRESOLVED,
        metrics=None,
        relationships=(),
        uncertainty_flags=flags,
    )


def _payload(
    *,
    context: LargeTransferObservation,
    as_of_ms: int,
    window_start: int,
    window_end: int | None,
    observed_at: int | None,
    status: LargeTransferStatus,
    label: LargeTransferLabel,
    metrics: LargeTransferClusterMetrics | None,
    relationships: tuple[RepeatedTransferRelationship, ...],
    flags: tuple[str, ...],
) -> dict[str, object]:
    return {
        "asset": context.asset,
        "as_of_ms": as_of_ms,
        "attribution_method": context.attribution_method,
        "engine_version": LARGE_TRANSFER_CLUSTER_ENGINE_VERSION,
        "label": label,
        "metrics": metrics,
        "network": context.network,
        "observed_at_ms": observed_at,
        "relationships": relationships,
        "source_provider": context.source_provider,
        "source_window_end_ms": window_end,
        "source_window_start_ms": window_start,
        "status": status,
        "uncertainty_flags": flags,
    }


def _analysis_payload(analysis: LargeTransferClusterAnalysis) -> dict[str, object]:
    return {
        "asset": analysis.asset,
        "as_of_ms": analysis.as_of_ms,
        "attribution_method": analysis.attribution_method,
        "engine_version": analysis.engine_version,
        "label": analysis.label,
        "metrics": analysis.metrics,
        "network": analysis.network,
        "observed_at_ms": analysis.observed_at_ms,
        "relationships": analysis.relationships,
        "source_provider": analysis.source_provider,
        "source_window_end_ms": analysis.source_window_end_ms,
        "source_window_start_ms": analysis.source_window_start_ms,
        "status": analysis.status,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze(
    analysis: LargeTransferClusterAnalysis,
    observations: tuple[LargeTransferObservation, ...],
) -> LargeTransferClusterEvidenceFreeze:
    payload = {
        "analysis_identity": analysis.evidence_identity,
        "observation_identities": [item.transfer_identity for item in observations],
        "schema_version": LARGE_TRANSFER_CLUSTER_FREEZE_SCHEMA_VERSION,
    }
    return LargeTransferClusterEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=LARGE_TRANSFER_CLUSTER_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        observations=observations,
    )


def _freeze_payload(freeze: LargeTransferClusterEvidenceFreeze) -> dict[str, object]:
    return {
        "analysis_identity": freeze.analysis.evidence_identity,
        "observation_identities": [
            item.transfer_identity for item in freeze.observations
        ],
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
