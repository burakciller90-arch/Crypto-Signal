from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.liquidity_structure import (
    LiquiditySide,
    LiquidityStructureConfig,
)
from crypto_signal.intelligence.liquidity_sweep import (
    LIQUIDITY_SWEEP_ENGINE_VERSION,
    LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION,
    LiquiditySweepConfig,
    LiquiditySweepState,
    LiquiditySweepStatus,
    analyze_liquidity_sweeps,
    build_liquidity_sweep_evidence_freeze,
)


def _levels(items: list[tuple[str, str]]) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(price=Decimal(price), size=Decimal(size))
        for price, size in items
    )


def _book(
    *,
    event_at_ms: int,
    sequence: int,
    bid_size: str = "10",
    ask_size: str = "1",
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
):
    source_ms = event_at_ms + 10
    response_ms = source_ms + 10
    ingest_ms = response_ms + 10 if ingested_at_ms is None else ingested_at_ms
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_ms,
        response_time_ms=response_ms,
        ingested_at_ms=ingest_ms,
        update_id=sequence,
        sequence=sequence,
        bids=_levels([("100", bid_size), ("99", "1"), ("98", "1")]),
        asks=_levels([("101", ask_size), ("102", "1"), ("103", "1")]),
        source=DataSource.WEBSOCKET,
        adapter_version="liquidity-sweep-test/1",
    )


def _trade(
    *,
    event_at_ms: int,
    sequence: int,
    side: AggressorSide,
    price: str,
    size: str,
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
    is_block_trade: bool = False,
    is_rpi_trade: bool = False,
):
    source_ms = event_at_ms + 5
    ingest_ms = source_ms + 5 if ingested_at_ms is None else ingested_at_ms
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        exec_id=f"exec-{sequence}",
        sequence=sequence,
        aggressor_side=side,
        price=Decimal(price),
        size=Decimal(size),
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingest_ms,
        is_block_trade=is_block_trade,
        is_rpi_trade=is_rpi_trade,
        source=DataSource.WEBSOCKET,
        adapter_version="liquidity-sweep-test/1",
    )


def _structure_config() -> LiquidityStructureConfig:
    return LiquidityStructureConfig(
        depth_levels=3,
        lookback_ms=10_000,
        minimum_snapshots=5,
        max_snapshot_age_ms=1_000,
        max_snapshot_gap_ms=2_000,
        persistent_presence_fraction=Decimal("0.60"),
        material_notional_multiple=Decimal("1.50"),
        approach_bps=Decimal(100),
        rapid_withdrawal_max_lifetime_ms=5_000,
        rapid_withdrawal_min_fraction=Decimal("0.80"),
        hidden_liquidity_min_replenishment_cycles=2,
        hidden_liquidity_min_replenishment_fraction=Decimal("0.50"),
    )


def _config(**overrides) -> LiquiditySweepConfig:
    payload = {
        "lookback_ms": 10_000,
        "minimum_orderbook_snapshots": 5,
        "minimum_public_trades": 3,
        "max_snapshot_age_ms": 1_000,
        "max_trade_age_ms": 2_500,
        "max_snapshot_gap_ms": 2_000,
        "pool_touch_tolerance_bps": Decimal(10),
        "max_pool_interaction_distance_bps": Decimal(150),
        "minimum_depth_depletion_fraction": Decimal("0.20"),
        "minimum_aggressor_share": Decimal("0.60"),
        "minimum_displacement_bps": Decimal(20),
        "minimum_follow_through_trades": 1,
        "recovery_tolerance_bps": Decimal(10),
        "structure_config": _structure_config(),
    }
    payload.update(overrides)
    return LiquiditySweepConfig(**payload)


def _depleting_books():
    sizes = ["10", "8", "5", "2", "1"]
    return tuple(
        _book(
            event_at_ms=8_000 + index * 1_000,
            sequence=index + 1,
            bid_size=size,
        )
        for index, size in enumerate(sizes)
    )


def _bid_sweep_trades():
    return (
        _trade(
            event_at_ms=10_300,
            sequence=1,
            side=AggressorSide.SELL,
            price="100",
            size="4",
        ),
        _trade(
            event_at_ms=10_500,
            sequence=2,
            side=AggressorSide.SELL,
            price="99.70",
            size="4",
        ),
        _trade(
            event_at_ms=10_700,
            sequence=3,
            side=AggressorSide.SELL,
            price="99.40",
            size="4",
        ),
        _trade(
            event_at_ms=10_900,
            sequence=4,
            side=AggressorSide.SELL,
            price="99.20",
            size="3",
        ),
        _trade(
            event_at_ms=11_200,
            sequence=5,
            side=AggressorSide.BUY,
            price="100.05",
            size="1",
        ),
    )


def test_bid_sweep_candidate_requires_pool_depletion_flow_displacement_and_followthrough() -> None:
    books = _depleting_books()
    trades = _bid_sweep_trades()

    freeze = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=12_050,
        config=_config(),
    )

    result = freeze.analysis
    assert freeze.schema_version == LIQUIDITY_SWEEP_FREEZE_SCHEMA_VERSION
    assert result.engine_version == LIQUIDITY_SWEEP_ENGINE_VERSION
    assert result.status is LiquiditySweepStatus.MEASURED
    assert result.sweep_state is LiquiditySweepState.BID_SIDE_CANDIDATE
    assert result.evaluated_persistent_pool_count >= 1
    assert len(result.candidates) == 1

    candidate = result.candidates[0]
    assert candidate.side is LiquiditySide.BID
    assert candidate.pool_price == Decimal(100)
    assert candidate.depth_depletion_fraction >= Decimal("0.20")
    assert candidate.aggressor_share >= Decimal("0.60")
    assert candidate.max_displacement_bps >= Decimal(20)
    assert candidate.follow_through_trade_count >= 1
    assert candidate.recovered is True
    assert candidate.recovery_at_ms == 11_200
    assert candidate.uncertainty_flags == (
        "candidate_only_not_stop_hunt_proof",
        "public_trade_flow_does_not_identify_actor_intent",
    )
    assert "liquidity_sweep_candidate_not_stop_hunt_proof" in result.uncertainty_flags
    assert len(result.evidence_identity) == 64
    assert len(freeze.freeze_identity) == 64


def test_ordering_is_deterministic_and_future_or_late_trades_cannot_rewrite_freeze() -> None:
    books = _depleting_books()
    trades = _bid_sweep_trades()
    baseline = build_liquidity_sweep_evidence_freeze(
        books,
        trades,
        as_of_ms=12_050,
        config=_config(),
    )

    future = _trade(
        event_at_ms=12_100,
        sequence=99,
        side=AggressorSide.SELL,
        price="90",
        size="100",
    )
    late = _trade(
        event_at_ms=10_600,
        sequence=100,
        side=AggressorSide.SELL,
        price="90",
        size="100",
        ingested_at_ms=12_100,
    )
    changed_order = build_liquidity_sweep_evidence_freeze(
        tuple(reversed(books)),
        tuple(reversed((*trades, future, late))),
        as_of_ms=12_050,
        config=_config(),
    )

    assert changed_order == baseline
    assert future not in changed_order.trades
    assert late not in changed_order.trades


def test_level_touch_without_depth_depletion_is_not_sweep_candidate() -> None:
    books = tuple(
        _book(event_at_ms=8_000 + index * 1_000, sequence=index + 1)
        for index in range(5)
    )
    result = analyze_liquidity_sweeps(
        books,
        _bid_sweep_trades(),
        as_of_ms=12_050,
        config=_config(),
    )

    assert result.status is LiquiditySweepStatus.MEASURED
    assert result.sweep_state is LiquiditySweepState.NONE
    assert result.candidates == ()
    assert "no_qualified_liquidity_sweep_candidate" in result.uncertainty_flags


def test_weak_aggressive_flow_is_not_sweep_candidate() -> None:
    trades = (
        _trade(
            event_at_ms=10_300,
            sequence=1,
            side=AggressorSide.SELL,
            price="99.70",
            size="1",
        ),
        _trade(
            event_at_ms=10_500,
            sequence=2,
            side=AggressorSide.BUY,
            price="99.60",
            size="10",
        ),
        _trade(
            event_at_ms=10_700,
            sequence=3,
            side=AggressorSide.BUY,
            price="99.40",
            size="10",
        ),
    )
    result = analyze_liquidity_sweeps(
        _depleting_books(),
        trades,
        as_of_ms=12_050,
        config=_config(max_trade_age_ms=2_000),
    )

    assert result.status is LiquiditySweepStatus.MEASURED
    assert result.sweep_state is LiquiditySweepState.NONE
    assert result.candidates == ()


@pytest.mark.parametrize(
    ("trades", "as_of_ms", "config", "expected_flag"),
    [
        (
            _bid_sweep_trades()[:2],
            12_050,
            _config(),
            "insufficient_public_trades",
        ),
        (
            _bid_sweep_trades(),
            15_000,
            _config(max_snapshot_age_ms=5_000, max_trade_age_ms=500),
            "stale_latest_public_trade",
        ),
    ],
)
def test_degraded_trade_evidence_fails_closed(
    trades,
    as_of_ms: int,
    config: LiquiditySweepConfig,
    expected_flag: str,
) -> None:
    result = analyze_liquidity_sweeps(
        _depleting_books(),
        trades,
        as_of_ms=as_of_ms,
        config=config,
    )

    assert result.status is LiquiditySweepStatus.UNRESOLVED
    assert result.sweep_state is LiquiditySweepState.UNAVAILABLE
    assert result.candidates == ()
    assert expected_flag in result.uncertainty_flags


def test_block_and_rpi_trades_do_not_create_book_sweep_evidence() -> None:
    trades = (
        _trade(
            event_at_ms=10_300,
            sequence=1,
            side=AggressorSide.SELL,
            price="99.5",
            size="10",
            is_block_trade=True,
        ),
        _trade(
            event_at_ms=10_500,
            sequence=2,
            side=AggressorSide.SELL,
            price="99.4",
            size="10",
            is_rpi_trade=True,
        ),
        _trade(
            event_at_ms=10_700,
            sequence=3,
            side=AggressorSide.SELL,
            price="99.3",
            size="10",
            is_block_trade=True,
        ),
    )
    result = analyze_liquidity_sweeps(
        _depleting_books(),
        trades,
        as_of_ms=12_050,
        config=_config(),
    )

    assert result.status is LiquiditySweepStatus.UNRESOLVED
    assert result.consumed_trade_count == 0
    assert "public_trade_unavailable_at_as_of" in result.uncertainty_flags


def test_duplicate_and_mixed_context_fail_closed() -> None:
    book = _depleting_books()[0]
    with pytest.raises(ValueError, match="duplicate liquidity sweep snapshot identity"):
        analyze_liquidity_sweeps(
            (book, book),
            _bid_sweep_trades(),
            as_of_ms=12_050,
            config=_config(),
        )

    trade = _bid_sweep_trades()[0]
    with pytest.raises(ValueError, match="duplicate liquidity sweep trade identity"):
        analyze_liquidity_sweeps(
            _depleting_books(),
            (trade, trade),
            as_of_ms=12_050,
            config=_config(),
        )

    eth_trade = _trade(
        event_at_ms=10_300,
        sequence=11,
        side=AggressorSide.SELL,
        price="99.5",
        size="1",
        symbol="ETHUSDT",
    )
    with pytest.raises(ValueError, match="one market context"):
        analyze_liquidity_sweeps(
            _depleting_books(),
            (*_bid_sweep_trades(), eth_trade),
            as_of_ms=12_050,
            config=_config(),
        )


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    freeze = build_liquidity_sweep_evidence_freeze(
        _depleting_books(),
        _bid_sweep_trades(),
        as_of_ms=12_050,
        config=_config(),
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_sweep_engine_does_not_claim_stop_hunt_or_manipulation_as_proven() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src/crypto_signal/intelligence/liquidity_sweep.py"
    )
    source = path.read_text(encoding="utf-8").lower()
    assert "stop hunt proven" not in source
    assert "market maker manipulation proven" not in source
    assert "institutional actor confirmed" not in source
    assert "guaranteed sweep" not in source
