from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.paper.portfolio_risk_v2 import (
    AssetGrossExposure,
    CorrelationCluster,
    PortfolioRiskStatus,
    assess_portfolio_allocation,
    build_portfolio_risk_snapshot,
)

SOURCES = ("a" * 64, "b" * 64)


def _clusters(
    *,
    crypto_cap: str = "0.50",
) -> tuple[CorrelationCluster, ...]:
    return (
        CorrelationCluster(
            cluster_id="CRYPTO_BETA",
            members=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
            max_gross_exposure_fraction=Decimal(crypto_cap),
        ),
    )


def _snapshot(
    *,
    cash: str = "1000",
    nav: str = "1000",
    drawdown: str = "0.05",
    exposures: tuple[AssetGrossExposure, ...] = (),
    clusters: tuple[CorrelationCluster, ...] | None = None,
    portfolio_cap: str = "0.80",
    cash_reserve: str = "0.10",
    max_drawdown: str = "0.20",
    fixed_risk: str = "0.01",
):
    return build_portfolio_risk_snapshot(
        as_of_ms=10_000,
        cash_usdt=Decimal(cash),
        nav_usdt=Decimal(nav),
        current_drawdown_fraction=Decimal(drawdown),
        asset_exposures=exposures,
        clusters=_clusters() if clusters is None else clusters,
        portfolio_max_gross_exposure_fraction=Decimal(portfolio_cap),
        minimum_cash_reserve_fraction=Decimal(cash_reserve),
        maximum_drawdown_fraction=Decimal(max_drawdown),
        fixed_fractional_risk_fraction=Decimal(fixed_risk),
        source_evidence_identities=SOURCES,
    )


def _assess(
    snapshot=None,
    *,
    asset: str = "BTCUSDT",
    cost: str = "0.001",
    stop: str = "0.05",
    event: bool = True,
    liquidity: bool = True,
    conflict: bool = True,
):
    return assess_portfolio_allocation(
        snapshot=_snapshot() if snapshot is None else snapshot,
        candidate_asset=asset,
        transaction_cost_fraction=Decimal(cost),
        stop_invalidation_fraction=Decimal(stop),
        event_risk_clear=event,
        liquidity_eligible=liquidity,
        conflict_clear=conflict,
    )


def test_cash_only_eligible_portfolio_can_deploy_without_forced_underuse() -> None:
    assessment = _assess(_snapshot())

    assert assessment.status is PortfolioRiskStatus.DEPLOYABLE
    assert assessment.current_gross_exposure_usdt == Decimal(0)
    assert assessment.current_cluster_exposure_usdt == Decimal(0)
    assert assessment.portfolio_headroom_usdt == Decimal(800)
    assert assessment.cluster_headroom_usdt == Decimal(500)
    assert assessment.cash_headroom_usdt == Decimal(900)
    assert assessment.fixed_fractional_risk_budget_usdt == Decimal(10)
    assert assessment.risk_limited_notional_usdt == Decimal(10) / Decimal("0.051")
    assert assessment.max_deployable_notional_usdt == (
        Decimal(10) / Decimal("0.051")
    )
    assert assessment.reason_codes == ()
    assert assessment.kelly_enabled is False
    assert assessment.leverage_allowed is False
    assert assessment.borrowing_allowed is False
    assert assessment.forced_deployment is False


def test_existing_btc_exposure_constrains_eth_in_same_crypto_beta_cluster() -> None:
    snapshot = _snapshot(
        cash="550",
        exposures=(
            AssetGrossExposure(
                asset="BTCUSDT",
                gross_exposure_usdt=Decimal(450),
            ),
        ),
    )

    assessment = _assess(snapshot, asset="ETHUSDT")

    assert assessment.status is PortfolioRiskStatus.DEPLOYABLE
    assert assessment.current_gross_exposure_usdt == Decimal(450)
    assert assessment.current_cluster_exposure_usdt == Decimal(450)
    assert assessment.portfolio_headroom_usdt == Decimal(350)
    assert assessment.cluster_headroom_usdt == Decimal(50)
    assert assessment.cash_headroom_usdt == Decimal(450)
    assert assessment.max_deployable_notional_usdt == Decimal(50)


def test_exhausted_cluster_cap_holds_cash_even_when_portfolio_has_headroom() -> None:
    snapshot = _snapshot(
        cash="500",
        exposures=(
            AssetGrossExposure(
                asset="BTCUSDT",
                gross_exposure_usdt=Decimal(500),
            ),
        ),
    )

    assessment = _assess(snapshot, asset="ETHUSDT")

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.portfolio_headroom_usdt == Decimal(300)
    assert assessment.cluster_headroom_usdt == Decimal(0)
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert "cluster_gross_cap" in assessment.reason_codes


def test_drawdown_gate_fails_closed() -> None:
    assessment = _assess(_snapshot(drawdown="0.21"))

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert "drawdown_gate" in assessment.reason_codes


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"event": False}, "event_risk_gate"),
        ({"liquidity": False}, "liquidity_gate"),
        ({"conflict": False}, "conflict_gate"),
    ],
)
def test_evidence_gates_fail_closed(kwargs, reason: str) -> None:
    assessment = _assess(_snapshot(), **kwargs)

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert reason in assessment.reason_codes


def test_cash_reserve_gate_can_hold_100_percent_cash_without_failure() -> None:
    snapshot = _snapshot(cash="100", nav="1000")

    assessment = _assess(snapshot)

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.current_gross_exposure_usdt == Decimal(0)
    assert assessment.cash_headroom_usdt == Decimal(0)
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert "cash_reserve_gate" in assessment.reason_codes


def test_missing_portfolio_snapshot_is_not_proven() -> None:
    assessment = assess_portfolio_allocation(
        snapshot=None,
        candidate_asset="BTCUSDT",
        transaction_cost_fraction=Decimal("0.001"),
        stop_invalidation_fraction=Decimal("0.05"),
        event_risk_clear=True,
        liquidity_eligible=True,
        conflict_clear=True,
    )

    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN
    assert assessment.snapshot_identity is None
    assert assessment.candidate_cluster_id is None
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert assessment.reason_codes == ("portfolio_snapshot_not_proven",)


def test_unknown_candidate_cluster_is_not_proven() -> None:
    assessment = _assess(_snapshot(), asset="AVAXUSDT")

    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert assessment.reason_codes == ("candidate_cluster_not_proven",)


def test_overlapping_candidate_clusters_are_not_proven() -> None:
    clusters = (
        CorrelationCluster(
            cluster_id="ALT_BETA",
            members=("ETHUSDT", "SOLUSDT"),
            max_gross_exposure_fraction=Decimal("0.30"),
        ),
        CorrelationCluster(
            cluster_id="CRYPTO_BETA",
            members=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
            max_gross_exposure_fraction=Decimal("0.50"),
        ),
    )
    assessment = _assess(
        _snapshot(clusters=clusters),
        asset="ETHUSDT",
    )

    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN
    assert assessment.reason_codes == ("candidate_cluster_not_proven",)


def test_transaction_cost_reduces_risk_limited_notional() -> None:
    snapshot = _snapshot()
    no_cost = _assess(snapshot, cost="0")
    with_cost = _assess(snapshot, cost="0.01")

    assert no_cost.risk_limited_notional_usdt == Decimal(200)
    assert with_cost.risk_limited_notional_usdt == (
        Decimal(10) / Decimal("0.06")
    )
    assert (
        with_cost.max_deployable_notional_usdt
        < no_cost.max_deployable_notional_usdt
    )


def test_exact_replay_identity_is_stable() -> None:
    snapshot = _snapshot(
        cash="700",
        exposures=(
            AssetGrossExposure(
                asset="BTCUSDT",
                gross_exposure_usdt=Decimal(300),
            ),
        ),
    )

    first = _assess(snapshot, asset="SOLUSDT")
    replay = _assess(snapshot, asset="SOLUSDT")

    assert replay == first
    assert replay.assessment_identity == first.assessment_identity
    assert snapshot.snapshot_identity == _snapshot(
        cash="700",
        exposures=(
            AssetGrossExposure(
                asset="BTCUSDT",
                gross_exposure_usdt=Decimal(300),
            ),
        ),
    ).snapshot_identity


def test_snapshot_requires_sorted_unique_asset_exposures() -> None:
    with pytest.raises(ValueError, match="sorted unique"):
        _snapshot(
            exposures=(
                AssetGrossExposure("ETHUSDT", Decimal(10)),
                AssetGrossExposure("BTCUSDT", Decimal(10)),
            )
        )


def test_combined_stop_and_cost_fraction_cannot_exceed_one() -> None:
    with pytest.raises(ValueError, match="combined stop"):
        _assess(_snapshot(), cost="0.60", stop="0.50")
