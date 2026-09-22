from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.microstructure import OrderBookLevel, build_orderbook_snapshot
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.liquidity_dynamics import LiquiditySourceQuality
from crypto_signal.intelligence.liquidity_structure import (
    LIQUIDITY_STRUCTURE_ENGINE_VERSION,
    LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION,
    LiquidityLevelCandidate,
    LiquiditySide,
    LiquidityStructureConfig,
    LiquidityStructureStatus,
    analyze_liquidity_structure,
    build_liquidity_structure_evidence_freeze,
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
    bids: list[tuple[str, str]],
    asks: list[tuple[str, str]],
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
        bids=_levels(bids),
        asks=_levels(asks),
        source=DataSource.WEBSOCKET,
        adapter_version="liquidity-structure-test/1",
    )


def _config(**overrides):
    payload = {
        "depth_levels": 3,
        "lookback_ms": 10_000,
        "minimum_snapshots": 5,
        "max_snapshot_age_ms": 1_000,
        "max_snapshot_gap_ms": 2_000,
        "persistent_presence_fraction": Decimal("0.60"),
        "material_notional_multiple": Decimal("1.50"),
        "approach_bps": Decimal(100),
        "rapid_withdrawal_max_lifetime_ms": 5_000,
        "rapid_withdrawal_min_fraction": Decimal("0.80"),
        "hidden_liquidity_min_replenishment_cycles": 2,
        "hidden_liquidity_min_replenishment_fraction": Decimal("0.50"),
    }
    payload.update(overrides)
    return LiquidityStructureConfig(**payload)


def _persistent_history():
    return tuple(
        _book(
            event_at_ms=8_000 + index * 1_000,
            sequence=index + 1,
            bids=[
                ("100", str(10 + index)),
                ("99", "1"),
                ("98", "1"),
            ],
            asks=[
                ("101", "1"),
                ("102", "1"),
                ("103", "1"),
            ],
        )
        for index in range(5)
    )


def test_persistent_pool_and_rates_are_deterministic_and_frozen() -> None:
    books = _persistent_history()
    first = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=12_050,
        config=_config(),
    )
    second = build_liquidity_structure_evidence_freeze(
        tuple(reversed(books)),
        as_of_ms=12_050,
        config=_config(),
    )

    assert first == second
    assert first.schema_version == LIQUIDITY_STRUCTURE_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == LIQUIDITY_STRUCTURE_ENGINE_VERSION
    assert first.analysis.status is LiquidityStructureStatus.MEASURED
    assert first.analysis.source_quality is LiquiditySourceQuality.GOOD
    assert first.analysis.consumed_snapshot_count == 5
    assert first.analysis.latest_snapshot_age_ms == 50
    assert len(first.analysis.evidence_identity) == 64
    assert len(first.freeze_identity) == 64

    bid100 = next(item for item in first.analysis.bid_levels if item.price == Decimal(100))
    assert bid100.side is LiquiditySide.BID
    assert bid100.presence_fraction == Decimal(1)
    assert bid100.survival_ms == 4_000
    assert bid100.materiality_multiple > Decimal("1.50")
    assert LiquidityLevelCandidate.PERSISTENT_POOL in bid100.candidates
    assert LiquidityLevelCandidate.SPOOFING not in bid100.candidates

    assert first.analysis.bid_appearance_notional_per_second is not None
    assert first.analysis.bid_cancellation_notional_per_second == Decimal(0)
    assert first.analysis.ask_appearance_notional_per_second is not None


def test_rapid_material_withdrawal_is_only_spoofing_candidate() -> None:
    books = (
        _book(
            event_at_ms=8_000,
            sequence=1,
            bids=[("100", "1"), ("99", "1"), ("98", "1")],
            asks=[("101", "1"), ("102", "1"), ("105", "1")],
        ),
        _book(
            event_at_ms=9_000,
            sequence=2,
            bids=[("103", "1"), ("102", "1"), ("101", "1")],
            asks=[("104", "1"), ("105", "20"), ("106", "1")],
        ),
        _book(
            event_at_ms=10_000,
            sequence=3,
            bids=[("103", "1"), ("102", "1"), ("101", "1")],
            asks=[("104", "1"), ("105", "20"), ("106", "1")],
        ),
        _book(
            event_at_ms=11_000,
            sequence=4,
            bids=[("103", "1"), ("102", "1"), ("101", "1")],
            asks=[("104", "1"), ("106", "1"), ("107", "1")],
        ),
        _book(
            event_at_ms=12_000,
            sequence=5,
            bids=[("103", "1"), ("102", "1"), ("101", "1")],
            asks=[("104", "1"), ("106", "1"), ("107", "1")],
        ),
    )

    result = analyze_liquidity_structure(
        books,
        as_of_ms=12_050,
        config=_config(approach_bps=Decimal(150)),
    )
    ask105 = next(item for item in result.ask_levels if item.price == Decimal(105))
    assert LiquidityLevelCandidate.SPOOFING in ask105.candidates
    assert ask105.last_notional == Decimal(0)
    assert ask105.disappearance_count >= 1
    assert "candidate_only_no_actor_intent_attribution" in ask105.uncertainty_flags
    assert "spoofing_candidate_not_proof_of_actor_intent" in result.uncertainty_flags


def test_repeated_depletion_and_refresh_is_hidden_liquidity_candidate_only() -> None:
    sizes = ["10", "4", "10", "4", "10"]
    books = tuple(
        _book(
            event_at_ms=8_000 + index * 1_000,
            sequence=index + 1,
            bids=[("100", size), ("99", "1"), ("98", "1")],
            asks=[("101", "1"), ("102", "1"), ("103", "1")],
        )
        for index, size in enumerate(sizes)
    )

    result = analyze_liquidity_structure(
        books,
        as_of_ms=12_050,
        config=_config(),
    )
    bid100 = next(item for item in result.bid_levels if item.price == Decimal(100))
    assert bid100.replenishment_cycles == 2
    assert bid100.replenishment_notional > Decimal(0)
    assert LiquidityLevelCandidate.HIDDEN_LIQUIDITY in bid100.candidates
    assert (
        "orderbook_refresh_requires_trade_flow_confirmation"
        in bid100.uncertainty_flags
    )
    assert (
        "hidden_liquidity_candidate_requires_trade_flow_confirmation"
        in result.uncertainty_flags
    )


def test_future_and_late_ingested_books_cannot_rewrite_historical_freeze() -> None:
    books = _persistent_history()
    baseline = build_liquidity_structure_evidence_freeze(
        books,
        as_of_ms=12_050,
        config=_config(),
    )
    future = _book(
        event_at_ms=12_100,
        sequence=99,
        bids=[("100", "100"), ("99", "1"), ("98", "1")],
        asks=[("101", "100"), ("102", "1"), ("103", "1")],
    )
    late = _book(
        event_at_ms=11_500,
        sequence=100,
        bids=[("100", "100"), ("99", "1"), ("98", "1")],
        asks=[("101", "100"), ("102", "1"), ("103", "1")],
        ingested_at_ms=12_100,
    )
    with_unsafe = build_liquidity_structure_evidence_freeze(
        (*books, future, late),
        as_of_ms=12_050,
        config=_config(),
    )
    assert with_unsafe == baseline
    assert future not in with_unsafe.snapshots
    assert late not in with_unsafe.snapshots


@pytest.mark.parametrize(
    ("books", "as_of_ms", "config", "flag"),
    [
        (
            _persistent_history()[:3],
            10_050,
            _config(),
            "insufficient_orderbook_snapshots",
        ),
        (
            _persistent_history(),
            15_000,
            _config(max_snapshot_age_ms=500),
            "stale_latest_orderbook",
        ),
    ],
)
def test_degraded_inputs_fail_closed_without_level_candidates(
    books,
    as_of_ms: int,
    config: LiquidityStructureConfig,
    flag: str,
) -> None:
    result = analyze_liquidity_structure(
        books,
        as_of_ms=as_of_ms,
        config=config,
    )
    assert result.status is LiquidityStructureStatus.UNRESOLVED
    assert result.source_quality is LiquiditySourceQuality.DEGRADED
    assert result.bid_levels == ()
    assert result.ask_levels == ()
    assert result.bid_appearance_notional_per_second is None
    assert flag in result.uncertainty_flags


def test_no_safe_snapshot_and_identity_tampering_fail_closed() -> None:
    future = _book(
        event_at_ms=10_100,
        sequence=1,
        bids=[("100", "1"), ("99", "1"), ("98", "1")],
        asks=[("101", "1"), ("102", "1"), ("103", "1")],
    )
    result = analyze_liquidity_structure(
        (future,),
        as_of_ms=10_000,
        config=_config(),
    )
    assert result.status is LiquidityStructureStatus.UNRESOLVED
    assert result.source_quality is LiquiditySourceQuality.UNAVAILABLE
    assert result.uncertainty_flags == ("orderbook_unavailable_at_as_of",)

    freeze = build_liquidity_structure_evidence_freeze(
        _persistent_history(),
        as_of_ms=12_050,
        config=_config(),
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_duplicate_and_mixed_context_fail_closed() -> None:
    book = _persistent_history()[0]
    with pytest.raises(ValueError, match="duplicate orderbook snapshot identity"):
        analyze_liquidity_structure(
            (book, book),
            as_of_ms=10_000,
            config=_config(minimum_snapshots=3),
        )

    eth = _book(
        event_at_ms=9_000,
        sequence=2,
        symbol="ETHUSDT",
        bids=[("100", "1"), ("99", "1"), ("98", "1")],
        asks=[("101", "1"), ("102", "1"), ("103", "1")],
    )
    with pytest.raises(ValueError, match="one market context"):
        analyze_liquidity_structure(
            (book, eth),
            as_of_ms=10_000,
            config=_config(minimum_snapshots=3),
        )


def test_candidate_semantics_do_not_assert_proven_manipulation_or_actor() -> None:
    source = __import__(
        "crypto_signal.intelligence.liquidity_structure",
        fromlist=["dummy"],
    )
    path = source.__file__
    assert path is not None
    with open(path, encoding="utf-8") as handle:
        text = handle.read().lower()
    assert "market maker manipulation proven" not in text
    assert "institutional actor confirmed" not in text
    assert "guaranteed spoofing" not in text
