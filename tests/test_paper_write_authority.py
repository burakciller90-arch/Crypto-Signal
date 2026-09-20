"""Tests for append-only virtual-paper write authority."""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from crypto_signal.paper import write_authority as paper_write_authority
from crypto_signal.paper.activation import activate_paper_policy
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import REAL_CAPITAL, build_fund_creation
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.paper.write_authority import (
    append_paper_write_authority_event,
    list_paper_write_authority_events,
    load_current_paper_write_authority,
)


def _activated_ledger(tmp_path):
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    state = reconstruct_paper_fund_state(ledger)
    _, activation = activate_paper_policy(
        ledger=ledger,
        state=state,
        activated_at_ms=100,
        baseline_signal_freeze_count=0,
        baseline_latest_signal_freeze_identity=None,
        baseline_latest_frozen_at_ms=None,
    )
    return ledger, activation


def test_write_authority_enable_disable_chain_is_append_only(tmp_path) -> None:
    ledger, activation = _activated_ledger(tmp_path)
    event_id = "a" * 64
    trace_id = "b" * 64

    enable_write, enabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=True,
        created_at_ms=200,
        reason="reviewed production evidence",
        reviewed_event_identities=(event_id,),
        reviewed_trace_identities=(trace_id,),
    )
    disable_write, disabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=False,
        created_at_ms=300,
        reason="operator pause",
    )

    assert enable_write is PaperLedgerWriteDisposition.INSERTED
    assert disable_write is PaperLedgerWriteDisposition.INSERTED
    assert enabled.enabled is True
    assert disabled.enabled is False
    assert disabled.previous_event_identity == enabled.authority_event_identity
    assert load_current_paper_write_authority(ledger) == disabled
    assert list_paper_write_authority_events(ledger) == (enabled, disabled)
    assert enabled.real_capital == disabled.real_capital == REAL_CAPITAL == 0


def test_enabling_write_authority_requires_review_evidence(tmp_path) -> None:
    ledger, activation = _activated_ledger(tmp_path)

    with pytest.raises(ValueError, match="reviewed production events"):
        append_paper_write_authority_event(
            ledger=ledger,
            activation=activation,
            enabled=True,
            created_at_ms=200,
            reason="missing evidence",
        )


def test_write_authority_sql_rows_reject_update_delete(tmp_path) -> None:
    ledger, activation = _activated_ledger(tmp_path)
    _, enabled = append_paper_write_authority_event(
        ledger=ledger,
        activation=activation,
        enabled=True,
        created_at_ms=200,
        reason="reviewed production evidence",
        reviewed_event_identities=("a" * 64,),
        reviewed_trace_identities=("b" * 64,),
    )

    for statement in (
        (
            "UPDATE paper_write_authority_events SET enabled = 0 "
            "WHERE authority_event_identity = ?"
        ),
        (
            "DELETE FROM paper_write_authority_events "
            "WHERE authority_event_identity = ?"
        ),
    ):
        with (
            sqlite3.connect(ledger.path) as connection,
            pytest.raises(sqlite3.IntegrityError, match="immutable"),
        ):
            connection.execute(statement, (enabled.authority_event_identity,))


def test_write_authority_surface_has_no_real_order_or_network_authority() -> None:
    source = inspect.getsource(paper_write_authority).lower()
    forbidden = (
        "requests",
        "httpx",
        "urllib",
        "socket",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert paper_write_authority.REAL_CAPITAL == REAL_CAPITAL == 0
