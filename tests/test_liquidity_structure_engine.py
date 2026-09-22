from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.microstructure import (
    OrderBookLevel,
    OrderBookSnapshot,
    build_orderbook_snapshot,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.liquidity_dynamics import LiquiditySourceQuality
from crypto_signal.intelligence.liquidity_structure import (
    LIQUIDITY_STRUCTURE_ENGINE_VERSION,
    LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION,
    LiquidityLevelSide,
    LiquidityStructureCandidateKind,
    LiquidityStructureConfig,
    LiquidityStructureStatus,
    analyze_liquidity_structure,
    build_liquidity_structure_evidence_freeze,
)


def _levels(*items: tuple[str, str]) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(price=Decimal(price), size=Decimal(size))
        for price, size in items
    )


def _book(
    *,
    event_at_ms: int,
    sequence: int,
    bids: tuple[OrderBookLevel, ...],
    asks: tuple[OrderBookLevel, ...],
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
) -> OrderBookSnapshot:
    source_timestamp_ms = event_at_ms + 10
    response_time_ms = event_at_ms + 20
    actual_ingested_at_ms = (
        event_at_ms + 30 if ingested_at_ms is None else ingested_at_ms
    )
    return build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        event_at_ms=event_at_ms,
        source_timestamp_ms=source_timestamp_ms,
        response_time_ms=response_time_ms,
        ingested_at_ms=actual_ingested_at_ms,
        update_id=sequence,
        sequence=sequence,
        bids=bids,
        asks=asks,
        source=DataSource.WEBSOCKET,
        adapter_version="liquidity-structure-test/1",
    )


def _config(**overrides: object) -> LiquidityStructureConfig:
    payload: dict[str, object] = {
        "depth_levels": 3,
        "lookback_ms": 10_000,
        "minimum_snapshots": 5,
        "max_snapshot_age_ms": 1_000,
        "max_snapshot_gap_ms": 1_500,
        "persistent_min_presence_fraction": Decimal("0.60"),
        "minimum_pool_snapshots": 3,
        "large_level_multiplier": Decimal(3),
        "ghost_min_snapshots": 2,
        "hidden_liquidity_min_replenishments": 2,
        "shallow_depth_fraction": Decimal("0.35"),
    }
    payload.update(overrides)
    return LiquidityStructureConfig(**payload)


def _stable_asks() -> tuple[OrderBookLevel, ...]:
    return _levels(("101", "1"), ("102", "1"), ("103", "1"))


def _replenishment_history() -> tuple[OrderBookSnapshot, ...]:
    bid_sizes = ("5", "4", "6", "3", "5", "4")
    return tuple(
        _book(
            event_at_ms=5_000 + index * 1_000,
            sequence=index + 1,
            bids=_levels(
                ("100", size),
                ("99", "1"),
                ("98", "1"),
            ),
            asks=_stable_asks(),
        )
        for index, size in enumerate(bid_sizes)
    )


def test_persistent_pool_and_replenishment_candidate_are_deterministic() -> None:
    books = _replenishment_history()

    first = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=10_050,
        config=_config(),
    )
    second = build_liquidity_structure_evidence_freeze(
        tuple(reversed(books)),
        as_of_ms=10_050,
        config=_config(),
    )

    assert first == second
    assert first.schema_version == LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == LIQUIDITY_STRUCTURE_ENGINE_VERSION
    assert first.analysis.status is LiquidityStructureStatus.MEASURED
    assert first.analysis.source_quality is LiquiditySourceQuality.GOOD
    assert first.analysis.consumed_snapshot_count == 6
    assert first.analysis.latest_snapshot_age_ms == 50
    assert first.snapshots == books

    bid_100 = next(
        pool
        for pool in first.analysis.persistent_pools
        if pool.side is LiquidityLevelSide.BID and pool.price == Decimal(100)
    )
    assert bid_100.snapshots_present == 6
    assert bid_100.presence_fraction == Decimal(1)
    assert bid_100.replenishment_events == 2
    assert bid_100.latest_notional == Decimal(400)
    assert bid_100.max_notional == Decimal(600)

    hidden = next(
        item
        for item in first.analysis.candidates
        if item.kind is LiquidityStructureCandidateKind.HIDDEN_LIQUIDITY
        and item.side is LiquidityLevelSide.BID
        and item.price == Decimal(100)
    )
    assert hidden.supporting_snapshot_count == 6
    assert hidden.reason_codes == (
        "repeated_same_price_replenishment",
        "level_persisted_across_window",
    )
    assert hidden.uncertainty_flags == (
        "orderbook_only_replenishment_not_proof_of_hidden_liquidity",
    )
    assert first.analysis.uncertainty_flags == (
        "candidate_labels_are_bounded_evidence_not_actor_intent_or_causality",
    )
    assert len(first.analysis.evidence_identity) == 64
    assert len(first.freeze_identity) == 64


def test_persistent_pool_disappearance_with_quote_traversal_is_sweep_candidate() -> None:
    books = (
        _book(
            event_at_ms=5_000,
            sequence=1,
            bids=_levels(("100", "5"), ("99", "2"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=6_000,
            sequence=2,
            bids=_levels(("100", "5"), ("99", "2"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=7_000,
            sequence=3,
            bids=_levels(("100", "4"), ("99", "2"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=8_000,
            sequence=4,
            bids=_levels(("100", "3"), ("99", "2"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=9_000,
            sequence=5,
            bids=_levels(("99", "2"), ("98", "1"), ("97", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=10_000,
            sequence=6,
            bids=_levels(("98", "2"), ("97", "1"), ("96", "1")),
            asks=_stable_asks(),
        ),
    )

    result = analyze_liquidity_structure(
        books,
        as_of_ms=10_050,
        config=_config(),
    )

    candidate = next(
        item
        for item in result.candidates
        if item.kind is LiquidityStructureCandidateKind.LIQUIDITY_SWEEP
        and item.side is LiquidityLevelSide.BID
        and item.price == Decimal(100)
    )
    assert candidate.reason_codes == (
        "persistent_pool_disappeared",
        "best_quote_traversed_pool_price",
    )
    assert candidate.uncertainty_flags == (
        "orderbook_only_sweep_candidate_not_trade_causality",
    )


def test_large_transient_level_without_quote_traversal_is_ghost_order_candidate() -> None:
    normal = _stable_asks()
    transient = _levels(("101", "1"), ("102", "1"), ("105", "20"))
    books = tuple(
        _book(
            event_at_ms=5_000 + index * 1_000,
            sequence=index + 1,
            bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
            asks=transient if index in {1, 2} else normal,
        )
        for index in range(6)
    )

    result = analyze_liquidity_structure(
        books,
        as_of_ms=10_050,
        config=_config(),
    )

    candidate = next(
        item
        for item in result.candidates
        if item.kind is LiquidityStructureCandidateKind.GHOST_ORDER
        and item.side is LiquidityLevelSide.ASK
        and item.price == Decimal(105)
    )
    assert candidate.supporting_snapshot_count == 2
    assert candidate.peak_notional == Decimal(2100)
    assert candidate.reason_codes == (
        "large_transient_level_appeared",
        "level_disappeared_without_quote_traversal",
    )
    assert candidate.uncertainty_flags == (
        "orderbook_only_cannot_distinguish_cancel_reprice_or_execution",
    )


def test_relative_depth_collapse_is_shallow_book_candidate_not_prediction() -> None:
    books = tuple(
        _book(
            event_at_ms=5_000 + index * 1_000,
            sequence=index + 1,
            bids=(
                _levels(("100", "0.2"), ("99", "0.2"), ("98", "0.2"))
                if index == 5
                else _levels(("100", "5"), ("99", "5"), ("98", "5"))
            ),
            asks=_stable_asks(),
        )
        for index in range(6)
    )

    result = analyze_liquidity_structure(
        books,
        as_of_ms=10_050,
        config=_config(),
    )

    assert result.metrics is not None
    assert (
        result.metrics.latest_bid_depth_notional
        < result.metrics.median_bid_depth_notional
    )
    candidate = next(
        item
        for item in result.candidates
        if item.kind is LiquidityStructureCandidateKind.SHALLOW_BOOK
        and item.side is LiquidityLevelSide.BID
    )
    assert candidate.uncertainty_flags == (
        "relative_depth_condition_not_directional_prediction",
    )


def test_appearance_disappearance_velocities_are_explicit() -> None:
    books = (
        _book(
            event_at_ms=5_000,
            sequence=1,
            bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=6_000,
            sequence=2,
            bids=_levels(("100", "1"), ("99", "1"), ("97", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=7_000,
            sequence=3,
            bids=_levels(("100", "1"), ("98", "1"), ("97", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=8_000,
            sequence=4,
            bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=9_000,
            sequence=5,
            bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
            asks=_stable_asks(),
        ),
        _book(
            event_at_ms=10_000,
            sequence=6,
            bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
            asks=_stable_asks(),
        ),
    )

    result = analyze_liquidity_structure(
        books,
        as_of_ms=10_050,
        config=_config(),
    )
    metrics = result.metrics
    assert metrics is not None
    assert metrics.bid_appearance_events == 3
    assert metrics.bid_disappearance_events == 3
    assert metrics.bid_appearance_events_per_second == Decimal("0.6")
    assert metrics.bid_disappearance_events_per_second == Decimal("0.6")


def test_future_and_late_ingested_snapshots_cannot_rewrite_freeze() -> None:
    books = _replenishment_history()
    baseline = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=10_050,
        config=_config(),
    )
    future = _book(
        event_at_ms=10_100,
        sequence=7,
        bids=_levels(("100", "50"), ("99", "50"), ("98", "50")),
        asks=_levels(("101", "50"), ("102", "50"), ("103", "50")),
    )
    late = _book(
        event_at_ms=9_500,
        sequence=8,
        bids=_levels(("100", "50"), ("99", "50"), ("98", "50")),
        asks=_levels(("101", "50"), ("102", "50"), ("103", "50")),
        ingested_at_ms=10_100,
    )

    with_unsafe = build_liquidity_structure_evidence_freeze(
        (*books, future, late),
        as_of_ms=10_050,
        config=_config(),
    )

    assert with_unsafe == baseline
    assert future not in with_unsafe.snapshots
    assert late not in with_unsafe.snapshots


@pytest.mark.parametrize(
    ("books", "as_of_ms", "config", "expected_flag"),
    [
        (
            _replenishment_history()[:4],
            8_050,
            _config(),
            "insufficient_orderbook_snapshots",
        ),
        (
            _replenishment_history(),
            12_000,
            _config(max_snapshot_age_ms=500),
            "stale_latest_orderbook",
        ),
        (
            (
                _replenishment_history()[0],
                _book(
                    event_at_ms=8_000,
                    sequence=2,
                    bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
                    asks=_stable_asks(),
                ),
                _book(
                    event_at_ms=9_000,
                    sequence=3,
                    bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
                    asks=_stable_asks(),
                ),
                _book(
                    event_at_ms=10_000,
                    sequence=4,
                    bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
                    asks=_stable_asks(),
                ),
                _book(
                    event_at_ms=10_100,
                    sequence=5,
                    bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
                    asks=_stable_asks(),
                ),
            ),
            10_150,
            _config(max_snapshot_gap_ms=500),
            "snapshot_gap_exceeds_limit",
        ),
    ],
)
def test_degraded_structure_fails_closed_without_candidates(
    books: tuple[OrderBookSnapshot, ...],
    as_of_ms: int,
    config: LiquidityStructureConfig,
    expected_flag: str,
) -> None:
    result = analyze_liquidity_structure(
        books,
        as_of_ms=as_of_ms,
        config=config,
    )

    assert result.status is LiquidityStructureStatus.UNRESOLVED
    assert result.source_quality is LiquiditySourceQuality.DEGRADED
    assert result.metrics is None
    assert result.persistent_pools == ()
    assert result.candidates == ()
    assert expected_flag in result.uncertainty_flags


def test_no_safe_snapshot_is_unavailable_and_pit_bounded() -> None:
    future = _book(
        event_at_ms=10_100,
        sequence=1,
        bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
        asks=_stable_asks(),
    )

    result = analyze_liquidity_structure(
        (future,),
        as_of_ms=10_000,
        config=_config(),
    )

    assert result.status is LiquidityStructureStatus.UNRESOLVED
    assert result.source_quality is LiquiditySourceQuality.UNAVAILABLE
    assert result.consumed_snapshot_count == 0
    assert result.source_window_end_ms is None
    assert result.first_snapshot_identity is None
    assert result.last_snapshot_identity is None
    assert result.uncertainty_flags == ("orderbook_unavailable_at_as_of",)


def test_duplicate_and_mixed_context_fail_closed() -> None:
    book = _replenishment_history()[0]

    with pytest.raises(ValueError, match="duplicate orderbook snapshot identity"):
        analyze_liquidity_structure(
            (book, book),
            as_of_ms=10_000,
            config=_config(minimum_snapshots=2),
        )

    eth = _book(
        event_at_ms=6_000,
        sequence=2,
        symbol="ETHUSDT",
        bids=_levels(("100", "1"), ("99", "1"), ("98", "1")),
        asks=_stable_asks(),
    )
    with pytest.raises(ValueError, match="one market context"):
        analyze_liquidity_structure(
            (book, eth),
            as_of_ms=10_000,
            config=_config(minimum_snapshots=2),
        )


def test_freeze_analysis_pool_and_candidate_tampering_fail_closed() -> None:
    freeze = build_liquidity_structure_evidence_freeze(
        _replenishment_history(),
        as_of_ms=10_050,
        config=_config(),
    )

    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)

    pool = next(
        item
        for item in freeze.analysis.persistent_pools
        if item.side is LiquidityLevelSide.BID and item.price == Decimal(100)
    )
    with pytest.raises(ValueError, match="pool identity mismatch"):
        replace(pool, pool_identity="f" * 64)

    candidate = next(
        item
        for item in freeze.analysis.candidates
        if item.kind is LiquidityStructureCandidateKind.HIDDEN_LIQUIDITY
    )
    with pytest.raises(ValueError, match="candidate identity mismatch"):
        replace(candidate, candidate_identity="f" * 64)


def test_candidate_language_is_bounded_and_contains_no_actor_claims() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src/crypto_signal/intelligence/liquidity_structure.py"
    ).read_text()

    assert "manipulation" not in source.lower()
    assert "institution" not in source.lower()
    assert "market maker" not in source.lower()
    assert "liquidity_sweep_candidate" in source
    assert "ghost_order_candidate" in source
    assert "hidden_liquidity_candidate" in source
    assert "not_actor_intent_or_causality" in source
