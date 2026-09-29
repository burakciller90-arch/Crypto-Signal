from __future__ import annotations

from decimal import Decimal

from crypto_signal.data.microstructure import OrderBookLevel, build_orderbook_snapshot
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.paper.execution_timing_v2 import (
    PaperOrderType,
    TimedExecutionStatus,
    build_timing_request,
    evaluate_timed_execution,
)
from crypto_signal.paper.models import PaperAction, PaperSymbol


def _book(
    *,
    source_timestamp_ms: int,
    sequence: int,
    bid: str = "100",
    ask: str = "101",
):
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=source_timestamp_ms - 1,
        source_timestamp_ms=source_timestamp_ms,
        response_time_ms=source_timestamp_ms + 1,
        ingested_at_ms=source_timestamp_ms + 2,
        update_id=sequence,
        sequence=sequence,
        bids=(OrderBookLevel(Decimal(bid), Decimal(2)),),
        asks=(OrderBookLevel(Decimal(ask), Decimal(2)),),
        source=DataSource.REST,
        adapter_version="fp4b-test/1",
    )


def _request(
    *,
    order_type: PaperOrderType = PaperOrderType.MARKET,
    latency_ms: int = 100,
    deadline_at_ms: int = 1_300,
    cancel_at_ms: int | None = None,
    limit_price: Decimal | None = None,
):
    return build_timing_request(
        action=PaperAction.BUY,
        symbol=PaperSymbol.BTCUSDT,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        order_type=order_type,
        submitted_at_ms=1_000,
        latency_ms=latency_ms,
        deadline_at_ms=deadline_at_ms,
        cancel_at_ms=cancel_at_ms,
        limit_price=limit_price,
        partial_fills_enabled=True,
    )


def test_market_waits_for_first_post_latency_book() -> None:
    pre_latency = _book(source_timestamp_ms=1_050, sequence=1)
    eligible = _book(source_timestamp_ms=1_100, sequence=2)

    decision = evaluate_timed_execution(
        request=_request(),
        orderbooks=(eligible, pre_latency),
        evaluation_cutoff_ms=1_200,
    )

    assert decision.status is TimedExecutionStatus.EXECUTION_READY
    assert decision.eligible_at_ms == 1_100
    assert decision.observed_orderbook_identities == (eligible.snapshot_identity,)
    assert decision.terminal_orderbook_identity == eligible.snapshot_identity


def test_latency_configuration_changes_eligibility_mechanically() -> None:
    first = _book(source_timestamp_ms=1_100, sequence=1)
    second = _book(source_timestamp_ms=1_200, sequence=2)

    slow = evaluate_timed_execution(
        request=_request(latency_ms=200),
        orderbooks=(first, second),
        evaluation_cutoff_ms=1_250,
    )
    fast = evaluate_timed_execution(
        request=_request(latency_ms=100),
        orderbooks=(first, second),
        evaluation_cutoff_ms=1_250,
    )

    assert slow.terminal_orderbook_identity == second.snapshot_identity
    assert fast.terminal_orderbook_identity == first.snapshot_identity
    assert slow.decision_identity != fast.decision_identity


def test_future_book_cannot_change_historical_pending_result() -> None:
    passive = _book(source_timestamp_ms=1_100, sequence=1, ask="105")
    future_cross = _book(source_timestamp_ms=1_250, sequence=2, bid="98", ask="99")
    request = _request(
        order_type=PaperOrderType.LIMIT,
        limit_price=Decimal(100),
    )

    with_future = evaluate_timed_execution(
        request=request,
        orderbooks=(passive, future_cross),
        evaluation_cutoff_ms=1_120,
    )
    without_future = evaluate_timed_execution(
        request=request,
        orderbooks=(passive,),
        evaluation_cutoff_ms=1_120,
    )

    assert with_future.status is TimedExecutionStatus.PENDING
    assert with_future == without_future


def test_cancellation_before_first_eligible_book_wins() -> None:
    decision = evaluate_timed_execution(
        request=_request(cancel_at_ms=1_090),
        orderbooks=(_book(source_timestamp_ms=1_100, sequence=1),),
        evaluation_cutoff_ms=1_200,
    )

    assert decision.status is TimedExecutionStatus.CANCELLED
    assert decision.observed_orderbook_identities == ()
    assert decision.terminal_orderbook_identity is None


def test_deadline_without_eligible_book_times_out() -> None:
    decision = evaluate_timed_execution(
        request=_request(deadline_at_ms=1_150),
        orderbooks=(_book(source_timestamp_ms=1_200, sequence=1),),
        evaluation_cutoff_ms=1_200,
    )

    assert decision.status is TimedExecutionStatus.TIMED_OUT
    assert decision.terminal_orderbook_identity is None


def test_immediately_marketable_limit_becomes_execution_ready() -> None:
    book = _book(source_timestamp_ms=1_100, sequence=1, bid="98", ask="99")
    decision = evaluate_timed_execution(
        request=_request(
            order_type=PaperOrderType.LIMIT,
            limit_price=Decimal(100),
        ),
        orderbooks=(book,),
        evaluation_cutoff_ms=1_120,
    )

    assert decision.status is TimedExecutionStatus.EXECUTION_READY
    assert decision.terminal_orderbook_identity == book.snapshot_identity


def test_passive_limit_later_touch_is_fill_not_proven() -> None:
    passive = _book(source_timestamp_ms=1_100, sequence=1, ask="105")
    later_touch = _book(source_timestamp_ms=1_200, sequence=2, bid="99", ask="100")
    decision = evaluate_timed_execution(
        request=_request(
            order_type=PaperOrderType.LIMIT,
            limit_price=Decimal(100),
        ),
        orderbooks=(passive, later_touch),
        evaluation_cutoff_ms=1_220,
    )

    assert decision.status is TimedExecutionStatus.FILL_NOT_PROVEN
    assert decision.terminal_orderbook_identity == later_touch.snapshot_identity
    assert decision.reason_code == "passive_limit_touch_or_cross_lacks_queue_proof"


def test_passive_limit_can_be_cancelled_before_later_touch() -> None:
    passive = _book(source_timestamp_ms=1_100, sequence=1, ask="105")
    later_touch = _book(source_timestamp_ms=1_200, sequence=2, ask="100")
    decision = evaluate_timed_execution(
        request=_request(
            order_type=PaperOrderType.LIMIT,
            cancel_at_ms=1_150,
            limit_price=Decimal(100),
        ),
        orderbooks=(passive, later_touch),
        evaluation_cutoff_ms=1_220,
    )

    assert decision.status is TimedExecutionStatus.CANCELLED
    assert decision.observed_orderbook_identities == (passive.snapshot_identity,)


def test_exact_replay_is_identity_stable() -> None:
    request = _request()
    books = (_book(source_timestamp_ms=1_100, sequence=1),)

    first = evaluate_timed_execution(
        request=request,
        orderbooks=books,
        evaluation_cutoff_ms=1_120,
    )
    replay = evaluate_timed_execution(
        request=request,
        orderbooks=books,
        evaluation_cutoff_ms=1_120,
    )

    assert replay == first
    assert replay.decision_identity == first.decision_identity
