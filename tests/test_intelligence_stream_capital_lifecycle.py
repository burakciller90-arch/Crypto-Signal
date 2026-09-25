from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from test_canonical_capital_sell_runtime import _half_step_quantity
from test_intelligence_stream_capital import _execution_snapshot, _prepare, _sha
from test_smart_capital_allocator import AS_OF, _candidate
from test_transaction_tape_atomic import _initial_state

from crypto_signal.paper.canonical_capital_runtime import commit_canonical_paper_sell
from crypto_signal.paper.canonical_vault_decisions import (
    CanonicalVaultDecisionLedger,
    build_vault_decision,
)
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol
from crypto_signal.paper.smart_capital_allocator import assess_smart_capital_candidate
from crypto_signal.product.intelligence_stream_capital_decisions import (
    project_vault_decision_to_stream,
)
from crypto_signal.product.intelligence_stream_capital_lifecycle import (
    IntelligenceStreamCapitalLifecycleLedger,
    StreamCapitalLifecycleWriteDisposition,
    project_capital_bundle_lifecycle_to_stream,
    project_capital_candidate_to_stream,
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
    path = tmp_path / "lifecycle-stream.sqlite3"
    ledger = IntelligenceStreamLedger(path)
    activation = build_stream_activation_boundary(activated_at_ms=1_000)
    assert ledger.append_activation(activation) is StreamLedgerWriteDisposition.INSERTED
    IntelligenceStreamNarrativeLedger(path).initialize()
    return path


def test_s11_candidate_precedes_three_vault_decisions_in_same_stream(
    tmp_path: Path,
) -> None:
    epoch2_path, state = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    candidate = _candidate()
    assessment = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )
    decisions = tuple(
        build_vault_decision(
            state.activation,
            candidate,
            assessment,
            vault_id=vault_id,
            decided_at_ms=AS_OF + 10 + index,
        )
        for index, vault_id in enumerate(PaperVaultId)
    )
    ledger = CanonicalVaultDecisionLedger(epoch2_path)
    assert all(ledger.append(item) is True for item in decisions)

    candidate_projection = project_capital_candidate_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        allocator_assessment_identity=assessment.assessment_identity,
    )
    assert (
        candidate_projection.message_disposition
        is StreamCapitalLifecycleWriteDisposition.INSERTED
    )
    for decision in decisions:
        project_vault_decision_to_stream(
            epoch2_path=epoch2_path,
            stream_path=stream_path,
            decision_identity=decision.decision_identity,
        )

    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    assert [item["subtype"] for item in reversed(page.items)] == [
        "capital_candidate",
        "capital_eligible",
        "capital_eligible",
        "capital_eligible",
    ]
    candidate_item = next(
        item for item in page.items if item["subtype"] == "capital_candidate"
    )
    assert candidate_item["allocator_candidate_identity"] == candidate.candidate_identity
    assert candidate_item["allocator_assessment_identity"] == assessment.assessment_identity
    assert candidate_item["vault_id"] is None
    assert candidate_item["real_capital"] == 0
    assert candidate_item["production_authority"] is False


def test_s11_buy_lifecycle_emits_execution_then_accounting_update(
    tmp_path: Path,
) -> None:
    stream_path, epoch2_path, _, _, _, buy = _prepare(tmp_path)
    IntelligenceStreamNarrativeLedger(stream_path).initialize()

    projected = project_capital_bundle_lifecycle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=buy.accounting_bundle_identity,
    )

    assert projected.outcome is None
    assert projected.accounting.subtype == "capital_accounting_updated"
    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    chronological = list(reversed(page.items))
    assert [item["subtype"] for item in chronological] == [
        "capital_executed",
        "capital_accounting_updated",
    ]
    assert chronological[0]["event_at_ms"] < chronological[1]["event_at_ms"]
    accounting = chronological[1]
    assert accounting["bundle_identity"] == buy.accounting_bundle_identity
    assert Decimal(str(accounting["cash_after_usdt"])) < Decimal(
        str(accounting["cash_before_usdt"])
    )
    assert accounting["real_capital"] == 0


def test_s11_reduce_lifecycle_emits_outcome_before_accounting(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        epoch2_path,
        forecast,
        proof,
        assessment,
        buy,
    ) = _prepare(tmp_path)
    IntelligenceStreamNarrativeLedger(stream_path).initialize()
    project_capital_bundle_lifecycle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=buy.accounting_bundle_identity,
    )

    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    reduced = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.REDUCE,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=_half_step_quantity(core.positions[0].quantity),
        reference_price=Decimal(105),
        reference_price_evidence_identity=_sha("lifecycle-reduce-reference"),
        exit_evidence_identity=_sha("lifecycle-reduce-outcome"),
        exit_reason_codes=("lifecycle_partial_reduction",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(105)},
        mark_evidence_identity=_sha("lifecycle-reduce-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=2_000_220,
        filled_at_ms=2_000_230,
        mutated_at_ms=2_000_231,
        snapshot_at_ms=2_000_240,
    )
    projected = project_capital_bundle_lifecycle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=reduced.accounting_bundle_identity,
    )
    assert projected.outcome is not None
    assert projected.outcome.subtype == "capital_outcome"

    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    chronological = list(reversed(page.items))
    reduce_slice = [
        item
        for item in chronological
        if item.get("bundle_identity") == reduced.accounting_bundle_identity
    ]
    assert [item["subtype"] for item in reduce_slice] == [
        "capital_reduced",
        "capital_outcome",
        "capital_accounting_updated",
    ]
    assert [item["event_at_ms"] for item in reduce_slice] == sorted(
        item["event_at_ms"] for item in reduce_slice
    )
    outcome = reduce_slice[1]
    assert outcome["outcome_identity"] == reduced.outcome_identity
    assert outcome["financial_outcome"] == "PARTIAL_REDUCTION"
    assert Decimal(str(outcome["position_quantity_after"])) > 0
    assert Decimal(str(outcome["realized_pnl_delta_usdt"])) == (
        reduced.realized_pnl_delta_usdt
    )


def test_s11_bundle_lifecycle_projection_is_idempotent(tmp_path: Path) -> None:
    stream_path, epoch2_path, _, _, _, buy = _prepare(tmp_path)
    first = project_capital_bundle_lifecycle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=buy.accounting_bundle_identity,
    )
    second = project_capital_bundle_lifecycle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=buy.accounting_bundle_identity,
    )
    assert first.execution.narrative_identity == second.execution.narrative_identity
    assert first.accounting.narrative_identity == second.accounting.narrative_identity
    assert (
        second.accounting.message_disposition
        is StreamCapitalLifecycleWriteDisposition.UNCHANGED
    )
    stored = IntelligenceStreamCapitalLifecycleLedger(stream_path).read(
        second.accounting.narrative_identity
    )
    assert stored is not None
    assert stored["subtype"] == "capital_accounting_updated"
