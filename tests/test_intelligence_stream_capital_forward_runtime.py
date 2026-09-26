from __future__ import annotations

from pathlib import Path

from test_immutable_forecast_stream import _event_context
from test_transaction_tape_atomic import _initial_state
from test_unified_decision_runtime import _issue

from crypto_signal.paper.canonical_vault_decisions import CanonicalVaultDecisionLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital_forward_runtime import (
    IntelligenceStreamCapitalForwardRuntime,
    StreamCapitalForwardDisposition,
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
)


def _stream(tmp_path: Path) -> Path:
    path = tmp_path / "stream.sqlite3"
    activation = build_stream_activation_boundary(activated_at_ms=1000)
    assert (
        IntelligenceStreamLedger(path).append_activation(activation)
        is StreamLedgerWriteDisposition.INSERTED
    )
    IntelligenceStreamNarrativeLedger(path).initialize()
    return path


def test_f5_forward_runtime_persists_three_vault_decisions_and_stream_story(
    tmp_path: Path,
) -> None:
    epoch2_path, _ = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    _, issuance = _issue(tmp_path)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1

    runtime = IntelligenceStreamCapitalForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
    )
    activation_identity = runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms,
    )
    first = runtime.project_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
    )
    second = runtime.project_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
    )

    assert first.activation_identity == activation_identity
    assert first.disposition is StreamCapitalForwardDisposition.INSERTED
    assert first.inserted_decision_count == 3
    assert first.hold_intent_count == 2
    assert first.projected_message_count == 4
    assert len(first.decision_identities) == 3
    assert first.real_capital == 0
    assert first.production_authority is False

    assert second.disposition is StreamCapitalForwardDisposition.UNCHANGED
    assert second.inserted_decision_count == 0
    assert second.hold_intent_count == 0
    assert second.projected_message_count == 0
    assert second.decision_identities == first.decision_identities

    decisions = CanonicalVaultDecisionLedger(epoch2_path).read_assessment_decisions(
        first.allocator_assessment_identity
    )
    assert len(decisions) == 3
    assert {item["vault_id"] for item in decisions} == {
        vault_id.value for vault_id in PaperVaultId
    }
    dispositions = {item["vault_id"]: item["disposition"] for item in decisions}
    assert dispositions[PaperVaultId.CORE.value] == "eligible"
    assert dispositions[PaperVaultId.TACTICAL.value] == "hold"
    assert dispositions[PaperVaultId.OPPORTUNITY_RESERVE.value] == "hold"
    assert [item["decided_at_ms"] for item in decisions] == [
        assessed_at_ms + 1,
        assessed_at_ms + 2,
        assessed_at_ms + 3,
    ]

    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == (2, 0, 0)

    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    assert len(page.items) == 4
    assert {item["subtype"] for item in page.items} == {
        "capital_candidate",
        "capital_eligible",
        "capital_hold",
    }
    assert all(item["real_capital"] == 0 for item in page.items)
    assert all(item["production_authority"] is False for item in page.items)


def test_f5_forward_runtime_skips_issuance_before_f5_activation(
    tmp_path: Path,
) -> None:
    epoch2_path, _ = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    _, issuance = _issue(tmp_path)

    runtime = IntelligenceStreamCapitalForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
    )
    runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms + 10,
    )
    result = runtime.project_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 20,
    )

    assert (
        result.disposition
        is StreamCapitalForwardDisposition.SKIPPED_BEFORE_ACTIVATION
    )
    assert result.decision_identities == ()
    assert result.inserted_decision_count == 0
    assert result.hold_intent_count == 0
    assert result.projected_message_count == 0

    assert (
        CanonicalVaultDecisionLedger(epoch2_path).read_assessment_decisions(
            "0" * 64
        )
        == ()
    )
    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    assert page.items == ()
