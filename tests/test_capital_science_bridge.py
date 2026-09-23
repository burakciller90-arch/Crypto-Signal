from __future__ import annotations

import pytest
from test_immutable_forecast_stream import _event_context
from test_smart_capital_allocator import _recovery, _tactical
from test_unified_decision_runtime import _issue

from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.paper.capital_science_bridge import assess_unified_decision_capital
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.smart_capital_allocator import VaultEligibilityState


def _vaults(result):
    return {item.vault_id: item for item in result.allocation.vaults}


def test_unified_market_decision_binds_base_asset_event_risk_to_core_capital(
    tmp_path,
) -> None:
    _, issuance = _issue(tmp_path)
    event = _event_context()

    result = assess_unified_decision_capital(
        issuance,
        event_context=event,
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 1,
    )
    vaults = _vaults(result)

    assert result.forecast_identity == issuance.forecast.forecast_identity
    assert result.proof_identity == issuance.proof.proof_identity
    assert result.confluence_identity == issuance.confluence.snapshot_identity
    assert result.event_risk_identity == event.evidence_identity
    assert result.candidate.asset == "BTCUSDT"
    assert result.candidate.event_risk.asset == "BTC"
    assert result.candidate.confluence == issuance.confluence
    assert result.candidate.source_evidence_identities == tuple(
        sorted(
            (
                event.evidence_identity,
                issuance.confluence.snapshot_identity,
            )
        )
    )
    assert (
        vaults[PaperVaultId.CORE].eligibility_state
        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
    )
    assert (
        vaults[PaperVaultId.TACTICAL].eligibility_state
        is VaultEligibilityState.HOLD_CASH
    )
    assert (
        vaults[PaperVaultId.OPPORTUNITY_RESERVE].eligibility_state
        is VaultEligibilityState.HOLD_CASH
    )
    assert "tactical_microstructure_unavailable" in (
        vaults[PaperVaultId.TACTICAL].reason_codes
    )
    assert "recovery_evidence_unavailable" in (
        vaults[PaperVaultId.OPPORTUNITY_RESERVE].reason_codes
    )
    assert result.allocation.automatic_sizing_authority is False
    assert result.allocation.automatic_trade_authority is False
    assert result.production_authority is False
    assert result.real_capital == 0


def test_explicit_tactical_and_recovery_evidence_can_open_research_envelopes(
    tmp_path,
) -> None:
    _, issuance = _issue(tmp_path)
    result = assess_unified_decision_capital(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 1,
        tactical_microstructure=_tactical(),
        opportunity_recovery=_recovery(),
    )
    assert all(
        item.eligibility_state
        is VaultEligibilityState.ELIGIBLE_RESEARCH_ENVELOPE
        for item in result.allocation.vaults
    )
    assert all(
        item.sizing_required_before_any_trade
        for item in result.allocation.vaults
    )
    assert all(item.recommended_notional_usdt is None for item in result.allocation.vaults)


@pytest.mark.parametrize(
    "state",
    (
        CircuitBreakerState.CAUTION,
        CircuitBreakerState.EVENT_BLOCK,
        CircuitBreakerState.DEGRADED_DATA,
        CircuitBreakerState.ABSTAIN,
    ),
)
def test_non_clear_exact_event_risk_still_forces_every_vault_to_cash(
    tmp_path,
    state,
) -> None:
    _, issuance = _issue(tmp_path, event_state=state)
    result = assess_unified_decision_capital(
        issuance,
        event_context=_event_context(state=state),
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 1,
        tactical_microstructure=_tactical(),
        opportunity_recovery=_recovery(),
    )
    assert all(
        item.eligibility_state is VaultEligibilityState.HOLD_CASH
        for item in result.allocation.vaults
    )
    assert all(
        f"event_risk_not_clear:{state.value}" in item.reason_codes
        for item in result.allocation.vaults
    )


def test_bridge_rejects_wrong_base_asset_without_relabeling_event_evidence(
    tmp_path,
) -> None:
    _, issuance = _issue(tmp_path)
    with pytest.raises(ValueError, match="Event Risk/base asset mismatch"):
        assess_unified_decision_capital(
            issuance,
            event_context=_event_context(),
            base_asset="ETH",
            assessed_at_ms=issuance.forecast.issued_at_ms + 1,
        )


def test_bridge_rejects_event_context_not_bound_into_decision_proof(
    tmp_path,
) -> None:
    _, issuance = _issue(tmp_path)
    wrong_event = _event_context(asset="BTCUSDT")
    with pytest.raises(ValueError, match="Event Risk/base asset mismatch"):
        assess_unified_decision_capital(
            issuance,
            event_context=wrong_event,
            base_asset="BTC",
            assessed_at_ms=issuance.forecast.issued_at_ms + 1,
        )


def test_bridge_never_selects_sizing_or_trade_authority(
    tmp_path,
) -> None:
    _, issuance = _issue(tmp_path)
    result = assess_unified_decision_capital(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 1,
    )
    assert result.automatic_sizing_authority is False
    assert result.automatic_trade_authority is False
    assert result.allocation.automatic_sizing_authority is False
    assert result.allocation.automatic_trade_authority is False
    assert result.allocation.production_authority is False
    assert result.production_authority is False
    assert result.real_capital == 0
