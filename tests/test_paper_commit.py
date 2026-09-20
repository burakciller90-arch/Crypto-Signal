"""Focused Stage 6C Slice 4 tests for atomic paper-bundle persistence."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.paper import commit as paper_commit
from crypto_signal.paper.commit import (
    PaperBundleCommitError,
    commit_orchestration_bundle,
)
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerConflictError,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
)
from crypto_signal.paper.orchestration import orchestrate_paper_plan
from crypto_signal.paper.planning import plan_hold_cash, plan_paper_trade
from crypto_signal.paper.state import reconstruct_paper_fund_state


def _pristine(tmp_path: Path, *, name: str = "paper_commit.sqlite3"):
    ledger = PaperFundLedger(tmp_path / name)
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    return ledger, reconstruct_paper_fund_state(ledger)


def _trade_bundle(state):
    plan = plan_paper_trade(
        state=state,
        planned_at_ms=10,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.001"),
        reference_price=Decimal(20000),
        cost_budget_usdt=Decimal("0.05"),
        reason="bounded virtual buy",
        invalidation_context="close below frozen structure",
        mark_prices={PaperSymbol.BTCUSDT: Decimal(20000)},
    )
    snapshot = build_frozen_execution_snapshot(
        venue_reference="frozen:test-venue",
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        min_notional_usdt=Decimal(5),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
        policy_version=PAPER_EXECUTION_POLICY_VERSION,
    )
    return orchestrate_paper_plan(state=state, plan=plan, snapshot=snapshot)


def test_trade_bundle_commits_atomically_and_rereads_state(tmp_path: Path) -> None:
    ledger, state = _pristine(tmp_path)
    bundle = _trade_bundle(state)

    result = commit_orchestration_bundle(
        ledger=ledger,
        state=state,
        bundle=bundle,
    )

    assert result.disposition is PaperLedgerWriteDisposition.INSERTED
    assert result.record_identities == (
        bundle.decision.record_identity,
        bundle.fill.record_identity,
        bundle.mutation.record_identity,
    )
    assert bundle.mutation is not None
    assert result.state_after.cash_usdt == bundle.mutation.cash_after_usdt
    assert result.state_after.positions == bundle.mutation.positions_after
    assert result.state_after.last_mutation_identity == bundle.mutation.record_identity
    assert result.state_after.replayed_record_count == 4
    assert reconstruct_paper_fund_state(ledger) == result.state_after


def test_exact_retry_is_idempotent_with_original_precommit_state(
    tmp_path: Path,
) -> None:
    ledger, state = _pristine(tmp_path)
    bundle = _trade_bundle(state)

    first = commit_orchestration_bundle(ledger=ledger, state=state, bundle=bundle)
    replay_after_first = ledger.replay()
    second = commit_orchestration_bundle(ledger=ledger, state=state, bundle=bundle)

    assert first.disposition is PaperLedgerWriteDisposition.INSERTED
    assert second.disposition is PaperLedgerWriteDisposition.UNCHANGED
    assert ledger.replay() == replay_after_first
    assert second.state_after == first.state_after


def test_hold_cash_commits_decision_only(tmp_path: Path) -> None:
    ledger, state = _pristine(tmp_path)
    plan = plan_hold_cash(
        state=state,
        planned_at_ms=20,
        reason="cash is valid",
        invalidation_context="wait for better evidence",
    )
    bundle = orchestrate_paper_plan(state=state, plan=plan, snapshot=None)

    result = commit_orchestration_bundle(
        ledger=ledger,
        state=state,
        bundle=bundle,
    )

    assert result.disposition is PaperLedgerWriteDisposition.INSERTED
    assert result.record_identities == (bundle.decision.record_identity,)
    assert result.state_after.cash_usdt == state.cash_usdt
    assert result.state_after.positions == state.positions
    assert result.state_after.replayed_record_count == 2


def test_stale_state_is_rejected_before_new_bundle_write(tmp_path: Path) -> None:
    ledger, stale_state = _pristine(tmp_path)
    bundle = _trade_bundle(stale_state)
    unrelated = build_decision_intent(
        fund_identity=stale_state.fund_identity,
        decided_at_ms=5,
        action=PaperAction.HOLD_CASH,
        reason="intervening immutable decision",
        invalidation_context="none",
    )
    ledger.append_decision_intent(unrelated)
    before = ledger.replay()

    with pytest.raises(PaperBundleCommitError, match="stale"):
        commit_orchestration_bundle(
            ledger=ledger,
            state=stale_state,
            bundle=bundle,
        )

    assert ledger.replay() == before


def test_partially_existing_trade_bundle_is_rejected(tmp_path: Path) -> None:
    ledger, state = _pristine(tmp_path)
    bundle = _trade_bundle(state)
    ledger.append_decision_intent(bundle.decision)
    before = ledger.replay()

    with pytest.raises(PaperLedgerConflictError, match="partially existing"):
        commit_orchestration_bundle(ledger=ledger, state=state, bundle=bundle)

    assert ledger.replay() == before


def test_mid_bundle_sql_failure_rolls_back_every_new_record(tmp_path: Path) -> None:
    ledger, state = _pristine(tmp_path)
    bundle = _trade_bundle(state)
    ledger.initialize()

    with sqlite3.connect(ledger.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_test_fill_insert
            BEFORE INSERT ON paper_simulated_fills
            BEGIN
                SELECT RAISE(ABORT, 'test injected fill failure');
            END
            """
        )

    before = ledger.replay()
    with pytest.raises(sqlite3.IntegrityError, match="test injected fill failure"):
        commit_orchestration_bundle(ledger=ledger, state=state, bundle=bundle)

    assert ledger.replay() == before
    assert len(before) == 1


def test_atomic_bundle_replay_order_is_contiguous(tmp_path: Path) -> None:
    ledger, state = _pristine(tmp_path)
    bundle = _trade_bundle(state)
    result = commit_orchestration_bundle(ledger=ledger, state=state, bundle=bundle)
    replay = ledger.replay()

    positions = [
        next(
            index
            for index, entry in enumerate(replay)
            if entry.record_identity == identity
        )
        for identity in result.record_identities
    ]
    assert positions == [1, 2, 3]


def test_commit_boundary_has_no_real_order_or_network_surface() -> None:
    source = inspect.getsource(paper_commit).lower()
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
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert paper_commit.REAL_CAPITAL == REAL_CAPITAL == 0
