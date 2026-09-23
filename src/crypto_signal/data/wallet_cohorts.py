from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.data.models import DataSource
from crypto_signal.ledger.serialization import canonical_sha256

WALLET_COHORT_ADMISSION_SCHEMA_VERSION = "wallet-cohort-admission-v1/1"
WALLET_COHORT_FORWARD_SCHEMA_VERSION = "wallet-cohort-forward-v1/1"


@dataclass(frozen=True, slots=True)
class WalletCohortAdmission:
    admission_identity: str
    schema_version: str
    cohort_id: str
    cluster_id: str
    asset: str
    network: str
    admitted_at_ms: int
    basis_available_at_ms: int
    source_provider: str
    attribution_method: str
    admission_rule_version: str
    basis_evidence_identities: tuple[str, ...]
    source: DataSource

    def __post_init__(self) -> None:
        _require_sha256(self.admission_identity, "wallet cohort admission identity")
        if self.schema_version != WALLET_COHORT_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported wallet cohort admission schema")
        for value, label in (
            (self.cohort_id, "cohort_id"),
            (self.cluster_id, "cluster_id"),
            (self.network, "network"),
            (self.source_provider, "source_provider"),
            (self.attribution_method, "attribution_method"),
            (self.admission_rule_version, "admission_rule_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("wallet cohort asset must be non-empty uppercase")
        if min(self.admitted_at_ms, self.basis_available_at_ms) < 0:
            raise ValueError("wallet cohort timestamps must be non-negative")
        if self.basis_available_at_ms > self.admitted_at_ms:
            raise ValueError("wallet cohort admission cannot predate basis evidence")
        if not self.basis_evidence_identities:
            raise ValueError("wallet cohort admission requires basis evidence")
        if tuple(sorted(set(self.basis_evidence_identities))) != self.basis_evidence_identities:
            raise ValueError("wallet cohort basis evidence identities must be unique and sorted")
        for identity in self.basis_evidence_identities:
            _require_sha256(identity, "wallet cohort basis evidence identity")
        if self.admission_identity != canonical_sha256(wallet_cohort_admission_payload(self)):
            raise ValueError("wallet cohort admission identity mismatch")


@dataclass(frozen=True, slots=True)
class WalletCohortForwardObservation:
    observation_identity: str
    schema_version: str
    admission_identity: str
    cohort_id: str
    cluster_id: str
    asset: str
    network: str
    measurement_start_ms: int
    measurement_end_ms: int
    metric_name: str
    metric_value: Decimal
    source_provider: str
    source: DataSource
    source_timestamp_ms: int
    ingested_at_ms: int
    adapter_version: str

    def __post_init__(self) -> None:
        _require_sha256(self.observation_identity, "wallet cohort forward observation identity")
        _require_sha256(self.admission_identity, "wallet cohort forward admission identity")
        if self.schema_version != WALLET_COHORT_FORWARD_SCHEMA_VERSION:
            raise ValueError("unsupported wallet cohort forward schema")
        for value, label in (
            (self.cohort_id, "cohort_id"),
            (self.cluster_id, "cluster_id"),
            (self.network, "network"),
            (self.metric_name, "metric_name"),
            (self.source_provider, "source_provider"),
            (self.adapter_version, "adapter_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("wallet cohort forward asset must be non-empty uppercase")
        if min(
            self.measurement_start_ms,
            self.measurement_end_ms,
            self.source_timestamp_ms,
            self.ingested_at_ms,
        ) < 0:
            raise ValueError("wallet cohort forward timestamps must be non-negative")
        if self.measurement_end_ms <= self.measurement_start_ms:
            raise ValueError("wallet cohort forward measurement end must follow start")
        if self.source_timestamp_ms < self.measurement_end_ms:
            raise ValueError("wallet cohort forward source timestamp cannot predate measurement end")
        if self.ingested_at_ms < self.source_timestamp_ms:
            raise ValueError("wallet cohort forward ingestion cannot predate source timestamp")
        if self.metric_value.is_nan() or self.metric_value.is_infinite():
            raise ValueError("wallet cohort forward metric must be finite")
        if self.observation_identity != canonical_sha256(
            wallet_cohort_forward_observation_payload(self)
        ):
            raise ValueError("wallet cohort forward observation identity mismatch")


def build_wallet_cohort_admission(
    *,
    cohort_id: str,
    cluster_id: str,
    asset: str,
    network: str,
    admitted_at_ms: int,
    basis_available_at_ms: int,
    source_provider: str,
    attribution_method: str,
    admission_rule_version: str,
    basis_evidence_identities: tuple[str, ...],
    source: DataSource,
) -> WalletCohortAdmission:
    evidence = tuple(sorted(set(basis_evidence_identities)))
    payload = {
        "admission_rule_version": admission_rule_version,
        "admitted_at_ms": admitted_at_ms,
        "asset": asset,
        "attribution_method": attribution_method,
        "basis_available_at_ms": basis_available_at_ms,
        "basis_evidence_identities": evidence,
        "cluster_id": cluster_id,
        "cohort_id": cohort_id,
        "network": network,
        "schema_version": WALLET_COHORT_ADMISSION_SCHEMA_VERSION,
        "source": source,
        "source_provider": source_provider,
    }
    return WalletCohortAdmission(
        admission_identity=canonical_sha256(payload),
        schema_version=WALLET_COHORT_ADMISSION_SCHEMA_VERSION,
        cohort_id=cohort_id,
        cluster_id=cluster_id,
        asset=asset,
        network=network,
        admitted_at_ms=admitted_at_ms,
        basis_available_at_ms=basis_available_at_ms,
        source_provider=source_provider,
        attribution_method=attribution_method,
        admission_rule_version=admission_rule_version,
        basis_evidence_identities=evidence,
        source=source,
    )


def build_wallet_cohort_forward_observation(
    *,
    admission_identity: str,
    cohort_id: str,
    cluster_id: str,
    asset: str,
    network: str,
    measurement_start_ms: int,
    measurement_end_ms: int,
    metric_name: str,
    metric_value: Decimal,
    source_provider: str,
    source: DataSource,
    source_timestamp_ms: int,
    ingested_at_ms: int,
    adapter_version: str,
) -> WalletCohortForwardObservation:
    payload = {
        "adapter_version": adapter_version,
        "admission_identity": admission_identity,
        "asset": asset,
        "cluster_id": cluster_id,
        "cohort_id": cohort_id,
        "ingested_at_ms": ingested_at_ms,
        "measurement_end_ms": measurement_end_ms,
        "measurement_start_ms": measurement_start_ms,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "network": network,
        "schema_version": WALLET_COHORT_FORWARD_SCHEMA_VERSION,
        "source": source,
        "source_provider": source_provider,
        "source_timestamp_ms": source_timestamp_ms,
    }
    return WalletCohortForwardObservation(
        observation_identity=canonical_sha256(payload),
        schema_version=WALLET_COHORT_FORWARD_SCHEMA_VERSION,
        admission_identity=admission_identity,
        cohort_id=cohort_id,
        cluster_id=cluster_id,
        asset=asset,
        network=network,
        measurement_start_ms=measurement_start_ms,
        measurement_end_ms=measurement_end_ms,
        metric_name=metric_name,
        metric_value=metric_value,
        source_provider=source_provider,
        source=source,
        source_timestamp_ms=source_timestamp_ms,
        ingested_at_ms=ingested_at_ms,
        adapter_version=adapter_version,
    )


def wallet_cohort_admission_payload(
    admission: WalletCohortAdmission,
) -> dict[str, object]:
    return {
        "admission_rule_version": admission.admission_rule_version,
        "admitted_at_ms": admission.admitted_at_ms,
        "asset": admission.asset,
        "attribution_method": admission.attribution_method,
        "basis_available_at_ms": admission.basis_available_at_ms,
        "basis_evidence_identities": admission.basis_evidence_identities,
        "cluster_id": admission.cluster_id,
        "cohort_id": admission.cohort_id,
        "network": admission.network,
        "schema_version": admission.schema_version,
        "source": admission.source,
        "source_provider": admission.source_provider,
    }


def wallet_cohort_forward_observation_payload(
    observation: WalletCohortForwardObservation,
) -> dict[str, object]:
    return {
        "adapter_version": observation.adapter_version,
        "admission_identity": observation.admission_identity,
        "asset": observation.asset,
        "cluster_id": observation.cluster_id,
        "cohort_id": observation.cohort_id,
        "ingested_at_ms": observation.ingested_at_ms,
        "measurement_end_ms": observation.measurement_end_ms,
        "measurement_start_ms": observation.measurement_start_ms,
        "metric_name": observation.metric_name,
        "metric_value": observation.metric_value,
        "network": observation.network,
        "schema_version": observation.schema_version,
        "source": observation.source,
        "source_provider": observation.source_provider,
        "source_timestamp_ms": observation.source_timestamp_ms,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
