"""Tests for the strictly read-only paper mission-control composition."""

from __future__ import annotations

import hashlib
import inspect
import sqlite3

from crypto_signal.paper import mission_control as paper_mission_control
from crypto_signal.paper.activation import activate_paper_policy
from crypto_signal.paper.event_scanner import (
    PAPER_SIGNAL_EVENT_SCANNER_VERSION,
    PaperSignalEventScanResult,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import REAL_CAPITAL, build_fund_creation
from crypto_signal.paper.performance import PaperTradePerformanceStatus
from crypto_signal.paper.portfolio import PaperPortfolioAvailability
from crypto_signal.paper.state import reconstruct_paper_fund_state


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _paper(tmp_path):
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


def _init_signal_db(path) -> None:
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


def _insert_overview_freeze(
    path,
    *,
    suffix: str,
    as_of_ms: int,
    frozen_at_ms: int,
) -> None:
    with sqlite3.connect(path) as connection:
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
                _sha(f"bundle:{suffix}"),
                _sha(f"freeze:{suffix}"),
                "binance",
                "spot",
                "BTCUSDT",
                "15m",
                as_of_ms,
                max(0, as_of_ms - 1),
                "watch",
                "bullish",
                "{}",
                frozen_at_ms,
            ),
        )


def _insert_4h_freeze(
    path,
    *,
    exchange: str,
    suffix: str,
    as_of_ms: int,
    frozen_at_ms: int,
) -> None:
    with sqlite3.connect(path) as connection:
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
                _sha(f"bundle:4h:{exchange}:{suffix}"),
                _sha(f"freeze:4h:{exchange}:{suffix}"),
                exchange,
                "spot",
                "BTCUSDT",
                "4h",
                as_of_ms,
                max(0, as_of_ms - 1),
                "watch",
                "bullish",
                "{}",
                frozen_at_ms,
            ),
        )


def _paper_counts(path) -> tuple[int, ...]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        return tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "paper_fund_creations",
                "paper_decision_intents",
                "paper_simulated_fills",
                "paper_position_cash_mutations",
                "paper_nav_snapshots",
                "paper_replay_index",
                "paper_activation_state",
                "paper_processed_events",
            )
        )


def test_mission_control_composes_cash_only_truth_without_fabricated_success(
    tmp_path,
) -> None:
    ledger, activation = _paper(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    before = _paper_counts(ledger.path)

    first = paper_mission_control.read_paper_mission_control_snapshot(
        paper_ledger_path=ledger.path,
        signal_ledger_path=signal_db,
        candle_cache_path=tmp_path / "missing-candles.sqlite3",
        observed_at_ms=500,
    )
    second = paper_mission_control.read_paper_mission_control_snapshot(
        paper_ledger_path=ledger.path,
        signal_ledger_path=signal_db,
        candle_cache_path=tmp_path / "missing-candles.sqlite3",
        observed_at_ms=500,
    )
    after = _paper_counts(ledger.path)

    assert first == second
    assert before == after
    assert first.activation_identity == activation.activation_identity
    assert first.activation_cutoff_ms == activation.activation_cutoff_ms
    assert first.signal_stream.total_freeze_count == 0
    assert tuple(
        (item.symbol.value, item.status.value)
        for item in first.decision_cadence
    ) == (
        ("BTCUSDT", "no_4h_evidence"),
        ("ETHUSDT", "no_4h_evidence"),
        ("SOLUSDT", "no_4h_evidence"),
    )
    assert first.eligible_post_activation_freezes == 0
    assert first.incomplete_provider_pairs == 0
    assert first.processed_event_skips == 0
    assert first.candidates == ()
    assert first.ready_candidate_count == 0
    assert first.attention_required is False
    assert first.portfolio.availability is PaperPortfolioAvailability.AVAILABLE
    assert first.portfolio.cash_usdt == first.portfolio.nav_usdt
    assert first.portfolio.positions == ()
    assert first.performance.status is PaperTradePerformanceStatus.NOT_YET_MEASURED
    assert first.performance.closed_trade_count == 0
    assert first.performance.win_rate_fraction is None
    assert first.trade_policy == "NOT_ACTIVATED"
    assert first.real_capital == REAL_CAPITAL == 0


def test_signal_stream_overview_is_point_in_time(tmp_path) -> None:
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_overview_freeze(
        signal_db,
        suffix="past",
        as_of_ms=90,
        frozen_at_ms=100,
    )
    _insert_overview_freeze(
        signal_db,
        suffix="future",
        as_of_ms=590,
        frozen_at_ms=600,
    )

    overview = paper_mission_control.read_paper_signal_stream_overview(
        signal_ledger_path=signal_db,
        observed_at_ms=500,
    )

    assert overview.total_freeze_count == 1
    assert overview.latest_signal_freeze_identity == _sha("freeze:past")
    assert overview.latest_frozen_at_ms == 100
    assert overview.latest_signal_as_of_ms == 90
    assert overview.latest_exchange == "binance"
    assert overview.latest_symbol == "BTCUSDT"
    assert overview.latest_timeframe == "15m"
    assert overview.latest_signal_state == "watch"
    assert overview.latest_direction == "bullish"
    assert overview.latest_freeze_age_ms == 400


def test_mission_control_surface_is_strictly_read_only() -> None:
    source = inspect.getsource(paper_mission_control).lower()
    forbidden = (
        "insert into",
        "update ",
        "delete from",
        "create table",
        "append_",
        "commit_",
        "httpx",
        "requests",
        "place_order",
        "submit_order",
        "cancel_order",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert paper_mission_control.REAL_CAPITAL == REAL_CAPITAL == 0


def test_decision_cadence_explains_pre_activation_pair(tmp_path) -> None:
    _, activation = _paper(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_4h_freeze(
        signal_db,
        exchange="binance",
        suffix="past",
        as_of_ms=90,
        frozen_at_ms=95,
    )
    _insert_4h_freeze(
        signal_db,
        exchange="bybit",
        suffix="past",
        as_of_ms=90,
        frozen_at_ms=96,
    )
    scan = PaperSignalEventScanResult(
        scanner_version=PAPER_SIGNAL_EVENT_SCANNER_VERSION,
        activation_identity=activation.activation_identity,
        eligible_freeze_count=0,
        incomplete_pair_count=0,
        processed_skip_count=0,
        candidates=(),
        real_capital=REAL_CAPITAL,
    )

    readiness = paper_mission_control.read_paper_decision_cadence_readiness(
        signal_ledger_path=signal_db,
        activation=activation,
        scan=scan,
        observed_at_ms=500,
    )

    btc = readiness[0]
    assert btc.symbol.value == "BTCUSDT"
    assert btc.status.value == "pre_activation_pair"
    assert btc.binance is not None
    assert btc.bybit is not None
    assert btc.binance.signal_as_of_ms == 90
    assert btc.bybit.signal_as_of_ms == 90
    assert btc.paired_as_of_ms == 90
    assert btc.candidate_available is False
    assert readiness[1].status.value == "no_4h_evidence"
    assert readiness[2].status.value == "no_4h_evidence"


def test_decision_cadence_explains_waiting_provider_pair(tmp_path) -> None:
    _, activation = _paper(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_4h_freeze(
        signal_db,
        exchange="binance",
        suffix="only-binance",
        as_of_ms=150,
        frozen_at_ms=160,
    )
    scan = PaperSignalEventScanResult(
        scanner_version=PAPER_SIGNAL_EVENT_SCANNER_VERSION,
        activation_identity=activation.activation_identity,
        eligible_freeze_count=1,
        incomplete_pair_count=1,
        processed_skip_count=0,
        candidates=(),
        real_capital=REAL_CAPITAL,
    )

    readiness = paper_mission_control.read_paper_decision_cadence_readiness(
        signal_ledger_path=signal_db,
        activation=activation,
        scan=scan,
        observed_at_ms=500,
    )

    btc = readiness[0]
    assert btc.status.value == "waiting_provider_pair"
    assert btc.binance is not None
    assert btc.bybit is None
    assert btc.paired_as_of_ms is None
    assert btc.candidate_available is False


def test_decision_cadence_explains_provider_asof_mismatch(tmp_path) -> None:
    _, activation = _paper(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_4h_freeze(
        signal_db,
        exchange="binance",
        suffix="binance-newer",
        as_of_ms=200,
        frozen_at_ms=210,
    )
    _insert_4h_freeze(
        signal_db,
        exchange="bybit",
        suffix="bybit-older",
        as_of_ms=150,
        frozen_at_ms=160,
    )
    scan = PaperSignalEventScanResult(
        scanner_version=PAPER_SIGNAL_EVENT_SCANNER_VERSION,
        activation_identity=activation.activation_identity,
        eligible_freeze_count=2,
        incomplete_pair_count=2,
        processed_skip_count=0,
        candidates=(),
        real_capital=REAL_CAPITAL,
    )

    readiness = paper_mission_control.read_paper_decision_cadence_readiness(
        signal_ledger_path=signal_db,
        activation=activation,
        scan=scan,
        observed_at_ms=500,
    )

    btc = readiness[0]
    assert btc.status.value == "provider_asof_mismatch"
    assert btc.binance is not None
    assert btc.bybit is not None
    assert btc.binance.signal_as_of_ms == 200
    assert btc.bybit.signal_as_of_ms == 150
    assert btc.paired_as_of_ms is None
    assert btc.candidate_available is False
