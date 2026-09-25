from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_canonical_capital_runtime import _capital_inputs
from test_decision_proof_live_feed import ISSUED_AT
from test_transaction_tape_atomic import _initial_state

from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.canonical_sizing_events import (
    CanonicalSizingEventLedger,
    build_canonical_sizing_event,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.product.intelligence_stream_capital_sizing import (
    IntelligenceStreamCapitalSizingLedger,
    StreamCapitalSizingWriteDisposition,
    project_sizing_event_to_stream,
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


def _sizing_event(tmp_path: Path, vault_id: PaperVaultId = PaperVaultId.CORE):
    epoch2_path, state = _initial_state(tmp_path)
    current = next(item for item in state.vault_snapshots if item.vault_id is vault_id)
    assessment, eligibility = _capital_inputs(vault_id)
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=current,
        selected_at_ms=ISSUED_AT + 10,
    )
    event = build_canonical_sizing_event(selection, eligibility)
    return epoch2_path, state, selection, event


def _stream(tmp_path: Path) -> Path:
    path = tmp_path / "stream.sqlite3"
    activation = build_stream_activation_boundary(activated_at_ms=1000)
    stream = IntelligenceStreamLedger(path)
    assert stream.append_activation(activation) is StreamLedgerWriteDisposition.INSERTED
    IntelligenceStreamNarrativeLedger(path).initialize()
    return path


def test_s11_sizing_event_is_durable_before_any_fill(tmp_path: Path) -> None:
    epoch2_path, state, selection, event = _sizing_event(tmp_path)
    ledger = CanonicalSizingEventLedger(epoch2_path)

    assert ledger.append(event) is True
    assert ledger.append(event) is False
    stored = ledger.read(event.event_identity)
    assert stored is not None
    assert stored["selection_identity"] == selection.selection_identity
    assert stored["vault_id"] == PaperVaultId.CORE.value
    assert stored["canonical_notional_usdt"] == str(
        selection.canonical_notional_usdt
    )
    assert stored["current_vault_snapshot_identity"] == (
        selection.current_vault_snapshot_identity
    )
    assert stored["real_capital"] == 0

    # Sizing does not mutate R21 accounting or create an R22 fill.
    assert state == __import__(
        "crypto_signal.paper.epoch2_accounting",
        fromlist=["Epoch2CanonicalLedger"],
    ).Epoch2CanonicalLedger(epoch2_path).read_state()


def test_s11_capital_sized_joins_main_stream_and_deep_link(tmp_path: Path) -> None:
    epoch2_path, _, selection, event = _sizing_event(tmp_path)
    CanonicalSizingEventLedger(epoch2_path).append(event)
    stream_path = _stream(tmp_path)

    projected = project_sizing_event_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        sizing_event_identity=event.event_identity,
    )
    replayed = project_sizing_event_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        sizing_event_identity=event.event_identity,
    )

    assert (
        replayed.message_disposition
        is StreamCapitalSizingWriteDisposition.UNCHANGED
    )
    assert replayed.narrative_identity == projected.narrative_identity

    reader = IntelligenceStreamReadModel(stream_path)
    page = reader.read_messages(StreamMessageQuery(limit=20, category="capital"))
    assert len(page.items) == 1
    assert page.items[0]["subtype"] == "capital_sized"
    assert page.items[0]["selection_identity"] == selection.selection_identity
    assert page.items[0]["canonical_notional_usdt"] == str(
        selection.canonical_notional_usdt
    )
    assert page.items[0]["real_capital"] == 0

    search = reader.read_messages(StreamMessageQuery(limit=20, text="boyut"))
    assert len(search.items) == 1

    direct = reader.read_message(projected.narrative_identity)
    assert direct is not None
    assert direct["sizing_event_identity"] == event.event_identity

    detail = reader.read_message_detail(projected.narrative_identity)
    assert detail is not None
    assert detail["capital_sizing"]["selection_identity"] == (
        selection.selection_identity
    )
    assert "analytical_view" not in detail
    assert "fact_bundle" not in detail


def test_s11_sizing_rows_are_physically_immutable(tmp_path: Path) -> None:
    epoch2_path, _, _, event = _sizing_event(tmp_path)
    CanonicalSizingEventLedger(epoch2_path).append(event)

    with (
        sqlite3.connect(epoch2_path) as connection,
        pytest.raises(
            sqlite3.DatabaseError,
            match="immutable S11 canonical sizing event ledger",
        ),
    ):
        connection.execute(
            "UPDATE s11_canonical_sizing_events SET vault_id = 'TACTICAL'"
        )

    stream_path = _stream(tmp_path)
    projected = project_sizing_event_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        sizing_event_identity=event.event_identity,
    )
    assert projected.narrative_identity

    with (
        sqlite3.connect(stream_path) as connection,
        pytest.raises(
            sqlite3.DatabaseError,
            match="immutable intelligence stream capital-sizing ledger",
        ),
    ):
        connection.execute(
            "UPDATE stream_capital_sizing_messages SET timeframe = '1m'"
        )

    assert IntelligenceStreamCapitalSizingLedger(stream_path).path == stream_path
