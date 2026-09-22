from __future__ import annotations

from decimal import Decimal

from crypto_signal.data.derivatives import (
    DerivativesInstrumentType,
    build_derivatives_observation,
)
from crypto_signal.data.market_tape import (
    MarketTapeStore,
    MarketTapeWriteDisposition,
)
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType


def _book(*, event_at_ms: int, sequence: int):
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 1,
        response_time_ms=event_at_ms + 2,
        ingested_at_ms=event_at_ms + 3,
        update_id=sequence,
        sequence=sequence,
        bids=(
            OrderBookLevel(Decimal("100"), Decimal("2")),
            OrderBookLevel(Decimal("99"), Decimal("3")),
        ),
        asks=(
            OrderBookLevel(Decimal("101"), Decimal("2.5")),
            OrderBookLevel(Decimal("102"), Decimal("4")),
        ),
        source=DataSource.REST,
        adapter_version="test-book/1",
    )


def _trade(*, event_at_ms: int, sequence: int, exec_id: str):
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id=exec_id,
        sequence=sequence,
        aggressor_side=(
            AggressorSide.BUY if sequence % 2 else AggressorSide.SELL
        ),
        price=Decimal("100.5"),
        size=Decimal("0.25"),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms + 1,
        ingested_at_ms=event_at_ms + 2,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.REST,
        adapter_version="test-trade/1",
    )


def _derivatives(*, event_at_ms: int, oi: str):
    return build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        funding_rate=Decimal("0.0001"),
        open_interest=Decimal(oi),
        mark_price=Decimal("100.7"),
        index_price=Decimal("100.5"),
        funding_interval_hours=8,
        source=DataSource.REST,
        source_timestamp_ms=event_at_ms + 1,
        ingested_at_ms=event_at_ms + 2,
        adapter_version="test-derivatives/1",
    )


def test_market_tape_is_append_only_and_idempotent(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    book = _book(event_at_ms=1_000, sequence=10)
    trade = _trade(event_at_ms=1_001, sequence=20, exec_id="trade-1")
    derivative = _derivatives(event_at_ms=1_002, oi="1234")

    assert store.append_orderbook(book) is MarketTapeWriteDisposition.INSERTED
    assert store.append_trade(trade) is MarketTapeWriteDisposition.INSERTED
    assert store.append_derivatives(derivative) is MarketTapeWriteDisposition.INSERTED

    assert store.append_orderbook(book) is MarketTapeWriteDisposition.UNCHANGED
    assert store.append_trade(trade) is MarketTapeWriteDisposition.UNCHANGED
    assert store.append_derivatives(derivative) is MarketTapeWriteDisposition.UNCHANGED

    counts = store.counts()
    assert counts.orderbooks == 1
    assert counts.trades == 1
    assert counts.derivatives == 1
    assert counts.total == 3
    assert store.quick_check() is True
    assert store.latest_event_at_ms() == 1_002


def test_market_tape_recent_reads_round_trip_exact_models(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")

    books = (
        _book(event_at_ms=1_000, sequence=10),
        _book(event_at_ms=2_000, sequence=11),
    )
    trades = (
        _trade(event_at_ms=1_100, sequence=20, exec_id="trade-1"),
        _trade(event_at_ms=2_100, sequence=21, exec_id="trade-2"),
    )
    derivatives = (
        _derivatives(event_at_ms=1_200, oi="1000"),
        _derivatives(event_at_ms=2_200, oi="1100"),
    )

    for book in books:
        store.append_orderbook(book)
    for trade in trades:
        store.append_trade(trade)
    for observation in derivatives:
        store.append_derivatives(observation)

    assert store.recent_orderbooks(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
    ) == books
    assert store.recent_trades(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
    ) == trades
    assert store.recent_derivatives(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
    ) == derivatives


def test_market_tape_microstructure_snapshot_batches_book_and_trades(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    book = _book(event_at_ms=1_000, sequence=10)
    trades = (
        _trade(event_at_ms=1_001, sequence=20, exec_id="trade-1"),
        _trade(event_at_ms=1_002, sequence=21, exec_id="trade-2"),
    )

    book_result, trade_results = store.append_microstructure_snapshot(book, trades)

    assert book_result is MarketTapeWriteDisposition.INSERTED
    assert trade_results == (
        MarketTapeWriteDisposition.INSERTED,
        MarketTapeWriteDisposition.INSERTED,
    )
    assert store.counts().total == 3


def test_market_tape_read_limit_is_bounded(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    for index in range(5):
        store.append_trade(
            _trade(
                event_at_ms=1_000 + index,
                sequence=20 + index,
                exec_id=f"trade-{index}",
            )
        )

    recent = store.recent_trades(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        limit=2,
    )
    assert tuple(item.exec_id for item in recent) == ("trade-3", "trade-4")


def test_market_tape_deduplicates_same_exchange_trade_seen_later(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    first = build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id="stable-exec",
        sequence=99,
        aggressor_side=AggressorSide.BUY,
        price=Decimal("100.5"),
        size=Decimal("0.25"),
        event_at_ms=10_000,
        source_timestamp_ms=10_010,
        ingested_at_ms=10_020,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.REST,
        adapter_version="test-trade/1",
    )
    later_poll = build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id="stable-exec",
        sequence=99,
        aggressor_side=AggressorSide.BUY,
        price=Decimal("100.5"),
        size=Decimal("0.25"),
        event_at_ms=10_000,
        source_timestamp_ms=10_110,
        ingested_at_ms=10_120,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.REST,
        adapter_version="test-trade/1",
    )

    assert first.trade_identity != later_poll.trade_identity
    assert store.append_trade(first) is MarketTapeWriteDisposition.INSERTED
    assert store.append_trade(later_poll) is MarketTapeWriteDisposition.UNCHANGED
    assert store.counts().trades == 1


def test_market_tape_deduplicates_replayed_historical_oi_row(tmp_path) -> None:
    store = MarketTapeStore(tmp_path / "market_tape.sqlite3")
    first = build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        event_at_ms=20_000,
        funding_rate=None,
        open_interest=Decimal("1234"),
        mark_price=None,
        index_price=None,
        funding_interval_hours=None,
        source=DataSource.REST,
        source_timestamp_ms=20_100,
        ingested_at_ms=20_110,
        adapter_version="test-derivatives/1",
    )
    later_poll = build_derivatives_observation(
        exchange=Exchange.BYBIT,
        instrument_type=DerivativesInstrumentType.LINEAR_PERPETUAL,
        symbol="BTCUSDT",
        event_at_ms=20_000,
        funding_rate=None,
        open_interest=Decimal("1234"),
        mark_price=None,
        index_price=None,
        funding_interval_hours=None,
        source=DataSource.REST,
        source_timestamp_ms=20_500,
        ingested_at_ms=20_510,
        adapter_version="test-derivatives/1",
    )

    assert first.observation_identity != later_poll.observation_identity
    assert store.append_derivatives(first) is MarketTapeWriteDisposition.INSERTED
    assert (
        store.append_derivatives(later_poll)
        is MarketTapeWriteDisposition.UNCHANGED
    )
    assert store.counts().derivatives == 1
