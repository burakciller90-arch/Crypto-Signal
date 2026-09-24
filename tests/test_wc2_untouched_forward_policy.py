from __future__ import annotations

import sqlite3
from dataclasses import fields, replace
from pathlib import Path

import pytest

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2_MIN_CALENDAR_DAYS,
    WC2_MIN_DECISIVE_PER_ASSET,
    WC2_MIN_DECISIVE_PER_REGIME,
    WC2_MIN_QUALIFYING_REGIMES,
    WC2_MIN_TOTAL_DECISIVE_N,
    WC2PolicyStore,
    WC2ReviewStatus,
    build_wc2_cohort_readiness_evidence,
    build_wc2_untouched_forward_policy,
    evaluate_wc2_review_readiness,
)
from crypto_signal.outcomes.models import EvidenceClass

DAY_MS = 86_400_000
PREREGISTERED_AT_MS = 1_000
COLLECTION_START_MS = 2_000


def _policy():
    return build_wc2_untouched_forward_policy(
        preregistered_at_ms=PREREGISTERED_AT_MS,
        collection_start_ms=COLLECTION_START_MS,
    )


def _eligible_evidence():
    policy = _policy()
    collection_end_ms = (
        COLLECTION_START_MS + WC2_MIN_CALENDAR_DAYS * DAY_MS
    )
    return build_wc2_cohort_readiness_evidence(
        policy=policy,
        observed_at_ms=collection_end_ms + 1,
        collection_start_ms=COLLECTION_START_MS,
        collection_end_ms=collection_end_ms,
        total_forecast_n=420,
        resolved_forecast_n=360,
        decisive_n=WC2_MIN_TOTAL_DECISIVE_N,
        paper_decision_n=420,
        trade_decision_n=180,
        simulated_execution_n=180,
        explicit_cost_evidence_trade_n=180,
        asset_decisive_counts=(
            ("BTCUSDT", 100),
            ("ETHUSDT", 100),
            ("SOLUSDT", 100),
        ),
        regime_decisive_counts=(
            ("high_vol_trend", 100),
            ("low_vol_range", 100),
            ("transition", 100),
        ),
        loss_retention_complete=True,
        abstain_retention_complete=True,
        invalidation_retention_complete=True,
        unresolved_retention_complete=True,
        source_evidence_identities=("a" * 64, "b" * 64),
    )


def test_wc2_policy_is_preregistered_and_does_not_claim_performance() -> None:
    policy = _policy()

    assert policy.preregistered_at_ms < policy.collection_start_ms
    assert policy.evidence_class is EvidenceClass.LIVE_UNTOUCHED_FORWARD
    assert policy.minimum_total_decisive_n == 300
    assert policy.minimum_decisive_per_asset == 75
    assert policy.minimum_qualifying_regimes == 3
    assert policy.minimum_decisive_per_regime == 50
    assert policy.minimum_calendar_days == 120
    assert policy.automatic_promotion is False
    assert policy.performance_thresholds_included is False
    assert policy.production_authority is False
    assert policy.real_capital == 0

    field_names = {item.name for item in fields(type(policy))}
    forbidden = {
        "minimum_accuracy",
        "minimum_win_rate",
        "minimum_profit_factor",
        "minimum_expectancy",
        "minimum_sharpe",
        "minimum_sortino",
    }
    assert field_names.isdisjoint(forbidden)


def test_wc2_policy_cannot_be_registered_after_collection_start() -> None:
    with pytest.raises(ValueError, match="preregistered before collection"):
        build_wc2_untouched_forward_policy(
            preregistered_at_ms=2_000,
            collection_start_ms=2_000,
        )


def test_wc2_review_eligibility_requires_all_preregistered_support() -> None:
    policy = _policy()
    evidence = _eligible_evidence()

    readiness = evaluate_wc2_review_readiness(policy, evidence)

    assert readiness.status is WC2ReviewStatus.REVIEW_ELIGIBLE
    assert readiness.reason_codes == ()
    assert readiness.qualifying_regime_count == 3
    assert readiness.calendar_duration_days == 120
    assert (
        readiness.semantic
        == "eligible_for_wc3_review_not_edge_or_profitability_claim"
    )
    assert readiness.automatic_promotion is False
    assert readiness.production_authority is False
    assert readiness.real_capital == 0


def test_wc2_review_fails_closed_on_sample_asset_regime_cost_and_retention() -> None:
    policy = _policy()
    base = _eligible_evidence()
    evidence = build_wc2_cohort_readiness_evidence(
        policy=policy,
        observed_at_ms=base.observed_at_ms,
        collection_start_ms=base.collection_start_ms,
        collection_end_ms=(
            base.collection_start_ms
            + (WC2_MIN_CALENDAR_DAYS - 1) * DAY_MS
        ),
        total_forecast_n=420,
        resolved_forecast_n=250,
        decisive_n=220,
        paper_decision_n=419,
        trade_decision_n=180,
        simulated_execution_n=179,
        explicit_cost_evidence_trade_n=178,
        asset_decisive_counts=(
            ("BTCUSDT", WC2_MIN_DECISIVE_PER_ASSET),
            ("ETHUSDT", WC2_MIN_DECISIVE_PER_ASSET - 1),
            ("SOLUSDT", 71),
        ),
        regime_decisive_counts=(
            ("high_vol_trend", WC2_MIN_DECISIVE_PER_REGIME),
            ("low_vol_range", WC2_MIN_DECISIVE_PER_REGIME - 1),
            ("transition", WC2_MIN_DECISIVE_PER_REGIME - 2),
            ("unclassified", 73),
        ),
        loss_retention_complete=False,
        abstain_retention_complete=False,
        invalidation_retention_complete=False,
        unresolved_retention_complete=False,
        source_evidence_identities=base.source_evidence_identities,
    )

    readiness = evaluate_wc2_review_readiness(policy, evidence)

    assert readiness.status is WC2ReviewStatus.INSUFFICIENT_EVIDENCE
    assert readiness.reason_codes == tuple(
        sorted(
            {
                "abstain_retention_incomplete",
                "asset_ETHUSDT_decisive_support_below_minimum",
                "asset_SOLUSDT_decisive_support_below_minimum",
                "calendar_duration_below_minimum",
                "decisive_sample_below_minimum",
                "execution_cost_evidence_incomplete",
                "invalidation_retention_incomplete",
                "loss_retention_incomplete",
                "paper_decision_lineage_incomplete",
                "qualifying_regime_support_below_minimum",
                "simulated_execution_lineage_incomplete",
                "unresolved_retention_incomplete",
            }
        )
    )
    assert readiness.automatic_promotion is False


def test_wc2_cohort_cannot_backdate_into_pre_policy_history() -> None:
    policy = _policy()
    base = _eligible_evidence()

    with pytest.raises(ValueError, match="predate preregistered"):
        build_wc2_cohort_readiness_evidence(
            policy=policy,
            observed_at_ms=base.observed_at_ms,
            collection_start_ms=COLLECTION_START_MS - 1,
            collection_end_ms=base.collection_end_ms,
            total_forecast_n=base.total_forecast_n,
            resolved_forecast_n=base.resolved_forecast_n,
            decisive_n=base.decisive_n,
            paper_decision_n=base.paper_decision_n,
            trade_decision_n=base.trade_decision_n,
            simulated_execution_n=base.simulated_execution_n,
            explicit_cost_evidence_trade_n=(
                base.explicit_cost_evidence_trade_n
            ),
            asset_decisive_counts=base.asset_decisive_counts,
            regime_decisive_counts=base.regime_decisive_counts,
            loss_retention_complete=True,
            abstain_retention_complete=True,
            invalidation_retention_complete=True,
            unresolved_retention_complete=True,
            source_evidence_identities=base.source_evidence_identities,
        )


def test_wc2_cohort_is_live_untouched_forward_only() -> None:
    evidence = _eligible_evidence()

    with pytest.raises(ValueError, match="LIVE_UNTOUCHED_FORWARD"):
        replace(evidence, evidence_class=EvidenceClass.WALK_FORWARD)


def test_wc2_policy_registry_is_append_only_idempotent_and_chronological(
    tmp_path: Path,
) -> None:
    store = WC2PolicyStore(tmp_path / "wc2-policy.sqlite3")
    first = _policy()

    assert store.append(first) is True
    assert store.append(first) is False
    assert store.count() == 1
    assert store.quick_check() is True

    second = build_wc2_untouched_forward_policy(
        preregistered_at_ms=3_000,
        collection_start_ms=4_000,
    )
    assert store.append(second) is True
    assert store.count() == 2

    backdated = build_wc2_untouched_forward_policy(
        preregistered_at_ms=2_500,
        collection_start_ms=3_500,
    )
    with pytest.raises(ValueError, match="after prior policy cohort"):
        store.append(backdated)

    with sqlite3.connect(store.path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "UPDATE wc2_forward_policies "
                "SET collection_start_ms=999999"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM wc2_forward_policies")


def test_wc2_threshold_constants_are_locked() -> None:
    assert WC2_MIN_TOTAL_DECISIVE_N == 300
    assert WC2_MIN_DECISIVE_PER_ASSET == 75
    assert WC2_MIN_QUALIFYING_REGIMES == 3
    assert WC2_MIN_DECISIVE_PER_REGIME == 50
    assert WC2_MIN_CALENDAR_DAYS == 120
