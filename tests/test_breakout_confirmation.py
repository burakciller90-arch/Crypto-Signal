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
from crypto_signal.intelligence.breakout_confirmation import (
    BREAKOUT_ENGINE_VERSION,
    BREAKOUT_FREEZE_SCHEMA_VERSION,
    BreakoutConfig,
    BreakoutSide,
    BreakoutState,
    BreakoutStatus,
    build_breakout_confirmation_freeze,
)
from crypto_signal.intelligence.liquidity_structure import (
    LiquidityStructureConfig,
    build_liquidity_structure_evidence_freeze,
)
from crypto_signal.intelligence.liquidity_sweep import (
    LiquiditySweepConfig,
    build_liquidity_sweep_evidence_freeze,
)
from crypto_signal.intelligence.order_flow_patterns import (
    AbsorptionConfig,
    build_absorption_freeze,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowConfig,
    build_temporal_order_flow_freeze,
)


def _levels(items: list[tuple[str, str]]) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(price=Decimal(price), size=Decimal(size))
        for price, size in items
    )


def _book(
    *,
    event_ms: int,
    seq: int,
    ask101_size: str,
    bid100_size: str = "1",
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
        adapter_version="m3-slice3-test/1",
    )


def _trade(
    *,
    event_ms: int,
    seq: int,
    side: AggressorSide,
    price: str,
    size: str = "1",
    symbol: str = "BTCUSDT",
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
        ingested_at_ms=event_ms + 2,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.WEBSOCKET,
        adapter_version="m3-slice3-test/1",
    )


def _candle(
    *,
    open_ms: int,
    close: str,
    high: str | None = None,
    low: str | None = None,
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
) -> Candle:
    close_value = Decimal(close)
    high_value = Decimal(high) if high is not None else close_value + Decimal("0.20")
    low_value = Decimal(low) if low is not None else close_value - Decimal("0.20")
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="1m",
        open_time_ms=open_ms,
        close_time_ms=open_ms + 999,
        open=close_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=Decimal("10"),
        quote_volume=Decimal("1000"),
        trade_count=10,
        is_closed=True,
        source=DataSource.WEBSOCKET,
        source_timestamp_ms=open_ms + 999,
        ingested_at_ms=open_ms + 999 if ingested_at_ms is None else ingested_at_ms,
        adapter_version="m3-slice3-test/1",
    )


def _flow_config() -> TemporalFlowConfig:
    return TemporalFlowConfig(
        window_ms=10_000,
        bucket_ms=2_000,
        minimum_trades=5,
        max_trade_age_ms=2_500,
        max_trade_gap_ms=3_000,
        large_print_min_notional=Decimal(1000),
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
        hidden_liquidity_min_replenishment_fraction=Decimal("0.20"),
    )


def _sweep_config() -> LiquiditySweepConfig:
    return LiquiditySweepConfig(
        lookback_ms=10_000,
        minimum_orderbook_snapshots=5,
        minimum_public_trades=3,
        max_snapshot_age_ms=1_000,
        max_trade_age_ms=2_500,
        max_snapshot_gap_ms=2_000,
        pool_touch_tolerance_bps=Decimal(10),
        max_pool_interaction_distance_bps=Decimal(150),
        minimum_depth_depletion_fraction=Decimal("0.20"),
        minimum_aggressor_share=Decimal("0.60"),
        minimum_displacement_bps=Decimal(5),
        minimum_follow_through_trades=1,
        recovery_tolerance_bps=Decimal(10),
        structure_config=_structure_config(),
    )


def _confirmation_inputs():
    books = tuple(
        _book(
            event_ms=8_000 + index * 1_000,
            seq=index + 1,
            ask101_size=size,
        )
        for index, size in enumerate(["10", "8", "5", "2", "1"])
    )
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.BUY, price="101.00"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.BUY, price="101.06"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.BUY, price="101.08"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.BUY, price="101.10"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.BUY, price="101.20"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_flow_config(),
    )
    sweep = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=12_050,
        config=_sweep_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=12_050,
        config=_structure_config(),
    )
    absorption = build_absorption_freeze(
        flow,
        structure,
        as_of_ms=12_050,
        config=AbsorptionConfig(
            interaction_tolerance_bps=Decimal(20),
            minimum_aggressor_share=Decimal("0.60"),
            minimum_aggressive_trade_count=2,
            minimum_replenishment_cycles=1,
            minimum_replenishment_fraction=Decimal("0.20"),
            minimum_level_presence_fraction=Decimal("0.50"),
            max_price_nonresponse_bps=Decimal(20),
        ),
    )
    candles = (
        _candle(open_ms=10_000, close="101.20"),
        _candle(open_ms=11_000, close="101.50"),
    )
    return books, trades, flow, sweep, absorption, candles


def _failure_inputs():
    books = tuple(
        _book(
            event_ms=8_000 + index * 1_000,
            seq=index + 1,
            ask101_size=size,
        )
        for index, size in enumerate(["10", "5", "10", "5", "1"])
    )
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.BUY, price="101.00"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.BUY, price="101.06"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.BUY, price="101.08"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.BUY, price="101.10"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.SELL, price="101.01"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_flow_config(),
    )
    sweep = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=12_050,
        config=_sweep_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=12_050,
        config=_structure_config(),
    )
    absorption = build_absorption_freeze(
        flow,
        structure,
        as_of_ms=12_050,
        config=AbsorptionConfig(
            interaction_tolerance_bps=Decimal(20),
            minimum_aggressor_share=Decimal("0.60"),
            minimum_aggressive_trade_count=2,
            minimum_replenishment_cycles=1,
            minimum_replenishment_fraction=Decimal("0.20"),
            minimum_level_presence_fraction=Decimal("0.50"),
            max_price_nonresponse_bps=Decimal(20),
        ),
    )
    candles = (
        _candle(open_ms=10_000, close="101.08"),
        _candle(open_ms=11_000, close="101.02"),
    )
    return books, trades, flow, sweep, absorption, candles


def test_upside_breakout_confirmation_requires_sweep_flow_close_and_no_absorption() -> None:
    _, _, flow, sweep, absorption, candles = _confirmation_inputs()

    freeze = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
        config=BreakoutConfig(
            minimum_closed_candles=2,
            minimum_close_distance_bps=Decimal(10),
            minimum_taker_imbalance=Decimal("0.15"),
            reentry_tolerance_bps=Decimal(10),
            absorption_level_tolerance_bps=Decimal(20),
        ),
    )

    assert freeze.schema_version == BREAKOUT_FREEZE_SCHEMA_VERSION
    assert freeze.analysis.engine_version == BREAKOUT_ENGINE_VERSION
    assert freeze.analysis.status is BreakoutStatus.MEASURED
    confirmed = [
        item
        for item in freeze.analysis.candidates
        if item.state is BreakoutState.CONFIRMED
    ]
    assert len(confirmed) == 1
    candidate = confirmed[0]
    assert candidate.side is BreakoutSide.UPSIDE
    assert candidate.reference_level == Decimal(101)
    assert candidate.latest_close == Decimal("101.50")
    assert candidate.taker_imbalance > Decimal("0.15")
    assert candidate.sweep_recovered is False
    assert candidate.opposing_absorption_present is False
    assert len(freeze.analysis.evidence_identity) == 64
    assert len(freeze.freeze_identity) == 64


def test_recovered_sweep_plus_matching_absorption_is_breakout_failure_candidate() -> None:
    _, _, flow, sweep, absorption, candles = _failure_inputs()

    freeze = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
        config=BreakoutConfig(
            minimum_closed_candles=2,
            minimum_close_distance_bps=Decimal(10),
            minimum_taker_imbalance=Decimal("0.15"),
            reentry_tolerance_bps=Decimal(15),
            absorption_level_tolerance_bps=Decimal(20),
        ),
    )

    failures = [
        item
        for item in freeze.analysis.candidates
        if item.state is BreakoutState.FAILURE
    ]
    assert len(failures) == 1
    candidate = failures[0]
    assert candidate.side is BreakoutSide.UPSIDE
    assert candidate.sweep_recovered is True
    assert candidate.sweep_recovery_at_ms == 11_500
    assert candidate.opposing_absorption_present is True
    assert candidate.absorption_evidence_identity == absorption.analysis.evidence_identity


def test_downside_breakout_confirmation_is_symmetric() -> None:
    books = tuple(
        _book(
            event_ms=8_000 + index * 1_000,
            seq=index + 1,
            ask101_size="1",
            bid100_size=size,
        )
        for index, size in enumerate(["10", "8", "5", "2", "1"])
    )
    trades = (
        _trade(event_ms=8_500, seq=1, side=AggressorSide.SELL, price="100.00"),
        _trade(event_ms=9_500, seq=2, side=AggressorSide.SELL, price="99.94"),
        _trade(event_ms=10_500, seq=3, side=AggressorSide.SELL, price="99.92"),
        _trade(event_ms=11_000, seq=4, side=AggressorSide.SELL, price="99.90"),
        _trade(event_ms=11_500, seq=5, side=AggressorSide.SELL, price="99.80"),
    )
    flow = build_temporal_order_flow_freeze(
        trades,
        as_of_ms=12_050,
        config=_flow_config(),
    )
    sweep = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=12_050,
        config=_sweep_config(),
    )
    structure = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=12_050,
        config=_structure_config(),
    )
    absorption = build_absorption_freeze(
        flow,
        structure,
        as_of_ms=12_050,
        config=AbsorptionConfig(
            interaction_tolerance_bps=Decimal(20),
            minimum_aggressor_share=Decimal("0.60"),
            minimum_aggressive_trade_count=2,
            minimum_replenishment_cycles=1,
            minimum_replenishment_fraction=Decimal("0.20"),
            minimum_level_presence_fraction=Decimal("0.50"),
            max_price_nonresponse_bps=Decimal(20),
        ),
    )
    candles = (
        _candle(open_ms=10_000, close="99.80"),
        _candle(open_ms=11_000, close="99.50"),
    )

    freeze = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
        config=BreakoutConfig(
            minimum_closed_candles=2,
            minimum_close_distance_bps=Decimal(10),
            minimum_taker_imbalance=Decimal("0.15"),
            reentry_tolerance_bps=Decimal(10),
            absorption_level_tolerance_bps=Decimal(20),
        ),
    )

    confirmed = [
        item
        for item in freeze.analysis.candidates
        if item.state is BreakoutState.CONFIRMED
    ]
    assert len(confirmed) == 1
    assert confirmed[0].side is BreakoutSide.DOWNSIDE
    assert confirmed[0].reference_level == Decimal(100)
    assert confirmed[0].taker_imbalance < Decimal("-0.15")


def test_price_cross_without_close_acceptance_is_not_confirmation() -> None:
    _, _, flow, sweep, absorption, _ = _confirmation_inputs()
    candles = (
        _candle(open_ms=10_000, close="101.04"),
        _candle(open_ms=11_000, close="101.05"),
    )

    freeze = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
        config=BreakoutConfig(minimum_close_distance_bps=Decimal(10)),
    )

    assert freeze.analysis.status is BreakoutStatus.MEASURED
    assert freeze.analysis.candidates == ()
    assert "no_qualified_breakout_confirmation_or_failure" in freeze.analysis.uncertainty_flags


def test_recovery_without_matching_absorption_is_not_failure() -> None:
    _, _, flow, sweep, _, candles = _failure_inputs()
    confirmation = _confirmation_inputs()
    no_absorption = confirmation[4]

    freeze = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        no_absorption,
        as_of_ms=12_050,
        config=BreakoutConfig(reentry_tolerance_bps=Decimal(15)),
    )

    assert freeze.analysis.candidates == ()


def test_future_and_late_candles_cannot_rewrite_historical_breakout_freeze() -> None:
    _, _, flow, sweep, absorption, candles = _confirmation_inputs()
    baseline = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
    )
    future = _candle(open_ms=12_100, close="105")
    late = _candle(
        open_ms=9_000,
        close="105",
        ingested_at_ms=12_100,
    )

    replay = build_breakout_confirmation_freeze(
        (*candles, future, late),
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
    )

    assert replay == baseline
    assert future not in replay.candles
    assert late not in replay.candles


def test_mixed_context_and_asof_mismatch_fail_closed() -> None:
    _, _, flow, sweep, absorption, candles = _confirmation_inputs()
    eth = _candle(open_ms=9_000, close="101", symbol="ETHUSDT")
    with pytest.raises(ValueError, match="mixed breakout candle context"):
        build_breakout_confirmation_freeze(
            (*candles, eth),
            flow,
            sweep,
            absorption,
            as_of_ms=12_050,
        )

    with pytest.raises(ValueError, match="exact upstream as_of alignment"):
        build_breakout_confirmation_freeze(
            candles,
            flow,
            sweep,
            absorption,
            as_of_ms=12_051,
        )


def test_identity_tampering_fails_closed() -> None:
    _, _, flow, sweep, absorption, candles = _confirmation_inputs()
    freeze = build_breakout_confirmation_freeze(
        candles,
        flow,
        sweep,
        absorption,
        as_of_ms=12_050,
    )
    with pytest.raises(ValueError, match="breakout evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)
    with pytest.raises(ValueError, match="breakout freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
