from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.microstructure import (
    OrderBookLevel,
    build_orderbook_snapshot,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.liquidity_dynamics import (
    LIQUIDITY_DYNAMICS_ENGINE_VERSION,
    LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION,
    LiquidityDynamicsConfig,
    LiquidityDynamicsStatus,
    LiquiditySourceQuality,
    analyze_liquidity_dynamics,
    build_liquidity_dynamics_evidence_freeze,
)


def _levels(
    first_price: str,
    first_size: str,
    second_price: str,
    second_size: str,
) -> tuple[OrderBookLevel, ...]:
    return (
        OrderBookLevel(
            price=Decimal(first_price),
            size=Decimal(first_size),
        ),
        OrderBookLevel(
            price=Decimal(second_price),
            size=Decimal(second_size),
        ),
    )


def _book(
    *,
    event_at_ms: int,
    sequence: int,
    bids: tuple[OrderBookLevel, ...],
    asks: tuple[OrderBookLevel, ...],
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
        bids=bids,
        asks=asks,
        source=DataSource.WEBSOCKET,
        adapter_version="liquidity-dynamics-test/1",
    )


def _history():
    return (
        _book(
            event_at_ms=8_000,
            sequence=1,
            bids=_levels("100", "2", "99", "1"),
            asks=_levels("101", "1", "102", "1"),
        ),
        _book(
            event_at_ms=9_000,
            sequence=2,
            bids=_levels("100", "3", "99", "0.5"),
            asks=_levels("101", "0.5", "103", "1"),
        ),
        _book(
            event_at_ms=10_000,
            sequence=3,
            bids=_levels("100", "1", "98", "2"),
            asks=_levels("101", "1.5", "102", "1"),
        ),
    )


def _config(**overrides):
    payload = {
        "depth_levels": 2,
        "lookback_ms": 3_000,
        "minimum_snapshots": 3,
        "max_snapshot_age_ms": 1_000,
        "max_snapshot_gap_ms": 1_500,
    }
    payload.update(overrides)
    return LiquidityDynamicsConfig(**payload)


def test_temporal_liquidity_metrics_are_deterministic_and_frozen() -> None:
    books = _history()
    config = _config()

    first = build_liquidity_dynamics_evidence_freeze(
        books,
        as_of_ms=10_050,
        config=config,
    )
    second = build_liquidity_dynamics_evidence_freeze(
        tuple(reversed(books)),
        as_of_ms=10_050,
        config=config,
    )

    assert first == second
    assert first.schema_version == LIQUIDITY_DYNAMICS_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == LIQUIDITY_DYNAMICS_ENGINE_VERSION
    assert first.analysis.status is LiquidityDynamicsStatus.MEASURED
    assert first.analysis.source_quality is LiquiditySourceQuality.GOOD
    assert first.analysis.source_window_start_ms == 7_050
    assert first.analysis.source_window_end_ms == 10_000
    assert first.analysis.consumed_snapshot_count == 3
    assert first.analysis.latest_snapshot_age_ms == 50
    assert first.analysis.first_snapshot_identity == books[0].snapshot_identity
    assert first.analysis.last_snapshot_identity == books[-1].snapshot_identity
    assert first.analysis.uncertainty_flags == ()
    assert first.snapshots == books

    metrics = first.analysis.metrics
    assert metrics is not None
    assert metrics.depth_levels == 2
    assert metrics.snapshot_count == 3
    assert metrics.transition_count == 2
    assert metrics.duration_ms == 2_000

    assert metrics.first_bid_depth_notional == Decimal(299)
    assert metrics.last_bid_depth_notional == Decimal(296)
    assert metrics.first_ask_depth_notional == Decimal(203)
    assert metrics.last_ask_depth_notional == Decimal("253.5")

    assert metrics.gross_bid_added_notional == Decimal(296)
    assert metrics.gross_bid_removed_notional == Decimal(299)
    assert metrics.gross_ask_added_notional == Decimal(306)
    assert metrics.gross_ask_removed_notional == Decimal("255.5")
    assert metrics.net_bid_depth_change_notional == Decimal(-3)
    assert metrics.net_ask_depth_change_notional == Decimal("50.5")

    assert metrics.bid_added_notional_per_second == Decimal(148)
    assert metrics.bid_removed_notional_per_second == Decimal("149.5")
    assert metrics.ask_added_notional_per_second == Decimal(153)
    assert metrics.ask_removed_notional_per_second == Decimal("127.75")
    assert metrics.bid_depth_change_notional_per_second == Decimal("-1.5")
    assert metrics.ask_depth_change_notional_per_second == Decimal("25.25")

    assert metrics.best_bid_depletion_notional == Decimal(200)
    assert metrics.best_bid_replenishment_notional == Decimal(100)
    assert metrics.best_ask_depletion_notional == Decimal("50.5")
    assert metrics.best_ask_replenishment_notional == Decimal(101)
    assert metrics.best_bid_price_persistence_fraction == Decimal(1)
    assert metrics.best_ask_price_persistence_fraction == Decimal(1)
    assert len(first.analysis.evidence_identity) == 64
    assert len(first.freeze_identity) == 64


def test_future_or_late_ingested_snapshot_cannot_rewrite_historical_freeze() -> None:
    books = _history()
    baseline = build_liquidity_dynamics_evidence_freeze(
        books,
        as_of_ms=10_050,
        config=_config(),
    )
    future = _book(
        event_at_ms=10_100,
        sequence=4,
        bids=_levels("100", "100", "99", "100"),
        asks=_levels("101", "100", "102", "100"),
    )
    late = _book(
        event_at_ms=9_500,
        sequence=5,
        bids=_levels("100", "100", "99", "100"),
        asks=_levels("101", "100", "102", "100"),
        ingested_at_ms=10_100,
    )

    with_unsafe_evidence = build_liquidity_dynamics_evidence_freeze(
        (*books, future, late),
        as_of_ms=10_050,
        config=_config(),
    )

    assert with_unsafe_evidence == baseline
    assert future not in with_unsafe_evidence.snapshots
    assert late not in with_unsafe_evidence.snapshots


@pytest.mark.parametrize(
    ("books", "as_of_ms", "config", "expected_flag"),
    [
        (
            _history()[:2],
            9_050,
            _config(),
            "insufficient_orderbook_snapshots",
        ),
        (
            _history(),
            12_000,
            _config(lookback_ms=5_000, max_snapshot_age_ms=500),
            "stale_latest_orderbook",
        ),
        (
            (
                _history()[0],
                _book(
                    event_at_ms=10_000,
                    sequence=2,
                    bids=_levels("100", "1", "99", "1"),
                    asks=_levels("101", "1", "102", "1"),
                ),
                _book(
                    event_at_ms=10_100,
                    sequence=3,
                    bids=_levels("100", "1", "99", "1"),
                    asks=_levels("101", "1", "102", "1"),
                ),
            ),
            10_150,
            _config(lookback_ms=3_000, max_snapshot_gap_ms=500),
            "snapshot_gap_exceeds_limit",
        ),
        (
            (
                _book(
                    event_at_ms=8_000,
                    sequence=1,
                    bids=(OrderBookLevel(price=Decimal(100), size=Decimal(1)),),
                    asks=(OrderBookLevel(price=Decimal(101), size=Decimal(1)),),
                ),
                _book(
                    event_at_ms=9_000,
                    sequence=2,
                    bids=(OrderBookLevel(price=Decimal(100), size=Decimal(1)),),
                    asks=(OrderBookLevel(price=Decimal(101), size=Decimal(1)),),
                ),
                _book(
                    event_at_ms=10_000,
                    sequence=3,
                    bids=(OrderBookLevel(price=Decimal(100), size=Decimal(1)),),
                    asks=(OrderBookLevel(price=Decimal(101), size=Decimal(1)),),
                ),
            ),
            10_050,
            _config(),
            "insufficient_orderbook_depth",
        ),
    ],
)
def test_degraded_source_is_unresolved_without_fabricated_metrics(
    books,
    as_of_ms: int,
    config: LiquidityDynamicsConfig,
    expected_flag: str,
) -> None:
    result = analyze_liquidity_dynamics(
        books,
        as_of_ms=as_of_ms,
        config=config,
    )

    assert result.status is LiquidityDynamicsStatus.UNRESOLVED
    assert result.source_quality is LiquiditySourceQuality.DEGRADED
    assert result.metrics is None
    assert expected_flag in result.uncertainty_flags


def test_no_safe_snapshot_is_unavailable_and_pit_bounded() -> None:
    future = _book(
        event_at_ms=10_100,
        sequence=1,
        bids=_levels("100", "1", "99", "1"),
        asks=_levels("101", "1", "102", "1"),
    )

    result = analyze_liquidity_dynamics(
        (future,),
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.status is LiquidityDynamicsStatus.UNRESOLVED
    assert result.source_quality is LiquiditySourceQuality.UNAVAILABLE
    assert result.metrics is None
    assert result.consumed_snapshot_count == 0
    assert result.source_window_end_ms is None
    assert result.first_snapshot_identity is None
    assert result.last_snapshot_identity is None
    assert result.uncertainty_flags == ("orderbook_unavailable_at_as_of",)


def test_duplicate_and_mixed_context_fail_closed() -> None:
    book = _history()[0]

    with pytest.raises(ValueError, match="duplicate orderbook snapshot identity"):
        analyze_liquidity_dynamics(
            (book, book),
            as_of_ms=10_000,
            config=_config(minimum_snapshots=2),
        )

    eth = _book(
        event_at_ms=9_000,
        sequence=2,
        symbol="ETHUSDT",
        bids=_levels("100", "1", "99", "1"),
        asks=_levels("101", "1", "102", "1"),
    )
    with pytest.raises(ValueError, match="one market context"):
        analyze_liquidity_dynamics(
            (book, eth),
            as_of_ms=10_000,
            config=_config(minimum_snapshots=2),
        )


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    freeze = build_liquidity_dynamics_evidence_freeze(
        _history(),
        as_of_ms=10_050,
        config=_config(),
    )

    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_m2_liquidity_slice_is_observation_only_and_avoids_intent_claims() -> None:
    assert set(LiquidityDynamicsStatus) == {
        LiquidityDynamicsStatus.MEASURED,
        LiquidityDynamicsStatus.UNRESOLVED,
    }

    source = (
        Path(__file__).resolve().parents[1]
        / "src/crypto_signal/intelligence/liquidity_dynamics.py"
    ).read_text()
    assert "spoofing" not in source.lower()
    assert "manipulation" not in source.lower()
    assert "institution" not in source.lower()
    assert "iceberg" not in source.lower()
