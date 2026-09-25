from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_smart_capital_allocator import AS_OF, _candidate, _tactical
from test_transaction_tape_atomic import _initial_state

from crypto_signal.intelligence.event_risk_circuit_breaker import CircuitBreakerState
from crypto_signal.paper.canonical_vault_decisions import (
    CanonicalVaultDecisionLedger,
    build_vault_decision,
    commit_canonical_hold,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.smart_capital_allocator import assess_smart_capital_candidate
from crypto_signal.product.intelligence_stream_capital_decisions import (
    IntelligenceStreamCapitalDecisionLedger,
    StreamCapitalDecisionWriteDisposition,
    project_vault_decision_to_stream,
)
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
    StreamLedgerWriteDisposition,
)
from crypto_signal.product.intelligence_stream_models import (
    build_stream_activation_boundary,
)
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
    decode_stream_cursor,
)


def _assessment(candidate):
    return assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )


def _stream(tmp_path: Path) -> Path:
    path = tmp_path / "stream.sqlite3"
    stream = IntelligenceStreamLedger(path)
    activation = build_stream_activation_boundary(activated_at_ms=1000)
    assert stream.append_activation(activation) is StreamLedgerWriteDisposition.INSERTED
    IntelligenceStreamNarrativeLedger(path).initialize()
    return path


def _decision(
    *,
    state,
    candidate,
    vault_id: PaperVaultId,
    decided_at_ms: int,
):
    assessment = _assessment(candidate)
    return build_vault_decision(
        state.activation,
        candidate,
        assessment,
        vault_id=vault_id,
        decided_at_ms=decided_at_ms,
    )


def test_s11_projects_eligible_hold_and_blocked_capital_decisions_into_feed(
    tmp_path: Path,
) -> None:
    epoch2_path, state = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)

    eligible = _decision(
        state=state,
        candidate=_candidate(),
        vault_id=PaperVaultId.CORE,
        decided_at_ms=AS_OF + 10,
    )
    hold = _decision(
        state=state,
        candidate=_candidate(tactical=_tactical(complete=False)),
        vault_id=PaperVaultId.TACTICAL,
        decided_at_ms=AS_OF + 20,
    )
    blocked = _decision(
        state=state,
        candidate=_candidate(event_state=CircuitBreakerState.EVENT_BLOCK),
        vault_id=PaperVaultId.OPPORTUNITY_RESERVE,
        decided_at_ms=AS_OF + 30,
    )

    ledger = CanonicalVaultDecisionLedger(epoch2_path)
    assert ledger.append(eligible) is True
    assert commit_canonical_hold(
        epoch2_path=epoch2_path,
        decision=hold,
    ).intent_inserted is True
    assert commit_canonical_hold(
        epoch2_path=epoch2_path,
        decision=blocked,
    ).intent_inserted is True

    projected = tuple(
        project_vault_decision_to_stream(
            epoch2_path=epoch2_path,
            stream_path=stream_path,
            decision_identity=item.decision_identity,
        )
        for item in (eligible, hold, blocked)
    )
    assert all(
        item.message_disposition is StreamCapitalDecisionWriteDisposition.INSERTED
        for item in projected
    )

    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    assert [item["subtype"] for item in page.items] == [
        "capital_blocked",
        "capital_hold",
        "capital_eligible",
    ]
    assert [item["vault_id"] for item in page.items] == [
        PaperVaultId.OPPORTUNITY_RESERVE.value,
        PaperVaultId.TACTICAL.value,
        PaperVaultId.CORE.value,
    ]
    assert all(item["real_capital"] == 0 for item in page.items)
    assert all(item["production_authority"] is False for item in page.items)
    assert page.newest_cursor is not None
    assert decode_stream_cursor(page.newest_cursor).narrative_identity == (
        projected[-1].narrative_identity
    )


def test_s11_capital_decision_projection_is_idempotent_and_searchable(
    tmp_path: Path,
) -> None:
    epoch2_path, state = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    decision = _decision(
        state=state,
        candidate=_candidate(tactical=_tactical(complete=False)),
        vault_id=PaperVaultId.TACTICAL,
        decided_at_ms=AS_OF + 10,
    )
    commit_canonical_hold(epoch2_path=epoch2_path, decision=decision)

    first = project_vault_decision_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        decision_identity=decision.decision_identity,
    )
    second = project_vault_decision_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        decision_identity=decision.decision_identity,
    )

    assert first.narrative_identity == second.narrative_identity
    assert second.source_event_disposition is StreamLedgerWriteDisposition.UNCHANGED
    assert (
        second.message_disposition
        is StreamCapitalDecisionWriteDisposition.UNCHANGED
    )

    reader = IntelligenceStreamReadModel(stream_path)
    search = reader.read_messages(StreamMessageQuery(limit=20, text="nakitte"))
    assert len(search.items) == 1
    assert search.items[0]["subtype"] == "capital_hold"
    assert search.items[0]["disposition"] == "hold"

    no_stance_fabrication = reader.read_messages(
        StreamMessageQuery(limit=20, effective_stance="bullish")
    )
    assert no_stance_fabrication.items == ()


def test_s11_capital_decision_detail_keeps_exact_allocator_lineage(
    tmp_path: Path,
) -> None:
    epoch2_path, state = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    decision = _decision(
        state=state,
        candidate=_candidate(event_state=CircuitBreakerState.EVENT_BLOCK),
        vault_id=PaperVaultId.CORE,
        decided_at_ms=AS_OF + 10,
    )
    commit_canonical_hold(epoch2_path=epoch2_path, decision=decision)
    projected = project_vault_decision_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        decision_identity=decision.decision_identity,
    )

    reader = IntelligenceStreamReadModel(stream_path)
    message = reader.read_message(projected.narrative_identity)
    assert message is not None
    assert message["decision_identity"] == decision.decision_identity
    assert message["allocator_assessment_identity"] == (
        decision.allocator_assessment_identity
    )
    assert decision.event_risk_identity in message["capital_reference_identities"]

    detail = reader.read_message_detail(projected.narrative_identity)
    assert detail is not None
    assert detail["capital_decision"]["decision_identity"] == (
        decision.decision_identity
    )
    assert "analytical_view" not in detail
    assert "fact_bundle" not in detail
    assert detail["real_capital"] == 0
    assert detail["production_authority"] is False


def test_s11_stream_capital_decision_rows_are_physically_immutable(
    tmp_path: Path,
) -> None:
    epoch2_path, state = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    decision = _decision(
        state=state,
        candidate=_candidate(),
        vault_id=PaperVaultId.CORE,
        decided_at_ms=AS_OF + 10,
    )
    CanonicalVaultDecisionLedger(epoch2_path).append(decision)
    projected = project_vault_decision_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        decision_identity=decision.decision_identity,
    )
    stored = IntelligenceStreamCapitalDecisionLedger(stream_path)

    with (
        sqlite3.connect(stream_path) as connection,
        pytest.raises(
            sqlite3.DatabaseError,
            match="immutable intelligence stream capital-decision ledger",
        ),
    ):
        connection.execute(
            "UPDATE stream_capital_decision_messages SET subtype = 'capital_hold'"
        )

    assert projected.narrative_identity
    assert stored.path == stream_path
