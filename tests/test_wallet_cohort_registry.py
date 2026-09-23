from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.models import DataSource
from crypto_signal.data.wallet_cohorts import (
    build_wallet_cohort_admission,
    build_wallet_cohort_forward_observation,
)
from crypto_signal.intelligence.wallet_cohorts import (
    WalletCohortStatus,
    analyze_wallet_cohort,
    build_wallet_cohort_evidence_freeze,
)
from crypto_signal.ledger.serialization import canonical_sha256

AS_OF = 10_000_000


def _evidence(label: str) -> str:
    return canonical_sha256({"evidence": label})


def _admission(
    cluster_id: str,
    *,
    admitted_at_ms: int,
    asset: str = "BTC",
    cohort_id: str = "cohort-alpha",
    network: str = "bitcoin_mainnet",
):
    return build_wallet_cohort_admission(
        cohort_id=cohort_id,
        cluster_id=cluster_id,
        asset=asset,
        network=network,
        admitted_at_ms=admitted_at_ms,
        basis_available_at_ms=admitted_at_ms - 100,
        source_provider="test-attribution-provider",
        attribution_method="provider-cluster-attribution/v1",
        admission_rule_version="cohort-rule-v1",
        basis_evidence_identities=(
            _evidence(f"{cluster_id}-b"),
            _evidence(f"{cluster_id}-a"),
        ),
        source=DataSource.AGGREGATED,
    )


def _forward(
    admission,
    *,
    start_ms: int,
    end_ms: int,
    value: str,
    metric_name: str = "provider_forward_performance_fraction",
    ingested_at_ms: int | None = None,
):
    source_ms = end_ms + 10
    return build_wallet_cohort_forward_observation(
        admission_identity=admission.admission_identity,
        cohort_id=admission.cohort_id,
        cluster_id=admission.cluster_id,
        asset=admission.asset,
        network=admission.network,
        measurement_start_ms=start_ms,
        measurement_end_ms=end_ms,
        metric_name=metric_name,
        metric_value=Decimal(value),
        source_provider="test-performance-provider",
        source=DataSource.AGGREGATED,
        source_timestamp_ms=source_ms,
        ingested_at_ms=source_ms + 10 if ingested_at_ms is None else ingested_at_ms,
        adapter_version="wallet-cohort-test/1",
    )


def test_admission_identity_is_deterministic_and_cannot_backdate_basis() -> None:
    first = _admission("cluster-a", admitted_at_ms=1_000)
    second = _admission("cluster-a", admitted_at_ms=1_000)

    assert first == second
    assert first.basis_evidence_identities == tuple(sorted(first.basis_evidence_identities))
    assert len(first.admission_identity) == 64

    with pytest.raises(ValueError, match="cannot predate basis evidence"):
        replace(first, basis_available_at_ms=first.admitted_at_ms + 1)


def test_registry_only_freezes_membership_before_any_forward_sample() -> None:
    admissions = (
        _admission("cluster-a", admitted_at_ms=1_000),
        _admission("cluster-b", admitted_at_ms=2_000),
    )
    freeze = build_wallet_cohort_evidence_freeze(admissions, as_of_ms=3_000)

    assert freeze.analysis.status is WalletCohortStatus.REGISTRY_ONLY
    assert freeze.analysis.metrics is not None
    assert freeze.analysis.metrics.admitted_member_count == 2
    assert freeze.analysis.metrics.measured_member_count == 0
    assert freeze.analysis.metrics.measurement_coverage_fraction == Decimal(0)
    assert freeze.analysis.metrics.metric_name is None
    assert freeze.forward_observations == ()


def test_forward_measurement_uses_only_post_admission_latest_per_member() -> None:
    a = _admission("cluster-a", admitted_at_ms=1_000)
    b = _admission("cluster-b", admitted_at_ms=2_000)
    observations = (
        _forward(a, start_ms=1_000, end_ms=4_000, value="0.10"),
        _forward(a, start_ms=1_000, end_ms=6_000, value="0.20"),
        _forward(b, start_ms=2_000, end_ms=5_000, value="-0.10"),
    )

    first = build_wallet_cohort_evidence_freeze(
        (a, b),
        observations,
        as_of_ms=7_000,
    )
    second = build_wallet_cohort_evidence_freeze(
        (b, a),
        tuple(reversed(observations)),
        as_of_ms=7_000,
    )

    assert first == second
    assert first.analysis.status is WalletCohortStatus.MEASURED
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.admitted_member_count == 2
    assert first.analysis.metrics.measured_member_count == 2
    assert first.analysis.metrics.measurement_coverage_fraction == Decimal(1)
    assert first.analysis.metrics.mean_forward_metric == Decimal("0.05")
    assert first.analysis.metrics.median_forward_metric == Decimal("0.05")
    assert len(first.forward_observations) == 2
    assert {item.metric_value for item in first.forward_observations} == {
        Decimal("0.20"),
        Decimal("-0.10"),
    }


def test_future_admission_and_future_or_late_measurement_cannot_rewrite_freeze() -> None:
    a = _admission("cluster-a", admitted_at_ms=1_000)
    base_obs = _forward(a, start_ms=1_000, end_ms=6_000, value="0.20")
    baseline = build_wallet_cohort_evidence_freeze(
        (a,),
        (base_obs,),
        as_of_ms=7_000,
    )

    future_admission = _admission("cluster-future", admitted_at_ms=8_000)
    future_obs = _forward(
        a,
        start_ms=1_000,
        end_ms=7_500,
        value="9.99",
    )
    late_obs = _forward(
        a,
        start_ms=1_000,
        end_ms=6_500,
        value="-9.99",
        ingested_at_ms=7_001,
    )
    changed = build_wallet_cohort_evidence_freeze(
        (a, future_admission),
        (base_obs, future_obs, late_obs),
        as_of_ms=7_000,
    )

    assert changed == baseline


def test_forward_measurement_cannot_start_before_member_admission() -> None:
    admission = _admission("cluster-a", admitted_at_ms=5_000)
    invalid = _forward(
        admission,
        start_ms=4_999,
        end_ms=6_000,
        value="0.20",
    )

    with pytest.raises(ValueError, match="cannot start before admission"):
        analyze_wallet_cohort((admission,), (invalid,), as_of_ms=7_000)


def test_unknown_admission_context_and_duplicate_cluster_fail_closed() -> None:
    a = _admission("cluster-a", admitted_at_ms=1_000)
    b = _admission("cluster-b", admitted_at_ms=2_000)
    wrong_context = build_wallet_cohort_forward_observation(
        admission_identity=a.admission_identity,
        cohort_id=a.cohort_id,
        cluster_id="cluster-other",
        asset=a.asset,
        network=a.network,
        measurement_start_ms=1_000,
        measurement_end_ms=4_000,
        metric_name="provider_forward_performance_fraction",
        metric_value=Decimal("0.10"),
        source_provider="test-performance-provider",
        source=DataSource.AGGREGATED,
        source_timestamp_ms=4_010,
        ingested_at_ms=4_020,
        adapter_version="wallet-cohort-test/1",
    )
    unknown = _forward(b, start_ms=2_000, end_ms=4_500, value="0.10")

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_wallet_cohort((a,), (wrong_context,), as_of_ms=5_000)
    with pytest.raises(ValueError, match="unknown admission"):
        analyze_wallet_cohort((a,), (unknown,), as_of_ms=5_000)

    duplicate_cluster = _admission("cluster-a", admitted_at_ms=2_000)
    with pytest.raises(ValueError, match="admitted only once"):
        analyze_wallet_cohort((a, duplicate_cluster), as_of_ms=3_000)


def test_mixed_forward_metric_semantics_are_not_aggregated() -> None:
    a = _admission("cluster-a", admitted_at_ms=1_000)
    b = _admission("cluster-b", admitted_at_ms=2_000)
    first = _forward(a, start_ms=1_000, end_ms=4_000, value="0.10")
    second = _forward(
        b,
        start_ms=2_000,
        end_ms=5_000,
        value="3.0",
        metric_name="provider_forward_risk_adjusted_score",
    )

    with pytest.raises(ValueError, match="one metric semantic"):
        analyze_wallet_cohort((a, b), (first, second), as_of_ms=6_000)


def test_no_admission_available_at_as_of_is_unresolved_without_hindsight() -> None:
    future = _admission("cluster-a", admitted_at_ms=8_000)
    result = analyze_wallet_cohort((future,), as_of_ms=7_000)

    assert result.status is WalletCohortStatus.UNRESOLVED
    assert result.metrics is None
    assert result.earliest_admission_ms is None
    assert result.uncertainty_flags == (
        "wallet_cohort_admission_unavailable_at_as_of",
    )


def test_identity_tampering_fails_closed() -> None:
    admission = _admission("cluster-a", admitted_at_ms=1_000)
    freeze = build_wallet_cohort_evidence_freeze((admission,), as_of_ms=2_000)

    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    with pytest.raises(ValueError, match="admission identity mismatch"):
        replace(admission, admission_identity="f" * 64)
