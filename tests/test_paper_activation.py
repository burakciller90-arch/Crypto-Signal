"""Tests for persistent paper activation watermark and event receipts."""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from crypto_signal.paper import activation as paper_activation
from crypto_signal.paper.activation import (
    PaperActivationError,
    PaperProcessedEventOutcome,
    activate_paper_policy,
    build_processed_event_receipt,
    is_paper_event_processed,
    list_processed_paper_events,
    load_paper_activation,
    record_terminal_no_action,
)
from crypto_signal.paper.ledger import PaperFundLedger, PaperLedgerWriteDisposition
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state

LATEST_FREEZE = "f" * 64
SOURCE_IDS = ("a" * 64, "b" * 64)


def _ledger_state(tmp_path):
    ledger = PaperFundLedger(tmp_path / "activation.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return ledger, reconstruct_paper_fund_state(ledger)


def _activate(ledger, state, *, activated_at_ms: int = 10_000):
    return activate_paper_policy(
        ledger=ledger,
        state=state,
        activated_at_ms=activated_at_ms,
        baseline_signal_freeze_count=312,
        baseline_latest_signal_freeze_identity=LATEST_FREEZE,
        baseline_latest_frozen_at_ms=9_900,
    )


def _receipt(activation, *, reason: str = "terminal hold"):
    return build_processed_event_receipt(
        activation=activation,
        source_freeze_identities=SOURCE_IDS,
        symbol=PaperSymbol.BTCUSDT,
        timeframe="4h",
        signal_as_of_ms=10_100,
        outcome=PaperProcessedEventOutcome.TERMINAL_NO_ACTION,
        processed_at_ms=10_200,
        terminal_reason=reason,
    )


def test_activation_is_singleton_persistent_and_idempotent(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    first_disposition, first = _activate(ledger, state)
    second_disposition, second = _activate(ledger, state)

    assert first_disposition is PaperLedgerWriteDisposition.INSERTED
    assert second_disposition is PaperLedgerWriteDisposition.UNCHANGED
    assert first == second
    assert first.activation_cutoff_ms == first.activated_at_ms == 10_000
    assert load_paper_activation(PaperFundLedger(ledger.path)) == first
    assert reconstruct_paper_fund_state(ledger) == state
    assert first.real_capital == REAL_CAPITAL == 0


def test_activation_cannot_be_rebased_silently(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    _activate(ledger, state)

    with pytest.raises(PaperActivationError, match="immutable"):
        _activate(ledger, state, activated_at_ms=10_001)


def test_pre_activation_event_is_permanently_ineligible(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    _, activation = _activate(ledger, state)

    with pytest.raises(PaperActivationError, match="predates activation"):
        build_processed_event_receipt(
            activation=activation,
            source_freeze_identities=SOURCE_IDS,
            symbol=PaperSymbol.BTCUSDT,
            timeframe="4h",
            signal_as_of_ms=9_999,
            outcome=PaperProcessedEventOutcome.TERMINAL_NO_ACTION,
            processed_at_ms=10_200,
            terminal_reason="historical evidence",
        )


def test_terminal_no_action_receipt_is_restart_safe_and_idempotent(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    _, activation = _activate(ledger, state)
    receipt = _receipt(activation)

    first = record_terminal_no_action(
        ledger=ledger,
        state=state,
        activation=activation,
        receipt=receipt,
    )
    second = record_terminal_no_action(
        ledger=PaperFundLedger(ledger.path),
        state=state,
        activation=activation,
        receipt=receipt,
    )

    assert first is PaperLedgerWriteDisposition.INSERTED
    assert second is PaperLedgerWriteDisposition.UNCHANGED
    assert is_paper_event_processed(ledger, receipt.event_identity) is True
    assert list_processed_paper_events(PaperFundLedger(ledger.path)) == (receipt,)
    assert reconstruct_paper_fund_state(ledger) == state
    assert len(ledger.replay()) == 1


def test_same_event_identity_cannot_change_terminal_outcome_payload(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    _, activation = _activate(ledger, state)
    receipt = _receipt(activation)
    record_terminal_no_action(
        ledger=ledger,
        state=state,
        activation=activation,
        receipt=receipt,
    )
    conflicting = _receipt(activation, reason="different terminal reason")
    assert conflicting.event_identity == receipt.event_identity

    with pytest.raises(PaperActivationError, match="identity conflict"):
        record_terminal_no_action(
            ledger=ledger,
            state=state,
            activation=activation,
            receipt=conflicting,
        )


def test_stale_paper_state_cannot_mark_event_processed(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    _, activation = _activate(ledger, state)
    receipt = _receipt(activation)
    intervening = build_decision_intent(
        fund_identity=state.fund_identity,
        decided_at_ms=10_150,
        action=PaperAction.HOLD_CASH,
        reason="intervening decision",
        invalidation_context="stale activation test",
    )
    ledger.append_decision_intent(intervening)

    with pytest.raises(PaperActivationError, match="stale"):
        record_terminal_no_action(
            ledger=ledger,
            state=state,
            activation=activation,
            receipt=receipt,
        )

    assert is_paper_event_processed(ledger, receipt.event_identity) is False


def test_activation_and_event_tables_are_immutable(tmp_path) -> None:
    ledger, state = _ledger_state(tmp_path)
    _, activation = _activate(ledger, state)
    receipt = _receipt(activation)
    record_terminal_no_action(
        ledger=ledger,
        state=state,
        activation=activation,
        receipt=receipt,
    )

    with sqlite3.connect(ledger.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper ledger"):
            connection.execute(
                "UPDATE paper_activation_state SET activated_at_ms = ? WHERE singleton = 1",
                (99_999,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper ledger"):
            connection.execute(
                "DELETE FROM paper_processed_events WHERE event_identity = ?",
                (receipt.event_identity,),
            )


def test_activation_surface_has_no_trade_network_or_runtime_authority() -> None:
    source = inspect.getsource(paper_activation).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
        "simulate_paper_fill",
        "commit_planned_pretrade",
        "run_paper_runtime_tick",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert paper_activation.REAL_CAPITAL == REAL_CAPITAL == 0
