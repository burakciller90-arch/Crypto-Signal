from __future__ import annotations

import inspect
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
from crypto_signal.paper import smart_capital_allocator
from crypto_signal.paper.epochs import EPOCH_2_SPEC, PaperVaultId
from crypto_signal.paper.smart_capital_allocator import (
    SMART_CAPITAL_ALLOCATOR_ENGINE_VERSION,
    SMART_CAPITAL_POLICY_VERSION,
    VaultEligibilityState,
    VaultMetricsStatus,
    assess_smart_capital_candidate,
    build_opportunity_recovery_evidence,
    build_smart_capital_candidate,
    build_tactical_microstructure_evidence,
)

AS_OF = 1_000_000


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _event(state: CircuitBreakerState = CircuitBreakerState.CLEAR):
    triggers = () if state is CircuitBreakerState.CLEAR else (f"state:{state.value}",)
    uncertainty = ("research_policy_only",)
    payload = {
        "as_of_ms": AS_OF,
        "asset": "BTCUSDT",
        "engine_version": CIRCUIT_BREAKER_ENGINE_VERSION,
        "event_risk_identity": _sha("event-risk"),
        "market_quality_identity": _sha("market-quality"),
        "news_evidence_identity": _sha("news"),
        "policy_version": "test-circuit/1",
        "real_capital": 0,
        "state": state,
        "triggers": triggers,
        "uncertainty_flags": uncertainty,
    }
    return CircuitBreakerAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CIRCUIT_BREAKER_ENGINE_VERSION,
        policy_version="test-circuit/1",
        asset="BTCUSDT",
        as_of_ms=AS_OF,
        state=state,
        event_risk_identity=_sha("event-risk"),
        news_evidence_identity=_sha("news"),
        market_quality_identity=_sha("market-quality"),
        triggers=triggers,
        uncertainty_flags=uncertainty,
        real_capital=0,
    )


def _confluence(
    *,
    opposing_family: ConfluenceFamily | None = None,
    conflict_family: ConfluenceFamily | None = None,
    missing_family: ConfluenceFamily | None = None,
):
    evidence = []
    for family in sorted(ConfluenceFamily, key=lambda item: item.value):
        if family is missing_family:
            evidence.append(
                build_confluence_family_evidence(
                    family=family,
                    asset="BTCUSDT",
                    timeframe="4h",
                    regime="trend_up",
                    as_of_ms=AS_OF,
                    state=MetaEvidenceState.NO_EVIDENCE,
                    direction=None,
                    directional_strength_0_1=None,
                    evidence_quality_0_1=None,
                    freshness_0_1=None,
                    market_available_at_ms=None,
                    observed_at_ms=None,
                    uncertainty_flags=("missing",),
                )
            )
            continue
        direction = (
            MetaDirection.BEARISH
            if family is opposing_family
            else MetaDirection.BULLISH
        )
        conflicts = (
            (_sha(f"conflict-{family.value}"),)
            if family is conflict_family
            else ()
        )
        evidence.append(
            build_confluence_family_evidence(
                family=family,
                asset="BTCUSDT",
                timeframe="4h",
                regime="trend_up",
                as_of_ms=AS_OF,
                state=MetaEvidenceState.OBSERVED,
                direction=direction,
                directional_strength_0_1=Decimal(1),
                evidence_quality_0_1=Decimal("0.90"),
                freshness_0_1=Decimal("0.95"),
                market_available_at_ms=AS_OF - 100,
                observed_at_ms=AS_OF - 50,
                source_engine_ids=(f"{family.value}-engine",),
                source_evidence_identities=(_sha(f"{family.value}-source"),),
                material_conflict_identities=conflicts,
                uncertainty_flags=(),
            )
        )
    return evaluate_confluence_matrix(
        build_locked_m6_policy(),
        tuple(evidence),
        candidate_direction=MetaDirection.BULLISH,
    )


def _tactical(*, complete: bool = True):
    return build_tactical_microstructure_evidence(
        asset="BTCUSDT",
        timeframe="5m",
        as_of_ms=AS_OF,
        liquidity_evidence_identity=_sha("liquidity"),
        order_flow_evidence_identity=_sha("order-flow"),
        market_quality_evidence_identity=_sha("tactical-quality"),
        cvd_available=complete,
        absorption_evidence_available=complete,
        liquidity_sweep_evidence_available=complete,
        evidence_complete=complete,
    )


def _recovery(
    *,
    spread: bool = True,
    liquidity: bool = True,
    price_discovery: bool = True,
    feed: bool = True,
):
    return build_opportunity_recovery_evidence(
        asset="BTCUSDT",
        as_of_ms=AS_OF,
        spread_stabilization_identity=_sha("spread"),
        liquidity_recovery_identity=_sha("liquidity-recovery"),
        price_discovery_identity=_sha("price-discovery"),
        feed_quality_identity=_sha("feed"),
        spread_stabilized=spread,
        liquidity_recovered=liquidity,
        price_discovery_stable=price_discovery,
        feed_quality_healthy=feed,
    )


def _candidate(
    *,
    event_state: CircuitBreakerState = CircuitBreakerState.CLEAR,
    confluence=None,
    tactical=None,
    recovery=None,
):
    return build_smart_capital_candidate(
        asset="BTCUSDT",
        as_of_ms=AS_OF,
        event_risk=_event(event_state),
        confluence=_confluence() if confluence is None else confluence,
        tactical_microstructure=_tactical() if tactical is None else tactical,
        opportunity_recovery=_recovery() if recovery is None else recovery,
    )


def _by_vault(assessment):
    return {item.vault_id: item for item in assessment.vaults}


def test_allocator_reuses_exact_epoch2_600_300_100_contract_without_sizing() -> None:
    candidate = _candidate()
    assessment = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=AS_OF + 1,
    )
    vaults = _by_vault(assessment)

    assert assessment.engine_version == SMART_CAPITAL_ALLOCATOR_ENGINE_VERSION
    assert assessment.policy_version == SMART_CAPITAL_POLICY_VERSION
    assert assessment.epoch_id == EPOCH_2_SPEC.epoch_id
    assert assessment.epoch_identity == EPOCH_2_SPEC.epoch_identity
    assert assessment.consolidated_starting_cash_usdt == Decimal("1000.00")
    assert {
        vault_id: vault.starting_budget_usdt
        for vault_id, vault in vaults.items()
    } == {
        PaperVaultId.CORE: Decimal("600.00"),
        PaperVaultId.TACTICAL: Decimal("300.00"),
        PaperVaultId.OPPORTUNITY_RESERVE: Decimal("100.00"),
    }
    assert all(
        item.eligibility_state
        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
        for item in assessment.vaults
    )
    assert all(item.sizing_required_before_any_trade for item in assessment.vaults)
    assert all(item.recommended_notional_usdt is None for item in assessment.vaults)
    assert assessment.automatic_sizing_authority is False
    assert assessment.automatic_trade_authority is False
    assert assessment.cross_vault_transfer_authority is False
    assert assessment.production_authority is False
    assert assessment.real_capital == 0


def test_pre_activation_allocator_never_invents_vault_nav_pnl_cost_or_turnover() -> None:
    assessment = assess_smart_capital_candidate(
        _candidate(),
        assessed_at_ms=AS_OF + 1,
    )

    assert assessment.current_consolidated_nav_usdt is None
    assert assessment.current_metrics_status is VaultMetricsStatus.NOT_ACTIVATED
    for vault in assessment.vaults:
        assert vault.metrics_status is VaultMetricsStatus.NOT_ACTIVATED
        assert vault.current_cash_usdt is None
        assert vault.current_nav_usdt is None
        assert vault.current_exposure_usdt is None
        assert vault.current_pnl_usdt is None
        assert vault.current_drawdown_fraction is None
        assert vault.current_cost_usdt is None
        assert vault.current_turnover_fraction is None
        assert vault.cross_vault_borrowing_allowed is False
        assert vault.forced_deployment is False


@pytest.mark.parametrize(
    "state",
    (
        CircuitBreakerState.CAUTION,
        CircuitBreakerState.EVENT_BLOCK,
        CircuitBreakerState.DEGRADED_DATA,
        CircuitBreakerState.ABSTAIN,
    ),
)
def test_non_clear_event_risk_forces_all_vaults_to_hold_cash(state) -> None:
    assessment = assess_smart_capital_candidate(
        _candidate(event_state=state),
        assessed_at_ms=AS_OF + 1,
    )

    assert all(
        item.eligibility_state is VaultEligibilityState.HOLD_CASH
        for item in assessment.vaults
    )
    assert all(
        f"event_risk_not_clear:{state.value}" in item.reason_codes
        for item in assessment.vaults
    )
    assert all(not item.sizing_required_before_any_trade for item in assessment.vaults)


def test_core_requires_full_measured_low_conflict_confluence() -> None:
    opposition = assess_smart_capital_candidate(
        _candidate(
            confluence=_confluence(opposing_family=ConfluenceFamily.DERIVATIVES)
        ),
        assessed_at_ms=AS_OF + 1,
    )
    core = _by_vault(opposition)[PaperVaultId.CORE]
    assert core.eligibility_state is VaultEligibilityState.HOLD_CASH
    assert "confluence_has_opposition" in core.reason_codes

    conflict = assess_smart_capital_candidate(
        _candidate(
            confluence=_confluence(conflict_family=ConfluenceFamily.ONCHAIN)
        ),
        assessed_at_ms=AS_OF + 1,
    )
    core = _by_vault(conflict)[PaperVaultId.CORE]
    assert core.eligibility_state is VaultEligibilityState.HOLD_CASH
    assert "confluence_has_material_conflict" in core.reason_codes
    assert (
        f"confluence_not_measured:{ConfluenceMatrixResolution.CONFLICT.value}"
        in core.reason_codes
    )

    partial = assess_smart_capital_candidate(
        _candidate(
            confluence=_confluence(missing_family=ConfluenceFamily.ONCHAIN)
        ),
        assessed_at_ms=AS_OF + 1,
    )
    core = _by_vault(partial)[PaperVaultId.CORE]
    assert core.eligibility_state is VaultEligibilityState.HOLD_CASH
    assert "confluence_not_full_coverage" in core.reason_codes


def test_tactical_requires_complete_short_horizon_microstructure() -> None:
    assessment = assess_smart_capital_candidate(
        _candidate(tactical=_tactical(complete=False)),
        assessed_at_ms=AS_OF + 1,
    )
    tactical = _by_vault(assessment)[PaperVaultId.TACTICAL]

    assert tactical.eligibility_state is VaultEligibilityState.HOLD_CASH
    assert "tactical_evidence_incomplete" in tactical.reason_codes
    assert "cvd_unavailable" in tactical.reason_codes
    assert "absorption_evidence_unavailable" in tactical.reason_codes
    assert "liquidity_sweep_evidence_unavailable" in tactical.reason_codes


def test_opportunity_reserve_never_blindly_buys_without_complete_recovery() -> None:
    assessment = assess_smart_capital_candidate(
        _candidate(recovery=_recovery(liquidity=False)),
        assessed_at_ms=AS_OF + 1,
    )
    reserve = _by_vault(assessment)[PaperVaultId.OPPORTUNITY_RESERVE]

    assert reserve.eligibility_state is VaultEligibilityState.HOLD_CASH
    assert "liquidity_not_recovered" in reserve.reason_codes
    assert reserve.recommended_notional_usdt is None
    assert reserve.forced_deployment is False


def test_vaults_evaluate_independently_without_cross_vault_budget_transfer() -> None:
    assessment = assess_smart_capital_candidate(
        _candidate(
            confluence=_confluence(opposing_family=ConfluenceFamily.DERIVATIVES),
            tactical=_tactical(complete=True),
            recovery=_recovery(liquidity=False),
        ),
        assessed_at_ms=AS_OF + 1,
    )
    vaults = _by_vault(assessment)

    assert vaults[PaperVaultId.CORE].eligibility_state is VaultEligibilityState.HOLD_CASH
    assert (
        vaults[PaperVaultId.TACTICAL].eligibility_state
        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
    )
    assert (
        vaults[PaperVaultId.OPPORTUNITY_RESERVE].eligibility_state
        is VaultEligibilityState.HOLD_CASH
    )
    assert vaults[PaperVaultId.TACTICAL].starting_budget_usdt == Decimal("300.00")
    assert assessment.cross_vault_transfer_authority is False


def test_candidate_context_and_exact_source_lineage_fail_closed() -> None:
    event = _event()
    tactical = _tactical()
    recovery = _recovery()
    confluence = _confluence()

    with pytest.raises(ValueError, match="confluence as_of mismatch"):
        build_smart_capital_candidate(
            asset="BTCUSDT",
            as_of_ms=AS_OF + 1,
            event_risk=replace(
                event,
                as_of_ms=AS_OF + 1,
                evidence_identity=canonical_sha256(
                    {
                        "as_of_ms": AS_OF + 1,
                        "asset": event.asset,
                        "engine_version": event.engine_version,
                        "event_risk_identity": event.event_risk_identity,
                        "market_quality_identity": event.market_quality_identity,
                        "news_evidence_identity": event.news_evidence_identity,
                        "policy_version": event.policy_version,
                        "real_capital": event.real_capital,
                        "state": event.state,
                        "triggers": event.triggers,
                        "uncertainty_flags": event.uncertainty_flags,
                    }
                ),
            ),
            confluence=confluence,
            tactical_microstructure=replace(
                tactical,
                as_of_ms=AS_OF + 1,
                evidence_identity=canonical_sha256(
                    {
                        "absorption_evidence_available": tactical.absorption_evidence_available,
                        "as_of_ms": AS_OF + 1,
                        "asset": tactical.asset,
                        "cvd_available": tactical.cvd_available,
                        "evidence_complete": tactical.evidence_complete,
                        "liquidity_evidence_identity": tactical.liquidity_evidence_identity,
                        "liquidity_sweep_evidence_available": tactical.liquidity_sweep_evidence_available,
                        "market_quality_evidence_identity": tactical.market_quality_evidence_identity,
                        "order_flow_evidence_identity": tactical.order_flow_evidence_identity,
                        "timeframe": tactical.timeframe,
                    }
                ),
            ),
            opportunity_recovery=replace(
                recovery,
                as_of_ms=AS_OF + 1,
                evidence_identity=canonical_sha256(
                    {
                        "as_of_ms": AS_OF + 1,
                        "asset": recovery.asset,
                        "feed_quality_healthy": recovery.feed_quality_healthy,
                        "feed_quality_identity": recovery.feed_quality_identity,
                        "liquidity_recovered": recovery.liquidity_recovered,
                        "liquidity_recovery_identity": recovery.liquidity_recovery_identity,
                        "price_discovery_identity": recovery.price_discovery_identity,
                        "price_discovery_stable": recovery.price_discovery_stable,
                        "spread_stabilization_identity": recovery.spread_stabilization_identity,
                        "spread_stabilized": recovery.spread_stabilized,
                    }
                ),
            ),
        )


def test_allocator_identity_tampering_fails_closed() -> None:
    candidate = _candidate()
    assessment = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=AS_OF + 1,
    )

    with pytest.raises(ValueError, match="capital candidate identity mismatch"):
        replace(candidate, candidate_identity="0" * 64)

    with pytest.raises(ValueError, match="capital assessment identity mismatch"):
        replace(assessment, assessed_at_ms=AS_OF + 2)

    with pytest.raises(ValueError, match="cannot size notional"):
        replace(
            assessment.vaults[0],
            recommended_notional_usdt=Decimal("1.00"),
        )


def test_allocator_surface_has_no_ledger_network_execution_or_sizing_authority() -> None:
    source = inspect.getsource(smart_capital_allocator).lower()
    forbidden = (
        "sqlite3",
        "paperfundledger",
        "append_",
        "write_text",
        "write_bytes",
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "simulate_paper_fill",
        "size_paper_candidate",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert smart_capital_allocator.REAL_CAPITAL == 0
