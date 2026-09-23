from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.price_cvd_divergence import (
    DivergenceConfig,
    DivergenceState,
    build_divergence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import TemporalFlowConfig


def _book(seq: int, at_ms: int, bid: str, *, ingest: int | None = None, symbol: str = "BTCUSDT"):
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        event_at_ms=at_ms,
        source_timestamp_ms=at_ms + 1,
        response_time_ms=at_ms + 2,
        ingested_at_ms=at_ms + 3 if ingest is None else ingest,
        update_id=seq,
        sequence=seq,
        bids=(OrderBookLevel(price=Decimal(bid), size=Decimal(10)),),
        asks=(OrderBookLevel(price=Decimal(bid) + 1, size=Decimal(10)),),
        source=DataSource.WEBSOCKET,
        adapter_version="m3-divergence-test/1",
    )


def _trade(seq: int, at_ms: int, side: AggressorSide, *, ingest: int | None = None):
    return build_public_trade_observation(
        exchange=Exchange.BYBIT, market_type=MarketType.SPOT,
        symbol="BTCUSDT", exec_id=f"div-{seq}", sequence=seq,
        aggressor_side=side, price=Decimal(100), size=Decimal(2),
        event_at_ms=at_ms, source_timestamp_ms=at_ms + 1,
        ingested_at_ms=at_ms + 2 if ingest is None else ingest,
        is_block_trade=False, is_rpi_trade=False,
        source=DataSource.WEBSOCKET, adapter_version="m3-divergence-test/1",
    )


def _books(up: bool = True):
    prices = ["100", "100.25", "100.5", "100.75", "101"]
    if not up:
        prices.reverse()
    return tuple(
        _book(i + 1, 8000 + i * 1000, price)
        for i, price in enumerate(prices)
    )


def _trades(side: AggressorSide = AggressorSide.SELL):
    return tuple(
        _trade(i + 1, at_ms, side)
        for i, at_ms in enumerate((8100, 8800, 9500, 10400, 11700))
    )


def _config():
    return DivergenceConfig(
        window_ms=5000, minimum_snapshots=3,
        max_book_age_ms=2000, max_book_gap_ms=2000,
        min_price_move_bps=Decimal(5),
        min_opposing_imbalance=Decimal("0.20"),
    )


def _flow_config():
    return TemporalFlowConfig(
        window_ms=5000, bucket_ms=1000, minimum_trades=5,
        max_trade_age_ms=2000, max_trade_gap_ms=2000,
        large_print_min_notional=Decimal(10000),
    )


def _freeze(books=None, trades=None, as_of_ms=12100):
    return build_divergence_freeze(
        _books() if books is None else books,
        _trades() if trades is None else trades,
        as_of_ms=as_of_ms, config=_config(), flow_config=_flow_config(),
    )


def test_bearish_candidate_requires_independent_price_up_and_cvd_down():
    frozen = _freeze()
    analysis = frozen.analysis
    assert analysis.state is DivergenceState.BEARISH_CANDIDATE
    assert analysis.price_move_bps is not None
    assert analysis.price_move_bps > Decimal(5)
    assert analysis.window_local_cvd is not None
    assert analysis.window_local_cvd < 0
    assert analysis.taker_imbalance == -1
    assert analysis.snapshot_count == 5
    assert len(analysis.evidence_identity) == len(frozen.freeze_identity) == 64
    assert "candidate_not_reversal_prediction" in analysis.uncertainty_flags


def test_bullish_candidate_requires_price_down_and_cvd_up():
    analysis = _freeze(_books(up=False), _trades(AggressorSide.BUY)).analysis
    assert analysis.state is DivergenceState.BULLISH_CANDIDATE
    assert analysis.price_move_bps is not None
    assert analysis.price_move_bps < -Decimal(5)


def test_matching_direction_never_generates_divergence():
    analysis = _freeze(_books(), _trades(AggressorSide.BUY)).analysis
    assert analysis.state is DivergenceState.NONE
    assert "no_qualified_divergence" in analysis.uncertainty_flags


def test_reversed_input_and_future_or_late_evidence_leave_freeze_unchanged():
    original = _freeze()
    books = _books()
    trades = _trades()
    future_book = _book(99, 12200, "200")
    late_book = _book(100, 10500, "200", ingest=12300)
    future_trade = _trade(99, 12200, AggressorSide.BUY)
    late_trade = _trade(100, 10500, AggressorSide.BUY, ingest=12300)
    changed = _freeze(
        tuple(reversed((*books, future_book, late_book))),
        tuple(reversed((*trades, future_trade, late_trade))),
    )
    assert changed == original


def test_sparse_and_stale_independent_price_fail_closed():
    sparse = _freeze(_books()[:2]).analysis
    assert sparse.state is DivergenceState.UNRESOLVED
    assert sparse.price_move_bps is None
    assert "insufficient_orderbook_snapshots" in sparse.uncertainty_flags

    stale = _freeze(_books()[:-1]).analysis
    assert stale.state is DivergenceState.UNRESOLVED
    assert "price_does_not_cover_trade_window" in stale.uncertainty_flags


def test_duplicate_and_mixed_market_context_fail_closed():
    books = _books()
    with pytest.raises(ValueError, match="duplicate divergence book identity"):
        _freeze((*books, books[0]))
    eth_book = _book(100, 10500, "100", symbol="ETHUSDT")
    with pytest.raises(ValueError, match="mixed divergence market context"):
        _freeze((*books, eth_book))


def test_freeze_and_evidence_identity_tampering_fail_closed():
    frozen = _freeze()
    with pytest.raises(ValueError, match="divergence freeze identity mismatch"):
        replace(frozen, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="divergence evidence identity mismatch"):
        replace(frozen.analysis, evidence_identity="f" * 64)


def test_no_orderbook_coverage_disallows_claiming_measured_divergence():
    shifted = tuple(
        _book(i + 1, 9000 + i * 750, price)
        for i, price in enumerate(("100", "100.2", "100.4", "100.6", "101"))
    )
    result = _freeze(shifted).analysis
    assert result.state is DivergenceState.UNRESOLVED
    assert "price_does_not_cover_trade_window" in result.uncertainty_flags


def test_research_scope_and_window_identity_are_fail_closed():
    with pytest.raises(ValueError, match="unmatched evidence windows"):
        build_divergence_freeze(
            _books(), _trades(), as_of_ms=12100,
            config=_config(), flow_config=TemporalFlowConfig(),
        )
    analysis = _freeze().analysis
    assert not hasattr(analysis, "trade_action")
    assert not hasattr(analysis, "win_probability")
    assert not hasattr(analysis, "confirmed_absorption")
