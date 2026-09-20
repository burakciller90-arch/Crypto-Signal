"""Focused tests for Stage 6C persistent paper-account runtime foundation."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from crypto_signal.paper import runtime as paper_runtime
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import INITIAL_CASH_USDT, REAL_CAPITAL
from crypto_signal.paper.runtime import (
    PaperFundBootstrapStatus,
    PaperRuntimeError,
    ensure_persistent_paper_fund,
    observe_signal_ledger,
    run_paper_runtime_tick,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state


def _signal_ledger(path: Path, *, with_signal: bool = True) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                bundle_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL UNIQUE,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                as_of_ms INTEGER NOT NULL,
                source_cutoff_open_time_ms INTEGER NOT NULL,
                signal_state TEXT NOT NULL,
                direction TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE lifecycle_evaluations (
                evaluation_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL,
                evaluated_as_of_ms INTEGER NOT NULL,
                current_state TEXT NOT NULL,
                status TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                appended_at_ms INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE outcome_evaluations (
                outcome_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL,
                evidence_class TEXT NOT NULL,
                evaluated_as_of_ms INTEGER NOT NULL,
                resolution_status TEXT NOT NULL,
                outcome_state TEXT,
                max_holding_bars INTEGER NOT NULL,
                outcome_json TEXT NOT NULL,
                appended_at_ms INTEGER NOT NULL
            )
            """
        )
        if with_signal:
            connection.execute(
                """
                INSERT INTO signal_freezes (
                    bundle_identity,
                    signal_freeze_identity,
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    as_of_ms,
                    source_cutoff_open_time_ms,
                    signal_state,
                    direction,
                    bundle_json,
                    frozen_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "b" * 64,
                    "s" * 64,
                    "bybit",
                    "spot",
                    "BTCUSDT",
                    "15m",
                    100,
                    90,
                    "watch",
                    "bullish",
                    "{}",
                    110,
                ),
            )
    return path


def test_bootstrap_creates_one_fund_and_restart_reuses_it(tmp_path: Path) -> None:
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")

    first_status, first = ensure_persistent_paper_fund(
        ledger,
        created_at_ms=100,
    )
    second_status, second = ensure_persistent_paper_fund(
        ledger,
        created_at_ms=999,
    )

    assert first_status is PaperFundBootstrapStatus.CREATED
    assert second_status is PaperFundBootstrapStatus.EXISTING
    assert first.fund_identity == second.fund_identity
    assert second.cash_usdt == INITIAL_CASH_USDT
    assert second.positions == ()
    assert second.replayed_record_count == 1
    assert len(ledger.list_fund_creations()) == 1
    assert REAL_CAPITAL == 0


def test_signal_ledger_observation_is_read_only(tmp_path: Path) -> None:
    path = _signal_ledger(tmp_path / "signal.sqlite3")
    before = path.read_bytes()

    observation = observe_signal_ledger(path)

    assert observation.freeze_count == 1
    assert observation.lifecycle_count == 0
    assert observation.outcome_count == 0
    assert observation.latest_signal_freeze_identity == "s" * 64
    assert observation.latest_frozen_at_ms == 110
    assert observation.latest_symbol == "BTCUSDT"
    assert observation.latest_timeframe == "15m"
    assert observation.latest_signal_state == "watch"
    assert observation.latest_direction == "bullish"
    assert path.read_bytes() == before


def test_empty_signal_ledger_has_explicit_no_latest_state(tmp_path: Path) -> None:
    path = _signal_ledger(tmp_path / "empty_signal.sqlite3", with_signal=False)

    observation = observe_signal_ledger(path)

    assert observation.freeze_count == 0
    assert observation.latest_signal_freeze_identity is None
    assert observation.latest_signal_state is None


def test_missing_signal_ledger_fails_before_paper_fund_creation(
    tmp_path: Path,
) -> None:
    paper_path = tmp_path / "paper.sqlite3"
    with pytest.raises(PaperRuntimeError, match="does not exist"):
        run_paper_runtime_tick(
            paper_ledger_path=paper_path,
            signal_ledger_path=tmp_path / "missing.sqlite3",
            created_at_ms=1,
        )
    assert not paper_path.exists()


def test_missing_required_signal_table_fails_closed(tmp_path: Path) -> None:
    signal_path = tmp_path / "malformed.sqlite3"
    with sqlite3.connect(signal_path) as connection:
        connection.execute("CREATE TABLE signal_freezes (x INTEGER)")

    with pytest.raises(PaperRuntimeError, match="missing required table"):
        observe_signal_ledger(signal_path)


def test_runtime_tick_observes_but_does_not_trade(tmp_path: Path) -> None:
    signal_path = _signal_ledger(tmp_path / "signal.sqlite3")
    paper_path = tmp_path / "paper.sqlite3"

    first = run_paper_runtime_tick(
        paper_ledger_path=paper_path,
        signal_ledger_path=signal_path,
        created_at_ms=100,
    )
    second = run_paper_runtime_tick(
        paper_ledger_path=paper_path,
        signal_ledger_path=signal_path,
        created_at_ms=999,
    )

    ledger = PaperFundLedger(paper_path)
    assert first.bootstrap_status is PaperFundBootstrapStatus.CREATED
    assert second.bootstrap_status is PaperFundBootstrapStatus.EXISTING
    assert first.trade_policy_activated is False
    assert second.trade_policy_activated is False
    assert reconstruct_paper_fund_state(ledger).replayed_record_count == 1
    assert len(ledger.replay()) == 1


def test_runtime_core_has_no_network_or_order_surface() -> None:
    source = inspect.getsource(paper_runtime).lower()
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
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert paper_runtime.REAL_CAPITAL == REAL_CAPITAL == 0
