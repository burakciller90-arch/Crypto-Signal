from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from test_canonical_capital_sell_runtime import _half_step_quantity
from test_intelligence_stream_ledger import _full_bundle
from test_position_sizing_intelligence import (
    _policy as sizing_policy,
)
from test_smart_capital_allocator import _candidate
from test_transaction_tape_atomic import _initial_state

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.canonical_capital_runtime import (
    commit_canonical_paper_buy,
    commit_canonical_paper_sell,
)
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.canonical_vault_eligibility import promote_vault_eligibility
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.models import PaperAction, PaperSymbol
from crypto_signal.paper.position_sizing_intelligence import (
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.smart_capital_allocator import assess_smart_capital_candidate
from crypto_signal.product.intelligence_stream_capital import (
    IntelligenceStreamCapitalLedger,
    StreamCapitalWriteDisposition,
    project_capital_bundle_to_stream,
)
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
    StreamLedgerWriteDisposition,
)
from crypto_signal.product.intelligence_stream_models import (
    build_forecast_issued_source_event,
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


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _execution_snapshot():
    return build_frozen_execution_snapshot(
        venue_reference="s11:capital-story-test",
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        min_notional_usdt=Decimal(1),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
    )


def _prepare(tmp_path: Path):
    (
        _,
        forecast,
        proof,
        decision_context,
        issuance_feed_event,
    ) = _full_bundle(
        as_of_ms=2_000_000,
        issued_at_ms=2_000_100,
        seed="s11-capital-story",
    )
    stream_path = tmp_path / "stream.sqlite3"
    activation = build_stream_activation_boundary(activated_at_ms=2_000_000)
    issuance_event = build_forecast_issued_source_event(
        activation,
        decision_context,
        issuance_feed_event,
    )
    stream = IntelligenceStreamLedger(stream_path)
    assert stream.append_activation(activation) is StreamLedgerWriteDisposition.INSERTED
    assert (
        stream.append_issuance_bundle(decision_context, issuance_event)
        is StreamLedgerWriteDisposition.INSERTED
    )

    epoch2_path, state = _initial_state(tmp_path)
    core = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    candidate = _candidate()
    allocator = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )
    core_envelope = next(
        item for item in allocator.vaults
        if item.vault_id is PaperVaultId.CORE
    )
    sizing_context = build_position_sizing_risk_context(
        vault_id=PaperVaultId.CORE,
        asset="BTCUSDT",
        as_of_ms=2_000_100,
        allocator_assessment_identity=allocator.assessment_identity,
        allocator_candidate_identity=candidate.candidate_identity,
        expected_win_r=Decimal(2),
        expected_loss_r=Decimal(1),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=Decimal("0.20"),
        current_drawdown_fraction=Decimal("0.05"),
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=(
            _sha("capital-story-correlation"),
            _sha("capital-story-drawdown"),
            _sha("capital-story-liquidity"),
            _sha("capital-story-payoff"),
            _sha("capital-story-volatility"),
        ),
    )
    assessment = evaluate_position_sizing_intelligence(
        policy=sizing_policy(),
        vault=core_envelope,
        context=sizing_context,
    )
    eligibility = promote_vault_eligibility(
        candidate,
        allocator,
        vault_id=PaperVaultId.CORE,
    )
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=core,
        selected_at_ms=2_000_110,
    )
    committed = commit_canonical_paper_buy(
        epoch2_path=epoch2_path,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        symbol=PaperSymbol.BTCUSDT,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("s11-reference-price"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("s11-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=2_000_120,
        filled_at_ms=2_000_130,
        mutated_at_ms=2_000_131,
        snapshot_at_ms=2_000_140,
    )
    return stream_path, epoch2_path, forecast, proof, assessment, committed


def test_s11_projects_verified_r22_bundle_into_immutable_capital_story(
    tmp_path: Path,
) -> None:
    stream_path, epoch2_path, forecast, _, _, committed = _prepare(tmp_path)

    result = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )

    assert result.message_disposition is StreamCapitalWriteDisposition.INSERTED
    assert result.real_capital == 0
    stored = IntelligenceStreamCapitalLedger(stream_path).read_message(
        result.narrative_identity
    )
    assert stored is not None
    assert stored["category"] == "capital"
    assert stored["subtype"] == "capital_executed"
    assert stored["vault_id"] == PaperVaultId.CORE.value
    assert stored["forecast_identity"] == forecast.forecast_identity
    assert stored["bundle_identity"] == committed.accounting_bundle_identity
    assert stored["real_capital"] == 0
    assert stored["production_authority"] is False
    assert "REAL_CAPITAL=0" in stored["text"]["collapsed_text"]
    assert committed.intent_identity in stored["capital_reference_identities"]
    assert committed.fill_identity in stored["capital_reference_identities"]


def test_s11_capital_projection_is_idempotent(tmp_path: Path) -> None:
    stream_path, epoch2_path, _, _, _, committed = _prepare(tmp_path)

    first = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )
    second = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )

    assert first.narrative_identity == second.narrative_identity
    assert second.source_event_disposition is StreamLedgerWriteDisposition.UNCHANGED
    assert second.message_disposition is StreamCapitalWriteDisposition.UNCHANGED

    with sqlite3.connect(stream_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM stream_capital_messages"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM stream_source_events WHERE category = 'capital'"
        ).fetchone() == (1,)


def test_s11_capital_story_rows_are_physically_immutable(tmp_path: Path) -> None:
    stream_path, epoch2_path, _, _, _, committed = _prepare(tmp_path)
    project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )

    with (
        sqlite3.connect(stream_path) as connection,
        pytest.raises(
            sqlite3.DatabaseError,
            match="immutable intelligence stream capital ledger",
        ),
    ):
        connection.execute(
            "UPDATE stream_capital_messages SET vault_id = 'TACTICAL'"
        )


def test_s11_capital_story_joins_canonical_stream_pagination_and_filters(
    tmp_path: Path,
) -> None:
    stream_path, epoch2_path, _, _, _, committed = _prepare(tmp_path)
    IntelligenceStreamNarrativeLedger(stream_path).initialize()
    projected = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )
    reader = IntelligenceStreamReadModel(stream_path)

    page = reader.read_messages(StreamMessageQuery(limit=20))
    assert [item["narrative_identity"] for item in page.items] == [
        projected.narrative_identity
    ]
    assert page.items[0]["category"] == "capital"
    assert page.items[0]["vault_id"] == PaperVaultId.CORE.value
    assert page.newest_cursor is not None
    assert decode_stream_cursor(page.newest_cursor).narrative_identity == (
        projected.narrative_identity
    )

    capital_only = reader.read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    assert len(capital_only.items) == 1

    core_only = reader.read_messages(
        StreamMessageQuery(limit=20, vault=PaperVaultId.CORE.value)
    )
    assert [item["narrative_identity"] for item in core_only.items] == [
        projected.narrative_identity
    ]

    tactical_only = reader.read_messages(
        StreamMessageQuery(limit=20, vault=PaperVaultId.TACTICAL.value)
    )
    assert tactical_only.items == ()

    executed_only = reader.read_messages(
        StreamMessageQuery(limit=20, state="capital_executed")
    )
    assert [item["narrative_identity"] for item in executed_only.items] == [
        projected.narrative_identity
    ]

    decision_only = reader.read_messages(
        StreamMessageQuery(limit=20, category="decision")
    )
    assert decision_only.items == ()

    text_match = reader.read_messages(
        StreamMessageQuery(limit=20, text="sanal alımı")
    )
    assert len(text_match.items) == 1

    no_stance_fabrication = reader.read_messages(
        StreamMessageQuery(limit=20, effective_stance="bullish")
    )
    assert no_stance_fabrication.items == ()


def test_s11_capital_story_lookup_and_detail_do_not_invent_analytical_truth(
    tmp_path: Path,
) -> None:
    stream_path, epoch2_path, _, _, _, committed = _prepare(tmp_path)
    IntelligenceStreamNarrativeLedger(stream_path).initialize()
    projected = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )
    reader = IntelligenceStreamReadModel(stream_path)

    message = reader.read_message(projected.narrative_identity)
    assert message is not None
    assert message["category"] == "capital"

    detail = reader.read_message_detail(projected.narrative_identity)
    assert detail is not None
    assert detail["narrative"]["narrative_identity"] == projected.narrative_identity
    assert detail["capital_story"]["bundle_identity"] == (
        committed.accounting_bundle_identity
    )
    assert "analytical_view" not in detail
    assert "fact_bundle" not in detail
    assert detail["production_authority"] is False
    assert detail["real_capital"] == 0



def test_s11_projects_reduce_and_exit_with_exact_outcome_lineage(
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

    buy_message = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=buy.accounting_bundle_identity,
    )
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )
    reduce_quantity = _half_step_quantity(core.positions[0].quantity)
    reduced = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.REDUCE,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=reduce_quantity,
        reference_price=Decimal(105),
        reference_price_evidence_identity=_sha("story-reduce-reference"),
        exit_evidence_identity=_sha("story-reduce-outcome"),
        exit_reason_codes=("story_partial_reduction",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(105)},
        mark_evidence_identity=_sha("story-reduce-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=2_000_220,
        filled_at_ms=2_000_230,
        mutated_at_ms=2_000_231,
        snapshot_at_ms=2_000_240,
    )
    reduce_message = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=reduced.accounting_bundle_identity,
    )

    reduce_stored = IntelligenceStreamCapitalLedger(stream_path).read_message(
        reduce_message.narrative_identity
    )
    assert reduce_stored is not None
    assert reduce_stored["subtype"] == "capital_reduced"
    assert reduce_stored["action"] == "REDUCE"
    assert reduce_stored["outcome_identity"] == reduced.outcome_identity
    assert reduce_stored["financial_outcome"] == "PARTIAL_REDUCTION"
    assert reduce_stored["realized_pnl_delta_usdt"] == str(
        reduced.realized_pnl_delta_usdt
    )
    assert reduced.outcome_identity in reduce_stored["capital_reference_identities"]

    exited = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.EXIT,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=None,
        reference_price=Decimal(110),
        reference_price_evidence_identity=_sha("story-exit-reference"),
        exit_evidence_identity=_sha("story-exit-outcome"),
        exit_reason_codes=("story_full_exit",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(110)},
        mark_evidence_identity=_sha("story-exit-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=2_000_320,
        filled_at_ms=2_000_330,
        mutated_at_ms=2_000_331,
        snapshot_at_ms=2_000_340,
    )
    exit_message = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=exited.accounting_bundle_identity,
    )
    exit_stored = IntelligenceStreamCapitalLedger(stream_path).read_message(
        exit_message.narrative_identity
    )
    assert exit_stored is not None
    assert exit_stored["subtype"] == "capital_exited"
    assert exit_stored["action"] == "EXIT"
    assert exit_stored["outcome_identity"] == exited.outcome_identity
    assert exit_stored["financial_outcome"] == "CLOSED_WIN"
    assert Decimal(str(exit_stored["position_quantity_after"])) == 0
    assert "REAL_CAPITAL=0" in exit_stored["text"]["collapsed_text"]

    page = IntelligenceStreamReadModel(stream_path).read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    capital_ids = {item["narrative_identity"] for item in page.items}
    assert capital_ids == {
        buy_message.narrative_identity,
        reduce_message.narrative_identity,
        exit_message.narrative_identity,
    }


def test_s11_sell_projection_is_idempotent(tmp_path: Path) -> None:
    (
        stream_path,
        epoch2_path,
        forecast,
        proof,
        assessment,
        buy,
    ) = _prepare(tmp_path)
    project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=buy.accounting_bundle_identity,
    )
    sold = commit_canonical_paper_sell(
        epoch2_path=epoch2_path,
        action=PaperAction.EXIT,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        symbol=PaperSymbol.BTCUSDT,
        quantity=None,
        reference_price=Decimal(105),
        reference_price_evidence_identity=_sha("idempotent-exit-reference"),
        exit_evidence_identity=_sha("idempotent-exit-outcome"),
        exit_reason_codes=("idempotent_exit",),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(105)},
        mark_evidence_identity=_sha("idempotent-exit-mark"),
        execution_snapshot=_execution_snapshot(),
        decided_at_ms=2_000_220,
        filled_at_ms=2_000_230,
        mutated_at_ms=2_000_231,
        snapshot_at_ms=2_000_240,
    )
    first = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=sold.accounting_bundle_identity,
    )
    second = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=sold.accounting_bundle_identity,
    )
    assert first.narrative_identity == second.narrative_identity
    assert second.source_event_disposition is StreamLedgerWriteDisposition.UNCHANGED
    assert second.message_disposition is StreamCapitalWriteDisposition.UNCHANGED
