from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.models import MethodologyKind
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.intelligence.trend_momentum import (
    DEFAULT_TREND_MOMENTUM_CONFIG,
    TREND_MOMENTUM_ENGINE_VERSION,
    TREND_MOMENTUM_FREEZE_SCHEMA_VERSION,
    MomentumPhase,
    TrendMomentumConfig,
    TrendMomentumLabel,
    analyze_trend_momentum,
    build_trend_momentum_evidence_freeze,
)

_STEP_MS = 15 * 60_000


def _candle(
    *,
    index: int,
    close: Decimal,
    symbol: str = "BTCUSDT",
    ingested_at_ms: int | None = None,
    source_timestamp_ms: int | None = None,
) -> Candle:
    open_time_ms = index * _STEP_MS
    close_time_ms = open_time_ms + _STEP_MS - 1
    source_ms = (
        close_time_ms
        if source_timestamp_ms is None
        else source_timestamp_ms
    )
    ingested_ms = close_time_ms if ingested_at_ms is None else ingested_at_ms
    return Candle(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol=symbol,
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=close,
        high=close + Decimal("0.5"),
        low=close - Decimal("0.5"),
        close=close,
        volume=Decimal(1),
        quote_volume=close,
        trade_count=1,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=source_ms,
        ingested_at_ms=ingested_ms,
        adapter_version="trend-momentum-test/1",
    )


def _series(closes: list[Decimal]) -> tuple[Candle, ...]:
    return tuple(
        _candle(index=index, close=close)
        for index, close in enumerate(closes)
    )


def _as_of(candles: tuple[Candle, ...]) -> int:
    return candles[-1].close_time_ms


def test_clear_uptrend_is_deterministic_frozen_and_steady() -> None:
    candles = _series([Decimal(100 + index) for index in range(24)])

    first = build_trend_momentum_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )
    second = build_trend_momentum_evidence_freeze(
        tuple(reversed(candles)),
        as_of_ms=_as_of(candles),
    )

    assert first == second
    assert first.schema_version == TREND_MOMENTUM_FREEZE_SCHEMA_VERSION
    assert first.analysis.engine_version == TREND_MOMENTUM_ENGINE_VERSION
    assert first.analysis.label is TrendMomentumLabel.BULLISH
    assert first.analysis.phase is MomentumPhase.STEADY
    assert first.analysis.metrics is not None
    assert first.analysis.metrics.long_return_bps == Decimal(2300)
    assert first.analysis.metrics.directional_consistency_ratio == Decimal(1)
    assert first.analysis.uncertainty_flags == ()
    assert first.candles == candles
    assert len(first.freeze_identity) == 64
    assert len(first.analysis.evidence_identity) == 64


def test_clear_downtrend_is_bearish() -> None:
    candles = _series([Decimal(123 - index) for index in range(24)])

    result = analyze_trend_momentum(candles, as_of_ms=_as_of(candles))

    assert result.label is TrendMomentumLabel.BEARISH
    assert result.metrics is not None
    assert result.metrics.long_return_bps < Decimal(0)
    assert result.metrics.directional_consistency_ratio == Decimal(1)


def test_flat_market_is_neutral_without_probability_claim() -> None:
    pattern = (Decimal("100.00"), Decimal("100.05"))
    candles = _series([pattern[index % 2] for index in range(24)])

    result = analyze_trend_momentum(candles, as_of_ms=_as_of(candles))

    assert result.label is TrendMomentumLabel.NEUTRAL
    assert result.phase is MomentumPhase.FLAT
    assert result.metrics is not None
    assert result.metrics.short_to_medium_rate_ratio is None
    assert result.uncertainty_flags == ()


def test_recent_reversal_is_mixed_with_explicit_horizon_disagreement() -> None:
    closes = [Decimal(100 + index) for index in range(20)]
    closes.extend((Decimal(118), Decimal(116), Decimal(113), Decimal(109)))
    candles = _series(closes)

    result = analyze_trend_momentum(candles, as_of_ms=_as_of(candles))

    assert result.label is TrendMomentumLabel.MIXED
    assert result.phase is MomentumPhase.MIXED
    assert result.metrics is not None
    assert "horizon_direction_disagreement" in result.uncertainty_flags


def test_high_direction_but_low_long_magnitude_is_mixed_not_probability() -> None:
    candles = _series(
        [Decimal(100) + Decimal(index) / Decimal(100) for index in range(24)]
    )

    result = analyze_trend_momentum(candles, as_of_ms=_as_of(candles))

    assert result.label is TrendMomentumLabel.NEUTRAL
    assert result.metrics is not None
    assert (
        abs(result.metrics.long_return_bps)
        <= DEFAULT_TREND_MOMENTUM_CONFIG.neutral_return_max_bps
    )


def test_insufficient_history_is_explicitly_unresolved() -> None:
    candles = _series([Decimal(100 + index) for index in range(10)])

    result = analyze_trend_momentum(candles, as_of_ms=_as_of(candles))

    assert result.label is TrendMomentumLabel.UNRESOLVED
    assert result.phase is MomentumPhase.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("insufficient_history",)


def test_gap_is_unresolved_instead_of_interpolated() -> None:
    candles = list(_series([Decimal(100 + index) for index in range(24)]))
    del candles[12]
    ordered = tuple(candles)

    result = analyze_trend_momentum(ordered, as_of_ms=_as_of(ordered))

    assert result.label is TrendMomentumLabel.UNRESOLVED
    assert result.metrics is None
    assert result.uncertainty_flags == ("candle_gaps",)


def test_future_candle_cannot_change_point_in_time_freeze() -> None:
    candles = _series([Decimal(100 + index) for index in range(24)])
    as_of_ms = _as_of(candles)
    future = _candle(
        index=24,
        close=Decimal(1_000),
        ingested_at_ms=as_of_ms + _STEP_MS,
        source_timestamp_ms=as_of_ms + _STEP_MS,
    )

    baseline = build_trend_momentum_evidence_freeze(
        candles,
        as_of_ms=as_of_ms,
    )
    with_future = build_trend_momentum_evidence_freeze(
        (*candles, future),
        as_of_ms=as_of_ms,
    )

    assert with_future == baseline
    assert future not in with_future.candles


def test_freeze_and_analysis_identity_tampering_fail_closed() -> None:
    candles = _series([Decimal(100 + index) for index in range(24)])
    freeze = build_trend_momentum_evidence_freeze(
        candles,
        as_of_ms=_as_of(candles),
    )

    with pytest.raises(
        ValueError,
        match="trend/momentum freeze identity mismatch",
    ):
        replace(freeze, freeze_identity="f" * 64)

    with pytest.raises(
        ValueError,
        match="trend/momentum evidence identity mismatch",
    ):
        replace(freeze.analysis, evidence_identity="f" * 64)


def test_mixed_context_is_rejected() -> None:
    candles = list(_series([Decimal(100 + index) for index in range(24)]))
    candles[-1] = _candle(index=23, close=Decimal(123), symbol="ETHUSDT")

    with pytest.raises(ValueError, match="context mismatch"):
        analyze_trend_momentum(tuple(candles), as_of_ms=_as_of(tuple(candles)))


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="neutral return threshold"):
        TrendMomentumConfig(
            neutral_return_max_bps=Decimal(150),
            trend_return_min_bps=Decimal(100),
        )


def test_stage8_trend_momentum_is_observation_only() -> None:
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
    ):
        source = (root / relative).read_text()
        assert "crypto_signal.intelligence.trend_momentum" not in source
