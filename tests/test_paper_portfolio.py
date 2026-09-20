"""Tests for the strictly read-only marked paper portfolio view."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import portfolio as paper_portfolio
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    ExecutionCostAssumptions,
    PaperAction,
    PaperSymbol,
    build_decision_intent,
    build_fund_creation,
    build_position_cash_mutation,
    build_simulated_fill,
)
from crypto_signal.paper.portfolio import (
    PAPER_PORTFOLIO_VIEW_VERSION,
    PaperPortfolioAvailability,
    read_paper_portfolio_snapshot,
)


def _empty_fund(tmp_path):
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    creation = build_fund_creation(created_at_ms=1)
    ledger.append_fund_creation(creation)
    return ledger, creation


def _fund_with_btc_position(tmp_path):
    ledger, creation = _empty_fund(tmp_path)
    decision = build_decision_intent(
        fund_identity=creation.record_identity,
        decided_at_ms=100,
        action=PaperAction.BUY,
        reason="portfolio test",
        invalidation_context="test only",
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.1"),
        reference_price=Decimal("100"),
    )
    ledger.append_decision_intent(decision)
    fill = build_simulated_fill(
        fund_identity=creation.record_identity,
        decision_identity=decision.record_identity,
        filled_at_ms=101,
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        quantity=Decimal("0.1"),
        reference_price=Decimal("100"),
        simulated_fill_price=Decimal("100.1"),
        costs=ExecutionCostAssumptions(
            fee_usdt=Decimal("0.01"),
            spread_usdt=Decimal("0.005"),
            slippage_usdt=Decimal("0.005"),
        ),
        venue_reference="test-venue",
    )
    ledger.append_simulated_fill(fill)
    mutation = build_position_cash_mutation(
        fund_identity=creation.record_identity,
        source_identity=fill.record_identity,
        mutated_at_ms=102,
        cash_before_usdt=Decimal("100.00"),
        cash_after_usdt=Decimal("89.97"),
        positions_before=(),
        positions_after={PaperSymbol.BTCUSDT: Decimal("0.1")},
    )
    ledger.append_position_cash_mutation(mutation)
    return ledger, creation


def _init_candle_cache(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE candles (
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                close_time_ms INTEGER NOT NULL,
                open TEXT NOT NULL,
                high TEXT NOT NULL,
                low TEXT NOT NULL,
                close TEXT NOT NULL,
                volume TEXT NOT NULL,
                quote_volume TEXT,
                trade_count INTEGER,
                is_closed INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_timestamp_ms INTEGER NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                adapter_version TEXT NOT NULL,
                PRIMARY KEY (
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    open_time_ms
                )
            )
            """
        )


def _insert_candle(
    path,
    *,
    open_time_ms: int,
    close_time_ms: int,
    close: str,
    ingested_at_ms: int,
    source_timestamp_ms: int,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO candles VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                Exchange.BINANCE.value,
                MarketType.SPOT.value,
                PaperSymbol.BTCUSDT.value,
                "15m",
                open_time_ms,
                close_time_ms,
                "100",
                "130",
                "90",
                close,
                "1",
                None,
                1,
                1,
                "rest",
                source_timestamp_ms,
                ingested_at_ms,
                "adapter.test.v1",
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
            )
        )


def test_cash_only_portfolio_has_factual_zero_nav_return_without_marks(tmp_path) -> None:
    ledger, creation = _empty_fund(tmp_path)

    snapshot = read_paper_portfolio_snapshot(
        paper_ledger_path=ledger.path,
        candle_cache_path=tmp_path / "missing-candles.sqlite3",
        observed_at_ms=500,
    )

    assert snapshot.version == PAPER_PORTFOLIO_VIEW_VERSION
    assert snapshot.fund_identity == creation.record_identity
    assert snapshot.availability is PaperPortfolioAvailability.AVAILABLE
    assert snapshot.cash_usdt == Decimal("100.00")
    assert snapshot.positions == ()
    assert snapshot.missing_mark_symbols == ()
    assert snapshot.marked_positions_value_usdt == Decimal(0)
    assert snapshot.nav_usdt == Decimal("100.00")
    assert snapshot.pnl_usdt == Decimal("0.00")
    assert snapshot.total_return_fraction == Decimal("0")
    assert snapshot.decision_count == 0
    assert snapshot.simulated_fill_count == 0
    assert snapshot.replayed_record_count == 1
    assert snapshot.real_capital == REAL_CAPITAL == 0


def test_marked_portfolio_uses_latest_closed_real_candle_asof_observation(tmp_path) -> None:
    ledger, _ = _fund_with_btc_position(tmp_path)
    candles = tmp_path / "candles.sqlite3"
    _init_candle_cache(candles)
    _insert_candle(
        candles,
        open_time_ms=100,
        close_time_ms=300,
        close="120",
        ingested_at_ms=301,
        source_timestamp_ms=300,
    )
    _insert_candle(
        candles,
        open_time_ms=400,
        close_time_ms=600,
        close="130",
        ingested_at_ms=601,
        source_timestamp_ms=600,
    )

    snapshot = read_paper_portfolio_snapshot(
        paper_ledger_path=ledger.path,
        candle_cache_path=candles,
        observed_at_ms=500,
    )

    assert snapshot.availability is PaperPortfolioAvailability.AVAILABLE
    assert len(snapshot.positions) == 1
    position = snapshot.positions[0]
    assert position.symbol is PaperSymbol.BTCUSDT
    assert position.quantity == Decimal("0.1")
    assert position.mark is not None
    assert position.mark.price == Decimal("120")
    assert position.mark.source_candle_close_time_ms == 300
    assert position.mark.price_field == "close"
    assert position.marked_value_usdt == Decimal("12.0")
    assert snapshot.cash_usdt == Decimal("89.97")
    assert snapshot.marked_positions_value_usdt == Decimal("12.0")
    assert snapshot.nav_usdt == Decimal("101.97")
    assert snapshot.pnl_usdt == Decimal("1.97")
    assert snapshot.total_return_fraction == Decimal("0.0197")
    assert snapshot.decision_count == 1
    assert snapshot.simulated_fill_count == 1
    assert snapshot.nav_snapshot_count == 0
    assert snapshot.replayed_record_count == 4
    assert snapshot.real_capital == REAL_CAPITAL == 0


def test_missing_position_mark_is_explicit_and_suppresses_aggregate_performance(
    tmp_path,
) -> None:
    ledger, _ = _fund_with_btc_position(tmp_path)
    candles = tmp_path / "candles.sqlite3"
    _init_candle_cache(candles)

    snapshot = read_paper_portfolio_snapshot(
        paper_ledger_path=ledger.path,
        candle_cache_path=candles,
        observed_at_ms=500,
    )

    assert snapshot.availability is PaperPortfolioAvailability.MISSING_MARKS
    assert snapshot.missing_mark_symbols == (PaperSymbol.BTCUSDT,)
    assert snapshot.positions[0].mark is None
    assert snapshot.positions[0].marked_value_usdt is None
    assert snapshot.marked_positions_value_usdt is None
    assert snapshot.nav_usdt is None
    assert snapshot.pnl_usdt is None
    assert snapshot.total_return_fraction is None


def test_portfolio_reader_is_strictly_read_only(tmp_path) -> None:
    ledger, _ = _fund_with_btc_position(tmp_path)
    candles = tmp_path / "candles.sqlite3"
    _init_candle_cache(candles)
    _insert_candle(
        candles,
        open_time_ms=100,
        close_time_ms=300,
        close="120",
        ingested_at_ms=301,
        source_timestamp_ms=300,
    )
    before = _paper_counts(ledger.path)

    first = read_paper_portfolio_snapshot(
        paper_ledger_path=ledger.path,
        candle_cache_path=candles,
        observed_at_ms=500,
    )
    second = read_paper_portfolio_snapshot(
        paper_ledger_path=ledger.path,
        candle_cache_path=candles,
        observed_at_ms=500,
    )
    after = _paper_counts(ledger.path)

    assert first == second
    assert before == after

    source = inspect.getsource(paper_portfolio).lower()
    forbidden = (
        "insert into",
        "update ",
        "delete from",
        "create table",
        "paperfundledger",
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
    assert paper_portfolio.REAL_CAPITAL == REAL_CAPITAL == 0
