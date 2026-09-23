from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crypto_signal.data.wallet_cohorts import WalletCohortAdmission
from crypto_signal.ledger.serialization import canonical_sha256

WALLET_COHORT_REGISTRY_ENGINE_VERSION = "wallet-cohort-registry-v2-slice2/1"
WALLET_COHORT_REGISTRY_FREEZE_SCHEMA_VERSION = "wallet-cohort-registry-freeze-v1/1"


@dataclass(frozen=True, slots=True)
class WalletCohortRegistrySnapshot:
    snapshot_identity: str
    engine_version: str
    as_of_ms: int
    admission_identities: tuple[str, ...]
    cohort_ids: tuple[str, ...]
    admission_count: int
    latest_admitted_at_ms: int | None
    distinct_source_provider_count: int
    distinct_attribution_method_count: int

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "wallet cohort registry snapshot identity")
        if self.engine_version != WALLET_COHORT_REGISTRY_ENGINE_VERSION:
            raise ValueError("unsupported wallet cohort registry engine version")
        if self.as_of_ms < 0:
            raise ValueError("wallet cohort registry as_of_ms must be non-negative")
        if self.admission_count < 0:
            raise ValueError("wallet cohort registry admission count cannot be negative")
        if self.admission_count != len(self.admission_identities):
            raise ValueError("wallet cohort registry admission identity count mismatch")
        if self.admission_count != len(self.cohort_ids):
            raise ValueError("wallet cohort registry cohort count mismatch")
        if tuple(sorted(set(self.admission_identities))) != self.admission_identities:
            raise ValueError("wallet cohort registry admission identities must be unique and sorted")
        if tuple(sorted(set(self.cohort_ids))) != self.cohort_ids:
            raise ValueError("wallet cohort registry cohort ids must be unique and sorted")
        for identity in self.admission_identities:
            _require_sha256(identity, "wallet cohort registry admission identity")
        if min(
            self.distinct_source_provider_count,
            self.distinct_attribution_method_count,
        ) < 0:
            raise ValueError("wallet cohort registry distinct counts cannot be negative")
        if self.admission_count == 0:
            if self.latest_admitted_at_ms is not None:
                raise ValueError("empty wallet cohort registry cannot have latest admission")
            if (
                self.distinct_source_provider_count != 0
                or self.distinct_attribution_method_count != 0
            ):
                raise ValueError("empty wallet cohort registry cannot have source counts")
        else:
            if self.latest_admitted_at_ms is None:
                raise ValueError("non-empty wallet cohort registry requires latest admission")
            if not 0 <= self.latest_admitted_at_ms <= self.as_of_ms:
                raise ValueError("wallet cohort registry latest admission outside PIT boundary")
            if (
                self.distinct_source_provider_count <= 0
                or self.distinct_attribution_method_count <= 0
            ):
                raise ValueError("non-empty wallet cohort registry requires source counts")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("wallet cohort registry snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class WalletCohortRegistryEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    snapshot: WalletCohortRegistrySnapshot
    admissions: tuple[WalletCohortAdmission, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "wallet cohort registry freeze identity")
        if self.schema_version != WALLET_COHORT_REGISTRY_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported wallet cohort registry freeze schema")
        if len(self.admissions) != self.snapshot.admission_count:
            raise ValueError("wallet cohort registry freeze admission count mismatch")
        expected_ids = tuple(sorted(item.admission_identity for item in self.admissions))
        if expected_ids != self.snapshot.admission_identities:
            raise ValueError("wallet cohort registry freeze admission identities mismatch")
        if any(item.admitted_at_ms > self.snapshot.as_of_ms for item in self.admissions):
            raise ValueError("wallet cohort registry freeze contains future admission")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("wallet cohort registry freeze identity mismatch")


def build_wallet_cohort_registry_evidence_freeze(
    admissions: Sequence[WalletCohortAdmission],
    *,
    as_of_ms: int,
) -> WalletCohortRegistryEvidenceFreeze:
    if as_of_ms < 0:
        raise ValueError("wallet cohort registry as_of_ms must be non-negative")
    _reject_duplicates(admissions)

    eligible = tuple(
        sorted(
            (item for item in admissions if item.admitted_at_ms <= as_of_ms),
            key=lambda item: (
                item.admitted_at_ms,
                item.cohort_id,
                item.admission_identity,
            ),
        )
    )
    admission_ids = tuple(sorted(item.admission_identity for item in eligible))
    cohort_ids = tuple(sorted(item.cohort_id for item in eligible))
    latest = max((item.admitted_at_ms for item in eligible), default=None)
    providers = {item.source_provider for item in eligible}
    attribution_methods = {item.attribution_method for item in eligible}

    payload = {
        "admission_count": len(eligible),
        "admission_identities": admission_ids,
        "as_of_ms": as_of_ms,
        "cohort_ids": cohort_ids,
        "distinct_attribution_method_count": len(attribution_methods),
        "distinct_source_provider_count": len(providers),
        "engine_version": WALLET_COHORT_REGISTRY_ENGINE_VERSION,
        "latest_admitted_at_ms": latest,
    }
    snapshot = WalletCohortRegistrySnapshot(
        snapshot_identity=canonical_sha256(payload),
        engine_version=WALLET_COHORT_REGISTRY_ENGINE_VERSION,
        as_of_ms=as_of_ms,
        admission_identities=admission_ids,
        cohort_ids=cohort_ids,
        admission_count=len(eligible),
        latest_admitted_at_ms=latest,
        distinct_source_provider_count=len(providers),
        distinct_attribution_method_count=len(attribution_methods),
    )
    return _freeze(snapshot, eligible)


def _reject_duplicates(admissions: Sequence[WalletCohortAdmission]) -> None:
    admission_ids = tuple(item.admission_identity for item in admissions)
    if len(admission_ids) != len(set(admission_ids)):
        raise ValueError("duplicate wallet cohort admission identity")

    cohort_ids = tuple(item.cohort_id for item in admissions)
    if len(cohort_ids) != len(set(cohort_ids)):
        raise ValueError("duplicate wallet cohort id")

    cluster_keys = tuple(
        (item.network, item.cluster_id, item.asset)
        for item in admissions
    )
    if len(cluster_keys) != len(set(cluster_keys)):
        raise ValueError("duplicate wallet cohort network/cluster/asset admission")


def _freeze(
    snapshot: WalletCohortRegistrySnapshot,
    admissions: tuple[WalletCohortAdmission, ...],
) -> WalletCohortRegistryEvidenceFreeze:
    payload = {
        "admission_identities": [
            item.admission_identity
            for item in sorted(admissions, key=lambda item: item.admission_identity)
        ],
        "schema_version": WALLET_COHORT_REGISTRY_FREEZE_SCHEMA_VERSION,
        "snapshot_identity": snapshot.snapshot_identity,
    }
    return WalletCohortRegistryEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=WALLET_COHORT_REGISTRY_FREEZE_SCHEMA_VERSION,
        snapshot=snapshot,
        admissions=admissions,
    )


def _snapshot_payload(snapshot: WalletCohortRegistrySnapshot) -> dict[str, object]:
    return {
        "admission_count": snapshot.admission_count,
        "admission_identities": snapshot.admission_identities,
        "as_of_ms": snapshot.as_of_ms,
        "cohort_ids": snapshot.cohort_ids,
        "distinct_attribution_method_count": snapshot.distinct_attribution_method_count,
        "distinct_source_provider_count": snapshot.distinct_source_provider_count,
        "engine_version": snapshot.engine_version,
        "latest_admitted_at_ms": snapshot.latest_admitted_at_ms,
    }


def _freeze_payload(
    freeze: WalletCohortRegistryEvidenceFreeze,
) -> dict[str, object]:
    return {
        "admission_identities": [
            item.admission_identity
            for item in sorted(
                freeze.admissions,
                key=lambda item: item.admission_identity,
            )
        ],
        "schema_version": freeze.schema_version,
        "snapshot_identity": freeze.snapshot.snapshot_identity,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
