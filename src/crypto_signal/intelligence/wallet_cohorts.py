from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.wallet_cohorts import (
    WalletCohortAdmission,
    WalletCohortForwardObservation,
)
from crypto_signal.ledger.serialization import canonical_sha256

WALLET_COHORT_ENGINE_VERSION = "wallet-cohort-registry-v2-slice2/1"
WALLET_COHORT_FREEZE_SCHEMA_VERSION = "wallet-cohort-registry-freeze-v1/1"


class WalletCohortStatus(StrEnum):
    MEASURED = "measured"
    REGISTRY_ONLY = "registry_only"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class WalletCohortMetrics:
    admitted_member_count: int
    measured_member_count: int
    measurement_coverage_fraction: Decimal
    metric_name: str | None
    mean_forward_metric: Decimal | None
    median_forward_metric: Decimal | None

    def __post_init__(self) -> None:
        if self.admitted_member_count <= 0:
            raise ValueError("wallet cohort metrics require admitted members")
        if not 0 <= self.measured_member_count <= self.admitted_member_count:
            raise ValueError("wallet cohort measured count outside admitted member count")
        if (
            self.measurement_coverage_fraction.is_nan()
            or self.measurement_coverage_fraction.is_infinite()
            or not Decimal(0) <= self.measurement_coverage_fraction <= Decimal(1)
        ):
            raise ValueError("wallet cohort coverage must be inside [0,1]")
        expected = Decimal(self.measured_member_count) / Decimal(self.admitted_member_count)
        if self.measurement_coverage_fraction != expected:
            raise ValueError("wallet cohort measurement coverage mismatch")
        if self.measured_member_count == 0:
            if (
                self.metric_name is not None
                or self.mean_forward_metric is not None
                or self.median_forward_metric is not None
            ):
                raise ValueError("unmeasured cohort cannot expose forward metrics")
        else:
            if not self.metric_name:
                raise ValueError("measured cohort requires metric name")
            if self.mean_forward_metric is None or self.median_forward_metric is None:
                raise ValueError("measured cohort requires aggregate forward metrics")
            for value in (self.mean_forward_metric, self.median_forward_metric):
                if value.is_nan() or value.is_infinite():
                    raise ValueError("wallet cohort aggregate metric must be finite")


@dataclass(frozen=True, slots=True)
class WalletCohortAnalysis:
    evidence_identity: str
    engine_version: str
    cohort_id: str
    asset: str
    network: str
    admission_rule_version: str
    as_of_ms: int
    earliest_admission_ms: int | None
    latest_admission_ms: int | None
    latest_forward_measurement_ms: int | None
    status: WalletCohortStatus
    metrics: WalletCohortMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "wallet cohort evidence identity")
        if self.engine_version != WALLET_COHORT_ENGINE_VERSION:
            raise ValueError("unsupported wallet cohort engine version")
        for value, label in (
            (self.cohort_id, "cohort_id"),
            (self.network, "network"),
            (self.admission_rule_version, "admission_rule_version"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("wallet cohort analysis asset must be uppercase")
        if self.as_of_ms < 0:
            raise ValueError("wallet cohort as_of_ms must be non-negative")
        if (self.earliest_admission_ms is None) != (self.latest_admission_ms is None):
            raise ValueError("wallet cohort admission bounds must appear together")
        if self.earliest_admission_ms is not None:
            assert self.latest_admission_ms is not None
            if not 0 <= self.earliest_admission_ms <= self.latest_admission_ms <= self.as_of_ms:
                raise ValueError("wallet cohort admission bounds outside PIT cutoff")
        if (
            self.latest_forward_measurement_ms is not None
            and not 0 <= self.latest_forward_measurement_ms <= self.as_of_ms
        ):
            raise ValueError("wallet cohort forward measurement outside PIT cutoff")
        if self.status is WalletCohortStatus.UNRESOLVED:
            if self.metrics is not None or not self.uncertainty_flags:
                raise ValueError("unresolved wallet cohort requires uncertainty only")
            if self.earliest_admission_ms is not None:
                raise ValueError("unresolved wallet cohort cannot expose admissions")
        elif self.metrics is None:
            raise ValueError("resolved wallet cohort requires metrics")
        elif self.status is WalletCohortStatus.REGISTRY_ONLY:
            if self.metrics.measured_member_count != 0:
                raise ValueError("registry-only wallet cohort cannot expose measurements")
        elif self.metrics.measured_member_count <= 0:
            raise ValueError("measured wallet cohort requires forward observations")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("wallet cohort evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class WalletCohortEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: WalletCohortAnalysis
    admissions: tuple[WalletCohortAdmission, ...]
    forward_observations: tuple[WalletCohortForwardObservation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "wallet cohort freeze identity")
        if self.schema_version != WALLET_COHORT_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported wallet cohort freeze schema")
        if any(item.admitted_at_ms > self.analysis.as_of_ms for item in self.admissions):
            raise ValueError("wallet cohort freeze contains future admission")
        if any(
            max(item.measurement_end_ms, item.source_timestamp_ms, item.ingested_at_ms)
            > self.analysis.as_of_ms
            for item in self.forward_observations
        ):
            raise ValueError("wallet cohort freeze contains future forward observation")
        if self.freeze_identity != canonical_sha256(_freeze_payload(self)):
            raise ValueError("wallet cohort freeze identity mismatch")


def analyze_wallet_cohort(
    admissions: Sequence[WalletCohortAdmission],
    forward_observations: Sequence[WalletCohortForwardObservation] = (),
    *,
    as_of_ms: int,
) -> WalletCohortAnalysis:
    return build_wallet_cohort_evidence_freeze(
        admissions,
        forward_observations,
        as_of_ms=as_of_ms,
    ).analysis


def build_wallet_cohort_evidence_freeze(
    admissions: Sequence[WalletCohortAdmission],
    forward_observations: Sequence[WalletCohortForwardObservation] = (),
    *,
    as_of_ms: int,
) -> WalletCohortEvidenceFreeze:
    if not admissions:
        raise ValueError("wallet cohort registry requires admissions")
    if as_of_ms < 0:
        raise ValueError("wallet cohort as_of_ms must be non-negative")

    ordered_admissions = tuple(
        sorted(admissions, key=lambda item: (item.admitted_at_ms, item.admission_identity))
    )
    _validate_admission_context(ordered_admissions)
    _reject_admission_duplicates(ordered_admissions)
    admission_by_id = {item.admission_identity: item for item in ordered_admissions}

    ordered_forward = tuple(
        sorted(
            forward_observations,
            key=lambda item: (
                item.measurement_end_ms,
                item.ingested_at_ms,
                item.observation_identity,
            ),
        )
    )
    _reject_forward_duplicates(ordered_forward)
    _validate_forward_context(ordered_forward, admission_by_id)

    eligible_admissions = tuple(
        item for item in ordered_admissions if item.admitted_at_ms <= as_of_ms
    )
    context = ordered_admissions[0]
    if not eligible_admissions:
        analysis = _unresolved(
            context=context,
            as_of_ms=as_of_ms,
            flags=("wallet_cohort_admission_unavailable_at_as_of",),
        )
        return _freeze(analysis, (), ())

    eligible_ids = {item.admission_identity for item in eligible_admissions}
    eligible_forward = tuple(
        item
        for item in ordered_forward
        if item.admission_identity in eligible_ids
        and max(item.measurement_end_ms, item.source_timestamp_ms, item.ingested_at_ms)
        <= as_of_ms
    )
    selected_by_admission: dict[str, WalletCohortForwardObservation] = {}
    for item in eligible_forward:
        selected_by_admission[item.admission_identity] = item
    selected_forward = tuple(
        sorted(
            selected_by_admission.values(),
            key=lambda item: (item.admission_identity, item.measurement_end_ms),
        )
    )

    metrics = _metrics(eligible_admissions, selected_forward)
    status = (
        WalletCohortStatus.REGISTRY_ONLY
        if metrics.measured_member_count == 0
        else WalletCohortStatus.MEASURED
    )
    flags = (
        "cohort_membership_frozen_before_forward_measurement",
        "cohort_performance_is_not_actor_identity_or_future_return",
    )
    payload = _payload(
        context=context,
        admissions=eligible_admissions,
        forward=selected_forward,
        as_of_ms=as_of_ms,
        status=status,
        metrics=metrics,
        flags=flags,
    )
    analysis = WalletCohortAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=WALLET_COHORT_ENGINE_VERSION,
        cohort_id=context.cohort_id,
        asset=context.asset,
        network=context.network,
        admission_rule_version=context.admission_rule_version,
        as_of_ms=as_of_ms,
        earliest_admission_ms=eligible_admissions[0].admitted_at_ms,
        latest_admission_ms=eligible_admissions[-1].admitted_at_ms,
        latest_forward_measurement_ms=(
            None
            if not selected_forward
            else max(item.measurement_end_ms for item in selected_forward)
        ),
        status=status,
        metrics=metrics,
        uncertainty_flags=flags,
    )
    return _freeze(analysis, eligible_admissions, selected_forward)


def _metrics(
    admissions: tuple[WalletCohortAdmission, ...],
    forward: tuple[WalletCohortForwardObservation, ...],
) -> WalletCohortMetrics:
    if not forward:
        return WalletCohortMetrics(
            admitted_member_count=len(admissions),
            measured_member_count=0,
            measurement_coverage_fraction=Decimal(0),
            metric_name=None,
            mean_forward_metric=None,
            median_forward_metric=None,
        )
    metric_names = {item.metric_name for item in forward}
    if len(metric_names) != 1:
        raise ValueError("wallet cohort forward observations require one metric semantic")
    values = tuple(sorted(item.metric_value for item in forward))
    count = len(values)
    midpoint = count // 2
    if count % 2:
        median = values[midpoint]
    else:
        median = (values[midpoint - 1] + values[midpoint]) / Decimal(2)
    return WalletCohortMetrics(
        admitted_member_count=len(admissions),
        measured_member_count=count,
        measurement_coverage_fraction=Decimal(count) / Decimal(len(admissions)),
        metric_name=next(iter(metric_names)),
        mean_forward_metric=sum(values, start=Decimal(0)) / Decimal(count),
        median_forward_metric=median,
    )


def _validate_admission_context(admissions: tuple[WalletCohortAdmission, ...]) -> None:
    first = admissions[0]
    context = (
        first.cohort_id,
        first.asset,
        first.network,
        first.admission_rule_version,
    )
    if any(
        (
            item.cohort_id,
            item.asset,
            item.network,
            item.admission_rule_version,
        )
        != context
        for item in admissions
    ):
        raise ValueError("wallet cohort admissions require exact cohort context")


def _reject_admission_duplicates(admissions: tuple[WalletCohortAdmission, ...]) -> None:
    identities = tuple(item.admission_identity for item in admissions)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate wallet cohort admission identity")
    cluster_ids = tuple(item.cluster_id for item in admissions)
    if len(cluster_ids) != len(set(cluster_ids)):
        raise ValueError("wallet cohort cluster can be admitted only once per cohort")


def _reject_forward_duplicates(
    observations: tuple[WalletCohortForwardObservation, ...],
) -> None:
    identities = tuple(item.observation_identity for item in observations)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate wallet cohort forward observation identity")


def _validate_forward_context(
    observations: tuple[WalletCohortForwardObservation, ...],
    admission_by_id: dict[str, WalletCohortAdmission],
) -> None:
    for item in observations:
        admission = admission_by_id.get(item.admission_identity)
        if admission is None:
            raise ValueError("wallet cohort forward observation references unknown admission")
        if (
            item.cohort_id,
            item.cluster_id,
            item.asset,
            item.network,
        ) != (
            admission.cohort_id,
            admission.cluster_id,
            admission.asset,
            admission.network,
        ):
            raise ValueError("wallet cohort forward observation context mismatch")
        if item.measurement_start_ms < admission.admitted_at_ms:
            raise ValueError("wallet cohort forward measurement cannot start before admission")


def _unresolved(
    *,
    context: WalletCohortAdmission,
    as_of_ms: int,
    flags: tuple[str, ...],
) -> WalletCohortAnalysis:
    payload = {
        "admission_rule_version": context.admission_rule_version,
        "as_of_ms": as_of_ms,
        "asset": context.asset,
        "cohort_id": context.cohort_id,
        "earliest_admission_ms": None,
        "engine_version": WALLET_COHORT_ENGINE_VERSION,
        "latest_admission_ms": None,
        "latest_forward_measurement_ms": None,
        "metrics": None,
        "network": context.network,
        "status": WalletCohortStatus.UNRESOLVED,
        "uncertainty_flags": flags,
    }
    return WalletCohortAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=WALLET_COHORT_ENGINE_VERSION,
        cohort_id=context.cohort_id,
        asset=context.asset,
        network=context.network,
        admission_rule_version=context.admission_rule_version,
        as_of_ms=as_of_ms,
        earliest_admission_ms=None,
        latest_admission_ms=None,
        latest_forward_measurement_ms=None,
        status=WalletCohortStatus.UNRESOLVED,
        metrics=None,
        uncertainty_flags=flags,
    )


def _payload(
    *,
    context: WalletCohortAdmission,
    admissions: tuple[WalletCohortAdmission, ...],
    forward: tuple[WalletCohortForwardObservation, ...],
    as_of_ms: int,
    status: WalletCohortStatus,
    metrics: WalletCohortMetrics,
    flags: tuple[str, ...],
) -> dict[str, object]:
    return {
        "admission_rule_version": context.admission_rule_version,
        "as_of_ms": as_of_ms,
        "asset": context.asset,
        "cohort_id": context.cohort_id,
        "earliest_admission_ms": admissions[0].admitted_at_ms,
        "engine_version": WALLET_COHORT_ENGINE_VERSION,
        "latest_admission_ms": admissions[-1].admitted_at_ms,
        "latest_forward_measurement_ms": (
            None if not forward else max(item.measurement_end_ms for item in forward)
        ),
        "metrics": metrics,
        "network": context.network,
        "status": status,
        "uncertainty_flags": flags,
    }


def _analysis_payload(analysis: WalletCohortAnalysis) -> dict[str, object]:
    return {
        "admission_rule_version": analysis.admission_rule_version,
        "as_of_ms": analysis.as_of_ms,
        "asset": analysis.asset,
        "cohort_id": analysis.cohort_id,
        "earliest_admission_ms": analysis.earliest_admission_ms,
        "engine_version": analysis.engine_version,
        "latest_admission_ms": analysis.latest_admission_ms,
        "latest_forward_measurement_ms": analysis.latest_forward_measurement_ms,
        "metrics": analysis.metrics,
        "network": analysis.network,
        "status": analysis.status,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _freeze(
    analysis: WalletCohortAnalysis,
    admissions: tuple[WalletCohortAdmission, ...],
    forward: tuple[WalletCohortForwardObservation, ...],
) -> WalletCohortEvidenceFreeze:
    payload = {
        "admission_identities": [item.admission_identity for item in admissions],
        "analysis_identity": analysis.evidence_identity,
        "forward_observation_identities": [
            item.observation_identity for item in forward
        ],
        "schema_version": WALLET_COHORT_FREEZE_SCHEMA_VERSION,
    }
    return WalletCohortEvidenceFreeze(
        freeze_identity=canonical_sha256(payload),
        schema_version=WALLET_COHORT_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        admissions=admissions,
        forward_observations=forward,
    )


def _freeze_payload(freeze: WalletCohortEvidenceFreeze) -> dict[str, object]:
    return {
        "admission_identities": [
            item.admission_identity for item in freeze.admissions
        ],
        "analysis_identity": freeze.analysis.evidence_identity,
        "forward_observation_identities": [
            item.observation_identity for item in freeze.forward_observations
        ],
        "schema_version": freeze.schema_version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
