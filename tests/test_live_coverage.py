from __future__ import annotations

from typing import cast

import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.coverage import (
    LiveCoverageContext,
    LiveCoveragePlan,
    LiveCoverageSourceStrategy,
)


def test_current_pilot_enables_focused_multi_asset_timeframe_scope() -> None:
    plan = LiveCoveragePlan.current_pilot()

    assert plan.version == "live-coverage-v1/3"
    assert [item.identity for item in plan.enabled_contexts] == [
        ("bybit", "spot", "BTCUSDT", "15m"),
        ("bybit", "spot", "BTCUSDT", "1h"),
        ("bybit", "spot", "BTCUSDT", "4h"),
        ("bybit", "spot", "ETHUSDT", "15m"),
        ("bybit", "spot", "ETHUSDT", "1h"),
        ("bybit", "spot", "ETHUSDT", "4h"),
        ("bybit", "spot", "SOLUSDT", "15m"),
        ("bybit", "spot", "SOLUSDT", "1h"),
        ("bybit", "spot", "SOLUSDT", "4h"),
        ("binance", "spot", "BTCUSDT", "15m"),
        ("binance", "spot", "BTCUSDT", "1h"),
        ("binance", "spot", "BTCUSDT", "4h"),
        ("binance", "spot", "ETHUSDT", "15m"),
        ("binance", "spot", "ETHUSDT", "1h"),
        ("binance", "spot", "ETHUSDT", "4h"),
        ("binance", "spot", "SOLUSDT", "15m"),
        ("binance", "spot", "SOLUSDT", "1h"),
        ("binance", "spot", "SOLUSDT", "4h"),
    ]
    base = [item for item in plan.enabled_contexts if item.timeframe == "15m"]
    higher = [item for item in plan.enabled_contexts if item.timeframe != "15m"]
    assert all(
        item.source_strategy
        is LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
        for item in base
    )
    assert all(
        item.source_strategy
        is LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
        and item.freeze_limit == 120
        and item.minimum_closed_candles == 100
        for item in higher
    )
    assert plan.enabled_base_15m_budget_per_run == 17_400

def test_higher_timeframe_requires_canonical_15m_aggregation() -> None:
    with pytest.raises(
        ValueError,
        match="higher-timeframe coverage must aggregate canonical 15m",
    ):
        LiveCoverageContext(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="1h",
            source_strategy=(
                LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
            ),
        )


def test_base_timeframe_requires_direct_canonical_source() -> None:
    with pytest.raises(
        ValueError,
        match="15m coverage must use direct canonical 15m source",
    ):
        LiveCoverageContext(
            exchange=Exchange.BYBIT,
            market_type=MarketType.SPOT,
            symbol="BTCUSDT",
            timeframe="15m",
            source_strategy=(
                LiveCoverageSourceStrategy.AGGREGATE_CANONICAL_15M
            ),
        )


def test_plan_rejects_duplicate_market_context() -> None:
    item = LiveCoverageContext(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        source_strategy=(
            LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
        ),
    )
    with pytest.raises(
        ValueError,
        match="contexts must be unique",
    ):
        LiveCoveragePlan(
            version="duplicate/1",
            contexts=(item, item),
        )


def test_timeframe_candidate_plan_keeps_expansion_disabled() -> None:
    plan = LiveCoveragePlan.post_v1_timeframe_candidates()

    assert len(plan.contexts) == 10
    assert len(plan.enabled_contexts) == 2
    assert {item.timeframe for item in plan.enabled_contexts} == {"15m"}
    assert {
        item.timeframe
        for item in plan.contexts
        if not item.enabled
    } == {"1h", "4h", "1D", "1W"}


def test_higher_timeframe_base_history_cost_is_explicit() -> None:
    contexts = {
        item.timeframe: item
        for item in LiveCoveragePlan.post_v1_timeframe_candidates().contexts
        if item.exchange is Exchange.BYBIT
    }

    assert contexts["15m"].base_15m_candles_for_freeze_limit == 500
    assert contexts["1h"].base_15m_candles_for_freeze_limit == 2_000
    assert contexts["4h"].base_15m_candles_for_freeze_limit == 8_000
    assert contexts["1D"].base_15m_candles_for_freeze_limit == 48_000
    assert contexts["1W"].base_15m_candles_for_freeze_limit == 336_000

    assert contexts["1W"].base_15m_candles_for_minimum_history == 67_200


def test_non_spot_activation_is_rejected_until_data_truth_contract_exists() -> None:
    with pytest.raises(
        ValueError,
        match="currently supports Spot only",
    ):
        LiveCoverageContext(
            exchange=Exchange.BYBIT,
            market_type=cast(MarketType, "perpetual"),
            symbol="BTCUSDT",
            timeframe="15m",
            source_strategy=(
                LiveCoverageSourceStrategy.DIRECT_CANONICAL_15M
            ),
        )
