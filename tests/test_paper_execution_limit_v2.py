from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.paper.execution_limit_v2 import (
    PassiveLimitExecutionRejectedError,
    PassiveLimitExecutionStatus,
    PassiveLimitTerminalState,
    simulate_passive_limit_execution,
)
from crypto_signal.paper.models import PaperAction


def _book(*, event_at_ms: int = 1_010, ingested_at_ms: int = 1_010):
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms,
        response_time_ms=ingested_at_ms,
        ingested_at_ms=ingested_at_ms,
        update_id=10,
        sequence=20,
        bids=(
            OrderBookLevel(Decimal(100), Decimal(2)),
            OrderBookLevel(Decimal(99), Decimal(3)),
        ),
        asks=(
            OrderBookLevel(Decimal(101), Decimal(4)),
            OrderBookLevel(Decimal(102), Decimal(5)),
        ),
        source=DataSource.REST,
        adapter_version="fp4b-test/1",
    )


def _trade(
    *,
    exec_id: str,
    sequence: int,
    side: AggressorSide,
    price: str,
    size: str,
    event_at_ms: int,
    ingested_at_ms: int | None = None,
):
    ingested = event_at_ms if ingested_at_ms is None else ingested_at_ms
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id=exec_id,
        sequence=sequence,
        aggressor_side=side,
        price=Decimal(price),
        size=Decimal(size),
        event_at_ms=event_at_ms,
        source_timestamp_ms=event_at_ms,
        ingested_at_ms=ingested,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.REST,
        adapter_version="fp4b-test/1",
    )


def _base_kwargs():
    return {
        "action": PaperAction.BUY,
        "requested_quantity": Decimal(2),
        "limit_price": Decimal(100),
        "arrival_book": _book(),
        "submitted_at_ms": 1_000,
        "latency_ms": 10,
        "timeout_ms": 100,
        "max_book_age_ms": 0,
        "partial_fills_enabled": True,
        "queue_position_proven": True,
    }


def test_latency_excludes_prearrival_trade_and_queue_is_consumed_first() -> None:
    trades = (
        _trade(
            exec_id="pre",
            sequence=1,
            side=AggressorSide.SELL,
            price="100",
            size="10",
            event_at_ms=1_009,
        ),
        _trade(
            exec_id="queue",
            sequence=2,
            side=AggressorSide.SELL,
            price="100",
            size="2",
            event_at_ms=1_020,
        ),
        _trade(
            exec_id="fill",
            sequence=3,
            side=AggressorSide.SELL,
            price="99",
            size="2",
            event_at_ms=1_030,
        ),
    )
    outcome = simulate_passive_limit_execution(public_trades=trades, **_base_kwargs())

    assert outcome.effective_arrival_ms == 1_010
    assert outcome.visible_queue_ahead_quantity == Decimal(2)
    assert outcome.queue_consumed_quantity == Decimal(2)
    assert outcome.filled_quantity == Decimal(2)
    assert outcome.status is PassiveLimitExecutionStatus.FULL
    assert outcome.terminal_state is PassiveLimitTerminalState.FILLED
    assert outcome.average_fill_price == Decimal(100)
    assert outcome.completed_at_ms == 1_030
    assert trades[0].trade_identity not in outcome.supporting_trade_identities


def test_unknown_queue_position_fails_closed_without_fill() -> None:
    kwargs = _base_kwargs()
    kwargs["queue_position_proven"] = False
    outcome = simulate_passive_limit_execution(
        public_trades=(
            _trade(
                exec_id="large",
                sequence=1,
                side=AggressorSide.SELL,
                price="99",
                size="20",
                event_at_ms=1_020,
            ),
        ),
        **kwargs,
    )

    assert outcome.status is PassiveLimitExecutionStatus.FILL_NOT_PROVEN
    assert outcome.terminal_state is PassiveLimitTerminalState.UNPROVEN
    assert outcome.filled_quantity == Decimal(0)
    assert outcome.supporting_trade_identities == ()


def test_stale_arrival_book_fails_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["arrival_book"] = _book(event_at_ms=1_005, ingested_at_ms=1_005)
    kwargs["max_book_age_ms"] = 4
    outcome = simulate_passive_limit_execution(public_trades=(), **kwargs)

    assert outcome.status is PassiveLimitExecutionStatus.FILL_NOT_PROVEN
    assert outcome.filled_quantity == Decimal(0)


def test_timeout_is_explicit_when_queue_never_clears() -> None:
    outcome = simulate_passive_limit_execution(public_trades=(), **_base_kwargs())

    assert outcome.status is PassiveLimitExecutionStatus.NOT_FILLED
    assert outcome.terminal_state is PassiveLimitTerminalState.TIMED_OUT
    assert outcome.terminal_at_ms == 1_110
    assert outcome.filled_quantity == Decimal(0)


def test_cancel_can_end_a_partial_fill() -> None:
    kwargs = _base_kwargs()
    kwargs["cancel_at_ms"] = 1_050
    outcome = simulate_passive_limit_execution(
        public_trades=(
            _trade(
                exec_id="queue-and-partial",
                sequence=1,
                side=AggressorSide.SELL,
                price="100",
                size="3",
                event_at_ms=1_020,
            ),
        ),
        **kwargs,
    )

    assert outcome.status is PassiveLimitExecutionStatus.PARTIAL
    assert outcome.terminal_state is PassiveLimitTerminalState.CANCELLED
    assert outcome.queue_consumed_quantity == Decimal(2)
    assert outcome.filled_quantity == Decimal(1)
    assert outcome.unfilled_quantity == Decimal(1)
    assert outcome.fill_notional == Decimal(100)


def test_partial_evidence_without_partial_policy_is_not_promoted() -> None:
    kwargs = _base_kwargs()
    kwargs["partial_fills_enabled"] = False
    outcome = simulate_passive_limit_execution(
        public_trades=(
            _trade(
                exec_id="queue-and-partial",
                sequence=1,
                side=AggressorSide.SELL,
                price="100",
                size="3",
                event_at_ms=1_020,
            ),
        ),
        **kwargs,
    )

    assert outcome.status is PassiveLimitExecutionStatus.FILL_NOT_PROVEN
    assert outcome.terminal_state is PassiveLimitTerminalState.UNPROVEN
    assert outcome.filled_quantity == Decimal(0)


def test_late_ingested_qualifying_trade_cannot_prove_fill() -> None:
    outcome = simulate_passive_limit_execution(
        public_trades=(
            _trade(
                exec_id="late",
                sequence=1,
                side=AggressorSide.SELL,
                price="99",
                size="20",
                event_at_ms=1_020,
                ingested_at_ms=1_111,
            ),
        ),
        **_base_kwargs(),
    )

    assert outcome.status is PassiveLimitExecutionStatus.FILL_NOT_PROVEN
    assert outcome.filled_quantity == Decimal(0)


def test_marketable_limit_is_rejected_for_fp4a_depth_path() -> None:
    kwargs = _base_kwargs()
    kwargs["limit_price"] = Decimal(101)
    with pytest.raises(
        PassiveLimitExecutionRejectedError,
        match="FP4-A depth execution",
    ):
        simulate_passive_limit_execution(public_trades=(), **kwargs)


def test_future_known_arrival_book_is_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["arrival_book"] = _book(event_at_ms=1_010, ingested_at_ms=1_011)
    with pytest.raises(
        PassiveLimitExecutionRejectedError,
        match="future-ingested",
    ):
        simulate_passive_limit_execution(public_trades=(), **kwargs)


def test_sell_limit_uses_buy_aggressor_flow_and_visible_ask_queue() -> None:
    outcome = simulate_passive_limit_execution(
        action=PaperAction.EXIT,
        requested_quantity=Decimal(2),
        limit_price=Decimal(101),
        arrival_book=_book(),
        public_trades=(
            _trade(
                exec_id="buy-through",
                sequence=1,
                side=AggressorSide.BUY,
                price="102",
                size="6",
                event_at_ms=1_020,
            ),
        ),
        submitted_at_ms=1_000,
        latency_ms=10,
        timeout_ms=100,
        max_book_age_ms=0,
        partial_fills_enabled=True,
        queue_position_proven=True,
    )

    assert outcome.visible_queue_ahead_quantity == Decimal(4)
    assert outcome.queue_consumed_quantity == Decimal(4)
    assert outcome.filled_quantity == Decimal(2)
    assert outcome.average_fill_price == Decimal(101)
    assert outcome.status is PassiveLimitExecutionStatus.FULL


def test_exact_replay_is_identity_stable_and_input_order_independent() -> None:
    first_trade = _trade(
        exec_id="a",
        sequence=1,
        side=AggressorSide.SELL,
        price="100",
        size="2",
        event_at_ms=1_020,
    )
    second_trade = _trade(
        exec_id="b",
        sequence=2,
        side=AggressorSide.SELL,
        price="99",
        size="2",
        event_at_ms=1_030,
    )
    first = simulate_passive_limit_execution(
        public_trades=(second_trade, first_trade),
        **_base_kwargs(),
    )
    replay = simulate_passive_limit_execution(
        public_trades=(first_trade, second_trade),
        **_base_kwargs(),
    )

    assert replay == first
    assert replay.outcome_identity == first.outcome_identity
