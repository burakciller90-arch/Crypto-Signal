from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceMatrixResolution,
    build_confluence_family_evidence,
    build_locked_m6_policy,
    evaluate_confluence_matrix,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CIRCUIT_BREAKER_ENGINE_VERSION,
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.autopilot_forward_sizing import (
    build_fp3_sizing_risk_inputs,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.portfolio_risk_v2 import (
    AssetGrossExposure,
    CorrelationCluster,
    PortfolioRiskStatus,
    assess_portfolio_allocation,
    build_portfolio_risk_policy,
    build_portfolio_risk_snapshot,
)
from crypto_signal.paper.position_sizing_intelligence import (
    build_position_sizing_policy,
)

AS_OF = 10_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _portfolio_policy(
    *,
    gross_cap: str = "0.80",
    cash_reserve: str = "0.10",
    new_trade_loss: str = "0.01",
    clusters: tuple[CorrelationCluster, ...] | None = None,
):
    selected = (
        (
            CorrelationCluster(
                cluster_id="CRYPTO_BETA",
                members=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
                max_gross_exposure_fraction=Decimal("0.50"),
            ),
        )
        if clusters is None
        else clusters
    )
    return build_portfolio_risk_policy(
        maximum_gross_exposure_fraction_of_nav=Decimal(gross_cap),
        minimum_cash_reserve_fraction_of_nav=Decimal(cash_reserve),
        maximum_new_trade_loss_fraction_of_nav=Decimal(new_trade_loss),
        clusters=selected,
    )


def _sizing_policy(
    *,
    fixed: str = "0.02",
    max_fraction: str = "0.25",
    max_correlation: str = "0.70",
    max_drawdown: str = "0.20",
    max_volatility: str = "0.25",
    min_liquidity: str = "0.60",
    max_cost_r: str = "0.20",
):
    return build_position_sizing_policy(
        policy_version="position-sizing-research-policy-v1/1",
        fixed_fraction_of_vault=Decimal(fixed),
        maximum_fraction_of_vault=Decimal(max_fraction),
        maximum_absolute_correlation=Decimal(max_correlation),
        maximum_drawdown_fraction=Decimal(max_drawdown),
        maximum_volatility_fraction=Decimal(max_volatility),
        minimum_liquidity_score_0_1=Decimal(min_liquidity),
        maximum_transaction_cost_r=Decimal(max_cost_r),
    )


def _risk(
    *,
    asset: str = "BTCUSDT",
    as_of_ms: int = AS_OF,
    correlation: str = "0.20",
    drawdown: str = "0.05",
    volatility: str = "0.10",
    liquidity: str = "0.90",
    cost_r: str = "0.10",
):
    return build_fp3_sizing_risk_inputs(
        vault_id=PaperVaultId.CORE,
        asset=asset,
        as_of_ms=as_of_ms,
        expected_win_r=Decimal("2.00"),
        expected_loss_r=Decimal("1.00"),
        transaction_cost_r=Decimal(cost_r),
        absolute_correlation_0_1=Decimal(correlation),
        current_drawdown_fraction=Decimal(drawdown),
        volatility_fraction=Decimal(volatility),
        liquidity_score_0_1=Decimal(liquidity),
        source_evidence_identities=tuple(
            sorted(
                {
                    _sha("correlation"),
                    _sha("drawdown"),
                    _sha("liquidity"),
                    _sha("payoff"),
                    _sha("transaction-cost"),
                    _sha("volatility"),
                }
            )
        ),
    )


def _event(
    *,
    base_asset: str = "BTC",
    as_of_ms: int = AS_OF,
    state: CircuitBreakerState = CircuitBreakerState.CLEAR,
) -> CircuitBreakerAnalysis:
    triggers = () if state is CircuitBreakerState.CLEAR else ("fp5-test-trigger",)
    uncertainty = (
        "circuit_breaker_has_no_trade_or_order_authority",
        "circuit_breaker_is_versioned_research_policy_not_universal_law",
    )
    payload = {
        "as_of_ms": as_of_ms,
        "asset": base_asset,
        "engine_version": CIRCUIT_BREAKER_ENGINE_VERSION,
        "event_risk_identity": _sha(f"event-risk-{base_asset}"),
        "market_quality_identity": _sha(f"market-quality-{base_asset}"),
        "news_evidence_identity": _sha(f"news-{base_asset}"),
        "policy_version": "event-policy/fp5-test",
        "real_capital": 0,
        "state": state,
        "triggers": triggers,
        "uncertainty_flags": uncertainty,
    }
    return CircuitBreakerAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CIRCUIT_BREAKER_ENGINE_VERSION,
        policy_version="event-policy/fp5-test",
        asset=base_asset,
        as_of_ms=as_of_ms,
        state=state,
        event_risk_identity=_sha(f"event-risk-{base_asset}"),
        news_evidence_identity=_sha(f"news-{base_asset}"),
        market_quality_identity=_sha(f"market-quality-{base_asset}"),
        triggers=triggers,
        uncertainty_flags=uncertainty,
    )


def _confluence(
    *,
    asset: str = "BTCUSDT",
    as_of_ms: int = AS_OF,
    resolution: ConfluenceMatrixResolution = ConfluenceMatrixResolution.MEASURED,
):
    evidence = []
    ordered = tuple(sorted(ConfluenceFamily, key=lambda item: item.value))
    for index, family in enumerate(ordered):
        state = MetaEvidenceState.OBSERVED
        direction = MetaDirection.BULLISH
        strength = Decimal(1)
        quality = Decimal("0.90")
        freshness = Decimal("0.95")
        available_at = as_of_ms - 100
        observed_at = as_of_ms - 50
        source_ids = (_sha(f"{asset}-{family.value}-source"),)
        engines = (f"{family.value}-fp5-test",)
        flags: tuple[str, ...] = ()
        if resolution is ConfluenceMatrixResolution.PARTIAL and index == len(ordered) - 1:
            state = MetaEvidenceState.NO_EVIDENCE
            direction = None
            strength = None
            quality = None
            freshness = None
            available_at = None
            observed_at = None
            source_ids = ()
            engines = ()
            flags = ("family_evidence_unavailable",)
        evidence.append(
            build_confluence_family_evidence(
                family=family,
                asset=asset,
                timeframe="4h",
                regime="trend_up",
                as_of_ms=as_of_ms,
                state=state,
                direction=direction,
                directional_strength_0_1=strength,
                evidence_quality_0_1=quality,
                freshness_0_1=freshness,
                market_available_at_ms=available_at,
                observed_at_ms=observed_at,
                source_engine_ids=engines,
                source_evidence_identities=source_ids,
                uncertainty_flags=flags,
            )
        )
    conflicts = (
        (_sha("fp5-material-conflict"),)
        if resolution is ConfluenceMatrixResolution.CONFLICT
        else ()
    )
    snapshot = evaluate_confluence_matrix(
        build_locked_m6_policy(),
        tuple(evidence),
        candidate_direction=MetaDirection.BULLISH,
        external_material_conflict_identities=conflicts,
    )
    assert snapshot.resolution is resolution
    return snapshot


def _snapshot(
    *,
    policy=None,
    cash: str = "1000",
    nav: str = "1000",
    exposures: tuple[AssetGrossExposure, ...] = (),
    as_of_ms: int = AS_OF,
):
    selected_policy = _portfolio_policy() if policy is None else policy
    return build_portfolio_risk_snapshot(
        policy=selected_policy,
        source_portfolio_identity=_sha(
            f"portfolio-{cash}-{nav}-{as_of_ms}-{exposures}"
        ),
        as_of_ms=as_of_ms,
        cash_usdt=Decimal(cash),
        nav_usdt=Decimal(nav),
        asset_exposures=exposures,
    )


def _assess(
    *,
    portfolio_policy=None,
    sizing_policy=None,
    snapshot=None,
    risk=None,
    event=None,
    confluence=None,
    base_asset: str = "BTC",
    stop: str = "0.05",
):
    pp = _portfolio_policy() if portfolio_policy is None else portfolio_policy
    sp = _sizing_policy() if sizing_policy is None else sizing_policy
    ri = _risk() if risk is None else risk
    ev = _event(base_asset=base_asset, as_of_ms=ri.as_of_ms) if event is None else event
    cf = (
        _confluence(asset=ri.asset, as_of_ms=ri.as_of_ms)
        if confluence is None
        else confluence
    )
    ps = _snapshot(policy=pp, as_of_ms=ri.as_of_ms) if snapshot is None else snapshot
    return assess_portfolio_allocation(
        policy=pp,
        sizing_policy=sp,
        snapshot=ps,
        risk_inputs=ri,
        event_context=ev,
        confluence=cf,
        base_asset=base_asset,
        stop_invalidation_fraction=Decimal(stop),
    )


def test_genuine_100_percent_cash_portfolio_is_valid_and_deployable() -> None:
    policy = _portfolio_policy()
    snapshot = _snapshot(policy=policy, cash="1000", nav="1000", exposures=())

    assessment = _assess(portfolio_policy=policy, snapshot=snapshot)

    assert assessment.status is PortfolioRiskStatus.DEPLOYABLE
    assert snapshot.current_gross_exposure_usdt == Decimal(0)
    assert snapshot.cash_usdt == snapshot.nav_usdt == Decimal(1000)
    assert assessment.baseline_fixed_fractional_notional_usdt == Decimal(20)
    assert assessment.portfolio_headroom_usdt == Decimal(800)
    assert assessment.cluster_headroom_usdt == Decimal(500)
    assert assessment.cash_headroom_usdt == Decimal(900)
    assert assessment.max_deployable_notional_usdt == Decimal(20)
    assert assessment.reason_codes == ()
    assert assessment.kelly_enabled is False
    assert assessment.leverage_allowed is False
    assert assessment.borrowing_allowed is False
    assert assessment.forced_deployment is False


def test_cash_only_portfolio_can_hold_100_percent_cash_without_failure() -> None:
    policy = _portfolio_policy()
    snapshot = _snapshot(policy=policy, cash="1000", nav="1000", exposures=())
    event = _event(state=CircuitBreakerState.CAUTION)

    assessment = _assess(
        portfolio_policy=policy,
        snapshot=snapshot,
        event=event,
    )

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert assessment.reason_codes == ("event_risk_gate",)
    assert snapshot.cash_usdt == snapshot.nav_usdt


def test_existing_btc_exposure_constrains_eth_in_same_cluster() -> None:
    policy = _portfolio_policy()
    snapshot = _snapshot(
        policy=policy,
        cash="550",
        nav="1000",
        exposures=(AssetGrossExposure("BTCUSDT", Decimal(450)),),
    )
    sizing = _sizing_policy(fixed="0.20")
    risk = _risk(asset="ETHUSDT")
    confluence = _confluence(asset="ETHUSDT")

    assessment = _assess(
        portfolio_policy=policy,
        sizing_policy=sizing,
        snapshot=snapshot,
        risk=risk,
        confluence=confluence,
        base_asset="ETH",
        event=_event(base_asset="ETH"),
    )

    assert assessment.status is PortfolioRiskStatus.DEPLOYABLE
    assert assessment.current_gross_exposure_usdt == Decimal(450)
    assert assessment.current_cluster_exposure_usdt == Decimal(450)
    assert assessment.portfolio_headroom_usdt == Decimal(350)
    assert assessment.cluster_headroom_usdt == Decimal(50)
    assert assessment.cash_headroom_usdt == Decimal(450)
    assert assessment.max_deployable_notional_usdt == Decimal(50)


def test_exhausted_cluster_cap_holds_cash() -> None:
    policy = _portfolio_policy()
    snapshot = _snapshot(
        policy=policy,
        cash="500",
        nav="1000",
        exposures=(AssetGrossExposure("BTCUSDT", Decimal(500)),),
    )
    risk = _risk(asset="ETHUSDT")

    assessment = _assess(
        portfolio_policy=policy,
        snapshot=snapshot,
        risk=risk,
        confluence=_confluence(asset="ETHUSDT"),
        base_asset="ETH",
        event=_event(base_asset="ETH"),
    )

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.cluster_headroom_usdt == Decimal(0)
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert "cluster_gross_cap" in assessment.reason_codes


def test_unclassified_existing_exposure_is_not_proven() -> None:
    policy = _portfolio_policy()
    snapshot = _snapshot(
        policy=policy,
        cash="900",
        nav="1000",
        exposures=(AssetGrossExposure("AVAXUSDT", Decimal(100)),),
    )

    assessment = _assess(portfolio_policy=policy, snapshot=snapshot)

    assert snapshot.unclassified_assets == ("AVAXUSDT",)
    assert snapshot.unclassified_exposure_usdt == Decimal(100)
    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert "portfolio_cluster_coverage_not_proven" in assessment.reason_codes


def test_candidate_without_cluster_is_not_proven() -> None:
    policy = _portfolio_policy()
    risk = _risk(asset="AVAXUSDT")

    assessment = _assess(
        portfolio_policy=policy,
        snapshot=_snapshot(policy=policy),
        risk=risk,
        event=_event(base_asset="AVAX"),
        confluence=_confluence(asset="AVAXUSDT"),
        base_asset="AVAX",
    )

    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert assessment.reason_codes == ("candidate_cluster_not_proven",)


def test_policy_rejects_overlapping_cluster_membership() -> None:
    clusters = (
        CorrelationCluster(
            cluster_id="ALT_BETA",
            members=("ETHUSDT", "SOLUSDT"),
            max_gross_exposure_fraction=Decimal("0.30"),
        ),
        CorrelationCluster(
            cluster_id="CRYPTO_BETA",
            members=("BTCUSDT", "ETHUSDT"),
            max_gross_exposure_fraction=Decimal("0.50"),
        ),
    )

    with pytest.raises(ValueError, match="multiple correlation clusters"):
        _portfolio_policy(clusters=clusters)


@pytest.mark.parametrize(
    ("risk_kwargs", "reason"),
    [
        ({"correlation": "0.80"}, "correlation_limit_breached"),
        ({"drawdown": "0.21"}, "drawdown_limit_breached"),
        ({"volatility": "0.30"}, "volatility_limit_breached"),
        ({"liquidity": "0.50"}, "liquidity_floor_breached"),
        ({"cost_r": "0.25"}, "transaction_cost_limit_breached"),
    ],
)
def test_existing_fp3_sizing_risk_gates_fail_closed(
    risk_kwargs,
    reason: str,
) -> None:
    risk = _risk(**risk_kwargs)

    assessment = _assess(risk=risk)

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert reason in assessment.reason_codes


def test_event_risk_non_clear_fails_closed_with_bound_identity() -> None:
    event = _event(state=CircuitBreakerState.EVENT_BLOCK)

    assessment = _assess(event=event)

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.event_risk_identity == event.evidence_identity
    assert "event_risk_gate" in assessment.reason_codes


def test_confluence_conflict_fails_closed_with_bound_identity() -> None:
    confluence = _confluence(resolution=ConfluenceMatrixResolution.CONFLICT)

    assessment = _assess(confluence=confluence)

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert assessment.confluence_identity == confluence.snapshot_identity
    assert "conflict_gate" in assessment.reason_codes


def test_non_measured_confluence_fails_closed() -> None:
    confluence = _confluence(resolution=ConfluenceMatrixResolution.PARTIAL)

    assessment = _assess(confluence=confluence)

    assert assessment.status is PortfolioRiskStatus.HOLD_CASH
    assert "confluence_not_measured" in assessment.reason_codes


def test_missing_portfolio_snapshot_is_not_proven() -> None:
    policy = _portfolio_policy()
    risk = _risk()

    assessment = assess_portfolio_allocation(
        policy=policy,
        sizing_policy=_sizing_policy(),
        snapshot=None,
        risk_inputs=risk,
        event_context=_event(),
        confluence=_confluence(),
        base_asset="BTC",
        stop_invalidation_fraction=Decimal("0.05"),
    )

    assert assessment.status is PortfolioRiskStatus.NOT_PROVEN
    assert assessment.snapshot_identity is None
    assert assessment.source_portfolio_identity is None
    assert assessment.max_deployable_notional_usdt == Decimal(0)
    assert assessment.reason_codes == ("portfolio_snapshot_not_proven",)


def test_cash_plus_gross_exposure_must_reconcile_to_nav() -> None:
    policy = _portfolio_policy()

    with pytest.raises(ValueError, match="cash plus gross exposure"):
        _snapshot(
            policy=policy,
            cash="900",
            nav="1000",
            exposures=(AssetGrossExposure("BTCUSDT", Decimal(50)),),
        )


def test_transaction_cost_r_reduces_risk_limited_capacity() -> None:
    policy = _portfolio_policy(new_trade_loss="0.01")
    low = _assess(
        portfolio_policy=policy,
        risk=_risk(cost_r="0"),
    )
    high = _assess(
        portfolio_policy=policy,
        risk=_risk(cost_r="0.20"),
    )

    assert low.risk_limited_notional_usdt == Decimal(200)
    assert high.risk_limited_notional_usdt == (
        Decimal(10) / Decimal("0.060")
    )
    assert high.risk_limited_notional_usdt < low.risk_limited_notional_usdt


def test_exact_replay_identity_is_stable() -> None:
    policy = _portfolio_policy()
    snapshot = _snapshot(
        policy=policy,
        cash="700",
        nav="1000",
        exposures=(AssetGrossExposure("BTCUSDT", Decimal(300)),),
    )

    first = _assess(portfolio_policy=policy, snapshot=snapshot)
    replay = _assess(portfolio_policy=policy, snapshot=snapshot)

    assert replay == first
    assert replay.assessment_identity == first.assessment_identity


def test_mismatched_asof_or_market_lineage_is_rejected() -> None:
    risk = _risk()

    with pytest.raises(ValueError, match="Event Risk/risk-input as-of"):
        _assess(
            risk=risk,
            event=_event(as_of_ms=AS_OF - 1),
        )

    with pytest.raises(ValueError, match="Confluence/risk-input market"):
        _assess(
            risk=risk,
            confluence=_confluence(asset="ETHUSDT"),
        )


def test_kelly_leverage_borrowing_and_forced_deployment_remain_disabled() -> None:
    policy = _portfolio_policy()
    assessment = _assess(portfolio_policy=policy)

    with pytest.raises(ValueError, match="forbids Kelly"):
        replace(policy, kelly_enabled=True)
    with pytest.raises(ValueError, match="forbids Kelly"):
        replace(assessment, leverage_allowed=True)

    assert assessment.kelly_enabled is False
    assert assessment.leverage_allowed is False
    assert assessment.borrowing_allowed is False
    assert assessment.forced_deployment is False
    assert assessment.production_authority is False
    assert assessment.real_capital == 0
