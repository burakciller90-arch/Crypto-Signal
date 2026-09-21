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


def _book(**overrides):
    payload = {
        "exchange": Exchange.BYBIT,
        "market_type": MarketType.SPOT,
        "symbol": "BTCUSDT",
        "event_at_ms": 1_000,
        "source_timestamp_ms": 1_010,
        "response_time_ms": 1_020,
        "ingested_at_ms": 1_030,
        "update_id": 10,
        "sequence": 20,
        "bids": (
            OrderBookLevel(price=Decimal(100), size=Decimal(2)),
            OrderBookLevel(price=Decimal(99), size=Decimal(1)),
        ),
        "asks": (
            OrderBookLevel(price=Decimal(101), size=Decimal(1)),
            OrderBookLevel(price=Decimal(102), size=Decimal(2)),
        ),
        "source": DataSource.REST,
        "adapter_version": "test/1",
    }
    payload.update(overrides)
    return build_orderbook_snapshot(**payload)


def _trade(**overrides):
    payload = {
        "exchange": Exchange.BYBIT,
        "market_type": MarketType.SPOT,
        "symbol": "BTCUSDT",
        "exec_id": "trade-1",
        "sequence": 20,
        "aggressor_side": AggressorSide.BUY,
        "price": Decimal("100.5"),
        "size": Decimal("0.5"),
        "event_at_ms": 1_000,
        "source_timestamp_ms": 1_010,
        "ingested_at_ms": 1_030,
        "is_block_trade": False,
        "is_rpi_trade": False,
        "source": DataSource.REST,
        "adapter_version": "test/1",
    }
    payload.update(overrides)
    return build_public_trade_observation(**payload)


def test_orderbook_identity_is_deterministic() -> None:
    first = _book()
    second = _book()

    assert first == second
    assert len(first.snapshot_identity) == 64
    assert first.bids[0].notional == Decimal(200)


def test_orderbook_identity_tampering_fails_closed() -> None:
    snapshot = _book()

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(snapshot, snapshot_identity="f" * 64)


def test_orderbook_rejects_crossed_or_unsorted_levels() -> None:
    with pytest.raises(ValueError, match="must not be crossed"):
        _book(
            bids=(OrderBookLevel(price=Decimal(101), size=Decimal(1)),),
            asks=(OrderBookLevel(price=Decimal(100), size=Decimal(1)),),
        )

    with pytest.raises(ValueError, match="strictly descending"):
        _book(
            bids=(
                OrderBookLevel(price=Decimal(99), size=Decimal(1)),
                OrderBookLevel(price=Decimal(100), size=Decimal(1)),
            )
        )


def test_orderbook_requires_source_time_chain() -> None:
    with pytest.raises(ValueError, match="event cannot postdate"):
        _book(event_at_ms=1_020, source_timestamp_ms=1_010)

    with pytest.raises(ValueError, match="cannot postdate response"):
        _book(source_timestamp_ms=1_030, response_time_ms=1_020)


def test_public_trade_identity_and_eligibility_are_deterministic() -> None:
    regular = _trade()
    rpi = _trade(exec_id="trade-rpi", is_rpi_trade=True)
    block = _trade(exec_id="trade-block", is_block_trade=True)

    assert len(regular.trade_identity) == 64
    assert regular.notional == Decimal("50.25")
    assert regular.book_eligible is True
    assert rpi.book_eligible is False
    assert block.book_eligible is False


def test_public_trade_identity_tampering_fails_closed() -> None:
    trade = _trade()

    with pytest.raises(ValueError, match="identity mismatch"):
        replace(trade, trade_identity="f" * 64)


def test_public_trade_rejects_invalid_measurements_or_time() -> None:
    with pytest.raises(ValueError, match="price must be finite and positive"):
        _trade(price=Decimal(0))

    with pytest.raises(ValueError, match="size must be finite and positive"):
        _trade(size=Decimal(-1))

    with pytest.raises(ValueError, match="cannot postdate"):
        _trade(event_at_ms=2_000, source_timestamp_ms=1_000)
