from __future__ import annotations

import pytest
from test_smart_capital_allocator import _candidate

from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.smart_capital_allocator import (
    VaultEligibilityState,
    assess_smart_capital_candidate,
)
from crypto_signal.paper.canonical_vault_eligibility import (
    S11_VAULT_ELIGIBILITY_VERSION,
    promote_vault_eligibility,
)


def _assessment(candidate):
    return assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )


@pytest.mark.parametrize("vault_id", tuple(PaperVaultId))
def test_s11_promotes_exact_allocator_eligibility_for_all_three_vaults(
    vault_id: PaperVaultId,
) -> None:
    candidate = _candidate()
    assessment = _assessment(candidate)

    proof = promote_vault_eligibility(
        candidate,
        assessment,
        vault_id=vault_id,
    )

    envelope = next(item for item in assessment.vaults if item.vault_id is vault_id)
    assert proof.proof_version == S11_VAULT_ELIGIBILITY_VERSION
    assert proof.allocator_assessment_identity == assessment.assessment_identity
    assert proof.allocator_candidate_identity == candidate.candidate_identity
    assert proof.vault_id is vault_id
    assert proof.starting_budget_usdt == envelope.starting_budget_usdt
    assert proof.eligibility_reason_codes == envelope.reason_codes
    assert proof.event_risk_identity == candidate.event_risk.evidence_identity
    assert proof.canonical_paper_execution_eligible is True
    assert proof.cross_vault_borrowing_allowed is False
    assert proof.forced_deployment is False
    assert proof.production_authority is False
    assert proof.real_capital == 0

    if vault_id is PaperVaultId.TACTICAL:
        assert proof.tactical_timeframe == "5m"
        assert proof.tactical_evidence_identity is not None
    else:
        assert proof.tactical_timeframe is None

    if vault_id is PaperVaultId.OPPORTUNITY_RESERVE:
        assert proof.recovery_evidence_identity is not None


def test_s11_refuses_hold_cash_envelope_promotion() -> None:
    candidate = _candidate(event_state=CircuitBreakerState.EVENT_BLOCK)
    assessment = _assessment(candidate)
    assert all(
        item.eligibility_state is VaultEligibilityState.HOLD_CASH
        for item in assessment.vaults
    )

    with pytest.raises(ValueError, match="HOLD_CASH"):
        promote_vault_eligibility(
            candidate,
            assessment,
            vault_id=PaperVaultId.CORE,
        )


def test_s11_refuses_assessment_from_different_candidate() -> None:
    candidate = _candidate()
    other = _candidate(event_state=CircuitBreakerState.CAUTION)
    assessment = _assessment(candidate)

    with pytest.raises(ValueError, match="assessment/candidate identity mismatch"):
        promote_vault_eligibility(
            other,
            assessment,
            vault_id=PaperVaultId.CORE,
        )


def test_s11_tactical_proof_keeps_short_horizon_adapter_timeframe() -> None:
    candidate = _candidate()
    assessment = _assessment(candidate)
    tactical = promote_vault_eligibility(
        candidate,
        assessment,
        vault_id=PaperVaultId.TACTICAL,
    )

    assert tactical.tactical_timeframe in {"1m", "5m"}
    assert tactical.tactical_timeframe == candidate.tactical_microstructure.timeframe
