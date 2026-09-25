from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from test_intelligence_stream_ledger import _full_bundle
from test_position_sizing_intelligence import (
    _context as sizing_context,
)
from test_position_sizing_intelligence import (
    _policy as sizing_policy,
)
from test_position_sizing_intelligence import (
    _vault as sizing_vault,
)
from test_transaction_tape_atomic import _initial_state

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.canonical_capital_runtime import (
    commit_canonical_paper_buy,
)
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.models import PaperSymbol
from crypto_signal.paper.position_sizing_intelligence import (
    evaluate_position_sizing_intelligence,
)
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
    assessment = evaluate_position_sizing_intelligence(
        policy=sizing_policy(),
        vault=sizing_vault(vault_id=PaperVaultId.CORE),
        context=sizing_context(vault_id=PaperVaultId.CORE),
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
    return stream_path, epoch2_path, forecast, committed


def test_s11_projects_verified_r22_bundle_into_immutable_capital_story(
    tmp_path: Path,
) -> None:
    stream_path, epoch2_path, forecast, committed = _prepare(tmp_path)

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
    stream_path, epoch2_path, _, committed = _prepare(tmp_path)

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
    stream_path, epoch2_path, _, committed = _prepare(tmp_path)
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
    stream_path, epoch2_path, _, committed = _prepare(tmp_path)
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
    stream_path, epoch2_path, _, committed = _prepare(tmp_path)
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
