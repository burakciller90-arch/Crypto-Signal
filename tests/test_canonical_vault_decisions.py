from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_smart_capital_allocator import AS_OF, _candidate, _tactical
from test_transaction_tape_atomic import _initial_state

from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.paper.canonical_vault_decisions import (
    CanonicalVaultDecisionDisposition,
    CanonicalVaultDecisionLedger,
    build_vault_decision,
    commit_canonical_hold,
)
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.smart_capital_allocator import assess_smart_capital_candidate
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape


def _assessment(candidate):
    return assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )


@pytest.mark.parametrize("vault_id", tuple(PaperVaultId))
def test_s11_persists_eligible_allocator_decision_without_accounting_mutation(
    tmp_path: Path,
    vault_id: PaperVaultId,
) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    candidate = _candidate()
    assessment = _assessment(candidate)
    decision = build_vault_decision(
        before.activation,
        candidate,
        assessment,
        vault_id=vault_id,
        decided_at_ms=AS_OF + 10,
    )

    assert decision.disposition is CanonicalVaultDecisionDisposition.ELIGIBLE
    ledger = CanonicalVaultDecisionLedger(epoch2_path)
    assert ledger.append(decision) is True
    assert ledger.append(decision) is False

    stored = ledger.read(decision.decision_identity)
    assert stored is not None
    assert stored["vault_id"] == vault_id.value
    assert stored["disposition"] == "eligible"
    assert stored["allocator_assessment_identity"] == assessment.assessment_identity
    assert stored["real_capital"] == 0
    assert Epoch2CanonicalLedger(epoch2_path).read_state() == before


def test_s11_event_risk_block_commits_r22_hold_without_mutating_nav(
    tmp_path: Path,
) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    candidate = _candidate(event_state=CircuitBreakerState.EVENT_BLOCK)
    assessment = _assessment(candidate)
    decision = build_vault_decision(
        before.activation,
        candidate,
        assessment,
        vault_id=PaperVaultId.CORE,
        decided_at_ms=AS_OF + 10,
    )
    assert decision.disposition is CanonicalVaultDecisionDisposition.BLOCKED

    committed = commit_canonical_hold(
        epoch2_path=epoch2_path,
        decision=decision,
    )

    assert committed.disposition is CanonicalVaultDecisionDisposition.BLOCKED
    assert committed.decision_inserted is True
    assert committed.intent_inserted is True
    assert committed.real_capital == 0
    assert Epoch2CanonicalLedger(epoch2_path).read_state() == before

    intent_count, fill_count, bundle_count = (
        R22Epoch2AtomicTape(epoch2_path).audit_all_read_only()
    )
    assert (intent_count, fill_count, bundle_count) == (1, 0, 0)


def test_s11_missing_tactical_confirmation_is_hold_not_execution(
    tmp_path: Path,
) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    candidate = _candidate(tactical=_tactical(complete=False))
    assessment = _assessment(candidate)
    decision = build_vault_decision(
        before.activation,
        candidate,
        assessment,
        vault_id=PaperVaultId.TACTICAL,
        decided_at_ms=AS_OF + 10,
    )

    assert decision.disposition is CanonicalVaultDecisionDisposition.HOLD
    assert any("unavailable" in code or "incomplete" in code for code in decision.reason_codes)
    committed = commit_canonical_hold(
        epoch2_path=epoch2_path,
        decision=decision,
    )
    assert committed.intent_inserted is True
    assert Epoch2CanonicalLedger(epoch2_path).read_state() == before


def test_s11_vault_decision_rows_are_physically_immutable(tmp_path: Path) -> None:
    epoch2_path, before = _initial_state(tmp_path)
    candidate = _candidate(event_state=CircuitBreakerState.CAUTION)
    assessment = _assessment(candidate)
    decision = build_vault_decision(
        before.activation,
        candidate,
        assessment,
        vault_id=PaperVaultId.OPPORTUNITY_RESERVE,
        decided_at_ms=AS_OF + 10,
    )
    CanonicalVaultDecisionLedger(epoch2_path).append(decision)

    with (
        sqlite3.connect(epoch2_path) as connection,
        pytest.raises(sqlite3.DatabaseError, match="immutable S11 vault decision ledger"),
    ):
        connection.execute(
            "UPDATE s11_vault_decisions SET disposition = 'eligible'"
        )
