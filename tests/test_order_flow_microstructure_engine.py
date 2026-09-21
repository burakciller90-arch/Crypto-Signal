from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.order_flow_microstructure import (
    ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION,
    ORDER_FLOW_MICROSTRUCTURE_FREEZE_SCHEMA_VERSION,
    BookPressureState,
    OrderFlowMicrostructureConfig,
    OrderFlowMicrostructureLabel,
    TakerFlowState,
    analyze_order_flow_microstructure,
    build_order_flow_microstructure_evidence_freeze,
)


def _book(
    *,
    event_at_ms: int = 9_500,
    source_timestamp_ms: int | None = None,
    response_time_ms: int | None = None,
    ingested_at_ms: int | None = None,
    sequence: int = 100,
    symbol: str = "BTCUSDT",
    bids: tuple[OrderBookLevel, ...] | None = None,
    asks: tuple[OrderBookLevel, ...] | None = None,
):
    source_ms = event_at_ms + 10 if source_timestamp_ms is None else source_timestamp_ms
    response_ms = source_ms + 10 if response_time_ms is None else response_time_ms
    ingested_ms = response_ms + 10 if ingested_at_ms is None else ingested_at_ms
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_ms,
        response_time_ms=response_ms,
        ingested_at_ms=ingested_ms,
        update_id=sequence,
        sequence=sequence,
        bids=bids
        or (
            OrderBookLevel(price=Decimal(100), size=Decimal(3)),
            OrderBookLevel(price=Decimal(99), size=Decimal(2)),
        ),
        asks=asks
        or (
            OrderBookLevel(price=Decimal(101), size=Decimal(1)),
            OrderBookLevel(price=Decimal(102), size=Decimal(1)),
        ),
        source=DataSource.REST,
        adapter_version="microstructure-engine-test/1",
    )


def _trade(
    exec_id: str,
    *,
    event_at_ms: int,
    side: AggressorSide,
    price: Decimal = Decimal(100),
    size: Decimal = Decimal(1),
    sequence: int | None = None,
    source_timestamp_ms: int | None = None,
    ingested_at_ms: int | None = None,
    is_block_trade: bool = False,
    is_rpi_trade: bool = False,
    symbol: str = "BTCUSDT",
):
    seq = event_at_ms if sequence is None else sequence
    source_ms = event_at_ms + 5 if source_timestamp_ms is None else source_timestamp_ms
    ingested_ms = source_ms + 5 if ingested_at_ms is None else ingested_at_ms
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        exec_id=exec_id,
        sequence=seq,
        aggressor_side=side,
        price=price,
        size=size,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingested_ms,
        is_block_trade=is_block_trade,
        is_rpi_trade=is_rpi_trade,
        source=DataSource.REST,
        adapter_version="microstructure-engine-test/1",
    )


def _buy_pressure_trades():
    return (
        _trade("b1", event_at_ms=9_600, side=AggressorSide.BUY),
        _trade("b2", event_at_ms=9_650, side=AggressorSide.BUY),
        _trade("b3", event_at_ms=9_700, side=AggressorSide.BUY),
        _trade("b4", event_at_ms=9_750, side=AggressorSide.BUY),
        _trade(
            "s1",
            event_at_ms=9_800,
            side=AggressorSide.SELL,
            size=Decimal("0.2"),
        ),
    )


def _config(**overrides):
    payload = {
        "depth_levels": 2,
        "minimum_trades": 5,
        "trade_lookback_ms": 1_000,
        "max_book_age_ms": 1_000,
        "max_trade_age_ms": 500,
        "imbalance_threshold": Decimal("0.15"),
    }
    payload.update(overrides)
    return OrderFlowMicrostructureConfig(**payload)


def test_buy_pressure_is_deterministic_and_frozen() -> None:
    book = _book()
    trades = _buy_pressure_trades()
    config = _config()

    first = build_order_flow_microstructure_evidence_freeze(
        (book,),
        trades,
        as_of_ms=10_000,
        config=config,
    )
    second = build_order_flow_microstructure_evidence_freeze(
        (book,),
        tuple(reversed(trades)),
        as_of_ms=10_000,
        config=config,
    )

    assert first == second
    assert first.schema_version == ORDER_FLOW_MICROSTRUCTURE_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == ORDER_FLOW_MICROSTRUCTURE_ENGINE_VERSION
    assert first.analysis.label is OrderFlowMicrostructureLabel.BUY_PRESSURE
    assert first.analysis.book_pressure is BookPressureState.BID_HEAVY
    assert first.analysis.taker_flow is TakerFlowState.BUY_DOMINANT
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.book_imbalance > Decimal("0.15")
    assert first.analysis.metrics.taker_flow_imbalance > Decimal("0.15")
    assert first.analysis.metrics.spread_bps > Decimal(0)
    assert first.analysis.uncertainty_flags == ()
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_sell_pressure_requires_book_and_taker_alignment() -> None:
    book = _book(
        bids=(
            OrderBookLevel(price=Decimal(100), size=Decimal(1)),
            OrderBookLevel(price=Decimal(99), size=Decimal(1)),
        ),
        asks=(
            OrderBookLevel(price=Decimal(101), size=Decimal(3)),
            OrderBookLevel(price=Decimal(102), size=Decimal(2)),
        ),
    )
    trades = tuple(
        _trade(
            f"s{index}",
            event_at_ms=9_550 + index * 50,
            side=AggressorSide.SELL,
        )
        for index in range(5)
    )

    result = analyze_order_flow_microstructure(
        (book,),
        trades,
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.label is OrderFlowMicrostructureLabel.SELL_PRESSURE
    assert result.book_pressure is BookPressureState.ASK_HEAVY
    assert result.taker_flow is TakerFlowState.SELL_DOMINANT


def test_balanced_context_uses_bounded_imbalances() -> None:
    book = _book(
        bids=(OrderBookLevel(price=Decimal(100), size=Decimal(1)),),
        asks=(
            OrderBookLevel(
                price=Decimal(101),
                size=Decimal(100) / Decimal(101),
            ),
        ),
    )
    trades = (
        _trade("b1", event_at_ms=9_600, side=AggressorSide.BUY),
        _trade("s1", event_at_ms=9_650, side=AggressorSide.SELL),
        _trade("b2", event_at_ms=9_700, side=AggressorSide.BUY),
        _trade("s2", event_at_ms=9_750, side=AggressorSide.SELL),
    )

    result = analyze_order_flow_microstructure(
        (book,),
        trades,
        as_of_ms=10_000,
        config=_config(depth_levels=1, minimum_trades=4),
    )

    assert result.label is OrderFlowMicrostructureLabel.BALANCED
    assert result.book_pressure is BookPressureState.BALANCED
    assert result.taker_flow is TakerFlowState.BALANCED
    assert result.metrics is not None
    assert result.metrics.book_imbalance == Decimal(0)
    assert result.metrics.taker_flow_imbalance == Decimal(0)


def test_disagreement_is_mixed_with_explicit_uncertainty() -> None:
    book = _book()
    trades = tuple(
        _trade(
            f"s{index}",
            event_at_ms=9_550 + index * 50,
            side=AggressorSide.SELL,
        )
        for index in range(5)
    )

    result = analyze_order_flow_microstructure(
        (book,),
        trades,
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.label is OrderFlowMicrostructureLabel.MIXED
    assert result.book_pressure is BookPressureState.BID_HEAVY
    assert result.taker_flow is TakerFlowState.SELL_DOMINANT
    assert (
        "book_flow_disagreement_or_partial_alignment"
        in result.uncertainty_flags
    )


def test_rpi_and_block_trades_are_excluded_from_book_flow() -> None:
    trades = (
        *_buy_pressure_trades(),
        _trade(
            "rpi",
            event_at_ms=9_810,
            side=AggressorSide.SELL,
            size=Decimal(100),
            is_rpi_trade=True,
        ),
        _trade(
            "block",
            event_at_ms=9_820,
            side=AggressorSide.SELL,
            size=Decimal(100),
            is_block_trade=True,
        ),
    )

    result = analyze_order_flow_microstructure(
        (_book(),),
        trades,
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.label is OrderFlowMicrostructureLabel.BUY_PRESSURE
    assert result.metrics is not None
    assert result.metrics.eligible_trade_count == 5
    assert result.metrics.excluded_trade_count == 2
    assert result.excluded_trade_count == 2
    assert "excluded_block_or_rpi_trades" in result.uncertainty_flags


@pytest.mark.parametrize(
    ("book", "trades", "expected_flag"),
    [
        (
            _book(event_at_ms=8_000),
            _buy_pressure_trades(),
            "stale_orderbook",
        ),
        (
            _book(
                bids=(OrderBookLevel(price=Decimal(100), size=Decimal(1)),),
                asks=(OrderBookLevel(price=Decimal(101), size=Decimal(1)),),
            ),
            _buy_pressure_trades(),
            "insufficient_orderbook_depth",
        ),
        (
            _book(),
            _buy_pressure_trades()[:2],
            "insufficient_public_trades",
        ),
    ],
)
def test_incomplete_or_stale_evidence_is_unresolved(
    book,
    trades,
    expected_flag: str,
) -> None:
    result = analyze_order_flow_microstructure(
        (book,),
        trades,
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.label is OrderFlowMicrostructureLabel.UNRESOLVED
    assert result.metrics is None
    assert result.book_pressure is BookPressureState.UNAVAILABLE
    assert result.taker_flow is TakerFlowState.UNAVAILABLE
    assert expected_flag in result.uncertainty_flags


def test_future_and_late_ingested_evidence_cannot_change_historical_freeze() -> None:
    baseline = build_order_flow_microstructure_evidence_freeze(
        (_book(),),
        _buy_pressure_trades(),
        as_of_ms=10_000,
        config=_config(),
    )
    future_book = _book(
        event_at_ms=10_100,
        source_timestamp_ms=10_110,
        response_time_ms=10_120,
        ingested_at_ms=10_130,
        sequence=200,
        bids=(
            OrderBookLevel(price=Decimal(100), size=Decimal(1)),
            OrderBookLevel(price=Decimal(99), size=Decimal(1)),
        ),
        asks=(
            OrderBookLevel(price=Decimal(101), size=Decimal(10)),
            OrderBookLevel(price=Decimal(102), size=Decimal(10)),
        ),
    )
    late_trade = _trade(
        "late",
        event_at_ms=9_850,
        side=AggressorSide.SELL,
        size=Decimal(100),
        source_timestamp_ms=9_860,
        ingested_at_ms=10_100,
    )

    with_future = build_order_flow_microstructure_evidence_freeze(
        (_book(), future_book),
        (*_buy_pressure_trades(), late_trade),
        as_of_ms=10_000,
        config=_config(),
    )

    assert with_future == baseline
    assert future_book is not with_future.orderbook
    assert late_trade not in with_future.trades


def test_no_safe_orderbook_is_unresolved_without_fabricated_metrics() -> None:
    future_book = _book(
        event_at_ms=10_100,
        source_timestamp_ms=10_110,
        response_time_ms=10_120,
        ingested_at_ms=10_130,
    )

    result = analyze_order_flow_microstructure(
        (future_book,),
        _buy_pressure_trades(),
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.label is OrderFlowMicrostructureLabel.UNRESOLVED
    assert result.metrics is None
    assert result.book_event_at_ms is None
    assert result.uncertainty_flags == ("orderbook_unavailable_at_as_of",)


def test_duplicate_or_mixed_context_fails_closed() -> None:
    book = _book()
    trade = _trade("b1", event_at_ms=9_600, side=AggressorSide.BUY)

    with pytest.raises(ValueError, match="duplicate public trade identity"):
        analyze_order_flow_microstructure(
            (book,),
            (trade, trade),
            as_of_ms=10_000,
            config=_config(minimum_trades=1),
        )

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_order_flow_microstructure(
            (book,),
            (
                _trade(
                    "eth",
                    event_at_ms=9_600,
                    side=AggressorSide.BUY,
                    symbol="ETHUSDT",
                ),
            ),
            as_of_ms=10_000,
            config=_config(minimum_trades=1),
        )


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    freeze = build_order_flow_microstructure_evidence_freeze(
        (_book(),),
        _buy_pressure_trades(),
        as_of_ms=10_000,
        config=_config(),
    )

    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_stage8_order_flow_is_observation_only_ablation_zero() -> None:
    assert set(MethodologyKind) == {
        MethodologyKind.PRICE_ACTION,
        MethodologyKind.HARMONIC,
        MethodologyKind.ELLIOTT,
    }

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/crypto_signal/confluence/models.py",
        "src/crypto_signal/confluence/adapters.py",
        "src/crypto_signal/ledger/bundle.py",
        "src/crypto_signal/signals/models.py",
        "src/crypto_signal/paper/mission_control.py",
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.order_flow_microstructure" not in source
