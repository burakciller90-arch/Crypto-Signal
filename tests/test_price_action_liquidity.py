from decimal import Decimal

from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.methodologies.price_action.liquidity import (
    LiquidityEventKind,
    LiquidityPoolKind,
    LiquidityPoolStatus,
    analyze_liquidity,
    detect_liquidity_pools,
    evaluate_liquidity_pool,
)
from crypto_signal.methodologies.price_action.models import StructureDirection
from crypto_signal.primitives.models import ConfirmedPivot, PivotKind


def candle(
    index: int,
    *,
    high: str = "105",
    low: str = "95",
    close: str = "100",
) -> Candle:
    open_time_ms = index * 900_000
    return Candle(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 899_999,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=open_time_ms + 900_000,
        ingested_at_ms=open_time_ms + 900_999,
        adapter_version="test/1",
    )


def pivot(
    kind: PivotKind,
    index: int,
    price: str,
    *,
    confirm_index: int,
) -> ConfirmedPivot:
    source = candle(index)
    confirmation = candle(confirm_index)
    return ConfirmedPivot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        kind=kind,
        candle_index=index,
        open_time_ms=source.open_time_ms,
        price=Decimal(price),
        left_bars=1,
        right_bars=confirm_index - index,
        market_confirmed_at_ms=confirmation.close_time_ms,
        observed_at_ms=confirmation.ingested_at_ms,
        source_candle_identity=source.identity,
        confirmation_candle_identity=confirmation.identity,
    )


def test_equal_high_pool_uses_explicit_bps_tolerance() -> None:
    swings = [
        pivot(PivotKind.HIGH, 1, "100", confirm_index=2),
        pivot(PivotKind.LOW, 2, "90", confirm_index=3),
        pivot(PivotKind.HIGH, 3, "100.04", confirm_index=4),
    ]

    pools = detect_liquidity_pools(swings, equal_tolerance_bps=Decimal(5))

    assert len(pools) == 1
    pool = pools[0]
    assert pool.kind is LiquidityPoolKind.EQUAL_HIGHS
    assert pool.zone_low == Decimal(100)
    assert pool.zone_high == Decimal("100.04")
    assert pool.pair_distance_bps <= Decimal(5)
    assert pool.formed_at_market_ms == swings[2].market_confirmed_at_ms


def test_pair_outside_tolerance_does_not_create_pool() -> None:
    swings = [
        pivot(PivotKind.HIGH, 1, "100", confirm_index=2),
        pivot(PivotKind.LOW, 2, "90", confirm_index=3),
        pivot(PivotKind.HIGH, 3, "100.10", confirm_index=4),
    ]
    assert detect_liquidity_pools(
        swings,
        equal_tolerance_bps=Decimal(5),
    ) == ()


def test_equal_low_pool_is_detected() -> None:
    swings = [
        pivot(PivotKind.LOW, 1, "100", confirm_index=2),
        pivot(PivotKind.HIGH, 2, "110", confirm_index=3),
        pivot(PivotKind.LOW, 3, "99.98", confirm_index=4),
    ]
    pools = detect_liquidity_pools(swings, equal_tolerance_bps=Decimal(5))

    assert len(pools) == 1
    assert pools[0].kind is LiquidityPoolKind.EQUAL_LOWS


def test_eqh_wick_sweep_and_close_back_inside_is_bearish_sfp() -> None:
    swings = [
        pivot(PivotKind.HIGH, 1, "100", confirm_index=2),
        pivot(PivotKind.LOW, 2, "90", confirm_index=3),
        pivot(PivotKind.HIGH, 3, "100.04", confirm_index=4),
    ]
    pool = detect_liquidity_pools(swings, equal_tolerance_bps=Decimal(5))[0]
    series = [candle(index) for index in range(6)]
    series[5] = candle(5, high="101", low="98", close="99.8")

    result = evaluate_liquidity_pool(pool, series)

    assert result.status is LiquidityPoolStatus.SWEPT_SFP
    assert result.event is not None
    assert result.event.kind is LiquidityEventKind.SFP_REJECTION
    assert result.event.implication_direction is StructureDirection.BEARISH
    assert result.event.excursion_bps > 0
    assert result.event.close_recovery_bps > 0


def test_eqh_close_through_is_not_sfp() -> None:
    swings = [
        pivot(PivotKind.HIGH, 1, "100", confirm_index=2),
        pivot(PivotKind.LOW, 2, "90", confirm_index=3),
        pivot(PivotKind.HIGH, 3, "100.04", confirm_index=4),
    ]
    pool = detect_liquidity_pools(swings, equal_tolerance_bps=Decimal(5))[0]
    series = [candle(index) for index in range(6)]
    series[5] = candle(5, high="101", low="99", close="100.5")

    result = evaluate_liquidity_pool(pool, series)

    assert result.status is LiquidityPoolStatus.BROKEN_CLOSE
    assert result.event is not None
    assert result.event.kind is LiquidityEventKind.CLOSE_THROUGH
    assert result.event.implication_direction is StructureDirection.BULLISH
    assert result.event.close_recovery_bps < 0


def test_eql_wick_sweep_and_reclaim_is_bullish_sfp() -> None:
    swings = [
        pivot(PivotKind.LOW, 1, "100", confirm_index=2),
        pivot(PivotKind.HIGH, 2, "110", confirm_index=3),
        pivot(PivotKind.LOW, 3, "99.98", confirm_index=4),
    ]
    pool = detect_liquidity_pools(swings, equal_tolerance_bps=Decimal(5))[0]
    series = [candle(index) for index in range(6)]
    series[5] = candle(5, high="102", low="99", close="100.2")

    result = evaluate_liquidity_pool(pool, series)

    assert result.status is LiquidityPoolStatus.SWEPT_SFP
    assert result.event is not None
    assert result.event.kind is LiquidityEventKind.SFP_REJECTION
    assert result.event.implication_direction is StructureDirection.BULLISH
    assert result.event.close_recovery_bps > 0


def test_preformation_sweep_is_not_retroactively_consumed() -> None:
    swings = [
        pivot(PivotKind.HIGH, 1, "100", confirm_index=2),
        pivot(PivotKind.LOW, 2, "90", confirm_index=3),
        pivot(PivotKind.HIGH, 3, "100.04", confirm_index=4),
    ]
    pool = detect_liquidity_pools(swings, equal_tolerance_bps=Decimal(5))[0]
    series = [candle(index) for index in range(6)]
    series[3] = candle(3, high="102", low="98", close="99")
    series[5] = candle(5, high="100", low="98", close="99")

    result = evaluate_liquidity_pool(pool, series)

    assert result.status is LiquidityPoolStatus.AVAILABLE
    assert result.event is None


def test_top_level_pool_does_not_exist_before_second_pivot_confirmation() -> None:
    highs = ["100", "110", "100", "110.02", "100", "101"]
    lows = ["90", "95", "80", "95", "90", "91"]
    closes = ["95", "100", "90", "100", "95", "96"]
    series = [
        candle(index, high=high, low=low, close=close)
        for index, (high, low, close) in enumerate(
            zip(highs, lows, closes, strict=True)
        )
    ]

    before = analyze_liquidity(
        series,
        left_bars=1,
        right_bars=1,
        equal_tolerance_bps=Decimal(5),
        as_of_ms=series[3].ingested_at_ms,
    )
    after = analyze_liquidity(
        series,
        left_bars=1,
        right_bars=1,
        equal_tolerance_bps=Decimal(5),
        as_of_ms=series[4].ingested_at_ms,
    )

    assert before.pools == ()
    assert len(after.pools) == 1
    assert after.pools[0].kind is LiquidityPoolKind.EQUAL_HIGHS
    assert after.equal_tolerance_bps == Decimal(5)
