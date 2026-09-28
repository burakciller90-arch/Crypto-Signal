from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

ONCHAIN_EVENT_COVERAGE_SCHEMA_VERSION = "onchain-event-coverage-v1/1"
STABLECOIN_SUPPLY_OBSERVATION_SCHEMA_VERSION = (
    "stablecoin-supply-observation-v1/1"
)
STABLECOIN_SUPPLY_TEMPORAL_SEMANTIC = (
    "provider_stablecoin_circulating_supply_snapshot"
)
REAL_CAPITAL = 0


class OnchainEventCoverageState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    GAP = "gap"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OnchainEventCoverage:
    coverage_identity: str
    provider: str
    source: str
    channel: str
    asset: str
    network: str
    event_kind: str
    coverage_start_ms: int
    coverage_end_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    state: OnchainEventCoverageState
    source_envelope_identity: str | None
    raw_identity: str | None
    reason_codes: tuple[str, ...]
    schema_version: str = ONCHAIN_EVENT_COVERAGE_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.coverage_identity, "on-chain coverage identity")
        if self.schema_version != ONCHAIN_EVENT_COVERAGE_SCHEMA_VERSION:
            raise ValueError("unsupported on-chain event coverage schema")
        for value, label in (
            (self.provider, "provider"),
            (self.source, "source"),
            (self.channel, "channel"),
            (self.network, "network"),
            (self.event_kind, "event_kind"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("on-chain coverage asset must be uppercase")
        if min(
            self.coverage_start_ms,
            self.coverage_end_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("on-chain coverage timestamps must be non-negative")
        if self.coverage_end_ms <= self.coverage_start_ms:
            raise ValueError("on-chain coverage end must follow start")
        if self.observed_at_ms < self.coverage_end_ms:
            raise ValueError(
                "on-chain coverage cannot be observed before interval end"
            )
        if self.ingested_at_ms < self.observed_at_ms:
            raise ValueError(
                "on-chain coverage ingestion cannot predate observation"
            )
        if not self.reason_codes:
            raise ValueError("on-chain coverage requires reason codes")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError(
                "on-chain coverage reason codes must be unique and sorted"
            )
        if self.state in {
            OnchainEventCoverageState.COMPLETE,
            OnchainEventCoverageState.PARTIAL,
        }:
            if (
                self.source_envelope_identity is None
                or self.raw_identity is None
            ):
                raise ValueError(
                    "observed on-chain coverage requires exact source lineage"
                )
            _require_sha256(
                self.source_envelope_identity,
                "on-chain coverage source envelope identity",
            )
            _require_sha256(
                self.raw_identity,
                "on-chain coverage raw identity",
            )
        elif (
            self.source_envelope_identity is not None
            or self.raw_identity is not None
        ):
            raise ValueError(
                "gap/unavailable on-chain coverage cannot substitute source data"
            )
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("on-chain coverage cannot grant authority")
        if self.coverage_identity != canonical_sha256(
            onchain_event_coverage_payload(self)
        ):
            raise ValueError("on-chain event coverage identity mismatch")

    @property
    def can_assert_zero_events(self) -> bool:
        return self.state is OnchainEventCoverageState.COMPLETE


@dataclass(frozen=True, slots=True)
class StablecoinSupplyObservation:
    observation_identity: str
    asset: str
    network_scope: str
    provider: str
    provider_metric_identity: str
    circulating_amount: Decimal
    usd_amount: Decimal | None
    source: DataSource
    source_timestamp_ms: int
    observed_at_ms: int
    ingested_at_ms: int
    adapter_version: str
    raw_identity: str
    source_envelope_identity: str
    temporal_semantic: str = STABLECOIN_SUPPLY_TEMPORAL_SEMANTIC
    schema_version: str = STABLECOIN_SUPPLY_OBSERVATION_SCHEMA_VERSION
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(
            self.observation_identity,
            "stablecoin supply observation identity",
        )
        if self.schema_version != STABLECOIN_SUPPLY_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("unsupported stablecoin supply schema")
        if self.temporal_semantic != STABLECOIN_SUPPLY_TEMPORAL_SEMANTIC:
            raise ValueError("unsupported stablecoin supply temporal semantic")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("stablecoin asset must be non-empty uppercase")
        for value, label in (
            (self.network_scope, "network_scope"),
            (self.provider, "provider"),
            (self.provider_metric_identity, "provider_metric_identity"),
            (self.adapter_version, "adapter_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        _require_sha256(self.raw_identity, "stablecoin supply raw identity")
        _require_sha256(
            self.source_envelope_identity,
            "stablecoin supply source envelope identity",
        )
        if min(
            self.source_timestamp_ms,
            self.observed_at_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("stablecoin supply timestamps must be non-negative")
        if self.observed_at_ms < self.source_timestamp_ms:
            raise ValueError(
                "stablecoin supply observation cannot predate source timestamp"
            )
        if self.ingested_at_ms < self.observed_at_ms:
            raise ValueError(
                "stablecoin supply ingestion cannot predate observation"
            )
        _require_non_negative_decimal(
            self.circulating_amount,
            "circulating_amount",
        )
        if self.usd_amount is not None:
            _require_non_negative_decimal(self.usd_amount, "usd_amount")
        if self.production_authority or self.real_capital != REAL_CAPITAL:
            raise ValueError("stablecoin supply cannot grant authority")
        if self.observation_identity != canonical_sha256(
            stablecoin_supply_observation_payload(self)
        ):
            raise ValueError("stablecoin supply observation identity mismatch")


def build_onchain_event_coverage(
    *,
    provider: str,
    source: str,
    channel: str,
    asset: str,
    network: str,
    event_kind: str,
    coverage_start_ms: int,
    coverage_end_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    state: OnchainEventCoverageState,
    source_envelope_identity: str | None,
    raw_identity: str | None,
    reason_codes: tuple[str, ...],
) -> OnchainEventCoverage:
    canonical_reasons = tuple(sorted(set(reason_codes)))
    values = {
        "asset": asset,
        "channel": channel,
        "coverage_end_ms": coverage_end_ms,
        "coverage_start_ms": coverage_start_ms,
        "event_kind": event_kind,
        "ingested_at_ms": ingested_at_ms,
        "network": network,
        "observed_at_ms": observed_at_ms,
        "production_authority": False,
        "provider": provider,
        "raw_identity": raw_identity,
        "real_capital": REAL_CAPITAL,
        "reason_codes": canonical_reasons,
        "schema_version": ONCHAIN_EVENT_COVERAGE_SCHEMA_VERSION,
        "source": source,
        "source_envelope_identity": source_envelope_identity,
        "state": state,
    }
    return OnchainEventCoverage(
        coverage_identity=canonical_sha256(values),
        provider=provider,
        source=source,
        channel=channel,
        asset=asset,
        network=network,
        event_kind=event_kind,
        coverage_start_ms=coverage_start_ms,
        coverage_end_ms=coverage_end_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        state=state,
        source_envelope_identity=source_envelope_identity,
        raw_identity=raw_identity,
        reason_codes=canonical_reasons,
    )


def build_stablecoin_supply_observation(
    *,
    asset: str,
    network_scope: str,
    provider: str,
    provider_metric_identity: str,
    circulating_amount: Decimal,
    usd_amount: Decimal | None,
    source: DataSource,
    source_timestamp_ms: int,
    observed_at_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
    raw_identity: str,
    source_envelope_identity: str,
) -> StablecoinSupplyObservation:
    values = {
        "adapter_version": adapter_version,
        "asset": asset,
        "circulating_amount": circulating_amount,
        "ingested_at_ms": ingested_at_ms,
        "network_scope": network_scope,
        "observed_at_ms": observed_at_ms,
        "production_authority": False,
        "provider": provider,
        "provider_metric_identity": provider_metric_identity,
        "raw_identity": raw_identity,
        "real_capital": REAL_CAPITAL,
        "schema_version": STABLECOIN_SUPPLY_OBSERVATION_SCHEMA_VERSION,
        "source": source,
        "source_envelope_identity": source_envelope_identity,
        "source_timestamp_ms": source_timestamp_ms,
        "temporal_semantic": STABLECOIN_SUPPLY_TEMPORAL_SEMANTIC,
        "usd_amount": usd_amount,
    }
    return StablecoinSupplyObservation(
        observation_identity=canonical_sha256(values),
        asset=asset,
        network_scope=network_scope,
        provider=provider,
        provider_metric_identity=provider_metric_identity,
        circulating_amount=circulating_amount,
        usd_amount=usd_amount,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        observed_at_ms=observed_at_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
        raw_identity=raw_identity,
        source_envelope_identity=source_envelope_identity,
    )


def onchain_event_coverage_payload(
    coverage: OnchainEventCoverage,
) -> dict[str, object]:
    return {
        "asset": coverage.asset,
        "channel": coverage.channel,
        "coverage_end_ms": coverage.coverage_end_ms,
        "coverage_start_ms": coverage.coverage_start_ms,
        "event_kind": coverage.event_kind,
        "ingested_at_ms": coverage.ingested_at_ms,
        "network": coverage.network,
        "observed_at_ms": coverage.observed_at_ms,
        "production_authority": coverage.production_authority,
        "provider": coverage.provider,
        "raw_identity": coverage.raw_identity,
        "real_capital": coverage.real_capital,
        "reason_codes": coverage.reason_codes,
        "schema_version": coverage.schema_version,
        "source": coverage.source,
        "source_envelope_identity": coverage.source_envelope_identity,
        "state": coverage.state,
    }


def stablecoin_supply_observation_payload(
    observation: StablecoinSupplyObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "asset": observation.asset,
        "circulating_amount": observation.circulating_amount,
        "ingested_at_ms": observation.ingested_at_ms,
        "network_scope": observation.network_scope,
        "observed_at_ms": observation.observed_at_ms,
        "production_authority": observation.production_authority,
        "provider": observation.provider,
        "provider_metric_identity": observation.provider_metric_identity,
        "raw_identity": observation.raw_identity,
        "real_capital": observation.real_capital,
        "schema_version": observation.schema_version,
        "source": observation.source,
        "source_envelope_identity": observation.source_envelope_identity,
        "source_timestamp_ms": observation.source_timestamp_ms,
        "temporal_semantic": observation.temporal_semantic,
        "usd_amount": observation.usd_amount,
    }


def _require_non_negative_decimal(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or value < Decimal(0):
        raise ValueError(f"{label} must be finite and non-negative")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be SHA256")
