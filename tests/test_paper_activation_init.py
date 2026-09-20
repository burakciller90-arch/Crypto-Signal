"""Tests for one-time pristine paper activation watermark initialization."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from crypto_signal.paper.activation_init import (
    PAPER_ACTIVATION_INIT_VERSION,
    PaperActivationInitError,
    initialize_paper_activation_watermark,
    read_signal_activation_baseline,
)
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import (
    PaperAction,
    build_decision_intent,
    build_fund_creation,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _paper_db(path) -> PaperFundLedger:
    ledger = PaperFundLedger(path)
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return ledger


def _signal_db(path, rows: tuple[tuple[str, int], ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                signal_freeze_identity TEXT PRIMARY KEY,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO signal_freezes (
                signal_freeze_identity,
                frozen_at_ms
            ) VALUES (?, ?)
            """,
            rows,
        )


def test_activation_init_captures_baseline_and_is_idempotent(tmp_path) -> None:
    paper = _paper_db(tmp_path / "paper.sqlite3")
    signals = tmp_path / "signals.sqlite3"
    first_id = _sha("first")
    second_id = _sha("second")
    _signal_db(signals, ((first_id, 100), (second_id, 200)))

    first = initialize_paper_activation_watermark(
        paper_ledger_path=paper.path,
        signal_ledger_path=signals,
        activated_at_ms=300,
    )
    with sqlite3.connect(signals) as connection:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                signal_freeze_identity,
                frozen_at_ms
            ) VALUES (?, ?)
            """,
            (_sha("post-activation"), 400),
        )
    second = initialize_paper_activation_watermark(
        paper_ledger_path=paper.path,
        signal_ledger_path=signals,
        activated_at_ms=500,
    )

    assert first.version == PAPER_ACTIVATION_INIT_VERSION
    assert first.disposition is PaperLedgerWriteDisposition.INSERTED
    assert second.disposition is PaperLedgerWriteDisposition.UNCHANGED
    assert second.activation == first.activation
    assert first.baseline.freeze_count == 2
    assert first.baseline.latest_signal_freeze_identity == second_id
    assert first.baseline.latest_frozen_at_ms == 200
    assert first.activation.activated_at_ms == 300
    state = reconstruct_paper_fund_state(paper)
    assert state.replayed_record_count == 1
    assert state.cash_usdt == 100
    assert state.positions == ()


def test_baseline_read_is_read_only(tmp_path) -> None:
    signals = tmp_path / "signals.sqlite3"
    identity = _sha("only")
    _signal_db(signals, ((identity, 100),))
    before = signals.read_bytes()
    baseline = read_signal_activation_baseline(signals)
    after = signals.read_bytes()

    assert baseline.freeze_count == 1
    assert baseline.latest_signal_freeze_identity == identity
    assert baseline.latest_frozen_at_ms == 100
    assert after == before


def test_activation_refuses_timestamp_before_latest_freeze(tmp_path) -> None:
    paper = _paper_db(tmp_path / "paper.sqlite3")
    signals = tmp_path / "signals.sqlite3"
    _signal_db(signals, ((_sha("latest"), 500),))

    with pytest.raises(PaperActivationInitError, match="predates latest"):
        initialize_paper_activation_watermark(
            paper_ledger_path=paper.path,
            signal_ledger_path=signals,
            activated_at_ms=499,
        )


def test_activation_refuses_non_pristine_paper_fund(tmp_path) -> None:
    paper = _paper_db(tmp_path / "paper.sqlite3")
    state = reconstruct_paper_fund_state(paper)
    paper.append_decision_intent(
        build_decision_intent(
            fund_identity=state.fund_identity,
            decided_at_ms=10,
            action=PaperAction.HOLD_CASH,
            reason="not pristine",
            invalidation_context="activation init test",
        )
    )
    signals = tmp_path / "signals.sqlite3"
    _signal_db(signals, ())

    with pytest.raises(PaperActivationInitError, match="pristine"):
        initialize_paper_activation_watermark(
            paper_ledger_path=paper.path,
            signal_ledger_path=signals,
            activated_at_ms=100,
        )
