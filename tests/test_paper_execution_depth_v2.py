from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.microstructure import OrderBookLevel, build_orderbook_snapshot
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.paper.execution_depth_v2 import (
    DepthExecutionRejectedError,
    DepthExecutionStatus,
    simulate_depth_execution,
)
from crypto_signal.paper.models import PaperAction


def _book(*, ingested_at_ms: int = 1_003):
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=1_000,
        source_timestamp_ms=1_001,
        response_time_ms=1_002,
        ingested_at_ms=ingested_at_ms,
        update_id=10,
        sequence=20,
        bids=(
            OrderBookLevel(Decimal(100), Decimal("1.5")),
            OrderBookLevel(Decimal(99), Decimal(2)),
        ),
        asks=(
            OrderBookLevel(Decimal(101), Decimal(1)),
            OrderBookLevel(Decimal(103), Decimal(2)),
        ),
        source=DataSource.REST,
        adapter_version="fp4-test/1",
    )


def test_buy_consumes_asks_and_reconciles_exact_vwap() -> None:
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal(2),
        orderbook=_book(),
        execution_cutoff_ms=1_003,
        partial_fills_enabled=True,
    )

    assert outcome.status is DepthExecutionStatus.FULL
    assert outcome.filled_quantity == Decimal(2)
    assert outcome.unfilled_quantity == Decimal(0)
    assert outcome.fill_notional == Decimal(204)
    assert outcome.average_fill_price == Decimal(102)
    assert tuple(
        (level.price, level.consumed_quantity) for level in outcome.consumed_levels
    ) == ((Decimal(101), Decimal(1)), (Decimal(103), Decimal(1)))


def test_sell_consumes_bids_best_price_first() -> None:
    outcome = simulate_depth_execution(
        action=PaperAction.EXIT,
        requested_quantity=Decimal(2),
        orderbook=_book(),
        execution_cutoff_ms=1_003,
        partial_fills_enabled=True,
    )

    assert outcome.status is DepthExecutionStatus.FULL
    assert outcome.fill_notional == Decimal("199.5")
    assert outcome.average_fill_price == Decimal("99.75")
    assert tuple(
        (level.price, level.consumed_quantity) for level in outcome.consumed_levels
    ) == ((Decimal(100), Decimal("1.5")), (Decimal(99), Decimal("0.5")))


def test_insufficient_visible_depth_can_be_explicit_partial() -> None:
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal(4),
        orderbook=_book(),
        execution_cutoff_ms=1_003,
        partial_fills_enabled=True,
    )

    assert outcome.status is DepthExecutionStatus.PARTIAL
    assert outcome.filled_quantity == Decimal(3)
    assert outcome.unfilled_quantity == Decimal(1)
    assert outcome.fill_notional == Decimal(307)
    assert outcome.average_fill_price == Decimal(307) / Decimal(3)


def test_insufficient_depth_without_partial_policy_is_not_filled() -> None:
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal(4),
        orderbook=_book(),
        execution_cutoff_ms=1_003,
        partial_fills_enabled=False,
    )

    assert outcome.status is DepthExecutionStatus.NOT_FILLED
    assert outcome.filled_quantity == Decimal(0)
    assert outcome.unfilled_quantity == Decimal(4)
    assert outcome.average_fill_price is None
    assert outcome.consumed_levels == ()


def test_unproven_execution_never_invents_a_fill() -> None:
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal(1),
        orderbook=_book(),
        execution_cutoff_ms=1_003,
        partial_fills_enabled=True,
        execution_provable=False,
    )

    assert outcome.status is DepthExecutionStatus.FILL_NOT_PROVEN
    assert outcome.filled_quantity == Decimal(0)
    assert outcome.fill_notional == Decimal(0)
    assert outcome.consumed_levels == ()


def test_future_ingested_depth_is_rejected_fail_closed() -> None:
    with pytest.raises(
        DepthExecutionRejectedError,
        match="future order-book state",
    ):
        simulate_depth_execution(
            action=PaperAction.BUY,
            requested_quantity=Decimal(1),
            orderbook=_book(ingested_at_ms=1_004),
            execution_cutoff_ms=1_003,
            partial_fills_enabled=True,
        )


def test_exact_replay_produces_identical_outcome_identity() -> None:
    kwargs = {
        "action": PaperAction.REDUCE,
        "requested_quantity": Decimal(2),
        "orderbook": _book(),
        "execution_cutoff_ms": 1_003,
        "partial_fills_enabled": True,
    }
    first = simulate_depth_execution(**kwargs)
    replay = simulate_depth_execution(**kwargs)

    assert replay == first
    assert replay.outcome_identity == first.outcome_identity


def test_hold_cash_is_not_an_execution_action() -> None:
    with pytest.raises(DepthExecutionRejectedError, match="unsupported"):
        simulate_depth_execution(
            action=PaperAction.HOLD_CASH,
            requested_quantity=Decimal(1),
            orderbook=_book(),
            execution_cutoff_ms=1_003,
            partial_fills_enabled=True,
        )
