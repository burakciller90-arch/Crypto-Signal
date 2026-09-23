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
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.intelligence.liquidity_structure import (
    LiquidityStructureConfig,
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_patterns import (
    ABSORPTION_ENGINE_VERSION,
    DIVERGENCE_ENGINE_VERSION,
    AbsorptionConfig,
    AbsorptionSide,
    DivergenceConfig,
    DivergenceSide,
    PatternStatus,
    build_absorption_freeze,
    build_price_cvd_divergence_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowConfig,
    build_temporal_order_flow_freeze,
)


def _candle(
    *,
    open_ms: int,
    low: str,
    high: str,
    close: str = "100",
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
) -> Candle:
    close_ms = open_ms + 10_000
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="10s-test",
        open_time_ms=open_ms,
        close_time_ms=close_ms,
        open=Decimal(100),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trade_count=10,
        is_closed=True,
        source=DataSource.AGGREGATED,
        source_timestamp_ms=close_ms,
        ingested_at_ms=close_ms + 10 if ingested_at_ms is None else ingested_at_ms,
        adapter_version="m3-slice2-test/1",
    )


def _trade(
    *,
    event_ms: int,
    seq: int,
    side: AggressorSide,
    price: str = "100",
    size: str = "10",
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
):
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        exec_id=f"exec-{seq}",
        sequence=seq,
        aggressor_side=side,
        price=Decimal(price),
        size=Decimal(size),
        event_at_ms=event_ms,
        source_timestamp_ms=event_ms + 1,
        ingested_at_ms=event_ms + 2 if ingested_at_ms is None else ingested_at_ms,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.WEBSOCKET,
        adapter_version="m3-slice2-test/1",
    )


def _flow_config() -> TemporalFlowConfig:
    return TemporalFlowConfig(
        window_ms=100_000,
        bucket_ms=10_000,
        minimum_trades=5,
        max_trade_age_ms=30_000,
        max_trade_gap_ms=30_000,
        large_print_min_notional=Decimal(5000),
    )


def _bullish_divergence_candles() -> tuple[Candle, ...]:
    return (
        _candle(open_ms=240_000, low="99", high="103"),
        _candle(open_ms=250_000, low="95", high="102"),
        _candle(open_ms=260_000, low="98", high="103"),
        _candle(open_ms=270_000, low="90", high="102"),
        _candle(open_ms=280_000, low="96", high="104"),
    )


def _bullish_divergence_trades():
    return (
        _trade(event_ms=252_000, seq=1, side=AggressorSide.SELL),
        _trade(event_ms=255_000, seq=2, side=AggressorSide.SELL),
        _trade(event_ms=263_000, seq=3, side=AggressorSide.BUY),
        _trade(event_ms=272_000, seq=4, side=AggressorSide.BUY),
        _trade(event_ms=275_000, seq=5, side=AggressorSide.BUY),
        _trade(event_ms=285_000, seq=6, side=AggressorSide.BUY),
    )


def test_bullish_price_cvd_divergence_uses_real_endpoint_trade_coverage() -> None:
    flow = build_temporal_order_flow_freeze(
        _bullish_divergence_trades(),
        as_of_ms=300_000,
        config=_flow_config(),
    )
    freeze = build_price_cvd_divergence_freeze(
        _bullish_divergence_candles(),
        flow,
        as_of_ms=300_000,
        config=DivergenceConfig(
            minimum_closed_candles=5,
            pivot_radius=1,
            minimum_price_change_bps=Decimal(5),
            minimum_cvd_change_notional=Decimal(0),
            max_endpoint_trade_gap_ms=10_000,
            minimum_endpoint_trade_count=1,
        ),
    )

    assert freeze.analysis.engine_version == DIVERGENCE_ENGINE_VERSION
    assert freeze.analysis.status is PatternStatus.MEASURED
    bullish = [
        item
        for item in freeze.analysis.candidates
        if item.side is DivergenceSide.BULLISH
    ]
    assert len(bullish) == 1
    candidate = bullish[0]
    assert candidate.first_price == Decimal(95)
    assert candidate.second_price == Decimal(90)
    assert candidate.second_cvd_notional > candidate.first_cvd_notional
    assert candidate.cvd_change_notional > Decimal(0)
    assert candidate.first_endpoint_trade_count == 2
    assert candidate.second_endpoint_trade_count == 2
    assert "window_local_cvd_not_exchange_global" in candidate.uncertainty_flags
    assert len(freeze.analysis.evidence_identity) == 64
    assert len(freeze.freeze_identity) == 64


def test_bearish_price_cvd_divergence_is_bounded_and_not_probability() -> None:
    candles = (
        _candle(open_ms=240_000, low="97", high="101"),
        _candle(open_ms=250_000, low="98", high="105"),
        _candle(open_ms=260_000, low="97", high="102"),
        _candle(open_ms=270_000, low="98", high="110"),
        _candle(open_ms=280_000, low="96", high="103"),
    )
    trades = (
        _trade(event_ms=252_000, seq=1, side=AggressorSide.BUY),
        _trade(event_ms=255_000, seq=2, side=AggressorSide.BUY),
        _trade(event_ms=263_000, seq=3, side=AggressorSide.SELL),
        _trade(event_ms=272_000, seq=4, side=AggressorSide.SELL),
        _trade(event_ms=275_000, seq=5, side=AggressorSide.SELL),
        _trade(event_ms=285_000, seq=6, side=AggressorSide.SELL),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=300_000,
        config=_flow_config(),
    )
    freeze = build_price_cvd_divergence_freeze(
        candles,
        flow,
        as_of_ms=300_000,
    )

    bearish = [
        item
        for item in freeze.analysis.candidates
        if item.side is DivergenceSide.BEARISH
    ]
    assert len(bearish) == 1
    assert bearish[0].first_price == Decimal(105)
    assert bearish[0].second_price == Decimal(110)
    assert bearish[0].cvd_change_notional < Decimal(0)


def test_price_shape_without_trade_coverage_does_not_create_divergence() -> None:
    trades = (
        _trade(event_ms=252_000, seq=1, side=AggressorSide.SELL),
        _trade(event_ms=255_000, seq=2, side=AggressorSide.SELL),
        _trade(event_ms=263_000, seq=3, side=AggressorSide.BUY),
        _trade(event_ms=264_000, seq=4, side=AggressorSide.BUY),
        _trade(event_ms=285_000, seq=5, side=AggressorSide.BUY),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=300_000,
        config=_flow_config(),
    )
    freeze = build_price_cvd_divergence_freeze(
        _bullish_divergence_candles(),
        flow,
        as_of_ms=300_000,
    )

    assert freeze.analysis.status is PatternStatus.MEASURED
    assert not any(
        item.side is DivergenceSide.BULLISH for item in freeze.analysis.candidates
    )


def test_future_and_late_candles_cannot_rewrite_divergence_freeze() -> None:
    flow = build_temporal_order_flow_freeze(
        _bullish_divergence_trades(),
        as_of_ms=300_000,
        config=_flow_config(),
    )
    baseline = build_price_cvd_divergence_freeze(
        _bullish_divergence_candles(),
        flow,
        as_of_ms=300_000,
    )
    future = _candle(open_ms=300_000, low="70", high="120")
    late = _candle(
        open_ms=230_000,
        low="80",
        high="120",
        ingested_at_ms=300_100,
    )
    replay = build_price_cvd_divergence_freeze(
        (*_bullish_divergence_candles(), future, late),
        flow,
        as_of_ms=300_000,
    )

    assert replay == baseline
    assert future not in replay.candles
    assert late not in replay.candles


def _levels(items: list[tuple[str, str]]) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(price=Decimal(price), size=Decimal(size))
        for price, size in items
    )


def _book(
    *,
    event_ms: int,
    seq: int,
    bid100_size: str = "10",
    ask101_size: str = "10",
    symbol: str = "BTCUSDT",
):
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        event_at_ms=event_ms,
        source_timestamp_ms=event_ms + 1,
        response_time_ms=event_ms + 2,
        ingested_at_ms=event_ms + 3,
        update_id=seq,
        sequence=seq,
        bids=_levels([("100", bid100_size), ("99", "1"), ("98", "1")]),
        asks=_levels([("101", ask101_size), ("102", "1"), ("103", "1")]),
        source=DataSource.WEBSOCKET,
        adapter_version="m3-slice2-test/1",
    )


def _structure_config() -> LiquidityStructureConfig:
    return LiquidityStructureConfig(
        depth_levels=3,
        lookback_ms=10_000,
        minimum_snapshots=5,
        max_snapshot_age_ms=1_000,
        max_snapshot_gap_ms=2_000,
        persistent_presence_fraction=Decimal("0.60"),
        material_notional_multiple=Decimal("1.20"),
        approach_bps=Decimal(100),
        rapid_withdrawal_max_lifetime_ms=5_000,
        rapid_withdrawal_min_fraction=Decimal("0.80"),
        hidden_liquidity_min_replenishment_cycles=1,
        hidden_liquidity_min_replenishment_fraction=Decimal("0.25"),
    )


def _absorption_flow_config() -> TemporalFlowConfig:
    return TemporalFlowConfig(
        window_ms=10_000,
        bucket_ms=2_000,
        minimum_trades=5,
        max_trade_age_ms=2_000,
        max_trade_gap_ms=3_000,
        large_print_min_notional=Decimal(1000),
    )


def _replenishing_bid_books():
    sizes = ["10", "5", "10", "5", "10"]
    return tuple(
        _book(
            event_ms=8_000 + index * 1_000,
            seq=index + 1,
            bid100_size=size,
        )
        for index, size in enumerate(sizes)
    )


def _replenishing_ask_books():
    sizes = ["10", "5", "10", "5", "10"]
    return tuple(
        _book(
            event_ms=8_000 + index * 1_000,
            seq=index + 1,
            bid100_size="1",
            ask101_size=size,
        )
        for index, size in enumerate(sizes)
    )


def test_bid_absorption_requires_sell_aggression_replenishment_and_nonresponse() -> None:
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.SELL, price="100.00", size="1"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.SELL, price="99.98", size="1"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.SELL, price="99.95", size="1"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.SELL, price="99.92", size="1"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.BUY, price="100.02", size="1"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_absorption_flow_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        _replenishing_bid_books(),
        as_of_ms=12_050,
        config=_structure_config(),
    )
    freeze = build_absorption_freeze(
        flow,
        structure,
        as_of_ms=12_050,
        config=AbsorptionConfig(
            interaction_tolerance_bps=Decimal(15),
            minimum_aggressor_share=Decimal("0.60"),
            minimum_aggressive_trade_count=2,
            minimum_replenishment_cycles=1,
            minimum_replenishment_fraction=Decimal("0.25"),
            minimum_level_presence_fraction=Decimal("0.50"),
            max_price_nonresponse_bps=Decimal(20),
        ),
    )

    assert freeze.analysis.engine_version == ABSORPTION_ENGINE_VERSION
    assert freeze.analysis.status is PatternStatus.MEASURED
    bids = [
        item
        for item in freeze.analysis.candidates
        if item.side is AbsorptionSide.BID
    ]
    assert len(bids) == 1
    candidate = bids[0]
    assert candidate.level_price == Decimal(100)
    assert candidate.aggressive_trade_count == 4
    assert candidate.aggressor_share >= Decimal("0.60")
    assert candidate.replenishment_cycles >= 1
    assert candidate.replenishment_notional > Decimal(0)
    assert candidate.max_price_response_bps <= Decimal(20)
    assert "candidate_not_proof_of_iceberg_execution" in candidate.uncertainty_flags


def test_ask_absorption_is_symmetric() -> None:
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.BUY, price="101.00", size="1"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.BUY, price="101.02", size="1"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.BUY, price="101.05", size="1"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.BUY, price="101.08", size="1"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.SELL, price="100.98", size="1"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_absorption_flow_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        _replenishing_ask_books(),
        as_of_ms=12_050,
        config=_structure_config(),
    )
    freeze = build_absorption_freeze(flow, structure, as_of_ms=12_050)

    asks = [
        item
        for item in freeze.analysis.candidates
        if item.side is AbsorptionSide.ASK
    ]
    assert len(asks) == 1
    assert asks[0].level_price == Decimal(101)


def test_wall_without_interacting_aggressive_flow_is_not_absorption() -> None:
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.SELL, price="98.50"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.SELL, price="98.40"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.BUY, price="98.60"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.SELL, price="98.50"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.BUY, price="98.70"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_absorption_flow_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        _replenishing_bid_books(),
        as_of_ms=12_050,
        config=_structure_config(),
    )
    freeze = build_absorption_freeze(flow, structure, as_of_ms=12_050)

    assert freeze.analysis.status is PatternStatus.MEASURED
    assert freeze.analysis.candidates == ()


def test_aggressive_prints_without_replenishment_are_not_absorption() -> None:
    stable_books = tuple(
        _book(event_ms=8_000 + index * 1_000, seq=index + 1)
        for index in range(5)
    )
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.SELL, price="100.00"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.SELL, price="99.98"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.SELL, price="99.96"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.SELL, price="99.95"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.BUY, price="100.02"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_absorption_flow_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        stable_books,
        as_of_ms=12_050,
        config=_structure_config(),
    )
    freeze = build_absorption_freeze(flow, structure, as_of_ms=12_050)

    assert freeze.analysis.candidates == ()


def test_excessive_price_response_rejects_absorption_candidate() -> None:
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.SELL, price="100.00"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.SELL, price="99.70"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.SELL, price="99.60"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.SELL, price="99.50"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.BUY, price="100.02"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_absorption_flow_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        _replenishing_bid_books(),
        as_of_ms=12_050,
        config=_structure_config(),
    )
    freeze = build_absorption_freeze(
        flow,
        structure,
        as_of_ms=12_050,
        config=AbsorptionConfig(
            interaction_tolerance_bps=Decimal(100),
            max_price_nonresponse_bps=Decimal(20),
        ),
    )

    assert freeze.analysis.candidates == ()


def test_mixed_context_and_identity_tampering_fail_closed() -> None:
    flow = build_temporal_order_flow_freeze(
        _bullish_divergence_trades(),
        as_of_ms=300_000,
        config=_flow_config(),
    )
    eth = _candle(open_ms=290_000, low="90", high="110", symbol="ETHUSDT")
    with pytest.raises(ValueError, match="mixed divergence candle context"):
        build_price_cvd_divergence_freeze(
            (*_bullish_divergence_candles(), eth),
            flow,
            as_of_ms=300_000,
        )

    freeze = build_price_cvd_divergence_freeze(
        _bullish_divergence_candles(),
        flow,
        as_of_ms=300_000,
    )
    with pytest.raises(ValueError, match="divergence evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    with pytest.raises(ValueError, match="divergence freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
