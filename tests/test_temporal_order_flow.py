from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from crypto_signal.data.microstructure import (
    AggressorSide,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.intelligence.temporal_order_flow import (
    ENGINE_VERSION,
    FREEZE_SCHEMA_VERSION,
    TemporalFlowConfig,
    TemporalFlowQuality,
    TemporalFlowStatus,
    analyze_temporal_order_flow,
    build_temporal_order_flow_freeze,
)


def _trade(
    seq: int,
    at_ms: int,
    side: AggressorSide,
    price: str,
    size: str,
    *,
    symbol: str = "BTCUSDT",
    ingest_ms: int | None = None,
    block: bool = False,
    rpi: bool = False,
):
    return build_public_trade_observation(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol=symbol,
        exec_id=f"m3-{seq}",
        sequence=seq,
        aggressor_side=side,
        price=Decimal(price),
        size=Decimal(size),
        event_at_ms=at_ms,
        source_timestamp_ms=at_ms + 5,
        ingested_at_ms=at_ms + 10 if ingest_ms is None else ingest_ms,
        is_block_trade=block,
        is_rpi_trade=rpi,
        source=DataSource.WEBSOCKET,
        adapter_version="m3-temporal-test/1",
    )


def _trades():
    return (
        _trade(1, 8_000, AggressorSide.BUY, "100", "2"),
        _trade(2, 8_500, AggressorSide.SELL, "100", "1"),
        _trade(3, 9_250, AggressorSide.BUY, "101", "3"),
        _trade(4, 10_000, AggressorSide.SELL, "101", "2"),
        _trade(5, 11_500, AggressorSide.BUY, "102", "1"),
    )


def _config(**overrides):
    values = {
        "window_ms": 5_000,
        "bucket_ms": 1_000,
        "minimum_trades": 5,
        "max_trade_age_ms": 2_500,
        "max_trade_gap_ms": 2_000,
        "large_print_min_notional": Decimal(200),
    }
    values.update(overrides)
    return TemporalFlowConfig(**values)


def test_window_local_cvd_bucket_delta_and_velocity_are_exact() -> None:
    freeze = build_temporal_order_flow_freeze(
        _trades(),
        as_of_ms=12_000,
        config=_config(),
    )
    a = freeze.analysis
    assert freeze.schema_version == FREEZE_SCHEMA_VERSION
    assert a.engine_version == ENGINE_VERSION
    assert a.status is TemporalFlowStatus.MEASURED
    assert a.quality is TemporalFlowQuality.GOOD
    assert a.consumed_trade_count == 5
    assert a.window_start_ms == 7_000
    assert a.window_end_ms == 11_500
    assert a.latest_eligible_trade_age_ms == 500
    assert a.metrics is not None
    m = a.metrics
    assert (m.buy_notional, m.sell_notional) == (Decimal(605), Decimal(302))
    assert (m.delta_notional, m.cvd_window_end_notional) == (
        Decimal(303), Decimal(303)
    )
    assert m.taker_imbalance == Decimal(303) / Decimal(907)
    assert m.large_buy_count == 2
    assert m.large_sell_count == 1
    assert m.eligible_trade_count == 5
    assert m.trade_velocity_per_second > Decimal(0)
    assert [b.bucket_start_ms for b in m.buckets] == [8_000, 9_000, 10_000, 11_000]
    assert [b.delta_notional for b in m.buckets] == [
        Decimal(100), Decimal(303), Decimal(-202), Decimal(102)
    ]
    assert [b.cvd_notional for b in m.buckets] == [
        Decimal(100), Decimal(403), Decimal(201), Decimal(303)
    ]
    assert "window_local_cvd_only" in a.uncertainty_flags
    assert len(a.evidence_identity) == len(freeze.freeze_identity) == 64


def test_input_order_is_irrelevant_to_cvd_and_freeze_identity() -> None:
    first = build_temporal_order_flow_freeze(
        _trades(), as_of_ms=12_000, config=_config()
    )
    second = build_temporal_order_flow_freeze(
        tuple(reversed(_trades())), as_of_ms=12_000, config=_config()
    )
    assert first == second


def test_block_and_rpi_are_frozen_as_excluded_source_evidence() -> None:
    block = _trade(
        6, 11_600, AggressorSide.SELL, "90", "300",
        block=True,
    )
    rpi = _trade(
        7, 11_700, AggressorSide.SELL, "90", "300",
        rpi=True,
    )
    original = analyze_temporal_order_flow(
        _trades(), as_of_ms=12_000, config=_config()
    )
    freeze = build_temporal_order_flow_freeze(
        (*_trades(), block, rpi),
        as_of_ms=12_000,
        config=_config(),
    )
    assert freeze.analysis.status is TemporalFlowStatus.MEASURED
    assert freeze.analysis.consumed_trade_count == 7
    assert freeze.analysis.metrics is not None
    assert original.metrics is not None
    assert freeze.analysis.metrics.buy_notional == original.metrics.buy_notional
    assert freeze.analysis.metrics.sell_notional == original.metrics.sell_notional
    assert freeze.analysis.metrics.excluded_trade_count == 2
    assert "block_or_rpi_excluded_from_aggressive_flow" in (
        freeze.analysis.uncertainty_flags
    )
    assert block in freeze.trades and rpi in freeze.trades


def test_future_and_late_ingested_trades_never_rewrite_historical_freeze() -> None:
    original = build_temporal_order_flow_freeze(
        _trades(), as_of_ms=12_000, config=_config()
    )
    future = _trade(8, 12_100, AggressorSide.BUY, "100", "999")
    late = _trade(
        9, 10_500, AggressorSide.SELL, "100", "999", ingest_ms=12_100
    )
    with_unsafe = build_temporal_order_flow_freeze(
        (*_trades(), future, late),
        as_of_ms=12_000,
        config=_config(),
    )
    assert with_unsafe == original
    assert future not in with_unsafe.trades
    assert late not in with_unsafe.trades


def test_no_safe_trade_fails_closed_without_metrics() -> None:
    future = _trade(9, 12_100, AggressorSide.BUY, "100", "1")
    result = analyze_temporal_order_flow(
        (future,), as_of_ms=12_000, config=_config()
    )
    assert result.status is TemporalFlowStatus.UNRESOLVED
    assert result.quality is TemporalFlowQuality.UNAVAILABLE
    assert result.metrics is None
    assert result.consumed_trade_count == 0
    assert result.uncertainty_flags[-2:] == (
        "trade_tape_unavailable_at_as_of",
        "insufficient_eligible_public_trades",
    )


@pytest.mark.parametrize(
    ("trades", "as_of", "config", "expected"),
    [
        (_trades()[:3], 12_000, _config(), "insufficient_eligible_public_trades"),
        (_trades(), 12_000, _config(max_trade_age_ms=400), "stale_latest_eligible_trade"),
        (
            _trades(),
            12_000,
            _config(max_trade_gap_ms=1_000),
            "eligible_trade_gap_exceeds_limit",
        ),
    ],
)
def test_sparse_stale_or_gapped_trade_tape_is_unresolved(
    trades, as_of: int, config: TemporalFlowConfig, expected: str
) -> None:
    result = analyze_temporal_order_flow(trades, as_of_ms=as_of, config=config)
    assert result.status is TemporalFlowStatus.UNRESOLVED
    assert result.quality is TemporalFlowQuality.DEGRADED
    assert result.metrics is None
    assert expected in result.uncertainty_flags


def test_identity_and_market_context_tampering_fail_closed() -> None:
    values = _trades()
    with pytest.raises(ValueError, match="duplicate temporal flow trade identity"):
        analyze_temporal_order_flow(
            (*values, values[0]), as_of_ms=12_000, config=_config()
        )
    eth = _trade(10, 10_500, AggressorSide.BUY, "100", "1", symbol="ETHUSDT")
    with pytest.raises(ValueError, match="mixed temporal flow market context"):
        analyze_temporal_order_flow(
            (*values, eth), as_of_ms=12_000, config=_config()
        )
    freeze = build_temporal_order_flow_freeze(
        values, as_of_ms=12_000, config=_config()
    )
    with pytest.raises(ValueError, match="freeze identity mismatch"):
        replace(freeze, freeze_identity="f" * 64)
    with pytest.raises(ValueError, match="evidence identity mismatch"):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_config_validation_and_research_scope() -> None:
    with pytest.raises(ValueError, match="bucket_ms"):
        TemporalFlowConfig(window_ms=1_000, bucket_ms=5_000)
    with pytest.raises(ValueError, match="large_print_min_notional"):
        TemporalFlowConfig(large_print_min_notional=Decimal("NaN"))
    assert _config().identity != _config(large_print_min_notional=Decimal(300)).identity
    # No trade decision, actor-intent attribution or probability is generated.
    analysis = analyze_temporal_order_flow(
        _trades(), as_of_ms=12_000, config=_config()
    )
    assert not hasattr(analysis, "trade_action")
    assert not hasattr(analysis, "win_probability")
    assert not hasattr(analysis, "institutional_actor")
